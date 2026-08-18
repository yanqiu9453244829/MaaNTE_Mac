# -*- coding: utf-8 -*-
"""
macOS WindowManager Implementation: Exclusively uses MaaFramework Toolkit.find_desktop_windows().

Strict Constraints:
- NO win32api / win32gui / ctypes.windll / pywin32 imports
- NO custom CoreGraphics window enumeration
- Relies on official MaaFramework Toolkit and DesktopWindow dataclass
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from ..base import BaseWindowManager, WindowInfo

try:
    from maa.toolkit import DesktopWindow, Toolkit
except ImportError:
    Toolkit = None  # type: ignore[assignment]
    DesktopWindow = None  # type: ignore[assignment]


class MacOSWindowManager(BaseWindowManager):
    """macOS window discovery and management powered by MaaFramework Toolkit."""

    def enumerate_windows(self) -> List[WindowInfo]:
        """Enumerate desktop windows using MaaFramework Toolkit.find_desktop_windows()."""
        if Toolkit is None or not hasattr(Toolkit, "find_desktop_windows"):
            return []

        try:
            raw_windows = Toolkit.find_desktop_windows()
        except Exception:
            return []

        results: List[WindowInfo] = []
        for w in raw_windows:
            # DesktopWindow has attributes: hwnd (holds CGWindowID / window_id on macOS), class_name, window_name
            window_id = getattr(w, "hwnd", 0)
            # Ensure window_id is integer
            if isinstance(window_id, int):
                wid = window_id
            elif hasattr(window_id, "value") and window_id.value is not None:
                wid = int(window_id.value)
            else:
                wid = 0

            title = getattr(w, "window_name", "") or ""
            class_name = getattr(w, "class_name", "") or ""

            results.append(
                WindowInfo(
                    id=wid,
                    title=title,
                    class_name=class_name,
                    width=0,
                    height=0,
                    raw=w,
                )
            )
        return results

    def find_game_window(
        self,
        pattern: str = r"^\s*(异环|NTE).*$",
        **kwargs: Any,
    ) -> Optional[WindowInfo]:
        """
        Find game window across Toolkit desktop windows by bundle/class or title.
        Matches:
        1. Exact/prefix bundle class_name: 'com.pwrd.yh.ios', 'com.pwrd.yh'
        2. Window title regex: '异环', 'NTE'
        3. Window title substring: '异环', 'NTE'
        """
        windows = self.enumerate_windows()
        regex = re.compile(pattern, re.IGNORECASE)

        # 1. Primary: match known game bundle identifier / class_name
        for w in windows:
            if w.class_name and ("com.pwrd.yh" in w.class_name or "yh.ios" in w.class_name):
                return w

        # 2. Title regex match
        for w in windows:
            if w.title and regex.search(w.title):
                return w

        # 3. Title substring fallback
        for w in windows:
            if "异环" in w.title or "NTE" in w.title:
                return w

        return None

    def get_window_id(self, window: WindowInfo | Any) -> Any:
        if isinstance(window, WindowInfo):
            return window.id
        if hasattr(window, "hwnd"):
            wid = getattr(window, "hwnd")
            return wid.value if hasattr(wid, "value") else wid
        return window

    def get_window_size(self, window_id: Any) -> Optional[Tuple[int, int]]:
        """
        On macOS, client resolution is managed by MacOSController or system display.
        """
        return None

    def ensure_window_resolution(
        self,
        width: int = 1280,
        height: int = 720,
        **kwargs: Any,
    ) -> dict:
        """
        On macOS, window resizing is handled by system resolution or native controller scaling.
        """
        return {
            "success": True,
            "reason": "macos_native_resolution",
            "target": (width, height),
        }
