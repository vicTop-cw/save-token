"""Kimi provider — https://kimi.moonshot.cn/

Uses OpenCLI eval() to interact with Kimi web chat.
Response extraction via DOM selectors.

NOTE: When Kimi updates its UI, update PROVIDER_CONFIG selectors/JS below.
"""

import logging
import re

from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="kimi",
    url="https://kimi.moonshot.cn/",
    description="Kimi (Moonshot AI, free)",
    input_selector="0",
    send_selector="1",
    send_method="eval",
    response_js="""
// Extract response text from Kimi chat page.
(function() {
  const selectors = [
    '[class*="markdown"]',
    '[class*="message-content"]',
    '[class*="chat-content"]',
    '[class*="reply"]',
    '[class*="answer"]',
    '[class*="kimi-message"]',
  ];
  let texts = [];
  for (const sel of selectors) {
    const els = document.querySelectorAll(sel);
    els.forEach(el => {
      const t = el.textContent.trim();
      if (t && t.length > 2 && !texts.includes(t)) texts.push(t);
    });
  }
  if (texts.length > 0) return texts.join('\\n---\\n');
  const body = document.body.innerText || document.body.textContent;
  const lines = body.split('\\n').filter(l => l.trim().length > 2);
  return lines.slice(-60).join('\\n');
})()
""",
    thinking_js="""
// Extract thinking/reasoning process from Kimi.
(function() {
  const selectors = [
    '[class*="thinking"]',
    '[class*="reasoning"]',
    '[class*="think"]',
    '[class*="chain"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 1) return el.textContent.trim();
  }
  return '';
})()
""",
    needs_fill_not_type=True,
    post_send_wait=15,
    pre_clear=False,
    session_name="save-token-kimi",
)


class Provider(BaseProvider):
    """Kimi via eval-based browser automation."""

    def __init__(self, config: ProviderConfig = None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question: str) -> AskResult:
        session = self.config.session_name
        cfg = self.config

        # 1. Open Kimi chat
        logger.info("Opening %s", cfg.url)
        result = self.bridge.navigate_and_wait(session, cfg.url, wait=5.0)

        # 2. Fill textarea using native value setter + dispatch
        fill_js = f"""(function() {{
  const ta = document.querySelector(
    'textarea[placeholder*="输入"], ' +
    'textarea[placeholder*="消息"], ' +
    'textarea[placeholder*="问题"], ' +
    'textarea[placeholder*="发送"], ' +
    'textarea'
  );
  if (!ta) return 'E_NOTEXTAREA';
  const setter = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype, 'value'
  ).set;
  setter.call(ta, {question!r});
  ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return 'OK';
}})()
"""
        r = self.bridge.eval(session, fill_js)
        logger.debug("fill: %s", r)
        if "E_NOTEXTAREA" in r:
            raise RuntimeError("Kimi page structure changed — update input_selector")

        self.bridge.wait(0.8)

        # 3. Click send button
        click_js = """(function() {
  const ta = document.querySelector('textarea');
  if (ta) {
    const container = ta.closest('form') || ta.closest('div[class]');
    if (container) {
      const btns = container.querySelectorAll('button, [role="button"]');
      for (const btn of btns) {
        if (btn.tagName === 'BUTTON' || btn.getAttribute('role') === 'button') {
          btn.click();
          return 'clicked';
        }
      }
      if (btns.length > 0) {
        btns[btns.length - 1].click();
        return 'clicked_last';
      }
    }
  }
  if (ta) {
    ta.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
    }));
    return 'enter';
  }
  return 'E_NOSEND';
})()
"""
        self.bridge.eval(session, click_js)

        # 4. Wait for response
        self.bridge.wait(cfg.post_send_wait)

        # 5. Extract thinking
        thinking = ""
        try:
            thinking = self.bridge.eval(session, cfg.thinking_js) if cfg.thinking_js else ""
        except Exception:
            pass

        # 6. Extract response
        raw = self.bridge.eval(session, cfg.response_js)
        logger.debug("response: %s", (raw or "")[:300])

        # 7. Clean up answer
        answer = raw or ""
        if question and question in answer:
            parts = answer.split(question, 1)
            if len(parts) > 1:
                answer = parts[1].strip()
        for noise in [
            "Kimi", "Moonshot", "开始对话", "发送",
            "内容由 AI 生成", "AI 生成", "仅供参考",
        ]:
            answer = answer.replace(noise, "")
        answer = re.sub(r'\n{3,}', '\n\n', answer)
        answer = re.sub(r'---\n?', '', answer)
        answer = answer.strip()

        if not answer or len(answer) < 2:
            answer = "(empty — selectors may need updating for current Kimi DOM)"

        return AskResult(
            question=question,
            answer=answer,
            thinking=thinking,
        )
