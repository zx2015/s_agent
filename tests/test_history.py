"""Unit tests for serialising AgentScope AgentState into frontend ChatMessages."""
import json
from agentscope.message import Msg, TextBlock, ThinkingBlock, ToolCallBlock, ToolResultBlock
from agentscope.state import AgentState

from server.service.history import agent_state_to_chat_messages


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
