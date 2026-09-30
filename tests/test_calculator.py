"""Unit tests for the calculator tool (server/tools/calculator.py)."""
from server.tools.calculator import calculate


def _text(response) -> str:
    return response.content[0].text


def test_calculate_basic_arithmetic():
    result = calculate("1 + 2 * 3")
    assert _text(result) == "1 + 2 * 3 = 7"


def test_calculate_handles_floats_and_parens():
    result = calculate("(153.2 - 100) / 100 * 100")
    assert "53.199999999999996" in _text(result) or "53.2" in _text(result)


def test_calculate_rejects_non_arithmetic_expressions():
    result = calculate("__import__('os').system('echo pwned')")
    assert "计算失败" in _text(result)


def test_calculate_rejects_name_lookups():
    result = calculate("os.getcwd()")
    assert "计算失败" in _text(result)
