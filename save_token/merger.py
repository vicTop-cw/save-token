"""
Result merger — combines sub-task results into a unified response.

Strategies:
- Simple concatenation (independent tasks)
- LLM synthesis (complex interdependent tasks, optional)
"""

from __future__ import annotations

from typing import List, Optional

from .task_splitter import Task
from .logging import get_logger

logger = get_logger(__name__)


def merge_concatenate(tasks: List[Task]) -> str:
    """Simple concatenation of completed task results.

    Best for: independent parallel tasks without interdependencies.
    """
    parts = []
    for i, t in enumerate(tasks, 1):
        if t.status == "completed" and t.result:
            parts.append(f"## 子任务 {i}：{t.description[:60]}\n\n{t.result}")
        elif t.status == "failed":
            parts.append(f"## 子任务 {i}：{t.description[:60]}\n\n❌ 失败")
    if not parts:
        return "(所有子任务均未完成)"
    return "\n\n---\n\n".join(parts)


_MERGE_PROMPT = """你是一个结果整合专家。请将以下并行执行的子任务结果整合为一个完整回答。

原始问题：{question}

各子任务结果：
{results}

要求：
1. 整合为一个连贯的回答
2. 消除重复内容
3. 保持逻辑顺序
4. 不要遗漏任何子任务的信息
5. 如果子任务之间发现矛盾，指出矛盾

整合结果："""


def merge_llm(tasks: List[Task], question: str, provider: str = "deepseek") -> str:
    """Use an AI provider to synthesize sub-task results.

    Best for: complex tasks where sub-results need cross-referencing.
    """
    results_text = []
    for i, t in enumerate(tasks, 1):
        if t.result:
            results_text.append(f"子任务{i} [{t.description[:60]}]:\n{t.result}")
        else:
            results_text.append(f"子任务{i} [{t.description[:60]}]: (未完成)")

    prompt = _MERGE_PROMPT.format(
        question=question,
        results="\n\n".join(results_text),
    )

    try:
        from .core import ask
        result = ask(prompt, provider=provider)
        logger.info("LLM merge: %d tasks → %d chars", len(tasks), len(result.answer))
        return result.answer
    except Exception as e:
        logger.warning("LLM merge failed: %s, falling back to concatenation", e)
        return merge_concatenate(tasks)


def merge_results(
    tasks: List[Task],
    question: str = "",
    use_llm: bool = False,
    provider: str = "deepseek",
) -> str:
    """Merge sub-task results into a unified response.

    Args:
        tasks: Completed task nodes with results.
        question: Original user question (for LLM context).
        use_llm: If True, use AI to synthesize (costs tokens).
        provider: Provider for LLM merging.

    Returns:
        Merged result string.
    """
    completed = [t for t in tasks if t.status == "completed" and t.result]
    if not completed:
        return "(无可用结果)"

    if use_llm and len(completed) >= 2:
        return merge_llm(completed, question, provider)

    return merge_concatenate(completed)
