# -*- coding: utf-8 -*-
"""
MaaNTE macOS Adapted Controller.

Purpose:
Wraps the official MaaFramework MacOSController using CustomController,
automatically intercepting screencap requests to crop the macOS title bar
and normalize frames to the standard 1280x720 16:9 canvas required by Tasker.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple
import numpy as np

import maa
from maa.controller import Controller, MacOSController, CustomController
from maa.define import MaaMacOSScreencapMethodEnum, MaaMacOSInputMethodEnum

from .frame_adapter import normalize_macos_game_frame, map_normalized_to_raw_coordinates

_logger = logging.getLogger("MaaNTE.MacOSAdapter")


import time
import ctypes
import sys

# ---------------------------------------------------------------------------
# Windows VK Code -> macOS CGKeyCode Mapping
# ---------------------------------------------------------------------------
VK_TO_MACOS_KEYCODE: Dict[int, int] = {
    # Letters (A-Z)
    65: 0,   # A
    66: 11,  # B
    67: 8,   # C
    68: 2,   # D
    69: 14,  # E
    70: 3,   # F
    71: 5,   # G
    72: 4,   # H
    73: 34,  # I
    74: 38,  # J
    75: 40,  # K
    76: 37,  # L
    77: 46,  # M
    78: 45,  # N
    79: 31,  # O
    80: 35,  # P
    81: 12,  # Q
    82: 15,  # R
    83: 1,   # S
    84: 17,  # T
    85: 32,  # U
    86: 9,   # V
    87: 13,  # W
    88: 7,   # X
    89: 16,  # Y
    90: 6,   # Z

    # Numbers (0-9)
    48: 29, 49: 18, 50: 19, 51: 20, 52: 21,
    53: 23, 54: 22, 55: 26, 56: 28, 57: 25,

    # Controls & Navigation
    27: 53,   # ESC
    32: 49,   # SPACE
    13: 36,   # ENTER / RETURN
    9:  48,   # TAB
    8:  51,   # BACKSPACE / DELETE
    16: 56,   # SHIFT
    17: 59,   # CTRL
    18: 58,   # ALT / OPTION
    37: 123,  # LEFT
    38: 126,  # UP
    39: 124,  # RIGHT
    40: 125,  # DOWN

    # Function Keys
    112: 122, 113: 120, 114: 99,  115: 118,
    116: 96,  117: 97,  118: 98,  119: 100,
    120: 101, 121: 109, 122: 103, 123: 111,
}

_CGEventCreateKeyboardEvent = None
_CGEventPost = None
_CFRelease = None

if sys.platform == "darwin":
    try:
        _app_services = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        _CGEventCreateKeyboardEvent = _app_services.CGEventCreateKeyboardEvent
        _CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        _CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]

        _CGEventPost = _app_services.CGEventPost
        _CGEventPost.restype = None
        _CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

        _CFRelease = _app_services.CFRelease
        _CFRelease.restype = None
        _CFRelease.argtypes = [ctypes.c_void_p]
    except Exception as e:
        _logger.warning("Could not load CoreGraphics for native key fallback: %s", e)


def _post_native_macos_key(mkey: int, down: bool):
    """Post hardware key event directly via CoreGraphics as fallback."""
    if _CGEventCreateKeyboardEvent and _CGEventPost and _CFRelease:
        try:
            evt = _CGEventCreateKeyboardEvent(None, int(mkey), bool(down))
            if evt:
                _CGEventPost(0, evt)  # kCGHIDEventTap = 0
                _CFRelease(evt)
        except Exception:
            pass


class MacOSAdaptedController(CustomController):
    """
    Adapter controller that wraps MacOSController, providing automatic
    1280x720 dynamic 16:9 normalization on every screencap frame and
    human-like mouse click & keyboard VK mapping on macOS.
    """

    def __init__(
        self,
        window_id: int,
        screencap_method: int = MaaMacOSScreencapMethodEnum.ScreenCaptureKit,
        input_method: int = MaaMacOSInputMethodEnum.GlobalEvent,
    ):
        super().__init__()
        self._window_id = window_id
        self._screencap_method = screencap_method
        self._input_method = input_method

        self._raw_controller = MacOSController(
            window_id,
            screencap_method=screencap_method,
            input_method=input_method,
        )
        self._raw_controller.set_screenshot_use_raw_size(True)
        self._last_raw_shape: Optional[Tuple[int, int]] = None

    @property
    def raw_controller(self) -> MacOSController:
        return self._raw_controller

    def connect(self) -> bool:
        job = self._raw_controller.post_connection()
        if hasattr(job, "wait"):
            job.wait()
        return self._raw_controller.connected

    def connected(self) -> bool:
        return self._raw_controller.connected

    def request_uuid(self) -> str:
        try:
            return self._raw_controller.uuid
        except Exception:
            return f"macos_window_{self._window_id}"

    def screencap(self) -> np.ndarray:
        cap_job = self._raw_controller.post_screencap()
        if hasattr(cap_job, "wait"):
            cap_job.wait()

        raw_frame = self._raw_controller.cached_image
        if raw_frame is None:
            raise RuntimeError("MacOSController.cached_image returned None.")

        self._last_raw_shape = raw_frame.shape[:2]
        normalized_frame = normalize_macos_game_frame(raw_frame)
        return normalized_frame

    def click(self, x: int, y: int) -> bool:
        """
        Click with precise timing:
        1. Move cursor to target position first
        2. Dwell briefly so game UI triggers hover state
        3. Press mouse down
        4. Hold momentarily (do NOT pull away immediately)
        5. Release mouse up
        """
        if self._last_raw_shape is not None:
            raw_h, raw_w = self._last_raw_shape
            rx, ry = map_normalized_to_raw_coordinates(x, y, raw_h, raw_w)
        else:
            rx, ry = x, y

        # 1. Move to coordinate first
        job = self._raw_controller.post_touch_move(rx, ry, 0, 1)
        if hasattr(job, "wait"):
            job.wait()
        time.sleep(0.04)

        # 2. Press down
        job = self._raw_controller.post_touch_down(rx, ry, 0, 1)
        if hasattr(job, "wait"):
            job.wait()

        # 3. Hold down for a moment
        time.sleep(0.08)

        # 4. Release up
        job = self._raw_controller.post_touch_up(0)
        if hasattr(job, "wait"):
            job.wait()
        time.sleep(0.02)
        return True

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        if self._last_raw_shape is not None:
            raw_h, raw_w = self._last_raw_shape
            rx1, ry1 = map_normalized_to_raw_coordinates(x1, y1, raw_h, raw_w)
            rx2, ry2 = map_normalized_to_raw_coordinates(x2, y2, raw_h, raw_w)
        else:
            rx1, ry1, rx2, ry2 = x1, y1, x2, y2

        job = self._raw_controller.post_swipe(rx1, ry1, rx2, ry2, duration)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def touch_down(self, contact: int, x: int, y: int, pressure: int) -> bool:
        if self._last_raw_shape is not None:
            raw_h, raw_w = self._last_raw_shape
            rx, ry = map_normalized_to_raw_coordinates(x, y, raw_h, raw_w)
        else:
            rx, ry = x, y
        job = self._raw_controller.post_touch_down(rx, ry, contact, pressure)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def touch_move(self, contact: int, x: int, y: int, pressure: int) -> bool:
        if self._last_raw_shape is not None:
            raw_h, raw_w = self._last_raw_shape
            rx, ry = map_normalized_to_raw_coordinates(x, y, raw_h, raw_w)
        else:
            rx, ry = x, y
        job = self._raw_controller.post_touch_move(rx, ry, contact, pressure)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def touch_up(self, contact: int) -> bool:
        job = self._raw_controller.post_touch_up(contact)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def _to_macos_key(self, keycode: int) -> int:
        return VK_TO_MACOS_KEYCODE.get(keycode, keycode)

    def click_key(self, keycode: int) -> bool:
        mkey = self._to_macos_key(keycode)
        job = self._raw_controller.post_key_down(mkey)
        if hasattr(job, "wait"):
            job.wait()
        _post_native_macos_key(mkey, True)
        time.sleep(0.06)
        job = self._raw_controller.post_key_up(mkey)
        if hasattr(job, "wait"):
            job.wait()
        _post_native_macos_key(mkey, False)
        return True

    def key_down(self, keycode: int) -> bool:
        mkey = self._to_macos_key(keycode)
        job = self._raw_controller.post_key_down(mkey)
        if hasattr(job, "wait"):
            job.wait()
        _post_native_macos_key(mkey, True)
        return True

    def key_up(self, keycode: int) -> bool:
        mkey = self._to_macos_key(keycode)
        job = self._raw_controller.post_key_up(mkey)
        if hasattr(job, "wait"):
            job.wait()
        _post_native_macos_key(mkey, False)
        return True

    def input_text(self, text: str) -> bool:
        job = self._raw_controller.post_input_text(text)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def start_app(self, intent: str) -> bool:
        job = self._raw_controller.post_start_app(intent)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def stop_app(self, intent: str) -> bool:
        job = self._raw_controller.post_stop_app(intent)
        if hasattr(job, "wait"):
            job.wait()
        return True
