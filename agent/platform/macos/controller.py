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


class MacOSAdaptedController(CustomController):
    """
    Adapter controller that wraps MacOSController, providing automatic
    1280x720 dynamic 16:9 normalization on every screencap frame.
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
        if self._last_raw_shape is not None:
            raw_h, raw_w = self._last_raw_shape
            rx, ry = map_normalized_to_raw_coordinates(x, y, raw_h, raw_w)
        else:
            rx, ry = x, y

        job = self._raw_controller.post_click(rx, ry)
        if hasattr(job, "wait"):
            job.wait()
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

    def click_key(self, keycode: int) -> bool:
        job = self._raw_controller.post_click_key(keycode)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def key_down(self, keycode: int) -> bool:
        job = self._raw_controller.post_key_down(keycode)
        if hasattr(job, "wait"):
            job.wait()
        return True

    def key_up(self, keycode: int) -> bool:
        job = self._raw_controller.post_key_up(keycode)
        if hasattr(job, "wait"):
            job.wait()
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
