"""
动态子智能体运行时套件 (Dynamic Sub-Agent Runtime Suite).
"""
from server.agent.subagents.runner import DynamicSubAgentRunner
from server.agent.subagents.templates import (
    BaseTemplateConfig,
    build_subagent_system_prompt,
    get_template_config,
)
from server.agent.subagents.tool_resolver import (
    TOOL_GROUP_REGISTRY,
    ToolResolver,
    expand_allowed_tools,
)

__all__ = [
    "BaseTemplateConfig",
    "DynamicSubAgentRunner",
    "TOOL_GROUP_REGISTRY",
    "ToolResolver",
    "build_subagent_system_prompt",
    "expand_allowed_tools",
    "get_template_config",
]
