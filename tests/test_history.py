"""Unit tests for serialising AgentScope AgentState into frontend ChatMessages."""
import json
from agentscope.message import Msg, TextBlock, ThinkingBlock, ToolCallBlock, ToolResultBlock
from agentscope.state import AgentState, Task

from server.service.history import (
    agent_state_to_chat_messages,
    get_paged_chat_messages,
    serialize_todos,
)


def test_empty_state_returns_empty_list():
    state = AgentState()
    assert agent_state_to_chat_messages(state) == []


def test_user_text_message():
    state = AgentState(
        context=[
            Msg(name="user", role="user", content=[TextBlock(text="你好")]),
        ]
    )
    messages = agent_state_to_chat_messages(state)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["text"] == "你好"
    assert messages[0]["thinking"] == ""
    assert messages[0]["toolCalls"] == []
    assert messages[0]["streaming"] is False


def test_assistant_with_thinking_and_text():
    state = AgentState(
        context=[
            Msg(
                name="Assistant",
                role="assistant",
                content=[
                    ThinkingBlock(thinking="让我想想"),
                    TextBlock(text="这是正式回答"),
                ],
            ),
        ]
    )
    messages = agent_state_to_chat_messages(state)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["thinking"] == "让我想想"
    assert messages[0]["text"] == "这是正式回答"


def test_assistant_with_tool_call_and_result():
    state = AgentState(
        context=[
            Msg(
                name="Assistant",
                role="assistant",
                content=[
                    ToolCallBlock(
                        id="c1",
                        name="calculate",
                        input=json.dumps({"expression": "1+1"}),
                    ),
                    ToolResultBlock(
                        id="c1",
                        name="calculate",
                        output="2",
                    ),
                    TextBlock(text="1+1 等于 2"),
                ],
            ),
        ]
    )
    messages = agent_state_to_chat_messages(state)
    assert len(messages) == 1
    assert len(messages[0]["toolCalls"]) == 1
    call = messages[0]["toolCalls"][0]
    assert call["callId"] == "c1"
    assert call["tool"] == "calculate"
    assert call["args"] == {"expression": "1+1"}
    assert call["summary"] == "2"
    assert call["status"] == "success"
    assert messages[0]["text"] == "1+1 等于 2"


def test_skips_system_messages_and_system_reminders():
    state = AgentState(
        context=[
            Msg(name="system", role="system", content=[TextBlock(text="system prompt")]),
            Msg(name="user", role="user", content=[TextBlock(text="<system-reminder>time</system-reminder>")]),
            Msg(name="user", role="user", content=[TextBlock(text="用户真正的问题")]),
        ]
    )
    messages = agent_state_to_chat_messages(state)
    assert len(messages) == 1
    assert messages[0]["text"] == "用户真正的问题"


def test_serialize_todos_empty_when_state_is_none():
    assert serialize_todos(None) == []


def test_serialize_todos_empty_when_no_tasks():
    state = AgentState()
    assert serialize_todos(state) == []


def test_serialize_todos_single_task_basic_fields():
    state = AgentState(
        tasks_context=__import__(
            "agentscope.state", fromlist=["TaskContext"]
        ).TaskContext(
            tasks=[
                Task(
                    id="1",
                    subject="读取配置",
                    description="读取 .env.example",
                    state="pending",
                    owner=None,
                    blocks=[],
                    blocked_by=[],
                    created_at="2026-09-30T10:00:00Z",
                    metadata={},
                ),
            ]
        )
    )
    todos = serialize_todos(state)
    assert len(todos) == 1
    assert todos[0] == {
        "id": "1",
        "subject": "读取配置",
        "description": "读取 .env.example",
        "state": "pending",
        "owner": None,
        "blocks": [],
        "blockedBy": [],
        "createdAt": "2026-09-30T10:00:00Z",
    }


def test_serialize_todos_preserves_dependency_graph_and_owner():
    state = AgentState(
        tasks_context=__import__(
            "agentscope.state", fromlist=["TaskContext"]
        ).TaskContext(
            tasks=[
                Task(
                    id="1",
                    subject="读取配置",
                    description="",
                    state="completed",
                    owner="explorer",
                    blocks=["2", "3"],
                    blocked_by=[],
                    created_at="2026-09-30T10:00:00Z",
                    metadata={},
                ),
                Task(
                    id="2",
                    subject="解析配置",
                    description="读取 yaml",
                    state="in_progress",
                    owner=None,
                    blocks=[],
                    blocked_by=["1"],
                    created_at="2026-09-30T10:00:01Z",
                    metadata={},
                ),
            ]
        )
    )
    todos = serialize_todos(state)
    assert len(todos) == 2
    by_id = {t["id"]: t for t in todos}
    assert by_id["1"]["owner"] == "explorer"
    assert by_id["1"]["state"] == "completed"
    assert by_id["1"]["blocks"] == ["2", "3"]
    assert by_id["2"]["owner"] is None
    assert by_id["2"]["state"] == "in_progress"
    assert by_id["2"]["blockedBy"] == ["1"]


def test_serialize_todos_handles_multiple_tasks_order():
    # Tasks are preserved in creation order (index in tasks_context.tasks)
    state = AgentState(
        tasks_context=__import__(
            "agentscope.state", fromlist=["TaskContext"]
        ).TaskContext(
            tasks=[
                Task(
                    id=str(i),
                    subject=f"步骤 {i}",
                    description="",
                    state="pending",
                    owner=None,
                    blocks=[],
                    blocked_by=[],
                    created_at="2026-09-30T10:00:00Z",
                    metadata={},
                )
                for i in range(1, 4)
            ]
        )
    )
    todos = serialize_todos(state)
    assert [t["id"] for t in todos] == ["1", "2", "3"]


def test_interleaved_blocks_preserve_chronological_order():
    """Verify that thinking, text, and tool calls are preserved in their exact interleaved order."""
    state = AgentState(
        context=[
            Msg(
                name="Assistant",
                role="assistant",
                content=[
                    ThinkingBlock(thinking="先分析一下任务"),
                    TextBlock(text="我将先调用计算器"),
                    ToolCallBlock(
                        id="call_1",
                        name="calculate",
                        input=json.dumps({"expression": "10*10"}),
                    ),
                    ToolResultBlock(
                        id="call_1",
                        name="calculate",
                        output="100",
                    ),
                    TextBlock(text="计算结果为 100，下面开始总结"),
                    ThinkingBlock(thinking="最后整理输出"),
                    TextBlock(text="# 最终报告\n计算结果为 100。"),
                ],
            ),
        ]
    )
    messages = agent_state_to_chat_messages(state)
    assert len(messages) == 1
    msg = messages[0]
    blocks = msg["blocks"]
    assert len(blocks) == 6
    assert blocks[0] == {"type": "thinking", "content": "先分析一下任务"}
    assert blocks[1] == {"type": "text", "content": "我将先调用计算器"}
    assert blocks[2]["type"] == "tool_call"
    assert blocks[2]["call"]["callId"] == "call_1"
    assert blocks[2]["call"]["summary"] == "100"
    assert blocks[3] == {"type": "text", "content": "计算结果为 100，下面开始总结"}
    assert blocks[4] == {"type": "thinking", "content": "最后整理输出"}
    assert blocks[5] == {"type": "text", "content": "# 最终报告\n计算结果为 100。"}


def test_get_paged_chat_messages_empty_state():
    paged, has_more, total = get_paged_chat_messages(None)
    assert paged == []
    assert has_more is False
    assert total == 0


def test_get_paged_chat_messages_pagination_and_cursors():
    # Build 10 messages: m0, m1, ..., m9
    context = [
        Msg(id=f"msg_{i}", name="user", role="user", content=[TextBlock(text=f"问题 {i}")])
        for i in range(10)
    ]
    state = AgentState(context=context)

    # 1. Total <= limit: should return all 10 messages, has_more=False
    paged, has_more, total = get_paged_chat_messages(state, limit=15)
    assert total == 10
    assert has_more is False
    assert len(paged) == 10
    assert [m["id"] for m in paged] == [f"msg_{i}" for i in range(10)]

    # 2. Latest page with limit=4: should return m6, m7, m8, m9 (last 4), has_more=True
    paged, has_more, total = get_paged_chat_messages(state, limit=4)
    assert total == 10
    assert has_more is True
    assert len(paged) == 4
    assert [m["id"] for m in paged] == ["msg_6", "msg_7", "msg_8", "msg_9"]

    # 3. Previous page before msg_6 with limit=4: should return m2, m3, m4, m5, has_more=True
    paged_prev, has_more_prev, total = get_paged_chat_messages(state, limit=4, before_id="msg_6")
    assert total == 10
    assert has_more_prev is True
    assert len(paged_prev) == 4
    assert [m["id"] for m in paged_prev] == ["msg_2", "msg_3", "msg_4", "msg_5"]

    # 4. Oldest page before msg_2 with limit=4: should return m0, m1, has_more=False
    paged_oldest, has_more_oldest, total = get_paged_chat_messages(state, limit=4, before_id="msg_2")
    assert total == 10
    assert has_more_oldest is False
    assert len(paged_oldest) == 2
    assert [m["id"] for m in paged_oldest] == ["msg_0", "msg_1"]

    # 5. before_id is oldest message msg_0: should return empty list, has_more=False
    paged_empty, has_more_empty, total = get_paged_chat_messages(state, limit=4, before_id="msg_0")
    assert total == 10
    assert has_more_empty is False
    assert paged_empty == []

    # 6. limit <= 0 returns all
    paged_all, has_more_all, total = get_paged_chat_messages(state, limit=0)
    assert total == 10
    assert has_more_all is False
    assert len(paged_all) == 10

