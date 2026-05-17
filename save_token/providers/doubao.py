"""豆包 provider — uses opencli native doubao adapter."""

import logging, json, subprocess, time
from pathlib import Path
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="doubao", url="https://www.doubao.com/chat/",
    description="豆包 — via opencli native adapter",
    input_selector="", send_selector="", send_method="",
    response_js="", thinking_js="",
    needs_fill_not_type=False, post_send_wait=60,
    session_name="save-token-db",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)

    def ask(self, question, options=None, session=None):
        cmd = ["opencli", "doubao", "ask", question, "-f", "json"]
        if options and options.file_paths:
            for fp in options.file_paths:
                cmd.extend(["--file", fp])

        t0 = time.monotonic()
        logger.info("opencli doubao ask: %s", question[:60])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=self.config.post_send_wait)
            if result.returncode != 0:
                raise RuntimeError(f"opencli doubao ask: {result.stderr or result.stdout}")

            data = json.loads(result.stdout)
            # Handle both array and dict formats
            if isinstance(data, list):
                answer = ""
                for m in data:
                    if isinstance(m, dict) and m.get("Role", "").lower() == "assistant":
                        answer = m.get("Text", "") or m.get("Content", "")
            else:
                answer = data.get("response", "") or data.get("answer", "") or data.get("text", "")
                msgs = data.get("messages", []) or data.get("conversation", [])
                for m in reversed(msgs):
                    if m.get("role") == "assistant":
                        answer = m.get("text", "") or m.get("content", "")
                        break
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Doubao timed out")
        except json.JSONDecodeError:
            raise RuntimeError(f"Doubao non-JSON: {result.stdout[:200]}")

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info("ask(doubao) → %s in %dms", (answer or "(empty)")[:80], elapsed)
        return AskResult(question=question, answer=answer or "(empty)")
