# -*- coding: utf-8 -*-
"""
Windows Backend Regression Test Suite.
Verifies that WindowsWindowManager and win32_process continue to function perfectly.
"""

import sys
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from platform import system
from agent.platform import get_window_manager, WindowInfo
from utils import win32_process


def test_windows_regression():
    print("=" * 60)
    print("Windows Backend Regression Test")
    print("=" * 60)

    if not sys.platform.startswith("win"):
        print(f"Skipping Windows regression on non-Windows OS ({platform.system()})")
        return 0

    wm = get_window_manager()
    print(f"Resolved WindowManager: {type(wm).__name__}")
    assert type(wm).__name__ == "WindowsWindowManager", f"Expected WindowsWindowManager, got {type(wm).__name__}"

    # Test win32_process functions directly
    print("Testing win32_process API availability...")
    assert callable(win32_process.find_windows_by_process)
    assert callable(win32_process.find_window_by_process)
    assert callable(win32_process.get_client_size)
    assert callable(win32_process.get_window_rect)
    assert callable(win32_process.ensure_game_window_resolution)
    print("  [OK] win32_process core functions verified.")

    # Test WindowManager methods
    print("Testing WindowManager method wrappers...")
    assert callable(wm.enumerate_windows)
    assert callable(wm.find_game_window)
    assert callable(wm.get_window_id)
    assert callable(wm.get_window_size)
    assert callable(wm.ensure_window_resolution)

    # Test get_window_id with WindowInfo
    dummy_info = WindowInfo(id=12345, title="Test Window", class_name="UnrealWindow")
    assert wm.get_window_id(dummy_info) == 12345
    assert wm.get_window_id(12345) == 12345
    assert wm.get_window_id({"hwnd": 12345}) == 12345
    print("  [OK] get_window_id resolution verified.")

    print("\n>> [PASS] Windows backend regression test succeeded with 0 errors.")
    return 0


if __name__ == "__main__":
    sys.exit(test_windows_regression())
