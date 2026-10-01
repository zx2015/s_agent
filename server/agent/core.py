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
from pathlib import Path

logger = logging.getLogger(__name__)

from agentscope.agent import Agent, ContextConfig
from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import OpenAIChatModel
from agentscope.middleware import AgenticMemoryMiddleware
from agentscope.permission import (
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
    "文件工具要求绝对路径时，请以该目录为前缀拼接。生成的网页、Markdown、"
    "图片等产物请写入工作区根目录，以便用户在右侧预览。任何超过两个数字的"
    "算术运算，必须调用 calculate 工具，禁止自己心算得出数字结果。\n\n"
    "除工具调用外，你输出的所有文本都会在工作台的对话气泡中以 GitHub 风格 "
    "Markdown（GFM）渲染后展示给用户，请照此排版——代码块标注语言、用表格"
    "呈现结构化数据、用列表整理步骤等。\n\n"
    "工具在用户当前选择的权限模式下运行；如果一次工具调用被拒绝，代表用户"
    "主动拒绝了该操作，而不是执行出错——请调整思路或更换方案，向用户说明被"
    "拒绝操作的影响以及其他可行方案，不要在没有新信息的情况下直接重试同一个"
    "命令。\n\n"
    "对话消息与工具结果中出现的 <system-reminder> 标签，是运行框架自动注入"
    "的运行时提示（例如当前时间、待办任务状态等），并非用户本人发出的内容。"
    "如果配置了工具中间件（middleware），它可能会拦截、修改甚至否决工具调"
    "用；请将中间件返回的结果当作对你本次操作意图的反馈来处理，而不是当作"
    "用户发来的新指令。\n\n"
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

    middlewares = []
    if config.LONGTERM_MEMORY_ENABLED:
        mem_path = Path(memory_dir or config.LONGTERM_MEMORY_DIR).resolve()
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
        agent._engine.context.mode = PermissionMode.DEFAULT

    agent._hitl_mode = effective_hitl_mode
    return agent

