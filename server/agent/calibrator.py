"""
Automatic context size calibrator for LLM endpoints.

Dynamically resolves the context window size of any model (upstream LiteLLM/OpenAI)
using a four-tier pipeline:
1. Explicit user override from environment (`config.MODEL_CONTEXT_SIZE` > 0).
2. Active probe against upstream LiteLLM endpoints (/model/info and /models).
3. Known model family regex mapping table (Gemini, DeepSeek, Claude, GPT-4o, Qwen, etc.).
4. Safe fallback default.
"""
import logging
import os
import re

import httpx

from server import config

logger = logging.getLogger(__name__)

# Known standard context windows for popular model families
KNOWN_MODEL_WINDOWS: list[tuple[str, int]] = [
    (r"gemini[-/].*flash|gemini[-/].*pro", 1_048_576),
    (r"deepseek[-/].*v4|deepseek[-/].*pro", 1_000_000),
    (r"claude[-/]3[-.]5|claude[-/]3[-.]7", 200_000),
    (r"gpt-4o|o1|o3", 128_000),
    (r"qwen.*3\.8[-_]flash|qwen.*flash[-_]next", 32_768),
    (r"qwen.*3[-.]5|qwen[-/]qwen", 131_072),
    (r"minimax[-/]m3", 1_000_000),
]

_context_size_cache: dict[str, int] = {}


def clear_context_size_cache() -> None:
    """Clear in-memory cache, useful for test isolation."""
    _context_size_cache.clear()


async def resolve_context_size(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    default_fallback: int = 128_000,
) -> int:
    """Resolve the effective context window size for a model.

    Args:
        model_name: Target model name (defaults to `config.MODEL_NAME`).
        base_url: Upstream model proxy base URL (defaults to `config.LITELLM_BASE_URL`).
        api_key: Upstream API key (defaults to `config.LITELLM_API_KEY`).
        default_fallback: Fallback context size if probe & regex both fail.

    Returns:
        The calibrated context window size in tokens.
    """
    # Tier 1: Explicit user override in config (if configured as positive int)
    explicit_size = getattr(config, "MODEL_CONTEXT_SIZE", 0)
    if isinstance(explicit_size, int) and explicit_size > 0:
        return explicit_size

    target_model = (model_name or getattr(config, "MODEL_NAME", "v-flash")).strip()
    if not target_model:
        return default_fallback

    # In-memory cache hit
    if target_model in _context_size_cache:
        return _context_size_cache[target_model]

    endpoint_base = (
        base_url or getattr(config, "LITELLM_BASE_URL", "http://127.0.0.1:4000")
    ).rstrip("/v1").rstrip("/")
    token = api_key or getattr(config, "LITELLM_API_KEY", "")

    # Tier 2: Active probe
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            headers = {"Authorization": f"Bearer {token}"} if token else {}

            # Probe /model/info
            try:
                resp = await client.get(f"{endpoint_base}/model/info", headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for item in data:
                        if item.get("model_name") == target_model:
                            info = item.get("model_info", {})
                            val = (
                                info.get("max_input_tokens")
                                or item.get("litellm_params", {}).get("max_tokens")
                            )
                            if val and int(val) > 0:
                                size = int(val)
                                logger.info(
                                    "Auto-calibrated context_size for %s via /model/info: %d tokens",
                                    target_model,
                                    size,
                                )
                                _context_size_cache[target_model] = size
                                return size
            except Exception as probe_err:
                logger.debug("Failed probing /model/info: %s", probe_err)

            # Probe /models
            try:
                resp = await client.get(f"{endpoint_base}/models", headers=headers)
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    for m in models:
                        if m.get("id") == target_model:
                            max_in = m.get("max_input_tokens")
                            if max_in and int(max_in) > 0:
                                size = int(max_in)
                                logger.info(
                                    "Auto-calibrated context_size for %s via /models: %d tokens",
                                    target_model,
                                    size,
                                )
                                _context_size_cache[target_model] = size
                                return size
            except Exception as probe_err:
                logger.debug("Failed probing /models: %s", probe_err)
    except Exception as exc:
        logger.debug("Could not probe model context size from proxy: %s", exc)

    # Tier 3: Heuristic pattern match
    for pattern, size in KNOWN_MODEL_WINDOWS:
        if re.search(pattern, target_model, re.IGNORECASE):
            logger.info(
                "Matched known model pattern '%s' for %s: context_size=%d tokens",
                pattern,
                target_model,
                size,
            )
            _context_size_cache[target_model] = size
            return size

    # Tier 4: Fallback
    logger.info(
        "Using default fallback context_size for %s: %d tokens",
        target_model,
        default_fallback,
    )
    _context_size_cache[target_model] = default_fallback
    return default_fallback
