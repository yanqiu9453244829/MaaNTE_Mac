# -*- coding: utf-8 -*-
"""
MaaNTE Platform Abstraction Package.
"""

from __future__ import annotations

import sys
from .base import BaseWindowManager, WindowInfo


def get_window_manager() -> BaseWindowManager:
    """Factory function returning the platform-specific WindowManager."""
    if sys.platform == "darwin":
        from .macos.window import MacOSWindowManager
        return MacOSWindowManager()
    elif sys.platform.startswith("win"):
        from .windows.window import WindowsWindowManager
        return WindowsWindowManager()
    else:
        # Fallback for Linux or other POSIX
        from .macos.window import MacOSWindowManager
        return MacOSWindowManager()


__all__ = [
    "BaseWindowManager",
    "WindowInfo",
    "get_window_manager",
]
