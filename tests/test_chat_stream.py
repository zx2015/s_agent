"""Tests for concurrent SSE chat stream and first-token latency optimization."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agentscope.event import ReplyEndEvent, TextBlockDeltaEvent
from server.main import app, task_manager


@pytest.mark.asyncio
async def test_chat_stream_first_token_not_blocked_by_slow_title(tmp_path):
    # Create a fresh task with title "新任务"
    task = task_manager.create_task("default", "新任务")

    async def mock_generate_title(msg: str) -> str:
        # Simulate slow LLM title generation
        await asyncio.sleep(0.1)
        return "新生成的任务标题"

    class FakeAgent:
        def __init__(self):
            self.state = type("State", (), {"tasks_context": None})()

        async def reply_stream(self, inputs):
            # Immediately yield first token
            yield TextBlockDeltaEvent(reply_id="r1", block_id="b1", delta="第一字")
            await asyncio.sleep(0.02)
            yield TextBlockDeltaEvent(reply_id="r1", block_id="b1", delta="后续内容")
            yield ReplyEndEvent(reply_id="r1", session_id="s1")

    fake_agent = FakeAgent()

    with (
        patch("server.main.generate_title", side_effect=mock_generate_title),
        patch.object(task_manager, "get_or_create_agent", new=AsyncMock(return_value=fake_agent)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            frames: list[str] = []
            async with client.stream(
                "POST",
                "/api/chat",
                json={"task_id": task.id, "message": "你好"},
            ) as response:
                assert response.status_code == 200
                async for chunk in response.aiter_text():
                    frames.append(chunk)

            full_body = "".join(frames)
            # Verify text_delta arrives before or concurrent with title, and both are in the stream
            assert "event: text_delta\ndata: {\"text\": \"第一字\"}" in full_body
            assert "event: task_renamed\ndata: {\"title\": \"新生成的任务标题\"}" in full_body
            assert "event: done" in full_body

            # Check that task title in task_manager was updated
            updated_task = task_manager.get_task(task.id)
            assert updated_task is not None
            assert updated_task.title == "新生成的任务标题"


@pytest.mark.asyncio
async def test_system_info_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/system/info")
        assert res.status_code == 200
        data = res.json()
        assert "workspaceRoot" in data
        assert "modelName" in data
        assert "baseUrl" in data
        assert "hitlMode" in data


@pytest.mark.asyncio
async def test_archive_and_reset_context_endpoints():
    task = task_manager.create_task("default", "端点测试任务")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test archive endpoint
        res = await client.post(f"/api/tasks/{task.id}/archive")
        assert res.status_code == 200
        archived_data = res.json()
        assert archived_data["isArchived"] is True
        assert "workspacePath" in archived_data

        # Test patch with is_archived
        res2 = await client.patch(f"/api/tasks/{task.id}", json={"isArchived": False})
        assert res2.status_code == 200
        assert res2.json()["isArchived"] is False

        # Test reset context endpoint
        with patch.object(task_manager, "reset_context", new=AsyncMock()) as mock_reset:
            res3 = await client.post(f"/api/tasks/{task.id}/reset-context")
            assert res3.status_code == 200
            assert res3.json() == {"ok": True}
            mock_reset.assert_awaited_once_with(task.id)


@pytest.mark.asyncio
async def test_list_artifacts_endpoint():
    ws = task_manager.create_workspace("产物测试工作区")
    task = task_manager.create_task(ws.id, "产物测试任务")
    ws_dir = task_manager.workspace_dir(task.id)
    (ws_dir / "test_report.md").write_text("# Test Report", encoding="utf-8")
    (ws_dir / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    # Simulate AgentScope ContextOffload sessions directory and internal files
    sessions_dir = ws_dir / "sessions" / "9ed720a1b0dc48d4abf86da9bc5d2237"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "tool_result-call_12345.txt").write_text("intermediate tool dump", encoding="utf-8")
    (ws_dir / ".gitkeep").write_text("", encoding="utf-8")

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(f"/api/tasks/{task.id}/artifacts")
            assert res.status_code == 200
            data = res.json()
            assert "artifacts" in data
            assert len(data["artifacts"]) == 2
            paths = [item["file_path"] for item in data["artifacts"]]
            assert "test_report.md" in paths
            assert "index.html" in paths
            assert not any("sessions" in p for p in paths)
            assert not any(p.startswith(".") for p in paths)

            # Direct preview of internal file must be rejected (404)
            preview_res = await client.get(
                f"/api/tasks/{task.id}/artifacts/preview/sessions/9ed720a1b0dc48d4abf86da9bc5d2237/tool_result-call_12345.txt"
            )
            assert preview_res.status_code == 404

            # list_files must also exclude internal sessions
            files_res = await client.get(f"/api/tasks/{task.id}/files")
            assert files_res.status_code == 200
    finally:
        await task_manager.delete_workspace(ws.id)
        file_paths = [f["path"] for f in files_res.json()["files"]]
        assert not any("sessions" in p for p in file_paths)


@pytest.mark.asyncio
async def test_get_task_messages_pagination():
    ws = task_manager.create_workspace("msg_page_ws")
    task = task_manager.create_task(ws.id, "测试分页任务")
    from agentscope.message import Msg, TextBlock
    from agentscope.state import AgentState

    context = [
        Msg(id=f"page_msg_{i}", name="user", role="user", content=[TextBlock(text=f"问 {i}")])
        for i in range(25)
    ]
    mock_state = AgentState(context=context)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("server.main.agent_state_store.load", new_callable=AsyncMock) as mock_load:
                mock_load.return_value = mock_state

                # 1. Default request (limit=30 >= 25 messages)
                resp = await client.get(f"/api/tasks/{task.id}/messages")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 25
                assert data["has_more"] is False
                assert len(data["messages"]) == 25

                # 2. Limit=10: returns last 10 messages (indices 15..24)
                resp10 = await client.get(f"/api/tasks/{task.id}/messages?limit=10")
                assert resp10.status_code == 200
                data10 = resp10.json()
                assert data10["total"] == 25
                assert data10["has_more"] is True
                assert len(data10["messages"]) == 10
                assert data10["messages"][0]["id"] == "page_msg_15"
                assert data10["messages"][-1]["id"] == "page_msg_24"

                # 3. Pagination with before_id="page_msg_15", limit=10: returns indices 5..14
                resp_prev = await client.get(f"/api/tasks/{task.id}/messages?limit=10&before_id=page_msg_15")
                assert resp_prev.status_code == 200
                data_prev = resp_prev.json()
                assert data_prev["total"] == 25
                assert data_prev["has_more"] is True
                assert len(data_prev["messages"]) == 10
                assert data_prev["messages"][0]["id"] == "page_msg_5"
                assert data_prev["messages"][-1]["id"] == "page_msg_14"

                # 4. Oldest page before_id="page_msg_5", limit=10: returns indices 0..4, has_more=False
                resp_old = await client.get(f"/api/tasks/{task.id}/messages?limit=10&before_id=page_msg_5")
                assert resp_old.status_code == 200
                data_old = resp_old.json()
                assert data_old["total"] == 25
                assert data_old["has_more"] is False
                assert len(data_old["messages"]) == 5
                assert data_old["messages"][0]["id"] == "page_msg_0"
                assert data_old["messages"][-1]["id"] == "page_msg_4"
    finally:
        await task_manager.delete_workspace(ws.id)

