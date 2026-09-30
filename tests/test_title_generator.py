"""
Tests for server/service/title_generator.py.

One real-network test against the actual LiteLLM proxy (same philosophy
as test_memory_store.py's real-Redis tests: a mock can't tell us whether
the actual model + prompt combination produces a usable short title) plus
fast, deterministic tests for the fallback paths that don't need network
at all.
"""
import pytest

from server.service.title_generator import generate_title


@pytest.mark.asyncio
async def test_empty_message_returns_the_fallback_without_calling_the_model():
    assert await generate_title("   ") == "新任务"
    assert await generate_title("", fallback="自定义兜底") == "自定义兜底"


@pytest.mark.asyncio
async def test_a_network_or_model_failure_falls_back_instead_of_raising(monkeypatch):
    async def broken_create(*args, **kwargs):
        raise RuntimeError("simulated LiteLLM outage")

    from server.service import title_generator

    monkeypatch.setattr(
        title_generator._client.chat.completions,
        "create",
        broken_create,
    )

    title = await generate_title("帮我分析一下贵州茅台最近的股价走势")

    assert title == "新任务"


@pytest.mark.asyncio
async def test_generates_a_short_title_from_a_real_first_message():
    title = await generate_title("帮我写一个个人主页的 HTML 页面")

    # Real model output isn't deterministic word-for-word, but the
    # contract is: short, non-empty, and not just the fallback sentinel
    # (which would mean the call silently failed and we didn't notice).
    assert title != "新任务"
    assert 0 < len(title) <= 24
