"""Local LLM provider — talks to lm-server OpenAI-compatible API."""

import logging, json, time
import urllib.request
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="local", url="http://127.0.0.1:1234/v1",
    description="本地模型 (lm-server OpenAI 兼容)",
    input_selector="", send_selector="", send_method="",
    response_js="", thinking_js="",
    needs_fill_not_type=False, post_send_wait=60,
    session_name="save-token-local",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)

    def ask(self, question, options=None, session=None):
        t0 = time.monotonic()
        url = f"{self.config.url}/chat/completions"
        body = json.dumps({
            "messages": [{"role": "user", "content": question}],
            "max_tokens": 2048,
            "temperature": 0.2,
        }).encode()

        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=self.config.post_send_wait) as resp:
                data = json.loads(resp.read())
            answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            raise RuntimeError(f"Local model error: {e}")

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info("ask(local) → %s in %dms", (answer or "(empty)")[:80], elapsed)
        return AskResult(question=question, answer=answer or "(empty)")
