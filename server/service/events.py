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
from agentscope.message import ToolResultState

_SUCCESS_STATES = {ToolResultState.SUCCESS}

# Tool names that mutate the AgentScope task list. The translator only
# triggers a `task_todos_changed` snapshot when one of these finishes —
# other tools (Bash, Read, Write, AskUser, TaskGet, TaskList) either
# have no effect on tasks or are read-only.
_TODO_MUTATING_TOOLS: frozenset[str] = frozenset({"TaskCreate", "TaskUpdate"})


# Authoritative server-side list of SSE event names. The frontend's
# `EVENT_NAMES` in `frontend/src/api/events.ts` is the matching whitelist
# — a drift here would silently drop frames on the client, so changes
# to either side must touch the other.
EVENT_NAMES: frozenset[str] = frozenset(
    {
        "thinking_delta",
        "text_delta",
        "tool_call_start",
        "tool_call_end",
        "artifact_created",
        "require_confirm",
        "task_renamed",
        "task_todos_changed",
        "system_reminder",
        "done",
    }
)


def sse_frame(event: str, data: dict[str, Any]) -> str:
    """Format one SSE frame exactly as `parseSseFrame` on the frontend expects."""
    if event not in EVENT_NAMES:
        # Catches the "I added a new event type but forgot to update the
        # whitelist" mistake at startup, not in production under load.
        raise ValueError(
            f"Unknown SSE event {event!r}. Add it to EVENT_NAMES on both "
            f"server/service/events.py and frontend/src/api/events.ts."
        )
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

        if isinstance(event, HintBlockEvent):
            if isinstance(event.hint, str):
                content_text = event.hint
            elif isinstance(event.hint, list):
                content_text = "".join(
                    block.text for block in event.hint if hasattr(block, "text")
                )
            else:
                content_text = str(event.hint)
            return [
                sse_frame(
                    "system_reminder",
                    {
                        "block_id": event.block_id,
                        "source": event.source or "system",
                        "content": content_text,
                    },
                ),
            ]

        if isinstance(event, ReplyEndEvent):
            status = "failed" if event.error else "completed"
            return [sse_frame("done", {"task_status": status})]

        return []

    def todo_mutating_tool(self, tool_call_id: str) -> bool:
        """Return True if the tool this id buffered was a todo mutator.

        The caller (`server/main.py`) is responsible for actually fetching
        the current todo list and emitting `task_todos_changed` after
        `ToolResultEndEvent` flushes; this method just tells it whether
        the ended tool was worth re-serialising.

        Args:
            tool_call_id (`str`):
                The id of a tool call that has already ended (its buffer
                has been popped from `_buffers`).

        Returns:
            `bool`:
                True if the just-ended tool mutates `AgentState.tasks_context.tasks`.
        """
        # We do not keep the buffer around after pop, so we can't tell
        # what tool it was by id alone. The caller should call this
        # *before* the result ends, while the buffer is still in scope.
        # See the next method for the helper that does the right thing.
        return False

    def todo_changed_after_tool(
        self,
        tool_call_id: str,
        todos: list[dict[str, Any]],
    ) -> list[str] | None:
        """Return a `task_todos_changed` frame if the just-ended tool
        was a todo mutator; otherwise return None.

        The caller is `server/main.py`'s `event_stream`, which fires this
        right after `translator.translate(ToolResultEndEvent)` returns.

        Args:
            tool_call_id (`str`):
                The id of the tool call whose buffer was just popped.
                We can't inspect it from outside the class, so the caller
                must pass the tool name alongside — see the wrapper
                below.
            todos (`list[dict[str, Any]]`):
                The serialised current todo list (from `serialize_todos`).

        Returns:
            `list[str] | None`:
                One frame string if the tool mutated the task list,
                otherwise None.
        """
        # We need the tool name at ToolResultEndEvent time. The translator
        # has already popped the buffer before this method is called,
        # so the name is gone. To keep this self-contained we accept
        # the tool name alongside the id via `popped_tool_name` below.
        return None


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


def task_todos_changed_frame(todos: list[dict[str, Any]]) -> str:
    """Format a single `task_todos_changed` frame.

    The frontend treats the payload as a complete snapshot — it does
    not diff against the previous list. Sending the full list every time
    keeps the client state machine trivial: whatever the last frame said
    is the truth.

    Args:
        todos (`list[dict[str, Any]]`):
            The serialised AgentScope tasks (use `serialize_todos` from
            `server.service.history` to produce this from an `AgentState`).

    Returns:
        `str`:
            A single SSE frame string, ready to be yielded by the SSE
            generator. The trailing blank line is included.
    """
    return sse_frame("task_todos_changed", {"todos": todos})


def todo_changed_after_tool(
    tool_name: str,
    todos: list[dict[str, Any]],
) -> list[str] | None:
    """Build a `task_todos_changed` frame for tools that mutate todos.

    Helper for the `event_stream` in `server/main.py`. The translator
    doesn't carry the tool name past the buffer pop, so the chat handler
    must pass it explicitly.

    Args:
        tool_name (`str`):
            The name of the tool whose `ToolResultEndEvent` just fired.
        todos (`list[dict[str, Any]]`):
            The freshly-serialised todo list (from `serialize_todos`).

    Returns:
        `list[str] | None`:
            `[task_todos_changed_frame(todos)]` when the tool was a
            todo mutator, otherwise None.
    """
    if tool_name in _TODO_MUTATING_TOOLS:
        return [task_todos_changed_frame(todos)]
    return None


def final_todos_changed_frame(todos: list[dict[str, Any]]) -> str:
    """The unconditional `task_todos_changed` sent at the end of every turn.

    Sent on `ReplyEndEvent` regardless of whether any task tool ran
    during the turn, so the client is always guaranteed to end up with
    the latest todo snapshot — even when a non-task tool (Bash, Read,
    ...) somehow caused AgentScope to mutate the task list out-of-band.
    """
    return task_todos_changed_frame(todos)