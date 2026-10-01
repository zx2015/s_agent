"""
Unit tests for Tencent Stock Native Toolkit (server/tools/stock.py).
"""
import pytest
from unittest.mock import patch, MagicMock

from server.tools.stock import (
    normalize_symbol,
    stock_search,
    stock_quote,
    stock_batch_quotes,
    stock_kline,
    stock_minute,
    stock_handicap,
    market_index_overview,
    _CACHE,
)


@pytest.fixture(autouse=True)
def clear_stock_cache(monkeypatch):
    _CACHE.clear()
    monkeypatch.setattr("server.tools.stock.finance_db.get_latest_daily_quote", lambda *args, **kwargs: None)
    monkeypatch.setattr("server.tools.stock.finance_db.get_kline_records", lambda *args, **kwargs: [])
    yield
    _CACHE.clear()


def test_normalize_symbol():
    assert normalize_symbol("600519") == "sh600519"
    assert normalize_symbol("688001") == "sh688001"
    assert normalize_symbol("000001") == "sz000001"
    assert normalize_symbol("300750") == "sz300750"
    assert normalize_symbol("600519.SH") == "sh600519"
    assert normalize_symbol("000858.sz") == "sz000858"
    assert normalize_symbol("00700") == "hk00700"
    assert normalize_symbol("hk00700") == "hk00700"
    assert normalize_symbol("AAPL") == "usaapl"
    assert normalize_symbol("sh600887") == "sh600887"


@patch("server.tools.stock._http_get")
def test_stock_search(mock_http):
    mock_http.return_value = 'v_hint="sh~600887~伊利股份~ylgf~GP-A^sz~002603~以岭药业~ylyy~GP-A"'

    res = stock_search("伊利")
    assert len(res) == 2
    assert res[0]["symbol"] == "sh600887"
    assert res[0]["code"] == "600887"
    assert res[0]["name"] == "伊利股份"
    assert res[0]["pinyin"] == "ylgf"
    assert res[0]["type"] == "GP-A"

    # Test cache hit
    res_cached = stock_search("伊利")
    assert len(res_cached) == 2
    mock_http.assert_called_once()  # Called only once due to cache


@patch("server.tools.stock._http_get")
def test_stock_quote(mock_http):
    mock_http.return_value = (
        'v_sh600887="1~伊利股份~600887~27.30~27.24~27.25~303783~163385~140398~'
        '27.29~65~27.28~226~27.27~713~27.26~246~27.25~470~'
        '27.30~875~27.31~375~27.32~933~27.33~10~27.34~20~~'
        '20260930161458~0.06~0.22~27.38~27.10~27.30/303783/828230588~303783~82823~0.48~18.2~~'
        '27.38~27.10~1.03~1737.89~1737.89~3.21~29.96~24.52~0.85~-500~27.26~17.5~18.2~4.5~'
        '10.0~82823.0588~GP-A~18.2~17.5~1737.89~0.92~4.5~27.30~";'
    )

    quote = stock_quote("600887")
    assert quote["symbol"] == "sh600887"
    assert quote["name"] == "伊利股份"
    assert quote["price"] == 27.30
    assert quote["change"] == 0.06
    assert quote["change_percent"] == 0.22
    assert quote["turnover_rate"] == 0.48
    assert quote["total_mv"] == 1737.89
    assert quote["circulating_mv"] == 1737.89
    assert quote["pb"] == 3.21
    assert quote["pe_dynamic"] == 18.2
    assert quote["active_buy_ratio"] is not None
    assert quote["active_buy_ratio"] > 0


@patch("server.tools.stock._http_get")
def test_stock_batch_quotes(mock_http):
    mock_http.return_value = (
        'v_s_sh600519="1~贵州茅台~600519~1258.62~23.04~1.86~38331~479725~~15733.78~GP-A~";\n'
        'v_s_sz000858="51~五粮液~000858~112.50~1.20~1.08~120000~135000~~4366.50~GP-A~";'
    )

    results = stock_batch_quotes(["600519", "000858"])
    assert len(results) == 2
    assert results[0]["symbol"] == "sh600519"
    assert results[0]["name"] == "贵州茅台"
    assert results[0]["price"] == 1258.62
    assert results[1]["symbol"] == "sz000858"
    assert results[1]["name"] == "五粮液"
    assert results[1]["price"] == 112.50


@patch("server.tools.stock._http_get")
def test_stock_kline(mock_http):
    mock_http.return_value = (
        '{"code":0,"msg":"","data":{"sh600887":{"qfqday":['
        '["2026-09-29","27.100","27.240","27.350","27.050","250000.000","680000000.000"],'
        '["2026-09-30","27.250","27.300","27.380","27.100","303783.000","828230588.000"]'
        ']}}}'
    )

    bars = stock_kline("600887", period="day", count=2)
    assert len(bars) == 2
    assert bars[0]["date"] == "2026-09-29"
    assert bars[0]["open"] == 27.10
    assert bars[0]["close"] == 27.24
    assert bars[1]["date"] == "2026-09-30"
    assert bars[1]["close"] == 27.30
    assert bars[1]["volume"] == 303783.0


@patch("server.tools.stock._http_get")
def test_stock_minute(mock_http):
    mock_http.return_value = (
        '{"code":0,"msg":"","data":{"sh600887":{"data":{"data":['
        '"0930 27.25 1553 4231925.00",'
        '"0931 27.28 3200 8729600.00"'
        ']}}}}'
    )

    points = stock_minute("600887", days=1)
    assert len(points) == 2
    assert points[0]["time"] == "09:30"
    assert points[0]["price"] == 27.25
    assert points[0]["volume"] == 1553
    assert points[1]["time"] == "09:31"
    assert points[1]["price"] == 27.28


@patch("server.tools.stock._http_get")
def test_stock_handicap(mock_http):
    mock_http.return_value = 'v_s_pksh600887="0.150~0.358~0.133~0.358";'

    pk = stock_handicap("600887")
    assert pk["symbol"] == "sh600887"
    assert pk["buy_big_ratio"] == 0.150
    assert pk["buy_small_ratio"] == 0.358
    assert pk["sell_big_ratio"] == 0.133
    assert pk["sell_small_ratio"] == 0.358


@patch("server.tools.stock._http_get")
def test_market_index_overview(mock_http):
    mock_http.return_value = (
        'v_s_sh000001="1~上证指数~000001~3842.19~11.74~0.31~414560247~67939899~~682245.82~ZS~";\n'
        'v_s_sz399001="51~深证成指~399001~12887.62~-14.33~-0.11~494715201~75861910~~422961.58~ZS~";\n'
        'v_s_sz399006="51~创业板指~399006~3135.28~-7.28~-0.23~133666684~36623872~~176297.87~ZS~";'
    )

    indices = market_index_overview()
    assert len(indices) == 3
    assert indices[0]["symbol"] == "sh000001"
    assert indices[0]["name"] == "上证指数"
    assert indices[0]["point"] == 3842.19
    assert indices[0]["change_percent"] == 0.31


@pytest.mark.asyncio
async def test_subagent_resolver_registers_all_stock_tools(tmp_path):
    from server.agent.subagents.tool_resolver import ToolResolver
    resolver = ToolResolver()
    tools = resolver.resolve(["stock_market"], tmp_path)
    tool_names = {t.name for t in tools}
    expected_tools = {
        "stock_search",
        "stock_quote",
        "stock_batch_quotes",
        "stock_kline",
        "stock_minute",
        "stock_handicap",
        "market_index_overview",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_build_agent_registers_lean_orchestrator_tools(tmp_path):
    from server.agent.core import build_agent
    agent = await build_agent(workspace_dir=tmp_path)
    schemas = await agent.toolkit.get_tool_schemas()
    tool_names = {
        s["function"]["name"] if "function" in s else s.get("name")
        for s in schemas
    }
    # Lean main agent tools
    assert "delegate_task" in tool_names
    assert "wiki_query" in tool_names
    assert "wiki_read" in tool_names
    assert "TaskCreate" in tool_names
    assert "Write" in tool_names
    # Low-level tools offloaded to sub-agents
    assert "stock_quote" not in tool_names
    assert "Bash" not in tool_names
