"""Core engine — orchestrates ask() calls with retry and logging."""

import time
import logging
from typing import Optional

from .providers.base import AskResult
from .providers.registry import get_provider, list_available

logger = logging.getLogger(__name__)


def ask(question: str, provider: Optional[str] = None,
        max_retries: int = 2, timeout: int = 120) -> AskResult:
    """Send a question to the specified (or default) AI provider.

    Args:
        question: The question to ask.
        provider: Provider name (e.g. 'deepseek', 'yuanbao'). None = default.
        max_retries: Retry on failure.
        timeout: Seconds to wait for response.

    Returns:
        AskResult with question, answer, thinking, timing.
    """
    prov = get_provider(provider)

    last_error = None
    for attempt in range(1, max_retries + 2):
        try:
            start = time.monotonic()
            result = prov.ask(question)
            result.elapsed_ms = int((time.monotonic() - start) * 1000)
            result.provider = prov.config.name
            result.url = prov.config.url
            logger.info("ask(%s) → %s in %dms",
                        prov.config.name, result.answer[:60], result.elapsed_ms)
            return result
        except Exception as e:
            last_error = e
            logger.warning("ask attempt %d/%d failed: %s",
                          attempt, max_retries + 1, e)
            if attempt <= max_retries:
                time.sleep(2 ** attempt)

    raise RuntimeError(
        f"All {max_retries + 1} attempts failed for {prov.config.name}: {last_error}"
    )


def list_providers() -> list:
    """Return list of available provider names."""
    return list_available()
