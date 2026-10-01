"""
Unit tests for Dynamic Sub-Agent Runtime and Delegation Tools.
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from agentscope.message import Msg
from agentscope.tool import FunctionTool

from server.agent.subagents.templates import (
    BASE_TEMPLATES,
    build_subagent_system_prompt,
    get_template_config,
)
from server.agent.subagents.tool_resolver import ToolResolver
from server.agent.subagents.runner import DynamicSubAgentRunner
from server.agent.tools_subagent import create_delegate_task_tool


def test_base_templates_and_prompt_builder(tmp_path: Path):
    assert "research" in BASE_TEMPLATES
    assert "finance" in BASE_TEMPLATES
    assert "reviewer" in BASE_TEMPLATES
    assert "general" in BASE_TEMPLATES

    cfg_research = get_template_config("research")
    assert cfg_research.default_max_iters == 15
    assert cfg_research.default_timeout == 300

    cfg_finance = get_template_config("finance")
    assert cfg_finance.default_max_iters == 10
    assert cfg_finance.default_timeout == 180

    prompt = build_subagent_system_prompt(
        base_template="research",
        role="资深乳品行业调研员",
        instruction="搜集伊利与蒙牛的最新原奶采购成本数据",
        workspace_dir=str(tmp_path),
        wiki_dir="data/wiki",
    )
    assert "资深乳品行业调研员" in prompt
    assert "搜集伊利与蒙牛的最新原奶采购成本数据" in prompt
    assert str(tmp_path) in prompt
    assert "data/wiki" in prompt
    assert "汇报协议规范" in prompt

    finance_prompt = build_subagent_system_prompt(
        base_template="finance",
        role="CPA建模师",
        instruction="DCF测算",
        workspace_dir=str(tmp_path),
        wiki_dir="data/wiki",
    )
    assert "严禁心算" in finance_prompt
    assert "f-string" in finance_prompt


def test_tool_resolver_alias_expansion(tmp_path: Path):
    resolver = ToolResolver()

    # 1. 股票组
    stock_tools = resolver.resolve(["stock_market"], tmp_path)
    stock_names = {t.name for t in stock_tools}
    assert "stock_quote" in stock_names
    assert "stock_kline" in stock_names
    assert "market_index_overview" in stock_names

    # 2. 计算组
    calc_tools = resolver.resolve(["python_calc"], tmp_path)
    calc_names = {t.name for t in calc_tools}
    assert "Bash" in calc_names
    assert "calculate" in calc_names

    # 3. 数据库与维基组
    db_tools = resolver.resolve(["finance_db", "wiki_tools"], tmp_path)
    db_names = {t.name for t in db_tools}
    assert "finance_overview" in db_names
    assert "sqlite_query" in db_names
    assert "wiki_save_page" in db_names
    assert "wiki_read" in db_names

    # 4. 文件IO组
    io_tools = resolver.resolve(["file_io"], tmp_path)
    io_names = {t.name for t in io_tools}
    assert "Read" in io_names
    assert "Write" in io_names
    assert "Glob" in io_names


def test_tool_resolver_anti_recursion(tmp_path: Path):
    resolver = ToolResolver()
    # 模拟传入了非法越权与可能导致套娃递归的工具
    tools = resolver.resolve(
        ["delegate_task", "TaskCreate", "TaskUpdate", "AskUser", "python_calc"],
        tmp_path,
    )
    names = {t.name for t in tools}
    assert "delegate_task" not in names
    assert "TaskCreate" not in names
    assert "TaskUpdate" not in names
    assert "AskUser" not in names
    assert "Bash" in names


def test_create_delegate_task_tool_schema(tmp_path: Path):
    tool = create_delegate_task_tool(workspace_dir=tmp_path)
    assert isinstance(tool, FunctionTool)
    assert tool.name == "delegate_task"

    schema = tool.input_schema
    props = schema["properties"]
    assert "role" in props
    assert "instruction" in props
    assert "allowed_tools" in props
    assert "base_template" in props
    assert "timeout_seconds" in props
    assert "max_iters" in props
    assert "persist_to_wiki" in props
    assert schema["required"] == ["role", "instruction", "allowed_tools"]


@pytest.mark.asyncio
async def test_dynamic_subagent_runner_execution(tmp_path: Path):
    runner = DynamicSubAgentRunner(
        role="估值精算师",
        instruction="测算自由现金流DCF",
        allowed_tools=["python_calc"],
        base_template="finance",
        workspace_dir=tmp_path,
        timeout_seconds=50,
        max_iters=6,
    )
    assert runner.timeout_seconds == 50
    assert runner.max_iters == 6

    # Mock Agent.reply to return a standard compact report
    mock_msg = Msg(
        name="估值精算师",
        role="assistant",
        content=[
            {
                "type": "text",
                "text": (
                    "### 1. 核心事实结论\n"
                    "DCF合理市值约为 1820 亿元。\n"
                    "### 2. 关键财务指标\n"
                    "| WACC | 永续增长率 | 合理股价 |\n"
                    "| 7.5% | 2.0% | 28.50元 |\n"
                    "### 3. 底稿文件索引\n"
                    "- data/wiki/analyses/yili_dcf.md\n"
                    "### 4. 存疑与风险提示\n"
                    "原奶下行周期持续时间超预期。"
                ),
            }
        ],
    )

    with patch("server.agent.subagents.runner.Agent.reply", new=AsyncMock(return_value=mock_msg)):
        result = await runner.run()
        assert "DCF合理市值约为 1820 亿元" in result
        assert "data/wiki/analyses/yili_dcf.md" in result


@pytest.mark.asyncio
async def test_dynamic_subagent_runner_timeout_handling(tmp_path: Path):
    runner = DynamicSubAgentRunner(
        role="长时间调研员",
        instruction="深度抓取海量页面",
        allowed_tools=["file_io"],
        base_template="general",
        workspace_dir=tmp_path,
        timeout_seconds=1,  # 1秒超时
    )

    async def slow_reply(*args, **kwargs):
        await asyncio.sleep(2)
        return Msg(name="sub", role="assistant", content=[{"type": "text", "text": "done"}])

    with patch("server.agent.subagents.runner.Agent.reply", new=slow_reply):
        result = await runner.run()
        assert "执行超时告警" in result
        assert "子任务在执行 1 秒后超出时限" in result
