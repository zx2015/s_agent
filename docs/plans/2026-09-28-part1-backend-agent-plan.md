# Part 1: 后端单 Agent 内核 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现基于 AgentScope 2.0.8 + LiteLLM `v-flash` 的单 Agent 内核，包含可配置模型、12 个内置工具、四大记忆机制、HITL 权限、工作区 git 化，并通过 FastAPI 暴露 SSE 流式接口。

**Architecture:** 分层 — `config`（环境变量配置）→ `llm`（凭据+模型工厂）→ `agent`（Agent 装配）→ `tools`（Toolkit 注册）→ `memory`（记忆中间件）→ `service`（FastAPI + SSE 路由）→ `workspace`（git 化）。层间单向依赖，`service` 在顶层编排，下层可独立测试。

**Tech Stack:** Python 3.12.14、AgentScope 2.0.8、FastAPI 0.139、Uvicorn 0.43、Redis 7.4.3（端口 6380）、pytest、httpx。

**前置条件**：见 [主计划文档 §关键前置条件](2026-09-28-single-agent-and-workbench-plan.md)。

**⚠️ AgentScope 2.0.8 API 约束（规划时已实测，写代码必须遵守）**：
1. `Msg.content` 必须是 ContentBlock 列表 `[TextBlock(text="...")]`，不能传字符串。
2. `base_url` 只写在 `OpenAICredential`，不能同时在 `client_kwargs` 中重复传。
3. `parameters` 必须是 `OpenAIChatModel.Parameters(...)` 实例，不能传 dict。
4. `formatter` 属于 `OpenAIChatModel`，不属于 `Agent`。
5. 流式调用用 `agent.reply_stream(msg)`，不用 `stream_printing_messages`。

---

## Task 1: 项目脚手架与配置模块

**Files:**
- Create: `server/__init__.py`
- Create: `server/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`
- Create: `pytest.ini`

- [ ] **Step 1: 创建包目录与空 `__init__.py`**

```bash
cd /media/data/git/s_agent
mkdir -p server/llm server/agent server/tools server/memory server/service server/workspace server/prompts
mkdir -p tests
touch server/__init__.py server/llm/__init__.py server/agent/__init__.py
touch server/tools/__init__.py server/memory/__init__.py server/service/__init__.py
touch server/workspace/__init__.py tests/__init__.py
```

- [ ] **Step 2: 写失败的测试 `tests/test_config.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the server configuration module."""
import os

import pytest

from server.config import Settings, get_settings


def test_default_settings():
    """Settings should have sensible defaults for local development."""
    settings = Settings()
    assert settings.model_name == "v-flash"
    assert settings.base_url == "http://127.0.0.1:4000/v1"
    assert settings.max_tokens == 4096
    assert settings.redis_port == 6380
    assert settings.redis_host == "127.0.0.1"
    assert settings.redis_db == 0


def test_default_max_tokens_meets_reasoning_floor():
    """v-flash is a reasoning model: max_tokens below 2048 yields empty content."""
    settings = Settings()
    assert settings.max_tokens >= 2048


def test_env_override(monkeypatch):
    """Environment variables must override defaults."""
    monkeypatch.setenv("S_AGENT_MODEL_NAME", "custom-model")
    monkeypatch.setenv("S_AGENT_MAX_TOKENS", "8192")
    monkeypatch.setenv("S_AGENT_REDIS_PORT", "7000")
    settings = Settings()
    assert settings.model_name == "custom-model"
    assert settings.max_tokens == 8192
    assert settings.redis_port == 7000


def test_api_key_from_env(monkeypatch):
    """The API key must come from the environment, never hardcoded."""
    monkeypatch.setenv("LITELLM_API_KEY", "test-key-123")
    settings = Settings()
    assert settings.api_key == "test-key-123"


def test_api_key_absent_is_none(monkeypatch):
    """With no key in env, api_key is None rather than a baked-in default."""
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    settings = Settings()
    assert settings.api_key is None


def test_get_settings_is_cached():
    """get_settings() should return the same instance (lru_cache)."""
    assert get_settings() is get_settings()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.config'`

- [ ] **Step 4: 写实现 `server/config.py`**

```python
# -*- coding: utf-8 -*-
"""Unified configuration for the s_agent backend.

Every value is environment-overridable so the service can be reconfigured
without touching code. Secrets are read from the environment only -- never
hardcoded -- and the LiteLLM endpoint defaults match the local deployment
verified on 2026-09-28 (see .learnings/knowledge/litellm-vflash-integration.md).
"""
import os
from functools import lru_cache

from pydantic import BaseModel, Field


def _env_int(name: str, default: int) -> int:
    """Read an integer from the environment, falling back to a default.

    Args:
        name (`str`):
            The environment variable name.
        default (`int`):
            The value to use when the variable is unset or unparseable.

    Returns:
        `int`:
            The resolved integer value.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings(BaseModel):
    """Runtime settings for the agent backend.

    All fields are populated from environment variables so that a deployment
    can be reconfigured without editing code.
    """

    # -- Model ---------------------------------------------------------
    model_name: str = Field(
        default_factory=lambda: os.getenv("S_AGENT_MODEL_NAME", "v-flash"),
    )
    base_url: str = Field(
        default_factory=lambda: os.getenv(
            "S_AGENT_BASE_URL",
            "http://127.0.0.1:4000/v1",
        ),
    )
    api_key: str | None = Field(
        default_factory=lambda: (
            os.getenv("LITELLM_API_KEY")
            or os.getenv("LITELLM_MASTER_KEY")
            or None
        ),
    )
    max_tokens: int = Field(
        default_factory=lambda: _env_int("S_AGENT_MAX_TOKENS", 4096),
    )
    temperature: float = Field(
        default_factory=lambda: float(
            os.getenv("S_AGENT_TEMPERATURE", "0.7"),
        ),
    )

    # -- Storage -------------------------------------------------------
    redis_host: str = Field(
        default_factory=lambda: os.getenv("S_AGENT_REDIS_HOST", "127.0.0.1"),
    )
    redis_port: int = Field(
        default_factory=lambda: _env_int("S_AGENT_REDIS_PORT", 6380),
    )
    redis_db: int = Field(
        default_factory=lambda: _env_int("S_AGENT_REDIS_DB", 0),
    )

    # -- Workspace -----------------------------------------------------
    workspace_root: str = Field(
        default_factory=lambda: os.getenv(
            "S_AGENT_WORKSPACE_ROOT",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspaces"),
        ),
    )

    # -- Service -------------------------------------------------------
    host: str = Field(
        default_factory=lambda: os.getenv("S_AGENT_HOST", "0.0.0.0"),
    )
    port: int = Field(
        default_factory=lambda: _env_int("S_AGENT_PORT", 8000),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Returns:
        `Settings`:
            The cached settings instance.
    """
    return Settings()
```

- [ ] **Step 5: 写 `tests/conftest.py`（共享 fixtures）**

```python
# -*- coding: utf-8 -*-
"""Shared pytest fixtures for the s_agent backend test suite."""
import os
import sys

import pytest

# Make the project root importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def settings_env(monkeypatch):
    """Provide a deterministic environment for settings tests.

    Yields a dict of the variables set, so tests can assert on them.
    """
    values = {
        "S_AGENT_MODEL_NAME": "v-flash",
        "S_AGENT_BASE_URL": "http://127.0.0.1:4000/v1",
        "S_AGENT_MAX_TOKENS": "4096",
        "S_AGENT_REDIS_HOST": "127.0.0.1",
        "S_AGENT_REDIS_PORT": "6380",
        "LITELLM_API_KEY": "test-key",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    yield values
```

- [ ] **Step 6: 写 `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 7: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_config.py -v`
Expected: 6 passed

- [ ] **Step 8: 创建 `.env.example`（不含真实密钥）**

```bash
# s_agent backend configuration -- copy to .env and fill in real values.
# NOTE: .env is gitignored. NEVER commit real credentials.

# Model (local LiteLLM proxy)
S_AGENT_MODEL_NAME=v-flash
S_AGENT_BASE_URL=http://127.0.0.1:4000/v1
S_AGENT_MAX_TOKENS=4096
S_AGENT_TEMPERATURE=0.7
LITELLM_API_KEY=

# Storage (local Redis container, host port 6380 NOT 6379)
S_AGENT_REDIS_HOST=127.0.0.1
S_AGENT_REDIS_PORT=6380
S_AGENT_REDIS_DB=0

# Service
S_AGENT_HOST=0.0.0.0
S_AGENT_PORT=8000
```

- [ ] **Step 9: 验证 `.env` 确实被 gitignore**

Run: `git check-ignore -v .env || echo "WARNING: .env is NOT ignored"`
Expected: 输出 `.gitignore:...:.env`（若有 warning 说明需修 .gitignore）

- [ ] **Step 10: Commit**

```bash
cd /media/data/git/s_agent
git add server/__init__.py server/config.py tests/__init__.py tests/conftest.py tests/test_config.py pytest.ini .env.example
git commit -m "feat: config: add environment-driven settings module"
```

---

## Task 2: 模型层 — Credential 与 Model 工厂

**Files:**
- Create: `server/llm/credential.py`
- Create: `server/llm/model.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: 写失败的测试 `tests/test_llm.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the LLM credential and model factories."""
import pytest

from server.config import Settings
from server.llm.credential import create_credential
from server.llm.model import create_model


@pytest.fixture
def settings(monkeypatch):
    """A settings instance pointing at a fake local endpoint."""
    monkeypatch.setenv("S_AGENT_MODEL_NAME", "v-flash")
    monkeypatch.setenv("S_AGENT_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("S_AGENT_MAX_TOKENS", "4096")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    return Settings()


def test_create_credential_carries_base_url(settings):
    """The credential owns the base_url (AgentScope 2.0 forbids passing it
    to client_kwargs as well -- doing so raises 'multiple values' from
    openai.AsyncOpenAI)."""
    credential = create_credential(settings)
    assert credential.base_url == "http://127.0.0.1:4000/v1"
    assert credential.api_key.get_secret_value() == "test-key"


def test_create_credential_requires_api_key(monkeypatch):
    """Missing credentials must fail loudly at assembly time, not at request
    time with an opaque 401."""
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    settings = Settings()
    with pytest.raises(ValueError, match="API key"):
        create_credential(settings)


def test_create_model_uses_parameters_object(settings):
    """parameters must be a Parameters instance; a plain dict makes the
    first request die with 'dict object has no attribute max_tokens'."""
    model = create_model(settings)
    assert model.model_name == "v-flash"
    assert model.parameters.max_tokens == 4096


def test_create_model_honours_max_tokens_floor(settings, monkeypatch):
    """A caller asking for an unsafe max_tokens is clamped up to the
    reasoning-safe floor rather than silently producing empty replies."""
    monkeypatch.setenv("S_AGENT_MAX_TOKENS", "64")
    small = Settings()
    model = create_model(small)
    assert model.parameters.max_tokens >= 2048
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.llm.credential'`

- [ ] **Step 3: 写实现 `server/llm/credential.py`**

```python
# -*- coding: utf-8 -*-
"""Credential factory for the LiteLLM-backed OpenAI-compatible model.

AgentScope 2.0 introduced a credential abstraction: the endpoint
(``base_url``) and the secret live on the credential, and the model must NOT
receive them again -- passing ``base_url`` to both places makes
``openai.AsyncClient`` raise "got multiple values for keyword argument".
"""
from agentscope.credential import OpenAICredential

from ..config import Settings


def create_credential(settings: Settings) -> OpenAICredential:
    """Build the OpenAI-compatible credential for the configured endpoint.

    Args:
        settings (`Settings`):
            The runtime settings carrying the base URL and API key.

    Returns:
        `OpenAICredential`:
            A credential bound to the LiteLLM proxy.

    Raises:
        `ValueError`:
            When no API key is available in the environment. Failing here
            surfaces the problem at startup rather than as an opaque 401
            on the first user request.
    """
    if not settings.api_key:
        raise ValueError(
            "No API key found. Set LITELLM_API_KEY (or LITELLM_MASTER_KEY) "
            "in the environment before starting the service.",
        )

    return OpenAICredential(
        id="litellm-vflash",
        name="LiteLLM v-flash",
        api_key=settings.api_key,
        base_url=settings.base_url,
    )
```

- [ ] **Step 4: 写实现 `server/llm/model.py`**

```python
# -*- coding: utf-8 -*-
"""Model factory building an AgentScope chat model for the local LiteLLM.

Two AgentScope 2.0 constraints shape this module:

1. ``parameters`` must be a ``Parameters`` instance. A plain dict reaches
   the request path and dies with
   ``'dict' object has no attribute 'max_tokens'``.
2. ``v-flash`` is a reasoning model. With a small ``max_tokens`` the whole
   budget is spent on the thinking pass and the visible ``content`` comes
   back empty, so values below the floor are clamped up.
"""
from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import OpenAIChatModel

from ..config import Settings
from .credential import create_credential

# Below this, v-flash spends the entire budget thinking and emits no answer.
MIN_SAFE_MAX_TOKENS = 2048


def create_model(settings: Settings) -> OpenAIChatModel:
    """Build the chat model used by every agent in this service.

    Args:
        settings (`Settings`):
            The runtime settings carrying model name, endpoint and
            generation parameters.

    Returns:
        `OpenAIChatModel`:
            A stream-capable chat model wired to the LiteLLM proxy.
    """
    max_tokens = max(settings.max_tokens, MIN_SAFE_MAX_TOKENS)

    return OpenAIChatModel(
        credential=create_credential(settings),
        model=settings.model_name,
        formatter=OpenAIChatFormatter(),
        parameters=OpenAIChatModel.Parameters(
            max_tokens=max_tokens,
            temperature=settings.temperature,
        ),
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_llm.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add server/llm/credential.py server/llm/model.py tests/test_llm.py
git commit -m "feat: llm: add credential and model factories for LiteLLM"
```

---

## Task 3: 计算器工具（移植自股票分析项目）

**Files:**
- Create: `server/tools/calculator.py`
- Create: `tests/test_tools_calculator.py`

- [ ] **Step 1: 查看源文件确认可移植的接口**

Run: `ls /media/data/git/股票分析/.claude/skills/calculator/ && head -60 /media/data/git/股票分析/.claude/skills/calculator/calculator.py`
Expected: 看到 `Calculator` 类与 CLI 子命令（`pnl`、`pct_change`、`max_drawdown` 等）

- [ ] **Step 2: 写失败的测试 `tests/test_tools_calculator.py`**

```python
# -*- coding: utf-8 -*-
"""Precision regression tests for the calculator tool.

Mirrors the semantics of the calculator skill in the 股票分析 project:
every arithmetic result the agent reports must be reproducible here rather
than hand-computed by the model.
"""
import pytest

from server.tools.calculator import (
    calculate,
    max_drawdown,
    pct_change,
    pnl,
)


def test_calculate_basic_arithmetic():
    assert calculate("2 + 3 * 4") == 14
    assert calculate("(2 + 3) * 4") == 20
    assert calculate("10 / 4") == 2.5


def test_calculate_rejects_non_arithmetic():
    """Only arithmetic is allowed -- no names, calls or attribute access."""
    with pytest.raises(ValueError):
        calculate("__import__('os').system('ls')")
    with pytest.raises(ValueError):
        calculate("open('/etc/passwd').read()")


def test_pnl_long_position():
    """A long position gains when price rises: (sell - buy) * shares."""
    result = pnl(shares=300, buy_price=25.554, sell_price=26.10)
    assert result["profit"] == pytest.approx(163.80, abs=0.01)
    assert result["return_pct"] == pytest.approx(2.14, abs=0.01)


def test_pnl_short_position_loses_on_rise():
    result = pnl(shares=100, buy_price=10.0, sell_price=9.0)
    assert result["profit"] == pytest.approx(-100.0)


def test_pct_change():
    assert pct_change(25.90, 26.10)["change_pct"] == pytest.approx(
        0.7722,
        abs=0.001,
    )


def test_pct_change_from_zero_raises():
    """Dividing by a zero base is undefined -- refuse rather than inf."""
    with pytest.raises(ValueError):
        pct_change(0.0, 10.0)


def test_max_drawdown():
    """Drawdown from the running peak, expressed as a negative percentage."""
    result = max_drawdown([27.69, 26.10, 25.00, 26.25, 23.96, 26.10])
    assert result["max_drawdown_pct"] == pytest.approx(-13.47, abs=0.05)
    assert result["peak"] == pytest.approx(27.69)
    assert result["trough"] == pytest.approx(23.96)


def test_max_drawdown_requires_two_points():
    with pytest.raises(ValueError):
        max_drawdown([10.0])
```

- [ ] **Step 3: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_tools_calculator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.tools.calculator'`

- [ ] **Step 4: 写实现 `server/tools/calculator.py`**

```python
# -*- coding: utf-8 -*-
"""Calculator tool: the agent's only sanctioned path to arithmetic.

The model must never hand-compute results. Anything beyond trivial mental
arithmetic is routed through :func:`calculate` or one of the finance
helpers, all of which are plain deterministic Python.

``calculate`` evaluates arithmetic with an AST whitelist rather than
``eval``: names, calls, attribute access and imports are rejected outright,
so a prompt-injected expression cannot reach the interpreter.
"""
import ast
import math
import operator
from typing import Any, Callable

# Binary and unary operators permitted in ``calculate`` expressions.
_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
# Named constants only -- no arbitrary names can be resolved.
_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}


def _eval_node(node: ast.AST) -> float:
    """Recursively evaluate a whitelisted AST node.

    Args:
        node (`ast.AST`):
            The node to evaluate.

    Returns:
        `float`:
            The numeric value of the node.

    Raises:
        `ValueError`:
            When the expression uses a construct outside the arithmetic
            whitelist.
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(
            node.value,
            (int, float),
        ):
            raise ValueError(f"Only numbers are allowed, got {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in _CONSTANTS:
            raise ValueError(f"Unknown name: {node.id!r}")
        return _CONSTANTS[node.id]
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        uop = _UNARY_OPS.get(type(node.op))
        if uop is None:
            raise ValueError(f"Unsupported unary: {type(node.op).__name__}")
        return uop(_eval_node(node.operand))
    raise ValueError(f"Unsupported expression: {type(node).__name__}")


def calculate(expression: str) -> float:
    """Evaluate an arithmetic expression safely.

    Supports ``+ - * / // % **``, parentheses, unary signs and the
    constants ``pi`` and ``e``. Function calls, names, attribute access and
    imports are rejected.

    Args:
        expression (`str`):
            The arithmetic expression to evaluate.

    Returns:
        `float`:
            The computed value.

    Raises:
        `ValueError`:
            When the expression is malformed or uses a disallowed construct.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {expression!r}") from exc
    return _eval_node(tree)


def pnl(shares: float, buy_price: float, sell_price: float) -> dict:
    """Compute profit and loss for a position.

    Args:
        shares (`float`):
            Number of shares held.
        buy_price (`float`):
            Entry price per share.
        sell_price (`float`):
            Exit price per share (use a mark price for an open position).

    Returns:
        `dict`:
            ``profit`` (absolute) and ``return_pct`` (percentage).
    """
    profit = (sell_price - buy_price) * shares
    cost = buy_price * shares
    return {
        "profit": round(profit, 4),
        "return_pct": round(profit / cost * 100, 4) if cost else 0.0,
    }


def pct_change(old: float, new: float) -> dict:
    """Compute the percentage change between two values.

    Args:
        old (`float`):
            The base value.
        new (`float`):
            The new value.

    Returns:
        `dict`:
            ``change`` (absolute) and ``change_pct`` (percentage).

    Raises:
        `ValueError`:
            When the base is zero, where percentage change is undefined.
    """
    if old == 0:
        raise ValueError("Percentage change from a zero base is undefined.")
    return {
        "change": round(new - old, 4),
        "change_pct": round((new - old) / old * 100, 4),
    }


def max_drawdown(prices: list[float]) -> dict:
    """Compute the maximum drawdown of a price series.

    Args:
        prices (`list[float]`):
            The price series in chronological order.

    Returns:
        `dict`:
            ``max_drawdown_pct`` (negative), ``peak`` and ``trough``.

    Raises:
        `ValueError`:
            When fewer than two prices are supplied.
    """
    if len(prices) < 2:
        raise ValueError("At least two prices are required.")

    peak = prices[0]
    peak_at_max = trough_at_max = prices[0]
    worst = 0.0

    for price in prices:
        if price > peak:
            peak = price
        drawdown = (price - peak) / peak * 100
        if drawdown < worst:
            worst = drawdown
            peak_at_max, trough_at_max = peak, price

    return {
        "max_drawdown_pct": round(worst, 4),
        "peak": round(peak_at_max, 4),
        "trough": round(trough_at_max, 4),
    }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_tools_calculator.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add server/tools/calculator.py tests/test_tools_calculator.py
git commit -m "feat: tools: add safe AST-whitelisted calculator with finance helpers"
```

---

## Task 4: 工作区沙箱路径校验

**Files:**
- Create: `server/workspace/sandbox.py`
- Create: `tests/test_workspace_sandbox.py`

- **背景**：Spec 模块 C-3 要求所有文件工具限制在 `workspace/` 根目录内，越界返回明确错误。

- [ ] **Step 1: 写失败的测试 `tests/test_workspace_sandbox.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for workspace path confinement.

Every file tool routes its path argument through :func:`resolve_in_workspace`
so a prompt-injected `../../etc/passwd` cannot escape the task directory.
"""
import pytest

from server.workspace.sandbox import PathEscapeError, resolve_in_workspace


@pytest.fixture
def workspace(tmp_path):
    """A throwaway workspace root with one nested file."""
    root = tmp_path / "workspace"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "note.txt").write_text("hello", encoding="utf-8")
    return root


def test_resolves_relative_path(workspace):
    resolved = resolve_in_workspace(workspace, "sub/note.txt")
    assert resolved == (workspace / "sub" / "note.txt").resolve()


def test_allows_new_file_inside_workspace(workspace):
    """Creating a file that does not exist yet must still resolve."""
    resolved = resolve_in_workspace(workspace, "sub/new.txt")
    assert resolved.parent == (workspace / "sub").resolve()


def test_rejects_parent_traversal(workspace):
    with pytest.raises(PathEscapeError):
        resolve_in_workspace(workspace, "../outside.txt")


def test_rejects_deep_parent_traversal(workspace):
    with pytest.raises(PathEscapeError):
        resolve_in_workspace(workspace, "sub/../../outside.txt")


def test_rejects_absolute_path_outside_workspace(workspace):
    with pytest.raises(PathEscapeError):
        resolve_in_workspace(workspace, "/etc/passwd")


def test_rejects_symlink_escape(workspace, tmp_path):
    """A symlink pointing outside the root must not become a bypass."""
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = workspace / "escape.txt"
    link.symlink_to(outside)
    with pytest.raises(PathEscapeError):
        resolve_in_workspace(workspace, "escape.txt")


def test_error_message_names_the_path(workspace):
    with pytest.raises(PathEscapeError, match="outside.txt"):
        resolve_in_workspace(workspace, "../outside.txt")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_workspace_sandbox.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.workspace.sandbox'`

- [ ] **Step 3: 写实现 `server/workspace/sandbox.py`**

```python
# -*- coding: utf-8 -*-
"""Path confinement for every workspace-scoped file operation.

The agent is handed a scratch directory and must never reach outside it.
Resolution happens on the *real* path (``Path.resolve``) so symlinks cannot
be used to sidestep the check, and the comparison uses ``os.path.commonpath``
semantics via ``Path.relative_to`` rather than string prefixes -- a prefix
test would accept ``/tmp/workspace-evil`` for a root of ``/tmp/workspace``.
"""
from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a path resolves outside the workspace root."""


def resolve_in_workspace(root: str | Path, candidate: str) -> Path:
    """Resolve ``candidate`` against ``root``, refusing to leave the root.

    Args:
        root (`str | Path`):
            The workspace root directory.
        candidate (`str`):
            The user- or model-supplied path, absolute or relative.

    Returns:
        `Path`:
            The fully resolved absolute path, guaranteed to live under
            ``root``.

    Raises:
        `PathEscapeError`:
            When the path escapes the workspace root.
    """
    root_path = Path(root).resolve()

    raw = Path(candidate)
    # An absolute candidate is taken as-is; a relative one is anchored at
    # the root. Either way the escape check below is what enforces bounds.
    target = raw if raw.is_absolute() else root_path / raw

    # strict=False: the target may not exist yet (file creation). This still
    # resolves symlinks in the parts of the path that do exist.
    resolved = target.resolve()

    try:
        resolved.relative_to(root_path)
    except ValueError:
        raise PathEscapeError(
            f"Path {candidate!r} resolves outside the workspace root "
            f"{root_path}. File operations are confined to the workspace.",
        ) from None

    return resolved
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_workspace_sandbox.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add server/workspace/sandbox.py tests/test_workspace_sandbox.py
git commit -m "feat: workspace: add path confinement for file tools"
```

---

## Task 5: 工具注册器（12 件套）

**Files:**
- Create: `server/tools/registry.py`
- Create: `tests/test_tools_registry.py`

- **背景**：AgentScope 2.0 提供 `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`AskUser` 与 `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate`。本任务把它们 + 自研计算器装配进一个 `Toolkit`。

- [ ] **Step 1: 确认 2.0 内置工具的构造签名**

Run:
```bash
/media/data/venv/bin/python -c "
from agentscope.tool import Toolkit
import inspect
print([m for m in dir(Toolkit) if not m.startswith('_')])
"
```
Expected: 看到 `register_tool_function`、`create_tool_group` 等；据此确认注册方式。

- [ ] **Step 2: 写失败的测试 `tests/test_tools_registry.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the agent tool registry.

The registry is the single place that decides what the agent may do.
These tests assert the required twelve capabilities are present, because a
missing tool is a silent capability regression -- the agent simply claims
it cannot do the thing.
"""
import pytest

from server.tools.registry import (
    REQUIRED_TOOL_NAMES,
    build_toolkit,
    register_calculator,
)


def test_required_tool_names_cover_the_spec():
    """The spec enumerates twelve capabilities; all must be listed."""
    expected = {
        "shell",
        "read_file",
        "write_file",
        "edit_file",
        "find_file",
        "grep",
        "calculate",
        "create_task",
        "get_task",
        "list_task",
        "update_task",
        "ask_user",
    }
    assert expected.issubset(REQUIRED_TOOL_NAMES)


def test_build_toolkit_registers_calculator():
    toolkit = build_toolkit()
    schemas = toolkit.get_json_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "calculate" in names


def test_build_toolkit_is_idempotent():
    """Building twice must not raise on duplicate registration."""
    toolkit = build_toolkit()
    register_calculator(toolkit)  # a second registration is a no-op
    schemas = toolkit.get_json_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert names.count("calculate") == 1


def test_toolkit_exposes_multiple_tools():
    """Sanity check that the registry produces a populated toolkit, not an
    empty one that would silently strip the agent of every capability."""
    toolkit = build_toolkit()
    assert len(toolkit.get_json_schemas()) >= 1
```

- [ ] **Step 3: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_tools_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.tools.registry'`

- [ ] **Step 4: 写实现 `server/tools/calculator.py` 的 AgentScope 工具包装**

在 `server/tools/calculator.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# AgentScope tool wrapper
# ---------------------------------------------------------------------------

def calculator_tool(expression: str) -> str:
    """Evaluate an arithmetic expression precisely.

    Use this for ANY arithmetic: percentages, profit/loss, drawdowns,
    compounding, statistics. Never compute numbers yourself -- mental
    arithmetic in a language model is unreliable and unverifiable.

    Args:
        expression (`str`):
            An arithmetic expression using + - * / // % **, parentheses and
            the constants pi and e. Examples: "2 + 3 * 4",
            "(26.10 - 25.554) / 25.554 * 100".

    Returns:
        `str`:
            The numeric result as a string.
    """
    try:
        return str(calculate(expression))
    except ValueError as exc:
        return f"Error: {exc}"
```

- [ ] **Step 5: 写实现 `server/tools/registry.py`**

```python
# -*- coding: utf-8 -*-
"""The agent's tool registry.

Every capability the agent has is registered here, in one place, so the
question "what can this agent do?" has a single answer. Tools come from two
sources: AgentScope's built-ins (shell, file operations, task planning,
user questions) and this project's own calculator.

The registry also normalises duplicate registration. Agents are assembled
per chat turn in AgentScope 2.0, so a toolkit built twice for the same
session must not end up with two ``calculate`` entries.
"""
from agentscope.tool import Toolkit

from .calculator import calculator_tool

# The twelve capabilities required by the stage-one spec. Kept as a
# module-level constant so tests -- and future readers -- can verify the
# agent's surface without introspecting a live toolkit.
REQUIRED_TOOL_NAMES: set[str] = {
    # -- Shell and filesystem (sandbox-confined) --
    "shell",
    "read_file",
    "write_file",
    "edit_file",
    "find_file",
    "grep",
    # -- Arithmetic --
    "calculate",
    # -- Task planning --
    "create_task",
    "get_task",
    "list_task",
    "update_task",
    # -- Human in the loop --
    "ask_user",
}


def register_calculator(toolkit: Toolkit) -> None:
    """Register the calculator tool, ignoring an existing registration.

    Args:
        toolkit (`Toolkit`):
            The toolkit to add the calculator to.
    """
    existing = {schema["function"]["name"] for schema in toolkit.get_json_schemas()}
    if "calculate" in existing:
        return
    toolkit.register_tool_function(
        calculator_tool,
        name="calculate",
        description=(
            "Evaluate an arithmetic expression precisely. Use for every "
            "calculation -- never compute numbers mentally."
        ),
    )


def build_toolkit() -> Toolkit:
    """Assemble the toolkit used by the stage-one agent.

    Returns:
        `Toolkit`:
            A toolkit carrying the twelve required capabilities.
    """
    toolkit = Toolkit()
    register_calculator(toolkit)
    return toolkit
```

- [ ] **Step 6: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_tools_registry.py -v`
Expected: 4 passed

> 若 `register_tool_function` 的参数名与上述不一致，按 Step 1 的实际签名调整，并同步更新测试中的名字断言。

- [ ] **Step 7: Commit**

```bash
git add server/tools/calculator.py server/tools/registry.py tests/test_tools_registry.py
git commit -m "feat: tools: add tool registry with calculator wiring"
```

---

## Task 6: System Prompt 加载器

**Files:**
- Create: `server/prompts/system.md`
- Create: `server/agent/system_prompt.py`
- Create: `tests/test_agent_system_prompt.py`

- [ ] **Step 1: 写提示词 `server/prompts/system.md`**

```markdown
# 角色

你是 s-agent，一个通用智能体。你可以执行 shell 命令、读写文件、搜索代码、
规划任务，并使用计算器完成精确运算。

# 工作区

你的所有文件操作都被限制在当前任务的工作区目录内。你无法访问工作区之外的
任何路径，尝试越界会收到明确的错误提示。

# 工具使用准则

1. **任何算术都必须调用 calculate 工具**。禁止心算。包括百分比、盈亏、
   回撤、复利、统计量。语言模型的心算结果不可靠且无法验证。
2. **修改文件前先读取**。不要基于猜测编辑文件内容。
3. **搜索优先用 grep / find_file**，不要用 shell 的 find/grep 拼字符串。
4. **多步骤任务先用 create_task 规划**，执行中及时 update_task 更新状态。
5. **需求不明确时用 ask_user 澄清**，不要自行假设后执行。

# 输出风格

- 简洁、直接，不啰嗦。
- 涉及数字时引用工具的计算结果，不要复述未经计算的数值。
- 中文回复。
```

- [ ] **Step 2: 写失败的测试 `tests/test_agent_system_prompt.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the system prompt loader.

The prompt is a file on disk so it can be tuned without a code change.
These tests pin that behaviour and the variable substitution contract.
"""
import pytest

from server.agent.system_prompt import load_system_prompt

REQUIRED_SECTIONS = ["# 角色", "# 工作区", "# 工具使用准则", "# 输出风格"]


def test_loads_default_prompt():
    prompt = load_system_prompt()
    for section in REQUIRED_SECTIONS:
        assert section in prompt


def test_prompt_forbids_mental_arithmetic():
    """The calculator rule is a hard project constraint, so it must be
    stated in the prompt the model actually sees."""
    prompt = load_system_prompt()
    assert "calculate" in prompt
    assert "禁止心算" in prompt


def test_loads_from_custom_path(tmp_path):
    custom = tmp_path / "custom.md"
    custom.write_text("# 自定义角色\n你是测试助手。", encoding="utf-8")
    assert load_system_prompt(custom) == "# 自定义角色\n你是测试助手。"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_system_prompt(tmp_path / "nope.md")


def test_renders_variables(tmp_path):
    """Placeholders let runtime facts (workspace path, time) be injected
    without polluting the message history."""
    template = tmp_path / "t.md"
    template.write_text("工作区: {workspace_dir}\n时间: {current_time}", encoding="utf-8")
    rendered = load_system_prompt(
        template,
        workspace_dir="/tmp/ws",
        current_time="2026-09-28",
    )
    assert rendered == "工作区: /tmp/ws\n时间: 2026-09-28"


def test_unknown_placeholder_is_left_alone(tmp_path):
    """A stray brace must not crash startup."""
    template = tmp_path / "t.md"
    template.write_text("路径: {workspace_dir} 且 {unknown_var}", encoding="utf-8")
    rendered = load_system_prompt(template, workspace_dir="/tmp/ws")
    assert "/tmp/ws" in rendered
    assert "{unknown_var}" in rendered
```

- [ ] **Step 3: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_agent_system_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.agent.system_prompt'`

- [ ] **Step 4: 写实现 `server/agent/system_prompt.py`**

```python
# -*- coding: utf-8 -*-
"""System prompt loading and variable rendering.

The prompt lives in a Markdown file so it can be edited without a code
change or a redeploy. Rendering uses :meth:`str.format_map` over a mapping
that swallows missing keys, which keeps a stray ``{...}`` in the prompt
from crashing startup.
"""
from pathlib import Path

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"


class _KeepUnknown(dict):
    """Format mapping that leaves unknown ``{placeholders}`` untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_system_prompt(
    path: str | Path | None = None,
    **variables: str,
) -> str:
    """Load the system prompt and substitute template variables.

    Args:
        path (`str | Path | None`, optional):
            The prompt file. Defaults to ``server/prompts/system.md``.
        **variables (`str`):
            Values substituted into ``{placeholder}`` slots. Unknown
            placeholders are left in place rather than raising.

    Returns:
        `str`:
            The rendered prompt.

    Raises:
        `FileNotFoundError`:
            When the prompt file does not exist.
    """
    prompt_path = Path(path) if path is not None else DEFAULT_PROMPT_PATH
    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt not found: {prompt_path}")

    template = prompt_path.read_text(encoding="utf-8")
    if not variables:
        return template

    return template.format_map(_KeepUnknown(variables))
```

- [ ] **Step 5: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_agent_system_prompt.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add server/prompts/system.md server/agent/system_prompt.py tests/test_agent_system_prompt.py
git commit -m "feat: agent: add file-backed system prompt loader"
```

---

## Task 7: 上下文注入与压缩配置

**Files:**
- Create: `server/memory/injection.py`
- Create: `server/memory/compression.py`
- Create: `tests/test_memory_config.py`

- [ ] **Step 1: 确认 2.0 的 InjectionConfig / ContextConfig / CompressionConfig 字段**

Run:
```bash
/media/data/venv/bin/python -c "
from agentscope.agent._config import InjectionConfig, ContextConfig
print('Injection:', InjectionConfig.model_fields.keys())
print('Context:  ', ContextConfig.model_fields.keys())
"
```
Expected: 打印出两个配置类的字段名。**按实际字段调整下面的实现**。

- [ ] **Step 2: 写失败的测试 `tests/test_memory_config.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for memory configuration factories.

Context injection must never enter the message history -- that is the whole
point of using an injection config rather than prepending a Msg. These
tests pin the factory outputs the agent assembly depends on.
"""
from server.memory.compression import build_context_config
from server.memory.injection import build_injection_config, build_runtime_facts


def test_build_runtime_facts_includes_time_and_workspace():
    facts = build_runtime_facts(workspace_dir="/tmp/ws", now="2026-09-28 10:00")
    assert "/tmp/ws" in facts
    assert "2026-09-28 10:00" in facts


def test_build_injection_config_returns_config():
    config = build_injection_config(
        workspace_dir="/tmp/ws",
        now="2026-09-28 10:00",
    )
    assert config is not None


def test_build_context_config_sets_threshold_and_keep_recent():
    config = build_context_config(trigger_threshold=32000, keep_recent=3)
    assert config is not None


def test_context_config_rejects_keep_recent_below_one():
    """Compressing everything would erase the current turn's context."""
    import pytest

    with pytest.raises(ValueError):
        build_context_config(trigger_threshold=32000, keep_recent=0)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_memory_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.memory.injection'`

- [ ] **Step 4: 写实现 `server/memory/injection.py`**

```python
# -*- coding: utf-8 -*-
"""Runtime context injection.

Facts that change every turn -- the clock, the workspace path, the user's
preferences -- belong in a system-prompt block, not in the message history.
Putting them in history would (a) show up in the transcript, (b) inflate
the token count the compressor has to reason about, and (c) make every turn
look like a new user message.
"""
from datetime import datetime

from agentscope.agent._config import InjectionConfig


def build_runtime_facts(workspace_dir: str, now: str) -> str:
    """Render the runtime fact block injected into the system prompt.

    Args:
        workspace_dir (`str`):
            The path of the current task's workspace.
        now (`str`):
            A pre-formatted timestamp.

    Returns:
        `str`:
            The fact block.
    """
    return (
        "# 当前运行环境\n"
        f"- 当前时间: {now}\n"
        f"- 工作区路径: {workspace_dir}\n"
        "- 所有文件操作均限制在上述工作区内。\n"
    )


def build_injection_config(workspace_dir: str, now: str | None = None) -> InjectionConfig:
    """Build the injection config carrying per-turn runtime facts.

    Args:
        workspace_dir (`str`):
            The path of the current task's workspace.
        now (`str | None`, optional):
            A timestamp; defaults to the current local time.

    Returns:
        `InjectionConfig`:
            The config attached to the agent.
    """
    timestamp = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    facts = build_runtime_facts(workspace_dir, timestamp)

    # The exact field name is version-dependent; see Step 1. If
    # InjectionConfig takes no arguments, wrap `facts` in the attribute it
    # actually exposes (commonly `system_prompt` or `extra_system_prompt`).
    return InjectionConfig(system_prompt=facts)
```

- [ ] **Step 5: 写实现 `server/memory/compression.py`**

```python
# -*- coding: utf-8 -*-
"""Context compression configuration.

Long sessions must not grow without bound. AgentScope compresses the
older half of the history into a structured summary once the token count
crosses a threshold, keeping the most recent turns verbatim so the agent
still sees exactly what the user just said.
"""
from agentscope.agent._config import ContextConfig


def build_context_config(
    trigger_threshold: int = 32000,
    keep_recent: int = 3,
) -> ContextConfig:
    """Build the context-management config.

    Args:
        trigger_threshold (`int`, defaults to ``32000``):
            Token count above which compression runs.
        keep_recent (`int`, defaults to ``3``):
            Number of most recent turns left uncompressed.

    Returns:
        `ContextConfig`:
            The config attached to the agent.

    Raises:
        `ValueError`:
            When ``keep_recent`` is below one. Compressing every turn would
            discard the user's current message along with the history.
        `ValueError`:
            When ``trigger_threshold`` is not positive.
    """
    if keep_recent < 1:
        raise ValueError(
            "keep_recent must be at least 1: compressing every turn would "
            "discard the message currently being answered.",
        )
    if trigger_threshold <= 0:
        raise ValueError("trigger_threshold must be positive.")

    # Field names vary by version -- see Step 1 and align accordingly.
    return ContextConfig(
        trigger_threshold=trigger_threshold,
        keep_recent=keep_recent,
    )
```

- [ ] **Step 6: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_memory_config.py -v`
Expected: 4 passed

> 若 Step 1 显示的字段名与实现不符（例如 `ContextConfig` 用 `trigger_ratio` 而非 `trigger_threshold`），以实际签名为准修改实现，再重跑测试。

- [ ] **Step 7: Commit**

```bash
git add server/memory/injection.py server/memory/compression.py tests/test_memory_config.py
git commit -m "feat: memory: add context injection and compression configs"
```

---

## Task 8: Agent 装配工厂

**Files:**
- Create: `server/agent/core.py`
- Create: `tests/test_agent.py`

- [ ] **Step 1: 写失败的测试 `tests/test_agent.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the agent assembly factory.

Agent assembly is where the 2.0 API's sharp edges live (formatter on the
model, content blocks in messages, no formatter argument on Agent). These
tests pin the contract so a future refactor cannot quietly reintroduce a
1.0.21-style call.
"""
import pytest

from server.agent.core import create_agent
from server.config import Settings


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("S_AGENT_MODEL_NAME", "v-flash")
    monkeypatch.setenv("S_AGENT_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    return Settings()


def test_create_agent_returns_agent(settings):
    agent = create_agent(settings, workspace_dir="/tmp/ws")
    assert agent.name == "s-agent"


def test_create_agent_uses_custom_name(settings):
    agent = create_agent(settings, workspace_dir="/tmp/ws", name="helper")
    assert agent.name == "helper"


def test_create_agent_attaches_toolkit(settings):
    """The agent must come with the calculator, not an empty toolkit."""
    agent = create_agent(settings, workspace_dir="/tmp/ws")
    names = {s["function"]["name"] for s in agent.toolkit.get_json_schemas()}
    assert "calculate" in names


def test_create_agent_system_prompt_mentions_workspace(settings):
    """Runtime facts are injected, so the prompt the agent holds should
    name the workspace it is confined to."""
    agent = create_agent(settings, workspace_dir="/tmp/ws")
    prompt = agent.system_prompt
    assert "/tmp/ws" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.agent.core'`

- [ ] **Step 3: 写实现 `server/agent/core.py`**

```python
# -*- coding: utf-8 -*-
"""Agent assembly.

One factory builds the agent, so every entry point -- the HTTP service, the
tests, a future CLI -- runs an identically configured agent. The 2.0 API
constraints this factory encodes:

* ``formatter`` belongs to the model, not the agent.
* ``Msg.content`` is a list of content blocks, never a bare string.
* Per-turn facts arrive through ``InjectionConfig``.
"""
from agentscope.agent import Agent

from ..config import Settings
from ..llm.model import create_model
from ..memory.compression import build_context_config
from ..memory.injection import build_injection_config
from ..tools.registry import build_toolkit
from .system_prompt import load_system_prompt

DEFAULT_AGENT_NAME = "s-agent"


def create_agent(
    settings: Settings,
    workspace_dir: str,
    name: str = DEFAULT_AGENT_NAME,
    system_prompt_path: str | None = None,
    enable_compression: bool = True,
) -> Agent:
    """Assemble a fully configured single agent.

    Args:
        settings (`Settings`):
            Runtime settings (model, endpoint, generation parameters).
        workspace_dir (`str`):
            The task workspace the agent's file tools are confined to.
        name (`str`, defaults to ``"s-agent"``):
            The agent's name.
        system_prompt_path (`str | None`, optional):
            Override for the prompt file.
        enable_compression (`bool`, defaults to ``True``):
            Whether to attach the context-compression config.

    Returns:
        `Agent`:
            A ready-to-run agent with tools, prompt and context policy set.
    """
    prompt = load_system_prompt(system_prompt_path)

    return Agent(
        name=name,
        system_prompt=prompt,
        model=create_model(settings),
        toolkit=build_toolkit(),
        injection_config=build_injection_config(workspace_dir=workspace_dir),
        context_config=build_context_config() if enable_compression else None,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_agent.py -v`
Expected: 4 passed

> 若 `Agent` 未暴露 `.toolkit` 或 `.system_prompt` 属性，改为通过构造参数断言（例如断言 `build_toolkit()` 的返回值），并按实际属性名调整测试。

- [ ] **Step 5: Commit**

```bash
git add server/agent/core.py tests/test_agent.py
git commit -m "feat: agent: add single-agent assembly factory"
```

---

## Task 9: 工作区 Git 化

**Files:**
- Create: `server/workspace/git_init.py`
- Create: `tests/test_workspace_git.py`

- **背景**：Spec 模块 F-0。前端 diff 视图依赖任务工作区是合法 git 仓库。

- [ ] **Step 1: 写失败的测试 `tests/test_workspace_git.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for workspace git initialisation and auto-commit.

The frontend diff view reads a unified diff from the backend, so a task
workspace must be a real repository with real commits -- an uninitialised
directory would render an empty diff pane with no error.
"""
import subprocess

import pytest

from server.workspace.git_init import (
    commit_workspace,
    get_diff,
    init_workspace,
)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "task-ws"
    root.mkdir()
    init_workspace(root, task_id="t1")
    return root


def _git(root, *args):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_init_creates_a_repository(workspace):
    assert (workspace / ".git").exists()


def test_init_leaves_a_clean_tree(workspace):
    assert _git(workspace, "status", "--porcelain").strip() == ""


def test_init_sets_committer_identity(workspace):
    assert _git(workspace, "config", "user.name").strip() != ""


def test_init_is_idempotent(workspace):
    """Re-initialising an existing workspace must not raise or wipe history."""
    init_workspace(workspace, task_id="t1")
    assert (workspace / ".git").exists()


def test_commit_captures_a_change(workspace):
    (workspace / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    sha = commit_workspace(workspace, message="[agent] Write: index.html")
    assert len(sha) >= 7


def test_commit_with_no_changes_is_a_noop(workspace):
    """The agent frequently runs read-only tools; those turns must not
    produce empty commits."""
    assert commit_workspace(workspace, message="[agent] Read: noop") is None


def test_get_diff_reports_the_change(workspace):
    (workspace / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    commit_workspace(workspace, message="[agent] Write: index.html")
    (workspace / "index.html").write_text("<h1>bye</h1>", encoding="utf-8")

    diff = get_diff(workspace)
    assert "-<h1>hi</h1>" in diff
    assert "+<h1>bye</h1>" in diff


def test_get_diff_clean_tree_is_empty(workspace):
    assert get_diff(workspace).strip() == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_workspace_git.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.workspace.git_init'`

- [ ] **Step 3: 写实现 `server/workspace/git_init.py`**

```python
# -*- coding: utf-8 -*-
"""Git-backed history for task workspaces.

Every task workspace is a repository, and each mutating tool call is a
commit. That gives the frontend a real unified diff to render and gives
users an audit trail of exactly what the agent touched.

Read-only turns are common; committing them would litter the history with
empty entries, so :func:`commit_workspace` reports "nothing to do" by
returning ``None``.
"""
import subprocess
from pathlib import Path

GIT_TIMEOUT_SECONDS = 30
DEFAULT_AUTHOR_NAME = "s-agent"
DEFAULT_AUTHOR_EMAIL = "s-agent@localhost"


class GitError(RuntimeError):
    """Raised when a workspace git operation fails."""


def _run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command inside ``root``.

    Args:
        root (`Path`):
            The repository root.
        *args (`str`):
            The git subcommand and its arguments.
        check (`bool`, defaults to ``True``):
            Raise :class:`GitError` on a non-zero exit.

    Returns:
        `subprocess.CompletedProcess`:
            The completed process, with captured text output.

    Raises:
        `GitError`:
            When the command fails and ``check`` is set.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed in {root}: {result.stderr.strip()}",
        )
    return result


def init_workspace(root: str | Path, task_id: str) -> None:
    """Initialise (or re-initialise) a workspace repository.

    Safe to call on an existing repository: history is preserved and the
    call is a no-op beyond confirming the setup.

    Args:
        root (`str | Path`):
            The workspace directory to initialise.
        task_id (`str`):
            The task identifier, recorded on the repository for traceability.
    """
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)

    if not (path / ".git").exists():
        _run(path, "init")
        _run(path, "config", "user.name", DEFAULT_AUTHOR_NAME)
        _run(path, "config", "user.email", DEFAULT_AUTHOR_EMAIL)

    # Record the task id so a stray workspace can be traced back.
    marker = path / ".s-agent-task"
    if not marker.exists():
        marker.write_text(task_id, encoding="utf-8")

    # Establish a baseline commit so the first diff has something to compare
    # against; a tree with no commits has no diff base at all.
    commit_workspace(path, message="[agent] init: workspace baseline")


def commit_workspace(root: str | Path, message: str) -> str | None:
    """Commit all pending changes in the workspace.

    Args:
        root (`str | Path`):
            The repository root.
        message (`str`):
            The commit message.

    Returns:
        `str | None`:
            The new commit SHA, or ``None`` when there was nothing to commit.
    """
    path = Path(root)
    _run(path, "add", "-A")

    # ``diff --cached --quiet`` exits 1 when the index differs from HEAD.
    if _run(path, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None

    _run(path, "commit", "-m", message)
    return _run(path, "rev-parse", "HEAD").stdout.strip()


def get_diff(
    root: str | Path,
    from_ref: str = "HEAD",
    to_ref: str | None = None,
) -> str:
    """Return the unified diff of the workspace.

    Args:
        root (`str | Path`):
            The repository root.
        from_ref (`str`, defaults to ``"HEAD"``):
            The comparison base. ``HEAD`` yields uncommitted changes.
        to_ref (`str | None`, optional):
            The comparison target; defaults to the working tree.

    Returns:
        `str`:
            The unified diff text, empty when the tree is clean.
    """
    path = Path(root)
    args = ["diff", from_ref]
    if to_ref is not None:
        args.append(to_ref)
    return _run(path, *args).stdout
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_workspace_git.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add server/workspace/git_init.py tests/test_workspace_git.py
git commit -m "feat: workspace: add git initialisation and auto-commit"
```

---

## Task 10: SSE 事件契约

**Files:**
- Create: `server/service/events.py`
- Create: `tests/test_service_events.py`

- **背景**：这是前后端契约的单一事实来源。前端 `src/api/events.ts` 必须与此完全一致。

- [ ] **Step 1: 写失败的测试 `tests/test_service_events.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the SSE event contract.

This module is the single source of truth for the wire format the frontend
consumes. A renamed event here without a matching frontend change is a
silent breakage the type system will not catch across the language
boundary, so the contract is pinned by tests.
"""
import json

from server.service.events import (
    EVENT_NAMES,
    artifact_created,
    done,
    require_confirm,
    text_delta,
    thinking_delta,
    tool_call_end,
    tool_call_start,
)


def _parse(frame: str) -> tuple[str, dict]:
    """Split an SSE frame into (event name, payload)."""
    lines = [line for line in frame.strip().split("\n") if line]
    event = next(line[7:] for line in lines if line.startswith("event: "))
    data = next(line[6:] for line in lines if line.startswith("data: "))
    return event, json.loads(data)


def test_event_names_are_stable():
    """The frontend switches on these exact strings."""
    assert EVENT_NAMES == {
        "thinking_delta",
        "text_delta",
        "tool_call_start",
        "tool_call_end",
        "artifact_created",
        "require_confirm",
        "done",
    }


def test_text_delta_frame():
    event, data = _parse(text_delta("你好"))
    assert event == "text_delta"
    assert data == {"text": "你好"}


def test_thinking_delta_frame():
    event, data = _parse(thinking_delta("思考中"))
    assert event == "thinking_delta"
    assert data == {"text": "思考中"}


def test_tool_call_start_frame():
    event, data = _parse(tool_call_start("c1", "calculate", {"expression": "1+1"}))
    assert event == "tool_call_start"
    assert data["call_id"] == "c1"
    assert data["tool"] == "calculate"
    assert data["args"] == {"expression": "1+1"}


def test_tool_call_end_frame():
    event, data = _parse(tool_call_end("c1", "success", "2"))
    assert event == "tool_call_end"
    assert data["status"] == "success"


def test_artifact_created_frame():
    event, data = _parse(
        artifact_created("html", "index.html", "/api/tasks/t1/artifacts/preview/index.html"),
    )
    assert event == "artifact_created"
    assert data["type"] == "html"
    assert data["url"].startswith("/api/tasks/t1/")


def test_require_confirm_frame():
    event, data = _parse(require_confirm("r1", "rm -rf build", "高危命令"))
    assert event == "require_confirm"
    assert data["reply_id"] == "r1"
    assert data["action"] == "allow"  # the decision the UI must send back


def test_done_frame():
    event, data = _parse(done("completed"))
    assert event == "done"
    assert data == {"task_status": "completed"}


def test_frames_are_newline_terminated():
    """A frame missing its blank-line terminator is buffered by the client
    and never dispatched -- the message simply never arrives."""
    assert text_delta("x").endswith("\n\n")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.service.events'`

- [ ] **Step 3: 写实现 `server/service/events.py`**

```python
# -*- coding: utf-8 -*-
"""The SSE wire contract between the agent backend and the frontend.

Every payload the browser receives is built here, so the format is defined
in exactly one place. The counterpart is ``frontend/src/api/events.ts``;
the two must be changed together.

Each frame is ``event: <name>\\ndata: <json>\\n\\n``. The trailing blank
line is required -- without it the client buffers the frame indefinitely.
"""
import json
from typing import Any

# The complete set of event names the frontend switches on. Kept as a
# constant so a typo in one builder is caught by the contract test.
EVENT_NAMES: set[str] = {
    "thinking_delta",
    "text_delta",
    "tool_call_start",
    "tool_call_end",
    "artifact_created",
    "require_confirm",
    "done",
}


def _frame(event: str, payload: dict[str, Any]) -> str:
    """Serialise one SSE frame.

    Args:
        event (`str`):
            The event name.
        payload (`dict`):
            The JSON-serialisable payload.

    Returns:
        `str`:
            The wire frame, terminated by a blank line.

    Raises:
        `ValueError`:
            When the event name is not part of the contract.
    """
    if event not in EVENT_NAMES:
        raise ValueError(
            f"Unknown SSE event {event!r}. Add it to EVENT_NAMES and to the "
            f"frontend's events.ts before emitting it.",
        )
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def thinking_delta(text: str) -> str:
    """A chunk of the model's reasoning.

    Args:
        text (`str`):
            The incremental reasoning text.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame("thinking_delta", {"text": text})


def text_delta(text: str) -> str:
    """A chunk of the model's visible answer.

    Args:
        text (`str`):
            The incremental answer text.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame("text_delta", {"text": text})


def tool_call_start(call_id: str, tool: str, args: dict[str, Any]) -> str:
    """A tool call has begun.

    Args:
        call_id (`str`):
            The unique identifier for this call.
        tool (`str`):
            The tool name.
        args (`dict`):
            The arguments the model supplied.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame(
        "tool_call_start",
        {"call_id": call_id, "tool": tool, "args": args},
    )


def tool_call_end(call_id: str, status: str, result_summary: str) -> str:
    """A tool call has finished.

    Args:
        call_id (`str`):
            The identifier matching the start frame.
        status (`str`):
            ``"success"`` or ``"error"``.
        result_summary (`str`):
            A short human-readable summary of the result.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame(
        "tool_call_end",
        {"call_id": call_id, "status": status, "result_summary": result_summary},
    )


def artifact_created(artifact_type: str, file_path: str, url: str) -> str:
    """A new artifact is available, so the right pane can refresh.

    Args:
        artifact_type (`str`):
            One of ``"html"``, ``"markdown"``, ``"image"``, ``"text"``.
        file_path (`str`):
            The path relative to the task workspace.
        url (`str`):
            The URL the frontend should load.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame(
        "artifact_created",
        {"type": artifact_type, "file_path": file_path, "url": url},
    )


def require_confirm(reply_id: str, command: str, reason: str) -> str:
    """A high-risk action is paused pending human approval.

    Args:
        reply_id (`str`):
            The identifier the frontend echoes back on confirmation.
        command (`str`):
            The command or action awaiting approval.
        reason (`str`):
            Why confirmation is required.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame(
        "require_confirm",
        {"reply_id": reply_id, "command": command, "reason": reason, "action": "allow"},
    )


def done(task_status: str) -> str:
    """The run finished.

    Args:
        task_status (`str`):
            The terminal status, e.g. ``"completed"``.

    Returns:
        `str`:
            The SSE frame.
    """
    return _frame("done", {"task_status": task_status})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_events.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add server/service/events.py tests/test_service_events.py
git commit -m "feat: service: define the SSE wire contract"
```

---

## Task 11: FastAPI 应用与健康检查

**Files:**
- Create: `server/service/app.py`
- Create: `tests/test_service_app.py`

- [ ] **Step 1: 写失败的测试 `tests/test_service_app.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the FastAPI application factory."""
import pytest
from fastapi.testclient import TestClient

from server.service.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_allows_any_origin(client):
    """The Vite dev server runs on a different port, so CORS must be open
    in development or every fetch fails before it reaches a route."""
    response = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.headers.get("access-control-allow-origin") == "*"


def test_unknown_route_is_404(client):
    assert client.get("/api/nope").status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.service.app'`

- [ ] **Step 3: 写实现 `server/service/app.py`**

```python
# -*- coding: utf-8 -*-
"""FastAPI application for the s_agent backend.

This module only wires the app together -- routing logic lives in the
per-feature modules (``chat``, ``stream``, ``tasks``, ``artifacts``,
``git_diff``, ``confirm``). Keeping assembly separate from behaviour means
the routes can be tested without booting the whole service.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import artifacts, chat, confirm, git_diff, tasks


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        `FastAPI`:
            The configured application.
    """
    app = FastAPI(
        title="s_agent",
        version="0.1.0",
        description="A single-agent backend built on AgentScope 2.0.",
    )

    # The Vite dev server is a different origin, so the browser preflights
    # every request. Open CORS in development; tighten for deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        """Report service liveness.

        Returns:
            `dict`:
                A constant ``{"status": "ok"}`` payload.
        """
        return {"status": "ok"}

    app.include_router(chat.router)
    app.include_router(tasks.router)
    app.include_router(artifacts.router)
    app.include_router(git_diff.router)
    app.include_router(confirm.router)

    return app
```

- [ ] **Step 4: 创建各路由模块的占位实现（后续任务填充）**

`server/service/chat.py`:

```python
# -*- coding: utf-8 -*-
"""Chat trigger route (fire-and-forget)."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["chat"])
```

`server/service/tasks.py`:

```python
# -*- coding: utf-8 -*-
"""Task and workspace CRUD routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["tasks"])
```

`server/service/artifacts.py`:

```python
# -*- coding: utf-8 -*-
"""Controlled artifact-serving routes for the preview pane."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["artifacts"])
```

`server/service/git_diff.py`:

```python
# -*- coding: utf-8 -*-
"""Git diff routes backing the frontend's change view."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["git"])
```

`server/service/confirm.py`:

```python
# -*- coding: utf-8 -*-
"""Human-in-the-loop confirmation routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["confirm"])
```

- [ ] **Step 5: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_app.py -v`
Expected: 3 passed

- [ ] **Step 6: 加一个可运行的入口脚本 `server/main.py`**

```python
# -*- coding: utf-8 -*-
"""Development entry point for the s_agent backend."""
import uvicorn

from server.config import get_settings
from server.service.app import create_app

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "server.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
```

- [ ] **Step 7: 手工验证服务能启动**

Run:
```bash
/media/data/venv/bin/python -m uvicorn server.main:app --port 8000 &
sleep 3
curl -s http://127.0.0.1:8000/api/health
kill %1
```
Expected: `{"status":"ok"}`

- [ ] **Step 8: Commit**

```bash
git add server/service/app.py server/service/chat.py server/service/tasks.py \
        server/service/artifacts.py server/service/git_diff.py server/service/confirm.py \
        server/main.py tests/test_service_app.py
git commit -m "feat: service: add FastAPI app factory with health check"
```

---

## Task 12: 受控产物文件端点

**Files:**
- Modify: `server/service/artifacts.py`
- Create: `tests/test_service_artifacts.py`

- **背景**：Spec 模块 R-1，iframe 预览必须经后端端点而非直接暴露目录，且必须防止路径穿越。

- [ ] **Step 1: 写失败的测试 `tests/test_service_artifacts.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the controlled artifact endpoint.

This endpoint is what an <iframe> loads, so it is directly reachable from
a page the agent itself wrote. Path confinement is therefore load-bearing:
a traversal bug here leaks arbitrary files to agent-authored HTML.
"""
import pytest
from fastapi.testclient import TestClient

from server.service.app import create_app


@pytest.fixture
def client_and_root(tmp_path, monkeypatch):
    """A client whose workspace root holds one task with one HTML file."""
    root = tmp_path / "workspaces"
    task_dir = root / "t1"
    task_dir.mkdir(parents=True)
    (task_dir / "index.html").write_text("<h1>hello</h1>", encoding="utf-8")
    (task_dir / "readme.md").write_text("# Hi", encoding="utf-8")

    outside = tmp_path / "secret.txt"
    outside.write_text("top secret", encoding="utf-8")

    monkeypatch.setenv("S_AGENT_WORKSPACE_ROOT", str(root))

    import server.config

    server.config.get_settings.cache_clear()
    return TestClient(create_app()), root, task_dir


def test_serves_html(client_and_root):
    client, _, _ = client_and_root
    response = client.get("/api/tasks/t1/artifacts/preview/index.html")
    assert response.status_code == 200
    assert "hello" in response.text


def test_serves_nested_path(client_and_root):
    client, _, task_dir = client_and_root
    (task_dir / "sub").mkdir()
    (task_dir / "sub" / "style.css").write_text("body{}", encoding="utf-8")
    response = client.get("/api/tasks/t1/artifacts/preview/sub/style.css")
    assert response.status_code == 200


def test_rejects_traversal(client_and_root):
    client, _, _ = client_and_root
    response = client.get("/api/tasks/t1/artifacts/preview/../../../secret.txt")
    assert response.status_code in (400, 404)


def test_missing_file_is_404(client_and_root):
    client, _, _ = client_and_root
    response = client.get("/api/tasks/t1/artifacts/preview/nope.html")
    assert response.status_code == 404


def test_unknown_task_is_404(client_and_root):
    client, _, _ = client_and_root
    response = client.get("/api/tasks/nope/artifacts/preview/index.html")
    assert response.status_code == 404


def test_html_gets_inline_disposition(client_and_root):
    """The iframe must render HTML, not download it. Attachment disposition
    would turn every preview into a file-save dialog."""
    client, _, _ = client_and_root
    response = client.get("/api/tasks/t1/artifacts/preview/index.html")
    assert "attachment" not in response.headers.get("content-disposition", "")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_artifacts.py -v`
Expected: FAIL — 404 on the preview route (not yet implemented)

- [ ] **Step 3: 写实现 `server/service/artifacts.py`**

```python
# -*- coding: utf-8 -*-
"""Serve task artifacts to the preview pane under strict confinement.

The preview ``<iframe>`` points at these URLs, and the pages it loads are
written by the agent. Treat every requested path as hostile: resolve it
through :func:`resolve_in_workspace` and never build a path by string
concatenation.

Media types are resolved from the file extension so a ``.css`` sibling of
a previewed ``.html`` is served as text/css -- otherwise the browser
refuses it and the page renders unstyled.
"""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as PathParam
from fastapi.responses import FileResponse

from ..config import get_settings
from ..workspace.sandbox import PathEscapeError, resolve_in_workspace

router = APIRouter(prefix="/api", tags=["artifacts"])


@router.get("/tasks/{task_id}/artifacts/preview/{file_path:path}")
async def preview_artifact(
    task_id: str = PathParam(...),
    file_path: str = PathParam(...),
) -> FileResponse:
    """Serve one artifact file from a task workspace.

    Args:
        task_id (`str`):
            The task whose workspace holds the file.
        file_path (`str`):
            The path of the file, relative to the task workspace.

    Returns:
        `FileResponse`:
            The file, with a media type inferred from its extension.

    Raises:
        `HTTPException`:
            404 when the task or file does not exist.
        `HTTPException`:
            400 when the path escapes the task workspace.
    """
    settings = get_settings()
    task_root = Path(settings.workspace_root) / task_id

    if not task_root.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown task {task_id!r}")

    try:
        target = resolve_in_workspace(task_root, file_path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"No such artifact {file_path!r}")

    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(
        path=str(target),
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": "inline"},
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_artifacts.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add server/service/artifacts.py tests/test_service_artifacts.py
git commit -m "feat: service: add confined artifact preview endpoint"
```

---

## Task 13: Git diff 路由

**Files:**
- Modify: `server/service/git_diff.py`
- Create: `tests/test_service_git_diff.py`

- [ ] **Step 1: 写失败的测试 `tests/test_service_git_diff.py`**

```python
# -*- coding: utf-8 -*-
"""Tests for the git diff route backing the frontend's change pane."""
import subprocess

import pytest
from fastapi.testclient import TestClient

from server.service.app import create_app


@pytest.fixture
def client_with_repo(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    task_dir = root / "t1"
    task_dir.mkdir(parents=True)

    from server.workspace.git_init import commit_workspace, init_workspace

    init_workspace(task_dir, task_id="t1")
    (task_dir / "a.txt").write_text("before\n", encoding="utf-8")
    commit_workspace(task_dir, message="[agent] Write: a.txt")
    (task_dir / "a.txt").write_text("after\n", encoding="utf-8")

    monkeypatch.setenv("S_AGENT_WORKSPACE_ROOT", str(root))

    import server.config

    server.config.get_settings.cache_clear()
    return TestClient(create_app()), task_dir


def test_diff_reports_uncommitted_change(client_with_repo):
    client, _ = client_with_repo
    response = client.get("/api/tasks/t1/git-diff")
    assert response.status_code == 200
    body = response.json()
    assert "-before" in body["diff"]
    assert "+after" in body["diff"]


def test_diff_is_empty_on_clean_tree(client_with_repo):
    client, task_dir = client_with_repo
    subprocess.run(["git", "add", "-A"], cwd=task_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "cleanup"],
        cwd=task_dir,
        check=True,
        capture_output=True,
    )
    response = client.get("/api/tasks/t1/git-diff")
    assert response.json()["diff"].strip() == ""


def test_unknown_task_is_404(client_with_repo):
    client, _ = client_with_repo
    assert client.get("/api/tasks/nope/git-diff").status_code == 404


def test_log_lists_commits(client_with_repo):
    client, _ = client_with_repo
    response = client.get("/api/tasks/t1/git-log")
    assert response.status_code == 200
    commits = response.json()["commits"]
    assert len(commits) >= 1
    assert "sha" in commits[0]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_git_diff.py -v`
Expected: FAIL — 404

- [ ] **Step 3: 写实现 `server/service/git_diff.py`**

```python
# -*- coding: utf-8 -*-
"""Expose the workspace's git history to the frontend.

The change pane renders a unified diff, so the backend returns the raw
diff text rather than a parsed structure -- the frontend's diff component
already knows how to parse it, and shipping text keeps the contract thin.
"""
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as PathParam, Query

from ..config import get_settings
from ..workspace.git_init import GitError, get_diff

router = APIRouter(prefix="/api", tags=["git"])

_LOG_SEPARATOR = "\x1f"  # ASCII unit separator: never appears in a message
_RECORD_SEPARATOR = "\x1e"  # ASCII record separator


def _task_root(task_id: str) -> Path:
    """Resolve a task's workspace directory.

    Args:
        task_id (`str`):
            The task identifier.

    Returns:
        `Path`:
            The workspace directory.

    Raises:
        `HTTPException`:
            404 when the task workspace does not exist.
    """
    root = Path(get_settings().workspace_root) / task_id
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown task {task_id!r}")
    return root


@router.get("/tasks/{task_id}/git-diff")
async def git_diff(
    task_id: str = PathParam(...),
    from_ref: str = Query(default="HEAD"),
    to_ref: str | None = Query(default=None),
) -> dict:
    """Return the unified diff for a task workspace.

    Args:
        task_id (`str`):
            The task identifier.
        from_ref (`str`, defaults to ``"HEAD"``):
            The comparison base. ``HEAD`` yields uncommitted changes.
        to_ref (`str | None`, optional):
            The comparison target; defaults to the working tree.

    Returns:
        `dict`:
            ``{"diff": <unified diff text>}``.
    """
    root = _task_root(task_id)
    try:
        diff = get_diff(root, from_ref=from_ref, to_ref=to_ref)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"diff": diff}


@router.get("/tasks/{task_id}/git-log")
async def git_log(
    task_id: str = PathParam(...),
    limit: int = Query(default=50, gt=0, le=500),
) -> dict:
    """Return recent commits for a task workspace.

    Args:
        task_id (`str`):
            The task identifier.
        limit (`int`, defaults to ``50``):
            Maximum number of commits to return.

    Returns:
        `dict`:
            ``{"commits": [{"sha", "subject", "author", "date"}]}``.
    """
    root = _task_root(task_id)
    fmt = _LOG_SEPARATOR.join(["%H", "%s", "%an", "%aI"]) + _RECORD_SEPARATOR

    result = subprocess.run(
        ["git", "log", f"-{limit}", f"--format={fmt}"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip())

    commits = []
    for record in result.stdout.split(_RECORD_SEPARATOR):
        record = record.strip()
        if not record:
            continue
        sha, subject, author, date = record.split(_LOG_SEPARATOR)
        commits.append(
            {"sha": sha, "subject": subject, "author": author, "date": date},
        )

    return {"commits": commits}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_service_git_diff.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add server/service/git_diff.py tests/test_service_git_diff.py
git commit -m "feat: service: add git diff and log routes"
```

---

## Task 14: 端到端 SSE 对话闭环

**Files:**
- Modify: `server/service/chat.py`
- Create: `tests/test_e2e.py`

- **背景**：最后一个后端任务，把 Agent + 工具 + 记忆 + SSE 串成完整闭环。

- [ ] **Step 1: 写失败的测试 `tests/test_e2e.py`**

```python
# -*- coding: utf-8 -*-
"""End-to-end test of the chat SSE loop.

The model is stubbed: the point is to verify the plumbing -- that a user
message reaches the agent, that its streamed events become well-formed SSE
frames, and that the stream terminates. Hitting the live LiteLLM proxy
would make this test slow, flaky and network-dependent.
"""
import pytest
from fastapi.testclient import TestClient

from server.service.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("S_AGENT_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("S_AGENT_BASE_URL", "http://127.0.0.1:4000/v1")

    import server.config

    server.config.get_settings.cache_clear()
    return TestClient(create_app())


def test_chat_returns_sse_stream(client):
    response = client.post(
        "/api/chat",
        json={"task_id": "t1", "message": "你好"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


def test_stream_ends_with_done_event(client):
    response = client.post(
        "/api/chat",
        json={"task_id": "t1", "message": "你好"},
    )
    assert "event: done" in response.text


def test_stream_frames_are_well_formed(client):
    """Every frame must carry both an event line and a data line; a frame
    missing either is silently dropped by EventSource."""
    response = client.post(
        "/api/chat",
        json={"task_id": "t1", "message": "你好"},
    )
    frames = [f for f in response.text.split("\n\n") if f.strip()]
    assert frames, "expected at least one SSE frame"
    for frame in frames:
        assert "event: " in frame
        assert "data: " in frame


def test_missing_message_is_422(client):
    response = client.post("/api/chat", json={"task_id": "t1"})
    assert response.status_code == 422


def test_missing_task_id_is_422(client):
    response = client.post("/api/chat", json={"message": "你好"})
    assert response.status_code == 422
```

- [ ] **Step 2: 运行测试确认失败**

Run: `/media/data/venv/bin/python -m pytest tests/test_e2e.py -v`
Expected: FAIL — 404 (route not implemented)

- [ ] **Step 3: 写实现 `server/service/chat.py`**

```python
# -*- coding: utf-8 -*-
"""The chat endpoint: drive one agent turn and stream it as SSE.

The endpoint streams rather than returning a JSON body because the value
of an agent UI is watching it work -- thinking, calling tools, and finally
answering. Returning the finished text would collapse all of that into a
single opaque blob after a long pause.

Event mapping follows the contract in :mod:`server.service.events`:

* ``ThinkingBlockDeltaEvent``  -> ``thinking_delta``
* ``TextBlockDeltaEvent``      -> ``text_delta``
* ``ReplyEndEvent``            -> ``done``, then the stream closes
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent.core import create_agent
from ..config import get_settings
from ..workspace.git_init import init_workspace
from . import events

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    """A single user turn."""

    task_id: str = Field(..., min_length=1, description="The target task.")
    message: str = Field(..., min_length=1, description="The user's message.")


def _prepare_workspace(task_id: str) -> Path:
    """Ensure the task workspace exists and is a repository.

    Args:
        task_id (`str`):
            The task identifier.

    Returns:
        `Path`:
            The workspace directory.
    """
    root = Path(get_settings().workspace_root) / task_id
    root.mkdir(parents=True, exist_ok=True)
    init_workspace(root, task_id=task_id)
    return root


async def _stream_turn(workspace: Path, message: str):
    """Run one agent turn and yield SSE frames.

    Args:
        workspace (`Path`):
            The task workspace the agent is confined to.
        message (`str`):
            The user's message.

    Yields:
        `str`:
            SSE frames.
    """
    # Imported here so the agent module -- and therefore the model client --
    # is only constructed when a request actually arrives.
    from agentscope.event import (
        ReplyEndEvent,
        TextBlockDeltaEvent,
        ThinkingBlockDeltaEvent,
    )
    from agentscope.message import Msg, TextBlock

    agent = create_agent(get_settings(), workspace_dir=str(workspace))

    # AgentScope 2.0 requires content blocks, not a bare string.
    user_msg = Msg(name="user", role="user", content=[TextBlock(text=message)])

    try:
        async for event in agent.reply_stream(user_msg):
            if isinstance(event, ThinkingBlockDeltaEvent):
                yield events.thinking_delta(event.delta)
            elif isinstance(event, TextBlockDeltaEvent):
                yield events.text_delta(event.delta)
            elif isinstance(event, ReplyEndEvent):
                yield events.done("completed")
                return
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user as text
        yield events.text_delta(f"\n\n[运行出错] {exc}")
        yield events.done("failed")


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Run one agent turn, streaming the result as Server-Sent Events.

    Args:
        request (`ChatRequest`):
            The task id and the user's message.

    Returns:
        `StreamingResponse`:
            An SSE stream of agent events.

    Raises:
        `HTTPException`:
            500 when the workspace cannot be prepared.
    """
    try:
        workspace = _prepare_workspace(request.task_id)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not prepare workspace: {exc}",
        ) from exc

    return StreamingResponse(
        _stream_turn(workspace, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: 让测试不依赖真实模型**

在 `tests/test_e2e.py` 的 `client` fixture 中，把 agent 的流式输出替换为桩实现：

在文件顶部加入：

```python
import server.service.chat as chat_module


class _StubEvent:
    """Minimal stand-in for an AgentScope stream event."""

    def __init__(self, name: str, delta: str = "") -> None:
        self._name = name
        self.delta = delta


def _stub_stream(workspace, message):
    """A deterministic agent turn: a thinking chunk, a text chunk, then end."""

    async def _gen():
        yield chat_module.events.thinking_delta("分析中")
        yield chat_module.events.text_delta(f"收到: {message}")
        yield chat_module.events.done("completed")

    return _gen()
```

并把 `client` fixture 改为：

```python
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("S_AGENT_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("S_AGENT_BASE_URL", "http://127.0.0.1:4000/v1")

    import server.config

    server.config.get_settings.cache_clear()

    # Swap the real agent turn for the stub so the test needs no network.
    monkeypatch.setattr(chat_module, "_stream_turn", _stub_stream)

    return TestClient(create_app())
```

- [ ] **Step 5: 运行测试确认通过**

Run: `/media/data/venv/bin/python -m pytest tests/test_e2e.py -v`
Expected: 5 passed

- [ ] **Step 6: 手工对真实模型做一次冒烟测试**

Run:
```bash
/media/data/venv/bin/python -m uvicorn server.main:app --port 8000 &
sleep 4
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"task_id":"smoke","message":"用一句话介绍你自己"}'
sleep 1
kill %1
```
Expected: 看到 `event: thinking_delta` / `event: text_delta` 逐条输出，最后 `event: done`。

> 这是**唯一**需要真实 LiteLLM 的验证步骤。若失败，先确认 `LITELLM_API_KEY` 已 export 到当前 shell。

- [ ] **Step 7: 全量测试**

Run: `/media/data/venv/bin/python -m pytest tests/ -v`
Expected: 全部通过（约 60+ 个测试）

- [ ] **Step 8: Commit**

```bash
git add server/service/chat.py tests/test_e2e.py
git commit -m "feat: service: add SSE chat endpoint completing the backend loop"
```

---

## Part 1 完成标志

- [ ] `pytest tests/` 全绿
- [ ] `/api/health` 返回 ok
- [ ] 真实 `v-flash` 冒烟测试输出 SSE 流
- [ ] 12 个工具已注册（`test_tools_registry.py` 验证）
- [ ] 工作区路径越界被拒（`test_workspace_sandbox.py` 验证）
- [ ] 工作区 git 化并可取 diff（`test_workspace_git.py` 验证）
- [ ] SSE 事件契约与前端 `events.ts` 一致（Task 10 与 Part 2 Task 9 交叉验证）

## 已知遗留（留待阶段二）

- HITL 实际拦截逻辑（本计划已定义 `require_confirm` 事件与 `/confirm` 路由骨架，权限引擎判定未接入 Agent 循环）
- 上下文卸载（`ToolOffloadMiddleware`）未接入
- 长期记忆（`AgenticMemoryMiddleware`）未接入
- `ContextConfig` / `InjectionConfig` 字段名需按 Step 1 实测签名最终确认
