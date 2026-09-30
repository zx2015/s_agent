"""
Transform an AgentScope AgentState into frontend ChatMessages.

Used by `GET /api/tasks/{task_id}/messages` to hydrate the middle pane
when the user switches tasks in the sidebar. The returned shape matches
`frontend/src/types/index.ts::ChatMessage` exactly, so the frontend can
assign the list directly to `sessionStore.messages`.
"""
from __future__ import annotations

import json
from typing import Any

from agentscope.message import (
    Msg,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from agentscope.state import AgentState


def _serialize_tool_output(output: Any) -> str:
    """Best-effort string extraction for a tool call summary."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(output)


def _safe_json_loads(raw: str) -> dict[str, Any]:
    """Parse tool input, returning an empty dict on malformed input."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"_": data}
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


def agent_state_to_chat_messages(state: AgentState | None) -> list[dict[str, Any]]:
    """Convert an AgentState's context into frontend-friendly ChatMessages.

    Args:
        state: The saved AgentState from Redis (or in-memory cache). When
            None or empty, returns an empty list.

    Returns:
        A list of dicts with the shape of `frontend/src/types/index.ts::ChatMessage`.
    """
    if state is None or not state.context:
        return []

    messages: list[dict[str, Any]] = []

    for msg in state.context:
        if not isinstance(msg, Msg):
            continue

        # Skip system prompts and runtime reminders (e.g. <system-reminder>).
        # These are internal to the model and must never be shown as chat bubbles.
        role = getattr(msg, "role", "")
        if role == "system":
            continue

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        # ToolResult blocks in AgentScope sometimes trail their matching
        # ToolCallBlock in the same message or in a subsequent message.
        # Track by call id to patch summaries into the call records.
        results_by_id: dict[str, str] = {}

        for block in getattr(msg, "content", []):
            if isinstance(block, TextBlock):
                txt = getattr(block, "text", "")
                # AgentScope sometimes injects runtime facts as a user message
                # wrapped in <system-reminder>...</system-reminder>.
                if "<system-reminder>" in txt:
                    continue
                text_parts.append(txt)
            elif isinstance(block, ThinkingBlock):
                thinking_parts.append(getattr(block, "thinking", ""))
            elif isinstance(block, ToolCallBlock):
                tool_calls.append(
                    {
                        "callId": getattr(block, "id", ""),
                        "tool": getattr(block, "name", ""),
                        "args": _safe_json_loads(getattr(block, "input", "")),
                        "status": "success",
                        "summary": "",
                    }
                )
            elif isinstance(block, ToolResultBlock):
                call_id = getattr(block, "id", "")
                output = getattr(block, "output", "")
                results_by_id[call_id] = _serialize_tool_output(output)

        # Patch summaries into matching tool calls
        for call in tool_calls:
            cid = call["callId"]
            if cid in results_by_id:
                call["summary"] = results_by_id[cid]

        # A message that ended up with no displayable content (e.g. pure
        # system-reminder user message) should be dropped.
        if not text_parts and not thinking_parts and not tool_calls:
            continue

        messages.append(
            {
                "id": getattr(msg, "id", f"hist-{len(messages)}"),
                "role": role if role in ("user", "assistant") else "assistant",
                "text": "\n".join(text_parts),
                "thinking": "\n".join(thinking_parts),
                "toolCalls": tool_calls,
                "streaming": False,
            }
        )

    return messages


def serialize_todos(state: AgentState | None) -> list[dict[str, Any]]:
    """Convert an AgentState's task list into the frontend TodoItem shape.

    Reads `AgentState.tasks_context.tasks` — the tasks the agent created
    or updated during its run via `TaskCreate`/`TaskUpdate`.

    Args:
        state: The saved `AgentState` from Redis. When None or the state has
            never had tasks recorded, returns an empty list.

    Returns:
        A list of dicts with the shape of `docs/specs/2026-09-28-todo-display.md`:
        id, subject, description, state, owner, blocks, blockedBy, createdAt.
    """
    if state is None:
        return []
    tasks_context = getattr(state, "tasks_context", None)
    if tasks_context is None:
        return []
    raw_tasks = getattr(tasks_context, "tasks", []) or []

    todos: list[dict[str, Any]] = []
    for t in raw_tasks:
        todos.append(
            {
                "id": str(getattr(t, "id", "")),
                "subject": str(getattr(t, "subject", "")),
                "description": str(getattr(t, "description", "") or ""),
                "state": getattr(t, "state", "pending"),
                "owner": getattr(t, "owner", None),
                "blocks": list(getattr(t, "blocks", []) or []),
                "blockedBy": list(getattr(t, "blocked_by", []) or []),
                "createdAt": str(getattr(t, "created_at", "") or ""),
            }
        )
    return todos
