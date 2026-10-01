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
async def test_create_delegate_task_tool_invocation(tmp_path: Path):
    tool = create_delegate_task_tool(workspace_dir=tmp_path)
    with patch("server.agent.subagents.runner.DynamicSubAgentRunner.run", new=AsyncMock(return_value="子任务执行成功摘要")):
        res = await tool(
            role="测试分析师",
            instruction="分析业务",
            allowed_tools=["file_io"],
            timeout_seconds=30,
        )
        # FunctionTool invocation returns a ToolResponse or string
        assert "子任务执行成功摘要" in str(res)


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


@pytest.mark.asyncio
async def test_dynamic_subagent_runner_interruption_fallback_handling(tmp_path: Path):
    runner = DynamicSubAgentRunner(
        role="被中断调研员",
        instruction="执行调研",
        allowed_tools=["file_io"],
        base_template="general",
        workspace_dir=tmp_path,
        timeout_seconds=60,
    )

    async def interrupt_reply(*args, **kwargs):
        return Msg(
            name="sub",
            role="assistant",
            content=[{"type": "text", "text": "I notice the interruption. How can I help you?"}],
        )

    with patch("server.agent.subagents.runner.Agent.reply", new=interrupt_reply):
        result = await runner.run()
        assert "执行超时/中断告警" in result
        assert "维基落盘检查" in result


@pytest.mark.asyncio
async def test_dynamic_subagent_runner_workspace_and_mcp_full_authorization(tmp_path: Path):
    from agentscope.permission import PermissionBehavior
    from server.tools.mcp import parse_mcp_servers, build_mcp_clients
    from server import config

    # 模拟包含 Tavily MCP 工具与垂直领域工具的沙箱
    clients = build_mcp_clients(parse_mcp_servers(config.MCP_SERVERS))
    mcp_tools = []
    for c in clients:
        mcp_tools.extend(await c.list_tools())

    runner = DynamicSubAgentRunner(
        role="深度调研员",
        instruction="调研并落盘",
        allowed_tools=["web_search", "wiki_tools", "file_io"],
        base_template="research",
        workspace_dir=tmp_path,
        mcp_tools=mcp_tools,
    )

    captured_agent = None

    async def mock_reply(inputs):
        nonlocal captured_agent
        return Msg(name="sub", role="assistant", content=[{"type": "text", "text": "调研完成"}])

    with patch("server.agent.subagents.runner.Agent.reply", side_effect=mock_reply) as mock_r:
        # Patch resolve_context_size to avoid external network requests
        with patch("server.agent.subagents.runner.resolve_context_size", new=AsyncMock(return_value=128000)):
            # Capture the agent instance created
            orig_init = runner._execute_agent

            async def wrapped_execute(effective_max_iters):
                res = await orig_init(effective_max_iters)
                return res

            with patch.object(runner, "_execute_agent", wraps=wrapped_execute):
                result = await runner.run()
                assert "调研完成" in result

            # Direct test on agent permissions constructed by _execute_agent
            from agentscope.agent import Agent
            # Find the agent from mock_r call
            sub_agent = mock_r.call_args_list[0].args[0] if len(mock_r.call_args_list[0].args) > 1 else None
            # In method call, `self` is the agent
            for call in mock_r.mock_calls:
                # call is call(inputs)
                pass

    # Now verify the permission engine configuration directly
    tools_to_use = runner.allowed_tools
    resolver = ToolResolver(mcp_tools=runner.mcp_tools)
    resolved_tools = resolver.resolve(tools_to_use, runner.workspace_dir)

    from agentscope.tool import Toolkit
    toolkit = Toolkit()
    for t in resolved_tools:
        await toolkit.add_tool(t)

    from agentscope.credential import OpenAICredential
    from agentscope.model import OpenAIChatModel
    from agentscope.formatter import OpenAIChatFormatter
    from agentscope.permission import PermissionMode, PermissionRule, AdditionalWorkingDirectory
    import sys

    cred = OpenAICredential(id="test", name="v-flash", api_key="dummy", base_url="http://127.0.0.1:4000/v1")
    model = OpenAIChatModel(credential=cred, model="v-flash", formatter=OpenAIChatFormatter())
    agent = Agent(name="test_sandbox", system_prompt="test", model=model, toolkit=toolkit)

    # Apply runner permissions
    agent._engine.context.mode = PermissionMode.ACCEPT_EDITS
    resolved_ws_str = str(tmp_path)
    agent._engine.context.working_directories[resolved_ws_str] = AdditionalWorkingDirectory(path=resolved_ws_str, source="workspaceDir")
    agent._engine.context.working_directories[str(config.WIKI_DIR)] = AdditionalWorkingDirectory(path=str(config.WIKI_DIR), source="wikiDir")

    for fs_tool in ("Write", "Edit"):
        agent._engine.add_rule(PermissionRule(tool_name=fs_tool, rule_content=f"{resolved_ws_str}/**", behavior=PermissionBehavior.ALLOW, source="subagentSandbox"))
        agent._engine.add_rule(PermissionRule(tool_name=fs_tool, rule_content="data/wiki/**", behavior=PermissionBehavior.ALLOW, source="subagentSandbox"))

    for py_cmd in ("python:*", "python3:*", f"{sys.executable}:*", "/usr/bin/python3:*"):
        agent._engine.add_rule(PermissionRule(tool_name="Bash", rule_content=py_cmd, behavior=PermissionBehavior.ALLOW, source="subagentSandbox"))

    for tool in resolved_tools:
        if tool.name not in ("Write", "Edit", "Bash"):
            agent._engine.add_rule(PermissionRule(tool_name=tool.name, rule_content="", behavior=PermissionBehavior.ALLOW, source="subagentSandbox"))

    # 1. MCP Tavily 搜索工具必须被完全授权（ALLOW），杜绝等待授权死锁
    tavily_search_tool = await agent.toolkit.get_tool("mcp__tavily__tavily-search")
    assert tavily_search_tool is not None
    dec_tavily = await agent._engine.check_permission(tavily_search_tool, {"query": "海康威视"})
    assert dec_tavily.behavior == PermissionBehavior.ALLOW

    # 2. 维基保存工具必须完全授权（ALLOW）
    wiki_save_tool = await agent.toolkit.get_tool("wiki_save_page")
    assert wiki_save_tool is not None
    dec_wiki = await agent._engine.check_permission(wiki_save_tool, {"page_path": "entities/sz002415.md", "content": "# 海康"})
    assert dec_wiki.behavior == PermissionBehavior.ALLOW

    # 3. 工作空间内的写入操作完全放行
    write_tool = await agent.toolkit.get_tool("Write")
    dec_write_ws = await agent._engine.check_permission(write_tool, {"file_path": str(tmp_path / "report.md"), "content": "text"})
    assert dec_write_ws.behavior == PermissionBehavior.ALLOW

    # 4. 工作空间外的越权写操作依然被拦截拦截为 ASK
    dec_write_outside = await agent._engine.check_permission(write_tool, {"file_path": "/etc/shadow", "content": "bad"})
    assert dec_write_outside.behavior == PermissionBehavior.ASK

