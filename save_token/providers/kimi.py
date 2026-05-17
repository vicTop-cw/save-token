"""Kimi provider — contenteditable div (chat-input-editor)"""

import logging, re, time, uuid
from pathlib import Path
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="kimi", url="https://kimi.moonshot.cn/",
    description="Kimi (Moonshot AI, free)",
    input_selector="div.chat-input-editor", send_selector="div.send-button-container", send_method="click",
    response_js=r"""
(function() {
  // Kimi uses specific class: chat-content-item-assistant
  const msg = document.querySelector('[class*="chat-content-item-assistant"]');
  if (msg) {
    const text = (msg.innerText || msg.textContent || '').trim();
    if (text && text.length > 5) return text;
  }
  // Fallback: generic message search
  const bubbles = document.querySelectorAll('[class*="message"], [class*="reply"], [class*="answer"]');
  let last = '';
  for (const el of bubbles) {
    const text = (el.innerText || el.textContent || '').trim();
    if (text.length > 30 && !text.includes('尽管问') && !text.includes('发送')) {
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
    session_name="save-token-km",
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

        # Fill contenteditable div
        fr = self.bridge.fill(s, "div.chat-input-editor", question)
        if not fr.get("filled"):
            raise RuntimeError(f"Kimi fill failed: {fr}")
        self.bridge.wait(0.5)
        # Trigger React events
        self.bridge.eval(s, "(function(){const e=document.querySelector('div.chat-input-editor');if(e){e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return'OK'}return'NO'})()")
        self.bridge.wait(0.5)

        # Click send
        sr = self.bridge.click(s, "div.send-button-container")
        if not sr.get("clicked"):
            raise RuntimeError(f"Kimi send failed: {sr}")
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
        for n in ["Kimi", "Moonshot", "内容由 AI 生成", "AI 生成", "仅供参考", "尽管问，带图也行"]:
            ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2:
            ans = "(empty)"
        return AskResult(question=question, answer=ans, thinking=thinking)
