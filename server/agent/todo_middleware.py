# -*- coding: utf-8 -*-
"""Todo lifecycle and continuation guardrail middleware for AgentScope agents."""
from typing import AsyncGenerator, Callable, TYPE_CHECKING
import logging

from agentscope.event import ReplyEndEvent, ReplyFinishedReason
from agentscope.message import HintBlock
from agentscope.middleware import MiddlewareBase

if TYPE_CHECKING:
    from agentscope.agent import Agent

logger = logging.getLogger(__name__)


class TodoLifecycleMiddleware(MiddlewareBase):
    """Middleware that manages the todo lifecycle and enforces task continuation.

    Key responsibilities:
    1. Prunes completed todos so they do not clutter context or frontend panels.
    2. Intercepts premature conclusion when valid uncompleted todos remain,
       prompting the agent to validate their effectiveness and complete them.
    """

    def __init__(self, max_checks: int = 2) -> None:
        super().__init__()
        self.max_checks = max_checks

    @staticmethod
    def _prune_completed_todos(agent: "Agent") -> int:
        """Prune todos with state == 'completed' from agent.state.tasks_context."""
        if (
            not hasattr(agent.state, "tasks_context")
            or agent.state.tasks_context is None
            or not agent.state.tasks_context.tasks
        ):
            return 0

        tasks = agent.state.tasks_context.tasks
        completed = [t for t in tasks if t.state == "completed"]
        if not completed:
            return 0

        completed_ids = {t.id for t in completed}
        agent.state.tasks_context.tasks = [
            t for t in tasks if t.state != "completed"
        ]

        # Clean up block relations
        for t in agent.state.tasks_context.tasks:
            t.blocked_by = [
                bid for bid in t.blocked_by if bid not in completed_ids
            ]
            t.blocks = [
                bid for bid in t.blocks if bid not in completed_ids
            ]

        logger.debug(
            "TodoLifecycleMiddleware: pruned %d completed todos: %s",
            len(completed),
            completed_ids,
        )
        return len(completed)

    async def on_reasoning(
        self,
        agent: "Agent",
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """Prune completed tasks at the beginning of each reasoning step."""
        self._prune_completed_todos(agent)
        async for event in next_handler(**input_kwargs):
            yield event

    async def on_reply(
        self,
        agent: "Agent",
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """Intercept ReplyEndEvent to enforce todo completion and continuation."""
        middleware_key = await self.get_middleware_key()

        async for event in next_handler(**input_kwargs):
            if isinstance(event, ReplyEndEvent):
                # Always clean completed tasks first
                self._prune_completed_todos(agent)

                # Never swallow interrupted replies (e.g. user abort / HITL)
                if event.finished_reason == ReplyFinishedReason.INTERRUPTED:
                    yield event
                    continue

                # Check for remaining uncompleted tasks
                tasks = getattr(agent.state.tasks_context, "tasks", [])
                uncompleted_tasks = [
                    t for t in tasks
                    if t.state in ("pending", "in_progress")
                ]

                # If no uncompleted tasks, clean exit
                if not uncompleted_tasks:
                    if middleware_key in agent.state.middle_context:
                        agent.state.middle_context[middleware_key].pop(
                            event.reply_id,
                            None,
                        )
                    yield event
                    continue

                # Check retry budget to avoid infinite loops
                reply_id = agent.state.reply_id
                if middleware_key not in agent.state.middle_context:
                    agent.state.middle_context[middleware_key] = {}
                check_count = agent.state.middle_context[middleware_key].get(
                    reply_id,
                    0,
                )

                if check_count < self.max_checks:
                    agent.state.middle_context[middleware_key][reply_id] = (
                        check_count + 1
                    )

                    task_items = "\n".join(
                        f"- #{t.id}: {t.subject} (状态: {t.state})"
                        for t in uncompleted_tasks
                    )
                    reminder_text = (
                        "<system-reminder>\n"
                        "【待办未竟与有效性闭环提醒】：\n"
                        "检测到待办列表中仍有未完成的待办任务：\n"
                        f"{task_items}\n\n"
                        "根据待办闭环公约，当前任务不能直接结束交付：\n"
                        "1. 已完成的待办已自动清理；\n"
                        "2. 请逐项审查上述未完成待办是否依然有效且必要：\n"
                        "   - 若已无效/冗余/已不适用：请调用 TaskUpdate(task_id='...', status='deleted') 进行清理剪枝，并在回复中简要说明原因；\n"
                        "   - 若仍然有效：严禁提前结束！必须立即调用相应工具或委派子智能体执行该待办任务，直到其完成交付！\n"
                        "</system-reminder>"
                    )
                    hint_block = HintBlock(hint=reminder_text)
                    agent.state.append_context(agent.name, [hint_block])

                    # Ensure agent has iteration headroom for the next round
                    if agent.state.cur_iter >= agent.react_config.max_iters:
                        agent.react_config.max_iters = agent.state.cur_iter + 5

                    logger.info(
                        "TodoLifecycleMiddleware: intercepted reply end with %d uncompleted tasks (check %d/%d). Prompting agent to continue.",
                        len(uncompleted_tasks),
                        check_count + 1,
                        self.max_checks,
                    )
                    # Swallow ReplyEndEvent to trigger the next reasoning round!
                    continue
                else:
                    logger.warning(
                        "TodoLifecycleMiddleware: check_count reached max %d for uncompleted tasks, releasing reply end.",
                        self.max_checks,
                    )
                    agent.state.middle_context[middleware_key].pop(
                        event.reply_id,
                        None,
                    )
                    yield event
                    continue

            yield event
