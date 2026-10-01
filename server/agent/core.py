"""
主协调智能体（Chief Orchestrator & Planner）构建工厂。

在 Multi-Agent 架构下，主 Agent 扮演总指挥角色：
1. 聚焦任务拆解、大纲设计与最终交付，严禁越俎代庖；
2. 接入极简工具链（仅 11 个工具，含 delegate_task、Task*、Read/Write/Edit/Glob、AskUser、wiki_query/wiki_read）；
3. 专业工具（Tavily 搜索、腾讯行情、SQLite 持久化、Python 运算）全面下沉至底层工具资源池，
   由子智能体（Sub-Agent）按需动态沙箱领用；
4. 交付文件自适应命名，全量研究成果落盘工作区根目录。
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
    Edit,
    Glob,
    LocalBackend,
    Read,
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
    ToolBase,
    Toolkit,
    Write,
    FunctionTool,
)

from server import config
from server.agent.calibrator import resolve_context_size
from server.agent.tools_subagent import create_delegate_task_tool
from server.agent.tools_wiki import wiki_query, wiki_read
from server.tools.mcp import build_mcp_clients, parse_mcp_servers

# 首席分析师与任务编排总监系统提示词
SYSTEM_PROMPT_TEMPLATE = (
    "你是 s_agent 投研与综合任务工作台的【首席分析师与任务调度编排总监 (Chief Orchestrator & Planner)】。\n"
    "你的工作区目录是：\n"
    "{workspace_dir}\n"
    "所有最终交付的投研报告、代码与分析文件都必须保存在该工作区目录下。\n\n"
    "【核心使命与架构职责（重要）】\n"
    "1. **大局统筹与顶层规划**：你专注于用户意图剖析、报告框架设计、任务拆解与最终综合交付；\n"
    "2. **⭐ 严禁越俎代庖（动态委派机制）**：你本身不直接进行底层信息检索、网页抓取、实时行情查询或 Python 复杂运算！"
    "所有垂直专业子任务，必须通过调用 `delegate_task` 工具动态委派给具有专属角色与独立沙箱的子智能体（Sub-Agent）完成；\n"
    "3. **认知查阅与沉淀**：你可通过 `wiki_query` 和 `wiki_read` 查阅本地投研维基（data/wiki/）已有成果；子智能体产出的深度底稿也会自动沉淀在维基中；\n"
    "4. **综合研报起草与落盘交付**：汇总各子智能体的高密度汇报底稿后，你负责统揽全局，消除分歧，撰写详尽完备的最终报告，并通过 Write 工具落盘到工作区。\n\n"
    "【动态子智能体委派规范 (delegate_task)】\n"
    "- **调研与资料搜集**：委派行业/公司调研专家（base_template='research'，allowed_tools=['web_search', 'wiki_tools', 'file_io']），"
    "负责全网搜索最新研报、行业周期数据，并自动将核心认知编译沉淀至 data/wiki/；\n"
    "- **财务建模与量化计算**：委派财务精算与估值建模师（base_template='finance'，allowed_tools=['stock_market', 'python_calc', 'finance_db', 'wiki_tools']），"
    "负责查询行情、拉取历史K线、运行 Python 进行三张表与DCF精准计算、将事实底稿录入 SQLite/维基，绝对避免心算；\n"
    "- **红队批判审阅**：委派审慎风控审查员（base_template='reviewer'，allowed_tools=['file_io', 'wiki_tools']），"
    "负责逆向审视商业模式漏洞、商誉应收风险与极端敏感性；\n"
    "- **通用专项任务**：委派通用执行员（base_template='general'，allowed_tools=['python_calc', 'file_io', 'wiki_tools']）；\n"
    "- **子智能体汇报契约**：子智能体会将全量详尽底稿写入本地维基，向你汇报时仅提供 300~600 字高密度 4 段式摘要（核心结论、关键指标表、维基底稿路径、存疑提示）。"
    "如需查阅特定完整细节，你可调用 wiki_read 查阅。\n\n"
    "【四步标准协同 SOP】\n"
    "1. **第一步：大纲规划与维基查阅**：调用 TaskCreate 创建清晰的分析任务大纲；先调用 wiki_query('标的/行业') 查看本地是否已有现成维基资产；\n"
    "2. **第二步：按需动态委派**：根据大纲，分别调用 delegate_task 委派垂直子智能体（如先派调研专家获取行业与业务情报，再派财务建模专家获取行情与精算财务比率）；"
    "每步启动与结束时调用 TaskUpdate 保持进度看板同步；\n"
    "3. **第三步：综合研报起草与自适应落盘**：统筹各子智能体汇交的事实底稿，按照【自适应交付物命名规范】调用 Write 工具生成专业研报；\n"
    "4. **第四步：完工同步**：调用 TaskUpdate 将所有任务置为 completed，并在对话中向用户呈现精炼结论与交付物索引。\n\n"
    "【自适应交付物命名规范（必须严格遵守）】\n"
    "- 必须根据用户具体提问与任务主题自适应命名交付文件，**绝不能死板固定**为某一个名字！\n"
    "- 命名范式：\n"
    "  • 单标的深度分析：`{workspace_dir}/<标的名称>投资价值深度分析.md`（如 `伊利股份_投资价值深度分析.md`）\n"
    "  • 同业横向对比：`{workspace_dir}/<行业名称>_<标的A>与<标的B>_<核心对比维度>.md`（如 `乳制品行业_伊利与蒙牛_核心财务与竞争格局对比.md`）\n"
    "  • 行业或宏观专题：`{workspace_dir}/<行业或赛道>_<核心议题分析>.md`（如 `生鲜乳周期演变与下游乳企毛利敏感性测算.md`）\n"
    "  • 专项测算底稿：`{workspace_dir}/<标的名称>_<估值模型类型>测算底稿.md`（如 `贵州茅台_自由现金流折现DCF模型底稿.md`）\n"
    "- 写入工作区的文件会自动出现在用户界面右侧的「产物/预览」面板中供用户在线预览。\n\n"
    "【排版与交互准则】\n"
    "- 在对话气泡中输出的所有文本都会以 GitHub 风格 Markdown 渲染展示，请规范排版——用表格呈现对比数据、用加粗标明核心事实与推论；\n"
    "- 遇到多意图或歧义需求时，可调用 AskUser 向用户澄清。\n\n"
    "【权限与运行时提示】\n"
    "- 如果一次工具调用被拒绝，代表用户主动拒绝了该操作，请调整思路或更换方案，说明被拒绝操作的影响，不要在没有新信息的情况下直接重试同一个命令。\n"
    "- 对话消息与工具结果中出现的 <system-reminder> 标签，是运行框架自动注入的运行时提示（例如当前时间、待办任务状态等），并非用户本人发出的内容。\n"
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
- 你也可以在需要时使用 `Read` 工具主动查阅 `{memory_dir}` 下的文件。
"""


def _detect_shell() -> str:
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
    """
    构造主协调智能体（Main Orchestrator Agent）实例。
    主 Agent 持有极简管理与调度工具链，底层专业工具交由 delegate_task 的子智能体沙箱领用。
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = str(workspace_dir.resolve())
    backend = LocalBackend()

    effective_model = model_name or config.MODEL_NAME
    effective_base_url = base_url or config.LITELLM_BASE_URL
    effective_hitl_mode = hitl_mode or "dangerous"

    # 1. 预先解析 MCP 客户端与工具池，作为底层资源池注入 delegate_task，不污染主 Agent Schema
    mcp_tools: list[ToolBase] = []
    try:
        mcp_clients = build_mcp_clients(parse_mcp_servers(config.MCP_SERVERS))
        for client in mcp_clients:
            try:
                tools = await client.list_tools()
                mcp_tools.extend(tools)
            except Exception as client_err:
                logger.warning(
                    "获取 MCP '%s' 工具列表异常: %s", client.name, client_err
                )
    except Exception as exc:
        logger.error("解析 MCP 服务配置失败 (S_AGENT_MCP_SERVERS): %s", exc)

    # 2. 组装主 Agent 极简工具链 (Lean Orchestrator Toolset)
    toolkit = Toolkit()

    # 核心：动态子智能体调度器
    delegate_tool = create_delegate_task_tool(
        workspace_dir=workspace_dir,
        model_name=effective_model,
        base_url=effective_base_url,
        api_key=config.LITELLM_API_KEY,
        mcp_tools=mcp_tools,
    )
    await toolkit.add_tool(delegate_tool)

    # 任务编排与看板工具 (Task Planning)
    await toolkit.add_tool(TaskCreate())
    await toolkit.add_tool(TaskGet())
    await toolkit.add_tool(TaskList())
    await toolkit.add_tool(TaskUpdate())

    # 交付物读写与文件管理 (Delivery Tools)
    await toolkit.add_tool(Read(backend=backend))
    await toolkit.add_tool(Write(backend=backend))
    await toolkit.add_tool(Edit(backend=backend))
    await toolkit.add_tool(Glob(backend=backend))

    # 人机交互澄清工具
    await toolkit.add_tool(AskUser())

    # 本地投研维基高层查阅工具
    await toolkit.add_tool(
        FunctionTool(
            wiki_query,
            permission=PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message="检索本地投研维基索引",
            ),
        ),
    )
    await toolkit.add_tool(
        FunctionTool(
            wiki_read,
            permission=PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message="查阅本地投研维基页面",
            ),
        ),
    )

    # 3. 凭证与模型组装
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

    # 4. 权限与 HITL 安全配置
    wiki_path_str = str(Path(config.WIKI_DIR).resolve())
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
        agent._engine.context.mode = PermissionMode.ACCEPT_EDITS

        resolved_ws = str(workspace_dir.resolve())
        agent._engine.context.working_directories[resolved_ws] = (
            AdditionalWorkingDirectory(
                path=resolved_ws,
                source="workspaceDir",
            )
        )
        resolved_mem = str(mem_path)
        agent._engine.context.working_directories[resolved_mem] = (
            AdditionalWorkingDirectory(
                path=resolved_mem,
                source="memoryDir",
            )
        )
        agent._engine.context.working_directories[wiki_path_str] = (
            AdditionalWorkingDirectory(
                path=wiki_path_str,
                source="wikiDir",
            )
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
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=fs_tool,
                    rule_content=f"{wiki_path_str}/**",
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=fs_tool,
                    rule_content="data/wiki/**",
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )

        # delegate_task 与维基高层查阅工具免人工确认直接放行
        for auto_allowed_tool in ("delegate_task", "wiki_query", "wiki_read"):
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=auto_allowed_tool,
                    rule_content="",
                    behavior=PermissionBehavior.ALLOW,
                    source="systemDefault",
                ),
            )

    agent._hitl_mode = effective_hitl_mode
    return agent
