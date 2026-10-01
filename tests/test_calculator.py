"""Unit tests for the calculator tool (server/tools/calculator.py)."""
import json
from server.tools.calculator import Calculator, calculate


def test_calculate_basic_arithmetic():
    assert calculate("1 + 2 * 3") == "1 + 2 * 3 = 7"


def test_calculate_handles_floats_and_parens():
    result = calculate("(153.2 - 100) / 100 * 100")
    assert "53.199999999999996" in result or "53.2" in result


def test_calculate_rejects_non_arithmetic_expressions():
    result = calculate("__import__('os').system('echo pwned')")
    assert "计算失败" in result


def test_calculate_rejects_name_lookups():
    result = calculate("os.getcwd()")
    assert "计算失败" in result


def test_calculate_built_in_math_functions():
    assert calculate("sqrt(16) * 2 + abs(-5)") == "sqrt(16) * 2 + abs(-5) = 13.0"
    assert calculate("round(3.14159, 2)") == "round(3.14159, 2) = 3.14"


def test_calculate_pct_change():
    result = calculate("pct_change(25.90, 26.10)")
    assert "0.7722" in result


def test_calculate_pnl():
    result = calculate("pnl(300, 25.554, 26.10)")
    assert "市值" in result
    assert "7830.0" in result
    assert "浮盈" in result
    assert "163.8" in result


def test_calculate_max_drawdown():
    result = calculate("max_drawdown([27.69, 26.10, 25.00, 26.25, 23.96, 26.10])")
    assert "max_drawdown_pct" in result
    assert "-13.47" in result


def test_calculate_sharpe_with_kwargs():
    result = calculate("sharpe([0.012, -0.005, 0.018, 0.022, -0.003, 0.015], rf=0.0)")
    assert "sharpe_ratio" in result
    assert "annual_return" in result
    assert "annual_vol" in result


def test_calculate_compounding_fv():
    result = calculate("fv(10000, 0.05, 10)")
    assert "16288.946" in result


def test_calculator_direct_error_handling():
    res = calculate("1 / 0")
    assert "计算失败" in res
    assert "division by zero" in res or "除零" in res

    res2 = calculate("pct_change(0, 10)")
    assert "计算失败" in res2
    assert "基数 old 不能为零" in res2
