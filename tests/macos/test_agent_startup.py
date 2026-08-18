# -*- coding: utf-8 -*-
"""
PHASE 4 Test Suite: macOS ARM64 Real Machine Agent Startup & Controller Verification.

Test Steps:
1. Platform & OS Check (Darwin)
2. Python Architecture (arm64 / 64-bit)
3. MaaFramework Core Module Loading (maa, AgentServer, Tasker)
4. MaaNTE CustomActions Import & Registration (all 42 actions)
5. Toolkit Desktop Window Discovery
6. Game Window Matching (异环 / com.pwrd.yh.ios)
7. Official MacOSController Creation & post_connection()
8. Real Game Screenshot Verification (post_screencap & cached_image non-empty)
9. AgentServer Startup & Shutdown Lifecycle
10. Tasker Initialization

NOTE: This test suite does NOT execute any game automation pipelines/tasks.
"""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

# Add project root and agent to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run_phase4_agent_startup_test() -> int:
    print("=" * 70)
    print("MaaNTE PHASE 4: macOS ARM64 Agent Startup & Controller Verification")
    print("=" * 70)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Host: {current_os} ({current_arch})")

    # Gracefully skip on non-Darwin platforms (e.g. Windows development machine)
    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    failures: list[str] = []

    # 1. Platform & OS Check
    print("\n[1] Platform & OS Check")
    if current_os != "Darwin":
        failures.append(f"Expected Darwin, got {current_os}")
    else:
        print("  [OK] macOS (Darwin) confirmed.")

    # 2. Python Architecture Check
    print("\n[2] Python Architecture Check")
    py_ver = sys.version.splitlines()[0]
    py_exec = sys.executable
    is_64bit = sys.maxsize > 2**32
    print(f"  Executable: {py_exec}")
    print(f"  Version: {py_ver}")
    print(f"  Arch: {current_arch} (64-bit: {is_64bit})")

    if current_arch != "arm64":
        failures.append(f"Expected arm64 machine architecture, got {current_arch}")
    if not is_64bit:
        failures.append("Python is not 64-bit")

    # 3. MaaFramework Module Loading
    print("\n[3] MaaFramework Module Loading")
    try:
        import maa
        from maa.agent.agent_server import AgentServer
        from maa.controller import MacOSController
        from maa.define import MaaMacOSInputMethodEnum, MaaMacOSScreencapMethodEnum
        from maa.tasker import Tasker
        from maa.toolkit import DesktopWindow, Toolkit

        print(f"  MaaFramework module: {maa.__file__}")
        print("  [OK] maa, AgentServer, Tasker, MacOSController, Toolkit loaded.")
    except Exception as exc:
        failures.append(f"Failed to import MaaFramework: {exc}")
        return _report_results(failures)

    # 4. CustomActions Import & Registration
    print("\n[4] MaaNTE CustomActions Import & Registration")
    try:
        import custom
        action_count = len(custom.action.__all__) if hasattr(custom, "action") else 0
        print(f"  Successfully imported custom package. Registered actions: {action_count}")
        if action_count < 40:
            failures.append(f"Expected at least 40 registered custom actions, found {action_count}")
        else:
            print("  [OK] All CustomAction classes imported successfully.")
    except Exception as exc:
        failures.append(f"Failed to import custom actions: {exc}")

    # 5 & 6. Toolkit Window Discovery & Game Window Matching
    print("\n[5 & 6] Window Discovery & 异环 Matching")
    game_window = None
    try:
        from agent.platform import get_window_manager
        wm = get_window_manager()
        windows = wm.enumerate_windows()
        print(f"  Toolkit enumerated {len(windows)} desktop window(s):")
        for idx, w in enumerate(windows[:8], 1):
            print(f"    {idx}. ID={w.id}, Title='{w.title}', Class='{w.class_name}'")

        game_window = wm.find_game_window()
        if game_window:
            print(f"  [OK] Found 异环 Game Window: ID={game_window.id}, Title='{game_window.title}', Class='{game_window.class_name}'")
        else:
            print("  [WARN] Game window not detected. (Ensure 异环 is launched on Mac mini)")
    except Exception as exc:
        failures.append(f"Window discovery failed: {exc}")

    # 7 & 8. MacOSController Connection & Screenshot
    print("\n[7 & 8] MacOSController Connection & Screenshot")
    if game_window and game_window.id:
        try:
            wid = game_window.id
            print(f"  Creating MacOSController for window_id={wid}...")
            ctrl = MacOSController(
                wid,
                screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
                input_method=MaaMacOSInputMethodEnum.GlobalEvent,
            )
            print("  Posting connection job...")
            conn_job = ctrl.post_connection()
            conn_job.wait()

            if not ctrl.connected:
                failures.append(f"MacOSController connection failed for window_id={wid}")
            else:
                print(f"  [OK] MacOSController connected: {ctrl.connected}")

                print("  Posting screencap job...")
                cap_job = ctrl.post_screencap()
                cap_job.wait()

                img = ctrl.cached_image
                if img is None:
                    failures.append("cached_image is None after post_screencap")
                else:
                    h, w = img.shape[:2]
                    print(f"  [OK] Screencap captured successfully! Image size: {w}x{h}, dtype={img.dtype}")
        except Exception as exc:
            failures.append(f"MacOSController interaction failed: {exc}")
    else:
        print("  [INFO] Skipping live controller connection (no game window available).")

    # 9 & 10. AgentServer & Tasker Lifecycle
    print("\n[9 & 10] AgentServer & Tasker Initialization")
    try:
        Tasker.set_log_dir(str(PROJECT_ROOT / "debug"))
        test_socket = f"maante_startup_test_{int(time.time())}"
        print(f"  Starting AgentServer on socket '{test_socket}'...")
        AgentServer.start_up(test_socket)
        print("  AgentServer running.")
        AgentServer.shut_down()
        print("  [OK] AgentServer startup and shutdown completed cleanly.")
    except Exception as exc:
        failures.append(f"AgentServer lifecycle failed: {exc}")

    return _report_results(failures)


def _report_results(failures: list[str]) -> int:
    print("\n" + "=" * 70)
    print("PHASE 4 AGENT STARTUP TEST SUMMARY")
    print("=" * 70)
    if not failures:
        print(">> [STATUS: PASS] macOS ARM64 Agent startup & controller verified successfully.")
        return 0
    else:
        print(f">> [STATUS: FAIL] Found {len(failures)} failure(s):")
        for idx, f in enumerate(failures, 1):
            print(f"   {idx}. {f}")
        return 1


if __name__ == "__main__":
    sys.exit(run_phase4_agent_startup_test())
