"""腾讯元宝 provider — https://yuanbao.tencent.com/chat

Uses OpenCLI CDP commands (fill + keys) for reliable React interaction.
Response extraction via DOM traversal.
"""

import logging
import re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="yuanbao",
    url="https://yuanbao.tencent.com/chat",
    description="腾讯元宝 (free)",
    input_selector="textarea",
    send_selector="Enter",
    send_method="keys",
    response_js=r"""
(function() {
  const selectors = ['[class*="hyc-common-markdown"]', '[class*="markdown"]',
    '[class*="message__content"]', '[class*="chat__answer"]',
    '[class*="agent-chat__answer"]', '[class*="content"]'];
  let texts = [];
  for (const sel of selectors) {
    document.querySelectorAll(sel).forEach(el => {
      const t = el.textContent.trim();
      if (t && t.length > 2 && !texts.includes(t)) texts.push(t);
    });
  }
  if (texts.length > 0) return texts.join('\n---\n');
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()
""",
    thinking_js="""
(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="think"], [class*="deep"]');
  for (const el of els) {
    const t = el.textContent.trim();
    if (t && t.length > 2) return t;
  }
  return '';
})()
""",
    needs_fill_not_type=True,
    post_send_wait=20,
    pre_clear=False,
    session_name="save-token-yb",
)


class Provider(BaseProvider):
    def __init__(self, config: ProviderConfig = None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question: str) -> AskResult:
        session = self.config.session_name
        cfg = self.config

        logger.info("Opening %s", cfg.url)
        self.bridge.navigate_and_wait(session, cfg.url, wait=8.0)

        fill_result = self.bridge.fill(session, "textarea", question)
        if not fill_result.get("filled"):
            if fill_result.get("error"):
                raise RuntimeError(f"Yuanbao fill error: {fill_result}")
            self.bridge.wait(3.0)
            fill_result = self.bridge.fill(session, "textarea", question)
            if not fill_result.get("filled"):
                raise RuntimeError(f"Yuanbao fill failed: {fill_result}")

        self.bridge.wait(1.0)
        self.bridge.eval(session, "document.querySelector('textarea')?.focus()")
        self.bridge.wait(0.3)
        self.bridge.keys(session, "Enter")
        self.bridge.wait(cfg.post_send_wait)

        thinking = ""
        try:
            thinking = self.bridge.eval(session, cfg.thinking_js) if cfg.thinking_js else ""
        except Exception:
            pass

        raw = self.bridge.eval(session, cfg.response_js)
        answer = raw or ""
        if question and question in answer:
            answer = answer.split(question, 1)[-1].strip()
        for noise in ["腾讯元宝", "yuanbao", "内容由 AI 生成", "AI 生成", "仅供参考", "发送"]:
            answer = answer.replace(noise, "")
        answer = re.sub(r'\n{3,}', '\n\n', answer).strip()
        if not answer or len(answer) < 2:
            answer = "(empty — selectors may need updating)"

        return AskResult(question=question, answer=answer, thinking=thinking)
