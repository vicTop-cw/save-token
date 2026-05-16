"""Provider registry — auto-discovers and loads provider classes."""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, Type

from .base import BaseProvider, ProviderConfig


_provider_classes: Dict[str, Type[BaseProvider]] = {}
_provider_configs: Dict[str, ProviderConfig] = {}


def _discover() -> None:
    if _provider_classes:
        return

    package_dir = Path(__file__).parent
    for finder, name, is_pkg in pkgutil.iter_modules([str(package_dir)]):
        if name in ("base", "registry", "__init__"):
            continue
        try:
            module = importlib.import_module(f".{name}", package="save_token.providers")
            if hasattr(module, "PROVIDER_CONFIG"):
                cfg = getattr(module, "PROVIDER_CONFIG")
                cls = getattr(module, "Provider")
                if isinstance(cfg, ProviderConfig) and issubclass(cls, BaseProvider):
                    _provider_classes[cfg.name] = cls
                    _provider_configs[cfg.name] = cfg
        except ImportError as e:
            pass


def get_provider(name: str = None) -> BaseProvider:
    _discover()
    if name is None:
        from save_token.config.manager import get_provider_config as gpc
        name = gpc(None).get("name", "deepseek")

    if name not in _provider_classes:
        from save_token.config.manager import get_provider_config as gpc
        pcfg = gpc(name)
        raise ValueError(
            f"Provider '{name}' has config but no implementation module.\n"
            f"Available: {list(_provider_classes.keys())}"
        )

    # Start with the provider's built-in defaults from PROVIDER_CONFIG
    default_cfg = _provider_configs.get(name)

    # Overlay user config (only url, deep_think, etc.)
    from save_token.config.manager import get_provider_config as gpc
    user_cfg = gpc(name)

    # Build final config: defaults + user overrides for known fields
    field_names = set(ProviderConfig.__dataclass_fields__.keys())
    merged = {k: getattr(default_cfg, k) for k in field_names if hasattr(default_cfg, k)}
    for k, v in user_cfg.items():
        if k in field_names and v is not None:
            merged[k] = v

    final_cfg = ProviderConfig(**merged)
    return _provider_classes[name](final_cfg)


def list_available() -> list:
    _discover()
    return sorted(_provider_classes.keys())
