"""
Finance Database Service & Autonomous SQLite Toolkit.
=====================================================

Provides structured persistence, transparent caching, and cross-session
querying for financial market assets using a local SQLite WAL database.

Features:
- Standard predefined schema (stocks, daily_quotes, kline_records, financial_metrics, watchlist, research_notes).
- Thread-safe connection management with WAL concurrency (PRAGMA journal_mode = WAL).
- Agent autonomous SQLite toolkit (show_tables, describe_table, query, execute) with strict guardrails.
- High-level business APIs (overview, watchlist, financial facts recording).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Sequence

from server.config import FINANCE_DB_PATH

logger = logging.getLogger(__name__)

# System core tables that must never be dropped or structurally truncated by autonomous tools
PROTECTED_TABLES = frozenset({
    "stocks",
    "stock_daily_quotes",
    "stock_kline_records",
    "stock_financial_metrics",
    "user_watchlist",
    "research_notes",
})

# DDL for predefined system tables
PREDEFINED_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stocks (
    symbol VARCHAR(32) PRIMARY KEY,
    code VARCHAR(16) NOT NULL,
    name VARCHAR(64) NOT NULL,
    market VARCHAR(16) NOT NULL,
    pinyin VARCHAR(32),
    industry VARCHAR(64),
    sec_type VARCHAR(16) DEFAULT 'GP-A',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks(name);
CREATE INDEX IF NOT EXISTS idx_stocks_code ON stocks(code);
CREATE INDEX IF NOT EXISTS idx_stocks_pinyin ON stocks(pinyin);

CREATE TABLE IF NOT EXISTS stock_daily_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(32) NOT NULL,
    trade_date DATE NOT NULL,
    close_price REAL NOT NULL,
    prev_close REAL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    pct_chg REAL NOT NULL,
    chg_amount REAL,
    amplitude REAL,
    volume_lot INTEGER,
    amount_wan REAL,
    turnover_rate REAL,
    pe_ttm REAL,
    pe_dynamic REAL,
    pe_static REAL,
    pb REAL,
    total_mv REAL,
    circ_mv REAL,
    high_52w REAL,
    low_52w REAL,
    outer_bid INTEGER,
    inner_bid INTEGER,
    active_buy_ratio REAL,
    big_order_buy_ratio REAL,
    big_order_sell_ratio REAL,
    raw_payload JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_quotes_symbol_date ON stock_daily_quotes(symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_quotes_pe ON stock_daily_quotes(pe_ttm);
CREATE INDEX IF NOT EXISTS idx_quotes_mv ON stock_daily_quotes(total_mv);

CREATE TABLE IF NOT EXISTS stock_kline_records (
    symbol VARCHAR(32) NOT NULL,
    period VARCHAR(16) NOT NULL,
    kline_date DATE NOT NULL,
    adjust_type VARCHAR(8) DEFAULT 'qfq',
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    volume REAL NOT NULL,
    amount REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, period, kline_date, adjust_type)
);
CREATE INDEX IF NOT EXISTS idx_kline_lookup ON stock_kline_records(symbol, period, adjust_type, kline_date);

CREATE TABLE IF NOT EXISTS stock_financial_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(32) NOT NULL,
    report_period VARCHAR(32) NOT NULL,
    category VARCHAR(32) NOT NULL,
    metric_name VARCHAR(64) NOT NULL,
    metric_value REAL,
    unit VARCHAR(16) DEFAULT '亿元',
    yoy_change VARCHAR(32),
    context_notes TEXT,
    source_task_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fin_symbol ON stock_financial_metrics(symbol, report_period);

CREATE TABLE IF NOT EXISTS user_watchlist (
    symbol VARCHAR(32) PRIMARY KEY,
    target_buy_price REAL,
    target_sell_price REAL,
    cost_price REAL,
    core_logic TEXT,
    alert_notes TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS research_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(32),
    title TEXT NOT NULL,
    source_name VARCHAR(64),
    summary_md TEXT NOT NULL,
    url TEXT,
    publish_date VARCHAR(32),
    task_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_res_symbol ON research_notes(symbol);
"""

# Thread-local storage for connection reuse per thread
_thread_local = threading.local()


def _resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is None:
        p = Path(FINANCE_DB_PATH)
    else:
        p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_db_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create or retrieve a configured SQLite connection with WAL enabled."""
    target_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(
        str(target_path),
        timeout=5.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite database operations with automatic commit/rollback."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Initialize predefined tables and indexes in the database."""
    with db_session(db_path) as conn:
        conn.executescript(PREDEFINED_SCHEMA_SQL)
    logger.info("Finance database initialized at %s", _resolve_db_path(db_path))


# Ensure database is initialized at import / startup
try:
    init_db()
except Exception as e:
    logger.warning("Auto init_db on import encountered non-fatal error: %s", e)


# ---------------------------------------------------------------------------
# Predefined Table CRUD Operations
# ---------------------------------------------------------------------------

def upsert_stock(
    symbol: str,
    name: str,
    code: str = "",
    market: str = "",
    pinyin: str = "",
    industry: str = "",
    sec_type: str = "GP-A",
    db_path: Path | str | None = None,
) -> None:
    """Insert or update a stock's metadata."""
    if not code:
        code = re.sub(r"^[a-zA-Z]+", "", symbol)
    if not market:
        prefix = symbol[:2].upper()
        market = prefix if prefix in ("SH", "SZ", "HK", "US") else "A"

    sql = """
    INSERT INTO stocks (symbol, code, name, market, pinyin, industry, sec_type, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(symbol) DO UPDATE SET
        name = excluded.name,
        code = excluded.code,
        market = excluded.market,
        pinyin = COALESCE(NULLIF(excluded.pinyin, ''), stocks.pinyin),
        industry = COALESCE(NULLIF(excluded.industry, ''), stocks.industry),
        sec_type = excluded.sec_type,
        updated_at = CURRENT_TIMESTAMP;
    """
    with db_session(db_path) as conn:
        conn.execute(sql, (symbol, code, name, market, pinyin, industry, sec_type))


def upsert_daily_quote(quote: dict[str, Any], db_path: Path | str | None = None) -> None:
    """Insert or update a stock's daily valuation and quote snapshot."""
    symbol = quote.get("symbol")
    if not symbol:
        return

    # Parse trade_date
    raw_ts = str(quote.get("timestamp") or "")
    if len(raw_ts) >= 8 and raw_ts[:8].isdigit():
        trade_date = f"{raw_ts[:4]}-{raw_ts[4:6]}-{raw_ts[6:8]}"
    else:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    price = quote.get("price")
    if price is None:
        return

    # Also make sure stock metadata exists
    name = quote.get("name")
    if name:
        upsert_stock(symbol=symbol, name=name, code=str(quote.get("code") or ""), db_path=db_path)

    sql = """
    INSERT INTO stock_daily_quotes (
        symbol, trade_date, close_price, prev_close, open_price, high_price, low_price,
        pct_chg, chg_amount, amplitude, volume_lot, amount_wan, turnover_rate,
        pe_ttm, pe_dynamic, pe_static, pb, total_mv, circ_mv, high_52w, low_52w,
        outer_bid, inner_bid, active_buy_ratio, big_order_buy_ratio, big_order_sell_ratio,
        raw_payload, updated_at
    ) VALUES (
        :symbol, :trade_date, :close_price, :prev_close, :open_price, :high_price, :low_price,
        :pct_chg, :chg_amount, :amplitude, :volume_lot, :amount_wan, :turnover_rate,
        :pe_ttm, :pe_dynamic, :pe_static, :pb, :total_mv, :circ_mv, :high_52w, :low_52w,
        :outer_bid, :inner_bid, :active_buy_ratio, :big_order_buy_ratio, :big_order_sell_ratio,
        :raw_payload, CURRENT_TIMESTAMP
    )
    ON CONFLICT(symbol, trade_date) DO UPDATE SET
        close_price = excluded.close_price,
        prev_close = excluded.prev_close,
        open_price = excluded.open_price,
        high_price = excluded.high_price,
        low_price = excluded.low_price,
        pct_chg = excluded.pct_chg,
        chg_amount = excluded.chg_amount,
        amplitude = excluded.amplitude,
        volume_lot = excluded.volume_lot,
        amount_wan = excluded.amount_wan,
        turnover_rate = excluded.turnover_rate,
        pe_ttm = COALESCE(excluded.pe_ttm, stock_daily_quotes.pe_ttm),
        pe_dynamic = COALESCE(excluded.pe_dynamic, stock_daily_quotes.pe_dynamic),
        pe_static = COALESCE(excluded.pe_static, stock_daily_quotes.pe_static),
        pb = COALESCE(excluded.pb, stock_daily_quotes.pb),
        total_mv = COALESCE(excluded.total_mv, stock_daily_quotes.total_mv),
        circ_mv = COALESCE(excluded.circ_mv, stock_daily_quotes.circ_mv),
        high_52w = COALESCE(excluded.high_52w, stock_daily_quotes.high_52w),
        low_52w = COALESCE(excluded.low_52w, stock_daily_quotes.low_52w),
        outer_bid = excluded.outer_bid,
        inner_bid = excluded.inner_bid,
        active_buy_ratio = COALESCE(excluded.active_buy_ratio, stock_daily_quotes.active_buy_ratio),
        big_order_buy_ratio = COALESCE(excluded.big_order_buy_ratio, stock_daily_quotes.big_order_buy_ratio),
        big_order_sell_ratio = COALESCE(excluded.big_order_sell_ratio, stock_daily_quotes.big_order_sell_ratio),
        raw_payload = excluded.raw_payload,
        updated_at = CURRENT_TIMESTAMP;
    """

    params = {
        "symbol": symbol,
        "trade_date": trade_date,
        "close_price": price,
        "prev_close": quote.get("prev_close"),
        "open_price": quote.get("open"),
        "high_price": quote.get("high"),
        "low_price": quote.get("low"),
        "pct_chg": quote.get("change_percent") or 0.0,
        "chg_amount": quote.get("change"),
        "amplitude": quote.get("amplitude"),
        "volume_lot": quote.get("volume_lot"),
        "amount_wan": quote.get("amount_wan"),
        "turnover_rate": quote.get("turnover_rate"),
        "pe_ttm": quote.get("pe_ttm"),
        "pe_dynamic": quote.get("pe_dynamic"),
        "pe_static": quote.get("pe_static"),
        "pb": quote.get("pb"),
        "total_mv": quote.get("total_mv"),
        "circ_mv": quote.get("circulating_mv"),
        "high_52w": quote.get("high_52w"),
        "low_52w": quote.get("low_52w"),
        "outer_bid": quote.get("outer_bid"),
        "inner_bid": quote.get("inner_bid"),
        "active_buy_ratio": quote.get("active_buy_ratio"),
        "big_order_buy_ratio": quote.get("buy_big_ratio"),
        "big_order_sell_ratio": quote.get("sell_big_ratio"),
        "raw_payload": json.dumps(quote, ensure_ascii=False),
    }

    with db_session(db_path) as conn:
        conn.execute(sql, params)


def get_latest_daily_quote(
    symbol: str,
    trade_date: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Retrieve the latest or specific date's quote from SQLite."""
    with db_session(db_path) as conn:
        if trade_date:
            row = conn.execute(
                """
                SELECT q.*, s.name, s.code, s.market, s.industry
                FROM stock_daily_quotes q
                LEFT JOIN stocks s ON q.symbol = s.symbol
                WHERE q.symbol = ? AND q.trade_date = ?
                """,
                (symbol, trade_date),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT q.*, s.name, s.code, s.market, s.industry
                FROM stock_daily_quotes q
                LEFT JOIN stocks s ON q.symbol = s.symbol
                WHERE q.symbol = ?
                ORDER BY q.trade_date DESC, q.updated_at DESC
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()

        if not row:
            return None
        return dict(row)


def upsert_kline_records(
    symbol: str,
    period: str,
    bars: list[dict[str, Any]],
    adjust_type: str = "qfq",
    db_path: Path | str | None = None,
) -> int:
    """Batch insert or update kline bars into SQLite."""
    if not bars:
        return 0

    sql = """
    INSERT INTO stock_kline_records (
        symbol, period, kline_date, adjust_type, open_price, close_price, high_price, low_price, volume, amount
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol, period, kline_date, adjust_type) DO UPDATE SET
        open_price = excluded.open_price,
        close_price = excluded.close_price,
        high_price = excluded.high_price,
        low_price = excluded.low_price,
        volume = excluded.volume,
        amount = excluded.amount;
    """
    rows = []
    for b in bars:
        d = b.get("date")
        if not d:
            continue
        rows.append((
            symbol,
            period,
            d,
            adjust_type,
            b.get("open") or 0.0,
            b.get("close") or 0.0,
            b.get("high") or 0.0,
            b.get("low") or 0.0,
            b.get("volume") or 0.0,
            b.get("amount"),
        ))

    with db_session(db_path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def get_kline_records(
    symbol: str,
    period: str = "day",
    count: int = 120,
    adjust_type: str = "qfq",
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical kline bars in ascending order from SQLite."""
    sql = """
    SELECT kline_date as date, open_price as open, close_price as close,
           high_price as high, low_price as low, volume, amount
    FROM stock_kline_records
    WHERE symbol = ? AND period = ? AND adjust_type = ?
    ORDER BY kline_date DESC
    LIMIT ?;
    """
    with db_session(db_path) as conn:
        rows = conn.execute(sql, (symbol, period, adjust_type, count)).fetchall()

    # Reverse to return ascending chronological order
    result = [dict(r) for r in reversed(rows)]
    return result


def get_kline_latest_date(
    symbol: str,
    period: str = "day",
    adjust_type: str = "qfq",
    db_path: Path | str | None = None,
) -> str | None:
    """Get the most recent kline_date stored in SQLite."""
    sql = """
    SELECT MAX(kline_date) as latest_date
    FROM stock_kline_records
    WHERE symbol = ? AND period = ? AND adjust_type = ?;
    """
    with db_session(db_path) as conn:
        row = conn.execute(sql, (symbol, period, adjust_type)).fetchone()
        return row["latest_date"] if row and row["latest_date"] else None


def record_financial_metric(
    symbol: str,
    report_period: str,
    metric_name: str,
    category: str = "cash_flow",
    metric_value: float | None = None,
    unit: str = "亿元",
    yoy_change: str = "",
    context_notes: str = "",
    source_task_id: str = "",
    db_path: Path | str | None = None,
) -> int:
    """Record a deep fundamental / calculation metric into SQLite."""
    sql = """
    INSERT INTO stock_financial_metrics (
        symbol, report_period, category, metric_name, metric_value, unit,
        yoy_change, context_notes, source_task_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    with db_session(db_path) as conn:
        cursor = conn.execute(
            sql,
            (
                symbol,
                report_period,
                category,
                metric_name,
                metric_value,
                unit,
                yoy_change,
                context_notes,
                source_task_id,
            ),
        )
        return cursor.lastrowid or 0


def query_financial_metrics(
    symbol: str,
    report_period: str = "",
    category: str = "",
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Query recorded financial facts for a stock."""
    conditions = ["symbol = ?"]
    params: list[Any] = [symbol]

    if report_period:
        conditions.append("report_period = ?")
        params.append(report_period)
    if category:
        conditions.append("category = ?")
        params.append(category)

    where_clause = " AND ".join(conditions)
    sql = f"""
    SELECT id, symbol, report_period, category, metric_name, metric_value,
           unit, yoy_change, context_notes, created_at
    FROM stock_financial_metrics
    WHERE {where_clause}
    ORDER BY report_period DESC, id DESC;
    """
    with db_session(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def manage_watchlist(
    action: str,
    symbol: str = "",
    target_buy_price: float | None = None,
    target_sell_price: float | None = None,
    cost_price: float | None = None,
    core_logic: str = "",
    alert_notes: str = "",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Manage the user's persistent watchlist across sessions."""
    act = action.lower().strip()
    with db_session(db_path) as conn:
        if act == "list":
            sql = """
            SELECT w.symbol, s.name, s.market, s.industry,
                   w.target_buy_price, w.target_sell_price, w.cost_price,
                   w.core_logic, w.alert_notes, w.added_at, w.updated_at,
                   q.close_price as latest_price, q.pct_chg, q.pe_ttm, q.total_mv
            FROM user_watchlist w
            LEFT JOIN stocks s ON w.symbol = s.symbol
            LEFT JOIN stock_daily_quotes q ON w.symbol = q.symbol
                 AND q.trade_date = (SELECT MAX(trade_date) FROM stock_daily_quotes WHERE symbol = w.symbol)
            ORDER BY w.updated_at DESC;
            """
            rows = conn.execute(sql).fetchall()
            return {"action": "list", "total": len(rows), "items": [dict(r) for r in rows]}

        if not symbol:
            raise ValueError("symbol is required for action: " + act)

        if act in ("add", "update"):
            sql = """
            INSERT INTO user_watchlist (
                symbol, target_buy_price, target_sell_price, cost_price, core_logic, alert_notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                target_buy_price = COALESCE(excluded.target_buy_price, user_watchlist.target_buy_price),
                target_sell_price = COALESCE(excluded.target_sell_price, user_watchlist.target_sell_price),
                cost_price = COALESCE(excluded.cost_price, user_watchlist.cost_price),
                core_logic = COALESCE(NULLIF(excluded.core_logic, ''), user_watchlist.core_logic),
                alert_notes = COALESCE(NULLIF(excluded.alert_notes, ''), user_watchlist.alert_notes),
                updated_at = CURRENT_TIMESTAMP;
            """
            conn.execute(sql, (symbol, target_buy_price, target_sell_price, cost_price, core_logic, alert_notes))
            return {"action": act, "symbol": symbol, "success": True}

        if act == "remove":
            conn.execute("DELETE FROM user_watchlist WHERE symbol = ?;", (symbol,))
            return {"action": "remove", "symbol": symbol, "success": True}

        raise ValueError(f"Unknown action {action!r}. Supported: 'list', 'add', 'update', 'remove'.")


def get_finance_overview(
    market: str = "ALL",
    order_by: str = "updated_at",
    limit: int = 50,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve cross-session overview of saved stocks with latest valuation."""
    valid_orders = {
        "updated_at": "q.updated_at DESC",
        "pe_ttm": "q.pe_ttm ASC",
        "total_mv": "q.total_mv DESC",
        "pct_chg": "q.pct_chg DESC",
    }
    order_clause = valid_orders.get(order_by, "q.updated_at DESC")

    where_clause = ""
    params: list[Any] = []
    if market.upper() != "ALL":
        where_clause = "WHERE s.market = ?"
        params.append(market.upper())

    sql = f"""
    SELECT s.symbol, s.name, s.code, s.market, s.industry,
           q.trade_date, q.close_price, q.pct_chg, q.pe_ttm, q.pb,
           q.total_mv, q.circ_mv, q.turnover_rate, q.high_52w, q.low_52w,
           q.big_order_buy_ratio, q.updated_at
    FROM stocks s
    JOIN stock_daily_quotes q ON s.symbol = q.symbol
         AND q.trade_date = (SELECT MAX(trade_date) FROM stock_daily_quotes WHERE symbol = s.symbol)
    {where_clause}
    ORDER BY {order_clause}
    LIMIT ?;
    """
    params.append(max(1, min(limit, 200)))

    with db_session(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Agent Autonomous SQLite Toolkit with Safety Guardrails
# ---------------------------------------------------------------------------

def sqlite_show_tables(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """查看数据库中当前存在的所有数据表名称、类别（预定义/自定义）及大致记录数。

    Returns:
        包含表名、表类型（system_predefined 或 agent_created）、记录数的数据表列表。
    """
    with db_session(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
        ).fetchall()

        results = []
        for r in rows:
            table_name = r["name"]
            is_predefined = table_name in PROTECTED_TABLES
            try:
                cnt = conn.execute(f"SELECT COUNT(*) as c FROM `{table_name}`").fetchone()["c"]
            except Exception:
                cnt = None
            results.append({
                "table_name": table_name,
                "type": "system_predefined" if is_predefined else "agent_created",
                "row_count": cnt,
            })
        return results


def sqlite_describe_table(table_name: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """获取指定数据表的列结构定义（字段名、数据类型、是否可为空、主键标志）与现有索引。

    Args:
        table_name: 要查看的表名。

    Returns:
        包含 columns 和 indexes 的表结构描述字典。
    """
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "", table_name.strip())
    if not clean_name:
        raise ValueError("Invalid table name")

    with db_session(db_path) as conn:
        col_rows = conn.execute(f"PRAGMA table_info(`{clean_name}`);").fetchall()
        if not col_rows:
            return {"error": f"Table '{clean_name}' does not exist."}

        cols = []
        for c in col_rows:
            cols.append({
                "name": c["name"],
                "type": c["type"],
                "notnull": bool(c["notnull"]),
                "default_value": c["dflt_value"],
                "primary_key": bool(c["pk"]),
            })

        idx_rows = conn.execute(f"PRAGMA index_list(`{clean_name}`);").fetchall()
        indexes = [r["name"] for r in idx_rows]

        return {
            "table_name": clean_name,
            "type": "system_predefined" if clean_name in PROTECTED_TABLES else "agent_created",
            "columns": cols,
            "indexes": indexes,
        }


def sqlite_query(
    sql: str,
    params: Sequence[Any] | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """在金融数据库中执行只读 SQL 查询（支持 SELECT、JOIN、GROUP BY、HAVING 等复杂聚合分析）。

    Args:
        sql: 纯只读 SELECT 查询语句。严禁传入修改性或多语句注入。
        params: 参数化列表（可选）。

    Returns:
        查询结果字典数组。
    """
    cleaned = sql.strip()
    # Strip leading SQL comments
    cleaned = re.sub(r"^/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^--.*?\n", "", cleaned).strip()

    first_word = cleaned.split()[0].upper() if cleaned else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        raise PermissionError(
            f"sqlite_query only permits read-only SELECT or WITH statements, got: {first_word!r}"
        )

    # Disallow dangerous multi-statements
    if ";" in cleaned:
        statements = [s.strip() for s in cleaned.split(";") if s.strip()]
        for s in statements:
            s_word = s.split()[0].upper() if s else ""
            if s_word not in ("SELECT", "WITH", "EXPLAIN"):
                raise PermissionError("Disallowed non-SELECT statement in multi-query")

    with db_session(db_path) as conn:
        cursor = conn.execute(cleaned, params or ())
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def sqlite_execute(
    sql: str,
    params: Sequence[Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """在数据库中受控执行 DDL（如 CREATE TABLE IF NOT EXISTS、CREATE INDEX）或 DML（INSERT、UPDATE、DELETE）操作。

    严密安全护栏：
    - 严禁对系统 6 大预定义核心表执行 DROP TABLE 或 ALTER TABLE DROP；
    - 严禁执行 ATTACH/DETACH DATABASE、VACUUM、PRAGMA write 等越界高危指令。

    Args:
        sql: 要执行的 SQL 语句。
        params: 参数化列表（可选）。

    Returns:
        包含 success、rows_affected、last_insert_id 及 message 的结果字典。
    """
    cleaned = sql.strip()
    upper_sql = cleaned.upper()

    # Disallow forbidden operations
    forbidden_tokens = ["ATTACH", "DETACH", "VACUUM", "PRAGMA"]
    for token in forbidden_tokens:
        if re.search(rf"\b{token}\b", upper_sql):
            raise PermissionError(f"Execution of SQL with '{token}' keyword is strictly forbidden.")

    # Protect system core tables from being dropped or altered
    drop_match = re.search(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([`\"\']?)([a-zA-Z0-9_]+)\1", upper_sql)
    if drop_match:
        target_tbl = drop_match.group(2).lower()
        if target_tbl in PROTECTED_TABLES:
            raise PermissionError(
                f"Cannot drop protected system core table '{target_tbl}'. This table is reserved for system operations."
            )

    alter_drop_match = re.search(r"\bALTER\s+TABLE\s+([`\"\']?)([a-zA-Z0-9_]+)\1\s+DROP", upper_sql)
    if alter_drop_match:
        target_tbl = alter_drop_match.group(2).lower()
        if target_tbl in PROTECTED_TABLES:
            raise PermissionError(
                f"Cannot alter drop column on protected system table '{target_tbl}'."
            )

    with db_session(db_path) as conn:
        cursor = conn.execute(cleaned, params or ())
        return {
            "success": True,
            "rows_affected": cursor.rowcount,
            "last_insert_id": cursor.lastrowid,
            "message": "Executed successfully",
        }
