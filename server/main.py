"""
FastAPI entry point.

Endpoints mirror `docs/specs/2026-09-28-frontend-three-column-workbench.md`
§3.1 exactly — the frontend's `apiClient` and Pinia stores are built
against those paths and payload shapes already.
"""
import asyncio
import logging
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from agentscope.event import (
    ConfirmResult,
    ExternalExecutionResultEvent,
    ReplyEndEvent,
    ReplyFinishedReason,
    RequireExternalExecutionEvent,
    RequireUserConfirmEvent,
    ToolResultEndEvent,
    UserConfirmResultEvent,
    UserInterruptEvent,
)
from agentscope.message import Msg, TextBlock, ToolResultBlock, ToolResultState

from server import __version__, config
from server.schemas.chat import (
    ChatRequest,
    ConfirmRequest,
    CreateTaskRequest,
    CreateWorkspaceRequest,
    TaskOut,
    UpdateTaskRequest,
    WorkspaceOut,
)
from server.service.active_turns import active_turn_manager
from server.service.events import (
    AgentEventTranslator,
    final_todos_changed_frame,
    sse_frame,
    task_todos_changed_frame,
    todo_changed_after_tool,
)
from server.service.history import (
    agent_state_to_chat_messages,
    get_paged_chat_messages,
    serialize_todos,
)
from server.service.memory_store import agent_state_store
from server.service.task_manager import task_manager
from server.service.title_generator import generate_title

logger = logging.getLogger(__name__)

app = FastAPI(title="s_agent backend", version=__version__)

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
    raw_workspaces = task_manager.list_workspaces()
    for ws in raw_workspaces:
        for t in ws.get("tasks", []):
            if active_turn_manager.is_running(t.get("id", "")):
                t["status"] = "running"
            elif t.get("status") == "running":
                t["status"] = "completed"
    workspaces = [
        WorkspaceOut(**workspace).model_dump(by_alias=True)
        for workspace in raw_workspaces
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
        "version": __version__,
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
    await active_turn_manager.abort(task_id)
    await task_manager.reset_context(task_id)
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    await active_turn_manager.abort(task_id)
    deleted = await task_manager.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True}


@app.get("/api/tasks/{task_id}/messages")
async def get_task_messages(
    task_id: str,
    limit: int = Query(default=30, ge=0, le=200),
    before_id: str | None = Query(default=None),
) -> dict:
    """Hydrate the middle pane with cursor-based pagination.

    The AgentScope `AgentState.context` already holds the full transcript;
    this endpoint serialises it into the `ChatMessage` shape and returns
    a paged slice along with `has_more` and `total` count.
    """
    if task_manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    state = await agent_state_store.load(task_id)
    paged_messages, has_more, total = get_paged_chat_messages(
        state,
        limit=limit,
        before_id=before_id,
    )
    return {
        "messages": paged_messages,
        "has_more": has_more,
        "total": total,
    }


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

    task_manager.update_task(payload.task_id, status="running")
    turn = active_turn_manager.create_turn(payload.task_id, lock=lock)

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

    async def _title_worker():
        if title_task is None:
            return
        try:
            new_title = await title_task
            task_manager.update_task(payload.task_id, title=new_title)
            await turn.broadcast(sse_frame("task_renamed", {"title": new_title}))
        except Exception:
            # 标题生成失败不影响核心对话流
            pass

    title_worker_task = asyncio.create_task(_title_worker()) if title_task is not None else None
    turn.title_worker_task = title_worker_task

    async def _agent_worker():
        turn_started_at = time.time()
        try:
            agent = await task_manager.get_or_create_agent(
                payload.task_id,
                model_name=payload.model_name,
                base_url=payload.base_url,
                hitl_mode=payload.hitl_mode,
            )
        except Exception as exc:  # noqa: BLE001 - e.g. missing API key
            task_manager.update_task(payload.task_id, status="failed")
            await turn.broadcast(sse_frame("text_delta", {"text": f"[后端配置错误: {exc}]"}))
            await turn.broadcast(sse_frame("done", {"task_status": "failed"}))
            return

        translator = AgentEventTranslator()
        inputs = Msg(
            name="user",
            role="user",
            content=[TextBlock(type="text", text=payload.message)],
        )

        try:
            external_execution_attempts = 0
            while True:
                pending_reply_id: str | None = None
                pending_tool_calls = None
                is_external_execution = False

                async for event in agent.reply_stream(inputs):
                    if isinstance(event, RequireUserConfirmEvent):
                        pending_reply_id = event.reply_id
                        pending_tool_calls = event.tool_calls
                        for frame in translator.translate(event):
                            await turn.broadcast(frame)
                        break

                    if isinstance(event, RequireExternalExecutionEvent):
                        logger.warning(
                            "收到未支持的外部工具执行请求: reply_id=%s, tools=%s",
                            event.reply_id,
                            [tc.name for tc in event.tool_calls],
                        )
                        external_execution_attempts += 1
                        if external_execution_attempts > 2:
                            logger.error(
                                "外部工具执行重试超限 (attempts=%d)，触发 UserInterruptEvent 中断",
                                external_execution_attempts,
                            )
                            await turn.broadcast(
                                sse_frame(
                                    "text_delta",
                                    {"text": "\n[系统提示: 外部工具交互多次未决，已自动终止该次调用]\n"},
                                )
                            )
                            inputs = UserInterruptEvent(reply_id=event.reply_id)
                            pending_reply_id = event.reply_id
                            is_external_execution = True
                            break

                        await turn.broadcast(
                            sse_frame(
                                "text_delta",
                                {
                                    "text": "\n[系统提示: 检测到模型发起外部工具交互，当前环境不支持，已通知模型以自然语言直接回复]\n"
                                },
                            )
                        )
                        execution_results = []
                        for tc in event.tool_calls:
                            meta: dict = {}
                            try:
                                tool = await agent.toolkit.get_tool(tc.name)
                                schema = getattr(tool, "metadata_schema", None)
                                if isinstance(schema, dict):
                                    req = schema.get("required", [])
                                    props = schema.get("properties", {})
                                    for field_name in req:
                                        t = props.get(field_name, {}).get("type")
                                        if t == "object":
                                            meta[field_name] = {}
                                        elif t == "array":
                                            meta[field_name] = []
                                        elif t == "string":
                                            meta[field_name] = ""
                                        elif t in ("integer", "number"):
                                            meta[field_name] = 0
                                        elif t == "boolean":
                                            meta[field_name] = False
                                        else:
                                            meta[field_name] = {}
                            except Exception:
                                pass
                            execution_results.append(
                                ToolResultBlock(
                                    id=tc.id,
                                    name=tc.name,
                                    output="[系统提示: 当前环境不支持外部工具执行交互，请直接在对话回复中以自然语言向用户澄清或说明]",
                                    metadata=meta,
                                    state=ToolResultState.ERROR,
                                )
                            )
                        inputs = ExternalExecutionResultEvent(
                            reply_id=event.reply_id,
                            execution_results=execution_results,
                        )
                        pending_reply_id = event.reply_id
                        is_external_execution = True
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
                            await turn.broadcast(frame)

                        # 3. 推送最终的 todo 状态快照
                        await turn.broadcast(
                            final_todos_changed_frame(
                                serialize_todos(agent.state),
                            )
                        )

                        # 4. 推送 done 结束帧并按实际完成状态持久化
                        final_status = "completed"
                        if event.error or getattr(event, "finished_reason", None) == ReplyFinishedReason.ERROR:
                            final_status = "failed"
                        elif getattr(event, "finished_reason", None) == ReplyFinishedReason.INTERRUPTED:
                            final_status = "aborted"

                        for frame in translator.translate(event):
                            await turn.broadcast(frame)

                        await task_manager.save_agent_state(payload.task_id)
                        task_manager.update_task(payload.task_id, status=final_status)
                        return

                    for frame in translator.translate(event):
                        await turn.broadcast(frame)

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
                                await turn.broadcast(frame)

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
                    await turn.broadcast(sse_frame("done", {"task_status": "completed"}))
                    task_manager.update_task(payload.task_id, status="completed")
                    return

                if is_external_execution:
                    continue

                future = task_manager.wait_for_confirm(pending_reply_id)
                action = await future
                inputs = UserConfirmResultEvent(
                    reply_id=pending_reply_id,
                    confirm_results=[
                        ConfirmResult(confirmed=action == "allow", tool_call=tc)
                        for tc in pending_tool_calls
                    ],
                )
        except asyncio.CancelledError:
            task_manager.update_task(payload.task_id, status="aborted")
            await task_manager.save_agent_state(payload.task_id)
            await turn.broadcast(sse_frame("done", {"task_status": "aborted"}))
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the client
            task_manager.update_task(payload.task_id, status="failed")
            await task_manager.save_agent_state(payload.task_id)
            await turn.broadcast(sse_frame("text_delta", {"text": f"\n\n[后端错误: {exc}]"}))
            await turn.broadcast(sse_frame("done", {"task_status": "failed"}))
        finally:
            await turn.finish()
            if lock.locked():
                lock.release()
            active_turn_manager.remove(payload.task_id)

    turn.worker_task = asyncio.create_task(_agent_worker())

    return StreamingResponse(turn.subscribe(), media_type="text/event-stream")


@app.get("/api/tasks/{task_id}/events")
async def stream_task_events(task_id: str) -> StreamingResponse:
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    turn = active_turn_manager.get(task_id)
    if turn is not None:
        return StreamingResponse(turn.subscribe(), media_type="text/event-stream")

    async def idle_stream():
        yield sse_frame("done", {"task_status": task.status})

    return StreamingResponse(idle_stream(), media_type="text/event-stream")


@app.post("/api/tasks/{task_id}/abort")
async def abort_task(task_id: str) -> dict:
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    aborted = await active_turn_manager.abort(task_id)
    return {"ok": True, "aborted": aborted}


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
    ".tasks",
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
