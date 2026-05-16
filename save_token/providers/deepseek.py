"""DeepSeek Chat provider — https://chat.deepseek.com/

Uses OpenCLI CDP commands (fill + keys) for reliable React interaction.
Response extraction via eval JS + Python cleanup.
"""

import logging
import re
from ..opencli_bridge import OpenCLIBridge
from .base import BaseProvider, ProviderConfig, AskResult

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = ProviderConfig(
    name="deepseek",
    url="https://chat.deepseek.com/",
    description="DeepSeek Chat (free, unlimited)",
    input_selector="textarea",
    send_selector="Enter",
    send_method="keys",
    response_js=r"""
(function() {
  const body = document.body.innerText || document.body.textContent || '';
  return body.substring(Math.max(0, body.length - 3000));
})()
""",
    thinking_js="""
(function() {
  const els = document.querySelectorAll('[class*="thinking"], [class*="reasoning"], [class*="deep"], [class*="think"]');
  for (const el of els) {
    const t = el.textContent.trim();
    if (t && t.length > 2) return t;
  }
  return '';
})()
""",
    needs_fill_not_type=True,
    post_send_wait=20,
    pre_clear=False,
    session_name="save-token-ds",
)


class Provider(BaseProvider):
    def __init__(self, config: ProviderConfig = None):
        super().__init__(config or PROVIDER_CONFIG)
        self.bridge = OpenCLIBridge()

    def ask(self, question: str) -> AskResult:
        session = self.config.session_name
        cfg = self.config

        logger.info("Opening %s", cfg.url)
        self.bridge.navigate_and_wait(session, cfg.url, wait=8.0)

        fill_result = self.bridge.fill(session, "textarea", question)
        logger.debug("fill: %s", fill_result)
        if not fill_result.get("filled"):
            if fill_result.get("error"):
                raise RuntimeError(f"DeepSeek fill error: {fill_result}")
            self.bridge.wait(3.0)
            fill_result = self.bridge.fill(session, "textarea", question)
            if not fill_result.get("filled"):
                raise RuntimeError(f"DeepSeek fill failed: {fill_result}")

        self.bridge.wait(1.0)
        self.bridge.eval(session, "document.querySelector('textarea')?.focus()")
        self.bridge.wait(0.3)
        self.bridge.keys(session, "Enter")
        self.bridge.wait(cfg.post_send_wait)

        thinking = ""
        try:
            thinking = self.bridge.eval(session, cfg.thinking_js) if cfg.thinking_js else ""
        except Exception:
            pass

        raw = self.bridge.eval(session, cfg.response_js)
        logger.debug("raw body (last 3000): %s", (raw or "")[:300])

        answer = self._extract_answer(raw, question)
        return AskResult(question=question, answer=answer, thinking=thinking)

    def _extract_answer(self, raw: str, question: str) -> str:
        if not raw:
            return "(empty)"

        # The last "Victor" in page text marks the current chat area;
        # all text above it is sidebar history that we want to skip.
        victor_pos = raw.rfind("Victor")
        chat_area = raw[victor_pos:] if victor_pos >= 0 else raw

        # Find the question in the chat area
        q_pos = chat_area.rfind(question)
        if q_pos < 0 and len(question) > 3:
            q_pos = chat_area.rfind(question[:3])

        if q_pos >= 0:
            after = chat_area[q_pos + len(question):].strip()
            if after.startswith(question):
                after = after[len(question):].strip()
            lines = after.split('\n')
            result = []
            for line in lines:
                line = line.strip()
                if not line:
                    if result:
                        break
                    continue
                if line in ('深度思考', '智能搜索', '快速模式', '专家模式',
                           '置顶', '今天', '7 天内', '30 天内', 'Victor',
                           '内容由 AI 生成', '请仔细甄别',
                           '使用快速模式开始对话', '开启新对话'):
                    break
                if re.match(r'\d{4}-\d{2}', line):
                    break
                result.append(line)
            ans = '\n'.join(result).strip()
            if ans and len(ans) > 1:
                return ans

        # Fallback
        for marker in ["\n快速模式\n", "\n深度思考\n"]:
            idx = chat_area.rfind(marker)
            if idx >= 0:
                after = chat_area[idx + len(marker):]
                for para in after.split('\n\n'):
                    para = para.strip()
                    if para and len(para) > 2 and para != question:
                        return para

        return "(empty)"
