"""Integration tests for server/service/memory_store.py.

These hit the real local Redis container (see CLAUDE.md's environment
notes, port 6380) rather than mocking it — the whole point of this
module is "does a round-trip through Redis actually preserve AgentState",
which a mock can't tell us.
"""
import uuid

import pytest
from agentscope.message import (
    Msg,
    TextBlock,
    ToolCallBlock,
    ToolCallState,
    ToolResultBlock,
)
from agentscope.state import AgentState

from server.service.memory_store import AgentStateStore, _key, sanitize_agent_state
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


def test_sanitize_agent_state_repairs_dangling_tool_calls():
    state = AgentState()
    state.context.append(
        Msg(name="user", role="user", content=[TextBlock(type="text", text="hi")]),
    )
    last_msg = Msg(
        name="Assistant",
        role="assistant",
        content=[
            ToolCallBlock(
                type="tool_call",
                id="call_1",
                name="AskUser",
                input="{}",
                state=ToolCallState.SUBMITTED,
            ),
            ToolCallBlock(
                type="tool_call",
                id="call_2",
                name="Bash",
                input="{}",
                state=ToolCallState.ASKING,
            ),
        ],
    )
    state.context.append(last_msg)

    # Before sanitization, state reports awaiting tool calls
    assert len(state.get_awaiting_tool_calls("Assistant")) == 2

    modified = sanitize_agent_state(state)
    assert modified is True

    # After sanitization, awaiting tool calls is empty
    assert len(state.get_awaiting_tool_calls("Assistant")) == 0

    # The tool calls are marked finished and have matching tool results
    tc1 = last_msg.get_content_blocks("tool_call")[0]
    tc2 = last_msg.get_content_blocks("tool_call")[1]
    assert tc1.state == ToolCallState.FINISHED
    assert tc2.state == ToolCallState.FINISHED

    results = last_msg.get_content_blocks("tool_result")
    assert len(results) == 2
    assert {r.id for r in results} == {"call_1", "call_2"}


@pytest.mark.asyncio
async def test_load_auto_heals_submitted_or_asking_tool_calls(store: AgentStateStore):
    task_id = _unique_task_id()
    state = AgentState()
    state.context.append(
        Msg(name="user", role="user", content=[TextBlock(type="text", text="分析这只股票")]),
    )
    state.context.append(
        Msg(
            name="Assistant",
            role="assistant",
            content=[
                ToolCallBlock(
                    type="tool_call",
                    id="call_corrupt_1",
                    name="AskUser",
                    input="{}",
                    state=ToolCallState.SUBMITTED,
                ),
            ],
        ),
    )

    try:
        # Save raw state with SUBMITTED tool call directly into Redis client
        await store._client.set(_key(task_id), state.model_dump_json())

        # load() should heal it in-memory cleanly without breaking read-only semantics
        healed_state = await store.load(task_id)
        assert healed_state is not None
        assert len(healed_state.get_awaiting_tool_calls("Assistant")) == 0
    finally:
        await store.delete(task_id)


@pytest.mark.asyncio
async def test_save_self_sanitizes_allowed_and_pending_states(store: AgentStateStore):
    task_id = _unique_task_id()
    state = AgentState()
    state.context.append(
        Msg(
            name="Assistant",
            role="assistant",
            content=[
                ToolCallBlock(
                    type="tool_call",
                    id="call_allowed",
                    name="Calculator",
                    input="{}",
                    state=ToolCallState.ALLOWED,
                ),
                ToolCallBlock(
                    type="tool_call",
                    id="call_pending",
                    name="Bash",
                    input="{}",
                    state=ToolCallState.PENDING,
                ),
            ],
        ),
    )

    try:
        # store.save() must automatically sanitize unfinished states before writing
        await store.save(task_id, state)

        reloaded_raw = await store._client.get(_key(task_id))
        reloaded_state = AgentState.model_validate_json(reloaded_raw)
        assert len(reloaded_state.get_awaiting_tool_calls("Assistant")) == 0

        # Tool calls should be FINISHED with INTERRUPTED string results
        tcs = reloaded_state.context[0].get_content_blocks("tool_call")
        assert all(tc.state == ToolCallState.FINISHED for tc in tcs)
        trs = reloaded_state.context[0].get_content_blocks("tool_result")
        assert len(trs) == 2
        assert all(isinstance(tr.output, str) for tr in trs)
    finally:
        await store.delete(task_id)


def test_serialize_tool_output_unpacks_textblocks():
    from server.service.history import _serialize_tool_output

    # List of TextBlocks
    blocks = [TextBlock(type="text", text="第一行"), TextBlock(type="text", text="第二行")]
    serialized = _serialize_tool_output(blocks)
    assert serialized == "第一行\n第二行"
    assert "TextBlock(" not in serialized

