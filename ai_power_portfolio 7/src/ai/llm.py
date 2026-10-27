"""
Thin wrapper around the Anthropic API, shared by Week 7 (profile explanations)
and Week 9 (news summaries).

generate_text() returns None - never raises - when there is no API key, the
anthropic package is missing, or the call fails for any reason (no network,
rate limit, bad key). Callers are expected to fall back to template text, so
the rest of the project works the same with or without a key.
"""
from typing import Optional

from src.config import settings


def llm_available() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def generate_text(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = 400,
    client=None,
) -> Optional[str]:
    """
    Returns the model's text reply, or None if it could not be generated.
    `client` lets tests inject a fake client instead of the real one.
    """
    if client is None:
        if not llm_available():
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        except Exception as e:  # package missing or bad config
            print(f"[llm] could not create client: {e}")
            return None

    try:
        kwargs = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        return text.strip() or None
    except Exception as e:
        print(f"[llm] call failed, using fallback text instead: {e}")
        return None
