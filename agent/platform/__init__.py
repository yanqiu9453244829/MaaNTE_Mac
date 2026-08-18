# -*- coding: utf-8 -*-
"""
MaaNTE Platform Abstraction Package.

Re-exports standard library `platform` attributes to ensure third-party libraries
(such as maa.define, numpy, scipy, onnxruntime, soundcard) continue to resolve standard platform APIs
without naming collisions when `agent/` is in sys.path.
"""

from __future__ import annotations

import sys as _sys

_stdlib_platform = None
try:
    import importlib.util as _importlib_util
    _orig_path = _sys.path[:]
    _filtered_path = [
        p for p in _orig_path
        if "agent" not in p.replace("\\", "/").split("/") and p != "." and p != ""
    ]
    for _finder in _sys.meta_path:
        if hasattr(_finder, "find_spec"):
            _spec = _finder.find_spec("platform", _filtered_path)
            if _spec and _spec.origin and "agent" not in _spec.origin.replace("\\", "/"):
                _stdlib_platform = _importlib_util.module_from_spec(_spec)
                _spec.loader.exec_module(_stdlib_platform)
                break
except Exception:
    _stdlib_platform = None

# If stdlib platform was loaded, copy its public attributes into globals
if _stdlib_platform is not None:
    for _k, _v in _stdlib_platform.__dict__.items():
        if not _k.startswith("__") or _k == "__doc__":
            globals()[_k] = _v

from .base import BaseWindowManager, WindowInfo


def get_window_manager() -> BaseWindowManager:
    """Factory function returning the platform-specific WindowManager."""
    if _sys.platform == "darwin":
        from .macos.window import MacOSWindowManager
        return MacOSWindowManager()
    elif _sys.platform.startswith("win"):
        from .windows.window import WindowsWindowManager
        return WindowsWindowManager()
    else:
        from .macos.window import MacOSWindowManager
        return MacOSWindowManager()


__all__ = [
    "BaseWindowManager",
    "WindowInfo",
    "get_window_manager",
]
if _stdlib_platform is not None:
    _extra = getattr(_stdlib_platform, "__all__", [k for k in dir(_stdlib_platform) if not k.startswith("_")])
    __all__.extend([k for k in _extra if k not in __all__])
