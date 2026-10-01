"""
FastAPI entry point.

Endpoints mirror `docs/specs/2026-09-28-frontend-three-column-workbench.md`
§3.1 exactly — the frontend's `apiClient` and Pinia stores are built
against those paths and payload shapes already.
"""
import asyncio
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from agentscope.event import (
    ConfirmResult,
    ReplyEndEvent,
    RequireUserConfirmEvent,
    ToolResultEndEvent,
    UserConfirmResultEvent,
)
from agentscope.message import Msg, TextBlock

from server import config
from server.schemas.chat import (
    ChatRequest,
    ConfirmRequest,
    CreateTaskRequest,
    CreateWorkspaceRequest,
    TaskOut,
    UpdateTaskRequest,
    WorkspaceOut,
)
from server.service.events import (
    AgentEventTranslator,
    final_todos_changed_frame,
    sse_frame,
    task_todos_changed_frame,
    todo_changed_after_tool,
)
from server.service.history import agent_state_to_chat_messages, serialize_todos
from server.service.memory_store import agent_state_store
from server.service.task_manager import task_manager
from server.service.title_generator import generate_title

app = FastAPI(title="s_agent backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/workspaces")
async def list_workspaces() -> dict:
    workspaces = [
        WorkspaceOut(**workspace).model_dump(by_alias=True)
        for workspace in task_manager.list_workspaces()
    ]
    return {"workspaces": workspaces}


@app.post("/api/workspaces")
async def create_workspace(payload: CreateWorkspaceRequest) -> dict:
    workspace = task_manager.create_workspace(payload.name)
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        tasks=[],
    ).model_dump(by_alias=True)


@app.delete("/api/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str) -> dict:
    # The "default" workspace is created unconditionally on startup (see
    # `TaskManager.__init__`'s `_ensure_workspace("default", ...)`) and is
    # where `create_task`/`ensureActiveTask` fall back to when no other
    # workspace exists — deleting it would leave the app with nowhere to
    # put a task by default. A dedicated 400 here (rather than letting it
    # fall through to `delete_workspace`'s generic False/404) gives a
    # clear reason instead of a bare "not found".
    if workspace_id == "default":
        raise HTTPException(status_code=400, detail="默认工作区不能删除")
    deleted = await task_manager.delete_workspace(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="workspace not found")
    return {"ok": True}


@app.get("/api/system/info")
async def get_system_info() -> dict:
    return {
        "workspaceRoot": str(config.WORKSPACES_ROOT.resolve()),
        "modelName": config.MODEL_NAME,
        "baseUrl": config.LITELLM_BASE_URL,
        "hitlMode": getattr(config, "HITL_MODE", "dangerous"),
    }


@app.post("/api/tasks")
async def create_task(payload: CreateTaskRequest) -> dict:
    task = task_manager.create_task(payload.workspace_id, payload.title)
    task_dict = vars(task).copy()
    task_dict["workspace_path"] = str(task_manager.workspace_dir(task.id).resolve())
    return TaskOut(**task_dict).model_dump(by_alias=True)


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, payload: UpdateTaskRequest) -> dict:
    task = task_manager.update_task(
        task_id,
        title=payload.title,
        status=payload.status,
        is_archived=payload.is_archived,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    task_dict = vars(task).copy()
    task_dict["workspace_path"] = str(task_manager.workspace_dir(task.id).resolve())
    return TaskOut(**task_dict).model_dump(by_alias=True)


@app.post("/api/tasks/{task_id}/archive")
async def archive_task(task_id: str) -> dict:
    task = task_manager.archive_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    task_dict = vars(task).copy()
    task_dict["workspace_path"] = str(task_manager.workspace_dir(task.id).resolve())
    return TaskOut(**task_dict).model_dump(by_alias=True)


@app.post("/api/tasks/{task_id}/reset-context")
async def reset_task_context(task_id: str) -> dict:
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    await task_manager.reset_context(task_id)
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    deleted = await task_manager.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True}


@app.get("/api/tasks/{task_id}/messages")
async def get_task_messages(task_id: str) -> dict:
    """Hydrate the middle pane when the user switches tasks.

    The AgentScope `AgentState.context` already holds the full transcript;
    this endpoint serialises it into the `ChatMessage` shape that the
    frontend's session store consumes. When no agent state exists (the
    task has never been chatted with), returns an empty list rather than
    a 404 — a missing transcript is not an error, it's just blank.
    """
    if task_manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    state = await agent_state_store.load(task_id)
    return {"messages": agent_state_to_chat_messages(state)}


@app.get("/api/tasks/{task_id}/todos")
async def get_task_todos(task_id: str) -> dict:
    """Return the current snapshot of the agent's internal todo list.

    Reads `AgentState.tasks_context.tasks` — the tasks the agent created
    or updated during its run via `TaskCreate`/`TaskUpdate`. The frontend
    hits this on cold task-switch or page reload. When no agent state
    exists (the task is new and untouched), returns an empty list rather
    than 404.
    """
    if task_manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    state = await agent_state_store.load(task_id)
    return {"todos": serialize_todos(state)}


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    task = task_manager.get_task(payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    lock = task_manager.get_task_lock(payload.task_id)
    if lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task {payload.task_id} is currently busy processing another message.",
        )
    await lock.acquire()

    # Every task is created with the same placeholder title ("新任务" —
    # see `SidebarLeft.vue`/`WorkspaceTree.vue`/`useChat.ts`'s
    # `ensureActiveTask`, all three task-creation paths use it), so it
    # doubles as "this task has never had a title generated for it yet"
    # without needing a separate boolean field. Kicked off as a
    # background task *before* `get_or_create_agent` below so the LLM
    # round-trip overlaps with agent creation/loading instead of adding
    # its own latency on top.
    title_task = None
    if task.title == "新任务":
        title_task = asyncio.create_task(generate_title(payload.message))

    async def _generate():
        try:
            agent = await task_manager.get_or_create_agent(
                payload.task_id,
                model_name=payload.model_name,
                base_url=payload.base_url,
                hitl_mode=payload.hitl_mode,
            )
        except Exception as exc:  # noqa: BLE001 - e.g. missing API key
            yield sse_frame("text_delta", {"text": f"[后端配置错误: {exc}]"})
            yield sse_frame("done", {"task_status": "failed"})
            return

        queue: asyncio.Queue[str | object] = asyncio.Queue()
        sentinel = object()

        async def _title_worker():
            if title_task is None:
                return
            try:
                new_title = await title_task
                task_manager.update_task(payload.task_id, title=new_title)
                await queue.put(sse_frame("task_renamed", {"title": new_title}))
            except Exception:
                # 标题生成失败不影响核心对话流
                pass

        title_worker_task: asyncio.Task | None = None
        if title_task is not None:
            title_worker_task = asyncio.create_task(_title_worker())

        async def _agent_worker():
            translator = AgentEventTranslator()
            turn_started_at = time.time()
            inputs = Msg(
                name="user",
                role="user",
                content=[TextBlock(type="text", text=payload.message)],
            )

            try:
                while True:
                    pending_reply_id: str | None = None
                    pending_tool_calls = None

                    async for event in agent.reply_stream(inputs):
                        if isinstance(event, RequireUserConfirmEvent):
                            pending_reply_id = event.reply_id
                            pending_tool_calls = event.tool_calls
                            for frame in translator.translate(event):
                                await queue.put(frame)
                            break

                        # Translate the event into SSE frames. Tools that
                        # ended during this iteration get their buffer
                        # popped by the translator; we capture the tool name
                        # before/after to decide whether to send a fresh
                        # `task_todos_changed` snapshot.
                        tool_name_after: str | None = None
                        if isinstance(event, ToolResultEndEvent):
                            # Peek at the buffer the translator is about to pop.
                            buf = translator._buffers.get(event.tool_call_id)
                            tool_name_after = buf.tool_name if buf else None

                        if isinstance(event, ReplyEndEvent):
                            # 1. 确保任务重命名在完成前到达（若尚未完成则最多等 2 秒）
                            if title_worker_task is not None and not title_worker_task.done():
                                try:
                                    await asyncio.wait_for(
                                        asyncio.shield(title_worker_task),
                                        timeout=2.0,
                                    )
                                except Exception:
                                    pass

                            # 2. 推送可能生成的新工件
                            for frame in _new_artifact_frames(
                                payload.task_id,
                                turn_started_at,
                            ):
                                await queue.put(frame)

                            # 3. 推送最终的 todo 状态快照
                            await queue.put(
                                final_todos_changed_frame(
                                    serialize_todos(agent.state),
                                )
                            )

                            # 4. 推送 done 结束帧
                            for frame in translator.translate(event):
                                await queue.put(frame)

                            await task_manager.save_agent_state(payload.task_id)
                            return

                        for frame in translator.translate(event):
                            await queue.put(frame)

                        if isinstance(event, ToolResultEndEvent):
                            # The translator's buffer has been popped during
                            # `translate`. Re-serialise the todo list and emit
                            # a snapshot when the just-finished tool was a
                            # todo mutator.
                            todos_now = serialize_todos(agent.state)
                            todo_frames = todo_changed_after_tool(
                                tool_name_after or "",
                                todos_now,
                            )
                            if todo_frames is not None:
                                for frame in todo_frames:
                                    await queue.put(frame)

                    if pending_reply_id is None:
                        # The stream ended without a ReplyEndEvent or a confirm
                        # request — close the turn defensively rather than
                        # hanging the connection open.
                        if title_worker_task is not None and not title_worker_task.done():
                            try:
                                await asyncio.wait_for(
                                    asyncio.shield(title_worker_task),
                                    timeout=2.0,
                                )
                            except Exception:
                                pass
                        await task_manager.save_agent_state(payload.task_id)
                        await queue.put(sse_frame("done", {"task_status": "completed"}))
                        return

                    future = task_manager.wait_for_confirm(pending_reply_id)
                    action = await future
                    inputs = UserConfirmResultEvent(
                        reply_id=pending_reply_id,
                        confirm_results=[
                            ConfirmResult(confirmed=action == "allow", tool_call=tc)
                            for tc in pending_tool_calls
                        ],
                    )
            except Exception as exc:  # noqa: BLE001 - surfaced to the client
                await queue.put(sse_frame("text_delta", {"text": f"\n\n[后端错误: {exc}]"}))
                await queue.put(sse_frame("done", {"task_status": "failed"}))
            finally:
                await queue.put(sentinel)

        worker_tasks = [
            asyncio.create_task(_agent_worker()),
        ]
        if title_worker_task is not None:
            worker_tasks.append(title_worker_task)

        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                yield item
        finally:
            for t in worker_tasks:
                if not t.done():
                    t.cancel()

    async def event_stream():
        try:
            async for item in _generate():
                yield item
        finally:
            if lock.locked():
                lock.release()

    try:
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception:
        if lock.locked():
            lock.release()
        raise


@app.post("/api/tasks/{task_id}/confirm")
async def confirm_task(task_id: str, payload: ConfirmRequest) -> dict:
    resolved = task_manager.resolve_confirm(payload.reply_id, payload.action)
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail="no pending confirmation with that reply_id",
        )
    return {"ok": True}


IGNORED_WORKSPACE_PARTS = {
    ".git",
    "sessions",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
}


def _is_internal_workspace_entry(entry: Path, workspace: Path) -> bool:
    try:
        parts = entry.relative_to(workspace).parts
    except ValueError:
        return True
    for part in parts:
        if part.startswith(".") or part in IGNORED_WORKSPACE_PARTS:
            return True
    return False


@app.get("/api/tasks/{task_id}/files")
async def list_files(task_id: str) -> dict:
    workspace = task_manager.workspace_dir(task_id)
    if not workspace.exists():
        return {"files": []}

    files = []
    for entry in sorted(workspace.rglob("*")):
        if _is_internal_workspace_entry(entry, workspace):
            continue
        files.append(
            {
                "path": str(entry.relative_to(workspace)),
                "isDir": entry.is_dir(),
            },
        )
    return {"files": files}


@app.get("/api/tasks/{task_id}/git-diff")
async def git_diff(task_id: str) -> dict:
    import subprocess

    workspace = task_manager.workspace_dir(task_id)
    if not workspace.exists() or not (workspace / ".git").is_dir():
        return {"diff": ""}

    result = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"diff": result.stdout}


@app.get("/api/tasks/{task_id}/artifacts")
async def list_artifacts(task_id: str) -> dict:
    workspace = task_manager.workspace_dir(task_id)
    if not workspace.exists():
        return {"artifacts": []}

    artifacts = []
    for entry in sorted(workspace.rglob("*")):
        if _is_internal_workspace_entry(entry, workspace) or not entry.is_file():
            continue
        rel_path = str(entry.relative_to(workspace))
        artifact_type = _ARTIFACT_TYPES.get(entry.suffix.lower(), "text")
        artifacts.append(
            {
                "type": artifact_type,
                "file_path": rel_path,
                "url": f"/api/tasks/{task_id}/artifacts/preview/{rel_path}",
            },
        )
    return {"artifacts": artifacts}


@app.get("/api/tasks/{task_id}/artifacts/preview/{file_path:path}")
async def preview_artifact(task_id: str, file_path: str) -> FileResponse:
    workspace = task_manager.workspace_dir(task_id)
    resolved = _safe_resolve(workspace, file_path)
    if (
        resolved is None
        or not resolved.is_file()
        or _is_internal_workspace_entry(resolved, workspace)
    ):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(resolved)


@app.get("/api/tasks/{task_id}/artifacts/download")
async def download_all(task_id: str) -> FileResponse:
    workspace = task_manager.workspace_dir(task_id)
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="task not found")

    archive_base = config.WORKSPACES_ROOT / f"_download_{task_id}"
    archive_path = Path(f"{archive_base}.zip")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in workspace.rglob("*"):
            if _is_internal_workspace_entry(entry, workspace):
                continue
            if entry.is_file():
                archive.write(entry, entry.relative_to(workspace))

    return FileResponse(
        archive_path,
        filename=f"{task_id}.zip",
        media_type="application/zip",
    )


def _safe_resolve(root: Path, relative: str) -> Path | None:
    """Resolve `relative` under `root`, rejecting any path traversal."""
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        return None
    return candidate


_ARTIFACT_TYPES = {
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".svg": "image",
}


def _new_artifact_frames(task_id: str, since_ts: float):
    """SSE frames for every file the turn wrote or touched.

    Files are detected by mtime rather than by hooking individual tool
    calls, so any tool that writes to the workspace — `Write`, `Edit`, or
    a `Bash` command — surfaces its output the same way. The frontend
    session store already dedupes by `filePath`, so re-announcing a file
    across turns is harmless.
    """
    workspace = task_manager.workspace_dir(task_id)
    if not workspace.exists():
        return []

    frames = []
    found_any = False
    for entry in sorted(workspace.rglob("*")):
        if _is_internal_workspace_entry(entry, workspace) or not entry.is_file():
            continue
        if entry.stat().st_mtime < since_ts:
            continue
        found_any = True
        rel_path = str(entry.relative_to(workspace))
        artifact_type = _ARTIFACT_TYPES.get(entry.suffix.lower(), "text")
        frames.append(
            sse_frame(
                "artifact_created",
                {
                    "type": artifact_type,
                    "file_path": rel_path,
                    "url": f"/api/tasks/{task_id}/artifacts/preview/{rel_path}",
                },
            ),
        )

    if found_any:
        task_manager.mark_has_artifacts(task_id)
    return frames
