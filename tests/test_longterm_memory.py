"""Tests for long-term memory (AgenticMemoryMiddleware) cross-task persistence."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from agentscope.agent import Agent
from agentscope.message import Msg, TextBlock
from agentscope.middleware import AgenticMemoryMiddleware
from agentscope.model import StructuredResponse

from server import config
from server.agent.core import CHINESE_MEMORY_INSTRUCTIONS, build_agent


@pytest.mark.asyncio
async def test_build_agent_mounts_memory_middleware(tmp_path: Path):
    """build_agent mounts AgenticMemoryMiddleware when LONGTERM_MEMORY_ENABLED is True."""
    workspace = tmp_path / "workspace"
    mem_dir = tmp_path / "shared_memory"

    agent = await build_agent(workspace, memory_dir=mem_dir)
    assert isinstance(agent, Agent)

    # Middleware should be registered across reply, reasoning, and system_prompt hooks
    memory_mws = [
        mw for mw in agent._system_prompt_middlewares
        if isinstance(mw, AgenticMemoryMiddleware)
    ]
    assert len(memory_mws) == 1
    assert any(isinstance(mw, AgenticMemoryMiddleware) for mw in agent._reply_middlewares)
    assert any(isinstance(mw, AgenticMemoryMiddleware) for mw in agent._reasoning_middlewares)

    # MEMORY.md should be automatically created in the memory directory
    assert (mem_dir / "MEMORY.md").exists()


@pytest.mark.asyncio
async def test_build_agent_respects_disabled_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When LONGTERM_MEMORY_ENABLED is False, no memory middleware is mounted."""
    monkeypatch.setattr(config, "LONGTERM_MEMORY_ENABLED", False)
    workspace = tmp_path / "workspace"
    mem_dir = tmp_path / "shared_memory"

    agent = await build_agent(workspace, memory_dir=mem_dir)
    assert len(agent._system_prompt_middlewares) == 0
    assert len(agent._reply_middlewares) == 0
    assert len(agent._reasoning_middlewares) == 0


@pytest.mark.asyncio
async def test_system_prompt_includes_memory_manifest(tmp_path: Path):
    """_get_system_prompt() includes Chinese instructions and MEMORY.md content."""
    workspace = tmp_path / "workspace"
    mem_dir = tmp_path / "shared_memory"
    mem_dir.mkdir(parents=True, exist_ok=True)

    index_content = (
        "- [user_pref](user_pref.md) (2026-10-01): 稳健型投资与夏普比率计算\n"
        "- [feedback_calc](feedback_calc.md) (2026-10-01): 必须调用 calculate 工具"
    )
    (mem_dir / "MEMORY.md").write_text(index_content, encoding="utf-8")

    agent = await build_agent(workspace, memory_dir=mem_dir)
    system_prompt = await agent._get_system_prompt()

    assert "跨任务持久化文件记忆库" in system_prompt
    assert str(mem_dir.resolve()) in system_prompt
    assert "user_pref" in system_prompt
    assert "feedback_calc" in system_prompt
    assert "稳健型投资与夏普比率计算" in system_prompt


@pytest.mark.asyncio
async def test_memory_frontmatter_parsing_and_listing(tmp_path: Path):
    """_list_md_files parses YAML frontmatter and excludes MEMORY.md."""
    workspace = tmp_path / "workspace"
    mem_dir = tmp_path / "shared_memory"
    mem_dir.mkdir(parents=True, exist_ok=True)

    card1 = mem_dir / "user_risk.md"
    card1.write_text(
        "---\n"
        "name: user_risk\n"
        "description: 用户投资偏好与仓位要求\n"
        "type: user\n"
        "---\n"
        "用户偏好稳健型投资，单票不超过20%。",
        encoding="utf-8",
    )

    card2 = mem_dir / "rule_calc.md"
    card2.write_text(
        "---\n"
        "name: rule_calc\n"
        "description: 股票量化计算规范\n"
        "type: feedback\n"
        "---\n"
        "严禁心算，必须调用 calculate 工具。",
        encoding="utf-8",
    )

    (mem_dir / "MEMORY.md").write_text("- [user_risk](user_risk.md)\n- [rule_calc](rule_calc.md)\n")

    agent = await build_agent(workspace, memory_dir=mem_dir)
    mw: AgenticMemoryMiddleware = agent._system_prompt_middlewares[0]

    headers = await mw._list_md_files()
    assert len(headers) == 2
    filenames = {h.filename for h in headers}
    assert filenames == {"user_risk.md", "rule_calc.md"}

    header_map = {h.filename: h for h in headers}
    assert header_map["user_risk.md"].type == "user"
    assert header_map["user_risk.md"].description == "用户投资偏好与仓位要求"
    assert header_map["rule_calc.md"].type == "feedback"


@pytest.mark.asyncio
async def test_cross_task_memory_sharing(tmp_path: Path):
    """Task A and Task B share the same long-term memory store."""
    shared_mem_dir = tmp_path / "global_shared_memory"
    task_a_workspace = tmp_path / "workspace_task_a"
    task_b_workspace = tmp_path / "workspace_task_b"

    # Agent A in Task A
    agent_a = await build_agent(task_a_workspace, memory_dir=shared_mem_dir)
    # Agent A writes a memory card to the shared memory directory
    card_path = shared_mem_dir / "portfolio_rule.md"
    card_path.write_text(
        "---\n"
        "name: portfolio_rule\n"
        "description: 投资组合风控规则：严格止损8%\n"
        "type: project\n"
        "---\n"
        "所有股票持仓严格执行8%止损线。",
        encoding="utf-8",
    )
    # Agent A updates MEMORY.md
    (shared_mem_dir / "MEMORY.md").write_text(
        "- [portfolio_rule](portfolio_rule.md) (2026-10-01): 投资组合风控规则：严格止损8%\n",
        encoding="utf-8",
    )

    # Agent B in Task B (different workspace, but same shared memory_dir)
    agent_b = await build_agent(task_b_workspace, memory_dir=shared_mem_dir)
    prompt_b = await agent_b._get_system_prompt()

    assert "portfolio_rule" in prompt_b
    assert "严格止损8%" in prompt_b

    # Verify Agent B's memory middleware scans the file created by Agent A
    mw_b: AgenticMemoryMiddleware = agent_b._system_prompt_middlewares[0]
    headers_b = await mw_b._list_md_files()
    assert any(h.filename == "portfolio_rule.md" for h in headers_b)


@pytest.mark.asyncio
async def test_async_retrieval_and_hint_injection(tmp_path: Path):
    """on_reply starts async retrieval and on_reasoning injects HintBlock into agent context."""
    workspace = tmp_path / "workspace"
    mem_dir = tmp_path / "shared_memory"
    mem_dir.mkdir(parents=True, exist_ok=True)

    (mem_dir / "user_pref.md").write_text(
        "---\n"
        "name: user_pref\n"
        "description: 用户偏好贵州茅台(600519)\n"
        "type: user\n"
        "---\n"
        "用户最关注贵州茅台，偏好长期持有。",
        encoding="utf-8",
    )
    (mem_dir / "MEMORY.md").write_text("- [user_pref](user_pref.md): 用户偏好茅台\n")

    agent = await build_agent(workspace, memory_dir=mem_dir)
    mw: AgenticMemoryMiddleware = agent._system_prompt_middlewares[0]

    # Mock model.generate_structured_output to return user_pref.md
    mock_response = StructuredResponse(
        content={"selected_files": ["user_pref.md"]},
        id="test-resp",
        created_at="2026-10-01T00:00:00",
        type="structured_response",
    )

    with patch.object(
        agent.model,
        "generate_structured_output",
        new=AsyncMock(return_value=mock_response),
    ):
        # In AgentScope, on_reasoning executes inside the on_reply handler chain
        async def dummy_reply_handler(**kwargs):
            if mw._retrieval_task:
                await mw._retrieval_task

            async def dummy_reasoning_handler(**r_kwargs):
                yield "dummy_reasoning_item"

            async for item in mw.on_reasoning(
                agent=agent,
                input_kwargs={},
                next_handler=dummy_reasoning_handler,
            ):
                yield item

        reply_gen = mw.on_reply(
            agent=agent,
            input_kwargs={"inputs": [Msg(name="user", role="user", content=[TextBlock(text="请分析一下茅台")])]},
            next_handler=dummy_reply_handler,
        )
        async for _ in reply_gen:
            pass

        # HintBlock should have been appended to agent context within a Msg
        context_msgs = agent.state.context
        assert len(context_msgs) >= 1
        hint_blocks = [
            block
            for msg in context_msgs
            for block in getattr(msg, "content", [])
            if hasattr(block, "hint")
        ]
        assert len(hint_blocks) == 1
        assert "user_pref.md" in hint_blocks[0].hint
        assert "用户最关注贵州茅台" in hint_blocks[0].hint

