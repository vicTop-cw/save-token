"""CLI entry point — `save-token` and `st` commands."""

import sys
import json
import click

from .core import ask, list_providers
from .config.manager import load_config, save_config, get_provider_config


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
@click.option("-j", "--json-output", is_flag=True,
              help="Output as JSON")
def ask_cmd(question: str, provider: str, retries: int,
            thinking: bool, json_output: bool):
    """Ask a question to a free AI chat provider.

    Uses browser cookies — no API key needed for most providers.
    """
    try:
        result = ask(question, provider=provider, max_retries=retries)
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


if __name__ == "__main__":
    main()
