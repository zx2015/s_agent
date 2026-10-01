"""
LLM Wiki 原生工具集 (Native Tools for Agents).

为智能体提供访问与编译本地投研维基（data/wiki/）的标准接口：
- wiki_query: 检索知识库索引与摘要目录
- wiki_read: 读取特定维基页面完整正文
- wiki_save_page: 编译或更新维基页面并同步索引
- wiki_get_index: 获取维基总目录 index.md 原始内容
"""
import logging
from typing import Any, Dict, List, Optional

from server.service.wiki_store import wiki_store

logger = logging.getLogger(__name__)


def wiki_query(keyword: str = "", category: str = "") -> Dict[str, Any]:
    """
    检索本地投研维基（LLM Wiki）的内容索引。
    在启动深度调研或回答个股/行业问题前，调用此工具可快速查阅本地是否已有编译好的研究成果，避免重复从全网盲目搜索。

    参数:
        keyword: 搜索关键词（如标的名称'伊利股份'、代码'sh600887'、行业赛道'乳制品'、专题主题'现金流'）
        category: 可选限定分类，可选值: 'entities'（个股公司）, 'industries'（行业宏观）, 'analyses'（专题测算）
    返回:
        包含匹配页面列表与总数的结构化数据（包含路径、标题、核心概述、标签、更新时间）。
    """
    try:
        entries = wiki_store.query_wiki(keyword=keyword, category=category)
        return {
            "status": "success",
            "count": len(entries),
            "results": entries,
            "hint": "如需查看某篇具体分析，请调用 wiki_read(rel_path) 并传入对应的 path。"
        }
    except Exception as e:
        logger.error(f"wiki_query 检索失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"维基索引检索异常: {str(e)}"
        }


def wiki_read(rel_path: str) -> str:
    """
    读取指定维基页面的 Markdown 正文。

    参数:
        rel_path: 页面相对路径，例如 'entities/sh600887.md'、'industries/dairy-industry.md' 或 'analyses/2024-h1-yili-cashflow.md'
    返回:
        页面的完整 Markdown 文本。若不存在则返回明确错误提示。
    """
    try:
        return wiki_store.read_page(rel_path)
    except FileNotFoundError:
        return f"【错误】维基页面不存在: '{rel_path}'。请先调用 wiki_query() 查阅可用页面路径。"
    except Exception as e:
        logger.error(f"wiki_read 读取失败: {e}", exc_info=True)
        return f"【错误】读取维基页面异常: {str(e)}"


def wiki_save_page(
    rel_path: str,
    content: str,
    title: str,
    summary: str,
    tags: Optional[List[str]] = None,
    category: str = "",
    author: str = "sub_agent",
) -> Dict[str, Any]:
    """
    将分析成果、个股档案、行业逻辑或测算底稿保存至本地投研维基（data/wiki/）。
    系统会自动将其登记至 index.md 导航地图并追加至 log.md 审计流水。

    参数:
        rel_path: 相对路径，规范要求:
                  - 个股档案: 'entities/<股票代码>.md'（如 'entities/sh600887.md'）
                  - 行业赛道: 'industries/<行业标识>.md'（如 'industries/dairy-industry.md'）
                  - 深度测算: 'analyses/<年份季度>-<标的>-<主题>.md'（如 'analyses/2024-h1-yili-fcf.md'）
        content: 完整的结构化 Markdown 分析正文
        title: 页面标题，清晰概括研究主体（如 '伊利股份 (600887) 核心业务与竞争壁垒'）
        summary: 1~2 句话提炼最核心的定论与事实（用于 index.md 目录展示）
        tags: 关联的股票代码、简称、行业标签列表，如 ['伊利股份', 'sh600887', '生鲜乳']
        category: 分类（entities/industries/analyses，若空按路径首段自动推导）
        author: 记录贡献该成果的智能体角色名
    返回:
        包含保存结果与落盘绝对路径的字典。
    """
    try:
        saved_file = wiki_store.save_page(
            rel_path=rel_path,
            content=content,
            title=title,
            summary=summary,
            category=category,
            tags=tags,
            author=author,
        )
        return {
            "status": "success",
            "message": f"成功保存维基页面并同步索引: {rel_path}",
            "saved_path": str(saved_file),
            "rel_path": rel_path,
        }
    except Exception as e:
        logger.error(f"wiki_save_page 保存失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"保存维基页面异常: {str(e)}"
        }


def wiki_get_index() -> str:
    """
    获取维基总索引目录（index.md）的原始 Markdown 表格。
    适合快速纵览当前已有的所有沉淀知识资产。
    """
    return wiki_store.get_index_content()
