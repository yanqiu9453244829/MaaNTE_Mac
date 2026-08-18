# -*- coding: utf-8 -*-
"""
Minimal Experiment Script: MaaFramework macOS Controller Screenshot Scaling Analysis.

Purpose:
Measure physical vs scaled screenshot dimensions produced by MaaFramework MacOSController
under 3 different scaling configurations on the live game window, WITHOUT executing
any Pipeline tasks or sending any keyboard/mouse input.

Configurations tested:
- Mode A: Raw Size (set_screenshot_use_raw_size(True))
- Mode B: Target Long Side = 1280 (set_screenshot_target_long_side(1280))
- Mode C: Target Short Side = 720 (set_screenshot_target_short_side(720))
"""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run_scaling_experiment() -> int:
    print("=" * 78)
    print("MaaNTE: macOS Controller Screenshot Scaling Analysis Experiment")
    print("=" * 78)

    current_os = platform.system()
    current_arch = platform.machine()
    print(f"Current Host: {current_os} ({current_arch})")

    if current_os != "Darwin":
        print("\n[SKIP] macOS-only test: skipped on Windows development host.")
        print("       Target machine: Mac mini Apple Silicon macOS ARM64.")
        print(">> [STATUS: SKIPPED (Non-Darwin)]")
        return 0

    import maa
    from maa.controller import MacOSController
    from maa.define import MaaMacOSScreencapMethodEnum, MaaMacOSInputMethodEnum
    from agent.platform import get_window_manager

    # 1. Discover Window
    print("\n[1] Discovering 异环 Game Window...")
    wm = get_window_manager()
    game_window = wm.find_game_window()
    if not game_window:
        print("[ERROR] 异环 window not found. Please launch the game first.")
        return 1

    print(f"  [OK] Window ID: {game_window.id}, Title: '{game_window.title}', Class: '{game_window.class_name}'")

    # 2. Instantiate MacOSController
    print("\n[2] Connecting MacOSController...")
    ctrl = MacOSController(
        game_window.id,
        screencap_method=MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
        input_method=MaaMacOSInputMethodEnum.GlobalEvent,
    )
    conn_job = ctrl.post_connection()
    conn_job.wait()

    if not ctrl.connected:
        print("[ERROR] MacOSController failed to connect.")
        return 1
    print(f"  [OK] Connected: {ctrl.connected}")

    # Standard 16:9 reference
    STD_16_9 = 16.0 / 9.0  # 1.777778

    modes = [
        ("Mode A: Raw Size", lambda c: c.set_screenshot_use_raw_size(True)),
        ("Mode B: Target Long Side = 1280", lambda c: c.set_screenshot_target_long_side(1280)),
        ("Mode C: Target Short Side = 720", lambda c: c.set_screenshot_target_short_side(720)),
    ]

    print("\n" + "=" * 78)
    print("[3] Running Screenshot Scaling Tests")
    print("=" * 78)

    results = []

    for name, config_fn in modes:
        print(f"\n>> Testing [{name}]...")
        ok = config_fn(ctrl)
        print(f"   Config Applied: {ok}")

        cap_job = ctrl.post_screencap()
        cap_job.wait()

        img = ctrl.cached_image
        if img is None:
            print("   [FAIL] cached_image is None")
            continue

        h, w = img.shape[:2]
        ch = img.shape[2] if len(img.shape) > 2 else 1
        res = ctrl.resolution
        aspect_ratio = w / h if h > 0 else 0.0
        aspect_diff = aspect_ratio - STD_16_9

        # Check InWorld EscMenuButton ROI fit: [1208, 5, 60, 60] -> max_x = 1268, max_y = 65
        fits_esc_roi = (1208 + 60 <= w) and (5 + 60 <= h)

        print(f"   Window Resolution (Logical): {res}")
        print(f"   Cached Image Shape (Physical/Scaled): {w} x {h} (channels: {ch})")
        print(f"   Aspect Ratio: {aspect_ratio:.4f} (Standard 16:9 = {STD_16_9:.4f}, diff = {aspect_diff:+.4f})")
        print(f"   EscMenuButton ROI [1208, 5, 60, 60] fits: {fits_esc_roi} (max_x=1268 <= {w}: {1268 <= w})")

        results.append({
            "mode": name,
            "res": res,
            "img_size": f"{w}x{h}",
            "aspect": f"{aspect_ratio:.4f}",
            "fits_roi": fits_esc_roi,
        })

    print("\n" + "=" * 78)
    print("SCALING ANALYSIS EXPERIMENT SUMMARY")
    print("=" * 78)
    print(f"{'Mode':<32} | {'Logical Res':<14} | {'Image Size':<12} | {'Aspect':<8} | {'Fits 1280x720 ROI'}")
    print("-" * 78)
    for r in results:
        fits_str = "YES (PASS)" if r["fits_roi"] else "NO (OUT OF RANGE)"
        print(f"{r['mode']:<32} | {str(r['res']):<14} | {r['img_size']:<12} | {r['aspect']:<8} | {fits_str}")
    print("-" * 78)

    return 0


if __name__ == "__main__":
    sys.exit(run_scaling_experiment())
