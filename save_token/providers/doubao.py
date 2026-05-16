"""豆包 provider — textarea with send button"""

import logging, re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="doubao", url="https://www.doubao.com/chat/",
    description="豆包 (ByteDance, free)",
    input_selector="textarea[placeholder*='发消息']", send_selector="button[class*='send']", send_method="click",
    response_js=r"""
(function() {
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

    def ask(self, question, options=None):
        s, c = self.config.session_name, self.config
        logger.info("Opening %s", c.url)
        self.bridge.navigate_and_wait(s, c.url, wait=8.0)

        # Doubao uses textarea with placeholder "发消息..."
        fr = self.bridge.fill(s, "textarea[placeholder*='发消息']", question)
        if not fr.get("filled"):
            raise RuntimeError(f"Doubao fill failed: {fr}")
        self.bridge.wait(0.5)
        # Trigger React input event
        self.bridge.eval(s, "(function(){const e=document.querySelector('textarea[placeholder*=\"发消息\"]');if(e){e.dispatchEvent(new Event('input',{bubbles:true}));return'OK'}return'NO'})()")
        self.bridge.wait(0.5)
        # Click send button
        sr = self.bridge.click(s, "button[class*='send']")
        if not sr.get("clicked"):
            raise RuntimeError(f"Doubao send failed: {sr}")
        self.bridge.wait(c.post_send_wait)

        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        raw = self.bridge.eval(s, c.response_js)
        ans = raw or ""
        if question and question in ans: ans = ans.split(question, 1)[-1].strip()
        for n in ["豆包", "Doubao", "内容由 AI 生成", "AI 生成", "仅供参考", "请仔细甄别"]:
            ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2: ans = "(empty — selectors may need updating)"
        return AskResult(question=question, answer=ans, thinking=thinking)
