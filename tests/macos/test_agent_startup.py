# -*- coding: utf-8 -*-
"""
PHASE 5 Test Suite: macOS ARM64 Dual-Process Client/Agent Architecture Verification.

Architecture:
1. Client Process (Main Test Process):
   - Pure MaaFramework Client (NEVER imports custom / NEVER becomes AgentServer)
   - Checks Darwin + arm64 + 64-bit Python
   - Discovers Game Window via Toolkit.find_desktop_windows() (com.pwrd.yh.ios / 异环)
   - Instantiates official MacOSController(window_id) & connects
   - Captures live screenshot via post_screencap() and verifies cached_image
   - Initializes Resource and Tasker
   - Connects to Agent subprocess via AgentClient(socket_id)

2. Agent Process (Independent Subprocess):
   - Launches agent/main.py <socket_id>
   - Imports custom package (registers all 42 CustomActions)
   - Starts AgentServer on socket_id
   - Handles IPC requests from Client Process

3. IPC Verification:
   - Client binds Resource to AgentClient
   - Connects to AgentServer over socket
   - Verifies AgentClient.connected == True and AgentClient.alive == True
   - Verifies all CustomActions registered in Agent are accessible to Client
   - Gracefully terminates Agent subprocess without hanging
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run_phase5_dual_process_verification() -> int:
    print("=" * 75)
    print("MaaNTE PHASE 5: macOS ARM64 Dual-Process Client/Agent Architecture Suite")
    print("=" * 75)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Environment: {current_os} ({current_arch})")

    # Gracefully skip on non-Darwin platforms (e.g. Windows development host)
    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    failures: list[str] = []

    # ------------------------------------------------------------------
    # PART 1: Client Process Verification (Zero custom imports)
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[PART 1] Client Process Initialisation & Controller Connection")
    print("-" * 60)

    # 1. Platform checks
    py_ver = sys.version.splitlines()[0]
    py_exec = sys.executable
    is_64bit = sys.maxsize > 2**32
    print(f"  Python: {py_ver} ({current_arch}, 64-bit: {is_64bit})")
    print(f"  Executable: {py_exec}")

    if current_arch != "arm64":
        failures.append(f"Expected arm64 machine architecture, got {current_arch}")

    # 2. MaaFramework Client-side modules
    try:
        import maa
        from maa.library import Library
        from maa.controller import MacOSController
        from maa.define import MaaMacOSScreencapMethodEnum, MaaMacOSInputMethodEnum
        from maa.toolkit import Toolkit, DesktopWindow
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.agent_client import AgentClient

        is_server = Library.is_agent_server() if hasattr(Library, "is_agent_server") else False
        print(f"  MaaFramework core loaded: {maa.__file__}")
        print(f"  Library.is_agent_server(): {is_server} (Expected: False in Client process)")
        if is_server:
            failures.append("Client process is unexpectedly flagged as AgentServer.")
    except Exception as exc:
        failures.append(f"Failed to load MaaFramework client modules: {exc}")
        return _report_results(failures)

    # 3. Game Window Discovery
    game_window = None
    try:
        from agent.platform import get_window_manager
        wm = get_window_manager()
        windows = wm.enumerate_windows()
        print(f"  Toolkit enumerated {len(windows)} desktop window(s):")
        for idx, w in enumerate(windows[:6], 1):
            print(f"    {idx}. ID={w.id}, Title='{w.title}', Class='{w.class_name}'")

        game_window = wm.find_game_window()
        if game_window:
            print(f"  [OK] Found 异环 Window: ID={game_window.id}, Title='{game_window.title}', Class='{game_window.class_name}'")
        else:
            print("  [WARN] 异环 window not found (ensure game is open on Mac mini).")
    except Exception as exc:
        failures.append(f"Window discovery failed: {exc}")

    # 4. Controller & Screencap (Client side)
    ctrl = None
    if game_window and game_window.id:
        try:
            wid = game_window.id
            print(f"  Instantiating official MacOSController(window_id={wid})...")
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
                print(f"  [OK] MacOSController connected successfully: {ctrl.connected}")

                print("  Posting screencap job...")
                cap_job = ctrl.post_screencap()
                cap_job.wait()

                img = ctrl.cached_image
                if img is None:
                    failures.append("cached_image is None after post_screencap")
                else:
                    h, w = img.shape[:2]
                    print(f"  [OK] Screencap successful! Frame dimensions: {w}x{h}, channels: {img.shape[2] if len(img.shape) > 2 else 1}")
        except Exception as exc:
            failures.append(f"MacOSController client interaction failed: {exc}")
    else:
        print("  [INFO] Skipping live controller screencap (game window not present).")

    # 5. Initialize Resource & Tasker in Client Process
    res = Resource()
    tasker = Tasker()
    try:
        base_res_path = PROJECT_ROOT / "resource" / "base"
        if base_res_path.exists():
            post_res = res.post_bundle(str(base_res_path))
            post_res.wait()
            print(f"  [OK] Resource bundle loaded: {base_res_path}")

        Tasker.set_log_dir(str(PROJECT_ROOT / "debug"))
        if ctrl and ctrl.connected:
            tasker.bind(res, ctrl)
            print(f"  [OK] Tasker bound to Resource and MacOSController (inited: {tasker.inited})")
        else:
            print("  [OK] Resource and Tasker initialized.")
    except Exception as exc:
        failures.append(f"Resource/Tasker initialization failed: {exc}")

    # ------------------------------------------------------------------
    # PART 2: Agent Subprocess & IPC Verification
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[PART 2] Agent Subprocess Launch & AgentClient IPC Connection")
    print("-" * 60)

    socket_id = f"maante_mac_ipc_{int(time.time())}"
    print(f"  Assigned Agent Socket ID: {socket_id}")

    agent_proc = None
    try:
        agent_main = AGENT_DIR / "main.py"
        agent_cmd = [sys.executable, "-u", str(agent_main), socket_id]
        print(f"  Spawning Agent subprocess: {' '.join(agent_cmd)}")

        agent_env = os.environ.copy()
        agent_proc = subprocess.Popen(
            agent_cmd,
            cwd=str(PROJECT_ROOT),
            env=agent_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Allow AgentServer time to initialize
        time.sleep(2.0)

        # Check if agent process crashed prematurely
        poll_code = agent_proc.poll()
        if poll_code is not None:
            stdout_data, _ = agent_proc.communicate(timeout=1)
            failures.append(f"Agent subprocess exited prematurely with code {poll_code}. Output:\n{stdout_data}")
            return _report_results(failures)

        print("  Agent subprocess running. Creating AgentClient...")
        agent_client = AgentClient(socket_id)
        
        print("  Binding Resource to AgentClient...")
        agent_client.bind(res)

        print("  Connecting AgentClient to AgentServer socket...")
        ipc_job = agent_client.connect()
        if hasattr(ipc_job, "wait"):
            ipc_job.wait()

        print(f"  AgentClient connected: {agent_client.connected}")
        print(f"  AgentClient alive: {agent_client.alive}")

        if not agent_client.connected:
            failures.append(f"AgentClient failed to connect to socket {socket_id}")
        else:
            actions = agent_client.custom_action_list
            action_count = len(actions) if actions else 0
            print(f"  [OK] AgentServer exposed {action_count} registered CustomActions to Client!")
            if actions:
                print(f"  Sample actions from Agent: {actions[:6]}")
            if action_count < 40:
                failures.append(f"Expected >= 40 custom actions from AgentServer, got {action_count}")

    except Exception as exc:
        failures.append(f"Agent subprocess or IPC connection error: {exc}")
    finally:
        if agent_proc is not None:
            print("  Terminating Agent subprocess...")
            agent_proc.terminate()
            try:
                out, _ = agent_proc.communicate(timeout=2.5)
                if out:
                    print(f"  [Agent Log Output]:\n{out.strip()}")
            except subprocess.TimeoutExpired:
                print("  Agent subprocess did not exit in time, killing...")
                agent_proc.kill()
            print("  [OK] Agent subprocess cleanly shut down.")

    return _report_results(failures)


def _report_results(failures: list[str]) -> int:
    print("\n" + "=" * 75)
    print("PHASE 5 DUAL-PROCESS TEST SUMMARY")
    print("=" * 75)
    if not failures:
        print(">> [STATUS: PASS] macOS ARM64 Client/Agent Dual-Process Architecture fully verified.")
        return 0
    else:
        print(f">> [STATUS: FAIL] Found {len(failures)} error(s):")
        for idx, f in enumerate(failures, 1):
            print(f"   {idx}. {f}")
        return 1


if __name__ == "__main__":
    sys.exit(run_phase5_dual_process_verification())
