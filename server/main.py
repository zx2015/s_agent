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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from agentscope.event import ReplyEndEvent, RequireUserConfirmEvent
from agentscope.event import UserConfirmResultEvent, ConfirmResult
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
from server.service.events import AgentEventTranslator, sse_frame
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


@app.post("/api/tasks")
async def create_task(payload: CreateTaskRequest) -> dict:
    task = task_manager.create_task(payload.workspace_id, payload.title)
    return TaskOut(**vars(task)).model_dump(by_alias=True)


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, payload: UpdateTaskRequest) -> dict:
    task = task_manager.update_task(
        task_id,
        title=payload.title,
        status=payload.status,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskOut(**vars(task)).model_dump(by_alias=True)


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    deleted = await task_manager.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True}


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    task = task_manager.get_task(payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

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

    async def event_stream():
        try:
            agent = await task_manager.get_or_create_agent(payload.task_id)
        except Exception as exc:  # noqa: BLE001 - e.g. missing API key
            yield sse_frame("text_delta", {"text": f"[后端配置错误: {exc}]"})
            yield sse_frame("done", {"task_status": "failed"})
            return

        if title_task is not None:
            new_title = await title_task
            task_manager.update_task(payload.task_id, title=new_title)
            yield sse_frame("task_renamed", {"title": new_title})

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
                            yield frame
                        break

                    for frame in translator.translate(event):
                        yield frame

                    if isinstance(event, ReplyEndEvent):
                        for frame in _new_artifact_frames(
                            payload.task_id,
                            turn_started_at,
                        ):
                            yield frame
                        await task_manager.save_agent_state(payload.task_id)
                        return

                if pending_reply_id is None:
                    # The stream ended without a ReplyEndEvent or a confirm
                    # request — close the turn defensively rather than
                    # hanging the connection open.
                    await task_manager.save_agent_state(payload.task_id)
                    yield sse_frame("done", {"task_status": "completed"})
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
            yield sse_frame("text_delta", {"text": f"\n\n[后端错误: {exc}]"})
            yield sse_frame("done", {"task_status": "failed"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/tasks/{task_id}/confirm")
async def confirm_task(task_id: str, payload: ConfirmRequest) -> dict:
    resolved = task_manager.resolve_confirm(payload.reply_id, payload.action)
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail="no pending confirmation with that reply_id",
        )
    return {"ok": True}


@app.get("/api/tasks/{task_id}/files")
async def list_files(task_id: str) -> dict:
    workspace = task_manager.workspace_dir(task_id)
    if not workspace.exists():
        return {"files": []}

    files = []
    for entry in sorted(workspace.rglob("*")):
        if ".git" in entry.relative_to(workspace).parts:
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
    if not workspace.exists():
        return {"diff": ""}

    result = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"diff": result.stdout}


@app.get("/api/tasks/{task_id}/artifacts/preview/{file_path:path}")
async def preview_artifact(task_id: str, file_path: str) -> FileResponse:
    workspace = task_manager.workspace_dir(task_id)
    resolved = _safe_resolve(workspace, file_path)
    if resolved is None or not resolved.is_file():
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
            if ".git" in entry.relative_to(workspace).parts:
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
        if ".git" in entry.relative_to(workspace).parts or not entry.is_file():
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
