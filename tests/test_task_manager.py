"""Unit tests for server/service/task_manager.py's persistence wiring."""
from unittest.mock import AsyncMock, patch

import pytest

from server.service.memory_store import agent_state_store
from server.service.task_manager import TaskManager


@pytest.mark.asyncio
async def test_save_agent_state_is_a_noop_when_agent_was_never_built():
    manager = TaskManager()
    # No get_or_create_agent() call happened for this id, so there is
    # nothing in manager._agents — must not raise.
    await manager.save_agent_state("never-touched-task")


@pytest.mark.asyncio
async def test_save_agent_state_swallows_persistence_failures():
    """A Redis hiccup during save must not raise past this call.

    By the time save_agent_state() runs, the turn's SSE frames (including
    the translator's `done` frame for ReplyEndEvent) have already reached
    the client — see server/main.py's chat handler. If this raised, the
    caller's outer except would send a second, spurious done/error frame
    after an otherwise-successful reply.
    """
    manager = TaskManager()
    fake_agent = type("FakeAgent", (), {"state": object()})()
    manager._agents["t1"] = fake_agent  # type: ignore[assignment]

    with patch(
        "server.service.task_manager.agent_state_store.save",
        new=AsyncMock(side_effect=ConnectionError("redis unreachable")),
    ):
        # Must not raise.
        await manager.save_agent_state("t1")


@pytest.mark.asyncio
async def test_delete_task_returns_false_for_an_unknown_task():
    manager = TaskManager()
    assert await manager.delete_task("does-not-exist") is False


@pytest.mark.asyncio
async def test_delete_task_removes_metadata_agent_state_and_workspace():
    manager = TaskManager()
    task = manager.create_task("default", "待删除的测试任务")
    workspace_dir = manager.workspace_dir(task.id)
    assert workspace_dir.exists()

    # Populate an in-memory agent placeholder and a Redis-persisted state
    # so the test proves both actually get cleaned up, not just metadata.
    manager._agents[task.id] = object()  # type: ignore[assignment]
    from agentscope.state import AgentState

    await agent_state_store.save(task.id, AgentState())

    deleted = await manager.delete_task(task.id)

    assert deleted is True
    assert manager.get_task(task.id) is None
    assert task.id not in manager._agents
    assert not workspace_dir.exists()
    assert await agent_state_store.load(task.id) is None


@pytest.mark.asyncio
async def test_delete_task_swallows_redis_failures():
    """A Redis hiccup during delete must not stop metadata/file cleanup."""
    manager = TaskManager()
    task = manager.create_task("default", "redis失败时也要删除的任务")

    with patch(
        "server.service.task_manager.agent_state_store.delete",
        new=AsyncMock(side_effect=ConnectionError("redis unreachable")),
    ):
        deleted = await manager.delete_task(task.id)

    assert deleted is True
    assert manager.get_task(task.id) is None
    assert not manager.workspace_dir(task.id).exists()
