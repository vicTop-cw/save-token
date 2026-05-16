"""Provider registry — auto-discovers and loads provider classes."""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, Type

from .base import BaseProvider, ProviderConfig


_provider_classes: Dict[str, Type[BaseProvider]] = {}


def _discover() -> None:
    """Auto-discover provider modules in this package."""
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
        except ImportError as e:
            pass  # Missing deps — skip this provider


def get_provider(name: str) -> BaseProvider:
    """Get a provider instance by name."""
    _discover()

    if name not in _provider_classes:
        from save_token.config.manager import get_provider_config as gpc
        pcfg = gpc(name)
        raise ValueError(
            f"Provider '{name}' has config but no implementation module.\n"
            f"Available: {list(_provider_classes.keys())}"
        )

    from save_token.config.manager import get_provider_config as gpc
    pcfg = gpc(name)
    cfg = ProviderConfig(**{k: v for k, v in pcfg.items() if k in ProviderConfig.__dataclass_fields__})
    return _provider_classes[name](cfg)


def list_available() -> list:
    """List all implemented (importable) provider names."""
    _discover()
    return sorted(_provider_classes.keys())
