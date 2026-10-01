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
    task = task_manager.create_task("default", "产物测试任务")
    ws_dir = task_manager.workspace_dir(task.id)
    (ws_dir / "test_report.md").write_text("# Test Report", encoding="utf-8")
    (ws_dir / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/tasks/{task.id}/artifacts")
        assert res.status_code == 200
        data = res.json()
        assert "artifacts" in data
        assert len(data["artifacts"]) == 2
        paths = [item["file_path"] for item in data["artifacts"]]
        assert "test_report.md" in paths
        assert "index.html" in paths
