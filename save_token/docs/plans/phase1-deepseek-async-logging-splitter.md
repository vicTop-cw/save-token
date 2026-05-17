# Save-Token Phase 1: DeepSeek + Async Logging + Task Splitter

> **Goal:** Fix DeepSeek provider bugs, add async logging, implement task splitter engine, and dogfood Save-Token to build Save-Token.

**Architecture:** Fix existing provider → add loguru async logging → wire into all modules → implement task_splitter with LLM-driven decomposition → integrate with core.ask() for auto-splitting.

**Tech Stack:** Python 3.10+, loguru, click, opencli, asyncio

---

## Task 1: Fix deepseek.py duplicate code & indentation bug

**Objective:** Remove duplicate file-upload block (lines 64-72 duplicate lines 51-59) and fix indentation on "if not fr.get" at line 74.

**Files:** `save_token/providers/deepseek.py`

**Step 1:** Read current file to confirm exact lines
**Step 2:** Remove lines 64-73 (duplicate upload + duplicate fill)
**Step 3:** Fix line 74 indentation (`if not fr.get("filled"):` should match preceding block)
**Step 4:** Verify file parses: `python -c "import save_token.providers.deepseek"`

---

## Task 2: Add loguru async logging throughout

**Objective:** Replace `logging` with `loguru` for async-safe, structured logging.

**Files:**
- Create: `save_token/logger.py`
- Modify: `save_token/__init__.py`, `core.py`, all `providers/*.py`, `opencli_bridge.py`

**Step 1:** Install loguru: `pip install loguru`
**Step 2:** Create `save_token/logger.py` with async file sink + console sink
**Step 3:** Replace all `logging.getLogger(__name__)` imports with `from save_token.logger import logger`
**Step 4:** Verify: `st ask "1+1=?" -p deepseek` and check `~/.config/save-token/save_token.log`

---

## Task 3: Implement task_splitter engine

**Objective:** Complete the `TaskSplitter` class with LLM-driven recursive decomposition.

**Files:**
- Modify: `save_token/task_splitter.py`

**Step 1:** Add `decompose(question: str) -> Task` method using DeepSeek to analyze complexity
**Step 2:** Add heuristic fallback for simple tasks (numbered lists, semicolons, "and" patterns)
**Step 3:** Add `estimate_complexity(text: str) -> int` to decide split vs atomic
**Step 4:** Test with simple and compound questions

---

## Task 4: Integrate task_splitter into core.ask()

**Objective:** Auto-split complex questions before sending to provider.

**Files:**
- Modify: `save_token/core.py`

**Step 1:** Wrap `ask()` with pre-processing: if question is compound, split then ask each sub-task
**Step 2:** Add `split_and_ask()` function that uses task_splitter + parallel execution
**Step 3:** Add `--split` CLI flag: `st ask "..." --split`
**Step 4:** Verify end-to-end with a multi-part question
