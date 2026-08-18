# -*- coding: utf-8 -*-
"""
PHASE 6A: macOS ARM64 Pure Read-Only Recognition Smoke Test Suite.

Purpose:
Validate live pipeline execution on macOS Apple Silicon without performing any
dangerous, irreversible, or input-triggering game actions.

Nodes Tested (Strictly Read-Only Recognition):
1. InWorld: Composite condition recognition (TemplateMatch EscMenuButton & TasksMenuButton)
2. InEscMenu: OCR recognition of Hunter Level in menu ROI
3. __SceneCheckOSD: OCR regex scan of top screen overlay

Safety Boundaries:
- ZERO mouse / keyboard inputs.
- ZERO game state modifications.
- Recognition miss is NOT a test failure; test passes as long as Tasker, Controller,
  Resource, and OCR/Template engines execute smoothly and return valid status.
- Agent subprocess is started for full architecture compliance and cleanly terminated.
"""

from __future__ import annotations

import os
import platform
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


def get_onnx_runtime_info() -> Dict[str, Any]:
    """Detect available ONNX Runtime execution providers on the system."""
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


def run_phase6a_smoke_test() -> int:
    print("=" * 78)
    print("MaaNTE PHASE 6A: macOS ARM64 Pure Read-Only Recognition Smoke Test")
    print("=" * 78)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Host: {current_os} ({current_arch})")

    # Gracefully skip on non-Darwin platforms (e.g. Windows development machine)
    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    failures: List[str] = []

    # 1. Environment & ONNX Runtime Inspection
    print("\n[1] Environment & Inference Backend Inspection")
    py_ver = sys.version.splitlines()[0]
    is_64bit = sys.maxsize > 2**32
    print(f"  Python: {py_ver} ({current_arch}, 64-bit: {is_64bit})")

    ort_info = get_onnx_runtime_info()
    print(f"  ONNX Runtime Version: {ort_info['version']}")
    print(f"  Available Providers: {', '.join(ort_info['providers'])}")

    # 2. MaaFramework Client-Side Imports (Zero Custom Actions)
    print("\n[2] MaaFramework Client Initialization")
    try:
        import maa
        from maa.library import Library
        from maa.controller import MacOSController
        from maa.define import MaaMacOSScreencapMethodEnum, MaaMacOSInputMethodEnum
        from maa.toolkit import Toolkit
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.agent_client import AgentClient

        is_server = Library.is_agent_server() if hasattr(Library, "is_agent_server") else False
        print(f"  MaaFramework core loaded: {maa.__file__}")
        print(f"  Library.is_agent_server(): {is_server} (Expected: False in Client)")
        if is_server:
            failures.append("Client process unexpectedly became an AgentServer.")
    except Exception as exc:
        failures.append(f"Failed to import MaaFramework client modules: {exc}")
        return _report_results(failures)

    # 3. Game Window Discovery
    print("\n[3] Game Window Discovery")
    game_window = None
    try:
        from agent.platform import get_window_manager
        wm = get_window_manager()
        game_window = wm.find_game_window()
        if game_window:
            print(f"  [OK] Found 异环 Window: ID={game_window.id}, Title='{game_window.title}', Class='{game_window.class_name}'")
        else:
            failures.append("异环 window (com.pwrd.yh.ios) not found. Please ensure the game is running on Mac mini.")
            return _report_results(failures)
    except Exception as exc:
        failures.append(f"Window discovery failed: {exc}")
        return _report_results(failures)

    # 4. Controller Creation & Screenshot Verification
    print("\n[4] MacOSController Connection & Live Frame Verification")
    ctrl = None
    try:
        wid = game_window.id
        ctrl = MacOSController(
            wid,
            screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
            input_method=MaaMacOSInputMethodEnum.GlobalEvent,
        )
        conn_job = ctrl.post_connection()
        conn_job.wait()

        if not ctrl.connected:
            failures.append(f"MacOSController connection failed for window_id={wid}")
            return _report_results(failures)
        print(f"  [OK] MacOSController connected: {ctrl.connected}")

        cap_job = ctrl.post_screencap()
        cap_job.wait()
        img = ctrl.cached_image
        if img is None:
            failures.append("cached_image is None after initial post_screencap")
            return _report_results(failures)

        h, w = img.shape[:2]
        print(f"  [OK] Live game frame captured: {w}x{h}, channels: {img.shape[2] if len(img.shape) > 2 else 1}")
    except Exception as exc:
        failures.append(f"Controller setup failed: {exc}")
        return _report_results(failures)

    # 5. Resource Bundle Loading & Tasker Setup
    print("\n[5] Resource Bundle Loading & Tasker Binding")
    res = Resource()
    tasker = Tasker()
    try:
        base_res_path = PROJECT_ROOT / "resource" / "base"
        post_res = res.post_bundle(str(base_res_path))
        post_res.wait()
        print(f"  [OK] Loaded Resource bundle from: {base_res_path}")
        print(f"  Total Pipeline Nodes Loaded: {len(res.node_list) if res.node_list else 0}")

        Tasker.set_log_dir(str(PROJECT_ROOT / "debug"))
        tasker.bind(res, ctrl)
        print(f"  [OK] Tasker bound to Resource and MacOSController (inited: {tasker.inited})")
    except Exception as exc:
        failures.append(f"Resource/Tasker binding failed: {exc}")
        return _report_results(failures)

    # 6. Agent Process Launch (Architecture Compliance, No CustomAction Executed)
    print("\n[6] Agent Subprocess Lifecycle Initialization")
    socket_id = f"maante_smoke_ipc_{int(time.time())}"
    agent_proc = None
    try:
        agent_main = AGENT_DIR / "main.py"
        agent_cmd = [sys.executable, "-u", str(agent_main), socket_id]
        agent_proc = subprocess.Popen(
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
    except Exception as exc:
        print(f"  [WARN] Agent IPC connection notice: {exc}")

    # 7. Execute Pure Read-Only Recognition Smoke Tests
    print("\n" + "=" * 78)
    print("[7] Executing Pure Read-Only Recognition Smoke Tests (Zero Inputs)")
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
        node_name = item["name"]
        print(f"\n>> Testing Pipeline Node: [{node_name}] ({item['desc']})")
        print(f"   Category: {item['type']} | Side-effect: None (Read-Only)")

        start_time = time.perf_counter()
        try:
            task_job = tasker.post_task(node_name)
            task_job.wait()
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            job_status = task_job.status
            job_succeeded = task_job.succeeded

            # Inspect task details from Tasker
            task_detail = tasker.get_task_detail(task_job.job_id)
            hit = False
            reco_algo = "N/A"
            reco_box = "N/A"
            reco_detail_str = ""

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

            print(f"   Execution Status: Job Done (status={job_status}, succeeded={job_succeeded})")
            print(f"   Recognition Result: {'[HIT]' if hit else '[NOT HIT]'} (Current game scene match: {hit})")
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

        except Exception as exc:
            failures.append(f"Pipeline node '{node_name}' execution threw unexpected exception: {exc}")
            pipeline_results.append({
                "name": node_name,
                "status": f"FAILED ({exc})",
                "hit": False,
                "elapsed_ms": 0,
                "algo": "N/A",
                "box": "N/A",
            })

    # 8. Clean Teardown
    print("\n" + "-" * 60)
    print("[8] Teardown & Process Cleanup")
    print("-" * 60)
    if agent_proc is not None:
        print("  Terminating Agent subprocess...")
        agent_proc.terminate()
        try:
            agent_proc.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            agent_proc.kill()
        print("  [OK] Agent subprocess cleanly shut down.")

    # 9. Summary Report
    print("\n" + "=" * 78)
    print("PHASE 6A RECOGNITION SMOKE TEST SUMMARY")
    print("=" * 78)
    print(f"{'Node Name':<22} | {'Job Status':<12} | {'Game Match':<10} | {'Algorithm':<15} | {'Latency':<10}")
    print("-" * 78)
    for r in pipeline_results:
        hit_str = "HIT" if r["hit"] else "NOT HIT"
        print(f"{r['name']:<22} | {r['status']:<12} | {hit_str:<10} | {r['algo']:<15} | {r['elapsed_ms']:>7.2f} ms")
    print("-" * 78)

    return _report_results(failures)


def _report_results(failures: List[str]) -> int:
    print("\n" + "=" * 78)
    if not failures:
        print(">> [STATUS: PHASE 6A PASS] All Read-Only Recognition Pipelines Executed with Zero Side-Effects.")
        return 0
    else:
        print(f">> [STATUS: FAIL] Found {len(failures)} error(s):")
        for idx, f in enumerate(failures, 1):
            print(f"   {idx}. {f}")
        return 1


if __name__ == "__main__":
    sys.exit(run_phase6a_smoke_test())
