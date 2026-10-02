"""
Redis-backed persistence for AgentScope's `AgentState` (conversation
history), keyed by task id.

Why `AgentState` is the right unit to persist: it's the exact,
self-contained snapshot AgentScope itself hands to `Agent(state=...)` to
resume from — a plain pydantic `BaseModel` covering `context` (every
user/assistant/tool-call/tool-result message), `summary` (the
compression summary once the context has been auto-compacted), and the
tool/permission/task sub-contexts. AgentScope's own advanced storage
backends (`agentscope.app.storage.RedisStorage`) persist this same
object for the same reason — round-tripping it via
`model_dump_json()`/`model_validate_json()` is not a project-specific
hack, it's what the framework itself does.

Why Redis over a JSON file per task (like `workspaces/registry.json`):
this repo already has a local Redis container provisioned for exactly
this (see CLAUDE.md's environment notes, port 6380) — it gives atomic
writes for free (no partial-write corruption if the process dies
mid-save, unlike a naive file write), and a TTL so abandoned tasks'
history doesn't accumulate forever without a separate cleanup job.

Why *not* also persisting on every `RequireUserConfirmEvent` (only on
`ReplyEndEvent`, i.e. once a turn fully finishes): a snapshot taken
while a tool call is still awaiting confirmation would, on restore,
contain a `ToolCallBlock` with no matching `ToolResultBlock` —
AgentScope's own `reply_stream()` explicitly raises
(`"Agent is waiting for N tool calls ... but received no event"`,
see `agentscope/agent/_agent.py`) if you feed it a fresh message
against a state like that. Saving only completed turns means a restored
state is always internally consistent; the cost is that a crash during
a genuinely in-flight confirmation loses just that one unfinished turn,
never a corrupted one.
"""
import asyncio
import logging

import redis.asyncio as redis
from agentscope.message import (
    TextBlock,
    ToolCallBlock,
    ToolCallState,
    ToolResultBlock,
    ToolResultState,
)
from agentscope.state import AgentState
from pydantic import ValidationError

from server import config

logger = logging.getLogger(__name__)


def sanitize_agent_state(state: AgentState | None) -> bool:
    """
    检查并修复 state 中的挂起/未决工具调用 (ToolCallState.ASKING / SUBMITTED)。
    若某轮回复异常中断、超时、用户取消或收到未支持的外部工具调用，避免残留的
    未决状态导致下一轮 reply_stream 抛出 "Agent is waiting for ... tool calls" 异常。

    返回是否对 state 进行了修复修改。
    """
    if state is None or not state.context:
        return False

    modified = False
    for msg in state.context:
        if getattr(msg, "role", None) != "assistant":
            continue
        result_ids = {
            b.id for b in msg.get_content_blocks("tool_result") if hasattr(b, "id")
        }
        for b in msg.get_content_blocks("tool_call"):
            if b.state in (ToolCallState.ASKING, ToolCallState.SUBMITTED):
                b.state = ToolCallState.FINISHED
                modified = True
                if b.id not in result_ids:
                    msg.content.append(
                        ToolResultBlock(
                            id=b.id,
                            name=b.name,
                            output=[TextBlock(type="text", text="[已自动重置未决工具调用]")],
                            state=ToolResultState.INTERRUPTED,
                        )
                    )
                    result_ids.add(b.id)
    return modified

_KEY_PREFIX = "s_agent:agent_state:"


def _key(task_id: str) -> str:
    return f"{_KEY_PREFIX}{task_id}"


class AgentStateStore:
    """Thin async wrapper around one Redis connection pool."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis_client: redis.Redis | None = None

    def _get_client(self) -> redis.Redis:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._redis_client is None or self._loop is not current_loop:
            self._loop = current_loop
            self._redis_client = redis.Redis.from_url(self._redis_url, decode_responses=True)
        return self._redis_client

    @property
    def _client(self) -> redis.Redis:
        return self._get_client()

    async def save(self, task_id: str, state: AgentState) -> None:
        await self._client.set(
            _key(task_id),
            state.model_dump_json(),
            ex=config.AGENT_STATE_TTL_SECONDS,
        )

    async def load(self, task_id: str) -> AgentState | None:
        """Load a task's saved state, or `None` if there isn't one.

        A validation failure (e.g. a saved state from a since-upgraded,
        schema-incompatible AgentScope version) is treated the same as
        "no saved state" rather than raised — resuming with fresh, empty
        history is strictly better than a 500 on the next message.
        """
        raw = await self._client.get(_key(task_id))
        if raw is None:
            return None
        try:
            state = AgentState.model_validate_json(raw)
            if sanitize_agent_state(state):
                logger.warning(
                    "任务 %s 历史中存在未决的工具调用，已自动清理修复并重新持久化",
                    task_id,
                )
                await self.save(task_id, state)
            return state
        except ValidationError:
            logger.warning(
                "Discarding unreadable saved AgentState for task %s "
                "(likely an AgentScope version mismatch); starting fresh.",
                task_id,
            )
            return None

    async def delete(self, task_id: str) -> None:
        await self._client.delete(_key(task_id))

    async def close(self) -> None:
        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None
            self._loop = None


agent_state_store = AgentStateStore(config.REDIS_URL)
