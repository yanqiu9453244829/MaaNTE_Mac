# -*- coding: utf-8 -*-
"""
Platform Abstraction Base Layer: WindowManager and WindowInfo definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class WindowInfo:
    """Standardized cross-platform window descriptor."""
    id: Any                      # HWND on Windows (int), window_id on macOS (int / uint32)
    title: str                   # Window title
    class_name: str = ""         # Window class or bundle identifier
    width: int = 0               # Window / client width
    height: int = 0              # Window / client height
    raw: Any = None              # Underlying platform object (DesktopWindow / dict)

    @property
    def size(self) -> Tuple[int, int]:
        return self.width, self.height


class BaseWindowManager(ABC):
    """Abstract interface for desktop window discovery and management."""

    @abstractmethod
    def enumerate_windows(self) -> List[WindowInfo]:
        """Enumerate all visible desktop windows."""
        raise NotImplementedError

    @abstractmethod
    def find_game_window(
        self,
        pattern: str = r"^(异环|NTE).*$",
        **kwargs: Any,
    ) -> Optional[WindowInfo]:
        """Find the main game window by process name or title pattern."""
        raise NotImplementedError

    @abstractmethod
    def get_window_id(self, window: WindowInfo | Any) -> Any:
        """Extract the numeric window handle/ID from a window object."""
        raise NotImplementedError

    @abstractmethod
    def get_window_size(self, window_id: Any) -> Optional[Tuple[int, int]]:
        """Get the client or outer size (width, height) of a window."""
        raise NotImplementedError

    @abstractmethod
    def ensure_window_resolution(
        self,
        width: int = 1280,
        height: int = 720,
        **kwargs: Any,
    ) -> dict:
        """Ensure the game window client area is resized to target resolution."""
        raise NotImplementedError
