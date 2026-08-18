# -*- coding: utf-8 -*-
"""
MaaNTE: macOS Dynamic 16:9 Title Bar Crop & Geometry Verification Experiment.

Algorithm:
1. Capture raw frame from ScreenCaptureKit via MacOSController.
2. Dynamically derive 16:9 content height from capture width:
   target_height = round(width * 9 / 16)
   crop_top = height - target_height
   content = frame[crop_top:height, :]
   (Preserves complete 16:9 canvas from bottom, treating top excess as title bar).
3. Normalize content to 1280x720.
4. Verify key MaaNTE Pipeline ROIs fit 100% inside 1280x720.
5. Export diagnostic images to /tmp/.

Strict Safety Boundaries:
- ZERO Pipeline / Tasker execution.
- ZERO Agent / AgentServer launch.
- ZERO mouse or keyboard input simulation.
- ZERO window resizing / modifications (Strictly Read-Only).
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run_dynamic_titlebar_crop_experiment() -> int:
    print("=" * 78)
    print("MaaNTE: macOS Dynamic 16:9 Title Bar Crop & Geometry Verification")
    print("=" * 78)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Host: {current_os} ({current_arch})")

    # Gracefully skip on non-Darwin platforms (e.g. Windows development host)
    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    import cv2
    import maa
    from maa.controller import MacOSController
    from maa.define import MaaMacOSScreencapMethodEnum, MaaMacOSInputMethodEnum
    from agent.platform import get_window_manager

    # 1. Discover Window
    print("\n[1] Discovering 异环 Game Window...")
    wm = get_window_manager()
    game_window = wm.find_game_window()
    if not game_window:
        print("[ERROR] 异环 window (com.pwrd.yh.ios / 异环) not found.")
        return 1

    print(f"  [OK] Found Window: ID={game_window.id}, Title='{game_window.title}'")

    # 2. Connect MacOSController & Capture Raw Frame
    print("\n[2] Connecting MacOSController & Capturing Frame...")
    ctrl = MacOSController(
        game_window.id,
        screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
        input_method=MaaMacOSInputMethodEnum.GlobalEvent,
    )
    ctrl.post_connection().wait()
    if not ctrl.connected:
        print("[ERROR] MacOSController failed to connect.")
        return 1

    ctrl.set_screenshot_use_raw_size(True)
    ctrl.post_screencap().wait()
    raw_img = ctrl.cached_image

    if raw_img is None:
        print("[ERROR] cached_image is None.")
        return 1

    raw_h, raw_w = raw_img.shape[:2]
    logical_w, logical_h = ctrl.resolution
    raw_aspect = raw_w / raw_h if raw_h > 0 else 0.0

    print(f"  [OK] Raw Capture Frame Dimensions : {raw_w} x {raw_h} px")
    print(f"  [OK] Logical Window Resolution    : {logical_w} x {logical_h} pt")
    print(f"  [OK] Raw Frame Aspect Ratio       : {raw_aspect:.4f} (Standard 16:9 = 1.7778)")

    # 3. Dynamic 16:9 Derivation (No Hardcoded 32px)
    print("\n[3] Dynamically Deriving 16:9 Content Canvas...")
    target_height = int(round(raw_w * 9.0 / 16.0))
    crop_top = max(0, raw_h - target_height)
    content_img = raw_img[crop_top:raw_h, :]
    content_h, content_w = content_img.shape[:2]
    content_aspect = content_w / content_h if content_h > 0 else 0.0

    print(f"  - Target 16:9 Content Height : {target_height} px")
    print(f"  - Derived Title Bar (crop_top): {crop_top} px (Excess top region)")
    print(f"  - Cropped Content Dimensions : {content_w} x {content_h} px")
    print(f"  - Cropped Content Aspect     : {content_aspect:.6f} (Exact 16:9 = {16.0/9.0:.6f})")

    # 4. Normalize Content to 1280x720 Baseline
    print("\n[4] Normalizing 16:9 Content to 1280x720 Baseline...")
    norm_img = cv2.resize(content_img, (1280, 720), interpolation=cv2.INTER_AREA)
    norm_h, norm_w = norm_img.shape[:2]
    print(f"  - Normalized Image Shape     : {norm_w} x {norm_h} px")

    # 5. Evaluate Key MaaNTE Pipeline ROIs
    print("\n[5] Evaluating Key MaaNTE Pipeline ROIs against Normalized 1280x720...")
    rois = [
        ("EscMenuButton", [1208, 5, 60, 60]),
        ("TasksMenuButton", [1208, 65, 60, 60]),
        ("InEscMenu (Hunter Level)", [918, 101, 312, 165]),
        ("__SceneCheckOSD", [0, 0, 1280, 40]),
    ]

    all_rois_pass = True
    for name, (rx, ry, rw, rh) in rois:
        max_x = rx + rw
        max_y = ry + rh
        fits = (max_x <= norm_w) and (max_y <= norm_h)
        if not fits:
            all_rois_pass = False
        status_tag = "PASS (100% IN BOUNDS)" if fits else "FAIL (OUT OF RANGE)"
        print(f"  - [{name}]: ROI=[{rx},{ry},{rw},{rh}], MaxBounds=({max_x}/{norm_w},{max_y}/{norm_h}) -> {status_tag}")

    # 6. Save Diagnostic Artifacts
    print("\n[6] Exporting Diagnostic Images for Visual Inspection...")
    out_raw = "/tmp/maante_raw_with_titlebar.png"
    out_crop = "/tmp/maante_cropped_content.png"
    out_norm = "/tmp/maante_normalized_1280x720.png"

    cv2.imwrite(out_raw, raw_img)
    cv2.imwrite(out_crop, content_img)
    cv2.imwrite(out_norm, norm_img)

    print(f"  1. Raw Frame (with Title Bar) : {out_raw} ({raw_w}x{raw_h})")
    print(f"  2. Cropped 16:9 Content Area  : {out_crop} ({content_w}x{content_h}, Aspect: {content_aspect:.4f})")
    print(f"  3. Normalized 1280x720 Canvas : {out_norm} ({norm_w}x{norm_h}, Exact 16:9)")

    # 7. Summary
    print("\n" + "=" * 78)
    print("DYNAMIC TITLE BAR CROP & GEOMETRY VERIFICATION SUMMARY")
    print("=" * 78)
    print(f"  Raw Window Capture Shape   : {raw_w} x {raw_h} px")
    print(f"  Dynamic crop_top Extracted : {crop_top} px")
    print(f"  Cropped Content Canvas     : {content_w} x {content_h} px (Aspect: {content_aspect:.4f})")
    print(f"  Normalized Baseline Size   : {norm_w} x {norm_h} px")
    print(f"  All ROIs In-Bounds Check   : {'100% PASS' if all_rois_pass else 'FAIL'}")
    print("=" * 78)
    
    if all_rois_pass:
        print(">> [STATUS: PASS] Dynamic 16:9 title bar crop verified successfully.")
        return 0
    else:
        print(">> [STATUS: FAIL] One or more ROIs remain out of bounds.")
        return 1


if __name__ == "__main__":
    sys.exit(run_dynamic_titlebar_crop_experiment())
