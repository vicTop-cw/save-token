"""Kimi provider — contenteditable div (chat-input-editor)"""

import logging, re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="kimi", url="https://kimi.moonshot.cn/",
    description="Kimi (Moonshot AI, free)",
    input_selector="div.chat-input-editor", send_selector="div.send-button-container", send_method="click",
    response_js=r"""
(function() {
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()""",
    thinking_js="""(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="think"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return ''; })()""",
    needs_fill_not_type=True, post_send_wait=20, pre_clear=False,
    session_name="save-token-km",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question, options=None):
        s, c = self.config.session_name, self.config
        logger.info("Opening %s", c.url)
        self.bridge.navigate_and_wait(s, c.url, wait=8.0)

        # Kimi uses div.chat-input-editor (contenteditable)
        fr = self.bridge.fill(s, "div.chat-input-editor", question)
        if not fr.get("filled"):
            raise RuntimeError(f"Kimi fill failed: {fr}")
        self.bridge.wait(0.5)
        # Trigger React events so Kimi detects the input
        self.bridge.eval(s, "(function(){const e=document.querySelector('div.chat-input-editor');if(e){e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return'OK'}return'NO'})()")
        self.bridge.wait(0.5)
        # Click send button
        sr = self.bridge.click(s, "div.send-button-container")
        if not sr.get("clicked"):
            raise RuntimeError(f"Kimi send failed: {sr}")
        self.bridge.wait(c.post_send_wait)

        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        raw = self.bridge.eval(s, c.response_js)
        ans = raw or ""
        if question and question in ans: ans = ans.split(question, 1)[-1].strip()
        for n in ["Kimi", "Moonshot", "内容由 AI 生成", "AI 生成", "仅供参考", "尽管问，带图也行"]:
            ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2: ans = "(empty — selectors may need updating)"
        return AskResult(question=question, answer=ans, thinking=thinking)
