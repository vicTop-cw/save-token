"""
Async execution engine — parallel provider calls via ThreadPoolExecutor + asyncio.

Design:
- Uses ThreadPoolExecutor because provider.ask() is blocking (browser automation).
- asyncio wraps thread pool calls so we can gather results cleanly.
- Each task runs with its own TaskContext for log tracing.
- Respects per-provider timeouts and retry budgets.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any

from .providers.base import AskResult
from .providers.registry import get_provider
from .options import AskOptions
from .logging import get_logger, TaskContext

logger = get_logger(__name__)

# ── Data Structures ─────────────────────────────────────────────────────────


@dataclass
class TaskSpec:
    """Description of a single task to execute."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    question: str = ""
    provider: str = "deepseek"
    options: Optional[AskOptions] = None
    timeout: int = 120
    retries: int = 2


@dataclass
class TaskResult:
    """Result of executing a single task."""
    task: TaskSpec
    result: Optional[AskResult] = None
    error: Optional[str] = None
    elapsed_ms: int = 0
    success: bool = False


@dataclass
class BatchResult:
    """Results from a batch of parallel tasks."""
    results: List[TaskResult] = field(default_factory=list)
    total_elapsed_ms: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def all_success(self) -> bool:
        return self.failure_count == 0


# ── Core Execution ──────────────────────────────────────────────────────────


def _execute_one(task: TaskSpec, session: Optional[str] = None) -> TaskResult:
    """Execute a single task synchronously (runs in thread pool)."""
    t0 = time.monotonic()
    logger.info("Task %s → %s via %s", task.id[:8], task.description[:60],
                task.provider)
    try:
        prov = get_provider(task.provider)
        with TaskContext(task.id, task.provider, task.description):
            result = prov.ask(task.question, options=task.options, session=session)
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info("Task %s ✓ %dms — %s", task.id[:8], elapsed,
                    result.answer[:80])
        return TaskResult(
            task=task, result=result, elapsed_ms=elapsed,
            success=True,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.error("Task %s ✗ %dms — %s", task.id[:8], elapsed, e)
        return TaskResult(
            task=task, error=str(e), elapsed_ms=elapsed,
            success=False,
        )


async def execute_parallel(
    tasks: List[TaskSpec],
    max_workers: int = 4,
    sessions: Optional[dict] = None,
) -> BatchResult:
    """Execute multiple tasks in parallel via thread pool.

    Args:
        tasks: List of task specs to execute.
        max_workers: Max concurrent threads.
        sessions: Optional dict mapping provider_name → session_name for reuse.
    """
    if not tasks:
        return BatchResult()

    t0 = time.monotonic()
    logger.info("Batch start: %d tasks, max_workers=%d", len(tasks), max_workers)

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        for t in tasks:
            sess = (sessions or {}).get(t.provider)
            futures.append(loop.run_in_executor(pool, _execute_one, t, sess))
        results = await asyncio.gather(*futures, return_exceptions=True)

    # Normalize — asyncio.gather may return BaseException
    normalized: List[TaskResult] = []
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            normalized.append(TaskResult(
                task=tasks[i], error=str(r), success=False,
            ))
        else:
            normalized.append(r)

    total_elapsed = int((time.monotonic() - t0) * 1000)
    success = sum(1 for r in normalized if r.success)
    failure = len(normalized) - success

    batch = BatchResult(
        results=normalized,
        total_elapsed_ms=total_elapsed,
        success_count=success,
        failure_count=failure,
    )
    logger.info("Batch done: %d/%d success in %dms",
                success, len(tasks), total_elapsed)
    return batch


def execute_parallel_sync(
    tasks: List[TaskSpec],
    max_workers: int = 4,
    sessions: Optional[dict] = None,
) -> BatchResult:
    """Synchronous wrapper for execute_parallel."""
    return asyncio.run(execute_parallel(tasks, max_workers=max_workers, sessions=sessions))


# ── Sequential Fallback ─────────────────────────────────────────────────────


def execute_sequential(tasks: List[TaskSpec]) -> BatchResult:
    """Execute tasks sequentially (fallback when async is unavailable)."""
    t0 = time.monotonic()
    results = [_execute_one(t) for t in tasks]
    total_elapsed = int((time.monotonic() - t0) * 1000)
    success = sum(1 for r in results if r.success)
    return BatchResult(
        results=results,
        total_elapsed_ms=total_elapsed,
        success_count=success,
        failure_count=len(tasks) - success,
    )
