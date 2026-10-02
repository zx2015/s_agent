"""Tests for TodoLifecycleMiddleware and todo continuation guardrail."""
import asyncio
from pathlib import Path
import pytest

from agentscope.agent import Agent
from agentscope.event import ReplyEndEvent, ReplyFinishedReason
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, TextBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.state import AgentState, Task

from server.agent.todo_middleware import TodoLifecycleMiddleware


class MockChatModel(ChatModelBase):
    class Parameters:
        pass

    def __init__(self, responses: list[str]) -> None:
        super().__init__(
            model="mock",
            credential=None,
            stream=False,
            parameters=MockChatModel.Parameters(),
        )
        self.responses = responses
        self.call_count = 0
        self.stream = False
        self.formatter = OpenAIChatFormatter()

    async def _call_api(self, *args, **kwargs):
        idx = min(self.call_count, len(self.responses) - 1)
        resp_text = self.responses[idx]
        self.call_count += 1
        return ChatResponse(
            content=[TextBlock(text=resp_text)],
            is_last=True,
        )


@pytest.mark.asyncio
async def test_prune_completed_todos_standalone():
    """Verify that _prune_completed_todos removes completed tasks and updates block lists."""
    state = AgentState()
    t1 = Task(id="1", subject="数据抓取", description="", state="completed", blocks=["2"], metadata={})
    t2 = Task(id="2", subject="财务建模", description="", state="in_progress", blocked_by=["1"], metadata={})
    t3 = Task(id="3", subject="研报撰写", description="", state="pending", metadata={})
    state.tasks_context.tasks = [t1, t2, t3]

    dummy_agent = type("DummyAgent", (), {"state": state})()
    pruned_count = TodoLifecycleMiddleware._prune_completed_todos(dummy_agent)

    assert pruned_count == 1
    assert len(state.tasks_context.tasks) == 2
    remaining_ids = [t.id for t in state.tasks_context.tasks]
    assert remaining_ids == ["2", "3"]
    # Verify blocked_by has been cleared of the completed task id
    t2_after = state.tasks_context.tasks[0]
    assert t2_after.id == "2"
    assert "1" not in t2_after.blocked_by


@pytest.mark.asyncio
async def test_all_completed_pruned_clean():
    """When all tasks are completed, the task list should be pruned to empty."""
    state = AgentState()
    t1 = Task(id="1", subject="任务1", description="", state="completed", metadata={})
    t2 = Task(id="2", subject="任务2", description="", state="completed", metadata={})
    state.tasks_context.tasks = [t1, t2]

    dummy_agent = type("DummyAgent", (), {"state": state})()
    pruned = TodoLifecycleMiddleware._prune_completed_todos(dummy_agent)

    assert pruned == 2
    assert len(state.tasks_context.tasks) == 0


@pytest.mark.asyncio
async def test_middleware_prunes_completed_and_intercepts_uncompleted():
    """Verify middleware swallows ReplyEndEvent when uncompleted tasks exist, then finishes after resolution."""
    model = MockChatModel([
        "我已完成第一步，这是阶段结论。",
        "收到提醒，我现在继续完成剩余待办并汇报最终结论。",
    ])

    mw = TodoLifecycleMiddleware(max_checks=2)
    state = AgentState()
    t1 = Task(id="1", subject="数据抓取", description="", state="completed", metadata={})
    t2 = Task(id="2", subject="竞品横向对比", description="", state="pending", metadata={})
    state.tasks_context.tasks = [t1, t2]

    agent = Agent(
        name="Assistant",
        system_prompt="You are a helpful assistant",
        model=model,
        state=state,
        middlewares=[mw],
    )

    # Custom observer to simulate task completion during the continuation round
    original_call = model._call_api

    async def hooked_call(*args, **kwargs):
        res = await original_call(*args, **kwargs)
        if model.call_count == 2:
            # During second round, simulate that t2 was completed and pruned
            agent.state.tasks_context.tasks = []
        return res

    model._call_api = hooked_call

    reply_msg = await agent.reply(UserMsg(name="user", content=[TextBlock(text="请分析伊利与蒙牛")]))

    # Model was called twice: round 1 intercepted, round 2 completed
    assert model.call_count == 2
    assert "收到提醒" in reply_msg.content[0].text
    # All tasks finished and pruned
    assert len(agent.state.tasks_context.tasks) == 0


@pytest.mark.asyncio
async def test_middleware_max_checks_prevents_loop():
    """Verify middleware does not loop infinitely if tasks remain uncompleted after max_checks."""
    model = MockChatModel([
        "交卷1",
        "交卷2",
        "交卷3",
    ])

    mw = TodoLifecycleMiddleware(max_checks=2)
    state = AgentState()
    t1 = Task(id="1", subject="未完成待办", description="", state="pending", metadata={})
    state.tasks_context.tasks = [t1]

    agent = Agent(
        name="Assistant",
        system_prompt="You are a helpful assistant",
        model=model,
        state=state,
        middlewares=[mw],
    )

    reply_msg = await agent.reply(UserMsg(name="user", content=[TextBlock(text="开始")]))

    # Called 3 times: initial + 2 retry checks, then released safely
    assert model.call_count == 3
    assert "交卷3" in reply_msg.content[0].text


@pytest.mark.asyncio
async def test_interrupted_reply_never_swallowed():
    """Interrupted replies should immediately yield ReplyEndEvent without swallowing."""
    mw = TodoLifecycleMiddleware(max_checks=2)
    state = AgentState()
    t1 = Task(id="1", subject="未完成待办", description="", state="pending", metadata={})
    state.tasks_context.tasks = [t1]

    agent = type("DummyAgent", (), {
        "state": state,
        "name": "Assistant",
    })()

    end_event = ReplyEndEvent(
        reply_id="r1",
        session_id="s1",
        finished_reason=ReplyFinishedReason.INTERRUPTED,
    )

    async def fake_handler(**kwargs):
        yield end_event

    yielded = []
    async for item in mw.on_reply(agent, {}, fake_handler):
        yielded.append(item)

    assert len(yielded) == 1
    assert yielded[0] is end_event


@pytest.mark.asyncio
async def test_agent_core_factory_includes_todo_middleware(tmp_path):
    """Verify that build_agent attaches TodoLifecycleMiddleware."""
    from unittest.mock import patch, AsyncMock
    from server.agent.core import build_agent

    with patch("server.agent.core.resolve_context_size", new=AsyncMock(return_value=128000)):
        agent = await build_agent(
            workspace_dir=Path(tmp_path),
            memory_dir=Path(tmp_path / "memory"),
        )

    has_todo_mw = any(
        isinstance(m, TodoLifecycleMiddleware)
        for m in getattr(agent, "_reply_middlewares", [])
    )
    assert has_todo_mw, "TodoLifecycleMiddleware must be registered in the agent's reply middlewares chain"
