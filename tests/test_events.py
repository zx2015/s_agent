"""Unit tests for the AgentScope -> SSE event translator.

Verifies `server/service/events.py` produces frames matching the wire
contract in `frontend/src/api/events.ts` (event names + JSON keys).
"""
import json
import pytest

from agentscope.event import (
    HintBlockEvent,
    ReplyEndEvent,
    RequireUserConfirmEvent,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    ToolResultTextDeltaEvent,
)
from agentscope.message import TextBlock, ToolCallBlock, ToolResultState
from agentscope.types import ErrorInfo

from server.service.events import (
    EVENT_NAMES,
    AgentEventTranslator,
    sse_frame,
    task_todos_changed_frame,
)


def _parse_one(frames: list[str]) -> tuple[str, dict]:
    assert len(frames) == 1
    lines = frames[0].split("\n")
    event = lines[0].removeprefix("event: ")
    data = json.loads(lines[1].removeprefix("data: "))
    return event, data


def test_thinking_delta_frame():
    translator = AgentEventTranslator()
    event, data = _parse_one(
        translator.translate(
            ThinkingBlockDeltaEvent(reply_id="r1", block_id="b1", delta="思考中"),
        ),
    )
    assert event == "thinking_delta"
    assert data == {"text": "思考中"}


def test_text_delta_frame():
    translator = AgentEventTranslator()
    event, data = _parse_one(
        translator.translate(
            TextBlockDeltaEvent(reply_id="r1", block_id="b1", delta="你好"),
        ),
    )
    assert event == "text_delta"
    assert data == {"text": "你好"}


def test_tool_call_start_then_end_accumulates_args_and_result():
    translator = AgentEventTranslator()

    start_frames = translator.translate(
        ToolCallStartEvent(reply_id="r1", tool_call_id="c1", tool_call_name="Bash"),
    )
    event, data = _parse_one(start_frames)
    assert event == "tool_call_start"
    assert data["call_id"] == "c1"
    assert data["tool"] == "Bash"

    # Args and result text stream in via delta events after the start event.
    assert translator.translate(
        ToolCallDeltaEvent(reply_id="r1", tool_call_id="c1", delta='{"command":'),
    ) == []
    assert translator.translate(
        ToolCallDeltaEvent(reply_id="r1", tool_call_id="c1", delta='"ls"}'),
    ) == []
    assert translator.translate(
        ToolResultTextDeltaEvent(reply_id="r1", tool_call_id="c1", delta="a.txt\n"),
    ) == []

    end_frames = translator.translate(
        ToolResultEndEvent(
            reply_id="r1",
            tool_call_id="c1",
            state=ToolResultState.SUCCESS,
        ),
    )
    event, data = _parse_one(end_frames)
    assert event == "tool_call_end"
    assert data == {
        "call_id": "c1",
        "status": "success",
        "result_summary": "a.txt\n",
    }


def test_tool_call_end_maps_non_success_states_to_error():
    translator = AgentEventTranslator()
    event, data = _parse_one(
        translator.translate(
            ToolResultEndEvent(
                reply_id="r1",
                tool_call_id="c1",
                state=ToolResultState.DENIED,
            ),
        ),
    )
    assert event == "tool_call_end"
    assert data["status"] == "error"


def test_require_confirm_frame_uses_bash_command_as_the_shown_command():
    translator = AgentEventTranslator()
    tool_call = ToolCallBlock(
        type="tool_call",
        id="c1",
        name="Bash",
        input=json.dumps({"command": "rm -rf build"}),
    )
    event, data = _parse_one(
        translator.translate(
            RequireUserConfirmEvent(reply_id="r1", tool_calls=[tool_call]),
        ),
    )
    assert event == "require_confirm"
    assert data["reply_id"] == "r1"
    assert data["command"] == "rm -rf build"
    assert data["action"] == "allow"


def test_reply_end_frame_reports_completed_and_failed():
    translator = AgentEventTranslator()
    event, data = _parse_one(
        translator.translate(ReplyEndEvent(reply_id="r1", session_id="s1")),
    )
    assert (event, data) == ("done", {"task_status": "completed"})

    event, data = _parse_one(
        translator.translate(
            ReplyEndEvent(
                reply_id="r1",
                session_id="s1",
                error=ErrorInfo(message="boom"),
            ),
        ),
    )
    assert (event, data) == ("done", {"task_status": "failed"})


def test_task_todos_changed_frame():
    todos = [
        {
            "id": "1",
            "subject": "读取配置",
            "description": "desc",
            "state": "pending",
            "owner": None,
            "blocks": [],
            "blockedBy": [],
            "createdAt": "2026-09-30T10:00:00Z",
        }
    ]
    frame = task_todos_changed_frame(todos)
    event, data = _parse_one([frame])
    assert event == "task_todos_changed"
    assert data == {"todos": todos}


def test_sse_frame_rejects_unknown_event():
    with pytest.raises(ValueError, match="Unknown SSE event"):
        sse_frame("unknown_event_type", {})


def test_hint_block_frame_with_string_hint():
    translator = AgentEventTranslator()
    frames = translator.translate(
        HintBlockEvent(
            reply_id="r1",
            block_id="b_hint_1",
            source="system",
            hint="当前时间为 2026-10-01 12:00:00",
        )
    )
    event, data = _parse_one(frames)
    assert event == "system_reminder"
    assert data["block_id"] == "b_hint_1"
    assert data["source"] == "system"
    assert data["content"] == "当前时间为 2026-10-01 12:00:00"


def test_hint_block_frame_with_block_list_hint():
    translator = AgentEventTranslator()
    frames = translator.translate(
        HintBlockEvent(
            reply_id="r1",
            block_id="b_hint_2",
            source="reminder",
            hint=[TextBlock(type="text", text="第一行提示\n"), TextBlock(type="text", text="第二行提示")],
        )
    )
    event, data = _parse_one(frames)
    assert event == "system_reminder"
    assert data["block_id"] == "b_hint_2"
    assert data["source"] == "reminder"
    assert data["content"] == "第一行提示\n第二行提示"

