"""
Tencent Stock Native Toolkit & Financial Persistence Bridge.
============================================================

Provides native Python FunctionTools for high-performance, token-free,
zero-authentication financial market queries (quotes, k-lines, minutes,
handicap, index overview, and code search) backed by Tencent Finance's
public HTTP endpoints, with automatic transparent persistence into a local
SQLite WAL database (`data/finance.db`).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Sequence

import httpx

from server.service import finance_db

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache to prevent repeated fetches within a single turn
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, Any]] = {}


def _get_cache(key: str) -> Any | None:
    now = time.time()
    if key in _CACHE:
        expire_at, data = _CACHE[key]
        if now < expire_at:
            return data
        del _CACHE[key]
    return None


def _set_cache(key: str, data: Any, ttl_seconds: float) -> None:
    _CACHE[key] = (time.time() + ttl_seconds, data)


def _to_float(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def is_market_trading_hours() -> bool:
    """Check if A-share market is currently in trading hours (Mon-Fri 09:15-15:05)."""
    now = datetime.now()
    if now.weekday() >= 5:  # Saturday, Sunday
        return False
    minutes = now.hour * 60 + now.minute
    return 555 <= minutes <= 905  # 09:15 to 15:05


def normalize_symbol(symbol: str) -> str:
    """Normalize user input stock codes to standard prefixed format (e.g. 'sh600519').

    Accepts:
    - '600519' -> 'sh600519'
    - '000001' -> 'sz000001'
    - 'sh600519', 'SZ000858' -> lowercased 'sh600519', 'sz000858'
    - '600519.SH', '000858.SZ' -> 'sh600519', 'sz000858'
    - '00700' or 'hk00700' -> 'hk00700'
    - 'AAPL' -> 'usaapl'
    """
    raw = str(symbol).strip()
    s = raw.lower()

    # Strip exchange suffixes like .sh, .sz, .hk, .us
    for suffix in (".sh", ".sz", ".hk", ".us", ".oq", ".n"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]

    # Already prefixed
    if re.match(r"^(sh|sz|hk|us)", s, re.IGNORECASE):
        return s.lower()

    # Pure alphabetic (e.g. AAPL, TSLA) -> US stock
    if s.isalpha():
        return f"us{s.lower()}"

    digits = re.sub(r"\D", "", s)
    if len(digits) == 6:
        # Shanghai: 60xxxx, 688xxx (STAR), 90xxxx (B-shares), 11xxxx/13xxxx (Bonds)
        if digits.startswith(("60", "68", "90", "11", "13")):
            return f"sh{digits}"
        # Shenzhen: 00xxxx, 30xxxx (ChiNext), 20xxxx (B-shares)
        if digits.startswith(("00", "30", "20")):
            return f"sz{digits}"
        # Beijing / default fallback
        return f"sh{digits}"
    if len(digits) == 5:
        # Hong Kong: 5-digit code
        return f"hk{digits.zfill(5)}"

    return s.lower()


def _http_get(url: str, params: dict[str, Any] | None = None, encoding: str = "gbk") -> str:
    """Execute HTTP GET with standard headers."""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://gu.qq.com/",
        "Accept": "*/*",
    }
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        raw_bytes = resp.content
        try:
            return raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return raw_bytes.decode("utf-8", errors="ignore")


def _parse_qt_response(text: str) -> dict[str, list[str]]:
    """Parse Tencent qt format `v_sh600519="1~贵州茅台~600519~...";`."""
    result: dict[str, list[str]] = {}
    pattern = re.compile(r'v_([a-zA-Z0-9_]+)="([^"]*)"')
    for match in pattern.finditer(text):
        sym, payload = match.group(1), match.group(2)
        if not payload:
            result[sym] = []
            continue
        result[sym] = payload.split("~")
    return result


# ---------------------------------------------------------------------------
# Public Tools
# ---------------------------------------------------------------------------

def stock_search(keyword: str) -> list[dict[str, Any]]:
    """搜索股票代码、公司名称与证券市场分类。

    Args:
        keyword: 股票中文名称（如'贵州茅台'、'伊利'）、拼音简称（如'gzmt'、'pa'）或数字代码（如'600519'）。

    Returns:
        匹配到的证券标的列表，包含标准代码(symbol)、名称(name)、市场(market)及类别。
    """
    kw = keyword.strip()
    if not kw:
        return []

    cache_key = f"search:{kw}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"https://smartbox.gtimg.cn/s3/?q={kw}&t=all"
    try:
        text = _http_get(url, encoding="utf-8")
        match = re.search(r'v_hint="([^"]*)"', text)
        if not match or match.group(1) == "N":
            return []

        items = []
        raw_items = match.group(1).split("^")
        for item in raw_items:
            parts = item.split("~")
            if len(parts) >= 3:
                market_prefix, code, raw_name = parts[0], parts[1], parts[2]
                try:
                    name = json.loads(f'"{raw_name}"')
                except Exception:
                    name = raw_name
                symbol = f"{market_prefix}{code}"
                pinyin = parts[3] if len(parts) > 3 else ""
                sec_type = parts[4] if len(parts) > 4 else "GP"
                items.append({
                    "symbol": symbol,
                    "code": code,
                    "name": name,
                    "pinyin": pinyin,
                    "type": sec_type,
                })

                # Transparent persistence into stocks table
                try:
                    finance_db.upsert_stock(
                        symbol=symbol,
                        name=name,
                        code=code,
                        pinyin=pinyin,
                        sec_type=sec_type,
                    )
                except Exception:
                    pass

        _set_cache(cache_key, items, ttl_seconds=300)
        return items
    except Exception as e:
        logger.warning("stock_search failed for %r: %s", kw, e)
        return []


def stock_quote(symbol: str) -> dict[str, Any]:
    """获取单只股票的完整实时行情、估值指标与量价数据（内置透明 SQLite 本地缓存）。

    Args:
        symbol: 股票代码，如 'sh600519', 'sz000858', 'hk00700', 'usAAPL'（亦支持纯代码如'600519'自动转换）。

    Returns:
        包含当前价格、涨跌幅、市盈率(PE)、市净率(PB)、总市值、流通市值、换手率、外盘、内盘、大单买卖比例等完整指标的字典。
    """
    sym = normalize_symbol(symbol)
    cache_key = f"quote:{sym}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    # 1. Transparent Cache-Aside from SQLite
    db_cached = None
    try:
        db_cached = finance_db.get_latest_daily_quote(sym)
    except Exception as e:
        logger.warning("Error reading daily quote from finance_db: %s", e)

    today_str = datetime.now().strftime("%Y-%m-%d")
    is_trading = is_market_trading_hours()

    if db_cached and db_cached.get("close_price") is not None:
        db_trade_date = str(db_cached.get("trade_date") or "")
        updated_at_str = str(db_cached.get("updated_at") or "")

        # A: Non-trading hours or weekend: If we already have quote, serve from DB
        if not is_trading:
            if db_trade_date == today_str or datetime.now().weekday() >= 5 or db_trade_date != "":
                if db_cached.get("raw_payload"):
                    try:
                        payload = json.loads(db_cached["raw_payload"])
                        payload["_source"] = "sqlite_cache"
                        _set_cache(cache_key, payload, ttl_seconds=180)
                        return payload
                    except Exception:
                        pass
        else:
            # B: Trading hours: serve from DB if within 3 minutes TTL (180s)
            try:
                # Parse updated_at
                clean_time = updated_at_str.split(".")[0].replace("T", " ")
                up_dt = datetime.fromisoformat(clean_time)
                if (datetime.now() - up_dt).total_seconds() < 180:
                    if db_cached.get("raw_payload"):
                        payload = json.loads(db_cached["raw_payload"])
                        payload["_source"] = "sqlite_cache"
                        _set_cache(cache_key, payload, ttl_seconds=180)
                        return payload
            except Exception:
                pass

    # 2. Cache miss or expired: fetch from Tencent API
    url = f"http://qt.gtimg.cn/q={sym}"
    try:
        text = _http_get(url, encoding="gbk")
        parsed = _parse_qt_response(text)
        fields = parsed.get(sym)
        if not fields:
            for k, v in parsed.items():
                if k.lower() == sym.lower() and v:
                    fields = v
                    break

        if not fields or len(fields) < 30:
            if db_cached and db_cached.get("raw_payload"):
                try:
                    payload = json.loads(db_cached["raw_payload"])
                    payload["_source"] = "sqlite_cache_fallback"
                    return payload
                except Exception:
                    pass
            return {"error": f"未查询到标的 {sym} 的行情数据", "symbol": sym}

        quote_data = {
            "symbol": sym,
            "name": fields[1],
            "code": fields[2],
            "price": _to_float(fields[3]),
            "prev_close": _to_float(fields[4]),
            "open": _to_float(fields[5]),
            "volume_lot": _to_int(fields[6]),
            "outer_bid": _to_int(fields[7]),
            "inner_bid": _to_int(fields[8]),
            "bid_1": {"price": _to_float(fields[9]), "volume": _to_int(fields[10])},
            "ask_1": {"price": _to_float(fields[19]), "volume": _to_int(fields[20])},
            "timestamp": fields[30] if len(fields) > 30 else "",
            "change": _to_float(fields[31]) if len(fields) > 31 else None,
            "change_percent": _to_float(fields[32]) if len(fields) > 32 else None,
            "high": _to_float(fields[33]) if len(fields) > 33 else None,
            "low": _to_float(fields[34]) if len(fields) > 34 else None,
            "amount_wan": _to_float(fields[37]) if len(fields) > 37 else None,
            "turnover_rate": _to_float(fields[38]) if len(fields) > 38 else None,
            "pe_dynamic": _to_float(fields[39]) if len(fields) > 39 else None,
            "amplitude": _to_float(fields[43]) if len(fields) > 43 else None,
            "circulating_mv": _to_float(fields[44]) if len(fields) > 44 else None,
            "total_mv": _to_float(fields[45]) if len(fields) > 45 else None,
            "pb": _to_float(fields[46]) if len(fields) > 46 else None,
            "limit_up": _to_float(fields[47]) if len(fields) > 47 else None,
            "limit_down": _to_float(fields[48]) if len(fields) > 48 else None,
            "pe_ttm": _to_float(fields[53]) if len(fields) > 53 else None,
            "pe_static": _to_float(fields[54]) if len(fields) > 54 else None,
            "high_52w": _to_float(fields[67]) if len(fields) > 67 else None,
            "low_52w": _to_float(fields[68]) if len(fields) > 68 else None,
        }

        # Active buy ratio
        if quote_data["outer_bid"] is not None and quote_data["inner_bid"] is not None:
            total_trades = quote_data["outer_bid"] + quote_data["inner_bid"]
            if total_trades > 0:
                quote_data["active_buy_ratio"] = round(quote_data["outer_bid"] / total_trades, 4)

        # Supplement with handicap big-order data
        try:
            pk = stock_handicap(sym)
            if "error" not in pk:
                quote_data["buy_big_ratio"] = pk.get("buy_big_ratio")
                quote_data["sell_big_ratio"] = pk.get("sell_big_ratio")
        except Exception:
            pass

        # 3. Transparent Write-Through to SQLite
        try:
            finance_db.upsert_daily_quote(quote_data)
        except Exception as e:
            logger.warning("Failed to persist quote to finance_db: %s", e)

        quote_data["_source"] = "tencent_api"
        ttl = 180 if is_trading else 3600
        _set_cache(cache_key, quote_data, ttl_seconds=ttl)
        return quote_data
    except Exception as e:
        logger.error("stock_quote error for %s: %s", sym, e)
        # Fallback to local DB if available
        if db_cached and db_cached.get("raw_payload"):
            try:
                payload = json.loads(db_cached["raw_payload"])
                payload["_source"] = "sqlite_cache_fallback"
                return payload
            except Exception:
                pass
        return {"error": str(e), "symbol": sym}


def stock_batch_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    """批量获取多只股票的简要实时行情（现价、涨跌幅、成交额、总市值），用于同行横向估值对比。

    Args:
        symbols: 股票代码列表，如 ['sh600519', 'sz000858', 'sz000568']，单次建议不超过 50 只。

    Returns:
        股票简要行情对比列表。
    """
    if not symbols:
        return []

    norm_symbols = [normalize_symbol(s) for s in symbols][:50]
    brief_keys = [f"s_{s}" for s in norm_symbols]
    url = "http://qt.gtimg.cn/q=" + ",".join(brief_keys)

    try:
        text = _http_get(url, encoding="gbk")
        parsed = _parse_qt_response(text)
        results = []
        for sym in norm_symbols:
            key = f"s_{sym}"
            fields = parsed.get(key)
            if not fields:
                for k, v in parsed.items():
                    if k.lower() == key.lower():
                        fields = v
                        break
            if fields and len(fields) >= 8:
                results.append({
                    "symbol": sym,
                    "name": fields[1],
                    "code": fields[2],
                    "price": _to_float(fields[3]),
                    "change": _to_float(fields[4]),
                    "change_percent": _to_float(fields[5]),
                    "volume_lot": _to_int(fields[6]),
                    "amount_wan": _to_float(fields[7]),
                    "total_mv": _to_float(fields[9]) if len(fields) > 9 else None,
                })
        return results
    except Exception as e:
        logger.error("stock_batch_quotes error: %s", e)
        return []


def stock_kline(
    symbol: str,
    period: str = "day",
    count: int = 120,
    fq: str = "qfq",
) -> list[dict[str, Any]]:
    """获取股票历史 K 线序列，用于技术分析、均线系统计算与历史走势复盘（内置 SQLite 增量存储）。

    Args:
        symbol: 股票代码，如 'sh600519'。
        period: K 线周期，可选 'day'(日K), 'week'(周K), 'month'(月K), 'm5', 'm15', 'm30', 'm60'。默认为 'day'。
        count: 获取的根数，默认为 120 根，上限 640 根。
        fq: 复权方式，可选 'qfq'(前复权，推荐走势分析使用), 'hfq'(后复权), 'none'(不复权)。默认为 'qfq'。

    Returns:
        按时间升序排列的历史 K 线数组，每项包含 date, open, close, high, low, volume, amount。
    """
    sym = normalize_symbol(symbol)
    valid_count = max(1, min(int(count), 640))
    cache_key = f"kline:{sym}:{period}:{valid_count}:{fq}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    # Check local SQLite database first
    local_bars = []
    try:
        local_bars = finance_db.get_kline_records(sym, period=period, count=valid_count, adjust_type=fq)
        latest_date = finance_db.get_kline_latest_date(sym, period=period, adjust_type=fq)
        today_str = datetime.now().strftime("%Y-%m-%d")

        # If we have enough bars and the latest date is today (or market closed/weekend)
        if len(local_bars) >= valid_count and latest_date:
            if latest_date == today_str or not is_market_trading_hours():
                _set_cache(cache_key, local_bars, ttl_seconds=300)
                return local_bars
    except Exception as e:
        logger.warning("Error reading klines from finance_db: %s", e)

    url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{sym},{period},,,{valid_count},{fq}"}
    try:
        text = _http_get(url, params=params, encoding="utf-8")
        if text.startswith("_var="):
            text = text.split("=", 1)[1]
        data = json.loads(text)
        if data.get("code") != 0:
            return local_bars

        payload = data.get("data", {}).get(sym, {})
        key = f"qfq{period}" if fq == "qfq" and period in ("day", "week", "month") else period
        raw_bars = payload.get(key) or payload.get(period) or []

        bars = []
        for bar in raw_bars:
            if len(bar) >= 6:
                bars.append({
                    "date": bar[0],
                    "open": _to_float(bar[1]),
                    "close": _to_float(bar[2]),
                    "high": _to_float(bar[3]),
                    "low": _to_float(bar[4]),
                    "volume": _to_float(bar[5]),
                    "amount": _to_float(bar[6]) if len(bar) > 6 else None,
                })

        # Save to SQLite
        if bars:
            try:
                finance_db.upsert_kline_records(sym, period=period, bars=bars, adjust_type=fq)
            except Exception as e:
                logger.warning("Failed to persist klines to finance_db: %s", e)

        _set_cache(cache_key, bars, ttl_seconds=180)
        return bars
    except Exception as e:
        logger.error("stock_kline error for %s: %s", sym, e)
        return local_bars


def stock_minute(symbol: str, days: int = 1) -> list[dict[str, Any]]:
    """获取股票当日（或近5日）逐分钟的分时走势数据与分时均价线。

    Args:
        symbol: 股票代码，如 'sh600519'。
        days: 1 表示当日分时明细，5 表示近 5 日分时明细。默认 1。

    Returns:
        逐分钟的数据点列表：time (HH:MM), price (当前价), volume (当前累计成交量手), avg_price (分时均价)。
    """
    sym = normalize_symbol(symbol)
    cache_key = f"minute:{sym}:{days}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    url = "http://web.ifzq.gtimg.cn/appstock/app/minute/query"
    param = sym if days == 1 else f"{sym},{days}day"
    params = {"code": sym, "param": param} if days != 1 else {"code": sym}

    try:
        text = _http_get(url, params=params, encoding="utf-8")
        if text.startswith("_var="):
            text = text.split("=", 1)[1]
        data = json.loads(text)
        if data.get("code") != 0:
            return []

        inner = data.get("data", {}).get(sym, {})
        raw_rows = inner.get("data", {}).get("data", [])
        results = []
        for line in raw_rows:
            parts = line.split()
            if len(parts) >= 4:
                hhmm, price, volume, avg = parts[0], parts[1], parts[2], parts[3]
                formatted_time = f"{hhmm[:2]}:{hhmm[2:]}" if len(hhmm) == 4 else hhmm
                results.append({
                    "time": formatted_time,
                    "price": _to_float(price),
                    "volume": _to_int(volume),
                    "avg_price": _to_float(avg),
                })
        _set_cache(cache_key, results, ttl_seconds=10)
        return results
    except Exception as e:
        logger.error("stock_minute error for %s: %s", sym, e)
        return []


def stock_handicap(symbol: str) -> dict[str, Any]:
    """获取买卖盘口大单与小单的分布比例，辅助判断主力博弈意愿与筹码流向。

    Args:
        symbol: 股票代码，如 'sh600519'。

    Returns:
        包含大单买入比、小单买入比、大单卖出比、小单卖出比（0~1的小数）。
    """
    sym = normalize_symbol(symbol)
    url = f"http://qt.gtimg.cn/q=s_pk{sym}"
    try:
        text = _http_get(url, encoding="gbk")
        parsed = _parse_qt_response(text)
        for k, v in parsed.items():
            if v and k.lower().endswith(sym.lower()):
                vals = [_to_float(x) for x in v]
                vals = vals + [None] * (4 - len(vals))
                return {
                    "symbol": sym,
                    "buy_big_ratio": vals[0],
                    "buy_small_ratio": vals[1],
                    "sell_big_ratio": vals[2],
                    "sell_small_ratio": vals[3],
                }
        return {"error": "未获取到盘口大单数据", "symbol": sym}
    except Exception as e:
        return {"error": str(e), "symbol": sym}


def market_index_overview() -> list[dict[str, Any]]:
    """获取全市场大盘核心基准指数（上证指数、深证成指、创业板指、科创50、沪深300、恒生指数）的实时点位与涨跌幅快照。

    Returns:
        各大核心指数的最新点位、涨跌额、涨跌幅、成交额列表，用于评估大盘宏观市场环境 (Beta)。
    """
    cache_key = "market_index_overview"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    indices = [
        "s_sh000001",  # 上证指数
        "s_sz399001",  # 深证成指
        "s_sz399006",  # 创业板指
        "s_sh000688",  # 科创50
        "s_sh000300",  # 沪深300
        "s_hkHSI",     # 恒生指数
    ]
    url = "http://qt.gtimg.cn/q=" + ",".join(indices)
    try:
        text = _http_get(url, encoding="gbk")
        parsed = _parse_qt_response(text)
        results = []
        for code in indices:
            fields = parsed.get(code)
            if not fields:
                for k, v in parsed.items():
                    if k.lower() == code.lower():
                        fields = v
                        break
            if fields and len(fields) >= 8:
                results.append({
                    "symbol": code.replace("s_", ""),
                    "name": fields[1],
                    "point": _to_float(fields[3]),
                    "change": _to_float(fields[4]),
                    "change_percent": _to_float(fields[5]),
                    "volume_lot": _to_int(fields[6]),
                    "amount_wan": _to_float(fields[7]),
                })
        _set_cache(cache_key, results, ttl_seconds=10)
        return results
    except Exception as e:
        logger.error("market_index_overview error: %s", e)
        return []


# ---------------------------------------------------------------------------
# High-Level Cross-Session Persistence & Autonomous SQLite Tools
# ---------------------------------------------------------------------------

def finance_overview(
    market: str = "ALL",
    order_by: str = "updated_at",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """查看本地数据库中已持久化沉淀的所有股票列表及其最新估值（现价、PE TTM、PB、总市值等）。

    Args:
        market: 市场筛选，可选 'ALL', 'SH', 'SZ', 'HK', 'US'。默认 'ALL'。
        order_by: 排序字段，可选 'updated_at'(最新更新), 'pe_ttm'(市盈率由低到高), 'total_mv'(市值由大到小), 'pct_chg'(涨跌幅)。默认 'updated_at'。
        limit: 返回记录数量限制，默认 50。

    Returns:
        包含已持久化股票估值对比的列表。
    """
    return finance_db.get_finance_overview(market=market, order_by=order_by, limit=limit)


def finance_watchlist(
    action: str,
    symbol: str = "",
    target_buy_price: float | None = None,
    target_sell_price: float | None = None,
    cost_price: float | None = None,
    core_logic: str = "",
    alert_notes: str = "",
) -> dict[str, Any]:
    """管理跨会话持久化的用户自选与核心关注股票池（支持增删改查、买卖心理价与逻辑跟踪）。

    Args:
        action: 操作类别，可选 'list'(查看自选池), 'add'(添加或更新关注), 'update'(更新目标价/逻辑), 'remove'(移除关注)。
        symbol: 股票代码，如 'sh600887'（查看自选池 list 时可留空）。
        target_buy_price: 目标估值买入心理价位（可选）。
        target_sell_price: 目标估值止盈卖出价位（可选）。
        cost_price: 实际持仓成本价（可选）。
        core_logic: 核心投资逻辑或跟踪催化剂（如'原奶周期触底，股息率4.5%'）。
        alert_notes: 核心风险警示点（如'需跟踪Q3常温奶去库存进度'）。

    Returns:
        自选池操作结果或自选标的详细信息列表。
    """
    norm_sym = normalize_symbol(symbol) if symbol else ""
    return finance_db.manage_watchlist(
        action=action,
        symbol=norm_sym,
        target_buy_price=target_buy_price,
        target_sell_price=target_sell_price,
        cost_price=cost_price,
        core_logic=core_logic,
        alert_notes=alert_notes,
    )


def finance_record_metric(
    symbol: str,
    report_period: str,
    metric_name: str,
    category: str = "cash_flow",
    metric_value: float | None = None,
    unit: str = "亿元",
    yoy_change: str = "",
    context_notes: str = "",
) -> dict[str, Any]:
    """记录深度财务测算事实（如经营活动现金流、销售费用率、回购上限等），使其跨会话永久可查。

    Args:
        symbol: 股票代码，如 'sh600887'。
        report_period: 报告期，如 '2026H1', '2025FY', '2026Q2'。
        metric_name: 指标名称，如 '经营活动现金流净额', '销售费用率', '回购计划上限'。
        category: 指标分类，可选 'cash_flow'(现金流), 'profitability'(盈利能力), 'balance_sheet'(负债与资本), 'shareholder'(分红回购)。默认 'cash_flow'。
        metric_value: 数值（如 97.59, 17.77, 39.53）。
        unit: 单位（如 '亿元', '%', '元/股'）。默认 '亿元'。
        yoy_change: 同比变动幅度（如 '+229%', '-1.48%'）。
        context_notes: 测算背景与推导备注（如'现金/归母 = 1.69，单季经营现金流60亿'）。

    Returns:
        包含成功状态与新记录 ID 的字典。
    """
    norm_sym = normalize_symbol(symbol)
    rec_id = finance_db.record_financial_metric(
        symbol=norm_sym,
        report_period=report_period,
        category=category,
        metric_name=metric_name,
        metric_value=metric_value,
        unit=unit,
        yoy_change=yoy_change,
        context_notes=context_notes,
    )
    return {"success": True, "id": rec_id, "symbol": norm_sym, "metric_name": metric_name}


def sqlite_show_tables() -> list[dict[str, Any]]:
    """查看当前本地金融数据库中现存的所有数据表名、表类别（系统预定义/Agent自主创建）及记录行数。

    Returns:
        包含数据表名、类型及行数的数据表列表。
    """
    return finance_db.sqlite_show_tables()


def sqlite_describe_table(table_name: str) -> dict[str, Any]:
    """查看指定数据表的列结构定义（列名、数据类型、主键约束等）与现有索引，便于编写精准 SQL。

    Args:
        table_name: 要自省的表名，如 'stocks', 'stock_daily_quotes', 或自主创建的表。

    Returns:
        表结构元数据描述。
    """
    return finance_db.sqlite_describe_table(table_name=table_name)


def sqlite_query(sql: str) -> list[dict[str, Any]]:
    """在本地金融数据库中执行只读 SQL SELECT 查询（支持多表关联 JOIN、GROUP BY 聚合、条件过滤）。

    注意：本工具仅允许只读 SELECT 语句。若需自主建表或插入数据，请使用 sqlite_execute。

    Args:
        sql: 纯只读 SELECT 查询语句。

    Returns:
        以字典列表形式返回查询结果集。
    """
    return finance_db.sqlite_query(sql=sql)


def sqlite_execute(sql: str) -> dict[str, Any]:
    """在数据库中受控执行 DDL（如自主创建新表 CREATE TABLE IF NOT EXISTS、创建索引）或 DML（INSERT、UPDATE）语句。

    安全护栏说明：
    - 严禁对系统预定义核心表（stocks, stock_daily_quotes 等）执行 DROP TABLE；
    - 严禁执行 ATTACH/DETACH DATABASE、VACUUM、PRAGMA 等高危越界指令。

    Args:
        sql: 要执行的 DDL 或 DML SQL 语句。

    Returns:
        包含 success、rows_affected、last_insert_id 的结果字典。
    """
    return finance_db.sqlite_execute(sql=sql)
