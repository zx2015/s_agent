"""
Tests for automatic context size calibration (server/agent/calibrator.py).
"""
import pytest
import httpx
from unittest.mock import patch, AsyncMock

from server import config
from server.agent.calibrator import (
    resolve_context_size,
    clear_context_size_cache,
    KNOWN_MODEL_WINDOWS,
)


@pytest.fixture(autouse=True)
def reset_cache_and_config():
    clear_context_size_cache()
    orig_size = config.MODEL_CONTEXT_SIZE
    config.MODEL_CONTEXT_SIZE = 0
    yield
    clear_context_size_cache()
    config.MODEL_CONTEXT_SIZE = orig_size


@pytest.mark.asyncio
async def test_explicit_override_takes_precedence():
    config.MODEL_CONTEXT_SIZE = 65536
    size = await resolve_context_size("gemini-pro")
    assert size == 65536


@pytest.mark.asyncio
async def test_probe_model_info_success():
    mock_data = {
        "data": [
            {
                "model_name": "custom-vflash",
                "model_info": {"max_input_tokens": 32768},
            }
        ]
    }
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        size = await resolve_context_size(
            model_name="custom-vflash",
            base_url="http://127.0.0.1:4000/v1",
            api_key="test-key",
        )
        assert size == 32768

        # Second call hits in-memory cache without calling get again
        with patch("httpx.AsyncClient.get", side_effect=RuntimeError("Should not be called")):
            cached_size = await resolve_context_size(model_name="custom-vflash")
            assert cached_size == 32768


@pytest.mark.asyncio
async def test_probe_models_endpoint_fallback():
    # /model/info returns 404, /models returns 200 with max_input_tokens
    def mock_get(url, **kwargs):
        mock_resp = AsyncMock(spec=httpx.Response)
        if "/models" in str(url):
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "data": [
                    {
                        "id": "gemini-test-model",
                        "max_input_tokens": 1048576,
                    }
                ]
            }
        else:
            mock_resp.status_code = 404
            mock_resp.json.return_value = {}
        return mock_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        size = await resolve_context_size(
            model_name="gemini-test-model",
            base_url="http://127.0.0.1:4000/v1",
        )
        assert size == 1048576


@pytest.mark.asyncio
async def test_heuristic_regex_matching_when_probe_fails():
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        # Test popular families
        assert await resolve_context_size("gemini-2.5-flash") == 1_048_576
        clear_context_size_cache()
        assert await resolve_context_size("deepseek-v4-flash") == 1_000_000
        clear_context_size_cache()
        assert await resolve_context_size("claude-3-5-sonnet") == 200_000
        clear_context_size_cache()
        assert await resolve_context_size("gpt-4o") == 128_000
        clear_context_size_cache()
        assert await resolve_context_size("qwen3.8-flash-next") == 32_768
        clear_context_size_cache()
        assert await resolve_context_size("qwen/qwen-2.5-72b") == 131_072


@pytest.mark.asyncio
async def test_default_fallback_on_unknown_model():
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        size = await resolve_context_size("completely-unknown-custom-model", default_fallback=64000)
        assert size == 64000
