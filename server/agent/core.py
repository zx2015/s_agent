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
import os
import platform
from pathlib import Path

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionBehavior, PermissionDecision
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
from server.tools.calculator import calculate

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


async def build_agent(workspace_dir: Path) -> Agent:
    """Assemble the toolkit and the model-backed agent for one task.

    Args:
        workspace_dir: The task's private working directory. All file
            tools operate relative to this path via a dedicated
            `LocalBackend`, so tasks cannot see or touch each other's
            files.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = str(workspace_dir.resolve())
    backend = LocalBackend()

    toolkit = Toolkit()
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

    credential = OpenAICredential(
        id="litellm-vflash",
        name="LiteLLM v-flash",
        api_key=config.LITELLM_API_KEY,
        base_url=config.LITELLM_BASE_URL,
    )
    model = OpenAIChatModel(
        credential=credential,
        model=config.MODEL_NAME,
        formatter=OpenAIChatFormatter(),
        parameters=OpenAIChatModel.Parameters(
            max_tokens=config.MODEL_MAX_TOKENS,
        ),
    )

    return Agent(
        name="Assistant",
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(
            workspace_dir=resolved_dir,
            environment_block=_build_environment_block(workspace_dir),
        ),
        model=model,
        toolkit=toolkit,
    )
