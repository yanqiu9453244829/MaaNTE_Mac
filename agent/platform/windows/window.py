# -*- coding: utf-8 -*-
"""
Windows WindowManager Implementation: Delegates directly to agent/utils/win32_process.py.
"""

from __future__ import annotations

import sys
from typing import Any, List, Optional, Tuple

from ..base import BaseWindowManager, WindowInfo

# Ensure Windows-specific imports only happen on Windows
if sys.platform.startswith("win"):
    try:
        from agent.utils import win32_process
    except ImportError:
        from utils import win32_process
else:
    win32_process = None  # type: ignore[assignment]


class WindowsWindowManager(BaseWindowManager):
    """Windows window discovery and management implementation."""

    def enumerate_windows(self) -> List[WindowInfo]:
        if win32_process is None:
            return []

        # Find all windows using Win32 process enumeration
        results: List[WindowInfo] = []
        try:
            # Enumerate typical game processes or all visible windows
            raw_windows = win32_process.find_windows_by_process(
                process_name=win32_process.DEFAULT_GAME_PROCESS_NAME
            )
            for w in raw_windows:
                size = w.get("client_size") or (0, 0)
                results.append(
                    WindowInfo(
                        id=w["hwnd"],
                        title=w.get("title", ""),
                        class_name=w.get("class_name", ""),
                        width=size[0],
                        height=size[1],
                        raw=w,
                    )
                )
        except Exception:
            pass
        return results

    def find_game_window(
        self,
        pattern: str = r"^(异环|NTE).*$",
        process_name: str = "HTGame.exe",
        **kwargs: Any,
    ) -> Optional[WindowInfo]:
        if win32_process is None:
            return None

        hwnd = win32_process.find_window_by_process(
            process_name=process_name,
            **kwargs,
        )
        if not hwnd:
            return None

        size = win32_process.get_client_size(hwnd) or (0, 0)
        title = win32_process.get_window_text(hwnd)
        class_name = win32_process.get_class_name(hwnd)

        return WindowInfo(
            id=hwnd,
            title=title,
            class_name=class_name,
            width=size[0],
            height=size[1],
            raw={"hwnd": hwnd, "client_size": size},
        )

    def get_window_id(self, window: WindowInfo | Any) -> Any:
        if isinstance(window, WindowInfo):
            return window.id
        if isinstance(window, dict) and "hwnd" in window:
            return window["hwnd"]
        return window

    def get_window_size(self, window_id: Any) -> Optional[Tuple[int, int]]:
        if win32_process is None or not window_id:
            return None
        return win32_process.get_client_size(window_id)

    def ensure_window_resolution(
        self,
        width: int = 1280,
        height: int = 720,
        process_name: str = "HTGame.exe",
        **kwargs: Any,
    ) -> dict:
        if win32_process is None:
            return {"success": False, "reason": "win32_unavailable", "hwnd": None}
        return win32_process.ensure_game_window_resolution(
            width=width,
            height=height,
            process_name=process_name,
            **kwargs,
        )
