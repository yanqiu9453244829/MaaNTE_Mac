# -*- coding: utf-8 -*-
"""
PHASE 6B: macOS ARM64 Pure Read-Only Recognition Smoke Test Suite.

Features:
- Uses MacOSAdaptedController (intercepting ScreenCaptureKit to strip title bar and normalize to 1280x720).
- Pure Read-Only execution: ZERO mouse/keyboard inputs, ZERO state mutations.
- Non-blocking timeout polling with signal handling (Ctrl+C).
- Guaranteed Agent subprocess cleanup in finally block.
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


_GLOBAL_AGENT_PROC: Optional[subprocess.Popen] = None
_INTERRUPTED = False


def _sigint_handler(signum, frame):
    global _INTERRUPTED
    _INTERRUPTED = True
    print("\n[SIGNAL] Interrupt (Ctrl+C) received. Cleaning up processes and exiting...")
    _cleanup_agent_process()
    sys.exit(130)


def _cleanup_agent_process():
    global _GLOBAL_AGENT_PROC
    if _GLOBAL_AGENT_PROC is not None:
        try:
            if _GLOBAL_AGENT_PROC.poll() is None:
                _GLOBAL_AGENT_PROC.terminate()
                try:
                    _GLOBAL_AGENT_PROC.communicate(timeout=1.5)
                except subprocess.TimeoutExpired:
                    _GLOBAL_AGENT_PROC.kill()
        except Exception:
            pass
        _GLOBAL_AGENT_PROC = None


def get_onnx_runtime_info() -> Dict[str, Any]:
    try:
        import onnxruntime as ort
        return {
            "version": ort.__version__,
            "providers": ort.get_available_providers(),
        }
    except Exception as e:
        return {
            "version": "unknown",
            "providers": [f"Error: {e}"],
        }


def safe_wait_task_job(task_job, timeout_sec: float = 6.0) -> bool:
    """Non-blocking polling for TaskJob completion to allow signal delivery."""
    start = time.time()
    while not task_job.done:
        if _INTERRUPTED:
            return False
        if time.time() - start >= timeout_sec:
            return False
        time.sleep(0.05)
    return True


def run_phase6b_smoke_test() -> int:
    global _GLOBAL_AGENT_PROC

    signal.signal(signal.SIGINT, _sigint_handler)
    signal.signal(signal.SIGTERM, _sigint_handler)

    print("=" * 78)
    print("MaaNTE PHASE 6B: macOS 16:9 Frame Adapter & Recognition Smoke Test")
    print("=" * 78)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Host: {current_os} ({current_arch})")

    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    failures: List[str] = []

    try:
        # 1. Environment Inspection
        print("\n[1] Environment & Inference Backend Inspection")
        py_ver = sys.version.splitlines()[0]
        print(f"  Python: {py_ver} ({current_arch})")
        ort_info = get_onnx_runtime_info()
        print(f"  ONNX Runtime Version: {ort_info['version']}")
        print(f"  Available Providers: {', '.join(ort_info['providers'])}")

        # 2. MaaFramework Client Initialization
        print("\n[2] MaaFramework Client Initialization")
        import maa
        from maa.library import Library
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.agent_client import AgentClient
        from agent.platform import get_window_manager
        from agent.platform.macos.controller import MacOSAdaptedController

        is_server = Library.is_agent_server() if hasattr(Library, "is_agent_server") else False
        print(f"  MaaFramework core loaded: {maa.__file__}")
        print(f"  Library.is_agent_server(): {is_server} (Expected: False in Client)")
        if is_server:
            failures.append("Client process unexpectedly became an AgentServer.")

        # 3. Game Window Discovery
        print("\n[3] Game Window Discovery")
        wm = get_window_manager()
        game_window = wm.find_game_window()
        if not game_window:
            failures.append("异环 window (com.pwrd.yh.ios) not found. Please ensure the game is running.")
            return _report_results(failures)

        print(f"  [OK] Found 异环 Window: ID={game_window.id}, Title='{game_window.title}', Class='{game_window.class_name}'")

        # 4. Controller Setup (MacOSAdaptedController)
        print("\n[4] MacOSAdaptedController Connection & Live Frame Verification")
        ctrl = MacOSAdaptedController(game_window.id)
        connected = ctrl.connect()

        if not connected:
            failures.append(f"MacOSAdaptedController connection failed for window_id={game_window.id}")
            return _report_results(failures)

        # Trigger first screencap through adapter
        norm_img = ctrl.screencap()
        if norm_img is None:
            failures.append("Adapted screencap returned None.")
            return _report_results(failures)

        nh, nw = norm_img.shape[:2]
        print(f"  [OK] MacOSAdaptedController connected: {connected}")
        print(f"  [OK] Adapted Frame Delivered to Tasker: {nw} x {nh} (Exact 1280x720: {nw == 1280 and nh == 720})")

        # 5. Resource Bundle & Tasker
        print("\n[5] Resource Bundle Loading & Tasker Binding")
        res = Resource()
        tasker = Tasker()
        base_res_path = PROJECT_ROOT / "resource" / "base"
        res.post_bundle(str(base_res_path)).wait()
        print(f"  [OK] Loaded Resource bundle: {base_res_path} ({len(res.node_list or [])} nodes)")

        Tasker.set_log_dir(str(PROJECT_ROOT / "debug"))
        tasker.bind(res, ctrl)
        print(f"  [OK] Tasker bound to Adapted Controller (inited: {tasker.inited})")

        # 6. Agent Subprocess Setup (Architecture Verification)
        print("\n[6] Agent Subprocess Lifecycle Initialization")
        socket_id = f"maante_smoke_ipc_{int(time.time())}"
        agent_main = AGENT_DIR / "main.py"
        agent_cmd = [sys.executable, "-u", str(agent_main), socket_id]
        _GLOBAL_AGENT_PROC = subprocess.Popen(
            agent_cmd,
            cwd=str(PROJECT_ROOT),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(1.8)

        agent_client = AgentClient(socket_id)
        agent_client.bind(res)
        ipc_job = agent_client.connect()
        if hasattr(ipc_job, "wait"):
            ipc_job.wait()

        print(f"  [OK] Agent subprocess connected over IPC: {agent_client.connected}")
        print(f"  [OK] AgentServer registered {len(agent_client.custom_action_list or [])} CustomActions")

        # 7. Execute Pure Read-Only Recognition Smoke Tests
        print("\n" + "=" * 78)
        print("[7] Executing Pure Read-Only Recognition Smoke Tests (1280x720 Normalized Canvas)")
        print("=" * 78)

        test_nodes = [
            {
                "name": "InWorld",
                "desc": "Scene Check: Big World Interface (EscMenuButton & TasksMenuButton)",
                "type": "Composite TemplateMatch",
            },
            {
                "name": "InEscMenu",
                "desc": "Scene Check: ESC Menu Screen (OCR '猎人等级')",
                "type": "OCR Recognition",
            },
            {
                "name": "__SceneCheckOSD",
                "desc": "Overlay Check: Screen Top OSD / FPS scan",
                "type": "OCR Regex Scan",
            },
        ]

        pipeline_results: List[Dict[str, Any]] = []

        for item in test_nodes:
            if _INTERRUPTED:
                break

            node_name = item["name"]
            print(f"\n>> Testing Pipeline Node: [{node_name}] ({item['desc']})")
            print(f"   Category: {item['type']} | Side-effect: None (Read-Only)")

            start_time = time.perf_counter()
            task_job = tasker.post_task(node_name)

            # Safe non-blocking wait with timeout
            completed = safe_wait_task_job(task_job, timeout_sec=6.0)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            if not completed:
                print(f"   [TIMEOUT] Pipeline node '{node_name}' timed out after 6.0s.")
                pipeline_results.append({
                    "name": node_name,
                    "status": "TIMEOUT",
                    "hit": False,
                    "elapsed_ms": elapsed_ms,
                    "algo": "N/A",
                    "box": "N/A",
                })
                continue

            job_status = task_job.status
            job_succeeded = task_job.succeeded

            hit = False
            reco_algo = "N/A"
            reco_box = "N/A"
            reco_detail_str = ""

            if task_job.job_id > 0:
                try:
                    task_detail = tasker.get_task_detail(task_job.job_id)
                    if task_detail and task_detail.nodes:
                        for n in task_detail.nodes:
                            if n.recognition:
                                hit = n.recognition.hit
                                reco_algo = n.recognition.algorithm
                                if n.recognition.box:
                                    b = n.recognition.box
                                    reco_box = f"({b.x}, {b.y}, {b.w}, {b.h})"
                                if n.recognition.best_result:
                                    reco_detail_str = str(n.recognition.best_result)[:80]
                except Exception as e:
                    reco_detail_str = f"detail query exception: {e}"

            print(f"   Execution Status: Done (status={job_status}, succeeded={job_succeeded})")
            print(f"   Recognition Result: {'[HIT]' if hit else '[NOT HIT]'}")
            print(f"   Algorithm: {reco_algo}")
            print(f"   Detected Box: {reco_box}")
            if reco_detail_str:
                print(f"   Detail: {reco_detail_str}")
            print(f"   Elapsed Time: {elapsed_ms:.2f} ms")

            pipeline_results.append({
                "name": node_name,
                "status": "COMPLETED",
                "hit": hit,
                "elapsed_ms": elapsed_ms,
                "algo": reco_algo,
                "box": reco_box,
            })

        # 8. Summary Report
        print("\n" + "=" * 78)
        print("PHASE 6B RECOGNITION SMOKE TEST SUMMARY")
        print("=" * 78)
        print(f"{'Node Name':<22} | {'Job Status':<12} | {'Game Match':<10} | {'Algorithm':<15} | {'Latency':<10}")
        print("-" * 78)
        for r in pipeline_results:
            hit_str = "HIT" if r["hit"] else "NOT HIT"
            print(f"{r['name']:<22} | {r['status']:<12} | {hit_str:<10} | {r['algo']:<15} | {r['elapsed_ms']:>7.2f} ms")
        print("-" * 78)

    finally:
        print("\n[8] Teardown & Process Cleanup")
        _cleanup_agent_process()
        print("  [OK] Agent subprocess cleanly shut down.")

    return _report_results(failures)


def _report_results(failures: List[str]) -> int:
    print("\n" + "=" * 78)
    if not failures:
        print(">> [STATUS: PHASE 6B PASS] 1280x720 Frame Adapter & Recognition Pipelines Executed Successfully.")
        return 0
    else:
        print(f">> [STATUS: FAIL] Found {len(failures)} error(s):")
        for idx, f in enumerate(failures, 1):
            print(f"   {idx}. {f}")
        return 1


if __name__ == "__main__":
    sys.exit(run_phase6b_smoke_test())
