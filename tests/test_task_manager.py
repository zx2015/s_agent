"""Unit tests for server/service/task_manager.py's persistence wiring."""
from unittest.mock import AsyncMock, patch

import pytest

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
