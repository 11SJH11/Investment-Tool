"""Strategy plugin package.

Any Python module dropped into this directory is imported automatically (except the
base/registry plumbing). A strategy only needs to subclass ``Strategy`` and use the
``@strategy_registry.register`` decorator to appear in Strategy Lab.
"""
from __future__ import annotations

import importlib
import pkgutil

from app.backtesting.strategies.registry import strategy_registry

for _module in pkgutil.iter_modules(__path__):
    if _module.name not in {"base", "registry"} and not _module.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module.name}")

__all__ = ["strategy_registry"]
