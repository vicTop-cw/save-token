"""Thin wrapper around OpenCLI browser commands.

All browser interaction goes through this module so provider code
never calls opencli directly — makes testing and provider evolution easier.
"""

import subprocess
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

OPENCLI_BIN = "/usr/local/bin/opencli"


class OpenCLIBridge:
    """Stateless wrapper — each call is an independent opencli invocation."""

    def __init__(self, binary: str = OPENCLI_BIN):
        self.binary = binary

    def _run(self, *args, timeout: int = 30) -> dict:
        """Run an opencli command and return parsed JSON."""
        cmd = [self.binary] + list(args)
        logger.debug("opencli: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            if stderr and "Press" not in stderr:
                logger.debug("opencli stderr: %s", stderr[:200])
            if stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    # Keys command returns plain text like "Pressed: Enter"
                    logger.debug("opencli non-JSON: %s", stdout[:200])
                    return {"ok": True, "raw": stdout, "note": "non-json response"}
            # stdout empty — could be success or failure
            if result.returncode != 0:
                return {"error": stderr or "unknown", "code": result.returncode}
            return {"ok": True, "raw": ""}
        except subprocess.TimeoutExpired:
            logger.error("opencli timeout: %s", " ".join(cmd))
            return {"error": "timeout", "cmd": " ".join(cmd)}
        except FileNotFoundError:
            raise RuntimeError(
                f"opencli not found at {self.binary}. Install: npm install -g opencli"
            )

    # ── browser commands ──────────────────────────────────────────

    def open(self, session: str, url: str, timeout: int = 30) -> dict:
        return self._run("browser", session, "open", url, timeout=timeout)

    def state(self, session: str, timeout: int = 15) -> dict:
        return self._run("browser", session, "state", timeout=timeout)

    def fill(self, session: str, target: str, text: str, timeout: int = 15) -> dict:
        return self._run("browser", session, "fill", target, text, timeout=timeout)

    def click(self, session: str, target: str, timeout: int = 15) -> dict:
        return self._run("browser", session, "click", target, timeout=timeout)

    def keys(self, session: str, keys: str, timeout: int = 15) -> dict:
        return self._run("browser", session, "keys", keys, timeout=timeout)

    def eval(self, session: str, js: str, timeout: int = 15) -> str:
        """Eval returns raw string, not JSON."""
        cmd = [self.binary, "browser", session, "eval", js]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    def scroll(self, session: str, direction: str, timeout: int = 10) -> dict:
        return self._run("browser", session, "scroll", direction, timeout=timeout)

    def extract(self, session: str, timeout: int = 15) -> dict:
        return self._run("browser", session, "extract", timeout=timeout)

    # ── convenience ───────────────────────────────────────────────

    def wait(self, seconds: float):
        time.sleep(seconds)

    def navigate_and_wait(self, session: str, url: str, wait: float = 4.0) -> dict:
        """Open URL and wait for page load."""
        result = self.open(session, url)
        self.wait(wait)
        return result

    def fill_and_send(self, session: str, input_target: str, send_target: str,
                      text: str, method: str = "enter", pre_wait: float = 0.5) -> dict:
        """Fill input and send — handles both Enter and click methods."""
        fill_result = self.fill(session, input_target, text)
        self.wait(pre_wait)
        if method == "enter":
            send_result = self.keys(session, "Enter")
        else:
            send_result = self.click(session, send_target)
        return {"fill": fill_result, "send": send_result}
