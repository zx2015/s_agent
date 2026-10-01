"""
Tests for background agent execution, active turn manager,
stream reconnection, and turn abort.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agentscope.event import ReplyEndEvent, TextBlockDeltaEvent
from server.main import active_turn_manager, app, task_manager
from server.service.active_turns import ActiveTurn, ActiveTurnManager


@pytest.mark.asyncio
async def test_active_turn_broadcast_and_history_replay():
    """Verify that an ActiveTurn correctly replays history to new subscribers

    and broadcasts live frames to all existing subscribers.
    """
    manager = ActiveTurnManager()
    turn = manager.create_turn("task-test-1")

    # Broadcast frame 1 before subscriber connects
    await turn.broadcast("event: text_delta\ndata: {\"text\": \"one\"}\n\n")

    # Subscriber 1 connects
    sub1_gen = turn.subscribe()
    frame1 = await anext(sub1_gen)
    assert "one" in frame1

    # Broadcast frame 2 while subscriber 1 is connected
    await turn.broadcast("event: text_delta\ndata: {\"text\": \"two\"}\n\n")
    frame2 = await anext(sub1_gen)
    assert "two" in frame2

    # Subscriber 2 connects late (reconnection simulation)
    sub2_gen = turn.subscribe()
    sub2_frame1 = await anext(sub2_gen)
    assert "one" in sub2_frame1
    sub2_frame2 = await anext(sub2_gen)
    assert "two" in sub2_frame2

    # Finish the turn
    await turn.finish()

    with pytest.raises(StopAsyncIteration):
        await anext(sub1_gen)
    with pytest.raises(StopAsyncIteration):
        await anext(sub2_gen)

    manager.remove("task-test-1")
    assert not manager.is_running("task-test-1")


@pytest.mark.asyncio
async def test_active_turn_manager_abort_cancels_worker():
    """Verify that manager.abort cancels worker_task and broadcasts abort frame."""
    manager = ActiveTurnManager()
    lock = asyncio.Lock()
    await lock.acquire()

    turn = manager.create_turn("task-test-2", lock=lock)

    async def dummy_worker():
        await asyncio.sleep(60.0)

    worker = asyncio.create_task(dummy_worker())
    turn.worker_task = worker

    assert manager.is_running("task-test-2")
    assert lock.locked()

    sub = turn.subscribe()

    aborted = await manager.abort("task-test-2")
    assert aborted is True
    await asyncio.sleep(0)
    assert worker.cancelled() or worker.done()
    assert not lock.locked()
    assert not manager.is_running("task-test-2")

    # Subscriber receives abort frame and terminates
    abort_frame = await anext(sub)
    assert "aborted" in abort_frame
    with pytest.raises(StopAsyncIteration):
        await anext(sub)


@pytest.mark.asyncio
async def test_endpoint_events_idle_when_not_running():
    """GET /api/tasks/{task_id}/events returns done frame if no active turn."""
    task = task_manager.create_task("default", "Idle Task")
    task_manager.update_task(task.id, status="completed")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{task.id}/events")
        assert resp.status_code == 200
        text = resp.text
        assert "event: done" in text
        assert "completed" in text

    await task_manager.delete_task(task.id)


@pytest.mark.asyncio
async def test_endpoint_abort_stops_running_task():
    """POST /api/tasks/{task_id}/abort stops an in-flight background worker."""
    task = task_manager.create_task("default", "Abort Task")

    class NeverEndingAgent:
        def __init__(self):
            self.state = type("State", (), {"tasks_context": None})()

        async def reply_stream(self, inputs):
            yield TextBlockDeltaEvent(reply_id="r1", block_id="b1", delta="hello")
            await asyncio.sleep(100.0)
            yield ReplyEndEvent(reply_id="r1", session_id="s1")

    agent = NeverEndingAgent()

    with patch.object(task_manager, "get_or_create_agent", new=AsyncMock(return_value=agent)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Start chat in background
            chat_task = asyncio.create_task(
                client.post("/api/chat", json={"task_id": task.id, "message": "hi"}),
            )
            # Give turn a moment to start
            await asyncio.sleep(0.05)
            assert active_turn_manager.is_running(task.id)

            # 2. Call abort endpoint
            abort_resp = await client.post(f"/api/tasks/{task.id}/abort")
            assert abort_resp.status_code == 200
            assert abort_resp.json()["aborted"] is True

            await asyncio.sleep(0.05)
            assert not active_turn_manager.is_running(task.id)

            # Chat stream should have finished with aborted
            chat_resp = await chat_task
            assert chat_resp.status_code == 200
            assert "aborted" in chat_resp.text

    await task_manager.delete_task(task.id)


@pytest.mark.asyncio
async def test_endpoint_events_reconnects_to_active_turn():
    """GET /api/tasks/{task_id}/events reconnects and receives stream from active turn."""
    task = task_manager.create_task("default", "Reconnect Task")

    class FastAgent:
        def __init__(self):
            self.state = type("State", (), {"tasks_context": None})()

        async def reply_stream(self, inputs):
            yield TextBlockDeltaEvent(reply_id="r1", block_id="b1", delta="reconnect test content")
            yield ReplyEndEvent(reply_id="r1", session_id="s1")

    agent = FastAgent()

    with patch.object(task_manager, "get_or_create_agent", new=AsyncMock(return_value=agent)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Complete chat turn
            chat_resp = await client.post("/api/chat", json={"task_id": task.id, "message": "hi"})
            assert chat_resp.status_code == 200
            assert "reconnect test content" in chat_resp.text

            # 2. Call events endpoint afterwards - should report completed
            events_resp = await client.get(f"/api/tasks/{task.id}/events")
            assert events_resp.status_code == 200
            assert "event: done" in events_resp.text
            assert "completed" in events_resp.text

    await task_manager.delete_task(task.id)
