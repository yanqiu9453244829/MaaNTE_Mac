# -*- coding: utf-8 -*-
"""
MaaNTE macOS Window Capture & Geometry Diagnostic Experiment.

Purpose:
Investigate the exact window geometry, logical points vs physical Retina pixels,
title bar inclusion, ScreenCaptureKit frame boundaries, and aspect ratios of the
《异环》 game window on macOS Apple Silicon.

Strict Safety Boundaries:
- ZERO business code modifications.
- ZERO Pipeline / Tasker execution.
- ZERO AgentServer / Agent subprocess launch.
- ZERO mouse or keyboard input simulation.
- ZERO window resizing (Strictly Read-Only).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def get_native_macos_window_info_via_osascript(app_name: str = "异环") -> Dict[str, Any]:
    """Read window position and size via macOS System Events (AppleScript, Read-Only)."""
    script = (
        'tell application "System Events"\n'
        f'    set procList to every process whose name is "{app_name}" or name contains "异环" or name contains "yh" or name contains "NTE"\n'
        '    if (count of procList) > 0 then\n'
        '        set targetProc to item 1 of procList\n'
        '        set procName to name of targetProc\n'
        '        set winCount to count of windows of targetProc\n'
        '        if winCount > 0 then\n'
        '            set targetWin to window 1 of targetProc\n'
        '            set winPos to position of targetWin\n'
        '            set winSize to size of targetWin\n'
        '            set winTitle to name of targetWin\n'
        '            return "{\\"proc\\":\\"" & procName & "\\",\\"title\\":\\"" & winTitle & "\\",\\"pos\\":[" & (item 1 of winPos) & "," & (item 2 of winPos) & "],\\"size\\":[" & (item 1 of winSize) & "," & (item 2 of winSize) & "]}"\n'
        '        end if\n'
        '    end if\n'
        'end tell\n'
        'return "{}"'
    )
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3.0)
        out = res.stdout.strip()
        if out and out.startswith("{"):
            return json.loads(out)
    except Exception as e:
        return {"error": str(e)}
    return {}


def query_cg_window_info(target_window_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Query window bounds and properties via macOS Quartz (CGWindowListCopyWindowInfo)."""
    results: List[Dict[str, Any]] = []
    if platform.system() != "Darwin":
        return results

    try:
        import Quartz
        wl = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        for w in wl:
            wid = w.get(Quartz.kCGWindowNumber, 0)
            owner = str(w.get(Quartz.kCGWindowOwnerName, ""))
            name = str(w.get(Quartz.kCGWindowName, ""))
            layer = w.get(Quartz.kCGWindowLayer, 0)
            bounds = w.get(Quartz.kCGWindowBounds, {})

            if target_window_id and wid != target_window_id:
                if not any(k in owner or k in name for k in ["异环", "yh", "pwrd", "NTE"]):
                    continue

            results.append({
                "window_id": wid,
                "owner": owner,
                "name": name,
                "layer": layer,
                "bounds": {
                    "x": bounds.get("X", 0),
                    "y": bounds.get("Y", 0),
                    "w": bounds.get("Width", 0),
                    "h": bounds.get("Height", 0),
                } if bounds else {},
            })
    except Exception:
        pass

    return results


def run_geometry_diagnostic() -> int:
    print("=" * 78)
    print("MaaNTE: macOS Window Capture & Geometry Diagnostic Experiment")
    print("=" * 78)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Host: {current_os} ({current_arch})")

    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    import cv2
    import maa
    from maa.controller import MacOSController
    from maa.define import MaaMacOSScreencapMethodEnum, MaaMacOSInputMethodEnum
    from maa.toolkit import Toolkit
    from agent.platform import get_window_manager

    # ------------------------------------------------------------------
    # SECTION A: MaaFramework Toolkit Window Discovery
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[SECTION A] MaaFramework Toolkit Window Discovery")
    print("-" * 60)

    wm = get_window_manager()
    desktop_windows = wm.enumerate_windows()
    print(f"  Toolkit found {len(desktop_windows)} desktop window(s).")

    game_window = wm.find_game_window()
    if not game_window:
        print("  [ERROR] 异环 window (com.pwrd.yh.ios / 异环) not found!")
        return 1

    print("  Selected Game Window:")
    print(f"    - Window ID (hwnd): {game_window.id}")
    print(f"    - Title: '{game_window.title}'")
    print(f"    - Class / Bundle ID: '{game_window.class_name}'")

    # ------------------------------------------------------------------
    # SECTION B: macOS Native Geometry Inspection (AppleScript / CGWindow)
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[SECTION B] macOS Native Window Geometry (Read-Only)")
    print("-" * 60)

    osa_info = get_native_macos_window_info_via_osascript()
    if osa_info:
        print("  AppleScript (System Events) Window Info:")
        print(f"    - Process Name: {osa_info.get('proc')}")
        print(f"    - Window Title: '{osa_info.get('title')}'")
        print(f"    - Position (X, Y): {osa_info.get('pos')}")
        print(f"    - Size (Width, Height): {osa_info.get('size')}")

    cg_windows = query_cg_window_info(game_window.id)
    if cg_windows:
        print("  CoreGraphics (CGWindowList) Info:")
        for idx, cw in enumerate(cg_windows, 1):
            print(f"    {idx}. ID={cw['window_id']}, Owner='{cw['owner']}', Name='{cw['name']}', Layer={cw['layer']}")
            b = cw.get("bounds", {})
            print(f"       Bounds: X={b.get('x')}, Y={b.get('y')}, W={b.get('w')}, H={b.get('h')}")

    # ------------------------------------------------------------------
    # SECTION C: MacOSController Connection & Screenshot Analysis
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[SECTION C] MacOSController Screenshot & Resolution Analysis")
    print("-" * 60)

    ctrl = MacOSController(
        game_window.id,
        screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
        input_method=MaaMacOSInputMethodEnum.GlobalEvent,
    )
    ctrl.post_connection().wait()
    print(f"  MacOSController connected: {ctrl.connected}")

    # Test Raw Mode
    ctrl.set_screenshot_use_raw_size(True)
    ctrl.post_screencap().wait()
    raw_img = ctrl.cached_image

    if raw_img is None:
        print("  [ERROR] raw_img is None")
        return 1

    raw_h, raw_w = raw_img.shape[:2]
    raw_res = ctrl.resolution
    print(f"  MaaController Reported Resolution: {raw_res} (Logical points)")
    print(f"  ScreenCaptureKit Physical Frame Shape: {raw_w} x {raw_h} (Physical pixels)")

    scale_w = raw_w / raw_res[0] if raw_res[0] > 0 else 1.0
    scale_h = raw_h / raw_res[1] if raw_res[1] > 0 else 1.0
    print(f"  Retina Pixel-to-Point Scale Ratio: Width x{scale_w:.4f}, Height x{scale_h:.4f}")

    # ------------------------------------------------------------------
    # SECTION D: Save Diagnostic Screenshots
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("[SECTION D] Exporting Diagnostic Screenshots")
    print("-" * 60)

    out_path_maa = "/tmp/maante_capture_geometry.png"
    try:
        cv2.imwrite(out_path_maa, raw_img)
        print(f"  [OK] Saved MaaFramework CachedImage to: {out_path_maa}")
    except Exception as e:
        print(f"  [WARN] Failed to save {out_path_maa}: {e}")

    out_path_native = "/tmp/maante_native_screencap.png"
    try:
        cmd = ["screencapture", "-l", str(game_window.id), "-o", "-x", out_path_native]
        subprocess.run(cmd, capture_output=True, timeout=3.0)
        if Path(out_path_native).exists():
            native_img = cv2.imread(out_path_native)
            if native_img is not None:
                nh, nw = native_img.shape[:2]
                print(f"  [OK] Saved macOS native screencapture to: {out_path_native} (Shape: {nw}x{nh})")
    except Exception as e:
        print(f"  [WARN] Native screencapture note: {e}")

    # ------------------------------------------------------------------
    # SECTION E: Aspect Ratio & Title Bar Geometry Calculation
    # ------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("[SECTION E] Geometry, Aspect Ratio & Title Bar Derivations")
    print("=" * 78)

    STD_16_9 = 16.0 / 9.0  # 1.777778

    window_w, window_h = raw_res
    window_aspect = window_w / window_h if window_h > 0 else 0.0

    frame_w, frame_h = raw_w, raw_h
    frame_aspect = frame_w / frame_h if frame_h > 0 else 0.0

    print(f"  1. Total Window Logical Bounds : {window_w} x {window_h} pt  (Aspect: {window_aspect:.4f}, 16:9 diff: {window_aspect - STD_16_9:+.4f})")
    print(f"  2. Total Physical Capture Frame: {frame_w} x {frame_h} px  (Aspect: {frame_aspect:.4f}, 16:9 diff: {frame_aspect - STD_16_9:+.4f})")

    ideal_content_h_pt = window_w * 9.0 / 16.0
    derived_titlebar_pt = window_h - ideal_content_h_pt

    ideal_content_h_px = frame_w * 9.0 / 16.0
    derived_titlebar_px = frame_h - ideal_content_h_px

    print("\n  Hypothesis Analysis (Is Title Bar included?):")
    print(f"    - If Content Width = {window_w} pt, ideal 16:9 Content Height = {ideal_content_h_pt:.2f} pt")
    print(f"    - Current Total Window Height = {window_h} pt")
    print(f"    - Derived Title Bar Height (Logical) = {derived_titlebar_pt:.2f} pt (Standard macOS title bar = ~28-38 pt)")
    print(f"    - Derived Title Bar Height (Physical)= {derived_titlebar_px:.2f} px")

    fits_1208 = (1208 + 60) <= frame_w
    print("\n  ROI [1208, 5, 60, 60] Evaluation:")
    print(f"    - Required Width: 1268 px")
    print(f"    - Current Capture Frame Width: {frame_w} px")
    print(f"    - Max X within bounds: {fits_1208} (Over by {1268 - frame_w} px if False)")

    print("\n" + "=" * 78)
    print("DIAGNOSTIC SUMMARY COMPLETE")
    print("=" * 78)
    print("  Artifacts created on Mac:")
    print(f"    1. {out_path_maa}")
    if Path(out_path_native).exists():
        print(f"    2. {out_path_native}")
    print(">> [STATUS: PASS] Window capture geometry diagnostic finished.")
    return 0


if __name__ == "__main__":
    sys.exit(run_geometry_diagnostic())
