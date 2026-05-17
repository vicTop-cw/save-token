"""豆包 provider — textarea with send button"""

import logging, re, time, uuid
from pathlib import Path
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="doubao", url="https://www.doubao.com/chat/",
    description="豆包 (ByteDance, free)",
    input_selector="textarea[placeholder*='发消息']", send_selector="button[class*='send']", send_method="click",
    response_js=r"""
(function() {
  // Try to find the last assistant message bubble
  const bubbles = document.querySelectorAll('[class*="message"], [class*="reply"], [class*="answer"], [class*="bubble"], [class*="chat-item"]');
  let last = '';
  for (const el of bubbles) {
    const text = (el.innerText || el.textContent || '').trim();
    if (text.length > 30 && !text.includes('发消息') && !text.includes('发送')) {
      last = text;
    }
  }
  if (last) return last;
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()""",
    thinking_js="""(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="think"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return ''; })()""",
    needs_fill_not_type=True, post_send_wait=15, pre_clear=False,
    session_name="save-token-db",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def _unique_session(self):
        return f"{self.config.session_name}-{uuid.uuid4().hex[:8]}"

    def ask(self, question, options=None, session=None):
        s = session or self._unique_session()
        c = self.config
        if not session:
            logger.info("Opening %s (session %s)", c.url, s)
            self.bridge.navigate_and_wait(s, c.url, wait=8.0)

        # Embed files
        if options and options.file_paths:
            for fp in options.file_paths:
                try:
                    content = Path(fp).read_text(encoding="utf-8")
                    lang = Path(fp).suffix.lstrip(".")
                    question = question + f"\n```{lang}\n{content}\n```\n"
                except Exception:
                    pass

        # Fill textarea
        fr = self.bridge.fill(s, "textarea[placeholder*='发消息']", question)
        if not fr.get("filled"):
            raise RuntimeError(f"Doubao fill failed: {fr}")
        self.bridge.wait(0.5)

        # Click send
        sr = self.bridge.click(s, "button[class*='send']")
        if not sr.get("clicked"):
            raise RuntimeError(f"Doubao send failed: {sr}")
        self.bridge.wait(c.post_send_wait)

        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        # Poll
        raw = ""
        for _ in range(10):
            raw = self.bridge.eval(s, c.response_js)
            if raw and len(raw) > 30:
                break
            self.bridge.wait(3.0)

        ans = raw or ""
        if question and question in ans:
            ans = ans.split(question, 1)[-1].strip()
        for n in ["豆包", "Doubao", "内容由 AI 生成", "AI 生成", "仅供参考", "发消息"]:
            ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2:
            ans = "(empty)"
        return AskResult(question=question, answer=ans, thinking=thinking)
