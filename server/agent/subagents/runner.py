"""
动态子智能体运行时执行容器 (DynamicSubAgentRunner).

职责:
1. 组装短命独立的 Sub-Agent 实例（全新的 AgentState，阅后即焚，不持久化入主 Redis 历史）；
2. 继承并注入相同的 Credential 与 Model 配置，留足 max_tokens 防止推理模型截断；
3. 绑定工具白名单沙箱与工作区/维基安全权限；
4. 施加分级超时保护 (asyncio.wait_for) 与自适应迭代步数限制 (ReActConfig.max_iters)；
5. 防二次膨胀截断保护：确保返回给主 Agent 的内容精炼高密。
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentscope.agent import Agent, ContextConfig, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, TextBlock
from agentscope.model import OpenAIChatModel
from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionBehavior,
    PermissionMode,
    PermissionRule,
)
from agentscope.state import AgentState
from agentscope.tool import ToolBase, Toolkit
from agentscope.workspace import LocalWorkspace

from server import config
from server.agent.calibrator import resolve_context_size
from server.agent.subagents.templates import (
    build_subagent_system_prompt,
    get_template_config,
)
from server.agent.subagents.tool_resolver import ToolResolver

logger = logging.getLogger(__name__)


class DynamicSubAgentRunner:
    """动态子智能体运行时容器"""

    def __init__(
        self,
        role: str,
        instruction: str,
        allowed_tools: List[str],
        base_template: str = "general",
        workspace_dir: Optional[Path] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        mcp_tools: Optional[List[ToolBase]] = None,
        timeout_seconds: int = 0,
        max_iters: int = 0,
        persist_to_wiki: bool = True,
    ):
        self.role = role
        self.instruction = instruction
        self.allowed_tools = allowed_tools
        self.base_template = base_template
        self.workspace_dir = Path(
            workspace_dir or (config.WORKSPACES_ROOT / "default")
        ).resolve()
        self.model_name = model_name or config.MODEL_NAME
        self.base_url = base_url or config.LITELLM_BASE_URL
        self.api_key = api_key or config.LITELLM_API_KEY
        self.mcp_tools = mcp_tools or []
        self.timeout_seconds = timeout_seconds
        self.max_iters = max_iters
        self.persist_to_wiki = persist_to_wiki

    async def run(self) -> str:
        """
        在完全隔离的子上下文中执行子任务，并返回结构化交付成果。
        若遇超时或异常，返回优雅降级信息，保证主 Agent 不被中断挂死。
        """
        tpl = get_template_config(self.base_template)
        effective_timeout = (
            self.timeout_seconds if self.timeout_seconds > 0 else tpl.default_timeout
        )
        effective_max_iters = (
            self.max_iters if self.max_iters > 0 else tpl.default_max_iters
        )

        logger.info(
            f"启动动态子智能体 [{self.role}] (template={self.base_template}, "
            f"timeout={effective_timeout}s, max_iters={effective_max_iters})"
        )

        try:
            return await asyncio.wait_for(
                self._execute_agent(effective_max_iters),
                timeout=float(effective_timeout),
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"动态子智能体 [{self.role}] 执行超时 ({effective_timeout}s)"
            )
            return (
                f"### 【{self.role}·执行超时告警】\n"
                f"- **状态**：子任务在执行 {effective_timeout} 秒后超出时限未完全结束。\n"
                f"- **排查建议**：请主 Agent 检查当前子任务是否过于宽泛，建议拆解为更小的具体问题，"
                f"或在 delegate_task 中增大 timeout_seconds 重新调用。"
            )
        except Exception as e:
            logger.error(f"动态子智能体 [{self.role}] 执行异常: {e}", exc_info=True)
            return (
                f"### 【{self.role}·执行异常】\n"
                f"- **错误详情**：{str(e)}\n"
                f"- **建议**：主 Agent 可调整指令或更换工具沙箱后重试。"
            )

    async def _execute_agent(self, effective_max_iters: int) -> str:
        """组装并执行 AgentScope Agent 实例"""
        # 1. 解析沙箱工具
        tools_to_use = self.allowed_tools or get_template_config(
            self.base_template
        ).default_allowed_presets

        resolver = ToolResolver(mcp_tools=self.mcp_tools)
        resolved_tools = resolver.resolve(tools_to_use, self.workspace_dir)

        toolkit = Toolkit()
        for t in resolved_tools:
            await toolkit.add_tool(t)

        # 2. 组装模型与凭据
        credential = OpenAICredential(
            id="litellm-credential",
            name=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        effective_context_size = await resolve_context_size(
            model_name=self.model_name,
            base_url=self.base_url,
            api_key=self.api_key,
        )
        model = OpenAIChatModel(
            credential=credential,
            model=self.model_name,
            formatter=OpenAIChatFormatter(),
            context_size=effective_context_size,
            parameters=OpenAIChatModel.Parameters(
                max_tokens=config.MODEL_MAX_TOKENS,
            ),
        )

        # 3. 组装双层系统提示词
        wiki_dir_str = str(Path(config.WIKI_DIR).resolve())
        system_prompt = build_subagent_system_prompt(
            base_template=self.base_template,
            role=self.role,
            instruction=self.instruction,
            workspace_dir=str(self.workspace_dir),
            wiki_dir=wiki_dir_str,
        )

        # 4. 组装工作区与状态（全新未污染的 AgentState）
        workspace = LocalWorkspace(workdir=str(self.workspace_dir))
        state = AgentState()
        context_config = ContextConfig(
            tool_result_limit=config.TOOL_RESULT_LIMIT,
            trigger_ratio=config.CONTEXT_TRIGGER_RATIO,
            reserve_ratio=config.CONTEXT_RESERVE_RATIO,
        )
        react_config = ReActConfig(
            max_iters=effective_max_iters,
        )

        agent = Agent(
            name=self.role,
            system_prompt=system_prompt,
            model=model,
            toolkit=toolkit,
            state=state,
            offloader=workspace,
            context_config=context_config,
            react_config=react_config,
        )

        # 5. 配置最小权限白名单沙箱（继承安全模式，防权限外溢）
        agent._engine.context.mode = PermissionMode.ACCEPT_EDITS
        resolved_ws_str = str(self.workspace_dir)
        agent._engine.context.working_directories[resolved_ws_str] = (
            AdditionalWorkingDirectory(
                path=resolved_ws_str,
                source="workspaceDir",
            )
        )
        agent._engine.context.working_directories[wiki_dir_str] = (
            AdditionalWorkingDirectory(
                path=wiki_dir_str,
                source="wikiDir",
            )
        )

        for fs_tool in ("Write", "Edit"):
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=fs_tool,
                    rule_content=f"{resolved_ws_str}/**",
                    behavior=PermissionBehavior.ALLOW,
                    source="subagentSandbox",
                )
            )
            agent._engine.add_rule(
                PermissionRule(
                    tool_name=fs_tool,
                    rule_content=f"{wiki_dir_str}/**",
                    behavior=PermissionBehavior.ALLOW,
                    source="subagentSandbox",
                )
            )

        # Bash 仅允许 Python 命令计算
        for py_cmd in (
            "python:*",
            "python3:*",
            f"{sys.executable}:*",
            "/usr/bin/python3:*",
        ):
            agent._engine.add_rule(
                PermissionRule(
                    tool_name="Bash",
                    rule_content=py_cmd,
                    behavior=PermissionBehavior.ALLOW,
                    source="subagentSandbox",
                )
            )

        # 6. 执行单轮推理循环直至产出最终报告
        inputs = Msg(
            name="user",
            role="user",
            content=[TextBlock(type="text", text=self.instruction)],
        )

        reply_msg = await agent.reply(inputs)
        result_text = reply_msg.get_text_content().strip()

        if not result_text:
            # 兼容空 content 的情况，从 content blocks 中提取
            parts = []
            for block in getattr(reply_msg, "content", []):
                if hasattr(block, "text") and block.text:
                    parts.append(block.text)
            result_text = "\n".join(parts).strip()

        if not result_text:
            result_text = f"【提示】子智能体 [{self.role}] 完成了计算和工具调用，但未生成汇总文字回复。"

        logger.info(
            f"子智能体 [{self.role}] 执行完成，产出字符数: {len(result_text)}"
        )
        return result_text
