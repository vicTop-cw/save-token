"""Config file management — TOML read/write with defaults."""

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None


DEFAULT_CONFIG = {
    "provider": {
        "default": {"name": "deepseek"},
        "deepseek": {"url": "https://chat.deepseek.com/", "deep_think": False},
        "yuanbao": {"url": "https://yuanbao.tencent.com/chat"},
        "kimi": {"url": "https://kimi.moonshot.cn/"},
        "doubao": {"url": "https://www.doubao.com/chat/"},
        "local": {"url": "http://127.0.0.1:1234/v1"},
    },
    "opencli": {
        "binary": "/usr/local/bin/opencli",
        "username_identifiers": ["Victor"],
    },
    "behavior": {
        "response_timeout": 120,
        "max_retries": 2,
        "save_history": True,
    },
}

CONFIG_DIR = Path.home() / ".config" / "save-token"
CONFIG_PATH = CONFIG_DIR / "config.toml"


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            user = tomllib.load(f)
        _deep_merge(config, user)
    return config


def save_config(config: dict) -> None:
    if tomli_w is None:
        raise ImportError("tomli-w required. pip install tomli-w")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(config, f)


def get_provider_config(name: str = None) -> dict:
    config = load_config()
    if name is None:
        name = config["provider"]["default"]["name"]
    provider = config["provider"].get(name, {})
    if not provider:
        raise ValueError(f"Unknown provider: {name}. Available: {list_providers()}")
    return {"name": name, **provider}


def get_opencli_config() -> dict:
    config = load_config()
    return config.get("opencli", {})


def list_providers() -> list:
    config = load_config()
    return [
        k for k in config["provider"].keys()
        if k != "default" and isinstance(config["provider"][k], dict)
    ]
