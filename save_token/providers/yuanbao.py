"""腾讯元宝 provider — contenteditable div (Quill editor)"""

import logging, re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="yuanbao", url="https://yuanbao.tencent.com/chat",
    description="腾讯元宝 (free)",
    input_selector="div.ql-editor", send_selector="Enter", send_method="keys",
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
    session_name="save-token-yb",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question, options=None):
        s, c = self.config.session_name, self.config
        logger.info("Opening %s", c.url)
        self.bridge.navigate_and_wait(s, c.url, wait=8.0)

        # Yuanbao uses div.ql-editor (Quill contenteditable). Fill via eval.
        fill_js = f"""(function() {{
  const editor = document.querySelector('div.ql-editor');
  if (!editor) return 'E_NOEDITOR';
  editor.focus();
  editor.textContent = {question!r};
  editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return 'OK';
}})()"""
        r = self.bridge.eval(s, fill_js)
        logger.debug("fill eval: %s", r)
        if "E_NOEDITOR" in r:
            # Fallback: try textarea
            fr = self.bridge.fill(s, "textarea", question)
            if not fr.get("filled"):
                raise RuntimeError(f"Yuanbao: no input element found")
        self.bridge.wait(1.0)

        # Send - try clicking send button first, then Enter
        send_js = """(function() {
  const editor = document.querySelector('div.ql-editor');
  if (editor) {
    const container = editor.closest('form') || editor.parentElement?.parentElement;
    if (container) {
      const btns = container.querySelectorAll('button, [role="button"]');
      for (const b of btns) {
        if (b.offsetParent !== null) { b.click(); return 'clicked'; }
      }
    }
  }
  // Enter fallback
  const ev = new KeyboardEvent('keydown', {key:'Enter',code:'Enter',keyCode:13,bubbles:true});
  (editor||document.querySelector('div.ql-editor'))?.dispatchEvent(ev);
  return 'enter';
})()"""
        self.bridge.eval(s, send_js)
        self.bridge.wait(c.post_send_wait)

        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        raw = self.bridge.eval(s, c.response_js)
        ans = raw or ""
        if question and question in ans: ans = ans.split(question, 1)[-1].strip()
        for n in ["腾讯元宝", "yuanbao", "内容由 AI 生成", "AI 生成", "仅供参考", "发送"]:
            ans = ans.replace(n, "")
        ans = re.sub(r'\n{3,}', '\n\n', ans).strip()
        if not ans or len(ans) < 2: ans = "(empty — selectors may need updating)"
        return AskResult(question=question, answer=ans, thinking=thinking)
