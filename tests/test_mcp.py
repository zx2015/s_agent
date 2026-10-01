"""Unit tests for MCP server config loading (server/tools/mcp.py).

These cover the *parsing and construction* of MCP clients — pure logic
that must not require a live MCP server. Whether the Tavily endpoint is
actually reachable is exercised separately by the end-to-end check.
"""
import pytest

from server.tools.mcp import McpServerSpec, build_mcp_clients, parse_mcp_servers


def test_parse_empty_string_yields_no_servers():
    assert parse_mcp_servers("") == []


def test_parse_single_http_server():
    raw = '[{"name": "tavily", "url": "http://127.0.0.1:18000/mcp", "is_stateful": true}]'
    specs = parse_mcp_servers(raw)
    assert len(specs) == 1
    assert specs[0] == McpServerSpec(
        name="tavily",
        url="http://127.0.0.1:18000/mcp",
        is_stateful=True,
    )


def test_parse_defaults_stateful_to_false():
    # Stateless is the safe default: AgentScope's Toolkit.__init__ forbids
    # stateful MCP clients that are not yet connected, so a stateful default
    # would make build_agent() crash unless a connect loop ran first.
    raw = '[{"name": "x", "url": "http://h/mcp"}]'
    specs = parse_mcp_servers(raw)
    assert specs[0].is_stateful is False


def test_parse_rejects_entry_without_url():
    raw = '[{"name": "broken"}]'
    with pytest.raises(ValueError, match="url"):
        parse_mcp_servers(raw)


def test_parse_rejects_entry_without_name():
    raw = '[{"url": "http://h/mcp"}]'
    with pytest.raises(ValueError, match="name"):
        parse_mcp_servers(raw)


def test_parse_rejects_malformed_json():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_mcp_servers("{not json")


def test_parse_rejects_non_list_payload():
    with pytest.raises(ValueError, match="array"):
        parse_mcp_servers('{"name": "x"}')


def test_parse_optional_fields():
    raw = (
        '[{"name": "t", "url": "http://h/mcp", "headers": {"Auth": "x"}, '
        '"timeout": 45.0, "enable_tools": ["tavily_search"]}]'
    )
    spec = parse_mcp_servers(raw)[0]
    assert spec.headers == {"Auth": "x"}
    assert spec.timeout == 45.0
    assert spec.enable_tools == ["tavily_search"]


def test_build_clients_constructs_one_per_spec():
    specs = parse_mcp_servers(
        '[{"name": "tavily", "url": "http://127.0.0.1:18000/mcp"}]'
    )
    clients = build_mcp_clients(specs)
    assert len(clients) == 1
    assert clients[0].name == "tavily"
    assert clients[0].mcp_config.url == "http://127.0.0.1:18000/mcp"


def test_build_clients_empty_specs():
    assert build_mcp_clients([]) == []


@pytest.mark.asyncio
async def test_main_agent_permissions_in_dangerous_mode(tmp_path):
    from agentscope.permission import PermissionBehavior
    from server.agent.core import build_agent
    from server import config

    agent = await build_agent(workspace_dir=tmp_path, hitl_mode="dangerous")

    # 1. 安全工作区内写文件与编辑文件：直接放行
    write_tool = await agent.toolkit.get_tool("Write")
    edit_tool = await agent.toolkit.get_tool("Edit")
    ws_file = str(tmp_path / "analysis_report.md")

    write_dec = await agent._engine.check_permission(write_tool, {"file_path": ws_file})
    assert write_dec.behavior == PermissionBehavior.ALLOW

    edit_dec = await agent._engine.check_permission(edit_tool, {"file_path": ws_file})
    assert edit_dec.behavior == PermissionBehavior.ALLOW

    # 2. 维基目录写文件：直接放行
    wiki_file = str(config.WIKI_DIR / "entities" / "sh600887.md")
    wiki_dec = await agent._engine.check_permission(write_tool, {"file_path": wiki_file})
    assert wiki_dec.behavior == PermissionBehavior.ALLOW

    # 3. 敏感/系统目录写文件：依然触发人工确认
    sys_dec = await agent._engine.check_permission(write_tool, {"file_path": "/etc/shadow"})
    assert sys_dec.behavior == PermissionBehavior.ASK

    # 4. delegate_task 与维基读查工具直接放行无需弹窗
    delegate_tool = await agent.toolkit.get_tool("delegate_task")
    assert delegate_tool is not None
    del_dec = await agent._engine.check_permission(delegate_tool, {})
    assert del_dec.behavior == PermissionBehavior.ALLOW

    query_tool = await agent.toolkit.get_tool("wiki_query")
    q_dec = await agent._engine.check_permission(query_tool, {})
    assert q_dec.behavior == PermissionBehavior.ALLOW


@pytest.mark.asyncio
async def test_subagent_sandbox_python_and_bash_permissions(tmp_path):
    from agentscope.permission import PermissionBehavior, PermissionMode, PermissionRule
    from server.agent.subagents.tool_resolver import ToolResolver
    import sys

    # 验证子智能体工具沙箱构建与权限
    resolver = ToolResolver()
    tools = resolver.resolve(["python_calc", "file_io"], tmp_path)
    tool_map = {t.name: t for t in tools}

    assert "Bash" in tool_map
    assert "Write" in tool_map
    assert "delegate_task" not in tool_map  # 防套娃递归拦截

    # 组装沙箱引擎权限规则测试
    from agentscope.agent import Agent
    from agentscope.tool import Toolkit
    tk = Toolkit()
    for t in tools:
        await tk.add_tool(t)

    from agentscope.credential import OpenAICredential
    from agentscope.model import OpenAIChatModel
    from agentscope.formatter import OpenAIChatFormatter
    cred = OpenAICredential(id="test", name="v-flash", api_key="dummy", base_url="http://127.0.0.1:4000/v1")
    model = OpenAIChatModel(credential=cred, model="v-flash", formatter=OpenAIChatFormatter())
    subagent = Agent(name="test_sub", system_prompt="test", model=model, toolkit=tk)

    # 注入与 runner 相同的安全沙箱规则
    subagent._engine.context.mode = PermissionMode.ACCEPT_EDITS
    for py_cmd in ("python:*", "python3:*", f"{sys.executable}:*"):
        subagent._engine.add_rule(
            PermissionRule(
                tool_name="Bash",
                rule_content=py_cmd,
                behavior=PermissionBehavior.ALLOW,
                source="subagentSandbox",
            )
        )

    bash_tool = await subagent.toolkit.get_tool("Bash")
    # Python 计算放行
    py_dec = await subagent._engine.check_permission(bash_tool, {"command": 'python3 -c "print(1+1)"'})
    assert py_dec.behavior == PermissionBehavior.ALLOW

    # 危险系统命令依然需要人工确认
    danger_dec = await subagent._engine.check_permission(bash_tool, {"command": "rm -rf /"})
    assert danger_dec.behavior == PermissionBehavior.ASK

