# -*- coding: utf-8 -*-
"""Comprehensive unit, regression, OpenCV template, Win32 struct, and headless UI tests for Pirate Token Farm."""

import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import cv2
import mss
import numpy as np

os.environ["PIRATE_HEADLESS"] = "1"
ROOT = Path(__file__).resolve().parent.parent
ART = Path(tempfile.gettempdir()) / "pirate_token_farm_test_art"
ART.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

import tkinter as tk
import fortnite_farm as ff


class TestWin32AndInputSafety(unittest.TestCase):
    def test_input_struct_size_and_ctypes_prototypes(self):
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(ff.INPUT), expected)
        self.assertIsNotNone(ff.user32.GetForegroundWindow.restype)
        self.assertIsNotNone(ff.user32.IsIconic.argtypes)
        self.assertEqual(ff.user32.SendInput.restype, ctypes.wintypes.UINT)

    def test_extended_key_flag_on_arrows_and_scan_code_on_wasd(self):
        sent_inputs = []

        def fake_send(count, p_inputs, cb_size):
            inp = ctypes.cast(p_inputs, ctypes.POINTER(ff.INPUT)).contents
            sent_inputs.append((inp.type, inp.ii.ki.wScan, inp.ii.ki.dwFlags))
            return 1

        with patch.object(ff.user32, "SendInput", side_effect=fake_send):
            ff.send_key_hw("w", True)
            ff.send_key_hw("right", True)
            ff.send_key_hw("right", False)

        self.assertEqual(len(sent_inputs), 3)
        self.assertEqual(sent_inputs[0][1], 0x11)
        self.assertEqual(sent_inputs[0][2] & ff.KEYEVENTF_EXTENDEDKEY, 0)
        self.assertTrue(sent_inputs[1][2] & ff.KEYEVENTF_EXTENDEDKEY)
        self.assertTrue(sent_inputs[2][2] & ff.KEYEVENTF_EXTENDEDKEY)
        self.assertTrue(sent_inputs[2][2] & ff.KEYEVENTF_KEYUP)

    def test_send_mouse_button_left_and_right_flags(self):
        mouse_flags = []

        def fake_send(count, p_inputs, cb_size):
            inp = ctypes.cast(p_inputs, ctypes.POINTER(ff.INPUT)).contents
            mouse_flags.append((inp.type, inp.ii.mi.dwFlags))
            return 1

        with patch.object(ff.user32, "SendInput", side_effect=fake_send):
            ff.send_mouse_button(True)
            ff.send_mouse_button(False, "left")
            ff.send_mouse_button(True, "right")
            ff.send_mouse_button(False, "right")

        self.assertEqual(mouse_flags, [
            (ff.INPUT_MOUSE, ff.MOUSEEVENTF_LEFTDOWN),
            (ff.INPUT_MOUSE, ff.MOUSEEVENTF_LEFTUP),
            (ff.INPUT_MOUSE, ff.MOUSEEVENTF_RIGHTDOWN),
            (ff.INPUT_MOUSE, ff.MOUSEEVENTF_RIGHTUP),
        ])

    def test_active_fortnite_hwnd_excludes_self_and_minimized(self):
        with patch.object(ff.user32, "GetForegroundWindow", return_value=12345), \
             patch.object(ff.user32, "IsIconic", return_value=0), \
             patch.object(ff.user32, "GetWindowTextLengthW", return_value=17), \
             patch.object(ff.user32, "GetWindowTextW", side_effect=lambda h, b, n: setattr(b, "value", "Pirate Token Farm") or 17):
            self.assertIsNone(ff.active_fortnite_hwnd(allow_any_window=False))
            self.assertIsNone(ff.active_fortnite_hwnd(allow_any_window=True))

        with patch.object(ff.user32, "GetForegroundWindow", return_value=12345), \
             patch.object(ff.user32, "IsIconic", return_value=1):
            self.assertIsNone(ff.active_fortnite_hwnd(allow_any_window=False))

        with patch.object(ff.user32, "GetForegroundWindow", return_value=55555), \
             patch.object(ff.user32, "IsIconic", return_value=0), \
             patch.object(ff.user32, "GetWindowTextLengthW", return_value=8), \
             patch.object(ff.user32, "GetWindowTextW", side_effect=lambda h, b, n: setattr(b, "value", "Fortnite") or 8):
            self.assertEqual(ff.active_fortnite_hwnd(allow_any_window=False), 55555)


class TestMatcherTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = ff.Matcher()

    def test_all_five_templates_loaded_and_match_exact_crops(self):
        self.assertEqual(set(self.matcher.data.keys()), {"play_again", "play_button", "menu_button", "return_lobby", "connecting"})
        for name in ("play_again", "play_button", "menu_button", "return_lobby", "connecting"):
            tpl = cv2.imdecode(np.fromfile(str(ff.TEMPLATES / f"{name}.png"), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            canvas = np.full((tpl.shape[0] + 120, tpl.shape[1] + 160), 32, dtype=np.uint8)
            canvas[60:60 + tpl.shape[0], 80:80 + tpl.shape[1]] = tpl
            score, box = self.matcher.find(canvas, name)
            self.assertIsNotNone(box, f"{name} failed to match own template")
            self.assertGreaterEqual(score, 0.88, f"{name} score too low: {score}")

    def test_connecting_halo_rejects_flat_screens_and_accepts_seasonal_backgrounds(self):
        tpl = cv2.imdecode(np.fromfile(str(ff.TEMPLATES / "connecting.png"), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        fg = tpl > 195
        h, w = tpl.shape

        for flat_val in (0, 128, 255):
            flat = np.full((h + 120, w + 160), flat_val, dtype=np.uint8)
            score, box = self.matcher.find(flat, "connecting")
            self.assertIsNone(box, f"False positive on flat={flat_val} (score={score})")
            self.assertLess(score, 0.25)

        for bg_mode in ("dark", "blue_tint", "noisy"):
            canvas = np.full((h + 120, w + 160), 18 if bg_mode == "dark" else 95, dtype=np.uint8)
            if bg_mode == "noisy":
                rng = np.random.default_rng(7)
                canvas = rng.integers(35, 110, size=canvas.shape, dtype=np.uint8)
            patch_roi = canvas[60:60 + h, 80:80 + w]
            patch_roi[fg] = tpl[fg]
            score, box = self.matcher.find(canvas, "connecting")
            self.assertIsNotNone(box, f"Missed connecting badge on {bg_mode} (score={score})")
            self.assertGreaterEqual(score, 0.90)


class TestAppAndUI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cfg_path = ff.CONFIG
        self.tmp_cfg = Path(self.tmpdir.name) / "settings.json"
        ff.CONFIG = self.tmp_cfg
        self.root = tk.Tk()
        self.app = ff.App(self.root)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        ff.CONFIG = self.orig_cfg_path
        self.tmpdir.cleanup()

    def test_legacy_no_method_migration_and_atomic_save(self):
        self.tmp_cfg.write_text(json.dumps({"no_method": True, "method": 2, "min": 5, "max": 9, "turn_px": 3100}), encoding="utf-8")
        self.app._load()
        self.assertEqual(self.app.live("method"), 0)
        self.assertEqual(self.app.live("min"), 5)
        self.assertEqual(self.app.live("max"), 9)
        self.assertEqual(self.app.live("turn_px"), 3100)

        self.app.set_cfg("turn_px", 2600)
        self.app.save()
        self.assertTrue(self.tmp_cfg.exists())
        self.assertFalse(self.tmp_cfg.with_suffix(".tmp").exists())
        loaded = json.loads(self.tmp_cfg.read_text(encoding="utf-8"))
        self.assertEqual(loaded["turn_px"], 2600)

    def test_undo_clear_on_flip_and_bump_turn_and_reset_undo(self):
        self.app.set_cfg("min", 13)
        self.app.set_cfg("max", 14)
        self.app.set_cfg("turn_px", 2400)
        self.app.reset_all()
        self.assertIsNotNone(self.app.undo_snap)
        self.assertEqual(self.app.live("min"), ff.DEFAULTS["min"])
        self.app.undo_reset()
        self.assertIsNone(self.app.undo_snap)
        self.assertEqual(self.app.live("min"), 13)
        self.assertEqual(self.app.live("turn_px"), 2400)

        # Undo cleared on flip("safe") & bump_turn() triggers clean rebuild
        self.app.reset_all()
        self.assertIsNotNone(self.app.undo_snap)
        self.app.flip("safe")
        self.assertIsNone(self.app.undo_snap)
        self.app.reset_all()
        self.app.bump_turn(100)
        self.assertIsNone(self.app.undo_snap)
        self.assertEqual(self.app.live("turn_px"), ff.DEFAULTS["turn_px"] + 100)

    def test_layout_independent_hotkey_capture_cyrillic_and_reserved(self):
        self.app.begin_capture("start")
        # Cyrillic_el ('л') on VK 0x4B ('K') -> must resolve to 'k', NOT 'cyrillic_el'
        ev_ru_k = types.SimpleNamespace(keysym="Cyrillic_el", keycode=0x4B, char="")
        self.app.on_key(ev_ru_k)
        self.assertIsNone(self.app.capturing)
        self.assertEqual(self.app.live("start_key"), "k")

        # Reserved physical key under Cyrillic layout ('Cyrillic_ef' on VK 0x41 = 'A') -> rejected cleanly
        self.app.begin_capture("start")
        ev_ru_a = types.SimpleNamespace(keysym="Cyrillic_ef", keycode=0x41, char="")
        self.app.on_key(ev_ru_a)
        self.assertIsNone(self.app.capturing)
        self.assertEqual(self.app.live("start_key"), "k")

        # Reserved key ('w') -> rejected cleanly
        self.app.begin_capture("start")
        ev_w = types.SimpleNamespace(keysym="w", keycode=0x57, char="w")
        self.app.on_key(ev_w)
        self.assertIsNone(self.app.capturing)
        self.assertEqual(self.app.live("start_key"), "k")

        # Escape cancels without overwriting
        self.app.begin_capture("start")
        ev_esc = types.SimpleNamespace(keysym="Escape", keycode=0x1B, char="")
        self.app.on_key(ev_esc)
        self.assertIsNone(self.app.capturing)
        self.assertEqual(self.app.live("start_key"), "k")

    def test_render_expanded_undo_running_and_en_previews(self):
        # 1. Clean default RU main screen preview
        self.app.set_lang("ru")
        self.app.set_cfg("method", 1)
        self.app.set_cfg("min", 13)
        self.app.set_cfg("max", 14)
        self.app.set_cfg("safe", True)
        self.app.set_cfg("immediate", True)
        self.app.set_cfg("human", True)
        self.app.set_cfg("space", True)
        self.app.params_open = False
        self.app.running = False
        self.app.state = "ready"
        self.app.undo_snap = None
        self.app.detail_ref = {"key": "dt_idle"}
        self.app.page = "main"
        self.app.rebuild_ui(snap=True)
        img_main = self.app.render_headless_preview()
        self.assertIsNotNone(img_main)
        out_main = ART / "pirate_app_main.png"
        img_main.save(out_main)
        self.assertTrue(out_main.exists())

        # 2. Settings screen (RU)
        self.app.page = "settings"
        self.app.rebuild_ui(snap=True)
        img_set = self.app.render_headless_preview()
        self.assertIsNotNone(img_set)
        out_set = ART / "pirate_app_set.png"
        img_set.save(out_set)
        self.assertTrue(out_set.exists())

        # 3. Expanded parameters + Undo + Running preview
        self.app.page = "main"
        self.app.set_cfg("method", 2)
        self.app.params_open = True
        self.app.reset_all()  # shows Undo banner
        self.app.state = "running"
        self.app.running = True
        self.app.detail_ref = {"key": "dt_waiting", "m": 11}
        self.app.rebuild_ui(snap=True)
        img_exp = self.app.render_headless_preview()
        self.assertIsNotNone(img_exp)
        out_exp = ART / "pirate_app_expanded_running.png"
        img_exp.save(out_exp)
        self.assertTrue(out_exp.exists())

        # 4. English main screen preview
        self.app.running = False
        self.app.state = "ready"
        self.app.undo_snap = None
        self.app.params_open = False
        self.app.detail_ref = {"key": "dt_idle"}
        self.app.set_lang("en")
        img_en = self.app.render_headless_preview()
        self.assertIsNotNone(img_en)
        out_en = ART / "pirate_app_en.png"
        img_en.save(out_en)
        self.assertTrue(out_en.exists())

    def test_localization_parity_and_placeholders(self):
        ru_keys = set(ff.TEXT["ru"].keys())
        en_keys = set(ff.TEXT["en"].keys())
        self.assertEqual(ru_keys, en_keys)
        for k in ru_keys:
            ru_val = ff.TEXT["ru"][k]
            en_val = ff.TEXT["en"][k]
            self.assertTrue(ru_val and en_val, f"Empty string for key {k}")
            if "{m}" in ru_val or "{m}" in en_val:
                self.assertEqual(ru_val.format(m=5)[:0], "")
                self.assertEqual(en_val.format(m=5)[:0], "")
            if "{keys}" in ru_val or "{keys}" in en_val:
                self.assertEqual(ru_val.format(keys="W+A")[:0], "")
                self.assertEqual(en_val.format(keys="W+A")[:0], "")


class TestEngineConcurrencyAndMechanics(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cfg = ff.CONFIG
        ff.CONFIG = Path(self.tmpdir.name) / "settings.json"
        self.root = tk.Tk()
        self.app = ff.App(self.root)
        self.cap = types.SimpleNamespace(
            monitors=[
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ],
            grab=lambda r: (_ for _ in ()).throw(mss.ScreenShotError("boom")),
        )
        self.engine = ff.Engine(self.app, self.cap)

    def tearDown(self):
        self.engine.stop.set()
        self.engine.release_all()
        try:
            self.root.destroy()
        except Exception:
            pass
        ff.CONFIG = self.orig_cfg
        self.tmpdir.cleanup()

    def test_frame_handles_mss_screenshot_error_gracefully(self):
        with patch.object(ff, "active_fortnite_hwnd", return_value=None):
            self.assertIsNone(self.engine.frame())

    def test_click_refuses_background_window_and_uses_monitor_coords(self):
        tpl = cv2.imdecode(np.fromfile(str(ff.TEMPLATES / "play_button.png"), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        gray = np.full((600, 800), 25, dtype=np.uint8)
        gray[100:100 + tpl.shape[0], 200:200 + tpl.shape[1]] = tpl

        with patch.object(self.engine, "is_target_focused", return_value=False), \
             patch.object(ff, "click_screen_pos") as m_click:
            ok = self.engine.click("play_button", "Play", timeout=0.25)
            self.assertFalse(ok)
            m_click.assert_not_called()

        self.engine.monitor = {"left": -1920, "top": 0, "width": 1920, "height": 1080}
        with patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "frame", return_value=gray), \
             patch.object(ff, "click_screen_pos") as m_click, \
             patch.object(time, "sleep"):
            ok = self.engine.click("play_button", "Play", timeout=1.0)
            self.assertTrue(ok)
            m_click.assert_called_once()
            cx, cy = m_click.call_args[0]
            self.assertEqual(cx, -1920 + 200 + tpl.shape[1] // 2)
            self.assertEqual(cy, 0 + 100 + tpl.shape[0] // 2)

    def test_release_all_releases_all_movement_and_mouse_keys(self):
        released = []
        with patch.object(ff, "send_key_hw", side_effect=lambda k, d: released.append((k, d))), \
             patch.object(ff, "send_mouse_button", side_effect=lambda d, b="left": released.append((f"mb_{b}", d))):
            self.engine.key_down("w")
            self.engine.key_down("shift")
            self.engine.key_down("space")
            self.engine.key_down("ctrl")
            self.engine.mouse_hold_set(True)
            self.engine.rmb_hold_set(True)
            released.clear()
            self.engine.release_all()

        released_keys = {k for k, d in released if d is False}
        self.assertTrue({"w", "shift", "space", "ctrl", "mb_left", "mb_right"}.issubset(released_keys))
        self.assertEqual(len(self.engine.held_keys), 0)
        self.assertFalse(self.engine.mouse_down)
        self.assertFalse(self.engine.rmb_down)
        self.assertFalse(self.engine.w_down)

    def test_pickaxe_swing_restores_shift_sprint(self):
        events = []
        with patch.object(ff, "send_key_hw", side_effect=lambda k, d: events.append((k, d))), \
             patch.object(ff, "send_mouse_button", side_effect=lambda d, b="left": events.append((f"mb_{b}", d))), \
             patch.object(ff, "send_mouse_rel"), \
             patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "anti_sleep", return_value=True):
            self.app.set_cfg("mouse", False)
            self.engine.w_down = True
            self.engine.key_down("shift")
            events.clear()
            self.engine.do_pickaxe_swing()

        self.assertIn(("shift", False), events)
        self.assertIn(("shift", True), events)
        self.assertEqual(events[-1], ("shift", True))
        self.assertIn("shift", self.engine.held_keys)

    def test_slide_burst_and_slide_hop_cleanup(self):
        events = []
        with patch.object(ff, "send_key_hw", side_effect=lambda k, d: events.append((k, d))), \
             patch.object(ff, "send_mouse_rel"), \
             patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "anti_sleep", return_value=True), \
             patch.object(time, "sleep"):
            events.clear()
            # Force allow_jump=False -> never sends space, balances ctrl toggle
            self.engine.do_slide_burst(allow_jump=False)
            ctrl_downs = [e for e in events if e == ("ctrl", True)]
            space_downs = [e for e in events if e == ("space", True)]
            self.assertEqual(len(ctrl_downs) % 2, 0, f"Expected even ctrl toggles when no jump: {events}")
            self.assertEqual(len(space_downs), 0)
            self.assertEqual(len(self.engine.held_keys), 0)

            events.clear()
            # Force slide-hop path via low random draw
            with patch.object(ff.random, "random", return_value=0.10):
                self.engine.do_slide_burst(allow_jump=True)
            self.assertIn(("w", True), events)
            self.assertIn(("shift", True), events)
            self.assertIn(("ctrl", True), events)
            self.assertIn(("space", True), events)
            self.assertEqual(len(self.engine.held_keys), 0)
            self.assertFalse(self.engine.w_down)

    def test_combat_wiggle_alternates_sides_and_releases_keys(self):
        events = []
        mouse_moves = []
        with patch.object(ff, "send_key_hw", side_effect=lambda k, d: events.append((k, d))), \
             patch.object(ff, "send_mouse_rel", side_effect=lambda dx, dy: mouse_moves.append((dx, dy))), \
             patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "anti_sleep", return_value=True):
            ok = self.engine.do_combat_wiggle()

        self.assertTrue(ok)
        pressed = {k for k, d in events if d is True}
        self.assertTrue("a" in pressed and "d" in pressed, f"Expected both A and D in wiggle: {events}")
        self.assertEqual(len(self.engine.held_keys), 0)

    def test_crouch_peek_balances_ctrl_toggle_in_both_modes(self):
        for strafe_flag in (True, False):
            events = []
            with patch.object(ff, "send_key_hw", side_effect=lambda k, d: events.append((k, d))), \
                 patch.object(ff, "send_mouse_rel"), \
                 patch.object(ff.random, "random", return_value=0.10), \
                 patch.object(self.engine, "is_target_focused", return_value=True), \
                 patch.object(self.engine, "anti_sleep", return_value=True), \
                 patch.object(time, "sleep"):
                self.engine.do_crouch_peek(allow_strafe=strafe_flag)
            ctrl_presses = [e for e in events if e == ("ctrl", True)]
            self.assertGreaterEqual(len(ctrl_presses), 2)
            self.assertEqual(len(ctrl_presses) % 2, 0, f"Unbalanced crouch toggle ({strafe_flag}): {events}")
            self.assertEqual(len(self.engine.held_keys), 0)

    def test_rmb_peek_and_jump_swing_safety_and_locks(self):
        mb_events = []
        key_events = []
        with patch.object(ff, "send_mouse_button", side_effect=lambda d, b="left": mb_events.append((b, d))), \
             patch.object(ff, "send_key_hw", side_effect=lambda k, d: key_events.append((k, d))), \
             patch.object(ff, "send_mouse_rel"), \
             patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "anti_sleep", return_value=True), \
             patch.object(time, "sleep"):
            self.app.set_cfg("mouse", False)
            self.engine.do_rmb_peek()
            self.assertEqual(mb_events[0], ("right", True))
            self.assertEqual(mb_events[-1], ("right", False))
            self.assertFalse(self.engine.rmb_down)

            # Must skip RMB peek when holding LMB for farming
            mb_events.clear()
            self.engine.mouse_down = True
            self.engine.do_rmb_peek()
            self.assertEqual(mb_events, [])
            self.engine.mouse_down = False

            # Jump-swing presses Space + LMB and releases cleanly
            mb_events.clear()
            key_events.clear()
            self.engine.do_jump_swing()
            self.assertIn(("space", True), key_events)
            self.assertIn(("space", False), key_events)
            self.assertIn(("left", True), mb_events)
            self.assertIn(("left", False), mb_events)
            self.assertFalse(self.engine.mouse_down)
            self.assertEqual(len(self.engine.held_keys), 0)

    def test_anti_loop_aborts_maneuvers_cleanly_on_stop(self):
        self.app.set_cfg("method", 0)
        self.app.set_cfg("immediate", True)
        self.app.set_cfg("human", True)
        self.app.set_cfg("walk", False)
        self.app.set_cfg("space", True)
        self.app.set_cfg("swing", True)
        self.app.set_cfg("mouse", False)

        now = time.monotonic()
        self.engine.next_slide = now - 0.1  # force slide right on start

        with patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(ff, "send_key_hw"), \
             patch.object(ff, "send_mouse_button"), \
             patch.object(ff, "send_mouse_rel"):
            t = threading.Thread(target=self.engine.anti_loop)
            t.start()
            time.sleep(0.18)
            self.engine.stop.set()
            t.join(timeout=1.5)
            self.assertFalse(t.is_alive())

        self.assertEqual(len(self.engine.held_keys), 0)
        self.assertFalse(self.engine.mouse_down)
        self.assertFalse(self.engine.rmb_down)
        self.assertFalse(self.engine.w_down)

    def test_human_look_clamps_pitch_accumulation(self):
        with patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(ff, "send_mouse_rel"), \
             patch.object(self.engine, "anti_sleep", return_value=True), \
             patch.object(time, "sleep"):
            for _ in range(120):
                self.engine.human_look()
        self.assertLessEqual(abs(self.engine.pitch_acc), 350)

    def test_engine_run_cleans_up_anti_thread_without_zombies(self):
        with patch.object(self.engine, "anti_loop", side_effect=lambda: self.engine.stop.wait(1.0)):
            t = threading.Thread(target=self.engine.run, args=(0,))
            t.start()
            time.sleep(0.15)
            self.engine.stop.set()
            t.join(timeout=3.0)
            self.assertFalse(t.is_alive())
            if self.engine.anti_thread is not None:
                self.assertFalse(self.engine.anti_thread.is_alive())

    def test_casual_player_strafes_with_walk_disabled(self):
        # User's saved config has human=True and walk=False: Casual Player must still strafe WASD
        self.app.set_cfg("method", 0)
        self.app.set_cfg("immediate", True)
        self.app.set_cfg("human", True)
        self.app.set_cfg("walk", False)
        self.app.set_cfg("space", False)
        self.app.set_cfg("swing", False)
        self.app.set_cfg("mouse", False)

        key_events = []

        class FakeMSS:
            monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def grab(self, r): return np.zeros((1080, 1920, 4), dtype=np.uint8)

        with patch.object(ff.mss, "MSS", return_value=FakeMSS()), \
             patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "_pick_human_move", return_value=("w+d", {"w", "d"}, 0.25)), \
             patch.object(ff, "send_key_hw", side_effect=lambda k, d: key_events.append((k, d))), \
             patch.object(ff, "send_mouse_rel"):
            t = threading.Thread(target=self.engine.anti_loop)
            t.start()
            time.sleep(0.25)
            self.engine.stop.set()
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive())

        pressed = {k for k, d in key_events if d is True}
        self.assertTrue({"w", "d"}.issubset(pressed), f"Expected W+D strafe, got {key_events}")
        released = {k for k, d in key_events if d is False}
        self.assertTrue({"w", "d"}.issubset(released))

    def test_start_clears_undo_and_worker_releases_engine(self):
        self.app.set_cfg("method", 0)
        self.app.set_cfg("human", True)
        self.app.reset_all()
        self.assertIsNotNone(self.app.undo_snap)
        self.app.emit("detail", "stale_detail")

        with patch.object(ff.Engine, "run", side_effect=lambda m: time.sleep(0.05)):
            self.app.start()
            self.assertIsNone(self.app.undo_snap)
            self.app.worker.join(timeout=3.0)
            self.assertFalse(self.app.worker.is_alive())
            self.assertIsNone(self.app.engine)
            self.app.poll()
            self.assertFalse(self.app.running)
            self.assertEqual(self.app.state, "ready")

    def test_set_move_keys_releases_unwanted_keys_even_when_busy_or_unfocused(self):
        events = []
        with patch.object(ff, "send_key_hw", side_effect=lambda k, d: events.append((k, d))):
            self.engine.key_down("w")
            self.engine.key_down("shift")
            events.clear()
            self.engine.busy.set()
            with patch.object(self.engine, "is_target_focused", return_value=False):
                self.engine.set_move_keys({"a"})
            self.engine.busy.clear()

        self.assertIn(("w", False), events)
        self.assertIn(("shift", False), events)
        self.assertNotIn(("a", True), events)
        self.assertEqual(len(self.engine.held_keys), 0)

    def test_idle_micro_fidget_emits_detail_without_log_spam(self):
        emitted = []
        with patch.object(self.app, "emit", side_effect=lambda kind, payload: emitted.append((kind, payload))), \
             patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "smooth_mouse_move", return_value=True) as m_move:
            self.engine.idle_micro_fidget()

        m_move.assert_called_once()
        self.assertIn(("detail", {"key": "dt_idle_look"}), emitted)
        self.assertFalse(any(kind == "log" for kind, _ in emitted))

    def test_method0_bypasses_opencv_and_frame_capture(self):
        self.app.set_cfg("method", 0)
        self.app.set_cfg("immediate", True)
        self.app.set_cfg("human", True)
        with patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "frame") as m_frame, \
             patch.object(self.engine.matcher, "find") as m_find, \
             patch.object(ff, "send_key_hw"), \
             patch.object(ff, "send_mouse_button"), \
             patch.object(ff, "send_mouse_rel"):
            t = threading.Thread(target=self.engine.anti_loop)
            t.start()
            time.sleep(0.22)
            self.engine.stop.set()
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive())

        m_frame.assert_not_called()
        m_find.assert_not_called()

    def test_stand_pause_suppresses_slide_and_wiggle_and_keeps_crouch_stationary(self):
        self.app.set_cfg("method", 0)
        self.app.set_cfg("immediate", True)
        self.app.set_cfg("human", True)
        self.app.set_cfg("walk", True)
        self.app.set_cfg("stand", True)
        self.app.set_cfg("space", False)
        self.app.set_cfg("swing", False)
        self.app.set_cfg("mouse", False)

        # Force immediate transition into stand after 1 walk step, and trigger slide/wiggle/crouch checks
        crouch_calls = []

        def fake_crouch(allow_strafe=True):
            crouch_calls.append(allow_strafe)
            self.engine.stop.set()
            return False

        now = time.monotonic()
        self.engine.next_slide = now + 0.05
        self.engine.next_wiggle = now + 0.05
        self.engine.next_crouch = now + 0.20

        with patch.object(self.engine, "is_target_focused", return_value=True), \
             patch.object(self.engine, "do_slide_burst") as m_slide, \
             patch.object(self.engine, "do_combat_wiggle") as m_wiggle, \
             patch.object(self.engine, "do_crouch_peek", side_effect=fake_crouch), \
             patch.object(self.engine, "_pick_human_move", return_value=("w", {"w"}, 0.02)), \
             patch.object(ff.random, "randint", return_value=1), \
             patch.object(ff, "send_key_hw"), \
             patch.object(ff, "send_mouse_rel"):
            # Pre-seed stand entry cleanly by letting slide/wiggle become due only after stand enters
            self.engine.next_slide = now + 0.18
            self.engine.next_wiggle = now + 0.18
            t = threading.Thread(target=self.engine.anti_loop)
            t.start()
            t.join(timeout=2.5)
            self.assertFalse(t.is_alive())

        m_slide.assert_not_called()
        m_wiggle.assert_not_called()
        self.assertEqual(crouch_calls, [False])

    def test_assets_fonts_and_templates_dirs_exist_and_icon_valid(self):
        self.assertTrue(ff.TEMPLATES.is_dir())
        self.assertTrue(ff.ASSETS.is_dir())
        self.assertTrue(ff.FONTS_DIR.is_dir())
        self.assertTrue((ff.ASSETS / "icon.ico").is_file())
        self.assertTrue((ff.ASSETS / "icon.png").is_file())
        self.assertGreater((ff.ASSETS / "icon.ico").stat().st_size, 10000)

    def test_rhythm_delay_bands_and_human_move_non_repetition(self):
        with patch.object(ff.random, "random", return_value=0.05):
            d_burst = self.engine._next_rhythm_delay(10.0, 20.0)
            self.assertTrue(3.5 <= d_burst <= 7.0)
        with patch.object(ff.random, "random", return_value=0.50):
            d_norm = self.engine._next_rhythm_delay(10.0, 20.0)
            self.assertTrue(10.0 <= d_norm <= 20.0)
        with patch.object(ff.random, "random", return_value=0.95):
            d_relax = self.engine._next_rhythm_delay(10.0, 20.0)
            self.assertTrue(22.0 <= d_relax <= 29.6)

        valid_keys = {"w", "a", "s", "d", "shift"}
        seen_tags = set()
        prev = ""
        for _ in range(180):
            tag, keys, dur = self.engine._pick_human_move(prev)
            self.assertNotEqual(tag, prev)
            self.assertTrue(keys.issubset(valid_keys))
            self.assertGreater(dur, 0.2)
            seen_tags.add(tag)
            prev = tag
        self.assertIn("w+a+shift", seen_tags)
        self.assertIn("w+d+shift", seen_tags)


if __name__ == "__main__":
    unittest.main(verbosity=2)
