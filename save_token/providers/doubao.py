"""豆包 provider — https://www.doubao.com/chat/ — CDP fill + keys."""

import logging, re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="doubao", url="https://www.doubao.com/chat/",
    description="豆包 (ByteDance, free)",
    input_selector="textarea", send_selector="Enter", send_method="keys",
    response_js=r"""
(function() {
  const selectors = ['[class*="markdown"]', '[class*="message-content"]',
    '[class*="chat-content"]', '[class*="reply"]', '[class*="answer"]',
    '[class*="doubao-message"]', '[class*="bot-message"]'];
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
})()""",
    thinking_js="""(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="think"], [class*="deep"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return ''; })()""",
    needs_fill_not_type=True, post_send_wait=20, pre_clear=False,
    session_name="save-token-db",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question):
        s, c = self.config.session_name, self.config
        logger.info("Opening %s", c.url)
        self.bridge.navigate_and_wait(s, c.url, wait=8.0)
        fr = self.bridge.fill(s, "textarea", question)
        if not fr.get("filled"):
            if fr.get("error"): raise RuntimeError(f"Doubao fill error: {fr}")
            self.bridge.wait(3.0)
            fr = self.bridge.fill(s, "textarea", question)
            if not fr.get("filled"): raise RuntimeError(f"Doubao fill failed: {fr}")
        self.bridge.wait(1.0)
        self.bridge.eval(s, "document.querySelector('textarea')?.focus()")
        self.bridge.wait(0.3)
        self.bridge.keys(s, "Enter")
        self.bridge.wait(c.post_send_wait)
        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass
        raw = self.bridge.eval(s, c.response_js)
        ans = raw or ""
        if question and question in ans: ans = ans.split(question, 1)[-1].strip()
        for n in ["豆包", "Doubao", "内容由 AI 生成", "AI 生成", "仅供参考"]: ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2: ans = "(empty — selectors may need updating)"
        return AskResult(question=question, answer=ans, thinking=thinking)
