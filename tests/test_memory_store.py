"""Integration tests for server/service/memory_store.py.

These hit the real local Redis container (see CLAUDE.md's environment
notes, port 6380) rather than mocking it — the whole point of this
module is "does a round-trip through Redis actually preserve AgentState",
which a mock can't tell us.
"""
import uuid

import pytest
from agentscope.message import Msg, TextBlock
from agentscope.state import AgentState

from server.service.memory_store import AgentStateStore, _key
from server import config


@pytest.fixture
def store() -> AgentStateStore:
    return AgentStateStore(config.REDIS_URL)


def _unique_task_id() -> str:
    return f"test-{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_load_returns_none_when_nothing_saved(store: AgentStateStore):
    assert await store.load(_unique_task_id()) is None


@pytest.mark.asyncio
async def test_save_then_load_round_trips_conversation_history(
    store: AgentStateStore,
):
    task_id = _unique_task_id()
    state = AgentState()
    state.context.append(
        Msg(name="user", role="user", content=[TextBlock(type="text", text="你好")]),
    )
    state.context.append(
        Msg(
            name="Assistant",
            role="assistant",
            content=[TextBlock(type="text", text="你好，有什么可以帮你？")],
        ),
    )

    try:
        await store.save(task_id, state)
        restored = await store.load(task_id)

        assert restored is not None
        assert len(restored.context) == 2
        assert restored.context[0].get_text_content() == "你好"
        assert restored.context[1].get_text_content() == "你好，有什么可以帮你？"
    finally:
        await store.delete(task_id)


@pytest.mark.asyncio
async def test_save_sets_a_ttl(store: AgentStateStore):
    task_id = _unique_task_id()
    try:
        await store.save(task_id, AgentState())
        ttl = await store._client.ttl(_key(task_id))
        assert 0 < ttl <= config.AGENT_STATE_TTL_SECONDS
    finally:
        await store.delete(task_id)


@pytest.mark.asyncio
async def test_load_discards_unreadable_saved_state_instead_of_raising(
    store: AgentStateStore,
):
    task_id = _unique_task_id()
    try:
        # A `context` that isn't a list fails AgentState's schema (this is
        # what a genuinely incompatible saved payload looks like — as
        # opposed to just an unknown extra key, which pydantic ignores by
        # default and would still validate successfully).
        await store._client.set(_key(task_id), '{"context": "not-a-list"}')
        assert await store.load(task_id) is None
    finally:
        await store.delete(task_id)


@pytest.mark.asyncio
async def test_delete_removes_the_saved_state(store: AgentStateStore):
    task_id = _unique_task_id()
    await store.save(task_id, AgentState())
    await store.delete(task_id)
    assert await store.load(task_id) is None
