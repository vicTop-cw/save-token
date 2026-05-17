"""
Structured logging system for save-token.

Features:
- JSON-formatted file logs for machine readability
- Human-readable console output
- Rotating file handler (10 MB × 5 backups)
- Module-level loggers via get_logger(__name__)
- Task execution tracing with context IDs
- Sensitive data masking
"""

import logging
import logging.handlers
import json
import sys
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────

LOG_DIR = Path.home() / ".config" / "save-token" / "logs"
LOG_FILE = LOG_DIR / "save-token.log"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5
DEFAULT_LEVEL = "INFO"

# Fields to mask in log records
_SENSITIVE_FIELDS = {"api_key", "token", "secret", "password", "cookie", "authorization"}

# Thread-local context for task tracing
_ctx = threading.local()


# ── Context Manager ────────────────────────────────────────────────────────

class TaskContext:
    """Thread-local context for correlating log entries within a task."""

    def __init__(self, task_id: str, provider: str = "", description: str = ""):
        self.task_id = task_id
        self.provider = provider
        self.description = description

    def __enter__(self):
        _ctx.task_id = self.task_id
        _ctx.provider = self.provider
        _ctx.description = self.description
        return self

    def __exit__(self, *args):
        _ctx.task_id = None
        _ctx.provider = None
        _ctx.description = None


def get_task_context() -> dict:
    """Return current thread-local task context as a dict."""
    return {
        "task_id": getattr(_ctx, "task_id", None),
        "provider": getattr(_ctx, "provider", None),
    }


# ── Formatters ─────────────────────────────────────────────────────────────

class ConsoleFormatter(logging.Formatter):
    """Human-readable console output with colors."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        ctx = get_task_context()
        tid = ctx.get("task_id", "")
        tid_part = f" [{tid[:8]}]" if tid else ""
        provider = ctx.get("provider", "")
        prov_part = f" [{provider}]" if provider else ""
        level = f"{color}{record.levelname:<8}{self.RESET}"
        msg = f"{ts}{tid_part}{prov_part} {level} {record.getMessage()}"
        return msg


class JSONFormatter(logging.Formatter):
    """Structured JSON output for log files."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_task_context()
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "task_id": ctx.get("task_id"),
            "provider": ctx.get("provider"),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exc"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


# ── Sensitive Data Masking Filter ─────────────────────────────────────────

class SensitiveFilter(logging.Filter):
    """Mask sensitive data in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            for field in _SENSITIVE_FIELDS:
                if field in record.msg.lower():
                    record.msg = record.msg[:500] + "... [masked]"
        return True


# ── Logger Factory ─────────────────────────────────────────────────────────

_root_configured = False
_root_lock = threading.Lock()


def configure(level: str = DEFAULT_LEVEL, log_dir: Optional[Path] = None):
    """Configure root logger with file + console handlers. Idempotent."""
    global _root_configured
    if _root_configured:
        return

    with _root_lock:
        if _root_configured:
            return
        _root_configured = True

    directory = log_dir or LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # File handler — JSON, rotating
    fh = logging.handlers.RotatingFileHandler(
        directory / "save-token.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JSONFormatter())
    fh.addFilter(SensitiveFilter())
    root.addHandler(fh)

    # Console handler — human-readable
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(getattr(logging, level.upper(), logging.WARNING))
    ch.setFormatter(ConsoleFormatter())
    ch.addFilter(SensitiveFilter())
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Calls configure() once."""
    configure()
    return logging.getLogger(name)


def set_level(level: str):
    """Change console log level at runtime."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setLevel(getattr(logging, level.upper(), logging.INFO))
