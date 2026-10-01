"""
Tests for task-level concurrency mutex lock (server/service/task_manager.py & server/main.py).
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agentscope.event import ReplyEndEvent, TextBlockDeltaEvent
from server.main import app, task_manager


@pytest.mark.asyncio
async def test_task_lock_lifecycle_in_task_manager():
    task1 = task_manager.create_task("default", "Task 1")
    task2 = task_manager.create_task("default", "Task 2")

    lock1_a = task_manager.get_task_lock(task1.id)
    lock1_b = task_manager.get_task_lock(task1.id)
    lock2 = task_manager.get_task_lock(task2.id)

    # Same task_id gets the identical Lock instance
    assert lock1_a is lock1_b
    # Different task_id gets different Lock instance
    assert lock1_a is not lock2

    # Delete task removes lock
    await task_manager.delete_task(task1.id)
    assert task1.id not in task_manager._task_locks

    # Clean up task2
    await task_manager.delete_task(task2.id)


@pytest.mark.asyncio
async def test_chat_endpoint_concurrent_rejection_409():
    task = task_manager.create_task("default", "Concurrency Test Task")
    lock = task_manager.get_task_lock(task.id)

    # Manually hold lock simulating an ongoing turn
    await lock.acquire()
    assert lock.locked()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request for busy task should be rejected immediately with 409
        resp = await client.post(
            "/api/chat",
            json={"task_id": task.id, "message": "并发消息"},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert "busy" in data["detail"]

        # Different task is not affected
        other_task = task_manager.create_task("default", "Other Task")
        class FakeAgent:
            def __init__(self):
                self.state = type("State", (), {"tasks_context": None})()
            async def reply_stream(self, inputs):
                yield TextBlockDeltaEvent(reply_id="r1", block_id="b1", delta="OK")
                yield ReplyEndEvent(reply_id="r1", session_id="s1")

        with patch.object(task_manager, "get_or_create_agent", new=AsyncMock(return_value=FakeAgent())):
            async with client.stream(
                "POST",
                "/api/chat",
                json={"task_id": other_task.id, "message": "其他任务消息"},
            ) as stream_resp:
                assert stream_resp.status_code == 200

        # Now release the lock on the original task
        lock.release()
        assert not lock.locked()

        # Subsequent call on original task should now succeed and acquire lock
        with patch.object(task_manager, "get_or_create_agent", new=AsyncMock(return_value=FakeAgent())):
            async with client.stream(
                "POST",
                "/api/chat",
                json={"task_id": task.id, "message": "锁释放后的消息"},
            ) as stream_resp:
                assert stream_resp.status_code == 200

        # After stream finishes, the lock must be released
        assert not lock.locked()

    # Clean up tasks
    await task_manager.delete_task(task.id)
    await task_manager.delete_task(other_task.id)
