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
from server.service.memory_store import agent_state_store

logger = logging.getLogger(__name__)

_REGISTRY_FILE = config.WORKSPACES_ROOT / "registry.json"


@dataclass
class TaskRecord:
    id: str
    title: str
    workspace_id: str
    status: str = "running"
    updated_at: str = field(default_factory=now_iso)
    has_artifacts: bool = False


@dataclass
class WorkspaceRecord:
    id: str
    name: str


class TaskManager:
    def __init__(self) -> None:
        self._workspaces: dict[str, WorkspaceRecord] = {}
        self._tasks: dict[str, TaskRecord] = {}
        self._agents: dict[str, Agent] = {}
        self._pending_confirms: dict[str, asyncio.Future] = {}
        self._load()
        self._ensure_workspace("default", "默认工作区")

    # --- workspaces & tasks -------------------------------------------------

    def _ensure_workspace(self, workspace_id: str, name: str) -> WorkspaceRecord:
        if workspace_id not in self._workspaces:
            self._workspaces[workspace_id] = WorkspaceRecord(workspace_id, name)
            self._save()
        return self._workspaces[workspace_id]

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
            result.append(
                {
                    "id": workspace.id,
                    "name": workspace.name,
                    "tasks": [vars(t) for t in tasks],
                },
            )
        return result

    def create_task(self, workspace_id: str, title: str) -> TaskRecord:
        self._ensure_workspace(workspace_id, workspace_id)
        task_id = f"task-{len(self._tasks) + 1}-{int(time.time() * 1000)}"
        task = TaskRecord(id=task_id, title=title, workspace_id=workspace_id)
        self._tasks[task_id] = task
        self.workspace_dir(task_id).mkdir(parents=True, exist_ok=True)
        self._init_git(task_id)
        self._save()
        return task

    def update_task(
        self,
        task_id: str,
        title: str | None = None,
        status: str | None = None,
    ) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if title is not None:
            task.title = title
        if status is not None:
            task.status = status
        task.updated_at = now_iso()
        self._save()
        return task

    def mark_has_artifacts(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.has_artifacts = True
            self._save()

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    async def delete_task(self, task_id: str) -> bool:
        """Permanently remove a task: metadata, cached agent, persisted
        conversation history, and the workspace directory on disk.

        Unlike `archiveTask` on the frontend (which today only hides a
        task locally without telling the backend anything — a
        pre-existing, separate gap, not something this touches), this is
        real, irreversible deletion. Returns `False` without touching
        anything if the task doesn't exist, so the caller can 404
        cleanly.
        """
        if task_id not in self._tasks:
            return False

        del self._tasks[task_id]
        self._agents.pop(task_id, None)
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

        shutil.rmtree(self.workspace_dir(task_id), ignore_errors=True)
        return True

    # --- workspace directories ------------------------------------------------

    def workspace_dir(self, task_id: str) -> Path:
        return config.WORKSPACES_ROOT / task_id

    def _init_git(self, task_id: str) -> None:
        import subprocess

        directory = self.workspace_dir(task_id)
        subprocess.run(["git", "init", "-q"], cwd=directory, check=False)
        subprocess.run(
            ["git", "config", "user.email", "agent@s-agent.local"],
            cwd=directory,
            check=False,
        )
        subprocess.run(
            ["git", "config", "user.name", "s_agent"],
            cwd=directory,
            check=False,
        )
        (directory / ".gitkeep").touch()
        subprocess.run(["git", "add", "-A"], cwd=directory, check=False)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init task workspace"],
            cwd=directory,
            check=False,
        )

    # --- agents --------------------------------------------------------------

    async def get_or_create_agent(self, task_id: str) -> Agent:
        if task_id not in self._agents:
            saved_state = await agent_state_store.load(task_id)
            self._agents[task_id] = await build_agent(
                self.workspace_dir(task_id),
                state=saved_state,
            )
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
        config.WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
        payload = {
            "workspaces": [vars(w) for w in self._workspaces.values()],
            "tasks": [vars(t) for t in self._tasks.values()],
        }
        _REGISTRY_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _load(self) -> None:
        if not _REGISTRY_FILE.exists():
            return
        try:
            payload = json.loads(_REGISTRY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for entry in payload.get("workspaces", []):
            self._workspaces[entry["id"]] = WorkspaceRecord(**entry)
        for entry in payload.get("tasks", []):
            self._tasks[entry["id"]] = TaskRecord(**entry)


task_manager = TaskManager()
