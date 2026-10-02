"""
LLM Wiki 原生工具集 (Native Tools for Agents).

为智能体提供访问与编译投研维基的标准接口：
- wiki_query: 检索知识库索引与摘要目录
- wiki_read: 读取特定维基页面完整正文
- wiki_save_page: 编译或更新维基页面并同步索引
- wiki_get_index: 获取维基总目录 index.md 原始内容

支持两种使用模式：
1. create_wiki_tools(wiki_root)：工厂函数，返回绑定到指定工作区维基的工具函数字典；
2. 模块级 standalone 函数（wiki_query, wiki_read, wiki_save_page）：兼容旧代码，默认使用全局 wiki_store。
"""
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from server.service.wiki_store import WikiStore, wiki_store

logger = logging.getLogger(__name__)


def create_wiki_tools(wiki_root: Path | str) -> Dict[str, Callable]:
    """
    为指定工作区维基目录创建上下文强绑定的维基工具集。
    返回包含 wiki_query, wiki_read, wiki_save_page, wiki_get_index 函数的字典。
    """
    store = WikiStore(root_dir=Path(wiki_root))

    def wiki_query(
        keyword: str = "",
        category: str = "",
        limit: Optional[int | str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        检索当前工作区投研维基（LLM Wiki）的内容索引。
        在启动深度调研或回答个股/行业问题前，调用此工具可快速查阅当前工作区是否已有编译好的研究成果，避免重复从全网盲目搜索。

        参数:
            keyword: 搜索关键词（如标的名称'伊利股份'、代码'sh600887'、行业赛道'乳制品'、专题主题'现金流'）
            category: 可选限定分类，可选值: 'entities'（个股公司）, 'industries'（行业宏观）, 'analyses'（专题测算）
            limit: 可选限制返回条数（支持数字或数字字符串）
        返回:
            包含匹配页面列表与总数的结构化数据（包含路径、标题、核心概述、标签、更新时间）。
        """
        try:
            entries = store.query_wiki(keyword=keyword, category=category)
            if limit is not None:
                try:
                    max_n = max(0, int(limit))
                    entries = entries[:max_n]
                except (ValueError, TypeError):
                    pass
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

    def wiki_read(
        rel_path: str,
        offset: Optional[int | str] = None,
        limit: Optional[int | str] = None,
        **kwargs: Any,
    ) -> str:
        """
        读取当前工作区指定维基页面的 Markdown 正文。支持可选的行范围分页（用于大文档按需阅读以节省上下文）。

        参数:
            rel_path: 页面相对路径，例如 'entities/sh600887.md'、'industries/dairy-industry.md' 或 'analyses/2024-h1-yili-cashflow.md'
            offset: 可选起始行号（从 1 开始计数，默认为 1）
            limit: 可选读取的最大行数（默认读取全文）
        返回:
            页面的完整 Markdown 文本。若不存在则返回明确错误提示。
        """
        try:
            content = store.read_page(rel_path)
            if offset is not None or limit is not None:
                lines = content.splitlines(keepends=True)
                total_lines = len(lines)
                start_idx = 0
                if offset is not None:
                    try:
                        start_idx = max(0, int(offset) - 1)
                    except (ValueError, TypeError):
                        start_idx = 0
                if limit is not None:
                    try:
                        limit_count = max(0, int(limit))
                        end_idx = start_idx + limit_count
                    except (ValueError, TypeError):
                        end_idx = total_lines
                else:
                    end_idx = total_lines
                sliced_lines = lines[start_idx:end_idx]
                header = f"<!-- 显示第 {start_idx + 1} 至 {min(end_idx, total_lines)} 行（共 {total_lines} 行） -->\n"
                return header + "".join(sliced_lines)
            return content
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
        将分析成果、个股档案、行业逻辑或测算底稿保存至当前工作区投研维基（wiki/）。
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
            saved_file = store.save_page(
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
        获取当前工作区维基总索引目录（index.md）的原始 Markdown 表格。
        适合快速纵览当前已有的所有沉淀知识资产。
        """
        return store.get_index_content()

    return {
        "wiki_query": wiki_query,
        "wiki_read": wiki_read,
        "wiki_save_page": wiki_save_page,
        "wiki_get_index": wiki_get_index,
    }


# ============================================================================
# 模块级兼容接口（默认绑定全局 wiki_store，供独立单测或无工作区环境使用）
# ============================================================================

def wiki_query(
    keyword: str = "",
    category: str = "",
    limit: Optional[int | str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """检索本地投研维基（LLM Wiki）的内容索引（默认全局实例）。"""
    try:
        entries = wiki_store.query_wiki(keyword=keyword, category=category)
        if limit is not None:
            try:
                max_n = max(0, int(limit))
                entries = entries[:max_n]
            except (ValueError, TypeError):
                pass
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


def wiki_read(
    rel_path: str,
    offset: Optional[int | str] = None,
    limit: Optional[int | str] = None,
    **kwargs: Any,
) -> str:
    """读取指定维基页面的 Markdown 正文（默认全局实例）。"""
    try:
        content = wiki_store.read_page(rel_path)
        if offset is not None or limit is not None:
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)
            start_idx = 0
            if offset is not None:
                try:
                    start_idx = max(0, int(offset) - 1)
                except (ValueError, TypeError):
                    start_idx = 0
            if limit is not None:
                try:
                    limit_count = max(0, int(limit))
                    end_idx = start_idx + limit_count
                except (ValueError, TypeError):
                    end_idx = total_lines
            else:
                end_idx = total_lines
            sliced_lines = lines[start_idx:end_idx]
            header = f"<!-- 显示第 {start_idx + 1} 至 {min(end_idx, total_lines)} 行（共 {total_lines} 行） -->\n"
            return header + "".join(sliced_lines)
        return content
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
    """将分析成果保存至本地投研维基（默认全局实例）。"""
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
    """获取维基总索引目录（index.md）的原始 Markdown 表格（默认全局实例）。"""
    return wiki_store.get_index_content()
