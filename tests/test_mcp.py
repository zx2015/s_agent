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
async def test_tavily_mcp_tools_allowed_by_default_in_dangerous_mode(tmp_path):
    from agentscope.permission import PermissionBehavior
    from server.agent.core import build_agent

    agent = await build_agent(workspace_dir=tmp_path, hitl_mode="dangerous")
    # All Tavily MCP operations are external read-only web requests and safe
    for tool_name in (
        "mcp__tavily__tavily-search",
        "mcp__tavily__tavily-extract",
        "mcp__tavily__tavily-crawl",
        "mcp__tavily__tavily-map",
    ):
        tool = await agent.toolkit.get_tool(tool_name)
        if tool is not None:
            decision = await agent._engine.check_permission(tool, {})
            assert decision.behavior == PermissionBehavior.ALLOW

    # High-risk mutating commands in Bash still trigger confirmation
    bash_tool = await agent.toolkit.get_tool("Bash")
    bash_decision = await agent._engine.check_permission(
        bash_tool, {"command": "rm -rf foo"}
    )
    assert bash_decision.behavior == PermissionBehavior.ASK


@pytest.mark.asyncio
async def test_tavily_mcp_tools_ask_confirmation_in_always_mode(tmp_path):
    from agentscope.permission import PermissionBehavior
    from server.agent.core import build_agent

    agent = await build_agent(workspace_dir=tmp_path, hitl_mode="always")
    tool = await agent.toolkit.get_tool("mcp__tavily__tavily-search")
    if tool is not None:
        decision = await agent._engine.check_permission(tool, {})
        assert decision.behavior == PermissionBehavior.ASK
