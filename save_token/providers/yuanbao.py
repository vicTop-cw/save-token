"""腾讯元宝 provider — https://yuanbao.tencent.com/chat

Uses OpenCLI browser automation. Requires Chrome cookies from prior login.

NOTE: This is a SKELETON. The selectors below are educated guesses.
When yuanbao updates its UI, update PROVIDER_CONFIG in this file.
"""

import logging

from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="yuanbao",
    url="https://yuanbao.tencent.com/chat",
    description="腾讯元宝 (free)",
    # --- SELECTORS (update when yuanbao UI changes) ---
    input_selector="0",           # TODO: find by inspecting page
    send_selector="1",            # TODO: find send button index
    send_method="enter",
    response_js="""
(function() {
  // TODO: update selectors for yuanbao's DOM structure
  const blocks = document.querySelectorAll(
    '[class*="markdown"], [class*="content"], [class*="message"], ' +
    '[class*="reply"], [class*="answer"], .prose'
  );
  const texts = [];
  blocks.forEach(b => {
    const t = b.textContent.trim();
    if (t && t.length > 1 && t.length < 3000) texts.push(t);
  });
  return JSON.stringify(texts.slice(-6));
})()
""",
    thinking_js="""
(function() {
  // TODO: yuanbao may or may not expose thinking
  const t = document.querySelector('[class*="thinking"], [class*="reasoning"]');
  return t ? t.textContent.trim() : '';
})()
""",
    # --- Behavior ---
    needs_fill_not_type=True,
    post_send_wait=15,
    pre_clear=False,
    session_name="save-token-yuanbao",
)


class Provider(BaseProvider):
    """腾讯元宝 via browser automation."""

    def __init__(self, config: ProviderConfig = None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question: str) -> AskResult:
        session = self.config.session_name
        cfg = self.config

        # 1. Open yuanbao chat
        logger.info("Opening %s", cfg.url)
        result = self.bridge.navigate_and_wait(session, cfg.url, wait=5.0)

        # 2. Fill input and send
        logger.info("Sending: %s", question[:60])
        self.bridge.fill_and_send(
            session,
            input_target=cfg.input_selector,
            send_target=cfg.send_selector,
            text=question,
            method=cfg.send_method,
            pre_wait=0.5,
        )

        # 3. Wait for response
        self.bridge.wait(cfg.post_send_wait)

        # 4. Extract response
        raw_js = self.bridge.eval(session, cfg.response_js)
        logger.debug("response_js raw: %s", raw_js[:200])

        # 5. Extract thinking
        thinking = ""
        try:
            thinking = self.bridge.eval(session, cfg.thinking_js)
        except Exception:
            pass

        # 6. Parse answer
        import json as _json
        try:
            blocks = _json.loads(raw_js) if raw_js else []
        except _json.JSONDecodeError:
            blocks = [raw_js] if raw_js else []

        answer = ""
        for block in reversed(blocks):
            block = str(block).strip()
            if block and block != question and len(block) > 1:
                answer = block
                break

        if not answer:
            answer = "(empty — selectors may need updating)"
            logger.warning("Empty yuanbao response — try updating selectors")

        return AskResult(
            question=question,
            answer=answer,
            thinking=thinking,
        )
