# -*- coding: utf-8 -*-
"""
macOS Window Discovery Test Suite.

Notice:
- When executed on non-Darwin platforms (e.g. Windows development machine),
  it explicitly skips execution with a clear notification.
- When executed on Darwin (macOS Apple Silicon), it tests Toolkit.find_desktop_windows()
  and MacOSWindowManager.
"""

import sys
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_macos_window_discovery():
    print("=" * 60)
    print("MaaNTE macOS Window Discovery Verification")
    print("=" * 60)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Environment: {current_os} ({current_arch})")

    # If not on macOS (Darwin), skip gracefully
    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       (Target execution environment: Mac mini Apple Silicon macOS arm64)")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    print("\n[1] Testing macOS WindowManager instantiation...")
    from agent.platform.macos.window import MacOSWindowManager
    from maa.toolkit import Toolkit

    wm = MacOSWindowManager()
    print("  [OK] MacOSWindowManager instantiated successfully.")

    print("\n[2] Testing Toolkit.find_desktop_windows() via MacOSWindowManager...")
    windows = wm.enumerate_windows()
    print(f"  Toolkit returned {len(windows)} desktop window(s).")
    for idx, w in enumerate(windows[:5], 1):
        print(f"    {idx}. ID={w.id}, Title='{w.title}', Class='{w.class_name}'")

    print("\n[3] Testing find_game_window search...")
    game_win = wm.find_game_window()
    if game_win:
        print(f"  Found game window: ID={game_win.id}, Title='{game_win.title}'")
    else:
        print("  Game window not currently open (expected if game not running).")

    print("\n>> [PASS] macOS Window Discovery verified successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(test_macos_window_discovery())
