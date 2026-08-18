# -*- coding: utf-8 -*-
"""
Unit Test Suite for macOS Frame Adapter & Dynamic 16:9 Title Bar Normalization.
"""

from __future__ import annotations

import platform
import sys
import unittest
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent"

for p in (str(PROJECT_ROOT), str(AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from agent.platform.macos.frame_adapter import (
    get_macos_frame_crop_info,
    normalize_macos_game_frame,
    map_normalized_to_raw_coordinates,
    BASELINE_WIDTH,
    BASELINE_HEIGHT,
)


class TestMacOSFrameAdapter(unittest.TestCase):

    def test_standard_mac_window_626x384(self):
        """Test with verified Mac mini 626x384 window frame."""
        info = get_macos_frame_crop_info(384, 626)
        self.assertEqual(info["raw_width"], 626)
        self.assertEqual(info["raw_height"], 384)
        self.assertEqual(info["target_16_9_height"], 352)
        self.assertEqual(info["crop_top"], 32)
        self.assertEqual(info["content_width"], 626)
        self.assertEqual(info["content_height"], 352)

        # Synthetic 626x384 frame
        frame = np.ones((384, 626, 3), dtype=np.uint8) * 128
        norm = normalize_macos_game_frame(frame)
        self.assertEqual(norm.shape, (720, 1280, 3))

    def test_retina_2x_window_1252x768(self):
        """Test with verified 2x Retina 1252x768 frame."""
        info = get_macos_frame_crop_info(768, 1252)
        self.assertEqual(info["target_16_9_height"], 704)
        self.assertEqual(info["crop_top"], 64)

        frame = np.ones((768, 1252, 3), dtype=np.uint8) * 200
        norm = normalize_macos_game_frame(frame)
        self.assertEqual(norm.shape, (720, 1280, 3))

    def test_non_integer_round_819x493(self):
        """Test with non-integer 819x493 aspect ratio."""
        # 819 * 9 / 16 = 460.6875 -> round = 461
        info = get_macos_frame_crop_info(493, 819)
        self.assertEqual(info["target_16_9_height"], 461)
        self.assertEqual(info["crop_top"], 32)

        frame = np.ones((493, 819, 3), dtype=np.uint8)
        norm = normalize_macos_game_frame(frame)
        self.assertEqual(norm.shape, (720, 1280, 3))

    def test_pure_16_9_1280x720(self):
        """Test with pure 16:9 frame where crop_top is 0."""
        info = get_macos_frame_crop_info(720, 1280)
        self.assertEqual(info["crop_top"], 0)
        self.assertEqual(info["target_16_9_height"], 720)

        frame = np.ones((720, 1280, 3), dtype=np.uint8)
        norm = normalize_macos_game_frame(frame)
        self.assertEqual(norm.shape, (720, 1280, 3))

    def test_coordinate_mapping(self):
        """Test mapping normalized 1280x720 coordinates back to raw frame."""
        # 626x384 frame with crop_top=32, content=(352, 626)
        rx0, ry0 = map_normalized_to_raw_coordinates(0, 0, 384, 626)
        self.assertEqual(rx0, 0)
        self.assertEqual(ry0, 32)  # Top-left of game content starts at y=32

        rx_max, ry_max = map_normalized_to_raw_coordinates(1280, 720, 384, 626)
        self.assertEqual(rx_max, 626)
        self.assertEqual(ry_max, 384)

    def test_invalid_and_error_inputs(self):
        """Test defensive error handling for invalid or incompatible frames."""
        with self.assertRaises(ValueError):
            normalize_macos_game_frame(None)

        with self.assertRaises(ValueError):
            normalize_macos_game_frame(np.array([]))

        # Frame wider than 16:9 (e.g. ultra-wide 1600x600 -> target_h=900 > raw_h=600)
        frame_ultra = np.ones((600, 1600, 3), dtype=np.uint8)
        with self.assertRaises(RuntimeError):
            normalize_macos_game_frame(frame_ultra)


def run_unit_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMacOSFrameAdapter)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_unit_tests())
