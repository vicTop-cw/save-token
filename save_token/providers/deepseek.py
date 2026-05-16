"""DeepSeek Chat provider — CDP fill+keys, supports deep think / web search toggles."""

import logging, re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="deepseek", url="https://chat.deepseek.com/",
    description="DeepSeek Chat (free, unlimited) — supports deep_think & web_search",
    input_selector="textarea", send_selector="Enter", send_method="keys",
    response_js=r"""
(function() {
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()""",
    thinking_js="""(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="deep"], [class*="think"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return ''; })()""",
    needs_fill_not_type=True, post_send_wait=30, pre_clear=False,
    session_name="save-token-ds",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question, options=None):
        s, c = self.config.session_name, self.config
        logger.info("Opening %s", c.url)
        self.bridge.navigate_and_wait(s, c.url, wait=8.0)
        if options:
            self._apply_options(s, options)
        fr = self.bridge.fill(s, "textarea", question)
        if not fr.get("filled"):
            if fr.get("error"): raise RuntimeError(f"DeepSeek fill error: {fr}")
            self.bridge.wait(3.0)
            fr = self.bridge.fill(s, "textarea", question)
            if not fr.get("filled"): raise RuntimeError(f"DeepSeek fill failed: {fr}")
        self.bridge.wait(1.0)
        self.bridge.eval(s, "document.querySelector('textarea')?.focus()")
        self.bridge.wait(0.3)
        self.bridge.keys(s, "Enter")
        self.bridge.wait(c.post_send_wait)
        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass
        raw = self.bridge.eval(s, c.response_js)
        answer = self._extract_answer(raw, question)
        return AskResult(question=question, answer=answer, thinking=thinking)

    def _apply_options(self, session, options):
        # React toggle buttons need PointerEvent sequence, not just .click()
        TRIGGER = ("['pointerdown','mousedown','pointerup','mouseup','click']"
                   ".forEach(t=>b.dispatchEvent(new PointerEvent(t,{bubbles:true,cancelable:true})))")
        if options.deep_think:
            self.bridge.eval(session,
                f"(()=>{{const b=document.querySelector('div.ds-toggle-button');"
                f"if(!b||!b.textContent.includes('深度思考'))return'dt:miss';{TRIGGER};return'dt:on'}})()")
            self.bridge.wait(0.5)
        if not options.web_search:
            self.bridge.eval(session,
                f"(()=>{{const b=document.querySelector('div.ds-toggle-button--selected');"
                f"if(!b||!b.textContent.includes('智能搜索'))return'ws:miss';{TRIGGER};return'ws:off'}})()")
            self.bridge.wait(0.5)

    def _extract_answer(self, raw, question):
        if not raw: return "(empty)"
        victor_pos = raw.rfind("Victor")
        chat_area = raw[victor_pos:] if victor_pos >= 0 else raw
        q_pos = chat_area.rfind(question)
        if q_pos < 0 and len(question) > 3: q_pos = chat_area.rfind(question[:3])
        if q_pos >= 0:
            after = chat_area[q_pos + len(question):].strip()
            if after.startswith(question): after = after[len(question):].strip()
            lines = after.split('\n'); result = []
            for line in lines:
                line = line.strip()
                if not line:
                    if result: break
                    continue
                if line in ('深度思考','智能搜索','快速模式','专家模式','置顶','今天','7 天内','30 天内','Victor','内容由 AI 生成','请仔细甄别','使用快速模式开始对话','开启新对话'): break
                if re.match(r'\d{4}-\d{2}', line): break
                result.append(line)
            ans = '\n'.join(result).strip()
            if ans and len(ans) > 1: return ans
        for marker in ["\n快速模式\n", "\n深度思考\n"]:
            idx = chat_area.rfind(marker)
            if idx >= 0:
                after = chat_area[idx + len(marker):]
                for para in after.split('\n\n'):
                    para = para.strip()
                    if para and len(para) > 2 and para != question: return para
        return "(empty)"
