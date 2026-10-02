"""
The precision calculator tool.

CLAUDE.md's rule for the stock-analysis phase — "严禁心算" — is
enforced here from day one: the model is never allowed to add, multiply,
or otherwise compute a numeric answer by itself. Every arithmetic request
must go through this tool, which evaluates with Python's own numeric
types rather than an LLM's approximate token-level "mental math".

The evaluator is a restricted AST walker, not `eval()`, so the tool
cannot be turned into an arbitrary-code-execution primitive via a
crafted expression. It supports basic arithmetic operators, list/tuple
literals, and a strict whitelist of math, statistical, and financial
functions ported from the stock analysis calculator skill.
"""
from __future__ import annotations

import ast
import json
import math
import operator
from typing import Any, Sequence, Union

import numpy as np

Number = Union[int, float]


class CalculatorError(Exception):
    """计算器输入错误或计算失败时抛此异常，模型应根据提示调整参数重试。"""


# =============================================================================
# 辅助函数
# =============================================================================

def _num(x: Any) -> float:
    """转换为 float，失败抛出 CalculatorError。"""
    if isinstance(x, bool):
        raise CalculatorError(f"布尔值不是合法数值: {x!r}")
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x)
        except ValueError:
            raise CalculatorError(f"无法转换为数值: {x!r}")
    raise CalculatorError(f"不支持的数值类型: {type(x).__name__}")


def _to_array(values: Any, name: str) -> np.ndarray:
    """转 ndarray，空序列或类型错误抛出 CalculatorError。"""
    if values is None:
        raise CalculatorError(f"{name}: 输入不能为 None")
    if isinstance(values, np.ndarray):
        arr = values.astype(float)
    elif isinstance(values, (list, tuple)):
        if len(values) == 0:
            raise CalculatorError(f"{name}: 输入不能为空")
        try:
            arr = np.array([_num(v) for v in values], dtype=float)
        except CalculatorError as e:
            raise CalculatorError(f"{name}: {e}")
    else:
        raise CalculatorError(f"{name}: 必须是 list/tuple/ndarray，得到 {type(values).__name__}")
    if arr.size == 0:
        raise CalculatorError(f"{name}: 输入不能为空")
    return arr


# =============================================================================
# Calculator 类 — 静态金融、统计与数学计算方法
# =============================================================================

class Calculator:
    """通用金融与统计计算器，所有方法无状态、可独立调用。"""

    # 一、基础四则
    @staticmethod
    def add(a: Number, b: Number) -> Number:
        """a + b"""
        return _num(a) + _num(b)

    @staticmethod
    def sub(a: Number, b: Number) -> Number:
        """a - b"""
        return _num(a) - _num(b)

    @staticmethod
    def mul(a: Number, b: Number) -> Number:
        """a × b"""
        return _num(a) * _num(b)

    @staticmethod
    def div(a: Number, b: Number) -> Number:
        """a / b，除零抛 CalculatorError"""
        b = _num(b)
        if b == 0:
            raise CalculatorError("除数不能为零")
        return _num(a) / b

    # 二、百分比与变化
    @staticmethod
    def pct(part: Number, total: Number) -> float:
        """part 占 total 的百分比。例: pct(25, 100) = 25.0"""
        total = _num(total)
        if total == 0:
            raise CalculatorError("分母 total 不能为零")
        return _num(part) / total * 100.0

    @staticmethod
    def pct_change(old: Number, new: Number) -> float:
        """(new - old) / old × 100，百分比变化率。例: pct_change(25.90, 26.10) ≈ 0.7722"""
        old = _num(old)
        if old == 0:
            raise CalculatorError("基数 old 不能为零")
        return (_num(new) - old) / old * 100.0

    @staticmethod
    def change_abs(old: Number, new: Number) -> Number:
        """绝对变化量 new - old"""
        return _num(new) - _num(old)

    # 三、持仓与盈亏
    @staticmethod
    def position_value(shares: Number, price: Number) -> float:
        """持仓市值 = 股数 × 价格"""
        return _num(shares) * _num(price)

    @staticmethod
    def pnl(shares: Number, avg_cost: Number, current: Number) -> dict:
        """持仓盈亏分析。

        返回市值、成本、浮盈与收益率%。
        """
        shares_f = _num(shares)
        avg_cost_f = _num(avg_cost)
        current_f = _num(current)
        market_value = shares_f * current_f
        cost = shares_f * avg_cost_f
        pnl_abs = market_value - cost
        pnl_pct = (pnl_abs / cost * 100.0) if cost != 0 else 0.0
        return {
            "市值": round(market_value, 4),
            "成本": round(cost, 4),
            "浮盈": round(pnl_abs, 4),
            "收益率%": round(pnl_pct, 6),
        }

    @staticmethod
    def stop_loss(avg_cost: Number, pct: Number) -> float:
        """止损价 = avg_cost × (1 + pct/100)。pct 通常为负（如 -10 表示跌 10% 止损）。"""
        return _num(avg_cost) * (1 + _num(pct) / 100.0)

    @staticmethod
    def take_profit(avg_cost: Number, pct: Number) -> float:
        """止盈价 = avg_cost × (1 + pct/100)。pct 通常为正。"""
        return Calculator.stop_loss(avg_cost, pct)

    @staticmethod
    def break_even_price(avg_cost: Number, fee_rate: Number = 0.0) -> float:
        """盈亏平衡价 = avg_cost × (1 + fee_rate/100)。fee_rate 单边手续费(%)。"""
        return _num(avg_cost) * (1 + _num(fee_rate) / 100.0)

    # 四、复利与年金
    @staticmethod
    def fv(pv: Number, rate: Number, periods: int) -> float:
        """复利终值 Future Value = PV × (1 + rate)^periods"""
        return _num(pv) * (1 + _num(rate)) ** _num(periods)

    @staticmethod
    def pv(fv: Number, rate: Number, periods: int) -> float:
        """复利现值 Present Value = FV / (1 + rate)^periods"""
        return _num(fv) / (1 + _num(rate)) ** _num(periods)

    @staticmethod
    def monthly_payment(principal: Number, annual_rate: Number, years: Number) -> float:
        """等额本息月供（月利率 = 年利率 / 12）。"""
        p = _num(principal)
        annual_r = _num(annual_rate)
        n = int(_num(years) * 12)
        if n <= 0:
            raise CalculatorError("年数必须 > 0")
        if annual_r == 0:
            return p / n
        r = annual_r / 12.0
        return p * r * (1 + r) ** n / ((1 + r) ** n - 1)

    @staticmethod
    def annualized_return(total_return: Number, years: Number) -> float:
        """年化收益率 = (1 + total_return/100)^(1/years) - 1，返回小数。"""
        tr = _num(total_return) / 100.0
        y = _num(years)
        if y <= 0:
            raise CalculatorError("年数必须 > 0")
        return (1 + tr) ** (1 / y) - 1

    # 五、统计
    @staticmethod
    def mean(values: Sequence[Number]) -> float:
        """算术平均"""
        arr = _to_array(values, "mean")
        return float(np.mean(arr))

    @staticmethod
    def median(values: Sequence[Number]) -> float:
        """中位数"""
        arr = _to_array(values, "median")
        return float(np.median(arr))

    @staticmethod
    def std(values: Sequence[Number], ddof: int = 1) -> float:
        """标准差，ddof=1 样本标准差（默认），ddof=0 总体标准差"""
        arr = _to_array(values, "std")
        return float(np.std(arr, ddof=ddof))

    @staticmethod
    def variance(values: Sequence[Number], ddof: int = 1) -> float:
        """方差，ddof 同上"""
        arr = _to_array(values, "variance")
        return float(np.var(arr, ddof=ddof))

    @staticmethod
    def percentile(values: Sequence[Number], p: Number) -> float:
        """p 分位数 (0-100)。例: percentile(prices, 50) = 中位数"""
        arr = _to_array(values, "percentile")
        return float(np.percentile(arr, _num(p)))

    @staticmethod
    def correlation(x: Sequence[Number], y: Sequence[Number]) -> float:
        """Pearson 相关系数，要求 x/y 等长且 len >= 2。"""
        xa = _to_array(x, "correlation.x")
        ya = _to_array(y, "correlation.y")
        if len(xa) != len(ya):
            raise CalculatorError(f"x 与 y 长度不一致: x={len(xa)}, y={len(ya)}")
        if len(xa) < 2:
            raise CalculatorError("至少需要 2 个数据点")
        return float(np.corrcoef(xa, ya)[0, 1])

    @staticmethod
    def max_drawdown(prices: Sequence[Number]) -> dict:
        """最大回撤。返回:
            max_drawdown_pct: 最大回撤幅度(负数，如 -13.5 表示跌 13.5%)
            peak_idx: 峰值索引
            trough_idx: 谷值索引
            recovery_idx: 恢复到前高的索引(若未恢复则为 None)
            peak_value: 峰值
            trough_value: 谷值
        """
        arr = _to_array(prices, "max_drawdown")
        if len(arr) < 2:
            raise CalculatorError("至少需要 2 个价格点")

        peak_so_far = arr[0]
        peak_idx = 0
        mdd = 0.0
        mdd_peak = 0
        mdd_trough = 0
        recovery_idx = None

        for i, p in enumerate(arr):
            if p > peak_so_far:
                peak_so_far = p
                peak_idx = i
            dd = (p - peak_so_far) / peak_so_far * 100.0
            if dd < mdd:
                mdd = dd
                mdd_peak = peak_idx
                mdd_trough = i

        for i in range(mdd_trough + 1, len(arr)):
            if arr[i] >= arr[mdd_peak]:
                recovery_idx = i
                break

        return {
            "max_drawdown_pct": round(mdd, 6),
            "peak_idx": int(mdd_peak),
            "trough_idx": int(mdd_trough),
            "recovery_idx": recovery_idx,
            "peak_value": float(arr[mdd_peak]),
            "trough_value": float(arr[mdd_trough]),
        }

    # 六、金融指标
    @staticmethod
    def sharpe(
        returns: Sequence[Number],
        rf: Number = 0.0,
        periods_per_year: int = 252,
    ) -> dict:
        """年化夏普比率。

        Sharpe = (mean(r) - rf) / std(r) × sqrt(periods_per_year)
        """
        arr = _to_array(returns, "sharpe")
        if len(arr) < 2:
            raise CalculatorError("至少需要 2 个收益数据点")
        rf_f = _num(rf)
        excess = arr - rf_f
        ann_ret = float(np.mean(excess)) * periods_per_year
        ann_vol = float(np.std(excess, ddof=1)) * math.sqrt(periods_per_year)
        sharpe_ratio = ann_ret / ann_vol if ann_vol != 0 else 0.0
        return {
            "sharpe_ratio": round(sharpe_ratio, 6),
            "annual_return": round(ann_ret, 6),
            "annual_vol": round(ann_vol, 6),
        }

    @staticmethod
    def annualized_volatility(
        returns: Sequence[Number],
        periods_per_year: int = 252,
    ) -> float:
        """年化波动率 = std(returns) × sqrt(periods_per_year)"""
        arr = _to_array(returns, "annualized_volatility")
        if len(arr) < 2:
            raise CalculatorError("至少需要 2 个收益数据点")
        return float(np.std(arr, ddof=1) * math.sqrt(periods_per_year))

    @staticmethod
    def win_rate(pnl_list: Sequence[Number]) -> float:
        """胜率: pnl_list 中正值(盈利)占比，返回百分比 (0-100)。"""
        arr = _to_array(pnl_list, "win_rate")
        if len(arr) == 0:
            raise CalculatorError("至少需要 1 个 PnL 数据点")
        wins = int(np.sum(arr > 0))
        return wins / len(arr) * 100.0

    # 七、坐标/位次
    @staticmethod
    def position_in_range(price: Number, low: Number, high: Number) -> float:
        """价格在 [low, high] 区间的位置百分比。"""
        low_f = _num(low)
        high_f = _num(high)
        price_f = _num(price)
        if high_f <= low_f:
            raise CalculatorError("high 必须大于 low")
        return (price_f - low_f) / (high_f - low_f) * 100.0

    # 八、换算
    @staticmethod
    def convert(amount: Number, rate: Number) -> float:
        """汇率换算 amount × rate。"""
        return _num(amount) * _num(rate)


# =============================================================================
# 安全 AST 语法树求值
# =============================================================================

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# 白名单安全函数映射
_ALLOWED_FUNCS: dict[str, Any] = {
    # 基础数学
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    # Calculator 静态方法
    "add": Calculator.add,
    "sub": Calculator.sub,
    "mul": Calculator.mul,
    "div": Calculator.div,
    "pct": Calculator.pct,
    "pct_change": Calculator.pct_change,
    "change_abs": Calculator.change_abs,
    "position_value": Calculator.position_value,
    "pnl": Calculator.pnl,
    "stop_loss": Calculator.stop_loss,
    "take_profit": Calculator.take_profit,
    "break_even_price": Calculator.break_even_price,
    "fv": Calculator.fv,
    "pv": Calculator.pv,
    "monthly_payment": Calculator.monthly_payment,
    "annualized_return": Calculator.annualized_return,
    "mean": Calculator.mean,
    "median": Calculator.median,
    "std": Calculator.std,
    "variance": Calculator.variance,
    "percentile": Calculator.percentile,
    "correlation": Calculator.correlation,
    "max_drawdown": Calculator.max_drawdown,
    "sharpe": Calculator.sharpe,
    "annualized_volatility": Calculator.annualized_volatility,
    "win_rate": Calculator.win_rate,
    "position_in_range": Calculator.position_in_range,
    "convert": Calculator.convert,
}


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](
            _eval_node(node.left),
            _eval_node(node.right),
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(elt) for elt in node.elts]
    if isinstance(node, ast.Dict):
        evaluated_dict: dict[Any, Any] = {}
        for k_node, v_node in zip(node.keys, node.values):
            if k_node is None:
                unpacked = _eval_node(v_node)
                if isinstance(unpacked, dict):
                    evaluated_dict.update(unpacked)
                else:
                    raise ValueError(f"无法解包非字典对象: {type(unpacked).__name__}")
            else:
                k_val = _eval_node(k_node)
                v_val = _eval_node(v_node)
                evaluated_dict[k_val] = v_val
        return evaluated_dict
    if isinstance(node, ast.Set):
        return {_eval_node(elt) for elt in node.elts}
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError(f"仅支持直接调用白名单函数，不支持属性或复杂调用: {ast.dump(node)}")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCS:
            raise ValueError(f"未授权调用的函数: {func_name}")

        func = _ALLOWED_FUNCS[func_name]
        args = [_eval_node(arg) for arg in node.args]
        kwargs = {kw.arg: _eval_node(kw.value) for kw in node.keywords if kw.arg is not None}
        return func(*args, **kwargs)

    raise ValueError(f"Unsupported expression element: {ast.dump(node)}")


def calculate(expression: str) -> str:
    """Evaluate a precise arithmetic or financial expression and return the exact result.

    Always call this for any arithmetic beyond trivial single-digit facts —
    sums, percentages, ratios, compounding, Sharpe ratio, max drawdown,
    and any calculation involving more than two numbers must go through
    this tool rather than being computed mentally.

    Supports single arithmetic expressions, list/tuple arrays, as well as
    structured compound dictionaries (e.g. computing multiple support/resistance/stop
    levels for one or more stocks in a single tool call).

    Args:
        expression (`str`):
            A Python-style arithmetic expression, financial function call,
            or compound dictionary/list, e.g.:
            - `"(153.2 - 100) / 100 * 100"`
            - `"pct_change(25.90, 26.10)"`
            - `"pnl(300, 25.554, 26.10)"`
            - `"max_drawdown([27.69, 26.10, 25.00, 26.25, 23.96, 26.10])"`
            - `"sharpe([0.012, -0.005, 0.018, 0.022, -0.003, 0.015])"`
            - `"{'name': '海康威视', 'cost_prot': round(31.025 * 0.9, 2), 'tp1': round(32.46 * 1.15, 2)}"`
            - `"[{'code': '002415', 'target': round(32.46 * 1.15, 2)}]"`
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        if isinstance(result, (dict, list)):
            try:
                formatted_json = json.dumps(result, ensure_ascii=False, indent=2)
                return f"{expression} =\n{formatted_json}"
            except (TypeError, ValueError):
                pass
        return f"{expression} = {result}"
    except Exception as exc:  # noqa: BLE001 - surfaced to the model as text
        return f"计算失败：{exc}"
