"""CLI entry point — `save-token` and `st` commands."""

import sys
import json
import click

from .core import ask, list_providers
from .options import AskOptions
from .config.manager import load_config, save_config, get_provider_config
from .logging import configure as configure_logging
from .orchestrator import run as run_pipeline


@click.group()
@click.version_option(version="0.1.0", prog_name="save-token")
def main():
    """save-token — query free AI web chats from the terminal.

    Uses browser automation (OpenCLI) to interact with AI chat
    websites without needing API keys. Supports DeepSeek, 元宝,
    Kimi, and more.

    \b
    Examples:
      st ask "用Python写一个快排"
      st ask "什么是Rust的所有权" -p deepseek
      st ask "今天天气怎么样" -p yuanbao
      st providers
    """
    pass


@main.command()
@click.argument("question")
@click.option("-p", "--provider", default=None,
              help="Provider name (deepseek, yuanbao, kimi)")
@click.option("-r", "--retries", default=2, type=int,
              help="Max retries on failure")
@click.option("-t", "--thinking", is_flag=True,
              help="Show thinking process")
@click.option("--deep-think", is_flag=True, help="Enable deep thinking")
@click.option("--web-search/--no-web-search", default=True,
              help="Enable/disable web search (default: on)")
@click.option("--expert", is_flag=True, help="Enable expert mode")
@click.option("-f", "--file", "files", multiple=True,
              help="Upload file(s) to AI chat")
@click.option("-j", "--json-output", is_flag=True,
              help="Output as JSON")
@click.option("-o", "--output", default=None,
              help="Write answer to file")
def ask_cmd(question: str, provider: str, retries: int,
            thinking: bool, json_output: bool, deep_think: bool,
            web_search: bool, expert: bool, files, output):
    """Ask a question to a free AI chat provider.

    Uses browser cookies — no API key needed for most providers.
    """
    try:
        opts = AskOptions(deep_think=deep_think, web_search=web_search,
                         mode="expert" if expert else "",
                         file_paths=list(files) if files else None)
        result = ask(question, provider=provider, max_retries=retries, ask_options=opts)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    if json_output:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    click.echo(f"\n{'─' * 50}")
    click.echo(f"🤖 {result.provider}  ({result.elapsed_ms}ms)")
    click.echo(f"{'─' * 50}")

    if thinking and result.thinking:
        click.echo(f"\n💭 思考过程:\n{result.thinking}")
        click.echo(f"\n{'─' * 50}")

    click.echo(f"\n{result.answer}")
    click.echo()

    if output:
        from pathlib import Path
        p = Path(output)
        p.write_text(result.answer, encoding="utf-8")
        click.echo(f"📄 Written to {p.resolve()}")


@main.command(name="providers")
def list_providers_cmd():
    """List available AI providers."""
    available = list_providers()
    config = load_config()
    default_name = config["provider"]["default"]["name"]

    click.echo(f"\nAvailable providers ({len(available)}):\n")
    for name in available:
        marker = " ★ (default)" if name == default_name else ""
        pcfg = config["provider"].get(name, {})
        url = pcfg.get("url", "?")
        click.echo(f"  {name:12s}  {url}{marker}")
    click.echo()


@main.group()
def config():
    """Manage configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    cfg = load_config()
    click.echo(json.dumps(cfg, indent=2, ensure_ascii=False, default=str))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a config value. e.g.: st config set provider.default.name yuanbao"""
    cfg = load_config()
    keys = key.split(".")
    target = cfg
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    # Try type coercion
    if value.lower() in ("true", "false"):
        value = value.lower() == "true"
    elif value.isdigit():
        value = int(value)
    target[keys[-1]] = value
    save_config(cfg)
    click.echo(f"  ✓ {key} = {value}")


@config.command("path")
def config_path():
    """Print config file path."""
    from .config.manager import CONFIG_PATH
    click.echo(str(CONFIG_PATH))


# ── Full Pipeline ──────────────────────────────────────────────────────────

@main.command()
@click.argument("question")
@click.option("-p", "--provider", default=None,
              help="Provider name (deepseek, yuanbao, kimi)")
@click.option("-w", "--workers", default=4, type=int,
              help="Max parallel workers (default: 4)")
@click.option("--llm-split", is_flag=True,
              help="Use LLM for task splitting (costs tokens, more accurate)")
@click.option("--llm-merge", is_flag=True,
              help="Use LLM for result merging (costs tokens)")
@click.option("--deep-think", is_flag=True, help="Enable deep thinking")
@click.option("--web-search/--no-web-search", default=True,
              help="Enable/disable web search (default: on)")
@click.option("--expert", is_flag=True, help="Enable expert mode")
@click.option("-f", "--file", "files", multiple=True,
              help="Upload file(s) to AI chat (only first turn)")
@click.option("-j", "--json-output", is_flag=True,
              help="Output as JSON")
@click.option("-o", "--output", default=None,
              help="Write merged answer to file")
@click.option("-v", "--verbose", is_flag=True,
              help="Show detailed progress (task tree, timing)")
@click.option("--dry-run", is_flag=True,
              help="Only split, don't execute")
def run_cmd(question: str, provider: str, workers: int,
            llm_split: bool, llm_merge: bool,
            deep_think: bool, web_search: bool, expert: bool,
            files, json_output: bool, output: str,
            verbose: bool, dry_run: bool):
    """Execute full Save-Token pipeline: split → parallel → merge.

    Complex questions are automatically split into sub-tasks
    and executed in parallel across multiple AI providers.

    \\b
    Examples:
      st run "分析Python、Rust、Go的性能差异，并给出选型建议"
      st run "用Python写快排" --dry-run         # 只拆分不执行
      st run "多任务分析" --llm-split -w 8      # LLM拆分 + 8并发
    """
    configure_logging("DEBUG" if verbose else "INFO")

    opts = AskOptions(deep_think=deep_think, web_search=web_search,
                     mode="expert" if expert else "",
                     file_paths=list(files) if files else None)

    if dry_run:
        from .task_splitter import split_task
        root = split_task(question, provider=provider or "deepseek",
                          use_llm=llm_split)
        click.echo(f"\n🌳 Task Tree ({root.flatten().__len__()} leaves):\n")
        click.echo(root.to_tree_str())
        return

    click.echo(f"\n🔍 Analyzing: {question[:100]}...")
    result = run_pipeline(
        question,
        provider=provider or "deepseek",
        options=opts,
        max_workers=workers,
        use_llm_split=llm_split,
        use_llm_merge=llm_merge,
    )

    if json_output:
        import json as _json
        result_json = {
            "question": result.question,
            "split_method": result.split_method,
            "task_count": result.task_count,
            "elapsed_ms": result.total_elapsed_ms,
            "success": result.success,
            "answer": result.merged_answer,
        }
        click.echo(_json.dumps(result_json, ensure_ascii=False, indent=2))
        return

    # Pretty output
    if verbose:
        click.echo(f"\n🌳 Task Tree ({result.task_count} leaves, {result.split_method}):")
        click.echo(result.root_task.to_tree_str())

    click.echo(f"\n{'═' * 55}")
    click.echo(f"📊 {result.task_count} tasks × {workers} workers  "
               f"({result.total_elapsed_ms}ms)")
    click.echo(f"{'═' * 55}")

    if not result.success:
        failed = [r for r in result.leaf_results if not r.success]
        click.echo(f"\n⚠️  {len(failed)}/{len(result.leaf_results)} tasks failed:")
        for f in failed:
            click.echo(f"  ✗ [{f.task.id[:8]}] {f.task.description[:60]} — {f.error}")

    click.echo(f"\n{result.merged_answer}\n")

    if output:
        from pathlib import Path as _Path
        p = _Path(output)
        p.write_text(result.merged_answer, encoding="utf-8")
        click.echo(f"📄 Written to {p.resolve()}")


# ── Log Management ─────────────────────────────────────────────────────────

@main.group()
def log():
    """Manage logs."""
    pass


@log.command("tail")
@click.option("-n", "--lines", default=20, type=int,
              help="Number of lines to show")
@click.option("-f", "--follow", is_flag=True,
              help="Follow log output (tail -f)")
def log_tail(lines: int, follow: bool):
    """Show recent log entries."""
    from .logging import LOG_DIR
    log_file = LOG_DIR / "save-token.log"
    if not log_file.exists():
        click.echo(f"No log file at {log_file}")
        return

    if follow:
        import subprocess
        subprocess.run(["tail", "-n", str(lines), "-f", str(log_file)])
    else:
        text = log_file.read_text(encoding="utf-8")
        for line in text.split("\n")[-lines:]:
            if line.strip():
                try:
                    import json as _json
                    entry = _json.loads(line)
                    ts = entry.get("ts", "")[11:19] if entry.get("ts") else ""
                    level = entry.get("level", "?")[:5]
                    msg = entry.get("msg", "")[:120]
                    click.echo(f"{ts} {level:<6} {msg}")
                except Exception:
                    click.echo(line[:150])


@log.command("path")
def log_path():
    """Print log directory path."""
    from .logging import LOG_DIR
    click.echo(str(LOG_DIR))


if __name__ == "__main__":
    main()
