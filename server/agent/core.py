"""
Builds one AgentScope `Agent` per task.

Mirrors the exact recipe pinned in `CLAUDE.md` §"模型接入" (verified
end-to-end against the local LiteLLM `v-flash` proxy on 2026-09-28) plus
the toolkit for one task's workspace. A new `Agent` — and therefore a
fresh `AgentState` / conversation history — is created per task rather
than shared, so two tasks can never leak context into each other.

The 12 built-in tools called for in `TODO.md` ship with AgentScope 2.0.8
itself (`agentscope.tool.{Bash,Read,Write,Edit,Glob,Grep,TaskCreate,
TaskGet,TaskList,TaskUpdate,AskUser}`) — nothing to reimplement there.
Only the calculator is project-specific.
"""
import logging
import os
import platform
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from agentscope.agent import Agent, ContextConfig
from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import OpenAIChatModel
from agentscope.middleware import AgenticMemoryMiddleware
from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionBehavior,
    PermissionDecision,
    PermissionMode,
    PermissionRule,
)
from agentscope.state import AgentState
from agentscope.workspace import LocalWorkspace
from agentscope.tool import (
    AskUser,
    Bash,
    Edit,
    Glob,
    Grep,
    LocalBackend,
    Read,
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
    Toolkit,
    Write,
    FunctionTool,
)

from server import config
from server.agent.calibrator import resolve_context_size
from server.tools.calculator import calculate
from server.tools.mcp import build_mcp_clients, parse_mcp_servers
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

# MCP tools that are external read-only operations and safe to run by default
# without requiring human-in-the-loop confirmation in "dangerous" mode.
SAFE_MCP_TOOL_PREFIXES: tuple[str, ...] = (
    "mcp__tavily__",
)
SAFE_MCP_TOOLS: set[str] = {
    "mcp__tavily__tavily-search",
    "mcp__tavily__tavily-extract",
    "mcp__tavily__tavily-crawl",
    "mcp__tavily__tavily-map",
}

# This is only layer 1 of what the model actually receives as its system
# prompt — AgentScope appends toolkit skill/offloader instructions on top
# of this string every reply, and separately injects a runtime-state
# `<system-reminder>` (current time, pending tasks, ...) as its own
# context message rather than into this string at all (so prompt caching
# on this fixed text keeps working). See CLAUDE.md's "System Prompt 的实际
# 组装方式" section for the full three-layer breakdown before changing
# this or debugging "the model doesn't know X".
SYSTEM_PROMPT_TEMPLATE = (
    "你是 s_agent 工作台里的通用任务助手。你的工作区目录是：\n"
    "{workspace_dir}\n"
    "所有文件读写、Bash 命令都必须在这个目录（或其子目录）下进行，"
    "文件工具要求绝对路径时，请以该目录为前缀拼接。\n\n"
    "【工作区产物与文件交付】\n"
    "- 当用户要求进行调研、投资分析、方案设计、编码开发或生成报告等任务时，"
    "除了在对话气泡中输出总结外，**必须**将完整的研究报告（.md）、代码、网页（.html）"
    "等交付文件写入工作区根目录（如 {workspace_dir}/<报告或产物名称>.md）。\n"
    "- 写入工作区的文件会自动出现在用户界面右侧的「产物/预览」和「全部文件」面板中，"
    "供用户实时查看、在线预览和打包下载。\n"
    "- 只有跨会话长期复用的全局偏好或事实档案才写入记忆库（data/memory），"
    "不可将本属于当前任务的交付报告仅写入记忆库而漏掉工作区。\n\n"
    "【任务规划与待办状态（Todos）】\n"
    "- 面对包含多步骤的复杂任务（如：1. 搜集数据 2. 计算分析 3. 沉淀记忆 4. 撰写分析交付报告），"
    "应首先调用 TaskCreate 工具创建清晰的步骤清单；\n"
    "- 在每个关键步骤开始或完成时，调用 TaskUpdate 更新任务状态（in_progress / completed），"
    "系统会自动在界面右侧「待办」面板中向用户动态展现执行进度。\n\n"
    "【计算与排版准则】\n"
    "- 任何超过两个数字的算术运算，优先调用 calculate 工具，禁止自己心算得出数字结果；"
    "若调用 Bash 运行 Python 处理复杂数据或批量指标计算，在包含百分号「%」的文本中务必使用 f-string（如 f'同比+229%, 净利润={{val:.2f}}'）而非百分号格式化，"
    "避免因未转义「%」触发语法错误。\n"
    "- 除工具调用外，你输出的所有文本都会在工作台的对话气泡中以 GitHub 风格 Markdown（GFM）渲染展示，"
    "请规范排版——代码块标注语言、用表格呈现对比数据、用列表整理要点。\n\n"
    "【金融投研与结构化数据跨会话持久化（双轨制架构）】\n"
    "- 市场量价与行情查询：\n"
    "  1. 标的识别：若代码不明确，调用 stock_search 搜索标准代码与市场（支持拼音、代码与中文名）；\n"
    "  2. 大盘环境：调用 market_index_overview 获取核心宏观指数环境；\n"
    "  3. 现价与估值：调用 stock_quote 获取实时价格、估值（PE/PB）与市值。系统已内置 SQLite WAL 透明缓存，盘中自动按 3 分钟 TTL 刷新，盘后与周末全天直读，无需担心重复消耗外网；\n"
    "  4. 历史形态与量价：调用 stock_kline 获取历史 K 线（内置增量存储）、stock_minute 获取分时明细，stock_handicap 获取主力盘口比例；\n"
    "  5. 深度全网资讯：结合 tavily 搜索工具（如 mcp__tavily__tavily-search）检索最新公告、研报与行业周期。\n"
    "- 结构化数据持久化与跨会话复用（预定义核心表 + Agent 自主动态建表）：\n"
    "  1. 查看数据库沉淀全览：调用 finance_overview 查看本地已保存的所有股票现价与估值对比；\n"
    "  2. 管理用户自选关注池：调用 finance_watchlist（list/add/update/remove）跨会话维护用户买卖心理价与核心逻辑；\n"
    "  3. 记录关键财务事实底稿：调用 finance_record_metric 记录经营现金流、费用率、分红等高价值财务测算；\n"
    "  4. 复杂只读 SQL 查询：调用 sqlite_query 针对本地数据库执行多表关联（JOIN）或统计筛选（如查找 PE < 20 且市值 > 500 亿的股票）；\n"
    "  5. Agent 自主动态建表（无限扩展能力）：当未来遇到未预先定义的全新结构化数据（如上游生鲜乳周度价格走势、高管增减持明细、自定义量化信号）且后续需要跨会话比对时，"
    "可自主调用 sqlite_execute 执行 CREATE TABLE IF NOT EXISTS custom_<表名> 并插入数据！预定义系统核心表受安全保护，严禁执行 DROP TABLE。\n"
    "- 分析必须客观求实，严禁编造虚假数据。所有系统性的长篇投研成果须通过 Write/Edit 工具在工作区根目录下生成规范的 Markdown 交付物（如《XXX投资价值分析.md》）。\n\n"
    "【权限与运行时提示】\n"
    "- 系统在安全模式下默认放行所有安全的只读工具、在当前任务工作区或记忆库内写文件（Write/Edit）以及常规 Python 命令运行（Bash: python3/python），无需用户反复确认；"
    "但当涉及工作区外的文件操作或高危系统命令（如破坏性删除、系统提权等）时，会触发人工确认（HITL）。\n"
    "- 如果一次工具调用被拒绝，代表用户主动拒绝了该操作，请调整思路或更换方案，说明被拒绝操作的影响，不要在没有新信息的情况下直接重试同一个命令。\n"
    "- 对话消息与工具结果中出现的 <system-reminder> 标签，是运行框架自动注入的运行时提示"
    "（例如当前时间、待办任务状态等），并非用户本人发出的内容。\n"
    "- 如果配置了工具中间件（middleware），它可能会拦截或调整工具调用，请将中间件返回的结果当作对操作意图的反馈来处理。\n\n"
    "{environment_block}"
)

CHINESE_MEMORY_INSTRUCTIONS = """\
你有位于 `{memory_dir}` 的跨任务持久化文件记忆库。该目录已存在且所有任务共享，请通过 `Write`、`Edit`、`Read` 工具直接读写该目录。

记忆库用于跨任务沉淀用户画像、偏好、协作准则、量化投资与业务事实，使后续的新任务或新会话能够持续复用。

## 记忆分类 (Types)
- **user**：用户的角色、投资偏好、风险承受能力、硬性要求等持久特征；
- **feedback**：用户给出的纠错、交互准则、“不要做X / 必须做Y”的指导；
- **project**：长期业务上下文、关注的股票标的、特定项目背景；
- **reference**：外部数据源、计算公式（如夏普比率、最大回撤计算规范）等指针。

## 记忆保存两步法
1. **第一步**：创建或更新具体卡片文件（如 `{memory_dir}/user_risk_pref.md`），文件头部必须包含 YAML frontmatter：
---
name: <唯一标识>
description: <检索触发条件，一句话明确说明在何种情境/提问下未来必须召回此记忆>
type: user | feedback | project | reference
---
正文内容...

2. **第二步**：在 `{memory_dir}/MEMORY.md` 索引文件中追加或更新一行索引（每行不超过 150 字符）：
- [name](filename.md) — 简要描述与触发情境

## 检索与查阅
- 在每轮回复时，系统会自动评估相关记忆并以 Hint 形式注入上下文；
- 你也可以在需要时使用 `Read` 或 `Grep` 工具主动查阅 `{memory_dir}` 下的文件。
"""


def _detect_shell() -> str:
    """Resolve the shell AgentScope's `Bash` tool actually invokes commands
    with.

    Despite the tool's name, it never runs `bash` directly — it wraps every
    command in `["/bin/sh", "-c", command]` (see
    `agentscope/tool/_builtin/_bash.py`). On many Linux distros `/bin/sh` is
    a symlink to `dash`, not `bash`, so resolving the actual symlink target
    is the only way to report this honestly instead of assuming.
    """
    sh_path = Path("/bin/sh")
    if sh_path.is_symlink():
        return Path(os.readlink(sh_path)).name
    return sh_path.name if sh_path.exists() else "sh"


def _detect_platform() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    return system.lower()


def _build_environment_block(workspace_dir: Path) -> str:
    """Describe the actual host/task environment, detected at agent-build
    time rather than hardcoded, so it stays correct if the backend ever
    runs somewhere other than this one Linux box.
    """
    is_git_repo = (workspace_dir / ".git").is_dir()
    lines = [
        "<env>",
        f"Working directory: {workspace_dir}",
        f"Is directory a git repo: {'Yes' if is_git_repo else 'No'}",
        f"Platform: {_detect_platform()}",
        f"Shell: {_detect_shell()}",
        f"OS Version: {platform.system()} {platform.release()}",
        f"Model: {config.MODEL_NAME}",
        "</env>",
    ]
    return "\n".join(lines)


async def build_agent(
    workspace_dir: Path,
    state: AgentState | None = None,
    memory_dir: Path | str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    hitl_mode: str | None = None,
) -> Agent:
    """Assemble the toolkit and the model-backed agent for one task.

    Args:
        workspace_dir: The task's private working directory. All file
            tools operate relative to this path via a dedicated
            `LocalBackend`, so tasks cannot see or touch each other's
            files.
        state: A previously saved `AgentState` to resume from (see
            `server/service/memory_store.py`). When `None`, the agent
            starts with empty conversation history, same as before
            persistence existed.
        memory_dir: Optional custom directory for long-term memory.
            Defaults to `config.LONGTERM_MEMORY_DIR`.
        model_name: Optional model override. Defaults to `config.MODEL_NAME`.
        base_url: Optional API endpoint override. Defaults to `config.LITELLM_BASE_URL`.
        hitl_mode: Optional human-in-the-loop mode ('always', 'dangerous', 'never').
            Defaults to 'dangerous'.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = str(workspace_dir.resolve())
    backend = LocalBackend()

    # MCP servers are supplementary: a typo in the config, or a container
    # that is down, must not cost the user their whole agent. Degrade to
    # "no MCP tools" with a loud log line instead of failing the turn —
    # the built-in tools below still work either way.
    try:
        mcp_clients = build_mcp_clients(parse_mcp_servers(config.MCP_SERVERS))
    except ValueError as exc:
        logger.error(
            "Ignoring MCP configuration (S_AGENT_MCP_SERVERS): %s", exc
        )
        mcp_clients = []

    toolkit = Toolkit(mcps=mcp_clients)
    await toolkit.add_tool(Bash(cwd=resolved_dir, backend=backend))
    await toolkit.add_tool(Read(backend=backend))
    await toolkit.add_tool(Write(backend=backend))
    await toolkit.add_tool(Edit(backend=backend))
    await toolkit.add_tool(Glob(backend=backend))
    await toolkit.add_tool(Grep(backend=backend))
    await toolkit.add_tool(AskUser())
    await toolkit.add_tool(TaskCreate())
    await toolkit.add_tool(TaskGet())
    await toolkit.add_tool(TaskList())
    await toolkit.add_tool(TaskUpdate())
    # `FunctionTool` asks for confirmation on every call unless a permission
    # is given explicitly (see agentscope/tool/_adapters.py) — safe default
    # for arbitrary custom tools, but wrong for calculate: it is a pure,
    # side-effect-free AST evaluator with no filesystem/network access, so
    # forcing a HITL prompt for "what's 2+2" would just be noise.
    await toolkit.add_tool(
        FunctionTool(
            calculate,
            permission=PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message="Pure arithmetic evaluation, no side effects",
            ),
        ),
    )

    # Tencent Stock Native Toolkit & Financial Persistence Bridge
    stock_tool_specs = [
        (stock_search, "Search stock symbol and company name"),
        (stock_quote, "Real-time stock quote and valuation with transparent SQLite caching"),
        (stock_batch_quotes, "Batch stock quotes comparison"),
        (stock_kline, "Historical K-line series query with local incremental storage"),
        (stock_minute, "Intraday minute price and volume"),
        (stock_handicap, "Handicap big/small order distribution"),
        (market_index_overview, "Market benchmark index overview"),
        (finance_overview, "Cross-session overview of all persisted stocks in the local SQLite database"),
        (finance_watchlist, "Manage persistent cross-session stock watchlist and buy/sell targets"),
        (finance_record_metric, "Record deep financial facts and calculations into SQLite"),
        (sqlite_show_tables, "List all tables in local financial SQLite database"),
        (sqlite_describe_table, "Inspect table columns and schemas in SQLite database"),
        (sqlite_query, "Execute read-only SQL SELECT queries against financial SQLite database"),
        (sqlite_execute, "Execute safe DDL/DML SQL statements to create custom tables or insert non-standard financial data"),
    ]
    for fn, desc in stock_tool_specs:
        await toolkit.add_tool(
            FunctionTool(
                fn,
                permission=PermissionDecision(
                    behavior=PermissionBehavior.ALLOW,
                    message=f"Safe financial market & structured persistence tool: {desc}",
                ),
            ),
        )

    effective_model = model_name or config.MODEL_NAME
    effective_base_url = base_url or config.LITELLM_BASE_URL
    effective_hitl_mode = hitl_mode or "dangerous"

    credential = OpenAICredential(
        id="litellm-credential",
        name=effective_model,
        api_key=config.LITELLM_API_KEY,
        base_url=effective_base_url,
    )
    effective_context_size = await resolve_context_size(
        model_name=effective_model,
        base_url=effective_base_url,
        api_key=config.LITELLM_API_KEY,
    )
    model = OpenAIChatModel(
        credential=credential,
        model=effective_model,
        formatter=OpenAIChatFormatter(),
        context_size=effective_context_size,
        parameters=OpenAIChatModel.Parameters(
            max_tokens=config.MODEL_MAX_TOKENS,
        ),
    )

    workspace = LocalWorkspace(workdir=resolved_dir)
    context_config = ContextConfig(
        tool_result_limit=config.TOOL_RESULT_LIMIT,
        trigger_ratio=config.CONTEXT_TRIGGER_RATIO,
        reserve_ratio=config.CONTEXT_RESERVE_RATIO,
    )

    mem_path = Path(memory_dir or config.LONGTERM_MEMORY_DIR).resolve()
    middlewares = []
    if config.LONGTERM_MEMORY_ENABLED:
        mem_path.mkdir(parents=True, exist_ok=True)
        memory_md = mem_path / AgenticMemoryMiddleware.FILENAME_MEMORY_MD
        if not memory_md.exists():
            memory_md.write_bytes(b"")
        memory_params = AgenticMemoryMiddleware.Parameters(
            memory_instructions=CHINESE_MEMORY_INSTRUCTIONS,
            memory_max_tokens=config.LONGTERM_MEMORY_MAX_TOKENS,
            retrieval_max_tokens_per_md=config.LONGTERM_MEMORY_RETRIEVAL_MAX_TOKENS,
        )
        memory_middleware = AgenticMemoryMiddleware(
            workdir=str(mem_path.parent),
            memory_dir=mem_path.name,
            parameters=memory_params,
        )
        middlewares.append(memory_middleware)

    agent = Agent(
        name="Assistant",
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(
            workspace_dir=resolved_dir,
            environment_block=_build_environment_block(workspace_dir),
        ),
        model=model,
        toolkit=toolkit,
        middlewares=middlewares,
        state=state,
        offloader=workspace,
        context_config=context_config,
    )

    if effective_hitl_mode == "never":
        agent._engine.context.mode = PermissionMode.BYPASS
    elif effective_hitl_mode == "always":
        agent._engine.context.mode = PermissionMode.DEFAULT
        schemas = await toolkit.get_tool_schemas()
        for s in schemas:
            tool_name = s.get("function", {}).get("name")
            if tool_name:
                agent._engine.add_rule(
                    PermissionRule(
                        tool_name=tool_name,
                        rule_content="",
                        behavior=PermissionBehavior.ASK,
                        source="userSettings",
                    ),
                )
    else:  # "dangerous" or default
        # 安全模式（dangerous）下：
        # 1. 在安全工作区目录及记忆目录内的写文件/编辑（Write/Edit）自动放行无需人工确认；
        # 2. 常规 Python 命令执行（Bash: python / python3）自动放行无需人工确认；
        # 3. 只有敏感目录写入、高危系统命令（破坏性删除、系统提权等）才触发人工确认（HITL）。
        agent._engine.context.mode = PermissionMode.ACCEPT_EDITS

        resolved_ws = str(workspace_dir.resolve())
        agent._engine.context.working_directories[resolved_ws] = AdditionalWorkingDirectory(
            path=resolved_ws,
            source="workspaceDir",
        )
        resolved_mem = str(mem_path)
        agent._engine.context.working_directories[resolved_mem] = AdditionalWorkingDirectory(
            path=resolved_mem,
            source="memoryDir",
        )

        for fs_tool in ("Write", "Edit"):
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=fs_tool,
                    rule_content=f"{resolved_ws}/**",
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=fs_tool,
                    rule_content=f"{resolved_mem}/**",
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )

        # 运行 python/python3 脚本或快速计算命令直接放行
        python_bash_rules = [
            "python:*",
            "python3:*",
            "python3.*:*",
            "/usr/bin/python:*",
            "/usr/bin/python3:*",
            "/usr/local/bin/python:*",
            "/usr/local/bin/python3:*",
            f"{sys.executable}:*",
        ]
        for rule_content in python_bash_rules:
            agent._engine.add_rule(
                PermissionRule(
                    tool_name="Bash",
                    rule_content=rule_content,
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )

        # Tavily MCP 等只读网络检索工具属于安全操作，默认自动放行无需人工确认
        allowed_tools = set(SAFE_MCP_TOOLS)
        try:
            schemas = await toolkit.get_tool_schemas()
            for s in schemas:
                tool_name = s.get("function", {}).get("name")
                if tool_name and any(
                    tool_name.startswith(prefix) for prefix in SAFE_MCP_TOOL_PREFIXES
                ):
                    allowed_tools.add(tool_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to inspect tool schemas for safe MCP tools: %s", exc
            )

        for safe_tool in allowed_tools:
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=safe_tool,
                    rule_content="",
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )

    agent._hitl_mode = effective_hitl_mode
    return agent

