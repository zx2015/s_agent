"""
Auto-generate a short conversation title from the user's first message.

Deliberately uses `config.MODEL_NAME_TITLE` (a small/cheap "flash-lite"
tier model on the same LiteLLM proxy as the main agent, see
`server/config.py`) rather than `config.MODEL_NAME` — summarizing one
short message into a title is a trivial task that doesn't need the main
agent's reasoning budget, and a smaller model answers in a few hundred
milliseconds instead of a few seconds.

Talks to the LiteLLM proxy directly via the `openai` SDK (already an
AgentScope transitive dependency) rather than spinning up a full
AgentScope `Agent` — no tools, no memory, no system-prompt assembly are
needed for a single one-shot completion.
"""
import logging

from openai import AsyncOpenAI

from server import config

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=config.LITELLM_BASE_URL, api_key=config.LITELLM_API_KEY)

_SYSTEM_PROMPT = (
    "你是一个对话标题生成器。根据用户的第一条消息，生成一个简短的中文标题，"
    "概括这次对话的主题。要求：不超过 16 个汉字，不使用任何标点符号，不要加引号，"
    "只输出标题本身，不要任何解释或前后缀。"
)

_MAX_TITLE_LENGTH = 24


async def generate_title(first_message: str, fallback: str = "新任务") -> str:
    """Best-effort title generation — never raises.

    Any failure (missing/invalid API key, network error, timeout,
    unexpected response shape) falls back to `fallback` and logs a
    warning, rather than blocking or failing the chat turn that
    triggered it: a wrong/missing title is a cosmetic problem, not
    worth turning into a broken conversation.
    """
    text = first_message.strip()
    if not text:
        return fallback

    try:
        response = await _client.chat.completions.create(
            model=config.MODEL_NAME_TITLE,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text[:500]},
            ],
            max_tokens=32,
            temperature=0.3,
        )
        title = (response.choices[0].message.content or "").strip()
    except Exception:  # noqa: BLE001 - best-effort, see docstring
        logger.warning(
            "Title generation failed; falling back to default title",
            exc_info=True,
        )
        return fallback

    # Models sometimes ignore "no quotes"/"one line" instructions anyway;
    # clean up defensively rather than trusting the prompt to be obeyed.
    title = title.strip("\"'\u201c\u201d\u2018\u2019 \u3000").splitlines()[0].strip() if title else ""
    title = title[:_MAX_TITLE_LENGTH]
    return title or fallback
