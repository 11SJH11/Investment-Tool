"""Strategy plugin package.

Any Python module dropped into this directory is imported automatically (except the
base/registry plumbing). A strategy only needs to subclass ``Strategy`` and use the
``@strategy_registry.register`` decorator to appear in Strategy Lab.
"""
from __future__ import annotations

import sys

from app.backtesting.strategies.registry import strategy_registry

_runtime = sys.modules.get('app.research_runtime')
_inputs = getattr(_runtime, '_inputs', None) or {}
_loaded = strategy_registry.refresh(sources=_inputs.get('strategy_sources'))
if not _loaded['ok']:
    # Startup still reports invalid trusted files explicitly rather than quietly
    # claiming an empty working registry. Runtime refresh rolls back atomically.
    raise ValueError(f"Strategy discovery failed: {_loaded['errors']}")

__all__ = ["strategy_registry"]
