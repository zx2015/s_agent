# -*- coding: utf-8 -*-
"""工作区沙箱化 Glob 与工作区专属 Wiki 专项单元测试。

验证内容:
1. WorkspaceGlob 严格受限于 workspace_dir，正常检索工作区内部文件与子目录；
2. WorkspaceGlob 拦截非法逃逸（../、绝对路径越权至其它工作区或宿主项目根目录）；
3. WorkspaceGlob 自动过滤排除 .tasks/ 私有沙箱目录；
4. create_wiki_tools 工厂产出工具实现多工作区 Wiki 强隔离（A 工作区沉淀的内容在 B 工作区查不到）；
5. TaskManager 正确获取工作区维基路径并自动迁移历史旧版维基。
"""
import pytest
from pathlib import Path
from agentscope.message import ToolResultState

from server import config
from server.agent.tools_glob import WorkspaceGlob
from server.agent.tools_wiki import create_wiki_tools
from server.agent.subagents.tool_resolver import ToolResolver
from server.service.task_manager import TaskManager


@pytest.fixture
def test_workspaces(tmp_path: Path):
    """创建两个相互独立的工作区用于隔离性测试。"""
    ws_a = tmp_path / "workspaces" / "ws_alpha"
    ws_b = tmp_path / "workspaces" / "ws_beta"
    ws_a.mkdir(parents=True, exist_ok=True)
    ws_b.mkdir(parents=True, exist_ok=True)
    return ws_a, ws_b


@pytest.mark.asyncio
async def test_workspace_glob_normal_match(tmp_path: Path):
    """测试在当前工作区内正常模式匹配与嵌套目录匹配。"""
    ws = tmp_path / "ws_main"
    ws.mkdir(parents=True, exist_ok=True)

    # 准备文件
    (ws / "report_2026.md").write_text("report", encoding="utf-8")
    (ws / "data.csv").write_text("csv", encoding="utf-8")
    sub_dir = ws / "models"
    sub_dir.mkdir()
    (sub_dir / "dcf.xlsx").write_text("model", encoding="utf-8")

    glob_tool = WorkspaceGlob(workspace_dir=ws)

    # 1. 默认根目录检索所有 md
    resp = await glob_tool.call(pattern="*.md")
    assert resp.state != ToolResultState.ERROR
    content = resp.content[0].text
    assert "report_2026.md" in content

    # 2. 递归检索
    resp_all = await glob_tool.call(pattern="**/*")
    content_all = resp_all.content[0].text
    assert "report_2026.md" in content_all
    assert "data.csv" in content_all
    assert "dcf.xlsx" in content_all

    # 3. 指定工作区内子目录
    resp_sub = await glob_tool.call(pattern="*", path="models")
    content_sub = resp_sub.content[0].text
    assert "dcf.xlsx" in content_sub


@pytest.mark.asyncio
async def test_workspace_glob_filters_tasks_dir(tmp_path: Path):
    """测试自动过滤 .tasks/ 私有沙箱目录。"""
    ws = tmp_path / "ws_main"
    ws.mkdir(parents=True, exist_ok=True)

    # 工作区公开产出物
    (ws / "summary.md").write_text("public summary", encoding="utf-8")

    # .tasks 私有目录中的文件
    task_dir = ws / ".tasks" / "task_123"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "scratchpad.txt").write_text("private scratch", encoding="utf-8")
    (task_dir / "internal_report.md").write_text("internal", encoding="utf-8")

    glob_tool = WorkspaceGlob(workspace_dir=ws)

    # 检索全部 md
    resp = await glob_tool.call(pattern="**/*.md")
    content = resp.content[0].text
    assert "summary.md" in content
    assert "internal_report.md" not in content
    assert ".tasks" not in content


@pytest.mark.asyncio
async def test_workspace_glob_intercepts_path_traversal(tmp_path: Path):
    """测试拦截尝试越界逃逸到宿主或其它目录的操作。"""
    workspaces_root = tmp_path / "workspaces"
    ws_a = workspaces_root / "ws_a"
    ws_b = workspaces_root / "ws_b"
    ws_a.mkdir(parents=True, exist_ok=True)
    ws_b.mkdir(parents=True, exist_ok=True)

    (ws_b / "secret_b.md").write_text("confidential b", encoding="utf-8")
    outside_file = tmp_path / "system_secret.txt"
    outside_file.write_text("top secret", encoding="utf-8")

    glob_tool = WorkspaceGlob(workspace_dir=ws_a)

    # 1. 使用相对路径 ../ 越权
    resp_rel = await glob_tool.call(pattern="*", path="../ws_b")
    assert resp_rel.state == ToolResultState.DENIED or "Permission Denied" in resp_rel.content[0].text

    # 2. 使用绝对路径越权访问 ws_b
    resp_abs = await glob_tool.call(pattern="*", path=str(ws_b))
    assert resp_abs.state == ToolResultState.DENIED or "Permission Denied" in resp_abs.content[0].text

    # 3. 访问更上层绝对路径
    resp_out = await glob_tool.call(pattern="*", path=str(tmp_path))
    assert resp_out.state == ToolResultState.DENIED or "Permission Denied" in resp_out.content[0].text


@pytest.mark.asyncio
async def test_workspace_glob_invalid_path(tmp_path: Path):
    """测试指定不存在的路径或非目录路径时的健壮性。"""
    ws = tmp_path / "ws_main"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "file.txt").write_text("content", encoding="utf-8")

    glob_tool = WorkspaceGlob(workspace_dir=ws)

    # 不存在的目录
    resp_not_found = await glob_tool.call(pattern="*", path="non_existent_folder")
    assert resp_not_found.state == ToolResultState.ERROR or "不存在" in resp_not_found.content[0].text

    # 传入文件而非目录
    resp_is_file = await glob_tool.call(pattern="*", path="file.txt")
    assert resp_is_file.state == ToolResultState.ERROR or "不是有效目录" in resp_is_file.content[0].text


@pytest.mark.asyncio
async def test_workspace_wiki_tools_multi_tenant_isolation(test_workspaces):
    """测试通过 create_wiki_tools 绑定的不同工作区 Wiki 强隔离。"""
    ws_a, ws_b = test_workspaces
    wiki_a_dir = ws_a / "wiki"
    wiki_b_dir = ws_b / "wiki"

    tools_a = create_wiki_tools(wiki_a_dir)
    tools_b = create_wiki_tools(wiki_b_dir)

    # 工作区 A 录入伊利股份深度报告
    tools_a["wiki_save_page"](
        rel_path="entities/yili.md",
        title="伊利股份",
        summary="中国乳制品行业龙头，常温奶市场份额稳固",
        content="# 伊利股份投研分析\n2025年总营收稳健增长，常温白奶市场份额保持第一。",
        category="entities",
    )

    # 1. 验证工作区 A 能够检索到
    query_a = tools_a["wiki_query"]("伊利股份")
    assert query_a["count"] > 0
    assert any("entities/yili.md" in item["path"] for item in query_a["results"])

    # 验证工作区 A 能够读取到
    page_a = tools_a["wiki_read"]("entities/yili.md")
    assert "总营收稳健增长" in page_a

    # 2. 验证工作区 B 绝对检索不到伊利股份（多租户隔离）
    query_b = tools_b["wiki_query"]("伊利股份")
    assert query_b["count"] == 0

    page_b = tools_b["wiki_read"]("entities/yili.md")
    assert "不存在" in page_b

    # 3. 验证文件物理隔离
    assert (wiki_a_dir / "entities" / "yili.md").exists()
    assert not (wiki_b_dir / "entities" / "yili.md").exists()


@pytest.mark.asyncio
async def test_subagent_tool_resolver_workspace_binding(tmp_path: Path):
    """测试 ToolResolver 为子智能体绑定工作区专属 Glob 与 Wiki 工具。"""
    ws = tmp_path / "subagent_ws"
    ws.mkdir(parents=True, exist_ok=True)

    resolver = ToolResolver()
    tools = resolver.resolve(
        allowed_tools=["file_io", "wiki_tools"],
        workspace_dir=ws,
    )

    # 检查工具列表
    tool_map = {t.name: t for t in tools}
    assert "Glob" in tool_map
    assert isinstance(tool_map["Glob"], WorkspaceGlob)
    assert tool_map["Glob"].workspace_dir == ws

    # 检查 wiki 工具
    assert "wiki_query" in tool_map
    assert "wiki_read" in tool_map
    assert "wiki_save_page" in tool_map

    # 验证执行 wiki_save_page 写入的是 subagent_ws/wiki
    save_tool = tool_map["wiki_save_page"]
    resp = await save_tool.call(
        rel_path="industries/dairy.md",
        title="乳制品行业",
        summary="原奶周期触底回升",
        content="# 乳制品行业研报",
        category="industries",
    )
    assert resp.state != ToolResultState.ERROR
    assert (ws / "wiki" / "industries" / "dairy.md").exists()


def test_task_manager_wiki_dirs_and_legacy_migration(tmp_path: Path, monkeypatch):
    """测试 TaskManager 的工作区 Wiki 目录管理与历史数据迁移。"""
    data_dir = tmp_path / "data"
    workspaces_dir = data_dir / "workspaces"
    legacy_wiki = data_dir / "wiki"
    legacy_wiki.mkdir(parents=True, exist_ok=True)

    # 伪造旧版本全局 wiki 内容
    (legacy_wiki / "entities").mkdir(parents=True, exist_ok=True)
    (legacy_wiki / "entities" / "old_stock.md").write_text("旧版股票", encoding="utf-8")
    (legacy_wiki / "SCHEMA.md").write_text("# Old Schema", encoding="utf-8")

    # 覆盖 REPO_ROOT 以测试从 legacy_wiki 自动迁移
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)

    # 启动 TaskManager
    tm = TaskManager(root_dir=workspaces_dir)

    # 1. 验证 get_workspace_wiki_dir
    ws_custom_wiki = tm.get_workspace_wiki_dir("my_ws")
    assert ws_custom_wiki == (workspaces_dir / "my_ws" / "wiki").resolve()

    # 2. 验证迁移机制：启动后旧版 legacy_wiki 中的 old_stock.md 应被迁移至 default 工作区 wiki
    default_wiki = workspaces_dir / "default" / "wiki"
    assert (default_wiki / "entities" / "old_stock.md").exists()
    assert (default_wiki / "entities" / "old_stock.md").read_text(encoding="utf-8") == "旧版股票"
