"""DeepSeek Chat provider — unique session, deep think, thinking extraction."""

import logging, re, time
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="deepseek", url="https://chat.deepseek.com/",
    description="DeepSeek Chat — deep_think & web_search toggles",
    input_selector="textarea", send_selector="Enter", send_method="keys",
    response_js=r"""
(function() {
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()""",
    thinking_js="""
(function() {
  const body = document.body.innerText || document.body.textContent || '';
  const start = body.lastIndexOf('已思考');
  const end = body.lastIndexOf('深度思考');
  if (start >= 0 && end > start) {
    return body.substring(start, end).trim();
  }
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="deep"], [class*="think"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return '';
})()""",
    needs_fill_not_type=True, post_send_wait=30, pre_clear=False,
    session_name="save-token-ds",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def _unique_session(self):
        return f"{self.config.session_name}-{int(time.time()*1000)}"

    def ask(self, question, options=None):
        s = self._unique_session()
        c = self.config
        logger.info("Opening %s (session %s)", c.url, s)
        self.bridge.navigate_and_wait(s, c.url, wait=8.0)
        if options:
            self._apply_options(s, options)

        # Upload files if provided
        if options and options.file_paths:
            for fp in options.file_paths:
                logger.info("Uploading %s", fp)
                ur = self.bridge._run("browser", s, "upload", "input[type=file]", fp, timeout=30)
                logger.debug("upload: %s", ur)
                if not ur.get("uploaded"):
                    raise RuntimeError(f"File upload failed: {ur}")
                self.bridge.wait(2.0)
        fr = self.bridge.fill(s, "textarea", question)
        if not fr.get("filled"):
            if fr.get("error"): raise RuntimeError(f"DeepSeek fill error: {fr}")
            self.bridge.wait(3.0)
    
        # Upload files if provided
        if options and options.file_paths:
            for fp in options.file_paths:
                logger.info("Uploading %s", fp)
                ur = self.bridge._run("browser", s, "upload", "input[type=file]", fp, timeout=30)
                logger.debug("upload: %s", ur)
                if not ur.get("uploaded"):
                    raise RuntimeError(f"File upload failed: {ur}")
                self.bridge.wait(2.0)
        fr = self.bridge.fill(s, "textarea", question)
            if not fr.get("filled"): raise RuntimeError(f"DeepSeek fill failed: {fr}")
        self.bridge.wait(1.0)
        self.bridge.keys(s, "Enter")
        self.bridge.wait(c.post_send_wait)
        thinking = ""
        try:
            thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass
        raw = self.bridge.eval(s, c.response_js)
        answer = self._extract_answer(raw, question)
        return AskResult(question=question, answer=answer, thinking=thinking)

    def _apply_options(self, session, options):
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
            # Deep think mode: answer is last line before toolbar in thinking block
            dt_idx = after.rfind('已思考')
            if dt_idx >= 0:
                toolbar_idx = after.rfind('\n深度思考\n')
                if toolbar_idx > dt_idx:
                    mid = after[dt_idx:toolbar_idx]
                    lines = mid.strip().split('\n')
                    ans = lines[-1].strip() if lines else ""
                    if ans and len(ans) > 2: return ans
            # Standard extraction
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
