"""
Orchestration engine — ties together splitting, execution, and merging.

This is the top-level pipeline that implements the full Save-Token workflow:

    User Question → Task Splitter → Parallel Execution → Result Merger → Output
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from .task_splitter import Task, split_task
from .async_engine import TaskSpec, TaskResult, BatchResult, execute_parallel_sync
from .merger import merge_results, merge_concatenate
from .options import AskOptions
from .providers.base import AskResult
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

    # Execute: single task or multi-turn — both use the same chat session logic
    import uuid
    from .providers.registry import get_provider as _gp

    s = f"st-{provider}-{uuid.uuid4().hex[:6]}"
    logger.info("│ Chat session %s: %d turns", s, len(specs))

    prov = _gp(provider)
    prov.bridge.navigate_and_wait(s, prov.config.url, wait=8.0)
    if options:
        prov._apply_options(s, options)

    leaf_results = []
    for i, sp in enumerate(specs):
        q = sp.question
        # Embed files in first turn only (context persists for subsequent turns)
        if i == 0 and options and options.file_paths:
            for fp in options.file_paths:
                try:
                    from pathlib import Path
                    content = Path(fp).read_text(encoding="utf-8")
                    lang = Path(fp).suffix.lstrip(".")
                    q = q + f"\n```{lang}\n{content}\n```\n"
                    logger.info("│ Embedded %s (%d chars)", Path(fp).name, len(content))
                except Exception as e:
                    logger.warning("Could not embed %s: %s", fp, e)

        logger.info("│ Turn %d/%d: %s", i+1, len(specs), sp.question[:60])
        # Clear textarea first (multi-turn residue)
        if i > 0:
            prov.bridge.eval(s, "(function(){var t=document.querySelector('textarea');if(t)t.value='';return!!t;})()")
            prov.bridge.wait(0.5)
        fr = prov.bridge.fill(s, "textarea", q)
        if not fr.get("filled"):
            raise RuntimeError(f"DeepSeek fill failed: {fr}")
        prov.bridge.wait(0.5)
        prov.bridge.keys(s, "Enter")
        # Longer wait when files are embedded
        w = prov.config.post_send_wait + (10 if (i == 0 and options and options.file_paths) else 0)
        prov.bridge.wait(w)

        # Poll for answer — ensure we get real AI response
        raw = ""
        for _ in range(15):
            raw = prov.bridge.eval(s, prov.config.response_js)
            if raw and len(raw) > max(40, len(q)) and "Victor" not in raw[:100]:
                break
            prov.bridge.wait(3.0)

        answer = prov._extract_answer(raw, sp.question)
        leaf_results.append(TaskResult(
            task=sp,
            result=AskResult(question=sp.question, answer=answer,
                           provider=provider, url=prov.config.url),
            success=True,
        ))
        logger.info("│ Turn %d/%d ✓ %s", i+1, len(specs), answer[:80])

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
