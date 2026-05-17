"""
Task splitting engine — decomposes complex requests into atomic sub-tasks.

Strategy (in priority order):
1. Heuristic — regex-based detection of numbered lists, steps, parallels
2. LLM-based — ask a provider to split (fallback)

Each leaf task is a self-contained question that one provider can answer.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .logging import get_logger, TaskContext

logger = get_logger(__name__)


@dataclass
class Task:
    """A unit of work — atomic or composed of sub-tasks."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    question: str = ""
    parent_id: Optional[str] = None
    children: List[Task] = field(default_factory=list)
    is_atomic: bool = True
    result: Optional[str] = None
    thinking: Optional[str] = None
    provider: Optional[str] = None
    elapsed_ms: int = 0
    status: str = "pending"
    # Allow flexible metadata
    meta: dict = field(default_factory=dict)

    def flatten(self) -> List[Task]:
        """Return all leaf (atomic) tasks in execution order."""
        if self.is_atomic or not self.children:
            return [self] if self.is_atomic else []
        leaves = []
        for child in self.children:
            leaves.extend(child.flatten())
        return leaves

    def to_tree_str(self, indent: int = 0) -> str:
        prefix = "  " * indent
        status_mark = {"pending": "○", "running": "◌", "completed": "●", "failed": "✗"}
        mark = status_mark.get(self.status, "?")
        lines = [f"{prefix}{mark} [{self.id[:8]}] {self.description[:80]}"]
        for child in self.children:
            lines.append(child.to_tree_str(indent + 1))
        return "\n".join(lines)


# ── Heuristic Splitting ────────────────────────────────────────────────────

# Pattern 1: Numbered lists — "1. A\n2. B\n3. C" or "1. A 2. B 3. C"
_NUMBERED = re.compile(
    r'(?:^|\s)(?:\d+[.)]\s*)(.+?)(?=(?:\s+\d+[.)]\s+)|\Z)',
    re.DOTALL,
)

# Pattern 2: Bullet points — "- A\n- B"
_BULLET = re.compile(
    r'(?:^|\n)\s*[-*•]\s+(.+?)(?=(?:\n\s*[-*•]\s+)|\Z)',
    re.DOTALL,
)

# Pattern 3: Explicit keywords — "且", "同时", "并行"
_PARALLEL_MARKERS = re.compile(r'[且和及与、]\s*|同时|并行|分别', re.DOTALL)

# Pattern 4: Step-by-step — "第一步...第二步..."
_STEPS = re.compile(
    r'第[一二三四五六七八九十\d]+步[：:]\s*(.+?)(?=第[一二三四五六七八九十\d]+步[：:]|\Z)',
    re.DOTALL,
)

# Pattern 5: "A 和 B" — comma-separated task descriptions
_COMMA_TASKS = re.compile(r'([^,，]+(?:和|及)[^,，]+)')


def _split_by_delimiter(text: str, pattern: re.Pattern) -> List[str]:
    """Extract sub-items using a regex pattern."""
    matches = pattern.findall(text)
    if not matches:
        return []
    items = [m.strip() for m in matches if len(m.strip()) >= 3]
    # Filter out items that are just the original text
    if len(items) > 1:
        return items
    return []


def _count_markers(text: str) -> int:
    """Count explicit parallel markers."""
    return len(_PARALLEL_MARKERS.findall(text))


def split_heuristic(question: str) -> Optional[List[str]]:
    """Try to split a question using heuristic patterns.

    Returns a list of sub-questions, or None if splitting isn't possible.
    """
    # Try numbered lists first (most reliable)
    items = _split_by_delimiter(question, _NUMBERED)
    if len(items) >= 2:
        logger.debug("Heuristic split: numbered list → %d items", len(items))
        return items

    # Try step-by-step
    items = _split_by_delimiter(question, _STEPS)
    if len(items) >= 2:
        logger.debug("Heuristic split: steps → %d items", len(items))
        return items

    # Try bullet points
    items = _split_by_delimiter(question, _BULLET)
    if len(items) >= 2 and _count_markers(question) >= 1:
        logger.debug("Heuristic split: bullets → %d items", len(items))
        return items

    # Try splitting on "且" / "同时" / "和" for simple parallel tasks
    if _count_markers(question) >= 2 and len(question) > 30:
        # Split on Chinese commas + 和
        parts = re.split(r'[，,；;]', question)
        parts = [p.strip() for p in parts if len(p.strip()) >= 8]
        if len(parts) >= 2:
            logger.debug("Heuristic split: comma-separated → %d items", len(parts))
            return parts

    return None


# ── LLM-based Splitting ────────────────────────────────────────────────────

_SPLIT_PROMPT = """你是一个任务分析专家。请将以下复杂任务拆分为可并行执行的原子子任务。

规则：
1. 每个子任务必须是独立的、可由一个 AI 单独完成的
2. 子任务之间不应有依赖关系（以便并行执行）
3. 如果任务已经足够简单，返回空列表
4. 只输出子任务列表，每行一个，不要编号

输入任务：
{question}

输出（直接写子任务，不要前缀符号）："""


def _load_provider():
    """Lazy import to avoid circular dependency at module level."""
    from .core import ask as _core_ask
    return _core_ask


def split_llm(question: str, provider: str = "deepseek") -> Optional[List[str]]:
    """Use an AI provider to split a complex task.

    Returns sub-questions or None if the task is already atomic.
    """
    prompt = _SPLIT_PROMPT.format(question=question)
    try:
        core_ask = _load_provider()
        result = core_ask(prompt, provider=provider)
        logger.info("LLM split response: %s", result.answer[:120])
        lines = [l.strip() for l in result.answer.split("\n") if l.strip()]
        # Filter out empty/meta lines
        items = [l for l in lines if len(l) >= 3 and not l.startswith(("无", "空", "不需要", "已经是"))]
        if len(items) < 2:
            return None
        return items
    except Exception as e:
        logger.warning("LLM splitting failed: %s, falling back to heuristic", e)
        return None


# ── Main API ────────────────────────────────────────────────────────────────


def split_task(
    question: str,
    *,
    provider: str = "deepseek",
    use_llm: bool = True,
    max_depth: int = 3,
) -> Task:
    """Split a question into a task tree.

    Args:
        question: The user's original question.
        provider: Provider for LLM-based splitting.
        use_llm: Whether to try LLM-based splitting (expensive but smarter).
        max_depth: Maximum recursion depth.

    Returns:
        Root Task node with children.
    """
    root = Task(id=uuid.uuid4().hex[:12], description=question, question=question)
    _split_recursive(root, provider, use_llm, max_depth, depth=0)
    leaves = root.flatten()
    logger.info(
        "Task split: '%s' → %d leaf tasks (depth=%d)",
        question[:60], len(leaves), max_depth,
    )
    return root


def _split_recursive(
    task: Task,
    provider: str,
    use_llm: bool,
    max_depth: int,
    depth: int,
) -> None:
    """Recursively split a task node."""
    if depth >= max_depth:
        return

    question = task.question or task.description

    # Try heuristic first (free, fast)
    sub_items = split_heuristic(question)
    used_llm = False

    # Try LLM if heuristic fails and allowed
    if not sub_items and use_llm and len(question) > 30:
        sub_items = split_llm(question, provider)
        used_llm = bool(sub_items)

    if not sub_items or len(sub_items) < 2:
        # Can't split further — mark as atomic
        task.is_atomic = True
        return

    # Create child tasks
    task.is_atomic = False
    for item in sub_items:
        child = Task(
            id=uuid.uuid4().hex[:12],
            description=item,
            question=item,
            parent_id=task.id,
            is_atomic=True,
        )
        task.children.append(child)
        _split_recursive(child, provider, use_llm, max_depth, depth + 1)

    logger.debug(
        "Split [%s] → %d children (heuristic=%s llm=%s)",
        task.id[:8], len(sub_items),
        not used_llm, used_llm,
    )
