"""DeepSeek Chat provider — https://chat.deepseek.com/

Uses OpenCLI eval() to dispatch React input events and click send.
Response extraction via body text minus sidebar noise.

NOTE: DeepSeek renders chat in a portal/panel that body.innerText
may not capture. This provider uses textContent with sidebar
filtering as a fallback. Update response_js when DOM changes.
"""

import logging

from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="deepseek",
    url="https://chat.deepseek.com/",
    description="DeepSeek Chat (free, unlimited)",
    input_selector="0",
    send_selector="1",
    send_method="eval",
    response_js="""
// Extract conversation text minus sidebar noise.
(function() {
  const body = document.body.textContent;
  // Find where sidebar ends (look for known sidebar markers)
  const cutMarkers = ['删除\n', '置顶', '今天', '7 天内'];
  let start = body.length;
  for (const m of cutMarkers) {
    const idx = body.lastIndexOf(m);
    if (idx > 0 && idx < start) start = idx;
  }
  // Get text after sidebar markers + some buffer
  const chat = body.substring(Math.max(0, start - 200));
  // Remove known UI noise
  return chat
    .replace(/深度思考|智能搜索|快速模式|专家模式|重命名|取消置顶|分享|删除/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
})()
""",
    thinking_js="",
    needs_fill_not_type=True,
    post_send_wait=15,
    pre_clear=False,
    session_name="save-token-deepseek",
)


class Provider(BaseProvider):
    """DeepSeek Chat via eval-based browser automation."""

    def __init__(self, config: ProviderConfig = None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question: str) -> AskResult:
        session = self.config.session_name
        cfg = self.config

        # 1. Open DeepSeek
        logger.info("Opening %s", cfg.url)
        result = self.bridge.navigate_and_wait(session, cfg.url, wait=4.0)

        if "sign_in" in str(result.get("url", "")):
            raise RuntimeError(
                "Not logged into DeepSeek. Login in Chrome first."
            )

        # 2. Fill textarea using native value setter + dispatch (React-compatible)
        fill_js = f"""(function() {{
  const ta = document.querySelector('textarea[placeholder*="发送消息"]');
  if (!ta) return 'E_NOTEXTAREA';
  const setter = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype, 'value'
  ).set;
  setter.call(ta, {question!r});
  ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return 'OK';
}})()
"""
        r = self.bridge.eval(session, fill_js)
        logger.debug("fill: %s", r)
        if "E_NOTEXTAREA" in r:
            raise RuntimeError("DeepSeek page structure changed — update input_selector")

        self.bridge.wait(0.8)

        # 3. Click send button via eval
        click_js = """(function() {
  const ta = document.querySelector('textarea[placeholder*="发送消息"]');
  if (!ta) return 'E_NOTEXTAREA';
  // Find the send button sibling
  const container = ta.parentElement?.parentElement || ta.closest('div[class]');
  if (container) {
    const btns = container.querySelectorAll('[role="button"]');
    if (btns.length > 0) { btns[0].click(); return 'clicked'; }
  }
  // Fallback: Enter key
  ta.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
  }));
  return 'enter';
})()
"""
        self.bridge.eval(session, click_js)

        # 4. Wait for response generation
        self.bridge.wait(cfg.post_send_wait)

        # 5. Extract thinking (may appear mid-response)
        thinking = ""
        try:
            thinking = self.bridge.eval(session, cfg.thinking_js) if cfg.thinking_js else ""
        except Exception:
            pass

        # 6. Extract response
        raw = self.bridge.eval(session, cfg.response_js)
        logger.debug("response: %s", raw[:200])

        # 7. Clean up answer — find question and extract after it
        answer = raw or ""
        # Try to isolate the answer: find question text, take what follows
        if question in answer:
            parts = answer.split(question, 1)
            if len(parts) > 1:
                answer = parts[1].strip()
        # Strip common noise
        for noise in ["使用快速模式开始对话", "Victor", "内容由 AI 生成"]:
            answer = answer.replace(noise, "")
        answer = answer.strip()

        if not answer or len(answer) < 2:
            answer = "(empty — may need longer wait or DOM selectors updated)"

        return AskResult(
            question=question,
            answer=answer,
            thinking=thinking,
        )
