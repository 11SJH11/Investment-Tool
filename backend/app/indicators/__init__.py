"""Indicator plugin package with automatic module discovery."""
from __future__ import annotations

import importlib
import pkgutil

from app.indicators.registry import indicator_registry

for _module in pkgutil.iter_modules(__path__):
    if _module.name not in {"base", "registry"} and not _module.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module.name}")

__all__ = ["indicator_registry"]
