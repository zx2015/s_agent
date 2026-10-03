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
    ToolResultState,
)
from agentscope.state import AgentState


def _serialize_tool_output(output: Any) -> str:
    """Best-effort string extraction for a tool call summary."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, (list, tuple)):
        texts: list[str] = []
        for item in output:
            if hasattr(item, "text"):
                texts.append(str(item.text))
            elif isinstance(item, dict) and "text" in item:
                texts.append(str(item["text"]))
            elif isinstance(item, str):
                texts.append(item)
            else:
                texts.append(str(item))
        return "\n".join(texts)
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

    # Pre-collect all tool results across the context so that tool calls
    # followed by tool results in subsequent messages can be resolved.
    results_by_id: dict[str, tuple[str, str]] = {}
    for msg in state.context:
        if not isinstance(msg, Msg):
            continue
        for block in getattr(msg, "content", []):
            if isinstance(block, ToolResultBlock):
                call_id = getattr(block, "id", "")
                output = getattr(block, "output", "")
                b_state = getattr(block, "state", None)
                status = (
                    "error"
                    if b_state in (
                        ToolResultState.ERROR,
                        ToolResultState.DENIED,
                        ToolResultState.INTERRUPTED,
                        "error",
                        "failed",
                        "interrupted",
                    )
                    else "success"
                )
                results_by_id[call_id] = (_serialize_tool_output(output), status)

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
        blocks: list[dict[str, Any]] = []

        for block in getattr(msg, "content", []):
            if isinstance(block, TextBlock):
                txt = getattr(block, "text", "")
                # AgentScope sometimes injects runtime facts as a user message
                # wrapped in <system-reminder>...</system-reminder>.
                if "<system-reminder>" in txt:
                    continue
                text_parts.append(txt)
                if blocks and blocks[-1]["type"] == "text":
                    blocks[-1]["content"] += ("\n" + txt)
                else:
                    blocks.append({"type": "text", "content": txt})

            elif isinstance(block, ThinkingBlock):
                th = getattr(block, "thinking", "")
                thinking_parts.append(th)
                if blocks and blocks[-1]["type"] == "thinking":
                    blocks[-1]["content"] += ("\n" + th)
                else:
                    blocks.append({"type": "thinking", "content": th})

            elif isinstance(block, ToolCallBlock):
                call_id = getattr(block, "id", "")
                res_tuple = results_by_id.get(call_id)
                summary = res_tuple[0] if res_tuple else ""
                status = res_tuple[1] if res_tuple else "success"
                call_dict = {
                    "callId": call_id,
                    "tool": getattr(block, "name", ""),
                    "args": _safe_json_loads(getattr(block, "input", "")),
                    "status": status,
                    "summary": summary,
                }
                tool_calls.append(call_dict)
                blocks.append({"type": "tool_call", "call": call_dict})

            elif isinstance(block, ToolResultBlock):
                # Captured via results_by_id and attached to ToolCallBlock
                pass

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
                "blocks": blocks,
                "streaming": False,
            }
        )

    return messages


def get_paged_chat_messages(
    state: AgentState | None,
    limit: int = 30,
    before_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool, int]:
    """Return a paged slice of chat messages, plus has_more flag and total count.

    Args:
        state: The saved AgentState from Redis.
        limit: Number of messages to return in this page. If limit <= 0, returns all.
        before_id: Cursor pointing to a message id. When provided, returns messages
            immediately preceding this message. When None, returns the latest messages.

    Returns:
        (paged_messages, has_more, total)
    """
    all_messages = agent_state_to_chat_messages(state)
    total = len(all_messages)
    if total == 0:
        return [], False, 0

    if limit <= 0:
        return all_messages, False, total

    if before_id:
        target_idx = next((i for i, m in enumerate(all_messages) if m.get("id") == before_id), -1)
        if target_idx == -1:
            end_idx = total
        else:
            end_idx = target_idx
    else:
        end_idx = total

    start_idx = max(0, end_idx - limit)
    paged = all_messages[start_idx:end_idx]
    has_more = start_idx > 0
    return paged, has_more, total


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
