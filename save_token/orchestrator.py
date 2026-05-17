"""
Orchestration engine — ties together splitting, execution, and merging.

This is the top-level pipeline that implements the full Save-Token workflow:

    User Question → Task Splitter → Parallel Execution → Result Merger → Output
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from .task_splitter import Task, split_task
from .async_engine import TaskSpec, TaskResult, BatchResult, execute_parallel_sync
from .merger import merge_results, merge_concatenate
from .options import AskOptions
from .providers.base import AskResult
from .providers.registry import get_provider
from .logging import get_logger, TaskContext

logger = get_logger(__name__)


@dataclass
class RunResult:
    """Top-level result of a save-token run."""
    question: str
    root_task: Task
    leaf_results: List[TaskResult] = field(default_factory=list)
    merged_answer: str = ""
    total_elapsed_ms: int = 0
    success: bool = False
    split_method: str = "none"
    task_count: int = 0


def run(
    question: str,
    *,
    provider: str = "deepseek",
    options: Optional[AskOptions] = None,
    max_workers: int = 4,
    use_llm_split: bool = False,
    use_llm_merge: bool = False,
    max_depth: int = 3,
) -> RunResult:
    """Execute the full Save-Token pipeline.

    Args:
        question: User's question/request.
        provider: Default provider for tasks.
        options: AskOptions (deep_think, web_search, etc.).
        max_workers: Max parallel executor threads.
        use_llm_split: Use LLM for task splitting (costs tokens).
        use_llm_merge: Use LLM for result merging (costs tokens).
        max_depth: Max recursion depth for task splitting.

    Returns:
        RunResult with the merged answer.
    """
    t0 = time.monotonic()
    logger.info("┌─ Run start: '%s'", question[:80])

    # 1. Task splitting
    root = split_task(question, provider=provider, use_llm=use_llm_split,
                      max_depth=max_depth)
    leaves = root.flatten()
    split_method = "llm" if use_llm_split else "heuristic"
    if len(leaves) <= 1:
        split_method = "atomic"
    logger.info("│ Split: %s → %d leaves (%s)", question[:40], len(leaves),
                split_method)

    # 2. Build TaskSpecs
    specs = []
    for leaf in leaves:
        spec = TaskSpec(
            id=leaf.id,
            description=leaf.description,
            question=leaf.question,
            provider=provider,
            options=options,
        )
        specs.append(spec)

    # Execute: sequential multi-turn via prov.ask() with session reuse
    s = f"st-{provider}-{uuid.uuid4().hex[:6]}"
    prov = get_provider(provider)
    logger.info("│ Chat session %s: %d turns", s, len(specs))

    leaf_results = []
    for i, sp in enumerate(specs):
        q = sp.question
        # Embed files in first turn only
        turn_opts = AskOptions(
            deep_think=options.deep_think if options else False,
            web_search=options.web_search if options else True,
            mode=options.mode if options else "",
            file_paths=list(options.file_paths) if (i == 0 and options and options.file_paths) else None,
        )

        logger.info("│ Turn %d/%d: %s", i+1, len(specs), sp.question[:60])
        try:
            result = prov.ask(q, options=turn_opts, session=(s if i == 0 else None))
            leaf_results.append(TaskResult(
                task=sp,
                result=AskResult(question=sp.question, answer=result.answer,
                               provider=provider, url=prov.config.url),
                success=True,
            ))
            logger.info("│ Turn %d/%d ✓ %s", i+1, len(specs), result.answer[:80])
        except Exception as e:
            logger.error("│ Turn %d/%d ✗ %s", i+1, len(specs), e)
            leaf_results.append(TaskResult(
                task=sp, error=str(e), success=False,
            ))

    # Update task statuses
    for lr in leaf_results:
        for leaf in leaves:
            if leaf.id == lr.task.id:
                leaf.status = "completed" if lr.success else "failed"
                leaf.result = lr.result.answer if lr.result else lr.error
                leaf.elapsed_ms = lr.elapsed_ms

    merged = merge_concatenate([t for t in leaves if t.status == "completed"])

    # 4. Result merging
    completed_tasks = [t for t in leaves if t.status == "completed"]
    if not use_llm_merge:
        # Already merged via concatenate above
        pass
    else:
        merged = merge_results(
            completed_tasks, question,
            use_llm=True, provider=provider,
        )

    total_elapsed = int((time.monotonic() - t0) * 1000)
    success = all(r.success for r in leaf_results)

    logger.info("└─ Run done: %s in %dms (%d/%d success)",
                "✓" if success else "✗", total_elapsed,
                sum(1 for r in leaf_results if r.success), len(leaf_results))

    return RunResult(
        question=question,
        root_task=root,
        leaf_results=leaf_results,
        merged_answer=merged,
        total_elapsed_ms=total_elapsed,
        success=success,
        split_method=split_method,
        task_count=len(leaves),
    )
