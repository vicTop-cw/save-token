"""腾讯元宝 provider — contenteditable div (Quill editor)"""

import logging, re, time, uuid
from pathlib import Path
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="yuanbao", url="https://yuanbao.tencent.com/chat",
    description="腾讯元宝 (free)",
    input_selector="div.ql-editor", send_selector="Enter", send_method="keys",
    response_js=r"""
(function() {
  // Try to find the last AI message bubble
  const bubbles = document.querySelectorAll('[class*="bubble"], [class*="message"], [class*="reply"], [class*="answer"]');
  let last = '';
  for (const el of bubbles) {
    const text = (el.innerText || el.textContent || '').trim();
    if (text.length > 30 && !text.includes('发送') && !text.includes('输入')) {
      last = text;
    }
  }
  if (last) return last;
  // Fallback: body text tail
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()""",
    thinking_js="""(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="think"], [class*="deep"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return ''; })()""",
    needs_fill_not_type=True, post_send_wait=15, pre_clear=False,
    session_name="save-token-yb",
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

        # Embed files as text in first turn
        if options and options.file_paths:
            for fp in options.file_paths:
                try:
                    content = Path(fp).read_text(encoding="utf-8")
                    lang = Path(fp).suffix.lstrip(".")
                    question = question + f"\n```{lang}\n{content}\n```\n"
                except Exception:
                    pass

        # Fill Quill editor via eval
        fill_js = f"""(function() {{
  const editor = document.querySelector('div.ql-editor');
  if (!editor) return 'E_NOEDITOR';
  editor.focus();
  editor.textContent = {question!r};
  editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return 'OK';
}})()"""
        r = self.bridge.eval(s, fill_js)
        if "E_NOEDITOR" in r:
            fr = self.bridge.fill(s, "textarea", question)
            if not fr.get("filled"):
                raise RuntimeError("Yuanbao: no input element found")
        self.bridge.wait(0.5)

        # Click send button or press Enter
        self.bridge.keys(s, "Enter")
        self.bridge.wait(c.post_send_wait)

        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        # Poll for answer
        raw = ""
        for _ in range(10):
            raw = self.bridge.eval(s, c.response_js)
            if raw and len(raw) > 30 and "输入" not in raw[:50]:
                break
            self.bridge.wait(3.0)

        ans = raw or ""
        if question and question in ans:
            ans = ans.split(question, 1)[-1].strip()
        for n in ["腾讯元宝", "yuanbao", "内容由 AI 生成", "AI 生成", "仅供参考", "发送"]:
            ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2:
            ans = "(empty)"
        return AskResult(question=question, answer=ans, thinking=thinking)
