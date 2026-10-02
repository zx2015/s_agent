"""
动态子智能体工具沙箱解析器 (Tool Sandbox Resolver).

职责:
1. 维护工具组别名注册表 TOOL_GROUP_REGISTRY；
2. 将主 Agent 授权的别名（如 'web_search', 'stock_market'）解析为具体的工具实例；
3. 防递归安全检查 (Anti-Recursion Guard)：强制剔除 delegate_task，杜绝子智能体套娃；
4. 权限沙箱隔离 (Permission Sandboxing)：按最小权限原则为子智能体工具赋予安全规则。
"""
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from agentscope.tool import (
    Bash,
    Edit,
    FunctionTool,
    Glob,
    Grep,
    Read,
    ToolBase,
    Write,
)
from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionBehavior,
    PermissionDecision,
    PermissionMode,
    PermissionRule,
)

from server import config
from server.tools.calculator import calculate
from server.agent.tools_glob import WorkspaceGlob
from server.agent.tools_wiki import create_wiki_tools, wiki_query, wiki_read, wiki_save_page
from server.tools.stock import (
    finance_overview,
    finance_record_metric,
    finance_watchlist,
    market_index_overview,
    sqlite_describe_table,
    sqlite_execute,
    sqlite_query,
    sqlite_show_tables,
    stock_batch_quotes,
    stock_handicap,
    stock_kline,
    stock_minute,
    stock_quote,
    stock_search,
)

logger = logging.getLogger(__name__)

TOOL_GROUP_REGISTRY: Dict[str, List[str]] = {
    "web_search": [
        "mcp__tavily__tavily-search",
        "mcp__tavily__tavily-extract",
    ],
    "stock_market": [
        "stock_search",
        "stock_quote",
        "stock_batch_quotes",
        "stock_kline",
        "stock_minute",
        "stock_handicap",
        "market_index_overview",
    ],
    "python_calc": [
        "Bash",
        "calculate",
    ],
    "finance_db": [
        "finance_overview",
        "finance_watchlist",
        "finance_record_metric",
        "sqlite_show_tables",
        "sqlite_describe_table",
        "sqlite_query",
        "sqlite_execute",
    ],
    "wiki_tools": [
        "wiki_query",
        "wiki_read",
        "wiki_save_page",
    ],
    "file_io": [
        "Read",
        "Write",
        "Edit",
        "Glob",
    ],
}

# 明确禁止子智能体使用的危险/元工具
DISALLOWED_SUBAGENT_TOOLS: Set[str] = {
    "delegate_task",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
    "AskUser",
}


def expand_allowed_tools(allowed_tools: List[str]) -> Set[str]:
    """将包含别名组和具体工具名的列表展开为扁平的工具名集合，并剥离非法工具"""
    expanded: Set[str] = set()
    for item in allowed_tools:
        name = item.strip()
        if name in TOOL_GROUP_REGISTRY:
            expanded.update(TOOL_GROUP_REGISTRY[name])
        else:
            expanded.add(name)

    # 强制防递归与元管理隔离
    for forbidden in DISALLOWED_SUBAGENT_TOOLS:
        expanded.discard(forbidden)

    return expanded


class ToolResolver:
    """工具解析与沙箱组装器"""

    def __init__(self, mcp_tools: Optional[List[ToolBase]] = None):
        self.mcp_tools: List[ToolBase] = mcp_tools or []
        self._mcp_tool_map: Dict[str, ToolBase] = {}
        # 将已有的 MCP 工具根据工具名做索引
        for t in self.mcp_tools:
            t_name = getattr(t, "name", None)
            if t_name:
                self._mcp_tool_map[t_name] = t

    def resolve(
        self,
        allowed_tools: List[str],
        workspace_dir: Path,
    ) -> List[ToolBase]:
        """
        根据白名单与工作区，构建子智能体的独立 Tool 实例列表。
        """
        tool_names = expand_allowed_tools(allowed_tools)
        resolved_tools: List[ToolBase] = []
        resolved_ws = str(workspace_dir.resolve())
        wiki_dir = (workspace_dir / "wiki").resolve()
        wiki_dir.mkdir(parents=True, exist_ok=True)
        wiki_ws = str(wiki_dir)
        workspace_wiki_tools = create_wiki_tools(wiki_dir)

        # 1. 解析基础文件与命令工具
        if "Read" in tool_names:
            resolved_tools.append(Read())
        if "Write" in tool_names:
            resolved_tools.append(Write())
        if "Edit" in tool_names:
            resolved_tools.append(Edit())
        if "Glob" in tool_names:
            resolved_tools.append(WorkspaceGlob(workspace_dir=workspace_dir))
        if "Grep" in tool_names:
            resolved_tools.append(Grep())
        if "Bash" in tool_names:
            resolved_tools.append(Bash())

        # 2. 计算器
        if "calculate" in tool_names:
            resolved_tools.append(
                FunctionTool(
                    calculate,
                    permission=PermissionDecision(
                        behavior=PermissionBehavior.ALLOW,
                        message="子智能体高精度数学计算",
                    ),
                )
            )

        # 3. 维基工具
        if "wiki_query" in tool_names:
            resolved_tools.append(
                FunctionTool(
                    workspace_wiki_tools["wiki_query"],
                    permission=PermissionDecision(
                        behavior=PermissionBehavior.ALLOW,
                        message="检索当前工作区投研维基",
                    ),
                )
            )
        if "wiki_read" in tool_names:
            resolved_tools.append(
                FunctionTool(
                    workspace_wiki_tools["wiki_read"],
                    permission=PermissionDecision(
                        behavior=PermissionBehavior.ALLOW,
                        message="读取当前工作区投研维基页面",
                    ),
                )
            )
        if "wiki_save_page" in tool_names:
            resolved_tools.append(
                FunctionTool(
                    workspace_wiki_tools["wiki_save_page"],
                    permission=PermissionDecision(
                        behavior=PermissionBehavior.ALLOW,
                        message="编译成果沉淀入当前工作区投研维基",
                    ),
                )
            )

        # 4. 股票与 SQLite 工具映射表
        stock_tool_map: Dict[str, tuple[Callable, str]] = {
            "stock_search": (stock_search, "搜索 A 股/港股标的代码"),
            "stock_quote": (stock_quote, "查询实时分时估值行情"),
            "stock_batch_quotes": (stock_batch_quotes, "批量横向对比标的行情"),
            "stock_kline": (stock_kline, "查询历史日K/周K复权走势"),
            "stock_minute": (stock_minute, "查询日内分时量价走势"),
            "stock_handicap": (stock_handicap, "查询五档盘口与买卖大单"),
            "market_index_overview": (market_index_overview, "查询宏观核心大盘指数"),
            "finance_overview": (finance_overview, "查询已沉淀标的财务全览"),
            "finance_watchlist": (finance_watchlist, "查询并维护自选池"),
            "finance_record_metric": (finance_record_metric, "将财务测算事实写入 SQLite"),
            "sqlite_show_tables": (sqlite_show_tables, "查看本地数据库表结构"),
            "sqlite_describe_table": (sqlite_describe_table, "查看表字段详情"),
            "sqlite_query": (sqlite_query, "执行只读 SELECT 查询"),
            "sqlite_execute": (sqlite_execute, "执行安全 DDL/DML 语句"),
        }

        for name, (fn, desc) in stock_tool_map.items():
            if name in tool_names:
                resolved_tools.append(
                    FunctionTool(
                        fn,
                        permission=PermissionDecision(
                            behavior=PermissionBehavior.ALLOW,
                            message=f"子智能体量化/数据库工具: {desc}",
                        ),
                    )
                )

        # 5. MCP 工具匹配
        for name in tool_names:
            if name.startswith("mcp__") and name in self._mcp_tool_map:
                resolved_tools.append(self._mcp_tool_map[name])

        return resolved_tools
