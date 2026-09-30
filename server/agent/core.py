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

SYSTEM_PROMPT_TEMPLATE = (
    "你是 s_agent 工作台里的通用任务助手。你的工作区目录是：\n"
    "{workspace_dir}\n"
    "所有文件读写、Bash 命令都必须在这个目录（或其子目录）下进行，"
    "文件工具要求绝对路径时，请以该目录为前缀拼接。生成的网页、Markdown、"
    "图片等产物请写入工作区根目录，以便用户在右侧预览。任何超过两个数字的"
    "算术运算，必须调用 calculate 工具，禁止自己心算得出数字结果。"
)


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
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(workspace_dir=resolved_dir),
        model=model,
        toolkit=toolkit,
    )
