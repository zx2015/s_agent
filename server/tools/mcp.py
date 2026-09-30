"""
MCP (Model Context Protocol) tool registration.

Lets the agent pick up tools exposed by external MCP servers (currently:
Tavily search, extract, crawl, map) without bundling the SDK in the
backend. The list of servers is declared in `server/config.py` and parsed
here into :class:`agentscope.mcp.MCPClient` instances, which are then
handed to the toolkit via ``Toolkit(mcps=[...])`` (AgentScope 2.0).

The transport is always Streamable HTTP for now: the local Tavily
container listens on ``/mcp`` and ``HttpMCPConfig`` is the right
shape. Stdio is supported by ``StdioMCPConfig``; wiring it in is a
follow-up once we actually need a stdio-only MCP server.

Stateful vs stateless
---------------------

``MCPClient.is_stateful=True`` (the default) requires the client to be
connected before it goes into a Toolkit -- ``Toolkit.__init__`` raises
``ValueError`` otherwise. The cleanest place to ``await client.connect()``
is once at backend startup (or on first use) and ``await client.close()``
on shutdown; that requires an async lifespan hook we don't have yet.

We sidestep that by initialising clients with ``is_stateful=False``: each
``list_tools()`` / tool invocation opens a fresh HTTP session internally
(no caller-visible ``connect()`` needed). This matches how the local
Tavily container is actually deployed (every request gets a brand-new
``mcp-session-id``) and keeps startup sync-only, which is the smallest
change that gets MCP working today.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from agentscope.mcp import HttpMCPConfig, MCPClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpServerSpec:
    """One row of the ``S_AGENT_MCP_SERVERS`` JSON config."""

    name: str
    url: str
    is_stateful: bool = False
    headers: dict[str, str] | None = None
    timeout: float | None = None
    enable_tools: list[str] | None = None
    disable_tools: list[str] | None = None


def parse_mcp_servers(raw: str) -> list[McpServerSpec]:
    """Parse the JSON array stored in the ``S_AGENT_MCP_SERVERS`` env var.

    Args:
        raw (str):
            A JSON array of objects (see :class:`McpServerSpec`). An empty
            string means "no servers" and is not an error.

    Returns:
        list[McpServerSpec]:
            One entry per server, in declaration order.

    Raises:
        ValueError:
            When the payload is malformed JSON, isn't an array, or any
            entry is missing required keys.
    """
    if not raw or not raw.strip():
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"S_AGENT_MCP_SERVERS is not valid JSON: {exc.msg}"
        ) from exc

    if not isinstance(payload, list):
        raise ValueError(
            f"S_AGENT_MCP_SERVERS must be a JSON array, got {type(payload).__name__}"
        )

    specs: list[McpServerSpec] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Each MCP server entry must be an object, got {type(entry).__name__}"
            )
        name = entry.get("name")
        url = entry.get("url")
        if not name:
            raise ValueError("MCP server entry missing 'name'")
        if not url:
            raise ValueError(f"MCP server {name!r} missing 'url'")

        specs.append(
            McpServerSpec(
                name=name,
                url=url,
                is_stateful=bool(entry.get("is_stateful", False)),
                headers=entry.get("headers"),
                timeout=entry.get("timeout"),
                enable_tools=entry.get("enable_tools"),
                disable_tools=entry.get("disable_tools"),
            )
        )
    return specs


def build_mcp_clients(
    specs: list[McpServerSpec],
) -> list[MCPClient]:
    """Construct the AgentScope MCP clients used to populate the toolkit.

    Args:
        specs (list[McpServerSpec]):
            The output of :func:`parse_mcp_servers`.

    Returns:
        list[MCPClient]:
            One Client per spec, in declaration order. Empty list when
            no servers are configured.
    """
    clients: list[MCPClient] = []
    for spec in specs:
        clients.append(
            MCPClient(
                name=spec.name,
                is_stateful=spec.is_stateful,
                mcp_config=HttpMCPConfig(
                    url=spec.url,
                    headers=spec.headers,
                    timeout=spec.timeout,
                ),
                enable_tools=spec.enable_tools,
                disable_tools=spec.disable_tools,
            )
        )
    logger.info(
        "Configured %d MCP server(s): %s",
        len(clients),
        [spec.name for spec in specs],
    )
    return clients