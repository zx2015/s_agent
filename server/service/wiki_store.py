"""
LLM Wiki (投研知识沉淀体系) 底层存储管理器。

基于 Andrej Karpathy 提出的 LLM Wiki 范式与持续知识编译 (Continual Knowledge Compilation)，
为 Multi-Agent 系统提供跨会话持久化的定性投研认知网络：
1. 三层架构：不可变证据 (raw/)、编译维基 (entities/, industries/, analyses/)、治理公约 (SCHEMA.md)；
2. 双核心索引与审计：index.md (目录地图) 与 log.md (纯追加审计流水)；
3. 原子写入与自愈：任何 save_page 操作均自动同步索引并追加变更日志。
"""
import datetime
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from server import config

logger = logging.getLogger(__name__)

DEFAULT_SCHEMA_CONTENT = """# LLM Wiki 投研知识库维护公约 (SCHEMA.md)

欢迎查阅本地投研知识库。本知识库用于沉淀关于个股、行业赛道、宏观周期及深度估值测算的长期定性与半结构化认知。

## 一、知识分层与目录规划
- `entities/`: 个股与公司标的档案（命名规范：`<市场代码>.md`，如 `sh600887.md`、`hk02319.md`、`sz000858.md`）。
- `industries/`: 行业与宏观赛道分析（命名规范：`<行业拼音或英文小写>.md`，如 `dairy-industry.md`、`liquor-industry.md`）。
- `analyses/`: 深度专题研究与测算底稿（命名规范：`<时期>-<标的>-<主题>.md`，如 `2024-h1-yili-fcf.md`）。
- `raw/`: 不可变信源与研报原始文本快照（只读证据）。

## 二、维护准则 (Maintenance Guidelines)
1. **持续编译 (Continual Compilation)**：遇到新信息时，优先与已有词条整合互补，标注演变事实，严禁整篇覆盖既有有效分析。
2. **超链接互联 (Hyperlinking)**：尽可能使用相对路径超链接（如 `[生鲜乳周期](../industries/raw-milk-cycle.md)`）构建网状认知。
3. **事实与观点分离**：明确区分财报客观数字与券商预测/模型推演观点。
4. **即时审计**：每次写入必须伴随 `index.md` 索引更新与 `log.md` 流水追加。
"""

DEFAULT_INDEX_HEADER = """# LLM Wiki 投研知识库总索引 (index.md)

> 本文件是系统的认知导航地图，记录已编译沉淀的所有词条档案。由系统自动维护。

| 路径 (Path) | 标题 (Title) | 分类 (Category) | 核心概述 (Summary) | 标签 (Tags) | 最后更新 (Updated At) |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

DEFAULT_LOG_HEADER = """# LLM Wiki 变更审计日志 (log.md)

> 纯追加流水账，记录所有智能体对维基的编译、修正与扩充记录。格式：`## [时间] 角色 | 操作类型 | 摘要说明 (关联路径)`

"""


class WikiStore:
    """LLM Wiki 底层文件与索引存储管理器"""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = Path(root_dir or config.WIKI_DIR).resolve()
        self.entities_dir = self.root_dir / "entities"
        self.industries_dir = self.root_dir / "industries"
        self.analyses_dir = self.root_dir / "analyses"
        self.raw_dir = self.root_dir / "raw"
        self.schema_path = self.root_dir / "SCHEMA.md"
        self.index_path = self.root_dir / "index.md"
        self.log_path = self.root_dir / "log.md"

        self.ensure_initialized()

    def ensure_initialized(self) -> None:
        """确保维基基础目录结构与核心引导文件存在"""
        for d in (self.entities_dir, self.industries_dir, self.analyses_dir, self.raw_dir):
            d.mkdir(parents=True, exist_ok=True)

        if not self.schema_path.exists():
            self.schema_path.write_text(DEFAULT_SCHEMA_CONTENT, encoding="utf-8")
        if not self.index_path.exists():
            self.index_path.write_text(DEFAULT_INDEX_HEADER, encoding="utf-8")
        if not self.log_path.exists():
            self.log_path.write_text(DEFAULT_LOG_HEADER, encoding="utf-8")

    def _now_str(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def _sanitize_rel_path(self, rel_path: str) -> str:
        """清洗并校验相对路径，防止路径遍历穿越攻击"""
        cleaned = rel_path.strip().replace("\\", "/").lstrip("/")
        if ".." in cleaned or cleaned.startswith("/"):
            raise ValueError(f"不安全的维基路径: {rel_path}")
        return cleaned

    def save_page(
        self,
        rel_path: str,
        content: str,
        title: str,
        summary: str,
        category: str = "",
        tags: Optional[List[str]] = None,
        author: str = "sub_agent",
        action_type: str = "compile",
    ) -> Path:
        """
        保存或更新一篇维基页面，并原子同步更新 index.md 与追加 log.md。

        参数:
            rel_path: 相对路径，如 'entities/sh600887.md' 或 'industries/dairy.md'
            content: 完整的 Markdown 正文
            title: 页面标题
            summary: 1~2 句话的核心概述
            category: 分类（若空则按路径前缀自动推导 entities/industries/analyses）
            tags: 标签或关联股票代码列表，如 ['伊利股份', 'sh600887', '乳制品']
            author: 执行保存的智能体角色名
            action_type: 操作类型，如 compile, update, revise
        """
        clean_rel = self._sanitize_rel_path(rel_path)
        full_path = self.root_dir / clean_rel
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. 写入正文
        full_path.write_text(content, encoding="utf-8")

        # 2. 推导分类与格式化标签
        if not category:
            parts = clean_rel.split("/")
            category = parts[0] if len(parts) > 1 else "general"

        tag_str = ",".join(tags) if tags else ""
        now = self._now_str()

        # 3. 更新 index.md
        self._upsert_index(clean_rel, title, category, summary, tag_str, now)

        # 4. 追加 log.md
        self._append_log(author, action_type, f"{title}: {summary}", clean_rel, now)

        logger.info(f"Wiki 页面保存并索引成功: {clean_rel} (author={author})")
        return full_path

    def read_page(self, rel_path: str) -> str:
        """读取指定维基页面的 Markdown 内容"""
        clean_rel = self._sanitize_rel_path(rel_path)
        full_path = self.root_dir / clean_rel
        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"维基页面不存在: {clean_rel}")
        return full_path.read_text(encoding="utf-8")

    def page_exists(self, rel_path: str) -> bool:
        """检查维基页面是否存在"""
        clean_rel = self._sanitize_rel_path(rel_path)
        return (self.root_dir / clean_rel).exists()

    def get_index_content(self) -> str:
        """获取 index.md 原始内容"""
        if self.index_path.exists():
            return self.index_path.read_text(encoding="utf-8")
        return DEFAULT_INDEX_HEADER

    def get_schema_content(self) -> str:
        """获取 SCHEMA.md 原始内容"""
        if self.schema_path.exists():
            return self.schema_path.read_text(encoding="utf-8")
        return DEFAULT_SCHEMA_CONTENT

    def query_wiki(self, keyword: str = "", category: str = "") -> List[Dict[str, Any]]:
        """
        检索知识库索引。
        若 keyword 和 category 均为空，返回全部索引条目；
        若提供 keyword，匹配路径、标题、摘要及标签（忽略大小写）。
        """
        entries = self._parse_index()
        results = []
        kw = keyword.strip().lower()
        cat = category.strip().lower()

        for entry in entries:
            if cat and entry.get("category", "").lower() != cat:
                continue
            if not kw:
                results.append(entry)
                continue

            searchable = (
                f"{entry.get('path', '')} {entry.get('title', '')} "
                f"{entry.get('summary', '')} {entry.get('tags', '')}"
            ).lower()
            if kw in searchable:
                results.append(entry)

        return results

    def _parse_index(self) -> List[Dict[str, str]]:
        """解析 index.md 中的表格为字典列表"""
        if not self.index_path.exists():
            return []

        lines = self.index_path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines:
            line_str = line.strip()
            if not line_str.startswith("|") or line_str.startswith("| :---"):
                continue
            cols = [c.strip() for c in line_str.split("|")[1:-1]]
            if len(cols) >= 6:
                path_col = cols[0]
                if "路径" in path_col or "Path" in path_col:
                    continue
                # 兼容形如 [sh600887.md](entities/sh600887.md) 或纯相对路径
                m = re.search(r"\((.*?)\)", path_col)
                raw_path = m.group(1) if m else path_col
                entries.append(
                    {
                        "path": raw_path,
                        "title": cols[1],
                        "category": cols[2],
                        "summary": cols[3],
                        "tags": cols[4],
                        "updated_at": cols[5],
                    }
                )
        return entries

    def _upsert_index(
        self,
        rel_path: str,
        title: str,
        category: str,
        summary: str,
        tags: str,
        updated_at: str,
    ) -> None:
        """更新或新增 index.md 中的条目行"""
        entries = self._parse_index()
        found = False
        for e in entries:
            if e["path"] == rel_path:
                e["title"] = title
                e["category"] = category
                e["summary"] = summary
                e["tags"] = tags
                e["updated_at"] = updated_at
                found = True
                break

        if not found:
            entries.append(
                {
                    "path": rel_path,
                    "title": title,
                    "category": category,
                    "summary": summary,
                    "tags": tags,
                    "updated_at": updated_at,
                }
            )

        # 重写 index.md
        out_lines = [DEFAULT_INDEX_HEADER.strip()]
        for e in entries:
            clean_title = e["title"].replace("|", " ")
            clean_sum = e["summary"].replace("|", " ")
            clean_tag = e["tags"].replace("|", " ")
            link = f"[{Path(e['path']).name}]({e['path']})"
            out_lines.append(
                f"| {link} | {clean_title} | {e['category']} | {clean_sum} | {clean_tag} | {e['updated_at']} |"
            )

        self.index_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    def _append_log(
        self,
        author: str,
        action: str,
        detail: str,
        rel_path: str,
        timestamp: str,
    ) -> None:
        """向 log.md 追加流水账"""
        clean_detail = detail.replace("\n", " ").strip()
        log_entry = f"## [{timestamp}] {author} | {action} | {clean_detail} ({rel_path})\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(log_entry)


# 全局单例与访问函数
_wiki_store: Optional[WikiStore] = None


def get_wiki_store() -> WikiStore:
    """获取全局 WikiStore 单例"""
    global _wiki_store
    if _wiki_store is None:
        _wiki_store = WikiStore()
    return _wiki_store


def set_wiki_store(store: WikiStore) -> None:
    """设置全局 WikiStore 单例（主要用于测试沙箱）"""
    global _wiki_store
    _wiki_store = store


class _WikiStoreProxy:
    """透明代理，确保引用 wiki_store 时动态获取当前激活的实例"""
    def __getattr__(self, name):
        return getattr(get_wiki_store(), name)


wiki_store = _WikiStoreProxy()

