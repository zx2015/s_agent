"""
Unit and Integration Tests for Structured Finance DB & Autonomous SQLite Toolkit.
================================================================================
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import respx
import httpx

from server.service import finance_db
from server.tools import stock


@pytest.fixture
def temp_db(tmp_path: Path):
    """Provide a clean isolated SQLite database file for testing."""
    db_file = tmp_path / "test_finance.db"
    finance_db.init_db(db_file)
    return db_file


def test_init_db_creates_predefined_tables(temp_db: Path):
    tables = finance_db.sqlite_show_tables(temp_db)
    table_names = {t["table_name"] for t in tables}
    expected = {
        "stocks",
        "stock_daily_quotes",
        "stock_kline_records",
        "stock_financial_metrics",
        "user_watchlist",
        "research_notes",
    }
    assert expected.issubset(table_names)
    for t in tables:
        assert t["type"] == "system_predefined"


def test_upsert_stock_and_daily_quote(temp_db: Path):
    # Upsert stock metadata
    finance_db.upsert_stock(
        symbol="sh600887",
        name="伊利股份",
        code="600887",
        market="SH",
        industry="乳品",
        db_path=temp_db,
    )

    # Upsert quote
    quote_data = {
        "symbol": "sh600887",
        "name": "伊利股份",
        "code": "600887",
        "price": 27.85,
        "prev_close": 27.50,
        "open": 27.60,
        "high": 28.10,
        "low": 27.45,
        "change": 0.35,
        "change_percent": 1.27,
        "amplitude": 2.36,
        "volume_lot": 350000,
        "amount_wan": 97000.0,
        "turnover_rate": 0.55,
        "pe_ttm": 16.8,
        "pb": 2.65,
        "total_mv": 1770.0,
        "circulating_mv": 1770.0,
        "high_52w": 31.50,
        "low_52w": 23.20,
        "outer_bid": 180000,
        "inner_bid": 170000,
        "active_buy_ratio": 0.5143,
        "buy_big_ratio": 0.32,
        "sell_big_ratio": 0.28,
        "timestamp": "20261001150000",
    }
    finance_db.upsert_daily_quote(quote_data, db_path=temp_db)

    # Query back
    latest = finance_db.get_latest_daily_quote("sh600887", db_path=temp_db)
    assert latest is not None
    assert latest["symbol"] == "sh600887"
    assert latest["close_price"] == 27.85
    assert latest["pe_ttm"] == 16.8
    assert latest["total_mv"] == 1770.0
    assert latest["name"] == "伊利股份"
    assert latest["trade_date"] == "2026-10-01"


def test_upsert_and_get_kline_records(temp_db: Path):
    bars = [
        {"date": "2026-09-28", "open": 27.0, "close": 27.2, "high": 27.5, "low": 26.9, "volume": 200000.0},
        {"date": "2026-09-29", "open": 27.2, "close": 27.5, "high": 27.8, "low": 27.1, "volume": 220000.0},
        {"date": "2026-09-30", "open": 27.5, "close": 27.85, "high": 28.1, "low": 27.4, "volume": 350000.0},
    ]
    inserted = finance_db.upsert_kline_records("sh600887", period="day", bars=bars, db_path=temp_db)
    assert inserted == 3

    # Idempotent re-insert
    re_inserted = finance_db.upsert_kline_records("sh600887", period="day", bars=bars, db_path=temp_db)
    assert re_inserted == 3

    fetched = finance_db.get_kline_records("sh600887", period="day", count=10, db_path=temp_db)
    assert len(fetched) == 3
    assert fetched[0]["date"] == "2026-09-28"
    assert fetched[2]["date"] == "2026-09-30"
    assert fetched[2]["close"] == 27.85

    latest_date = finance_db.get_kline_latest_date("sh600887", period="day", db_path=temp_db)
    assert latest_date == "2026-09-30"


def test_record_and_query_financial_metric(temp_db: Path):
    # Record metrics from user research
    mid = finance_db.record_financial_metric(
        symbol="sh600887",
        report_period="2026H1",
        category="cash_flow",
        metric_name="经营活动现金流净额",
        metric_value=97.59,
        unit="亿元",
        yoy_change="+229%",
        context_notes="现金/归母 = 1.69，Q2单季60亿",
        db_path=temp_db,
    )
    assert mid > 0

    finance_db.record_financial_metric(
        symbol="sh600887",
        report_period="2026H1",
        category="profitability",
        metric_name="销售费用率",
        metric_value=17.77,
        unit="%",
        context_notes="1143.22 / 6433.09",
        db_path=temp_db,
    )

    metrics = finance_db.query_financial_metrics("sh600887", report_period="2026H1", db_path=temp_db)
    assert len(metrics) == 2
    assert any(m["metric_name"] == "经营活动现金流净额" and m["metric_value"] == 97.59 for m in metrics)
    assert any(m["metric_name"] == "销售费用率" and m["metric_value"] == 17.77 for m in metrics)


def test_manage_watchlist_lifecycle(temp_db: Path):
    # Prepare stock and quote
    finance_db.upsert_stock("sh600887", name="伊利股份", db_path=temp_db)
    finance_db.upsert_daily_quote({"symbol": "sh600887", "price": 27.85, "timestamp": "20261001150000"}, db_path=temp_db)

    # 1. Add to watchlist
    res_add = finance_db.manage_watchlist(
        action="add",
        symbol="sh600887",
        target_buy_price=25.0,
        target_sell_price=35.0,
        core_logic="原奶周期见底，高股息稳健",
        db_path=temp_db,
    )
    assert res_add["success"] is True

    # 2. List watchlist
    res_list = finance_db.manage_watchlist(action="list", db_path=temp_db)
    assert res_list["total"] == 1
    item = res_list["items"][0]
    assert item["symbol"] == "sh600887"
    assert item["name"] == "伊利股份"
    assert item["target_buy_price"] == 25.0
    assert item["latest_price"] == 27.85

    # 3. Update watchlist
    finance_db.manage_watchlist(
        action="update",
        symbol="sh600887",
        target_buy_price=26.0,
        core_logic="原奶周期见底，回购上限39.53",
        db_path=temp_db,
    )
    res_list_updated = finance_db.manage_watchlist(action="list", db_path=temp_db)
    assert res_list_updated["items"][0]["target_buy_price"] == 26.0
    assert "回购上限39.53" in res_list_updated["items"][0]["core_logic"]

    # 4. Remove from watchlist
    res_del = finance_db.manage_watchlist(action="remove", symbol="sh600887", db_path=temp_db)
    assert res_del["success"] is True
    res_list_empty = finance_db.manage_watchlist(action="list", db_path=temp_db)
    assert res_list_empty["total"] == 0


def test_finance_overview(temp_db: Path):
    finance_db.upsert_stock("sh600887", name="伊利股份", market="SH", db_path=temp_db)
    finance_db.upsert_daily_quote({"symbol": "sh600887", "price": 27.85, "pe_ttm": 16.8, "total_mv": 1770.0, "timestamp": "20261001150000"}, db_path=temp_db)
    finance_db.upsert_stock("sz000858", name="五粮液", market="SZ", db_path=temp_db)
    finance_db.upsert_daily_quote({"symbol": "sz000858", "price": 140.0, "pe_ttm": 18.2, "total_mv": 5400.0, "timestamp": "20261001150000"}, db_path=temp_db)

    overview = finance_db.get_finance_overview(market="ALL", db_path=temp_db)
    assert len(overview) == 2

    sh_only = finance_db.get_finance_overview(market="SH", db_path=temp_db)
    assert len(sh_only) == 1
    assert sh_only[0]["symbol"] == "sh600887"


# ---------------------------------------------------------------------------
# Agent Autonomous SQLite Toolkit Tests & Guardrails
# ---------------------------------------------------------------------------

def test_sqlite_describe_table(temp_db: Path):
    info = finance_db.sqlite_describe_table("stocks", db_path=temp_db)
    assert info["table_name"] == "stocks"
    col_names = [c["name"] for c in info["columns"]]
    assert "symbol" in col_names
    assert "name" in col_names
    assert "market" in col_names


def test_sqlite_query_read_only_success(temp_db: Path):
    finance_db.upsert_stock("sh600887", name="伊利股份", db_path=temp_db)
    res = finance_db.sqlite_query("SELECT symbol, name FROM stocks WHERE symbol = 'sh600887'", db_path=temp_db)
    assert len(res) == 1
    assert res[0]["name"] == "伊利股份"


def test_sqlite_query_blocks_write_statements(temp_db: Path):
    with pytest.raises(PermissionError, match="only permits read-only"):
        finance_db.sqlite_query("DELETE FROM stocks", db_path=temp_db)

    with pytest.raises(PermissionError, match="only permits read-only"):
        finance_db.sqlite_query("INSERT INTO stocks (symbol, name) VALUES ('x', 'y')", db_path=temp_db)


def test_sqlite_execute_autonomous_table_creation(temp_db: Path):
    # Agent autonomously creates a custom table for raw milk prices
    ddl = """
    CREATE TABLE IF NOT EXISTS custom_raw_milk_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_week VARCHAR(16) NOT NULL,
        avg_price REAL NOT NULL,
        yoy_pct REAL,
        region VARCHAR(32) DEFAULT '全国主产区',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_res = finance_db.sqlite_execute(ddl, db_path=temp_db)
    assert create_res["success"] is True

    # Show tables must now include custom_raw_milk_prices as agent_created
    tables = finance_db.sqlite_show_tables(temp_db)
    custom_tbl = next(t for t in tables if t["table_name"] == "custom_raw_milk_prices")
    assert custom_tbl["type"] == "agent_created"

    # Agent inserts records
    insert_sql = "INSERT INTO custom_raw_milk_prices (report_week, avg_price, yoy_pct) VALUES ('2026-W38', 3.12, -7.5);"
    ins_res = finance_db.sqlite_execute(insert_sql, db_path=temp_db)
    assert ins_res["rows_affected"] == 1

    # Query custom table
    q_res = finance_db.sqlite_query("SELECT report_week, avg_price FROM custom_raw_milk_prices", db_path=temp_db)
    assert len(q_res) == 1
    assert q_res[0]["report_week"] == "2026-W38"
    assert q_res[0]["avg_price"] == 3.12


def test_sqlite_execute_guardrails_protect_predefined_tables(temp_db: Path):
    # Attempting to DROP a system predefined table must fail with PermissionError
    with pytest.raises(PermissionError, match="Cannot drop protected system core table 'stocks'"):
        finance_db.sqlite_execute("DROP TABLE stocks;", db_path=temp_db)

    with pytest.raises(PermissionError, match="Cannot drop protected system core table 'stock_daily_quotes'"):
        finance_db.sqlite_execute("DROP TABLE IF EXISTS stock_daily_quotes;", db_path=temp_db)


def test_sqlite_execute_guardrails_blocks_high_risk_keywords(temp_db: Path):
    with pytest.raises(PermissionError, match="strictly forbidden"):
        finance_db.sqlite_execute("ATTACH DATABASE '/tmp/other.db' AS other;", db_path=temp_db)

    with pytest.raises(PermissionError, match="strictly forbidden"):
        finance_db.sqlite_execute("VACUUM;", db_path=temp_db)


# ---------------------------------------------------------------------------
# Transparent Cache-Aside in stock_quote and stock_kline
# ---------------------------------------------------------------------------

@respx.mock
def test_stock_quote_transparent_cache_aside(monkeypatch, temp_db: Path):
    # Point default DB to temp_db
    monkeypatch.setattr(finance_db, "FINANCE_DB_PATH", temp_db)
    # Clear in-memory cache
    stock._CACHE.clear()

    # Pre-populate SQLite with a quote from "today"
    today_str = "2026-10-01"
    finance_db.upsert_stock("sh600887", name="伊利股份", db_path=temp_db)
    mock_payload = {
        "symbol": "sh600887",
        "name": "伊利股份",
        "code": "600887",
        "price": 27.85,
        "pe_ttm": 16.8,
        "total_mv": 1770.0,
        "timestamp": f"{today_str.replace('-', '')}150000",
    }
    finance_db.upsert_daily_quote(mock_payload, db_path=temp_db)

    # Force market not in trading hours (e.g. evening or weekend)
    monkeypatch.setattr(stock, "is_market_trading_hours", lambda: False)

    # Calling stock_quote must read from SQLite without hitting any HTTP endpoint!
    res = stock.stock_quote("sh600887")
    assert res["symbol"] == "sh600887"
    assert res["price"] == 27.85
    assert res.get("_source") == "sqlite_cache"
