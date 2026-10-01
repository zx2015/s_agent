"""
动态子智能体调度工具 (Dynamic Sub-Agent Delegation Tool).

为主协调智能体（Main Orchestrator Agent）提供统一的任务委派接口 `delegate_task`，
支持动态注入专属角色、特定指令、工具沙箱白名单及底座模板。
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, List, Optional

from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, ToolBase

from server import config
from server.agent.subagents.runner import DynamicSubAgentRunner

logger = logging.getLogger(__name__)


def create_delegate_task_tool(
    workspace_dir: Path,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    mcp_tools: Optional[List[ToolBase]] = None,
) -> FunctionTool:
    """
    构造绑定当前任务工作区与运行时环境的 delegate_task 工具实例。
    """
    resolved_ws = Path(workspace_dir).resolve()

    async def delegate_task(
        role: str,
        instruction: str,
        allowed_tools: List[str],
        base_template: str = "general",
        timeout_seconds: int = 0,
        max_iters: int = 0,
        persist_to_wiki: bool = True,
    ) -> str:
        """
        动态生成并委派一个具有专属角色和限定工具集的子智能体（Sub-Agent）去执行专业子任务。
        子智能体拥有完全隔离的上下文，执行完毕后向主智能体汇报高密度结构化摘要（300~600字以内）。

        参数:
            role: 子智能体的专业角色定义（如："资深乳品行业调研员"、"CPA财务精算与估值建模师"、"红队风险审查员"）
            instruction: 主 Agent 下达的具体任务目标、分析范围与交付要求
            allowed_tools: 授权该子智能体使用的工具组别名（web_search, stock_market, python_calc, finance_db, wiki_tools, file_io）或单个具体工具名
            base_template: 基础底座模板类型，可选值:
                           - "research": 适合搜索、研报解读与定性分析（默认超时 300s, max_iters=15）
                           - "finance": 适合数据建模、报表核算与公式计算（默认超时 180s, max_iters=10）
                           - "reviewer": 批判性审查与逻辑挑刺（默认超时 120s, max_iters=8）
                           - "general": 通用分析与代码任务（默认超时 60s, max_iters=8）
            timeout_seconds: 自定义超时秒数（0 表示使用模板默认值）
            max_iters: 自定义最大推理迭代轮数（0 表示使用模板默认值）
            persist_to_wiki: 是否授权子智能体将高价值认知与测算底稿自动写入本地投研维基 data/wiki/（默认为 True）
        返回:
            子智能体完成任务后产出的高密度结构化交付摘要与文件底稿路径。
        """
        start_time = asyncio.get_running_loop().time()
        logger.info(
            f"主 Agent 调用 delegate_task: 委派 [{role}] (template={base_template}, "
            f"timeout={timeout_seconds}s, max_iters={max_iters}, tools={allowed_tools})"
        )

        runner = DynamicSubAgentRunner(
            role=role,
            instruction=instruction,
            allowed_tools=allowed_tools,
            base_template=base_template,
            workspace_dir=resolved_ws,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            mcp_tools=mcp_tools,
            timeout_seconds=timeout_seconds,
            max_iters=max_iters,
            persist_to_wiki=persist_to_wiki,
        )

        res = await runner.run()
        elapsed = asyncio.get_running_loop().time() - start_time
        summary_preview = res[:150].replace("\n", " ") if res else "<empty>"
        logger.info(
            f"子智能体 [{role}] 汇报完成 (耗时 {elapsed:.1f}s, 返回字符数 {len(res)}): {summary_preview}..."
        )
        return res

    return FunctionTool(
        delegate_task,
        permission=PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="安全动态委派子智能体执行垂直子任务",
        ),
    )
