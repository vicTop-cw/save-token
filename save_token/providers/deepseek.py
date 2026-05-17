"""DeepSeek Chat provider — unique session, deep think, thinking extraction."""

import logging, re, time
from pathlib import Path
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="deepseek", url="https://chat.deepseek.com/",
    description="DeepSeek Chat — deep_think & web_search toggles",
    input_selector="textarea", send_selector="Enter", send_method="keys",
    response_js=r"""
(function() {
  // Extract only the latest assistant message
  // ds-virtual-list-visible-items has separate children per message
  const items = document.querySelector('[class*="ds-virtual-list-visible-items"]') ||
                document.querySelector('[class*="ds-virtual-list-items"]');
  if (items && items.children.length > 0) {
    const lastChild = items.children[items.children.length - 1];
    const text = (lastChild.innerText || lastChild.textContent || '').trim();
    if (text && text.length > 10) return text;
  }
  // Fallback: virtual list
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
    needs_fill_not_type=True, post_send_wait=15, pre_clear=False,
    session_name="save-token-ds",
)

class Provider(BaseProvider):
    def __init__(self, config=None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def _unique_session(self):
        import uuid
        return f"{self.config.session_name}-{uuid.uuid4().hex[:8]}"

    def ask(self, question, options=None, session=None):
        """Send a question. If session is given, reuse existing browser tab."""
        s = session or self._unique_session()
        c = self.config
        if not session:
            logger.info("Opening %s (session %s)", c.url, s)
            self.bridge.navigate_and_wait(s, c.url, wait=8.0)
            if options:
                self._apply_options(s, options)
        else:
            logger.info("Reusing session %s (sending follow-up)", s)

        # Upload files — read content and paste as text into textarea
        if options and options.file_paths:
            for fp in options.file_paths:
                logger.info("Uploading %s", fp)
                try:
                    content = Path(fp).read_text(encoding="utf-8")
                    # Paste file content directly into textarea with markdown code block
                    lang = Path(fp).suffix.lstrip(".")
                    file_text = f"\n```{lang}\n{content}\n```\n"
                    # Append to the question text
                    question = question + file_text
                    logger.info("Appended %s (%d chars) to question", Path(fp).name, len(content))
                except Exception as e:
                    logger.warning("Could not read %s: %s", fp, e)
                    # Fall back to browser file upload
                    ur = self.bridge._run("browser", s, "upload", "input[type=file]", fp, timeout=30)
                    if not ur.get("uploaded"):
                        raise RuntimeError(f"File upload failed: {ur}")
                    self.bridge.wait(2.0)

        # Fill and send
        fr = self.bridge.fill(s, "textarea", question)
        if not fr.get("filled"):
            raise RuntimeError(f"DeepSeek fill failed: {fr}")
        self.bridge.wait(0.5)

        self.bridge.keys(s, "Enter")
        # Longer wait for file/context-heavy questions
        wait_time = c.post_send_wait + (10 if options and options.file_paths else 0)
        self.bridge.wait(wait_time)
        thinking = ""
        try:
            thinking = self.bridge.eval(s, c.thinking_js) if c.thinking_js else ""
        except: pass

        # Poll for answer — wait up to 30 more seconds for the response to render
        raw = ""
        for _ in range(10):
            raw = self.bridge.eval(s, c.response_js)
            # Check that we have meaningful content (not just page chrome)
            if raw and len(raw) > 40 and "Victor" not in raw[:100]:
                break
            self.bridge.wait(3.0)

        answer = self._extract_answer(raw, question)
        return AskResult(question=question, answer=answer, thinking=thinking)

    def _apply_options(self, session, options):
        TRIGGER = ("['pointerdown','mousedown','pointerup','mouseup','click']"
                   ".forEach(t=>b.dispatchEvent(new PointerEvent(t,{bubbles:true,cancelable:true})))")
        # Deep think toggle
        if options.deep_think:
            self.bridge.eval(session,
                f"(()=>{{const b=document.querySelector('div.ds-toggle-button');"
                f"if(!b||!b.textContent.includes('深度思考'))return'dt:miss';{TRIGGER};return'dt:on'}})()")
            self.bridge.wait(0.5)
        # Web search toggle
        if not options.web_search:
            self.bridge.eval(session,
                f"(()=>{{const b=document.querySelector('div.ds-toggle-button--selected');"
                f"if(!b||!b.textContent.includes('联网搜索'))return'ws:miss';{TRIGGER};return'ws:off'}})()")
            self.bridge.wait(0.5)
        # Expert mode toggle — causes page reload, need longer wait
        if options.mode == 'expert':
            self.bridge.eval(session,
                f"(()=>{{const btns=document.querySelectorAll('div.ds-toggle-button');"
                f"for(const b of btns){{if(b.textContent.includes('快速模式')){{{TRIGGER};return'exp:on'}}}}"
                f"return'exp:miss'}})()")
            self.bridge.wait(3.0)

    def _extract_answer(self, raw, question):
        """Extract the answer from raw page text.
        
        The JS extractor already targets the AI response directly,
        so minimal post-processing is needed.
        """
        if not raw:
            return "(empty)"
        # Strip UI labels that may leak through
        answer = raw.strip()
        for label in ["快速模式", "深度思考", "智能搜索", "专家模式",
                      "内容由 AI 生成", "请仔细甄别", "置顶", "开启新对话"]:
            answer = answer.replace(label, "")
        # Remove leading question text if present
        if answer.startswith(question):
            answer = answer[len(question):].strip()
        # Remove the question from the end (sidebar entry)
        if question and answer.endswith(question):
            answer = answer[:-len(question)].strip()
        lines = [l.strip() for l in answer.split("\n") if l.strip() and
                 l.strip() not in ("python", "复制", "下载", "运行")]
        return "\n".join(lines) if lines else "(empty)"
