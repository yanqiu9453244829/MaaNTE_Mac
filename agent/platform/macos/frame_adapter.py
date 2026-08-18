# -*- coding: utf-8 -*-
"""
MaaNTE macOS Frame Normalization Adapter.

Purpose:
Dynamically strips the macOS window title bar by bottom-anchoring a 16:9 viewport
and normalizes the resulting game content to the 1280x720 baseline canvas expected
by all MaaNTE Pipeline recognition nodes.

Mathematical Model:
- Input: raw_frame of shape (raw_h, raw_w, channels)
- target_h = round(raw_w * 9 / 16)
- crop_top = max(0, raw_h - target_h)
- content = raw_frame[crop_top:raw_h, :]
- normalized = cv2.resize(content, (1280, 720), interpolation=cv2.INTER_AREA)
"""

from __future__ import annotations

from typing import Any, Dict, Tuple
import cv2
import numpy as np


BASELINE_WIDTH = 1280
BASELINE_HEIGHT = 720


def get_macos_frame_crop_info(raw_h: int, raw_w: int) -> Dict[str, Any]:
    """Calculate the dynamic 16:9 crop and scaling geometry for a given frame size."""
    if raw_h <= 0 or raw_w <= 0:
        raise ValueError(f"Invalid frame dimensions: {raw_w}x{raw_h}")

    target_h = int(round(raw_w * 9.0 / 16.0))
    if target_h <= 0 or target_h > raw_h:
        raise RuntimeError(
            f"Cannot derive valid 16:9 content: raw frame is {raw_w}x{raw_h}, "
            f"target 16:9 height is {target_h} (exceeds raw height {raw_h})."
        )

    crop_top = max(0, raw_h - target_h)
    content_w = raw_w
    content_h = target_h
    content_aspect = content_w / content_h if content_h > 0 else 0.0

    return {
        "raw_width": raw_w,
        "raw_height": raw_h,
        "target_16_9_height": target_h,
        "crop_top": crop_top,
        "content_width": content_w,
        "content_height": content_h,
        "content_aspect": content_aspect,
        "normalized_width": BASELINE_WIDTH,
        "normalized_height": BASELINE_HEIGHT,
    }


def normalize_macos_game_frame(raw_frame: np.ndarray) -> np.ndarray:
    """
    Transform a raw macOS window capture into a clean 1280x720 16:9 frame.

    Raises:
        ValueError: If raw_frame is None, not an ndarray, or has invalid dimensions.
        RuntimeError: If raw_h < target_h (frame is wider than 16:9, cannot crop top).
    """
    if raw_frame is None or not isinstance(raw_frame, np.ndarray) or raw_frame.size == 0:
        raise ValueError("Invalid raw_frame: frame must be a non-empty numpy ndarray.")

    if len(raw_frame.shape) < 2:
        raise ValueError(f"Invalid raw_frame shape: {raw_frame.shape}, expected at least 2 dimensions.")

    raw_h, raw_w = raw_frame.shape[:2]
    info = get_macos_frame_crop_info(raw_h, raw_w)

    crop_top = info["crop_top"]
    content = raw_frame[crop_top:raw_h, :]

    if content.shape[0] <= 0 or content.shape[1] <= 0:
        raise RuntimeError(f"Cropped content has invalid shape: {content.shape}")

    normalized = cv2.resize(
        content,
        (BASELINE_WIDTH, BASELINE_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )

    assert normalized.shape[0] == BASELINE_HEIGHT and normalized.shape[1] == BASELINE_WIDTH, (
        f"Normalized shape mismatch: expected ({BASELINE_HEIGHT}, {BASELINE_WIDTH}), got {normalized.shape[:2]}"
    )

    return normalized


def map_normalized_to_raw_coordinates(
    norm_x: int, norm_y: int, raw_h: int, raw_w: int
) -> Tuple[int, int]:
    """
    Map an (x, y) coordinate from the 1280x720 baseline canvas back to
    the raw capture frame coordinate space.
    """
    info = get_macos_frame_crop_info(raw_h, raw_w)
    content_w = info["content_width"]
    content_h = info["content_height"]
    crop_top = info["crop_top"]

    scale_x = content_w / float(BASELINE_WIDTH)
    scale_y = content_h / float(BASELINE_HEIGHT)

    raw_x = int(round(norm_x * scale_x))
    raw_y = int(round(crop_top + norm_y * scale_y))

    return raw_x, raw_y
