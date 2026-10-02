# -*- coding: utf-8 -*-
"""工作区沙箱化 Glob 文件检索工具。

严格限定文件检索范围在当前任务所在的工作区目录内，
防止跨工作区穿透以及泄露服务宿主代码。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import PermissionRule, PermissionBehavior
from agentscope.tool import Glob, ToolChunk

logger = logging.getLogger(__name__)


class WorkspaceGlob(Glob):
    """工作区沙箱限定的 Glob 工具。

    1. 默认检索基准根目录为当前任务所属的 workspace_dir；
    2. 严格校验任何传入的 path 参数，拦截越界路径（如 ../ 或跨工作区绝对路径）；
    3. 自动过滤隐藏私有运行态目录（如 .tasks/）。
    """

    def __init__(
        self,
        workspace_dir: Path | str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.workspace_dir = Path(workspace_dir).resolve()

    async def generate_suggestions(
        self,
        tool_input: dict[str, Any],
    ) -> list[PermissionRule]:
        """生成限定在当前工作区范围内的建议权限规则。"""
        pattern = str(self.workspace_dir).rstrip("/\\") + "/**"
        return [
            PermissionRule(
                tool_name=self.name,
                rule_content=pattern,
                behavior=PermissionBehavior.ALLOW,
                source="suggested",
            ),
        ]

    async def call(  # type: ignore[override]
        self,
        pattern: str,
        path: str | None = None,
    ) -> ToolChunk:
        """在当前工作区沙箱内检索匹配 pattern 的文件。

        Args:
            pattern: Glob 匹配模式（如 `*.md`、`**/*.py`、`reports/*.csv`）
            path: 可选的子路径，默认为工作区根目录。相对路径将基于工作区解析，严禁越界访问工作区外部。
        """
        # 1. 确定并校验目标目录
        if not path or path.strip() in ("", "."):
            target_dir = self.workspace_dir
        else:
            given_path = Path(path.strip())
            if not given_path.is_absolute():
                target_dir = (self.workspace_dir / given_path).resolve()
            else:
                target_dir = given_path.resolve()

            # 防越界与沙箱逃逸校验
            try:
                target_dir.relative_to(self.workspace_dir)
            except ValueError:
                logger.warning(
                    f"WorkspaceGlob 越界访问拦截: path='{path}', "
                    f"resolved='{target_dir}', workspace='{self.workspace_dir}'"
                )
                return ToolChunk(
                    content=[
                        TextBlock(
                            text=(
                                f"Permission Denied: Path '{path}' resolves to '{target_dir}', "
                                f"which is outside the current workspace directory '{self.workspace_dir}'. "
                                "Glob search is strictly confined to the current workspace."
                            )
                        )
                    ],
                    state=ToolResultState.ERROR,
                    is_last=True,
                )

        # 2. 检查目录有效性
        if not target_dir.exists() or not target_dir.is_dir():
            return ToolChunk(
                content=[
                    TextBlock(text=f"Directory not found in workspace: {path or target_dir}"),
                ],
                state=ToolResultState.ERROR,
                is_last=True,
            )

        # 3. 调用底层 Glob 执行检索
        chunk = await super().call(pattern=pattern, path=str(target_dir))

        if chunk.state == ToolResultState.ERROR:
            return chunk

        # 4. 过滤私有目录（如 .tasks/ 会话快照与临时截断文件）
        if not chunk.content:
            return chunk

        raw_text = chunk.content[0].text
        if not raw_text or raw_text.startswith("No files found"):
            return chunk

        lines = raw_text.splitlines()
        filtered_lines = []
        private_marker = str(self.workspace_dir / ".tasks")
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if "/.tasks/" in line_str or line_str.startswith(private_marker) or "/.tasks" in line_str:
                continue
            filtered_lines.append(line_str)

        if not filtered_lines:
            return ToolChunk(
                content=[
                    TextBlock(text=f"No files found matching pattern: {pattern}"),
                ],
                state=ToolResultState.RUNNING,
                is_last=True,
            )

        return ToolChunk(
            content=[TextBlock(text="\n".join(filtered_lines))],
            state=ToolResultState.RUNNING,
            is_last=True,
        )
