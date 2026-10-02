"""
In-process registry of workspaces, tasks, and their running agents.

Task/workspace *metadata* (id/title/status/timestamps) is mirrored to a
small JSON file under `config.WORKSPACES_ROOT` (gitignored, see
`.gitignore`'s `workspaces/` entry) so a dev-server reload does not wipe
the sidebar. Conversation *history* is a separate concern, persisted to
Redis via `server/service/memory_store.py` (one `AgentState` per task,
saved after each completed turn) — see that module's docstring for why
Redis, why `AgentState`, and why only on `ReplyEndEvent`. Before that
existed, a backend restart silently wiped every task's memory while the
sidebar still showed the task as if nothing happened; that gap is what
`AgentStateStore` closes.

The confirm/resume mechanism is the interesting part: AgentScope's
`reply_stream` yields `RequireUserConfirmEvent` and then simply ends —
resuming means calling `reply_stream` again with a `UserConfirmResultEvent`
as input (see `agentscope/agent/_agent.py`'s docstring). Because the SSE
response for `/api/chat` is a single long-lived async generator, and
`POST /api/tasks/{id}/confirm` arrives on a *different* request handled by
the same event loop, an `asyncio.Future` keyed by `reply_id` is the bridge
between them: the chat generator awaits it, the confirm endpoint resolves
it.
"""
import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from agentscope.agent import Agent

from server import config
from server.agent.core import build_agent
from server.schemas.chat import now_iso
from server.service.memory_store import agent_state_store, sanitize_agent_state

logger = logging.getLogger(__name__)


def _default_registry_path(root_dir: Path) -> Path:
    return root_dir / "registry.json"


@dataclass
class TaskRecord:
    id: str
    title: str
    workspace_id: str
    status: str = "running"
    updated_at: str = field(default_factory=now_iso)
    has_artifacts: bool = False
    is_archived: bool = False


@dataclass
class WorkspaceRecord:
    id: str
    name: str


class TaskManager:
    def __init__(self, root_dir: Path | None = None) -> None:
        # Defaulting to the production workspace root is the historical
        # behaviour, but it means any test that forgets to pass
        # ``tmp_path`` will silently write to the developer's real
        # registry and pollute their sidebar. The warning makes that
        # mistake loud rather than silent.
        if root_dir is None:
            logger.warning(
                "TaskManager using production default workspace root "
                "%s -- pass an explicit root_dir from tests to keep state "
                "isolated.",
                config.WORKSPACES_ROOT,
            )
            root_dir = config.WORKSPACES_ROOT

        self.root_dir: Path = Path(root_dir)
        self._registry_path: Path = _default_registry_path(self.root_dir)
        self._workspaces: dict[str, WorkspaceRecord] = {}
        self._tasks: dict[str, TaskRecord] = {}
        self._agents: dict[str, Agent] = {}
        self._agent_configs: dict[str, dict] = {}
        self._pending_confirms: dict[str, asyncio.Future] = {}
        self._task_locks: dict[str, asyncio.Lock] = {}
        self._load()
        self._ensure_workspace("default", "默认工作区")
        self.get_workspace_dir("default")
        self._migrate_legacy_workspaces()

    # --- workspaces & tasks -------------------------------------------------

    def _ensure_workspace(self, workspace_id: str, name: str) -> WorkspaceRecord:
        if workspace_id not in self._workspaces:
            self._workspaces[workspace_id] = WorkspaceRecord(workspace_id, name)
            self._save()
        self.get_workspace_dir(workspace_id)
        return self._workspaces[workspace_id]

    def create_workspace(self, name: str) -> WorkspaceRecord:
        """Create a new, empty workspace the user can then create tasks in.

        Unlike `create_task`, which implicitly creates whatever
        `workspace_id` it's given via `_ensure_workspace` (so passing an
        unseen id has always silently worked), this is the explicit,
        user-facing "new workspace" action — it exists so the frontend
        can offer "+ 新建工作区" without a task attached yet, and so the
        workspace gets a real display `name` distinct from its id (the
        implicit path reuses the id as the name, which is fine for
        "default" but not for anything a user types).
        """
        workspace_id = f"workspace-{len(self._workspaces) + 1}-{int(time.time() * 1000)}"
        workspace = WorkspaceRecord(id=workspace_id, name=name)
        self._workspaces[workspace_id] = workspace
        self.get_workspace_dir(workspace_id)
        self._save()
        return workspace

    def list_workspaces(self) -> list[dict]:
        tasks_by_workspace: dict[str, list[TaskRecord]] = {}
        for task in self._tasks.values():
            tasks_by_workspace.setdefault(task.workspace_id, []).append(task)

        result = []
        for workspace in self._workspaces.values():
            tasks = sorted(
                tasks_by_workspace.get(workspace.id, []),
                key=lambda t: t.updated_at,
                reverse=True,
            )
            tasks_out = []
            for t in tasks:
                t_dict = vars(t).copy()
                t_dict["workspace_path"] = str(self.workspace_dir(t.id).resolve())
                tasks_out.append(t_dict)
            result.append(
                {
                    "id": workspace.id,
                    "name": workspace.name,
                    "workspace_path": str(self.get_workspace_dir(workspace.id).resolve()),
                    "tasks": tasks_out,
                },
            )
        return result

    def create_task(self, workspace_id: str, title: str) -> TaskRecord:
        self._ensure_workspace(workspace_id, workspace_id)
        task_id = f"task-{len(self._tasks) + 1}-{int(time.time() * 1000)}"
        task = TaskRecord(id=task_id, title=title, workspace_id=workspace_id)
        self._tasks[task_id] = task
        self.workspace_dir(task_id).mkdir(parents=True, exist_ok=True)
        self.task_private_dir(task_id).mkdir(parents=True, exist_ok=True)
        self._save()
        return task

    def update_task(
        self,
        task_id: str,
        title: str | None = None,
        status: str | None = None,
        is_archived: bool | None = None,
    ) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if title is not None:
            task.title = title
        if status is not None:
            task.status = status
        if is_archived is not None:
            task.is_archived = is_archived
        task.updated_at = now_iso()
        self._save()
        return task

    def archive_task(self, task_id: str) -> TaskRecord | None:
        return self.update_task(task_id, is_archived=True)

    def mark_has_artifacts(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.has_artifacts = True
            self._save()

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def get_task_lock(self, task_id: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for the specified task_id to prevent concurrent turns."""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    async def reset_context(self, task_id: str) -> None:
        """Clear the task's persisted conversation history from Redis and cached in-memory agent."""
        self._agents.pop(task_id, None)
        self._agent_configs.pop(task_id, None)
        try:
            await agent_state_store.delete(task_id)
        except Exception:  # noqa: BLE001 - best-effort
            logger.warning(
                "Failed to clear Redis history during reset_context for %s",
                task_id,
                exc_info=True,
            )

    async def delete_task(self, task_id: str) -> bool:
        """Permanently remove a task: metadata, cached agent, persisted
        conversation history, and the task's private directory on disk.

        Note: The shared workspace directory (and all public deliverables in it)
        is preserved so other tasks in the same workspace are not impacted.
        """
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        # Clean up the task's private sandbox under .tasks/<task_id>
        private_dir = self.task_private_dir(task_id)
        shutil.rmtree(private_dir, ignore_errors=True)

        # Also clean up legacy task dir if it existed (self.root_dir / task_id)
        legacy_dir = self.root_dir / task_id
        if legacy_dir.exists() and legacy_dir.is_dir():
            shutil.rmtree(legacy_dir, ignore_errors=True)

        del self._tasks[task_id]
        self._agents.pop(task_id, None)
        self._agent_configs.pop(task_id, None)
        self._task_locks.pop(task_id, None)
        self._save()

        try:
            await agent_state_store.delete(task_id)
        except Exception:  # noqa: BLE001 - best-effort, matches save_agent_state
            logger.warning(
                "Failed to delete persisted conversation history for "
                "task %s from Redis; the task metadata and workspace "
                "files are gone regardless.",
                task_id,
                exc_info=True,
            )

        return True

    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace and, cascading, every task inside it.

        Mirrors deleting a folder on a real filesystem — its contents go
        with it. Each task is removed through `delete_task` so it gets
        the exact same cleanup (metadata, cached agent, Redis state)
        and then the shared workspace directory is removed. Returns `False`
        without touching anything if the workspace doesn't exist, or if it's
        the "default" workspace (which is protected).
        """
        if workspace_id == "default" or workspace_id not in self._workspaces:
            return False

        task_ids = [
            t.id for t in self._tasks.values() if t.workspace_id == workspace_id
        ]
        for task_id in task_ids:
            await self.delete_task(task_id)

        # Permanently remove the entire shared workspace directory
        shutil.rmtree(self.get_workspace_dir(workspace_id), ignore_errors=True)

        del self._workspaces[workspace_id]
        self._save()
        return True

    # --- workspace directories ------------------------------------------------

    def get_workspace_dir(self, workspace_id: str) -> Path:
        """Get the physical root directory for a workspace."""
        ws_dir = self.root_dir / workspace_id
        ws_dir.mkdir(parents=True, exist_ok=True)
        return ws_dir

    def workspace_dir(self, task_id: str) -> Path:
        """Return the shared workspace directory for the task's workspace."""
        task = self._tasks.get(task_id)
        workspace_id = task.workspace_id if task else "default"
        return self.get_workspace_dir(workspace_id)

    def task_private_dir(self, task_id: str) -> Path:
        """Return the private sandbox directory for a specific task."""
        task = self._tasks.get(task_id)
        workspace_id = task.workspace_id if task else "default"
        pdir = self.get_workspace_dir(workspace_id) / ".tasks" / task_id
        pdir.mkdir(parents=True, exist_ok=True)
        return pdir

    def get_workspace_wiki_dir(self, workspace_id: str) -> Path:
        """Return the physical directory path for the given workspace's wiki."""
        path = self.get_workspace_dir(workspace_id) / "wiki"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def workspace_wiki_dir(self, task_id: str) -> Path:
        """Return the physical wiki directory for the workspace that task_id belongs to."""
        task = self._tasks.get(task_id)
        workspace_id = task.workspace_id if task else "default"
        return self.get_workspace_wiki_dir(workspace_id)

    def _migrate_legacy_workspaces(self) -> None:
        """Migrate legacy per-task directories (workspaces/<task_id>/) into shared workspace directories."""
        ignored = {
            ".git",
            ".tasks",
            "sessions",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "node_modules",
        }
        for task_id, task in list(self._tasks.items()):
            legacy_dir = self.root_dir / task_id
            if legacy_dir.exists() and legacy_dir.is_dir():
                target_ws_dir = self.get_workspace_dir(task.workspace_id)
                for item in legacy_dir.iterdir():
                    if item.name.startswith(".") or item.name in ignored:
                        continue
                    target_file = target_ws_dir / item.name
                    if not target_file.exists():
                        try:
                            shutil.move(str(item), str(target_file))
                            logger.info("Migrated legacy artifact %s -> %s", item, target_file)
                        except Exception:
                            logger.warning("Failed to migrate artifact %s", item, exc_info=True)
                legacy_sessions = legacy_dir / "sessions"
                if legacy_sessions.exists() and legacy_sessions.is_dir():
                    priv_sessions = self.task_private_dir(task_id) / "sessions"
                    priv_sessions.parent.mkdir(parents=True, exist_ok=True)
                    if not priv_sessions.exists():
                        try:
                            shutil.move(str(legacy_sessions), str(priv_sessions))
                        except Exception:
                            pass
                shutil.rmtree(legacy_dir, ignore_errors=True)

        # Migrate legacy global data/wiki/ to default workspace wiki
        legacy_wiki = Path(config.REPO_ROOT) / "data" / "wiki"
        if legacy_wiki.exists() and legacy_wiki.is_dir():
            target_wiki = self.get_workspace_wiki_dir("default")
            target_wiki.mkdir(parents=True, exist_ok=True)
            for sub in ("entities", "industries", "analyses", "raw"):
                src_sub = legacy_wiki / sub
                dst_sub = target_wiki / sub
                if src_sub.exists() and src_sub.is_dir():
                    dst_sub.mkdir(parents=True, exist_ok=True)
                    for f in src_sub.iterdir():
                        dst_f = dst_sub / f.name
                        if not dst_f.exists():
                            try:
                                shutil.copy2(str(f), str(dst_f))
                            except Exception:
                                pass
            for meta_file in ("SCHEMA.md", "index.md", "log.md"):
                src_meta = legacy_wiki / meta_file
                dst_meta = target_wiki / meta_file
                if src_meta.exists() and not dst_meta.exists():
                    try:
                        shutil.copy2(str(src_meta), str(dst_meta))
                    except Exception:
                        pass

    # --- agents --------------------------------------------------------------

    async def get_or_create_agent(
        self,
        task_id: str,
        model_name: str | None = None,
        base_url: str | None = None,
        hitl_mode: str | None = None,
    ) -> Agent:
        new_config = {
            "model_name": model_name,
            "base_url": base_url,
            "hitl_mode": hitl_mode,
        }

        if task_id in self._agents:
            old_config = self._agent_configs.get(task_id, {})
            # Check if any specified setting changed from what the agent was created with
            config_changed = False
            for k, v in new_config.items():
                if v is not None and v != old_config.get(k):
                    config_changed = True
                    break

            if config_changed:
                existing_agent = self._agents[task_id]
                effective_model = model_name or old_config.get("model_name")
                effective_base = base_url or old_config.get("base_url")
                effective_hitl = hitl_mode or old_config.get("hitl_mode")
                self._agents[task_id] = await build_agent(
                    self.workspace_dir(task_id),
                    state=existing_agent.state,
                    model_name=effective_model,
                    base_url=effective_base,
                    hitl_mode=effective_hitl,
                )
                self._agent_configs[task_id] = {
                    "model_name": effective_model,
                    "base_url": effective_base,
                    "hitl_mode": effective_hitl,
                }
            return self._agents[task_id]

        saved_state = await agent_state_store.load(task_id)
        self._agents[task_id] = await build_agent(
            self.workspace_dir(task_id),
            state=saved_state,
            model_name=model_name,
            base_url=base_url,
            hitl_mode=hitl_mode,
        )
        self._agent_configs[task_id] = new_config
        return self._agents[task_id]

    async def save_agent_state(self, task_id: str) -> None:
        """Persist the task's current conversation history.

        Called once per completed turn (`ReplyEndEvent`, see
        `server/main.py`) rather than after every SSE frame — see
        `memory_store.py`'s docstring for why mid-turn snapshots (e.g.
        while a tool call awaits HITL confirmation) are deliberately
        avoided. A no-op if the agent was never built for this task
        (e.g. `/api/chat` was never called), so callers don't need to
        guard the call themselves.

        Failures here are logged, not raised: by the time this runs, the
        turn's SSE frames — including the `done` frame the translator
        emits for `ReplyEndEvent` — have already been sent to the client,
        so letting a Redis hiccup propagate would only make `main.py`'s
        outer `except Exception` send a second, spurious `done`/error
        frame after an otherwise-successful reply. `get_or_create_agent`'s
        *load* deliberately does NOT get this same treatment — a failure
        to read history when a conversation is starting is worth
        surfacing to the user as a real error, not silently proceeding as
        if there had never been any history at all.
        """
        agent = self._agents.get(task_id)
        if agent is None:
            return
        try:
            sanitize_agent_state(agent.state)
            await agent_state_store.save(task_id, agent.state)
        except Exception:  # noqa: BLE001 - best-effort, see docstring
            logger.warning(
                "Failed to persist conversation history for task %s; "
                "this turn's reply already reached the client, so "
                "continuing without persisting it rather than erroring.",
                task_id,
                exc_info=True,
            )

    # --- HITL confirm bridge ---------------------------------------------------

    def wait_for_confirm(self, reply_id: str) -> asyncio.Future:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_confirms[reply_id] = future
        return future

    def resolve_confirm(self, reply_id: str, action: str) -> bool:
        future = self._pending_confirms.pop(reply_id, None)
        if future is None or future.done():
            return False
        future.set_result(action)
        return True

    # --- persistence -----------------------------------------------------------

    def _save(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "workspaces": [vars(w) for w in self._workspaces.values()],
            "tasks": [vars(t) for t in self._tasks.values()],
        }
        self._registry_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _load(self) -> None:
        if not self._registry_path.exists():
            return
        try:
            payload = json.loads(self._registry_path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for entry in payload.get("workspaces", []):
            self._workspaces[entry["id"]] = WorkspaceRecord(**entry)
        for entry in payload.get("tasks", []):
            self._tasks[entry["id"]] = TaskRecord(
                id=entry["id"],
                title=entry["title"],
                workspace_id=entry["workspace_id"],
                status=entry.get("status", "running"),
                updated_at=entry.get("updated_at", now_iso()),
                has_artifacts=entry.get("has_artifacts", False),
                is_archived=entry.get("is_archived", False),
            )


task_manager = TaskManager()
