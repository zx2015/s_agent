"""
The precision calculator tool.

CLAUDE.md's rule for the later stock-analysis phase — "严禁心算" — is
enforced here from day one: the model is never allowed to add, multiply,
or otherwise compute a numeric answer by itself. Every arithmetic request
must go through this tool, which evaluates with Python's own numeric
types rather than an LLM's approximate token-level "mental math".

The evaluator is a restricted AST walker, not `eval()`, so the tool
cannot be turned into an arbitrary-code-execution primitive via a
crafted expression.
"""
import ast
import operator

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


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](
            _eval_node(node.left),
            _eval_node(node.right),
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression element: {ast.dump(node)}")


def calculate(expression: str) -> str:
    """Evaluate a precise arithmetic expression and return the exact result.

    Always call this for any arithmetic beyond trivial single-digit facts —
    sums, percentages, ratios, compounding, and any calculation involving
    more than two numbers must go through this tool rather than being
    computed mentally.

    Args:
        expression (`str`):
            A Python-style arithmetic expression, e.g. `"(153.2 - 100) /
            100 * 100"`. Supports `+ - * / // % **` and parentheses only.
    """
    # A plain `str` return is intentional: FunctionTool's adapter
    # (agentscope/tool/_adapters.py) only special-cases `ToolChunk`, `str`,
    # or JSON-serializable data for a wrapped function's return value —
    # returning `ToolResponse` here (a *different*, unrelated pydantic
    # model despite the similar name) falls through to `str(result)`,
    # which leaks the object's Python repr into the tool result shown to
    # the model and the user instead of the clean answer text.
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
    except Exception as exc:  # noqa: BLE001 - surfaced to the model as text
        return f"计算失败：{exc}"

    return f"{expression} = {result}"
