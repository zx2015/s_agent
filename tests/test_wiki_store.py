"""
Unit tests for WikiStore and Wiki Native Tools.
"""
from pathlib import Path
import pytest

from server.service.wiki_store import WikiStore, get_wiki_store, set_wiki_store
from server.agent.tools_wiki import wiki_get_index, wiki_query, wiki_read, wiki_save_page


@pytest.fixture
def test_wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wiki_dir = tmp_path / "wiki"
    monkeypatch.setattr("server.config.WIKI_DIR", wiki_dir)
    store = WikiStore(root_dir=wiki_dir)
    set_wiki_store(store)
    return store


def test_wiki_store_init_structure(test_wiki: WikiStore):
    root = test_wiki.root_dir
    assert (root / "entities").is_dir()
    assert (root / "industries").is_dir()
    assert (root / "analyses").is_dir()
    assert (root / "raw").is_dir()
    assert (root / "SCHEMA.md").is_file()
    assert (root / "index.md").is_file()
    assert (root / "log.md").is_file()

    schema_content = (root / "SCHEMA.md").read_text(encoding="utf-8")
    assert "LLM Wiki 投研知识库维护公约" in schema_content


def test_wiki_store_save_and_read(test_wiki: WikiStore):
    saved_path = test_wiki.save_page(
        rel_path="entities/sh600887_伊利股份.md",
        title="sh600887_伊利股份",
        content="## 核心财务指标\n- ROE: 18.5%\n- 股息率: 4.5%",
        summary="伊利股份最新财务与基本面分析",
        tags=["乳制品", "白马股", "分红"],
        author="财务建模分析师",
    )
    assert Path(saved_path).is_file()

    # Read back
    content = test_wiki.read_page("entities/sh600887_伊利股份.md")
    assert "ROE: 18.5%" in content
    assert "股息率: 4.5%" in content
    assert test_wiki.page_exists("entities/sh600887_伊利股份.md") is True


def test_wiki_store_index_and_log_update(test_wiki: WikiStore):
    test_wiki.save_page(
        rel_path="industries/乳制品行业竞争格局.md",
        title="乳制品行业竞争格局",
        content="伊利与蒙牛双寡头垄断，合计市占率超40%...",
        summary="全国乳制品两强双寡头格局演变",
        tags=["行业格局", "伊利", "蒙牛"],
    )

    # Check index.md
    index_text = (test_wiki.root_dir / "index.md").read_text(encoding="utf-8")
    assert "乳制品行业竞争格局" in index_text
    assert "全国乳制品两强双寡头格局演变" in index_text

    # Check log.md
    log_text = (test_wiki.root_dir / "log.md").read_text(encoding="utf-8")
    assert "乳制品行业竞争格局" in log_text
    assert "industries/乳制品行业竞争格局.md" in log_text


def test_wiki_store_query(test_wiki: WikiStore):
    test_wiki.save_page(
        rel_path="entities/sh600519_贵州茅台.md",
        title="sh600519_贵州茅台",
        content="高端白酒龙头，确定性极高，现金流充沛。",
        summary="贵州茅台价值研报",
        tags=["白酒", "消费龙头"],
    )

    results = test_wiki.query_wiki("茅台")
    assert len(results) >= 1
    assert results[0]["title"] == "sh600519_贵州茅台"
    assert "entities/sh600519_贵州茅台.md" in results[0]["path"]

    # Search for non-existent keyword
    empty_results = test_wiki.query_wiki("非标不存在关键词XYZ123")
    assert len(empty_results) == 0


def test_wiki_native_tools(test_wiki: WikiStore):
    # Test tool wrappers
    res = wiki_save_page(
        rel_path="analyses/伊利股份_DCF折现测算底稿.md",
        title="伊利股份_DCF折现测算底稿",
        content="DCF合理市值 1850 亿元，当前安全边际 15%...",
        summary="DCF三阶段折现估值模型",
        tags=["估值", "DCF"],
    )
    assert res["status"] == "success"
    assert "成功保存维基页面" in res["message"]

    read_res = wiki_read("analyses/伊利股份_DCF折现测算底稿.md")
    assert "DCF合理市值 1850 亿元" in read_res

    query_res = wiki_query("DCF")
    assert query_res["status"] == "success"
    assert query_res["count"] == 1
    assert query_res["results"][0]["title"] == "伊利股份_DCF折现测算底稿"

    index_res = wiki_get_index()
    assert "伊利股份_DCF折现测算底稿" in index_res


def test_wiki_read_offset_limit_and_kwargs(test_wiki: WikiStore):
    test_wiki.save_page(
        rel_path="analyses/multi_line_doc.md",
        title="多行测试文档",
        content="line 1\nline 2\nline 3\nline 4\nline 5",
        summary="多行文档",
    )

    # 1. Full read
    assert "line 1\nline 2\nline 3\nline 4\nline 5" in wiki_read("analyses/multi_line_doc.md")

    # 2. Offset and limit as string (from LLM call)
    sliced = wiki_read("analyses/multi_line_doc.md", offset="2", limit="2", extra_unrecognized_arg="foo")
    assert "line 2\nline 3" in sliced
    assert "line 1" not in sliced
    assert "line 4" not in sliced

    # 3. Limit on query
    q_all = wiki_query(keyword="测试")
    assert q_all["count"] >= 1
    q_limit = wiki_query(keyword="测试", limit=1, unexpected_arg=123)
    assert len(q_limit["results"]) <= 1
