"""
Translate AgentScope's `reply_stream` events into the SSE wire contract.

This is the server-side mirror of `frontend/src/api/events.ts` — the two
must stay in lockstep. Event *names* and payload *keys* here are pinned
to that file; if one changes, check the other.

Two AgentScope quirks drive the buffering in this module:

1. `ToolCallStartEvent` carries only a tool name and id, not arguments —
   arguments stream in afterwards as raw JSON text via
   `ToolCallDeltaEvent`. Rather than delaying the "running" UI state
   until the call is fully known, `tool_call_start` is emitted with
   whatever has accumulated so far (often still empty); the full
   command is visible anyway once the result comes back.
2. `ToolResultEndEvent` carries a state but not the result text — that
   arrives separately via `ToolResultTextDeltaEvent`. This module
   accumulates both per `tool_call_id` and flushes them into a single
   `tool_call_end` frame.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from agentscope.event import (
    ReplyEndEvent,
    RequireUserConfirmEvent,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    ToolResultTextDeltaEvent,
)
from agentscope.message import ToolResultState

_SUCCESS_STATES = {ToolResultState.SUCCESS}


def sse_frame(event: str, data: dict[str, Any]) -> str:
    """Format one SSE frame exactly as `parseSseFrame` on the frontend expects."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class _ToolCallBuffer:
    tool_name: str = ""
    args_json: str = ""
    result_text: str = ""


@dataclass
class AgentEventTranslator:
    """Stateful translator for one turn (one `reply_stream` call)."""

    _buffers: dict[str, _ToolCallBuffer] = field(default_factory=dict)

    def translate(self, event: Any) -> list[str]:
        """Convert one AgentScope event into zero or more SSE frames."""
        if isinstance(event, ThinkingBlockDeltaEvent):
            return [sse_frame("thinking_delta", {"text": event.delta})]

        if isinstance(event, TextBlockDeltaEvent):
            return [sse_frame("text_delta", {"text": event.delta})]

        if isinstance(event, ToolCallStartEvent):
            buffer = self._buffers.setdefault(
                event.tool_call_id,
                _ToolCallBuffer(),
            )
            buffer.tool_name = event.tool_call_name
            return [
                sse_frame(
                    "tool_call_start",
                    {
                        "call_id": event.tool_call_id,
                        "tool": event.tool_call_name,
                        "args": _parse_args(buffer.args_json),
                    },
                ),
            ]

        if isinstance(event, ToolCallDeltaEvent):
            buffer = self._buffers.setdefault(
                event.tool_call_id,
                _ToolCallBuffer(),
            )
            buffer.args_json += event.delta
            return []

        if isinstance(event, ToolResultTextDeltaEvent):
            buffer = self._buffers.setdefault(
                event.tool_call_id,
                _ToolCallBuffer(),
            )
            buffer.result_text += event.delta
            return []

        if isinstance(event, ToolResultEndEvent):
            buffer = self._buffers.pop(event.tool_call_id, _ToolCallBuffer())
            status = "success" if event.state in _SUCCESS_STATES else "error"
            return [
                sse_frame(
                    "tool_call_end",
                    {
                        "call_id": event.tool_call_id,
                        "status": status,
                        "result_summary": buffer.result_text[:4000],
                    },
                ),
            ]

        if isinstance(event, RequireUserConfirmEvent):
            tool_call = event.tool_calls[0]
            return [
                sse_frame(
                    "require_confirm",
                    {
                        "reply_id": event.reply_id,
                        "command": _format_tool_call(tool_call),
                        "reason": f"{tool_call.name} 属于高危操作，需要人工确认",
                        "action": "allow",
                    },
                ),
            ]

        if isinstance(event, ReplyEndEvent):
            status = "failed" if event.error else "completed"
            return [sse_frame("done", {"task_status": status})]

        return []


def _parse_args(args_json: str) -> dict[str, Any]:
    if not args_json:
        return {}
    try:
        parsed = json.loads(args_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _format_tool_call(tool_call: Any) -> str:
    args = _parse_args(tool_call.input)
    if tool_call.name == "Bash" and "command" in args:
        return str(args["command"])
    return f"{tool_call.name}({json.dumps(args, ensure_ascii=False)})"
