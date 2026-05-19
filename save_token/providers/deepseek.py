"""DeepSeek Chat provider — manual browser automation (native adapter unreliable on WSL)."""

import logging, re, time, uuid
from pathlib import Path
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

def _get_username_identifiers() -> list:
    try:
        from ..config.manager import get_opencli_config
        return get_opencli_config().get("username_identifiers", ["Victor"])
    except ImportError:
        return ["Victor"]

PROVIDER_CONFIG = ProviderConfig(
    name="deepseek", url="https://chat.deepseek.com/",
    description="DeepSeek Chat — deep_think, web_search, expert mode",
    input_selector="textarea", send_selector="Enter", send_method="keys",
    response_js=r"""
(function() {
  const items = document.querySelector('[class*="ds-virtual-list-visible-items"]') ||
                document.querySelector('[class*="ds-virtual-list-items"]');
  if (items && items.children.length > 0) {
    const lastChild = items.children[items.children.length - 1];
    const text = (lastChild.innerText || lastChild.textContent || '').trim();
    if (text && text.length > 10) return text;
  }
  const vl = document.querySelector('[class*="ds-virtual-list"]');
  if (vl) {
    let text = (vl.innerText || vl.textContent || '').trim();
    const footer = '深度思考\n智能搜索\n内容由 AI 生成';
    const fi = text.lastIndexOf(footer);
    if (fi > 0) text = text.substring(0, fi).trim();
    if (text && text.length > 10) return text;
  }
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 2000));
})()""",
    thinking_js="""(function() {
  const body = document.body.innerText || document.body.textContent || '';
  const start = body.lastIndexOf('已思考'); const end = body.lastIndexOf('深度思考');
  if (start >= 0 && end > start) return body.substring(start, end).trim();
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"]');
  for (const el of els) { const t = el.textContent.trim(); if (t && t.length > 2) return t; }
  return ''; })()""",
    needs_fill_not_type=True, post_send_wait=20, pre_clear=False,
    session_name="save-token-ds",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()
        self.username_identifiers = _get_username_identifiers()

    def _unique_session(self):
        return f"{self.config.session_name}-{uuid.uuid4().hex[:8]}"

    def _contains_username(self, text: str) -> bool:
        """Check if text contains any username identifier."""
        for username in self.username_identifiers:
            if username in text:
                return True
        return False

    def ask(self, question, options=None, session=None):
        s = session or self._unique_session()
        c = self.config
        if not session:
            logger.info("Opening %s (session %s)", c.url, s)
            self.bridge.navigate_and_wait(s, c.url, wait=8.0)
            if options:
                self._apply_options(s, options)
        # Upload files via DataTransfer API (hidden input workaround)
        if options and options.file_paths:
            for fp in options.file_paths:
                try:
                    content = Path(fp).read_text(encoding="utf-8")
                    fname = Path(fp).name
                    logger.info("Uploading %s via DataTransfer", fname)
                    # Escape content for JS string
                    escaped = content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
                    upload_js = f"""(() => {{
  const input = document.querySelector('input[type=file]');
  if (!input) return 'NO_INPUT';
  const file = new File([`{escaped}`], '{fname}', {{type: 'text/plain'}});
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', {{bubbles: true}}));
  input.dispatchEvent(new Event('input', {{bubbles: true}}));
  return 'OK:' + input.files[0].name;
}})()"""
                    r = self.bridge.eval(s, upload_js)
                    logger.debug("upload eval: %s", r)
                    if "NO_INPUT" in str(r):
                        raise RuntimeError("File input not found on page")
                    self.bridge.wait(1.0)
                except Exception as e:
                    logger.warning("DataTransfer upload failed: %s, falling back to text embed", e)
                    question = question + f"\n```{Path(fp).suffix.lstrip('.')}\n{content}\n```\n"

        fr = self.bridge.fill(s, "textarea", question)
        if not fr.get("filled"):
            raise RuntimeError(f"DeepSeek fill failed: {fr}")
        self.bridge.wait(0.5)
        self.bridge.keys(s, "Enter")
        # Longer wait for file/context-heavy or expert mode questions
        extra_wait = 0
        if options:
            if options.file_paths: extra_wait += 10
            if options.mode == 'expert': extra_wait += 10
        self.bridge.wait(c.post_send_wait + extra_wait)

        thinking = ""
        try: thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        raw = ""
        # Expert/long answers need more time
        extra_polls = 5 if (options and options.mode == 'expert') else 0
        for _ in range(10 + extra_polls):
            raw = self.bridge.eval(s, c.response_js)
            if raw and len(raw) > 80 and "Victor" not in raw[:100] and "开启新对话" not in raw[:100]:
                break
            self.bridge.wait(3.0)

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
                f"if(!b||!b.textContent.includes('联网搜索'))return'ws:miss';{TRIGGER};return'ws:off'}})()")
            self.bridge.wait(0.5)
        if getattr(options, 'mode', None) == 'expert':
            self.bridge.eval(session,
                f"(()=>{{const btns=document.querySelectorAll('div.ds-toggle-button');"
                f"for(const b of btns){{if(b.textContent.includes('快速模式')){{{TRIGGER};return'exp:on'}}}}"
                f"return'exp:miss'}})()")
            self.bridge.wait(3.0)

    def _extract_answer(self, raw, question):
        if not raw: return "(empty)"
        answer = raw.strip()
        for label in ["快速模式", "深度思考", "智能搜索", "专家模式",
                      "内容由 AI 生成", "请仔细甄别", "置顶", "开启新对话"]:
            answer = answer.replace(label, "")
        if answer.startswith(question): answer = answer[len(question):].strip()
        lines = [l.strip() for l in answer.split("\n") if l.strip()
                 and l.strip() not in ("python", "复制", "下载", "运行")]
        return "\n".join(lines) if lines else "(empty)"
