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
import logging

import redis.asyncio as redis
from agentscope.state import AgentState
from pydantic import ValidationError

from server import config

logger = logging.getLogger(__name__)

_KEY_PREFIX = "s_agent:agent_state:"


def _key(task_id: str) -> str:
    return f"{_KEY_PREFIX}{task_id}"


class AgentStateStore:
    """Thin async wrapper around one Redis connection pool."""

    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

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
            return AgentState.model_validate_json(raw)
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
        await self._client.aclose()


agent_state_store = AgentStateStore(config.REDIS_URL)
