# -*- coding: utf-8 -*-
"""
Pirate Token Farm - Fortnite Game Loop and Anti-AFK Tool
Obsidian layered Canvas renderer (0% idle CPU) + DirectInput engine.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import queue
import random
import sys
import threading
import time
from collections import deque

# ---------------------------------------------------------------------------
# DPI & Windows API Signatures (64-bit safe, set BEFORE GUI/C++ imports)
# ---------------------------------------------------------------------------
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import tkinter as tk
from tkinter import messagebox

import cv2
import mss
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import keyboard
except Exception:
    keyboard = None

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
try:
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
    winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
    winmm.timeBeginPeriod.restype = wintypes.UINT
    winmm.timeEndPeriod.argtypes = [wintypes.UINT]
    winmm.timeEndPeriod.restype = wintypes.UINT
except Exception:
    winmm = None


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("ii", INPUT_UNION),
    ]


# Explicit Win32 ctypes prototypes (prevents 64-bit HWND truncation)
try:
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
except Exception:
    pass

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MONITOR_DEFAULTTONEAREST = 2

# Hardware DirectInput scan codes & virtual keys
KEY_MAP = {
    "w": (0x57, 0x11),
    "a": (0x41, 0x1E),
    "s": (0x53, 0x1F),
    "d": (0x44, 0x20),
    "space": (0x20, 0x39),
    "esc": (0x1B, 0x01),
    "e": (0x45, 0x12),
    "shift": (0xA0, 0x2A),
    "ctrl": (0xA2, 0x1D),
    "up": (0x26, 0x48),
    "down": (0x28, 0x50),
    "left": (0x25, 0x4B),
    "right": (0x27, 0x4D),
}

EXTENDED_KEYS = {
    "up", "down", "left", "right", "insert", "delete",
    "home", "end", "page_up", "page_down", "rctrl", "ralt",
}

VK_BY_NAME: dict[str, int] = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "page_up": 0x21, "page_down": 0x22, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "space": 0x20, "backspace": 0x08, "pause": 0x13,
    "kp_0": 0x60, "kp_1": 0x61, "kp_2": 0x62, "kp_3": 0x63, "kp_4": 0x64,
    "kp_5": 0x65, "kp_6": 0x66, "kp_7": 0x67, "kp_8": 0x68, "kp_9": 0x69,
    "kp_multiply": 0x6A, "kp_add": 0x6B, "kp_subtract": 0x6D,
    "kp_decimal": 0x6E, "kp_divide": 0x6F,
    "grave": 0xC0, "minus": 0xBD, "equal": 0xBB,
    "bracketleft": 0xDB, "bracketright": 0xDD, "backslash": 0xDC,
    "semicolon": 0xBA, "apostrophe": 0xDE, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
}
for _ch in "abcdefghijklmnopqrstuvwxyz":
    VK_BY_NAME[_ch] = ord(_ch.upper())
for _d in "0123456789":
    VK_BY_NAME[_d] = ord(_d)

NAME_BY_VK: dict[int, str] = {}
for _kname, _kvk in VK_BY_NAME.items():
    if _kvk not in NAME_BY_VK and _kname not in ("pageup", "pagedown"):
        NAME_BY_VK[_kvk] = _kname

RESERVED_HOTKEYS = {"w", "a", "s", "d", "space", "ctrl", "shift", "esc", "escape", "e", "return", "tab"}

# Map Tk/VK key names to keyboard-library compatible names or hardware scan codes
KB_HOTKEY_MAP: dict[str, str | int] = {
    "page_up": "page up", "page_down": "page down", "pageup": "page up", "pagedown": "page down",
    "kp_multiply": "*", "kp_add": "add", "kp_subtract": "subtract",
    "kp_decimal": "decimal", "kp_divide": "slash",
    "kp_0": 0x52, "kp_1": 0x4F, "kp_2": 0x50, "kp_3": 0x51, "kp_4": 0x4B,
    "kp_5": 0x4C, "kp_6": 0x4D, "kp_7": 0x47, "kp_8": 0x48, "kp_9": 0x49,
    "grave": 0x29, "minus": "-", "equal": "=", "bracketleft": 0x1A, "bracketright": 0x1B,
    "backslash": "\\", "semicolon": ";", "apostrophe": 0x28, "comma": ",", "period": ".", "slash": "/",
}


def kb_hotkey_spec(kname: str) -> str | int:
    """Translate internal key name into a valid keyboard.add_hotkey key or scan-code spec."""
    kl = str(kname).strip().lower()
    return KB_HOTKEY_MAP.get(kl, kl)


def is_admin() -> bool:
    """Return True if process runs with Administrator elevation."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def system_reduced_motion() -> bool:
    """Query Windows SPI_GETCLIENTAREAANIMATION to respect OS animation preference."""
    try:
        enabled = wintypes.BOOL(True)
        if user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not bool(enabled.value)
    except Exception:
        pass
    return False


def send_key_hw(key: str, down: bool) -> None:
    """Send DirectInput scan-code keystroke safely via SendInput."""
    kl = key.lower()
    vk, scan = KEY_MAP.get(kl, (0, 0))
    if not vk and not scan:
        vk = VK_BY_NAME.get(kl, 0)
        if vk:
            scan = int(user32.MapVirtualKeyW(vk, 0))
    if not vk and not scan:
        return

    flags = KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP)
    if kl in EXTENDED_KEYS or scan >= 0xE000:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ii.ki.wVk = 0
    inp.ii.ki.wScan = scan & 0xFF
    inp.ii.ki.dwFlags = flags
    inp.ii.ki.time = 0
    inp.ii.ki.dwExtraInfo = 0
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent == 0:
        kb_flags = (0 if down else KEYEVENTF_KEYUP) | (KEYEVENTF_EXTENDEDKEY if kl in EXTENDED_KEYS else 0)
        user32.keybd_event(vk, scan & 0xFF, kb_flags, 0)


def send_mouse_rel(dx: int, dy: int) -> None:
    """Send relative mouse movement delta via SendInput."""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.ii.mi.dx = int(dx)
    inp.ii.mi.dy = int(dy)
    inp.ii.mi.mouseData = 0
    inp.ii.mi.dwFlags = MOUSEEVENTF_MOVE
    inp.ii.mi.time = 0
    inp.ii.mi.dwExtraInfo = 0
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent == 0:
        user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


def send_mouse_button(down: bool, button: str = "left") -> None:
    """Send left or right mouse button press or release via SendInput."""
    if button == "right":
        flag = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
    else:
        flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.ii.mi.dwFlags = flag
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent == 0:
        user32.mouse_event(flag, 0, 0, 0, 0)


def set_cursor_pos(x: int, y: int) -> None:
    """Move OS cursor to exact desktop screen coordinates (skipped in headless test runner)."""
    if os.environ.get("PIRATE_HEADLESS") == "1":
        return
    user32.SetCursorPos(int(x), int(y))


def click_screen_pos(x: int, y: int) -> None:
    """Move cursor to exact desktop screen coordinates, wake Unreal Slate hover, and left-click."""
    tx, ty = int(x), int(y)
    if os.environ.get("PIRATE_HEADLESS") != "1":
        set_cursor_pos(tx - 6, ty)
        time.sleep(0.025)
        send_mouse_rel(6, 0)
        time.sleep(0.025)
    set_cursor_pos(tx, ty)
    time.sleep(0.09)
    send_mouse_button(True)
    time.sleep(0.07)
    send_mouse_button(False)
    time.sleep(0.18)


def active_fortnite_hwnd(allow_any_window: bool = False) -> int | None:
    """Return foreground HWND if Fortnite (or allowed window) is active and not minimized."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    title = buf.value.lower()
    if "pirate token farm" in title or "otbros farm" in title or "fortnite assistant" in title:
        return None
    if allow_any_window:
        return int(hwnd)
    if "fortnite" in title or "unreal" in title:
        return int(hwnd)
    try:
        cbuf = ctypes.create_unicode_buffer(128)
        if user32.GetClassNameW(hwnd, cbuf, 128):
            if "unrealwindow" in cbuf.value.lower():
                return int(hwnd)
    except Exception:
        pass
    return None


def is_window_minimized(hwnd: int | None) -> bool:
    """Return True when a valid window handle is minimized (iconic)."""
    if not hwnd:
        return False
    try:
        return bool(user32.IsIconic(int(hwnd)))
    except Exception:
        return False


def find_fortnite_hwnd() -> int | None:
    """Find top-level Fortnite UnrealWindow handle even when minimized or in background."""
    if os.environ.get("PIRATE_HEADLESS") == "1":
        return None
    try:
        hwnd = user32.FindWindowW("UnrealWindow", None)
        if hwnd:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.lower()
            if "pirate token farm" not in title and ("fortnite" in title or not title):
                return int(hwnd)
    except Exception:
        pass
    return None


def monitor_rect_for_hwnd(hwnd: int | None, fallback: dict) -> dict:
    """Resolve virtual desktop monitor rectangle containing hwnd for multi-monitor capture."""
    if hwnd:
        try:
            hmon = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
            if hmon:
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                    r = mi.rcMonitor
                    w = int(r.right - r.left)
                    h = int(r.bottom - r.top)
                    if w > 0 and h > 0:
                        return {"left": int(r.left), "top": int(r.top), "width": w, "height": h}
        except Exception:
            pass
    return fallback


# ---------------------------------------------------------------------------
# Constants, Obsidian Palette & Localization
# ---------------------------------------------------------------------------
APP_NAME = "Pirate Token Farm"
APP_VERSION = ""
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT))
else:
    ROOT = Path(__file__).resolve().parent
    BUNDLE_DIR = ROOT
TEMPLATES = BUNDLE_DIR / "templates"
ASSETS = BUNDLE_DIR / "assets"
FONTS_DIR = BUNDLE_DIR / "fonts"
CONFIG = ROOT / "settings.json"
HEADLESS = bool(os.environ.get("PIRATE_HEADLESS") or os.environ.get("OTBROS_HEADLESS"))

WIN_W = 640

# Pure Obsidian Black Gradient Design System
C_BG_TOP = (14, 15, 19)       # #0E0F13
C_BG_BOT = (7, 8, 10)         # #07080A
C_FOOTER_BG = (10, 11, 14)    # #0A0B0E
C_CARD = (16, 18, 22)         # #101216
C_CARD_HOV = (21, 24, 30)     # #15181E
C_CARD_ACT = (24, 28, 36)     # #181C24
C_SUNK = (10, 11, 15)         # #0A0B0F
C_CTRL = (24, 27, 35)         # #181B23
C_CTRL_HOV = (32, 36, 46)     # #20242E
C_SWITCH_OFF = (30, 34, 43)   # #1E222B

C_BORDER_SUB = (34, 37, 45, 255)      # subtle card hairline (#22252D)
C_BORDER_MED = (48, 52, 62, 255)      # header / window hairline (#30343E)
C_BORDER_CTRL = (76, 82, 96, 255)     # >= 3:1 control outline (#4C5260)
C_BORDER_ACT = (128, 136, 154, 255)   # active / selected outline (#80889A)

C_TX = (242, 244, 248)        # #F2F4F8 (17+:1, soft white)
C_TX2 = (176, 182, 196)       # #B0B6C4 (8.8:1, soft readable slate)
C_TX3 = (138, 145, 160)       # #8A91A0 (5.6:1, muted metadata)

C_CTA_BG = (242, 244, 248)    # #F2F4F8
C_CTA_HOV = (255, 255, 255)   # #FFFFFF
C_CTA_FG = (9, 9, 11)         # #09090B

C_OK = (52, 211, 153)         # #34D399
C_RUN = (96, 165, 250)        # #60A5FA
C_STOP = (248, 113, 113)      # #F87171

FONT_FILES = {
    "rg": ("Inter-Regular.otf", "SegUIVar.ttf", "segoeui.ttf"),
    "md": ("Inter-Medium.otf", "SegUIVar.ttf", "seguisb.ttf"),
    "sb": ("Inter-SemiBold.otf", "SegUIVar.ttf", "seguisb.ttf"),
    "bd": ("Inter-Bold.otf", "SegUIVar.ttf", "segoeuib.ttf"),
}

TEXT = {
    "ru": {
        "sub": "Ассистент фарма и Анти-АФК для Fortnite",
        "settings": "Настройки",
        "back": "Назад",
        "sec_methods": "ИГРОВОЙ МЕТОД",
        "hint_auto": "Автоматический перезапуск",
        "hint_afk": "Только Анти-АФК",
        "m1_title": "1. Повторная игра",
        "m1_desc": "Находит и нажимает «Играть снова» после завершения матча",
        "m2_title": "2. Полный цикл через лобби",
        "m2_desc": "Играть → ожидание таймера → выход в лобби → новый старт",
        "m0_title": "3. Только Анти-АФК (без поиска кнопок)",
        "m0_desc": "Отключает игровой цикл и запускает только Анти-АФК",
        "params_title": "Параметры метода",
        "delay_title": "Таймер цикла (Метод 2)",
        "delay_desc": "Случайная пауза перед выходом в лобби, в минутах",
        "safe_title": "Запасной клик «Играть»",
        "safe_desc": "Нажимает «Играть» в лобби, если кнопка «Играть снова» недоступна",
        "sec_afk": "АНТИ-АФК ПОВЕДЕНИЕ",
        "afk_safety": "Только ввод клавиатуры и мыши",
        "imm_title": "Сразу запускать Анти-АФК",
        "imm_desc": "Не ждать экран «Подключение…» перед началом движений",
        "human_title": "Анти-АФК",
        "human_desc": "Стрейфы W/A/S/D, подкаты, приседания, увороты A–D, осмотр ПКМ и камера",
        "swing_title": "Удары киркой (ЛКМ)",
        "swing_desc": "Случайные взмахи или серия ударов во время фарма",
        "lmb_mode": "Режим ЛКМ:",
        "lmb_swings": "Случайные взмахи",
        "lmb_hold": "Зажатие ЛКМ",
        "space_title": "Случайные прыжки",
        "space_desc": "Периодические нажатия Пробела с переменным интервалом",
        "walk_title": "Движение и повороты",
        "walk_desc": "Ходьба по точкам и повороты обзора камеры",
        "pace_label": "Темп пауз:",
        "pace_norm": "Обычный ритм",
        "pace_stand": "Стоять ~20 с",
        "st_ready": "Готов к работе",
        "st_starting": "Запуск…",
        "st_running": "Работает",
        "st_stopping": "Остановка…",
        "st_stopped": "Остановлено",
        "dt_idle": "Нажмите «Запустить» или клавишу",
        "dt_wait_game": "Сверните окно и вернитесь в Fortnite…",
        "dt_afk_wait": "Запуск режима «Только Анти-АФК»…",
        "dt_method1": "Поиск кнопок «Играть снова» / «Играть»",
        "dt_method2": "Ожидание кнопки «Играть» в лобби",
        "dt_waiting": "Ожидание матча (~{m} мин)…",
        "dt_clicked": "Нажато: ",
        "dt_mouse_hold": "Зажатие ЛКМ (фарм)",
        "dt_space": "Случайный прыжок",
        "dt_swing": "Взмах киркой",
        "dt_jump_swing": "Удар киркой в прыжке",
        "dt_look": "Плавный обзор камерой",
        "dt_idle_look": "Микро-коррекция обзора",
        "dt_crouch": "Присед и осмотр",
        "dt_crouch_strafe": "Присед со стрейфом",
        "dt_slide": "Разгон и подкат",
        "dt_slide_jump": "Подкат с прыжком",
        "dt_wiggle": "Уворот стрейфами A–D",
        "dt_rmb_peek": "Короткий осмотр (ПКМ)",
        "dt_strafe": "Анти-АФК: {keys}",
        "dt_pause": "пауза",
        "dt_walk_go": "Ходьба вперёд",
        "dt_walk_stand": "Пауза ~20 с на месте",
        "dt_walk_turn": "Разворот камеры ~180°",
        "m0_part_human": "Анти-АФК",
        "m0_part_swing": "Кирка",
        "m0_part_space": "Прыжки",
        "m0_part_walk": "WASD",
        "m0_part_mouse": "ЛКМ",
        "log_ready": "Конфигурация загружена",
        "log_conn": "Экран загрузки распознан · Анти-АФК активен.",
        "btn_start": "Запустить",
        "btn_running": "Выполняется",
        "btn_stop": "Остановить",
        "btn_reset": "Сбросить настройки",
        "undo_msg": "Настройки сброшены к значениям по умолчанию.",
        "undo_btn": "Отменить",
        "undo_done": "Сброс настроек отменён.",
        "sec_perf": "ПРОИЗВОДИТЕЛЬНОСТЬ И АНИМАЦИИ",
        "perf_note": "Нулевая нагрузка в фоне",
        "anim_title": "Анимации интерфейса",
        "anim_desc": "Режим без анимаций даёт мгновенный отклик и 0% CPU",
        "anim_on": "Плавные (60 FPS)",
        "anim_off": "Отключены",
        "sec_input": "КАЛИБРОВКА И ГОРЯЧИЕ КЛАВИШИ",
        "turn_title": "Поворот камеры на 180° (px)",
        "turn_desc": "Подберите под вашу чувствительность мыши в игре",
        "hk_start": "Клавиша запуска",
        "hk_start_desc": "Нажмите кнопку и затем любую клавишу (Esc для отмены)",
        "hk_stop": "Клавиша остановки",
        "hk_stop_desc": "Мгновенно прекращает движения и отпускает клавиши",
        "hk_press": "Клавиша…",
        "any_title": "Разрешить работу в любом окне",
        "any_desc": "Для проверки макроса в Блокноте или на рабочем столе",
        "sec_about": "О ПРОГРАММЕ И ДИАГНОСТИКА",
        "about_title": "Pirate Token Farm · Anti-AFK",
        "about_desc": "Только системный ввод DirectInput (SendInput). Без чтения памяти и вмешательства в файлы игры.",
        "admin_ok": "Администратор · DirectInput",
        "admin_no": "Обычный режим · DirectInput",
        "min_word": "мин",
        "fb_on": "Запасной «Играть» вкл",
        "fb_off": "Запасной «Играть» выкл",
        "err_notfound": "Не найден шаблон в папке templates/: ",
        "err_afk_req": "Включите хотя бы одну опцию в разделе Анти-АФК.",
        "err_key_same": "Эта клавиша уже назначена для другого действия.",
        "err_key_res": "Нельзя назначить игровую клавишу (W/A/S/D/Space/Shift/Ctrl/Esc/E).",
        "log_key_set": "Назначена горячая клавиша: ",
        "log_error": "Ошибка: ",
        "log_retry_esc": "Меню не открылось · повторный Esc",
        "dt_fn_minimized": "Окно Fortnite свёрнуто · автофарм остановлен",
        "log_fn_minimized": "Окно Fortnite свёрнуто или неактивно · автофарм остановлен",
        "dt_check_mode": "Проверка режима лобби",
        "dt_fix_squad": "Установка: Отряд и Заполнение",
        "log_mode_solo_detected": "Обнаружен одиночный режим · переключение в Отряд",
        "log_mode_squad_ok": "Режим Отряд и Заполнение активен",
        "log_mode_squad_fixed": "Режим успешно изменен на Отряд и Заполнение",
        "log_m1_lobby_check": "Периодическая проверка режима в лобби (метод 1)",
    },
    "en": {
        "sub": "Fortnite Farming & Anti-AFK Assistant",
        "settings": "Settings",
        "back": "Back",
        "sec_methods": "GAME METHOD",
        "hint_auto": "Automatic queue loop",
        "hint_afk": "Anti-AFK only",
        "m1_title": "1. Play Again",
        "m1_desc": "Detects and clicks Play Again once a match finishes",
        "m2_title": "2. Full lobby cycle",
        "m2_desc": "Play → wait timer → return to lobby → start again",
        "m0_title": "3. Anti-AFK only (skip menu loop)",
        "m0_desc": "Disables queue automation and runs Anti-AFK movement only",
        "params_title": "Method parameters",
        "delay_title": "Cycle timer (Method 2)",
        "delay_desc": "Random delay before returning to the lobby, in minutes",
        "safe_title": "Fallback Play click",
        "safe_desc": "Clicks Play in the lobby when Play Again is unavailable",
        "sec_afk": "ANTI-AFK BEHAVIOR",
        "afk_safety": "Keyboard & mouse input only",
        "imm_title": "Start Anti-AFK immediately",
        "imm_desc": "Begin movement right away without waiting for Connecting…",
        "human_title": "Anti-AFK",
        "human_desc": "W/A/S/D strafes, sprint-slides, crouch-peeks, AD wiggles & camera look",
        "swing_title": "Pickaxe swings (LMB)",
        "swing_desc": "Random pickaxe swings or short combos during farming",
        "lmb_mode": "LMB mode:",
        "lmb_swings": "Random swings",
        "lmb_hold": "Hold LMB",
        "space_title": "Random jumps",
        "space_desc": "Periodic Space jumps with randomized timing",
        "walk_title": "Movement & turns",
        "walk_desc": "Waypoint walking and smooth camera turns",
        "pace_label": "Pause cadence:",
        "pace_norm": "Normal rhythm",
        "pace_stand": "Stand ~20 s",
        "st_ready": "Ready",
        "st_starting": "Starting…",
        "st_running": "Running",
        "st_stopping": "Stopping…",
        "st_stopped": "Stopped",
        "dt_idle": "Click Start or press",
        "dt_wait_game": "Switch focus back into Fortnite…",
        "dt_afk_wait": "Starting Anti-AFK only mode…",
        "dt_method1": "Scanning for Play Again / Play buttons",
        "dt_method2": "Waiting for Play button in lobby",
        "dt_waiting": "In match timer (~{m} min left)…",
        "dt_clicked": "Clicked: ",
        "dt_mouse_hold": "Holding LMB (harvest)",
        "dt_space": "Random jump",
        "dt_swing": "Pickaxe swing",
        "dt_jump_swing": "Jump pickaxe swing",
        "dt_look": "Smooth camera look",
        "dt_idle_look": "Idle aim drift",
        "dt_crouch": "Crouch peek",
        "dt_crouch_strafe": "Crouch strafe",
        "dt_slide": "Sprint slide burst",
        "dt_slide_jump": "Slide-hop combo",
        "dt_wiggle": "AD dodge wiggle",
        "dt_rmb_peek": "Brief ADS peek (RMB)",
        "dt_strafe": "Anti-AFK: {keys}",
        "dt_pause": "pause",
        "dt_walk_go": "Walking forward",
        "dt_walk_stand": "Pausing ~20 s",
        "dt_walk_turn": "Turning ~180°",
        "m0_part_human": "Anti-AFK",
        "m0_part_swing": "Pickaxe",
        "m0_part_space": "Space",
        "m0_part_walk": "WASD",
        "m0_part_mouse": "LMB",
        "log_ready": "Configuration loaded",
        "log_conn": "Connecting screen detected · Anti-AFK active.",
        "btn_start": "Start",
        "btn_running": "Running",
        "btn_stop": "Stop",
        "btn_reset": "Reset settings",
        "undo_msg": "Settings restored to defaults.",
        "undo_btn": "Undo",
        "undo_done": "Settings reset undone.",
        "sec_perf": "PERFORMANCE & MOTION",
        "perf_note": "Zero background CPU usage",
        "anim_title": "Interface animations",
        "anim_desc": "Disabling animations yields instant changes with 0% CPU",
        "anim_on": "Smooth (60 FPS)",
        "anim_off": "Disabled",
        "sec_input": "CALIBRATION & HOTKEYS",
        "turn_title": "180° camera turn (px)",
        "turn_desc": "Match to your in-game mouse sensitivity",
        "hk_start": "Start hotkey",
        "hk_start_desc": "Click the button, then press any key (Esc to cancel)",
        "hk_stop": "Stop hotkey",
        "hk_stop_desc": "Immediately stops and releases all held keys",
        "hk_press": "Key…",
        "any_title": "Allow any active window",
        "any_desc": "Useful for testing macro behavior in Notepad or on Desktop",
        "sec_about": "ABOUT & DIAGNOSTICS",
        "about_title": "Pirate Token Farm · Anti-AFK",
        "about_desc": "Uses standard DirectInput (SendInput) only. Never reads process memory or modifies game files.",
        "admin_ok": "Administrator · DirectInput",
        "admin_no": "Standard mode · DirectInput",
        "min_word": "min",
        "fb_on": "Fallback Play on",
        "fb_off": "Fallback Play off",
        "err_notfound": "Missing template inside templates/: ",
        "err_afk_req": "Enable at least one option in the Anti-AFK section.",
        "err_key_same": "That hotkey is already assigned to the other action.",
        "err_key_res": "Cannot bind a gameplay movement key (W/A/S/D/Space/Shift/Ctrl/Esc/E).",
        "log_key_set": "Assigned hotkey: ",
        "log_error": "Error: ",
        "log_retry_esc": "Menu missed · retrying Esc",
        "dt_fn_minimized": "Fortnite minimized · autofarm stopped",
        "log_fn_minimized": "Fortnite window minimized or unfocused · autofarm stopped",
        "dt_check_mode": "Checking lobby mode",
        "dt_fix_squad": "Setting Squads and Fill",
        "log_mode_solo_detected": "Solo mode detected · switching to Squads",
        "log_mode_squad_ok": "Squads and Fill mode active",
        "log_mode_squad_fixed": "Mode successfully switched to Squads and Fill",
        "log_m1_lobby_check": "Periodic lobby mode check (Method 1)",
    },
}


# ---------------------------------------------------------------------------
# Template Matcher (Multi-resolution 0.50x..2.15x, inner-core & dual-polarity)
# ---------------------------------------------------------------------------
TEMPLATE_NAMES = (
    "play_again",
    "play_button",
    "menu_button",
    "return_lobby",
    "connecting",
    "mode_squad_fill",
    "mode_solo",
    "esc_gotovo",
)

# Tight inner-core regions (y0, y1, x0, x1) strictly inside each button containing the text/icon,
# eliminating background corners and outer borders so any 3D post-match background matches cleanly.
CORE_BOXES: dict[str, tuple[int, int, int, int]] = {
    "play_again": (24, 72, 95, 393),
    "play_button": (24, 73, 60, 285),
    "return_lobby": (20, 58, 165, 425),
    "menu_button": (18, 60, 42, 98),
    "esc_gotovo": (18, 73, 20, 208),
}

# Post-match buttons that can appear either selected (yellow fill, dark text) or unselected (dark fill, light text)
DUAL_POLARITY_CORE: set[str] = {"play_again", "return_lobby"}


def check_templates_exist() -> None:
    """Fast file check without decoding/allocating template pyramids on UI thread."""
    for name in TEMPLATE_NAMES:
        path = TEMPLATES / f"{name}.png"
        if not path.exists():
            raise FileNotFoundError(str(path))


class Matcher:
    def __init__(self) -> None:
        self.data: dict[str, list[tuple[np.ndarray, np.ndarray | None, int, int]]] = {}
        self.core_data: dict[str, list[tuple[np.ndarray, int, int, int, int, int, int]]] = {}
        self.scales = (
            1.00, 0.96, 1.04, 0.92, 1.08, 0.88, 1.12, 0.83, 1.17, 0.79, 1.22,
            0.75, 1.28, 0.71, 1.33, 0.67, 1.40, 0.63, 1.48, 0.59, 1.56, 0.55,
            1.65, 0.50, 1.75, 1.88, 2.00, 2.15,
        )
        self._raw_imgs: dict[str, np.ndarray] = {}
        self._raw_cores: dict[str, tuple[np.ndarray, int, int, int, int]] = {}
        self._coarse_cache: dict[tuple[str, float, int], np.ndarray] = {}
        kernel = np.ones((5, 5), np.uint8)
        for name in TEMPLATE_NAMES:
            path = TEMPLATES / f"{name}.png"
            if not path.exists():
                raise FileNotFoundError(str(path))
            raw = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise RuntimeError(f"Cannot decode {path}")
            self._raw_imgs[name] = img
            h0, w0 = img.shape[:2]
            variants = []
            for scale in self.scales:
                w = max(20, int(round(w0 * scale)))
                h = max(12, int(round(h0 * scale)))
                tpl = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)
                mask = None
                if name == "connecting":
                    # Dilated 5x5 halo keeps both bright letters and immediate contrast border,
                    # isolating seasonal background colors without NaN variance or flat-white hits.
                    fg = (tpl > 195).astype(np.uint8) * 255
                    halo = cv2.dilate(fg, kernel)
                    if np.count_nonzero(fg) > 10 and np.count_nonzero(halo) > np.count_nonzero(fg):
                        tpl = np.where(fg > 0, tpl, 45).astype(np.uint8)
                        mask = halo
                variants.append((tpl, mask, w, h))
            self.data[name] = variants

            if name in CORE_BOXES:
                cy0, cy1, cx0, cx1 = CORE_BOXES[name]
                core_img = img[cy0:cy1, cx0:cx1]
                self._raw_cores[name] = (core_img, cx0, cy0, w0, h0)
                ch0, cw0 = core_img.shape[:2]
                c_variants = []
                for scale in self.scales:
                    cw = max(16, int(round(cw0 * scale)))
                    ch = max(10, int(round(ch0 * scale)))
                    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
                    ctpl = cv2.resize(core_img, (cw, ch), interpolation=interp)
                    ox = int(round(cx0 * scale))
                    oy = int(round(cy0 * scale))
                    fw = max(20, int(round(w0 * scale)))
                    fh = max(12, int(round(h0 * scale)))
                    c_variants.append((ctpl, cw, ch, ox, oy, fw, fh))
                self.core_data[name] = c_variants

    def _coarse_tpl(self, key_prefix: str, img: np.ndarray, scale: float, c_div: int) -> np.ndarray:
        key = (key_prefix, scale, c_div)
        ctpl = self._coarse_cache.get(key)
        if ctpl is None:
            h0, w0 = img.shape[:2]
            cw = max(10, int(round(w0 * scale / c_div)))
            ch = max(6, int(round(h0 * scale / c_div)))
            ctpl = cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)
            self._coarse_cache[key] = ctpl
        return ctpl

    def _search_single_frame(
        self,
        gray: np.ndarray,
        name: str,
        threshold: float,
        stop_event: threading.Event | None = None,
        expected_scale: float | None = None,
        is_roi: bool = False,
    ) -> tuple[float, tuple[int, int, int, int] | None]:
        variants = self.data.get(name, ())
        if not variants:
            return -1.0, None
        best = -1.0
        box = None
        gh, gw = gray.shape[:2]
        early_stop = max(threshold + 0.06, 0.94)
        dual_pol = name in DUAL_POLARITY_CORE
        has_core = name in self.core_data

        # Fast 2-stage coarse-to-fine pyramid search on full-screen frames (720p..4K)
        if not is_roi and gh >= 360 and gw >= 600:
            est_h = gh / 1080.0
            est_w = gw / 1920.0
            est_min = min(est_h, est_w)
            est_max = max(est_h, est_w)
            lo_sc = max(0.48, min(0.65, est_min * 0.58))
            hi_sc = min(2.20, max(1.35, est_max * 1.42))
            indexed = [
                (idx, self.scales[idx])
                for idx in range(len(variants))
                if lo_sc <= self.scales[idx] <= hi_sc
            ]
            if not indexed:
                indexed = [(idx, self.scales[idx]) for idx in range(len(variants))]
            est_mid = 0.5 * (est_h + est_w)
            indexed.sort(key=lambda item: (0 if item[1] == 1.0 and abs(est_mid - 1.0) <= 0.25 else 1, abs(item[1] - est_mid)))

            c_div = 4 if gw >= 2400 else 2
            c_gray = cv2.resize(gray, (max(32, gw // c_div), max(32, gh // c_div)), interpolation=cv2.INTER_AREA)
            raw_src = self._raw_cores[name][0] if has_core else self._raw_imgs[name]
            prefix = f"core:{name}" if has_core else f"full:{name}"

            coarse_hits: list[tuple[float, int, float, int, int]] = []
            for idx, sc in indexed:
                if stop_event is not None and stop_event.is_set():
                    return -1.0, None
                _, _, w, h = variants[idx]
                if h >= gh or w >= gw:
                    continue
                ctpl = self._coarse_tpl(prefix, raw_src, sc, c_div)
                ch_c, cw_c = ctpl.shape[:2]
                if ch_c >= c_gray.shape[0] or cw_c >= c_gray.shape[1]:
                    continue
                res_c = cv2.matchTemplate(c_gray, ctpl, cv2.TM_CCOEFF_NORMED)
                min_v, max_v, min_l, max_l = cv2.minMaxLoc(res_c)
                coarse_hits.append((float(max_v), idx, sc, int(max_l[0]), int(max_l[1])))
                if dual_pol and (-min_v) > 0.45:
                    coarse_hits.append((float(-min_v), idx, sc, int(min_l[0]), int(min_l[1])))
                # Also extract 2nd local peak so bright HUD clutter never masks the button
                if has_core:
                    res_c2 = res_c.copy()
                    ry0 = max(0, max_l[1] - max(4, ch_c // 2))
                    ry1 = min(res_c2.shape[0], max_l[1] + max(4, ch_c // 2) + 1)
                    rx0 = max(0, max_l[0] - max(6, cw_c // 2))
                    rx1 = min(res_c2.shape[1], max_l[0] + max(6, cw_c // 2) + 1)
                    res_c2[ry0:ry1, rx0:rx1] = 0.0
                    _, max_v2, _, max_l2 = cv2.minMaxLoc(res_c2)
                    if max_v2 > 0.45:
                        coarse_hits.append((float(max_v2), idx, sc, int(max_l2[0]), int(max_l2[1])))

            coarse_hits.sort(key=lambda item: item[0], reverse=True)
            pad = max(24, c_div * 10)
            for _, idx, _sc, cx, cy in coarse_hits[:6]:
                if stop_event is not None and stop_event.is_set():
                    return -1.0, None
                tpl, mask, w, h = variants[idx]
                if has_core:
                    ctpl, cw, ch, ox, oy, fw, fh = self.core_data[name][idx]
                    fx, fy = cx * c_div - ox, cy * c_div - oy
                else:
                    fx, fy = cx * c_div, cy * c_div
                x0 = max(0, fx - pad)
                y0 = max(0, fy - pad)
                x1 = min(gw, fx + w + pad)
                y1 = min(gh, fy + h + pad)
                roi = gray[y0:y1, x0:x1]
                if roi.shape[0] >= h and roi.shape[1] >= w:
                    if mask is not None:
                        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED, mask=mask)
                        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
                    else:
                        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                    _, score, _, loc = cv2.minMaxLoc(res)
                    if score > best:
                        best = float(score)
                        box = (int(x0 + loc[0]), int(y0 + loc[1]), int(w), int(h))
                if has_core:
                    ctpl, cw, ch, ox, oy, fw, fh = self.core_data[name][idx]
                    if roi.shape[0] >= ch and roi.shape[1] >= cw:
                        res_core = cv2.matchTemplate(roi, ctpl, cv2.TM_CCOEFF_NORMED)
                        c_min_v, c_max_v, c_min_l, c_max_l = cv2.minMaxLoc(res_core)
                        c_score = float(c_max_v)
                        c_loc = c_max_l
                        if dual_pol and (-c_min_v) > c_score:
                            c_score = float(-c_min_v)
                            c_loc = c_min_l
                        if c_score > best:
                            best = c_score
                            bx = max(0, int(x0 + c_loc[0] - ox))
                            by = max(0, int(y0 + c_loc[1] - oy))
                            box = (bx, by, int(fw), int(fh))
                if best >= early_stop:
                    break
            if best >= threshold and box is not None:
                return best, box
            return best, None

        indexed_direct = list(range(len(variants)))
        if expected_scale is not None:
            indexed_direct.sort(key=lambda idx: abs(self.scales[idx] - expected_scale))

        for idx in indexed_direct:
            tpl, mask, w, h = variants[idx]
            if stop_event is not None and stop_event.is_set():
                return -1.0, None
            if h < gh and w < gw:
                if mask is not None:
                    res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED, mask=mask)
                    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
                else:
                    res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
                _, score, _, loc = cv2.minMaxLoc(res)
                if score > best:
                    best = float(score)
                    box = (int(loc[0]), int(loc[1]), int(w), int(h))
            if has_core:
                ctpl, cw, ch, ox, oy, fw, fh = self.core_data[name][idx]
                if ch < gh and cw < gw:
                    res_core = cv2.matchTemplate(gray, ctpl, cv2.TM_CCOEFF_NORMED)
                    c_min_v, c_max_v, c_min_l, c_max_l = cv2.minMaxLoc(res_core)
                    c_score = float(c_max_v)
                    c_loc = c_max_l
                    if dual_pol and (-c_min_v) > c_score:
                        c_score = float(-c_min_v)
                        c_loc = c_min_l
                    if c_score > best:
                        best = c_score
                        bx = max(0, int(c_loc[0] - ox))
                        by = max(0, int(c_loc[1] - oy))
                        box = (bx, by, int(fw), int(fh))
            if best >= early_stop:
                break
        if best >= threshold and box is not None:
            return best, box
        return best, None

    def find(
        self,
        gray: np.ndarray | None,
        name: str,
        threshold: float = 0.84,
        stop_event: threading.Event | None = None,
        expected_scale: float | None = None,
        is_roi: bool = False,
    ) -> tuple[float, tuple[int, int, int, int] | None]:
        if gray is None or gray.size == 0:
            return -1.0, None
        best, box = self._search_single_frame(
            gray, name, threshold, stop_event, expected_scale=expected_scale, is_roi=is_roi
        )
        if box is not None:
            return best, box
        # For non-16:9 aspect ratios (e.g. stretched 4:3, 5:4, 16:10, 21:9), un-stretch to 16:9 and map box back
        gh, gw = gray.shape[:2]
        if not is_roi and gh >= 360 and gw >= 600 and abs((gw / gh) - (16.0 / 9.0)) > 0.03:
            norm_w = int(round(gh * 16.0 / 9.0))
            norm_gray = cv2.resize(gray, (norm_w, gh), interpolation=cv2.INTER_LINEAR)
            s2, b2 = self._search_single_frame(
                norm_gray, name, threshold, stop_event, expected_scale=expected_scale, is_roi=is_roi
            )
            if s2 > best:
                best = s2
            if b2 is not None:
                sx = gw / float(norm_w)
                nx, ny, nw, nh = b2
                return s2, (int(round(nx * sx)), int(ny), int(round(nw * sx)), int(nh))
        return best, None


# ---------------------------------------------------------------------------
# Automation & Anti-AFK Engine (Thread-safe, synchronized, live-reactive)
# ---------------------------------------------------------------------------
_LOCAL_TOKEN_NOTIFIER = None


class Engine:
    def __init__(self, app: "App", cap: mss.base.MSSBase) -> None:
        self.app = app
        self.cap = cap
        self.stop = app.stop_event
        self.busy = app.busy_event
        self.lock = app.action_lock
        self.matcher = Matcher()
        self.fallback_mon = cap.monitors[1] if len(cap.monitors) > 1 else cap.monitors[0]
        self.monitor = dict(self.fallback_mon)

        self.w_down = False
        self.mouse_down = False
        self.rmb_down = False
        self.held_keys: set[str] = set()
        self.pitch_acc = 0

        now = time.monotonic()
        self.next_space = now + random.uniform(1.8, 5.0)
        self.next_swing = now + random.uniform(6.0, 10.0)
        self.next_look = now + random.uniform(1.2, 3.2)
        self.next_idle_drift = now + random.uniform(1.6, 4.2)
        self.next_crouch = now + random.uniform(11.0, 26.0)
        self.next_slide = now + random.uniform(8.0, 19.0)
        self.next_wiggle = now + random.uniform(9.5, 22.0)
        self.next_rmb_peek = now + random.uniform(12.0, 28.0)
        self.next_strafe = now + random.uniform(3.5, 7.5)
        self.lmb_safe_after = 0.0
        self.next_recenter = now
        self.lobby_check_interval_range = (10.0 * 60.0, 15.0 * 60.0)
        self.next_lobby_mode_check = now + random.uniform(*self.lobby_check_interval_range)
        self._last_button_click_ts: dict[str, float] = {}
        self._ever_focused = False
        self._last_target_hwnd: int | None = None
        self._monitor_focus_loss = False
        self._focus_loss_logged = False
        self.anti_thread: threading.Thread | None = None
        self.token_thread: threading.Thread | None = None
        self._busy_lock = threading.Lock()
        self._busy_count = 0

    def enter_busy(self) -> None:
        with self._busy_lock:
            self._busy_count += 1
            self.busy.set()

    def exit_busy(self) -> None:
        with self._busy_lock:
            self._busy_count = max(0, self._busy_count - 1)
            if self._busy_count == 0:
                self.busy.clear()

    def _stop_due_to_window_state(self) -> None:
        """Immediately release all held inputs and stop autofarm when Fortnite is minimized or loses focus."""
        self.release_all()
        if not self._focus_loss_logged:
            self._focus_loss_logged = True
            self.app.emit("detail", {"key": "dt_fn_minimized"})
            self.app.emit("log", {"key": "log_fn_minimized"})
        self.stop.set()

    def check_target_window_active(self) -> bool:
        """Return True if target window is active; auto-stop if Fortnite is minimized or loses focus after active."""
        if self.stop.is_set():
            return False
        if self.is_target_focused():
            hwnd = self.active_hwnd()
            if hwnd:
                self._last_target_hwnd = hwnd
                if is_window_minimized(hwnd):
                    self._stop_due_to_window_state()
                    return False
            self._ever_focused = True
            return True
        if is_window_minimized(self._last_target_hwnd):
            self._stop_due_to_window_state()
            return False
        if not self.app.live("any_win"):
            fn_hwnd = find_fortnite_hwnd()
            if fn_hwnd and is_window_minimized(fn_hwnd) and (self._ever_focused or self._monitor_focus_loss):
                self._stop_due_to_window_state()
                return False
        if self._ever_focused or self._monitor_focus_loss:
            self._stop_due_to_window_state()
            return False
        return False

    def center_cursor(self) -> tuple[int, int]:
        """Place OS cursor at exact center of target monitor so it never touches top map, bottom notifications, or Play/Cancel."""
        mon = self.current_monitor()
        cx = int(mon["left"]) + int(mon["width"]) // 2
        cy = int(mon["top"]) + int(mon["height"]) // 2
        if self.is_target_focused() and not self.stop.is_set():
            set_cursor_pos(cx, cy)
        return cx, cy

    def _can_act(self) -> bool:
        """Return True when automation is active, not clicking UI, and target window is focused."""
        return not self.stop.is_set() and not self.busy.is_set() and self.check_target_window_active()

    @staticmethod
    def _next_rhythm_delay(min_s: float, max_s: float, burst_chance: float = 0.22) -> float:
        """Return non-periodic randomized delay mixing brisk bursts and relaxed breathers."""
        roll = random.random()
        if roll < burst_chance:
            return random.uniform(max(0.45, min_s * 0.35), max(0.75, min_s * 0.7))
        if roll > 0.86:
            return random.uniform(max_s * 1.1, max_s * 1.48)
        return random.uniform(min_s, max_s)

    def active_hwnd(self) -> int | None:
        return active_fortnite_hwnd(allow_any_window=self.app.live("any_win"))

    def is_target_focused(self) -> bool:
        return self.active_hwnd() is not None

    def current_monitor(self) -> dict:
        hwnd = self.active_hwnd()
        if hwnd:
            self.monitor = monitor_rect_for_hwnd(hwnd, self.fallback_mon)
        return self.monitor

    def frame(self, cap: mss.base.MSSBase | None = None) -> np.ndarray | None:
        c = cap or self.cap
        mon = self.current_monitor()
        try:
            a = np.array(c.grab(mon))
            if a.size == 0:
                return None
            return cv2.cvtColor(a, cv2.COLOR_BGRA2GRAY)
        except Exception:
            return None

    def frame_color(self, cap: mss.base.MSSBase | None = None) -> tuple[np.ndarray, np.ndarray | None] | None:
        """Capture both grayscale and BGR frame when available, falling back cleanly in mocked tests."""
        c = cap or self.cap
        mon = self.current_monitor()
        try:
            a = np.array(c.grab(mon))
            if a.size > 0:
                return cv2.cvtColor(a, cv2.COLOR_BGRA2GRAY), cv2.cvtColor(a, cv2.COLOR_BGRA2BGR)
        except Exception:
            pass
        gray = self.frame(cap)
        if gray is None:
            return None
        return gray, None

    def key_down(self, k: str) -> None:
        if k not in self.held_keys:
            send_key_hw(k, True)
            self.held_keys.add(k)
            if k == "w":
                self.w_down = True

    def key_up(self, k: str) -> None:
        send_key_hw(k, False)
        self.held_keys.discard(k)
        if k == "w":
            self.w_down = False

    def tap_key(self, key: str, hold_s: float = 0.065) -> None:
        """Send a short press while tracking key in held_keys for cleanup."""
        with self.lock:
            if self.stop.is_set():
                return
            self.key_down(key)
        end = time.monotonic() + hold_s
        while time.monotonic() < end:
            if self.stop.is_set():
                break
            time.sleep(min(0.015, max(0.002, end - time.monotonic())))
        with self.lock:
            self.key_up(key)

    def set_move_keys(self, target: set[str]) -> None:
        with self.lock:
            for k in tuple(self.held_keys - target):
                self.key_up(k)
            if self.busy.is_set() or self.stop.is_set() or not self.is_target_focused():
                return
            for k in target:
                if k not in self.held_keys:
                    self.key_down(k)

    def walk_hold(self, on: bool) -> None:
        self.set_move_keys({"w"} if on else set())

    def _mouse_hold_set(self, on: bool, attr: str, button: str) -> None:
        with self.lock:
            cur = getattr(self, attr)
            if on and not cur:
                send_mouse_button(True, button)
                setattr(self, attr, True)
            elif not on and cur:
                send_mouse_button(False, button)
                setattr(self, attr, False)

    def mouse_hold_set(self, on: bool) -> None:
        self._mouse_hold_set(on, "mouse_down", "left")

    def rmb_hold_set(self, on: bool) -> None:
        self._mouse_hold_set(on, "rmb_down", "right")

    def release_all(self) -> None:
        with self.lock:
            if self.mouse_down:
                send_mouse_button(False, "left")
                self.mouse_down = False
            if self.rmb_down:
                send_mouse_button(False, "right")
                self.rmb_down = False
            for k in set(self.held_keys) | {"w", "a", "s", "d", "shift", "ctrl", "space", "esc", "e"}:
                send_key_hw(k, False)
            self.held_keys.clear()
            self.w_down = False

    def anti_sleep(self, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.stop.is_set() or self.busy.is_set() or not self.check_target_window_active():
                return False
            time.sleep(min(0.02, max(0.002, end - time.monotonic())))
        return True

    def smooth_mouse_move(self, total_dx: int, total_dy: int = 0, duration: float = 0.42) -> bool:
        if self.stop.is_set() or self.busy.is_set() or not self.check_target_window_active():
            return False
        self.center_cursor()
        steps = max(10, int(round(duration / 0.012)))
        done_x = 0
        for i in range(1, steps + 1):
            if self.stop.is_set() or self.busy.is_set() or not self.check_target_window_active():
                return False
            t = i / steps
            ease = 0.5 * (1.0 - math.cos(math.pi * t))
            tx = round(total_dx * ease)
            if i < steps - 1:
                tx += random.randint(-1, 1)
            dx = tx - done_x
            done_x = tx
            if dx:
                with self.lock:
                    if self.busy.is_set() or self.stop.is_set() or not self.check_target_window_active():
                        return False
                    send_mouse_rel(dx, 0)
                    self.pitch_acc = 0
            time.sleep(random.uniform(0.009, 0.015))
        return True

    def turn_around(self) -> None:
        base = max(100, int(self.app.live("turn_px")))
        human_on = bool(self.app.live("human"))
        direction = random.choice((-1, 1)) if human_on else 1
        scale = random.uniform(0.68, 1.24) if human_on else random.uniform(0.88, 1.12)
        total = int(round(base * scale)) * direction
        self.center_cursor()
        if human_on and random.random() < 0.30:
            # Split turn mimics human mouse lift / reset mid-swipe while staying strictly horizontal
            part1 = int(round(total * random.uniform(0.45, 0.65)))
            part2 = total - part1
            if self.smooth_mouse_move(part1, 0, duration=random.uniform(0.18, 0.28)):
                if self.anti_sleep(random.uniform(0.06, 0.14)):
                    self.smooth_mouse_move(part2, 0, duration=random.uniform(0.16, 0.28))
            return
        self.smooth_mouse_move(total, 0, duration=random.uniform(0.36, 0.58))

    def idle_micro_fidget(self) -> None:
        """Apply subtle organic horizontal crosshair micro-drift along screen center."""
        if not self._can_act():
            return
        self.center_cursor()
        dx = random.randint(8, 36) * random.choice((-1, 1))
        self.app.emit("detail", {"key": "dt_idle_look"})
        self.smooth_mouse_move(dx, 0, duration=random.uniform(0.14, 0.28))

    def human_look(self) -> None:
        base = max(100, int(self.app.live("turn_px")))
        roll = random.random()
        big_turn = roll < 0.26
        frac = random.uniform(0.45, 0.96) if big_turn else random.uniform(0.07, 0.36)
        direction = random.choice((-1, 1))
        total_dx = int(round(base * frac)) * direction
        self.pitch_acc = 0
        dur = random.uniform(0.30, 0.54) if big_turn else random.uniform(0.16, 0.34)
        self.app.emit("detail", {"key": "dt_look"})
        if self._can_act():
            self.center_cursor()
            ok = self.smooth_mouse_move(total_dx, 0, duration=dur)
            if ok and big_turn and random.random() < 0.40 and self.anti_sleep(random.uniform(0.08, 0.20)):
                # Shoulder check: partial horizontal return glance toward original heading
                ret_dx = -int(round(total_dx * random.uniform(0.55, 0.85)))
                self.smooth_mouse_move(ret_dx, 0, duration=random.uniform(0.20, 0.34))

    def do_jump_swing(self) -> None:
        """Mid-air jump + horizontal aim flick + pickaxe swing combo."""
        if self.mouse_down or self.app.live("mouse") or not self._can_act():
            return
        self.center_cursor()
        self.app.emit("detail", {"key": "dt_jump_swing"})
        self.app.emit("log", {"key": "dt_jump_swing"})
        try:
            self.tap_key("space", hold_s=random.uniform(0.055, 0.10))
            if not self.anti_sleep(random.uniform(0.06, 0.13)):
                return
            if not self._can_act():
                return
            with self.lock:
                if self._can_act():
                    self.center_cursor()
                    send_mouse_rel(random.randint(-36, 36), 0)
            self.mouse_hold_set(True)
            ok = self.anti_sleep(random.uniform(0.08, 0.16))
            self.mouse_hold_set(False)
            if ok and random.random() < 0.45 and self.anti_sleep(random.uniform(0.26, 0.42)):
                if self._can_act():
                    self.center_cursor()
                    self.mouse_hold_set(True)
                    self.anti_sleep(random.uniform(0.07, 0.13))
                    self.mouse_hold_set(False)
        finally:
            self.mouse_hold_set(False)

    def do_pickaxe_swing(self, allow_jump: bool = False) -> None:
        if self.mouse_down or self.app.live("mouse"):
            return
        if allow_jump and self.app.live("human") and random.random() < 0.24:
            self.do_jump_swing()
            return
        with self.lock:
            had_shift = "shift" in self.held_keys
            if had_shift:
                self.key_up("shift")

        self.center_cursor()
        self.app.emit("detail", {"key": "dt_swing"})
        self.app.emit("log", {"key": "dt_swing"})
        mode = random.random()
        try:
            if mode < 0.38:
                with self.lock:
                    if not self._can_act():
                        return
                self.center_cursor()
                self.mouse_hold_set(True)
                self.anti_sleep(random.uniform(0.08, 0.16))
                self.mouse_hold_set(False)
                if random.random() < 0.5 and self._can_act():
                    with self.lock:
                        send_mouse_rel(random.randint(-28, 28), 0)
            elif mode < 0.76:
                hits = random.choice((2, 2, 3))
                for idx in range(hits):
                    if not self._can_act():
                        break
                    self.center_cursor()
                    self.mouse_hold_set(True)
                    ok = self.anti_sleep(random.uniform(0.07, 0.13))
                    self.mouse_hold_set(False)
                    if not ok:
                        break
                    if idx < hits - 1:
                        if self.app.live("human") and random.random() < 0.45 and self._can_act():
                            self.tap_key(random.choice(("a", "d")), hold_s=random.uniform(0.09, 0.18))
                        if random.random() < 0.65 and self._can_act():
                            with self.lock:
                                send_mouse_rel(random.randint(-22, 22), 0)
                        if not self.anti_sleep(random.uniform(0.32, 0.56)):
                            break
            else:
                with self.lock:
                    if not self._can_act():
                        return
                self.center_cursor()
                self.mouse_hold_set(True)
                self.anti_sleep(random.uniform(0.65, 1.35))
                self.mouse_hold_set(False)
        finally:
            self.mouse_hold_set(False)
            with self.lock:
                if had_shift and self.w_down and self._can_act():
                    self.key_down("shift")

    def do_slide_burst(self, allow_jump: bool = True) -> bool:
        """Sprint forward into a curved Fortnite slide with optional slide-hop exit."""
        if not self._can_act():
            return False
        self.center_cursor()
        self.app.emit("detail", {"key": "dt_slide"})
        if random.random() < 0.45:
            self.app.emit("log", {"key": "dt_slide"})
        try:
            self.set_move_keys({"w", "shift"})
            if not self.anti_sleep(random.uniform(0.62, 1.08)):
                return True
            if self._can_act() and random.random() < 0.60:
                base = max(100, int(self.app.live("turn_px")))
                drift = int(round(base * random.uniform(0.04, 0.12))) * random.choice((-1, 1))
                if not self.smooth_mouse_move(drift, 0, duration=random.uniform(0.16, 0.26)):
                    return True

            # Initiate slide while holding W+Shift, then ease out of Shift into slide glide
            self.tap_key("ctrl", hold_s=random.uniform(0.06, 0.10))
            self.set_move_keys({"w"})
            slide_dx = random.randint(45, 165) * random.choice((-1, 1))
            if not self.smooth_mouse_move(slide_dx, 0, duration=random.uniform(0.24, 0.44)):
                return True
            if not self.anti_sleep(random.uniform(0.18, 0.34)):
                return True

            if allow_jump and random.random() < 0.88 and self._can_act():
                self.app.emit("detail", {"key": "dt_slide_jump"})
                self.tap_key("space", hold_s=random.uniform(0.055, 0.095))
                if self._can_act():
                    self.set_move_keys({"w", random.choice(("a", "d"))})
                    self.anti_sleep(random.uniform(0.20, 0.36))
            elif self._can_act():
                # Ride out the slide momentum before toggling out so posture returns to standing cleanly
                if self.anti_sleep(random.uniform(0.55, 0.85)) and self._can_act():
                    self.tap_key("ctrl", hold_s=0.055)
                    self.anti_sleep(random.uniform(0.10, 0.22))
        finally:
            if self._can_act():
                self.set_move_keys(set())
            else:
                self.release_all()
        return True

    def do_combat_wiggle(self) -> bool:
        """Rapid alternating left/right strafe dodge with horizontal counter-aim ticks."""
        if not self._can_act():
            return False
        self.center_cursor()
        self.app.emit("detail", {"key": "dt_wiggle"})
        side = random.choice((-1, 1))
        steps = random.randint(3, 5)
        try:
            for idx in range(steps):
                if not self._can_act():
                    break
                if side < 0:
                    keys = random.choice((("a",), ("w", "a"), ("s", "a")))
                else:
                    keys = random.choice((("d",), ("w", "d"), ("s", "d")))
                self.set_move_keys(set(keys))
                if random.random() < 0.70 and self._can_act():
                    with self.lock:
                        if self._can_act():
                            send_mouse_rel(-side * random.randint(10, 32), 0)
                if not self.anti_sleep(random.uniform(0.12, 0.28)):
                    break
                if idx < steps - 1 and random.random() < 0.28:
                    self.set_move_keys(set())
                    if not self.anti_sleep(random.uniform(0.05, 0.11)):
                        break
                side = -side
        finally:
            if self._can_act():
                self.set_move_keys(set())
            else:
                self.release_all()
        return True

    def do_crouch_peek(self, allow_strafe: bool = True) -> bool:
        """Toggle crouch cleanly with either brief cover strafe or double crouch-peek."""
        if not self._can_act():
            return False
        self.center_cursor()
        if "shift" in self.held_keys:
            self.set_move_keys(self.held_keys - {"shift"})
        did_move = False
        crouched = False
        try:
            self.tap_key("ctrl", hold_s=0.06)
            crouched = True
            if allow_strafe and self._can_act() and random.random() < 0.72:
                did_move = True
                self.app.emit("detail", {"key": "dt_crouch_strafe"})
                strafe_keys = random.choice((("a",), ("d",), ("w", "a"), ("w", "d"), ("s",)))
                self.set_move_keys(set(strafe_keys))
                ok = self.smooth_mouse_move(
                    random.randint(35, 95) * random.choice((-1, 1)),
                    0,
                    duration=random.uniform(0.22, 0.38),
                )
                if ok:
                    self.anti_sleep(random.uniform(0.32, 0.78))
                self.set_move_keys(set())
            else:
                self.app.emit("detail", {"key": "dt_crouch"})
                if self.anti_sleep(random.uniform(0.26, 0.58)) and random.random() < 0.35 and self._can_act():
                    # Second quick crouch-uncrouch peek pulse
                    self.tap_key("ctrl", hold_s=0.055)
                    crouched = False
                    if self.anti_sleep(random.uniform(0.16, 0.32)) and self._can_act():
                        self.tap_key("ctrl", hold_s=0.055)
                        crouched = True
                        self.anti_sleep(random.uniform(0.20, 0.44))
            if crouched and self._can_act():
                self.tap_key("ctrl", hold_s=0.06)
                crouched = False
        finally:
            if crouched and self._can_act():
                self.tap_key("ctrl", hold_s=0.06)
                crouched = False
            if did_move:
                if self._can_act():
                    self.set_move_keys(set())
                else:
                    self.release_all()
        return did_move

    def do_rmb_peek(self) -> None:
        """Brief harmless right-click aim/ADS glance paired with horizontal camera tracking."""
        if self.mouse_down or self.app.live("mouse") or not self._can_act():
            return
        self.center_cursor()
        self.app.emit("detail", {"key": "dt_rmb_peek"})
        try:
            self.rmb_hold_set(True)
            dx = random.randint(24, 96) * random.choice((-1, 1))
            ok = self.smooth_mouse_move(dx, 0, duration=random.uniform(0.18, 0.36))
            if ok:
                self.anti_sleep(random.uniform(0.06, 0.16))
        finally:
            self.rmb_hold_set(False)

    def click(self, name: str, label: str, timeout: float | None = None) -> bool:
        start = time.monotonic()
        cooldown_s = 6.0 if name == "play_button" else (1.0 if name == "play_again" else 0.0)
        while not self.stop.is_set():
            if not self.check_target_window_active():
                if self.stop.is_set() or (timeout is not None and (time.monotonic() - start) >= timeout):
                    return False
                time.sleep(0.2)
                continue
            if cooldown_s > 0.0 and (time.monotonic() - self._last_button_click_ts.get(name, -999.0)) < cooldown_s:
                if timeout is not None and (time.monotonic() - start) >= timeout:
                    return False
                time.sleep(0.2)
                continue
            gray = self.frame()
            if gray is None:
                if timeout is not None and (time.monotonic() - start) >= timeout:
                    return False
                time.sleep(0.2)
                continue
            _, box = self.matcher.find(gray, name, stop_event=self.stop)
            if box is not None:
                if name == "play_button":
                    # Move cursor to center first and verify Play did not just switch to Cancel from a manual click
                    self.center_cursor()
                    time.sleep(0.30)
                    if self.stop.is_set() or not self.check_target_window_active():
                        return False
                    gray2 = self.frame()
                    if gray2 is None:
                        continue
                    _, box2 = self.matcher.find(gray2, name, stop_event=self.stop)
                    if box2 is None:
                        if timeout is not None and (time.monotonic() - start) >= timeout:
                            return False
                        time.sleep(0.16)
                        continue
                    box = box2
                    # Before clicking Play in the lobby, ensure Squads + Team Fill is active (if a mode pill is present)
                    if self.ensure_squad_fill_in_lobby(gray2, play_box=box):
                        poll_end = time.monotonic() + 2.5
                        box3 = None
                        while not self.stop.is_set() and time.monotonic() < poll_end:
                            time.sleep(0.18)
                            gray3 = self.frame()
                            if gray3 is None:
                                continue
                            _, box3 = self.matcher.find(gray3, name, stop_event=self.stop)
                            if box3 is not None:
                                box = box3
                                break
                        if box3 is None:
                            continue
                elif name == "play_again":
                    # Release movement keys and let post-match slide-in animation settle before clicking
                    with self.lock:
                        self.release_all()
                    time.sleep(0.18)
                    if self.stop.is_set() or not self.check_target_window_active():
                        return False
                    gray2 = self.frame()
                    if gray2 is not None:
                        _, box2 = self.matcher.find(gray2, name, stop_event=self.stop)
                        if box2 is not None:
                            box = box2
                x, y, w, h = box
                px = self.monitor["left"] + x + w // 2
                py = self.monitor["top"] + y + h // 2
                self.enter_busy()
                try:
                    clicked = False
                    with self.lock:
                        if self.check_target_window_active():
                            self.release_all()
                            click_screen_pos(px, py)
                            self.center_cursor()
                            now_click = time.monotonic()
                            self._last_button_click_ts[name] = now_click
                            self.lmb_safe_after = max(self.lmb_safe_after, now_click + 7.5)
                            self.next_swing = max(self.next_swing, now_click + random.uniform(7.5, 11.0))
                            self.app.emit("detail", f"{self.app.tr('dt_clicked')}{label}")
                            self.app.emit("log", f"{self.app.tr('dt_clicked')}{label}")
                            clicked = True
                    if not clicked:
                        time.sleep(0.15)
                        continue
                    if not self.stop.is_set():
                        time.sleep(0.65)
                finally:
                    self.exit_busy()
                return True
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False
            time.sleep(0.16)
        return False

    def _pick_human_move(self, prev_tag: str) -> tuple[str, set[str], float]:
        choices = [
            ("w", {"w"}, (1.0, 2.9), 21),
            ("w+shift", {"w", "shift"}, (0.85, 2.1), 13),
            ("w+a+shift", {"w", "a", "shift"}, (0.7, 1.5), 6),
            ("w+d+shift", {"w", "d", "shift"}, (0.7, 1.5), 6),
            ("w+a", {"w", "a"}, (0.85, 2.3), 12),
            ("w+d", {"w", "d"}, (0.85, 2.3), 12),
            ("a", {"a"}, (0.55, 1.65), 11),
            ("d", {"d"}, (0.55, 1.65), 11),
            ("s", {"s"}, (0.4, 1.05), 5),
            ("s+a", {"s", "a"}, (0.45, 1.15), 3),
            ("s+d", {"s", "d"}, (0.45, 1.15), 3),
            ("pause", set(), (0.28, 1.65), 8),
        ]
        pool = [c for c in choices if c[0] != prev_tag]
        weights = [c[3] for c in pool]
        tag, keys, dur_rng, _ = random.choices(pool, weights=weights, k=1)[0]
        return tag, set(keys), random.uniform(*dur_rng)

    def anti_loop(self) -> None:
        """Humanized Anti-AFK loop reading live settings dynamically."""
        method = int(self.app.live("method"))
        afk_active = bool(self.app.live("immediate") or method == 0)
        blocked_until_reconnect = False
        connecting_was_absent = True

        wstate = "init"
        wend = time.monotonic() + 0.4
        wstate_prev = None
        move_tag = ""
        move_steps_count = 0
        next_vision_check = 0.0
        action_visible = False

        try:
            if self.is_target_focused() and not self.busy.is_set():
                self.center_cursor()
            with mss.MSS() as local_cap:
                while not self.stop.is_set():
                    use_imm = bool(self.app.live("immediate"))
                    use_human = bool(self.app.live("human"))
                    use_swing = bool(self.app.live("swing"))
                    use_mouse = bool(self.app.live("mouse"))
                    use_space = bool(self.app.live("space"))
                    use_walk = bool(self.app.live("walk"))
                    use_stand = bool(self.app.live("stand"))
                    use_safe = bool(self.app.live("safe"))

                    if not (use_human or use_swing or use_space or use_walk or use_mouse):
                        self.release_all()
                        time.sleep(0.2)
                        continue

                    if self.busy.is_set():
                        self.release_all()
                        time.sleep(0.08)
                        continue

                    if not self.check_target_window_active():
                        self.release_all()
                        if self.stop.is_set():
                            break
                        time.sleep(0.16)
                        continue

                    now = time.monotonic()
                    if method == 0:
                        action_visible = False
                    elif now >= next_vision_check:
                        next_vision_check = now + 0.85
                        gray = self.frame(local_cap) if self.is_target_focused() else None
                        if method == 1:
                            buttons = ["play_again", "return_lobby", "play_button"] if use_safe else ["play_again", "return_lobby"]
                        else:
                            buttons = ["play_button", "menu_button", "return_lobby", "esc_gotovo"]

                        action_visible = False
                        if gray is not None:
                            for bname in buttons:
                                _, bbox = self.matcher.find(gray, bname, stop_event=self.stop)
                                if bbox is not None or self.stop.is_set():
                                    action_visible = (bbox is not None)
                                    break

                        if gray is not None and not use_imm and not self.stop.is_set():
                            _, cbox = self.matcher.find(gray, "connecting", 0.72, stop_event=self.stop)
                            connecting_now = cbox is not None
                            if not connecting_now:
                                connecting_was_absent = True
                            elif connecting_was_absent:
                                connecting_was_absent = False
                                afk_active = True
                                blocked_until_reconnect = False
                                self.app.emit("log", {"key": "log_conn"})

                    if action_visible:
                        self.release_all()
                        self.center_cursor()
                        now_vis = time.monotonic()
                        self.lmb_safe_after = max(self.lmb_safe_after, now_vis + 7.0)
                        self.next_swing = max(self.next_swing, now_vis + random.uniform(7.0, 10.5))
                        if not use_imm and method != 0:
                            afk_active = False
                            blocked_until_reconnect = True
                        time.sleep(0.22)
                        continue

                    if use_imm or method == 0:
                        afk_active = True
                        blocked_until_reconnect = False

                    if not afk_active or blocked_until_reconnect or not self.check_target_window_active():
                        self.release_all()
                        if self.stop.is_set():
                            break
                        time.sleep(0.16)
                        continue

                    now = time.monotonic()
                    if now >= self.next_recenter:
                        self.center_cursor()
                        self.next_recenter = now + 1.2

                    # 1. Pickaxe hold or randomized human swings (guarded by lmb_safe_after & centered cursor)
                    if now < self.lmb_safe_after:
                        self.mouse_hold_set(False)
                    elif use_mouse:
                        if not self.mouse_down:
                            self.center_cursor()
                            self.mouse_hold_set(True)
                            self.app.emit("detail", {"key": "dt_mouse_hold"})
                    else:
                        self.mouse_hold_set(False)
                        if use_swing and now >= self.next_swing:
                            self.center_cursor()
                            self.do_pickaxe_swing(allow_jump=use_space)
                            self.next_swing = time.monotonic() + self._next_rhythm_delay(2.8, 10.5)

                    # 2. Random jumps (Space)
                    now = time.monotonic()
                    if use_space and now >= self.next_space:
                        if self._can_act():
                            self.tap_key("space", hold_s=random.uniform(0.055, 0.11))
                            self.app.emit("detail", {"key": "dt_space"})
                            self.app.emit("log", {"key": "dt_space"})
                        if random.random() < 0.22 and self.anti_sleep(random.uniform(0.72, 1.15)):
                            if self._can_act():
                                self.tap_key("space", hold_s=random.uniform(0.055, 0.10))
                        self.next_space = time.monotonic() + self._next_rhythm_delay(2.4, 10.5)

                    # 3. Anti-AFK camera look, micro-drift & non-periodic tactical maneuvers
                    if use_human:
                        now = time.monotonic()
                        is_standing = (wstate == "stand")
                        if now >= self.next_look:
                            self.human_look()
                            after_look = time.monotonic()
                            self.next_look = after_look + self._next_rhythm_delay(1.3, 4.2, burst_chance=0.26)
                            self.next_idle_drift = max(self.next_idle_drift, after_look + random.uniform(1.0, 2.4))
                        elif now >= self.next_idle_drift and (is_standing or move_tag == "pause"):
                            self.idle_micro_fidget()
                            self.next_idle_drift = time.monotonic() + random.uniform(1.2, 3.2)

                        now = time.monotonic()
                        if not is_standing and now >= self.next_slide:
                            self.do_slide_burst(allow_jump=use_space)
                            after = time.monotonic()
                            self.next_slide = after + self._next_rhythm_delay(10.0, 24.0)
                            wstate = "walk"
                            move_tag = ""
                            wend = after + random.uniform(0.05, 0.24)
                        elif not is_standing and now >= self.next_wiggle:
                            self.do_combat_wiggle()
                            after = time.monotonic()
                            self.next_wiggle = after + self._next_rhythm_delay(11.0, 26.0)
                            wstate = "walk"
                            move_tag = ""
                            wend = after + random.uniform(0.05, 0.24)
                        elif now >= self.next_crouch:
                            if self._can_act():
                                did_move = self.do_crouch_peek(allow_strafe=(not is_standing))
                                after = time.monotonic()
                                self.next_crouch = after + self._next_rhythm_delay(14.0, 34.0)
                                if did_move:
                                    wstate = "walk"
                                    move_tag = ""
                                    wend = after + random.uniform(0.06, 0.25)
                            else:
                                self.next_crouch = time.monotonic() + 2.0
                        elif now >= self.next_rmb_peek and not use_mouse and not self.mouse_down:
                            self.do_rmb_peek()
                            self.next_rmb_peek = time.monotonic() + self._next_rhythm_delay(13.0, 30.0)

                    # 4. Movement & turns
                    now = time.monotonic()
                    if use_human:
                        if wstate == "init" or now >= wend:
                            if wstate == "stand":
                                self.set_move_keys(set())
                                if use_walk:
                                    self.turn_around()
                            move_steps_count += 1
                            if use_walk and use_stand and move_steps_count >= random.randint(6, 10):
                                move_steps_count = 0
                                wstate = "stand"
                                self.set_move_keys(set())
                                wend = time.monotonic() + random.uniform(14.0, 22.0)
                                self.app.emit("detail", {"key": "dt_walk_stand"})
                                self.app.emit("log", {"key": "dt_walk_stand"})
                            else:
                                wstate = "walk"
                                move_tag, move_keys, dur = self._pick_human_move(move_tag)
                                self.set_move_keys(move_keys)
                                wend = time.monotonic() + dur
                                label_keys = None if not move_keys else "+".join(k.upper() for k in sorted(move_keys))
                                self.app.emit("detail", {"key": "dt_strafe", "keys": label_keys})
                    elif use_walk:
                        if wstate == "init" and now >= wend:
                            wstate = "walk"
                            wend = now + random.uniform(20.0, 45.0)
                            self.walk_hold(True)
                        elif wstate == "walk":
                            self.walk_hold(True)
                            if now >= self.next_strafe:
                                sk = random.choice(("a", "d"))
                                self.tap_key(sk, hold_s=random.uniform(0.10, 0.24))
                                if not self.busy.is_set() and self.is_target_focused():
                                    with self.lock:
                                        send_mouse_rel(random.choice((-28, 28)), 0)
                                self.next_strafe = now + random.uniform(4.5, 9.5)
                            if now >= wend:
                                self.walk_hold(False)
                                wstate = "stand" if use_stand else "turn"
                                wend = now + random.uniform(16.0, 24.0) if use_stand else now + random.uniform(0.15, 0.35)
                        elif wstate == "stand":
                            self.walk_hold(False)
                            if now >= wend:
                                wstate = "turn"
                                wend = now + random.uniform(0.15, 0.35)
                        elif wstate == "turn":
                            self.walk_hold(False)
                            if now >= wend:
                                self.app.emit("detail", {"key": "dt_walk_turn"})
                                self.app.emit("log", {"key": "dt_walk_turn"})
                                if not self.busy.is_set() and self.is_target_focused():
                                    self.turn_around()
                                wstate = "walk"
                                wend = time.monotonic() + random.uniform(20.0, 48.0)
                                self.walk_hold(True)

                        if wstate != wstate_prev:
                            wstate_prev = wstate
                            if wstate == "walk":
                                self.app.emit("detail", {"key": "dt_walk_go"})
                                self.app.emit("log", {"key": "dt_walk_go"})
                            elif wstate == "stand":
                                self.app.emit("detail", {"key": "dt_walk_stand"})
                                self.app.emit("log", {"key": "dt_walk_stand"})
                    else:
                        self.set_move_keys(set())

                    time.sleep(0.06)
        except Exception as e:
            self.app.emit("error", str(e))
        finally:
            self.release_all()

    @staticmethod
    def _modal_team_and_fill_state(
        gray: np.ndarray | None,
        bgr: np.ndarray | None,
        gx: int,
        gy: int,
        gw_b: int,
        gh_b: int,
    ) -> tuple[bool, bool, bool]:
        """
        Inspect Team Size & Team Fill inside the open Mode Modal anchored at 'esc_gotovo'.
        Returns (solo_still_locked, fill_unlocked, fill_is_on).
        """
        if gray is None or gray.size == 0:
            return False, False, False
        fh, fw = gray.shape[:2]

        # 1. Check bottom line of Team Size ('ОДИНОЧКИ' right tail >= 0.11 vs blank after 'ОТРЯД' <= 0.08)
        hx0 = max(0, int(round(gx - 1.120 * gw_b)))
        hx1 = min(fw, max(hx0 + 1, int(round(gx - 0.770 * gw_b))))
        hy0 = max(0, int(round(gy - 5.920 * gh_b)))
        hy1 = min(fh, max(hy0 + 1, int(round(gy - 5.680 * gh_b))))
        odin_tail = float((gray[hy0:hy1, hx0:hx1] > 165).mean())

        # 2. Check bottom line of Team Fill label ('ЗАБЛОКИРОВАНО' is dim 0.000 vs 'ЗАПОЛНИТЬ'/'НЕ ЗАПОЛНЯТЬ' >= 0.17)
        tx0 = max(0, int(round(gx - 1.600 * gw_b)))
        tx1 = min(fw, max(tx0 + 1, int(round(gx - 0.370 * gw_b))))
        ty0 = max(0, int(round(gy - 4.460 * gh_b)))
        ty1 = min(fh, max(ty0 + 1, int(round(gy - 4.240 * gh_b))))
        lbl_white = float((gray[ty0:ty1, tx0:tx1] > 165).mean())

        ntx0 = max(0, int(round(gx - 0.835 * gw_b)))
        ntx1 = min(fw, max(ntx0 + 1, int(round(gx - 0.415 * gw_b))))
        ne_white = float((gray[ty0:ty1, ntx0:ntx1] > 165).mean())

        solo_still_locked = (odin_tail >= 0.110) and (lbl_white < 0.050)
        fill_unlocked = lbl_white >= 0.080

        # 3. Check Toggle Switch ON ('ЗАПОЛНИТЬ') vs OFF ('НЕ ЗАПОЛНЯТЬ')
        fx_rel = int(round(gx + 0.585 * gw_b))
        fy_rel = max(10, int(round(gy - 4.560 * gh_b)))
        pad_x = max(12, int(round(0.18 * gw_b)))
        pad_y = max(8, int(round(0.24 * gh_b)))
        sx0 = max(0, fx_rel - pad_x)
        sx1 = min(fw, max(sx0 + 1, fx_rel + pad_x))
        sy0 = max(0, fy_rel - pad_y)
        sy1 = min(fh, max(sy0 + 1, fy_rel + pad_y))

        fill_is_on = False
        if bgr is not None and bgr.shape[:2] == gray.shape[:2]:
            sw_bgr = bgr[sy0:sy1, sx0:sx1]
            if sw_bgr.size > 0:
                hsv = cv2.cvtColor(sw_bgr, cv2.COLOR_BGR2HSV)
                sat_ratio = float((hsv[:, :, 1] >= 45).mean())
                if sat_ratio >= 0.15:
                    yel = float(
                        ((hsv[:, :, 0] >= 18) & (hsv[:, :, 0] <= 42) & (hsv[:, :, 1] >= 80) & (hsv[:, :, 2] >= 120)).mean()
                    )
                    fill_is_on = (yel >= 0.14) and (ne_white < 0.040)
                    return solo_still_locked, fill_unlocked, fill_is_on

        if fill_unlocked:
            # Grayscale fallback when real text row is present: 'НЕ ЗАПОЛНЯТЬ' has bright tail >= 0.12
            fill_is_on = ne_white < 0.040
        else:
            sw_crop = gray[sy0:sy1, sx0:sx1]
            if sw_crop.size > 0:
                fill_is_on = float((sw_crop > 175).mean()) >= 0.20

        return solo_still_locked, fill_unlocked, fill_is_on

    def ensure_squad_fill_in_lobby(
        self,
        gray: np.ndarray | None = None,
        play_box: tuple[int, int, int, int] | None = None,
    ) -> bool:
        """
        Inspect the lobby Mode Pill above Play. If Solo ('Одиночки') or non-Squads mode is set,
        open the Mode Selection Modal, select Squads (4-player icon), wait for Team Fill to unlock,
        enable 'ЗАПОЛНИТЬ' only if OFF, and reliably close the modal until 'esc_gotovo' disappears.
        """
        if self.stop.is_set() or not self.check_target_window_active():
            return False
        cur_gray = gray if gray is not None else self.frame()
        if cur_gray is None or cur_gray.size == 0:
            return False
        gh, gw = cur_gray.shape[:2]

        if play_box is None:
            _, play_box = self.matcher.find(cur_gray, "play_button", stop_event=self.stop)

        # Restrict search to the Mode Pill column above play_button when play_box is known
        search_img = cur_gray
        rx0, ry0 = 0, 0
        pill_has_ui = False
        if play_box is not None:
            bx, by, bw, bh = play_box
            rx0 = max(0, bx - bw // 6)
            ry0 = max(0, int(round(by - 2.45 * bh)))
            rx1 = min(gw, bx + int(round(bw * 1.18)))
            ry1 = min(gh, max(ry0 + 1, by - int(round(0.08 * bh))))
            if (ry1 - ry0) >= 36 and (rx1 - rx0) >= 80:
                search_img = cur_gray[ry0:ry1, rx0:rx1]
                pmy0 = max(0, int(round(by - 1.95 * bh)))
                pmy1 = min(gh, max(pmy0 + 1, int(round(by - 1.08 * bh))))
                pmx0 = max(0, bx)
                pmx1 = min(gw, bx + bw)
                if (pmy1 - pmy0) >= 20 and (pmx1 - pmx0) >= 60:
                    pill_crop = cur_gray[pmy0:pmy1, pmx0:pmx1]
                    pill_has_ui = float(pill_crop.std()) > 22.0

        cur_sc = float(cur_gray.shape[0]) / 1080.0
        is_roi = search_img is not cur_gray
        sq_score, sq_box = self.matcher.find(
            search_img, "mode_squad_fill", threshold=0.78, stop_event=self.stop, expected_scale=cur_sc, is_roi=is_roi
        )
        so_score, so_box = self.matcher.find(
            search_img, "mode_solo", threshold=0.76, stop_event=self.stop, expected_scale=cur_sc, is_roi=is_roi
        )

        # 1. Already in Squads + Team Fill ('Отряд, Заполнить')
        if sq_box is not None and sq_score >= max(0.78, so_score + 0.05):
            return False

        # 2. If neither Solo nor a real Mode Pill UI was detected (e.g. minimal synthetic test canvas), do nothing
        if so_box is None and not pill_has_ui:
            return False

        # 3. Solo ('Одиночки') or non-Squads mode detected -> open Mode Selection Modal and switch to Squads + Fill
        self.enter_busy()
        try:
            self.app.emit("detail", {"key": "dt_fix_squad"})
            self.app.emit("log", {"key": "log_mode_solo_detected"})

            if so_box is not None:
                mx, my, mw, mh = so_box
                pill_px = self.monitor["left"] + rx0 + mx + mw // 2
                pill_py = self.monitor["top"] + ry0 + my + mh // 2
            elif play_box is not None:
                bx, by, bw, bh = play_box
                pill_px = self.monitor["left"] + bx + bw // 2
                pill_py = self.monitor["top"] + max(10, int(round(by - 1.505 * bh)))
            else:
                return False

            with self.lock:
                if not self.check_target_window_active():
                    return False
                self.release_all()
                click_screen_pos(pill_px, pill_py)
                self.center_cursor()

            # Wait up to 4.5s for Mode Selection Modal ('esc_gotovo') to appear
            modal_deadline = time.monotonic() + 4.5
            g_box = None
            gray_m = None
            bgr_m = None
            while not self.stop.is_set() and time.monotonic() < modal_deadline:
                if not self.check_target_window_active():
                    return False
                time.sleep(0.22)
                fc = self.frame_color()
                if fc is None:
                    continue
                gray_m, bgr_m = fc
                _, g_box = self.matcher.find(gray_m, "esc_gotovo", threshold=0.75, stop_event=self.stop)
                if g_box is not None:
                    break

            if g_box is None:
                return False

            # Let modal slide-in animation finish and refresh anchor box
            time.sleep(0.25)
            fc2 = self.frame_color()
            if fc2 is not None:
                _, g_box2 = self.matcher.find(fc2[0], "esc_gotovo", threshold=0.75, stop_event=self.stop)
                if g_box2 is not None:
                    g_box = g_box2
                    gray_m, bgr_m = fc2

            gx, gy, gw_b, gh_b = g_box
            # Click 4-player Squads ('ОТРЯД') icon and wait up to 2.2s for Team Fill to unlock (never toggle while locked!)
            sq_px = self.monitor["left"] + int(round(gx + 0.860 * gw_b))
            sq_py = self.monitor["top"] + max(10, int(round(gy - 6.000 * gh_b)))
            with self.lock:
                if not self.check_target_window_active():
                    return False
                click_screen_pos(sq_px, sq_py)
                self.center_cursor()

            unlock_deadline = time.monotonic() + 2.2
            retried_squad = False
            gray_f, bgr_f = gray_m, bgr_m
            fill_is_on = False
            while not self.stop.is_set() and time.monotonic() < unlock_deadline:
                time.sleep(0.16)
                if not self.check_target_window_active():
                    return False
                fc_u = self.frame_color()
                if fc_u is None:
                    continue
                gray_f, bgr_f = fc_u
                solo_locked, fill_unlocked, fill_is_on = self._modal_team_and_fill_state(
                    gray_f, bgr_f, gx, gy, gw_b, gh_b
                )
                if not solo_locked and fill_unlocked:
                    break
                if not solo_locked and not fill_unlocked:
                    # Synthetic/non-Russian frame without bright label row: one extra settle wait suffices
                    break
                if not retried_squad and (unlock_deadline - time.monotonic()) < 1.1:
                    retried_squad = True
                    with self.lock:
                        if self.check_target_window_active():
                            click_screen_pos(sq_px, sq_py)
                            self.center_cursor()

            time.sleep(0.16)
            fc_post = self.frame_color()
            if fc_post is not None:
                gray_f, bgr_f = fc_post
            _, _, fill_is_on = self._modal_team_and_fill_state(gray_f, bgr_f, gx, gy, gw_b, gh_b)

            # Toggle Team Fill ONLY if it is OFF ('НЕ ЗАПОЛНЯТЬ'), then wait up to 2.0s for 'ЗАПОЛНИТЬ' to confirm
            if not fill_is_on:
                fx_rel = int(round(gx + 0.585 * gw_b))
                fy_rel = max(10, int(round(gy - 4.560 * gh_b)))
                fill_px = self.monitor["left"] + fx_rel
                fill_py = self.monitor["top"] + fy_rel
                with self.lock:
                    if not self.check_target_window_active():
                        return False
                    click_screen_pos(fill_px, fill_py)
                    self.center_cursor()

                fill_deadline = time.monotonic() + 2.0
                while not self.stop.is_set() and time.monotonic() < fill_deadline:
                    time.sleep(0.16)
                    if not self.check_target_window_active():
                        return False
                    fc_chk = self.frame_color()
                    if fc_chk is None:
                        continue
                    _, _, fill_is_on = self._modal_team_and_fill_state(
                        fc_chk[0], fc_chk[1], gx, gy, gw_b, gh_b
                    )
                    if fill_is_on:
                        break
                time.sleep(0.16)

            # Close modal cleanly via Esc / 'ESC ГОТОВО' and VERIFY it actually closed
            done_px = self.monitor["left"] + gx + gw_b // 2
            done_py = self.monitor["top"] + gy + gh_b // 2
            modal_closed = False
            for close_try in range(3):
                if self.stop.is_set() or not self.check_target_window_active():
                    return False
                if close_try == 1:
                    with self.lock:
                        if self.check_target_window_active():
                            click_screen_pos(done_px, done_py)
                            self.center_cursor()
                else:
                    with self.lock:
                        if self.check_target_window_active():
                            self.tap_key("esc", hold_s=0.09)

                close_deadline = time.monotonic() + 1.4
                while not self.stop.is_set() and time.monotonic() < close_deadline:
                    time.sleep(0.20)
                    fc_c = self.frame_color()
                    if fc_c is None:
                        continue
                    _, still_modal = self.matcher.find(fc_c[0], "esc_gotovo", threshold=0.75, stop_event=self.stop)
                    if still_modal is None:
                        modal_closed = True
                        break
                if modal_closed:
                    break

            time.sleep(0.35)
            self.app.emit("log", {"key": "log_mode_squad_fixed"})
            return True
        finally:
            self.exit_busy()

    def return_to_lobby_from_match(self, gray: np.ndarray | None = None) -> bool:
        """
        Return from post-match screen (or in-match) to main lobby so lobby mode can be verified.
        Tries direct 'return_lobby' button first, then falls back to Esc -> menu_button -> return_lobby.
        """
        self.enter_busy()
        try:
            cur_gray = gray if gray is not None else self.frame()
            direct_lobby = None
            if cur_gray is not None:
                _, direct_lobby = self.matcher.find(cur_gray, "return_lobby", stop_event=self.stop)
            if direct_lobby is not None and self.click("return_lobby", "Return to Lobby", timeout=4.0):
                self.wait(3.0)
            else:
                with self.lock:
                    self.release_all()
                    if self.check_target_window_active():
                        send_key_hw("esc", True)
                        time.sleep(0.08)
                        send_key_hw("esc", False)
                self.wait(0.8)
                if not self.click("menu_button", "Menu", timeout=18.0):
                    if self.stop.is_set():
                        return False
                    self.app.emit("log", {"key": "log_retry_esc"})
                    with self.lock:
                        if self.check_target_window_active():
                            self.tap_key("esc", hold_s=0.08)
                    if not self.click("menu_button", "Menu", timeout=15.0):
                        return False
                if not self.click("return_lobby", "Return to Lobby", timeout=25.0):
                    return False
                self.wait(3.0)

            # Wait up to 35s for lobby ('play_button', 'mode_solo', or 'mode_squad_fill') to appear
            lobby_deadline = time.monotonic() + 35.0
            while not self.stop.is_set() and time.monotonic() < lobby_deadline:
                if not self.check_target_window_active():
                    if self.stop.is_set():
                        return False
                    time.sleep(0.25)
                    continue
                g_lob = self.frame()
                if g_lob is not None:
                    for bname in ("play_button", "mode_solo", "mode_squad_fill"):
                        _, bbox = self.matcher.find(g_lob, bname, stop_event=self.stop)
                        if bbox is not None:
                            return True
                time.sleep(0.35)
            return False
        finally:
            self.exit_busy()

    def method1(self) -> None:
        self.app.emit("status", "running")
        self.app.emit("detail", {"key": "dt_method1"})
        self.next_lobby_mode_check = time.monotonic() + random.uniform(*self.lobby_check_interval_range)
        while not self.stop.is_set():
            if not self.check_target_window_active():
                if self.stop.is_set():
                    break
                time.sleep(0.25)
                continue
            gray = self.frame()
            if gray is None:
                time.sleep(0.25)
                continue
            _, again = self.matcher.find(gray, "play_again")
            ret_lobby = None
            if again is None:
                _, ret_lobby = self.matcher.find(gray, "return_lobby")
            play = None
            if again is None and ret_lobby is None and self.app.live("safe"):
                _, play = self.matcher.find(gray, "play_button")
            if again is not None:
                self.enter_busy()
                try:
                    if time.monotonic() >= self.next_lobby_mode_check:
                        # Periodic 10-15 min check: instead of Play Again, return to lobby, verify Squads+Fill, and launch
                        self.app.emit("detail", {"key": "dt_check_mode"})
                        self.app.emit("log", {"key": "log_m1_lobby_check"})
                        if self.return_to_lobby_from_match(gray):
                            if self.click("play_button", "Play", timeout=12.0):
                                self.wait(7.5)
                        self.next_lobby_mode_check = time.monotonic() + random.uniform(*self.lobby_check_interval_range)
                    elif self.click("play_again", "Play Again", timeout=3.5):
                        self.wait(1.6)
                        if not self.stop.is_set() and self.check_target_window_active():
                            gray_recheck = self.frame()
                            if gray_recheck is not None:
                                _, still_again = self.matcher.find(gray_recheck, "play_again", stop_event=self.stop)
                                if still_again is not None and not self.stop.is_set():
                                    self.click("play_again", "Play Again", timeout=2.5)
                        self.wait(4.5)
                finally:
                    self.exit_busy()
            elif ret_lobby is not None:
                self.enter_busy()
                try:
                    self.app.emit("detail", {"key": "dt_check_mode"})
                    self.app.emit("log", {"key": "log_m1_lobby_check"})
                    if self.return_to_lobby_from_match(gray):
                        if self.click("play_button", "Play", timeout=12.0):
                            self.wait(7.5)
                    self.next_lobby_mode_check = time.monotonic() + random.uniform(*self.lobby_check_interval_range)
                finally:
                    self.exit_busy()
            elif play is not None:
                self.enter_busy()
                try:
                    if self.click("play_button", "Play", timeout=5.0):
                        self.next_lobby_mode_check = time.monotonic() + random.uniform(*self.lobby_check_interval_range)
                        self.wait(7.5)
                finally:
                    self.exit_busy()
            time.sleep(0.25)

    def method2(self) -> None:
        self.app.emit("status", "running")
        while not self.stop.is_set():
            self.app.emit("detail", {"key": "dt_method2"})
            if not self.click("play_button", "Play"):
                break
            lo = int(self.app.live("min"))
            hi = int(self.app.live("max"))
            if lo > hi:
                lo, hi = hi, lo
            end = time.monotonic() + random.uniform(lo * 60.0, hi * 60.0)
            while not self.stop.is_set() and time.monotonic() < end:
                if not self.check_target_window_active():
                    if self.stop.is_set():
                        break
                rem_min = max(1, int(math.ceil((end - time.monotonic()) / 60.0)))
                self.app.emit("detail", {"key": "dt_waiting", "m": rem_min})
                time.sleep(0.5)
            if self.stop.is_set():
                break

            self.enter_busy()
            try:
                with self.lock:
                    self.release_all()
                    if self.check_target_window_active():
                        send_key_hw("esc", True)
                        time.sleep(0.08)
                        send_key_hw("esc", False)
                self.wait(0.8)

                if not self.click("menu_button", "Menu", timeout=18.0):
                    if self.stop.is_set():
                        break
                    self.app.emit("log", {"key": "log_retry_esc"})
                    with self.lock:
                        if self.check_target_window_active():
                            self.tap_key("esc", hold_s=0.08)
                    if not self.click("menu_button", "Menu", timeout=15.0):
                        continue
                if not self.click("return_lobby", "Return to Lobby", timeout=25.0):
                    continue
                self.wait(3.0)
            finally:
                self.exit_busy()

    def wait(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self.stop.is_set() and time.monotonic() < end:
            if self._ever_focused and not self.check_target_window_active():
                break
            time.sleep(0.1)

    def _token_watch_loop(self) -> None:
        """Local-only background watcher that detects Pirate Token drops and sends a Telegram push."""
        if _LOCAL_TOKEN_NOTIFIER is None or not getattr(_LOCAL_TOKEN_NOTIFIER, "enabled", False):
            return
        if os.environ.get("PIRATE_HEADLESS") == "1":
            return
        try:
            with mss.MSS() as t_cap:
                while not self.stop.is_set():
                    if self.is_target_focused():
                        mon = self.current_monitor()
                        gray = self.frame(t_cap)
                        if gray is not None:
                            _LOCAL_TOKEN_NOTIFIER.check_and_notify(gray, app=self.app, cap=t_cap, monitor=mon)
                    time.sleep(0.75)
        except Exception:
            pass

    def run(self, method: int) -> None:
        try:
            self.app.emit("status", "starting")
            self.app.emit("detail", {"key": "dt_afk_wait" if method == 0 else "dt_wait_game"})
            self.wait(2.0 if method == 0 else 3.0)
            if self.stop.is_set():
                return

            now_start = time.monotonic()
            self.lmb_safe_after = max(self.lmb_safe_after, now_start + 6.5)
            self.next_swing = max(self.next_swing, now_start + random.uniform(6.5, 10.5))
            if self.is_target_focused():
                self._ever_focused = True
                self._monitor_focus_loss = True
                self.center_cursor()

            self.anti_thread = threading.Thread(target=self.anti_loop, daemon=True)
            self.anti_thread.start()
            if (
                _LOCAL_TOKEN_NOTIFIER is not None
                and getattr(_LOCAL_TOKEN_NOTIFIER, "enabled", False)
                and os.environ.get("PIRATE_HEADLESS") != "1"
            ):
                self.token_thread = threading.Thread(target=self._token_watch_loop, daemon=True)
                self.token_thread.start()

            if method == 0:
                self.app.emit("status", "running")
                part_keys = []
                if self.app.live("human"):
                    part_keys.append("m0_part_human")
                if self.app.live("swing"):
                    part_keys.append("m0_part_swing")
                if self.app.live("space"):
                    part_keys.append("m0_part_space")
                if self.app.live("walk"):
                    part_keys.append("m0_part_walk")
                if self.app.live("mouse"):
                    part_keys.append("m0_part_mouse")
                self.app.emit("detail", {"key": "dt_m0_summary", "parts": part_keys})
                grace_deadline = time.monotonic() + 3.0
                while not self.stop.is_set():
                    if time.monotonic() >= grace_deadline:
                        self._monitor_focus_loss = True
                    if not self.check_target_window_active() and self.stop.is_set():
                        break
                    time.sleep(0.25)
            elif method == 1:
                self.method1()
            elif method == 2:
                self.method2()
        except Exception as e:
            self.app.emit("error", str(e))
        finally:
            self.stop.set()
            self.release_all()
            if self.anti_thread is not None and self.anti_thread.is_alive():
                self.anti_thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Color & Font Utilities
# ---------------------------------------------------------------------------
def hexc(c: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % c


def clamp(v: float, a: float, b: float) -> float:
    return a if v < a else (b if v > b else v)


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = clamp(t, 0.0, 1.0)
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def register_private_fonts() -> None:
    """Register bundled fallback OTF fonts privately if Windows fonts are unavailable."""
    fdir = FONTS_DIR
    for own, _, _ in FONT_FILES.values():
        p = fdir / own
        if p.exists():
            try:
                gdi32.AddFontResourceExW(str(p), 0x10, 0)
            except Exception:
                pass


def font_candidates(weight: str) -> list[str]:
    own, var_win, win = FONT_FILES.get(weight, FONT_FILES["rg"])
    wd = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    c = [str(wd / var_win), str(FONTS_DIR / own), str(wd / win), str(wd / "segoeui.ttf")]
    c.append(str(wd / ("arialbd.ttf" if weight in ("sb", "bd") else "arial.ttf")))
    return c


# ---------------------------------------------------------------------------
# Layered Zero-Lag Obsidian UI Application (Pirate Token Farm)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "lang": "ru",
    "start_key": "f6",
    "stop_key": "f7",
    "method": 1,
    "safe": True,
    "immediate": True,
    "human": True,
    "swing": True,
    "mouse": False,
    "space": True,
    "walk": True,
    "stand": False,
    "any_win": False,
    "min": 8,
    "max": 10,
    "turn_px": 2000,
    "anim": True,
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        register_private_fonts()
        self.root = root
        self.root.title(APP_NAME)
        self.root.configure(bg=hexc(C_BG_BOT))
        self.root.resizable(False, False)

        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        self.S = clamp(dpi / 96.0, 1.0, 2.5)
        self.W = WIN_W
        self.Wp = int(round(self.W * self.S))

        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.busy_event = threading.Event()
        self.action_lock = threading.RLock()
        self.worker: threading.Thread | None = None
        self.engine: Engine | None = None
        self.running = False
        self.state = "ready"  # ready | starting | running | stopping

        self.cfg = dict(DEFAULTS)
        self._state_lock = threading.Lock()
        self.page = "main"      # main | set
        self.params_open = False
        self.undo_snap: dict | None = None
        self.capturing: str | None = None
        self.hotkeys: list = []
        self._vk_prev: dict[str, bool] = {}
        self._finished_at: float = 0.0

        self.detail_ref: str | dict = {"key": "dt_idle"}
        self.log: deque[tuple[str, str]] = deque(maxlen=2)

        # Animation state (runs ONLY during active transitions or live pulse -> 0% idle CPU)
        self.anim_jobs: dict[str, dict] = {}
        self.anim_running = False
        self._anim_after_id = None
        self._timer_1ms = False
        self._pending_geo_wh: tuple[int, int] | None = None
        self._geo_anim: tuple[int, int] | None = None
        self._slice_photos: list[ImageTk.PhotoImage] = []
        self._trans_photos: list[ImageTk.PhotoImage] = []
        self._grad_cache: dict[tuple[int, int], Image.Image] = {}
        self._text_cache: dict[tuple, tuple[Image.Image, ImageTk.PhotoImage]] = {}
        self._dyn_pil: dict[str, tuple[Image.Image, str, float, float]] = {}
        self._sub_scrims: dict[str, tuple[int, float]] = {}
        self._sub_bars: dict[str, tuple[float, float, float, float]] = {}
        self.fonts: dict[tuple, ImageFont.FreeTypeFont] = {}
        self.sprites: dict[str, ImageTk.PhotoImage] = {}
        self._pil_sprites: dict[str, Image.Image] = {}
        self.dyn_photos: dict[str, ImageTk.PhotoImage] = {}
        self._bg_photo: ImageTk.PhotoImage | None = None
        self._bg_item: int | None = None
        self._canvas_items: dict[str, int] = {}
        self._switch_items: dict[str, tuple[int, int, float, float]] = {}
        self._switch_pos: dict[str, tuple[float, float]] = {}
        self._chip_items: dict[str, tuple[int, int, int, str, str]] = {}
        self._radio_items: dict[int, int] = {}
        self._method_ys: dict[int, float] = {}
        self._hover_rects: dict[str, tuple[str, float, float, str, str]] = {}
        self._hover_items: dict[str, int] = {}
        self._hover_levels: dict[str, float] = {}
        self._sub_bounds: dict[str, tuple[float, float]] = {}
        self._params_bounds: tuple[float, float] = (0.0, 0.0)
        self._footer_y: float = 0.0
        self._params_x_sum: float = 0.0
        self._params_y_sum: float = 0.0
        self._hint_pos: tuple[float, float] = (0.0, 0.0)
        self._seg_pos: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self._chev_center: tuple[float, float] = (0.0, 0.0)
        self._chip_placements: list[tuple[str, float, float, float, float, str, bool]] = []

        self.regions: list[tuple[str, float, float, float, float, object]] = []
        self.hover_id: str | None = None
        self.scroll_y = 0.0
        self.total_h = 760.0
        self.view_h = 760.0
        self.last_headless_img: Image.Image | None = None
        self._headless_meta: dict = {}

        had_cfg = CONFIG.exists()
        self._load()
        if not had_cfg and not HEADLESS and system_reduced_motion():
            self.cfg["anim"] = False
        self.set_icon()
        self._bake_sprites()

        self.cv = tk.Canvas(
            self.root,
            width=self.Wp,
            height=680,
            bg=hexc(C_BG_BOT),
            highlightthickness=0,
            bd=0,
        )
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Motion>", self.on_move)
        self.cv.bind("<Leave>", self.on_leave)
        self.cv.bind("<Button-1>", self.on_click)
        self.root.bind_all("<MouseWheel>", self.on_wheel)

        self.add_log(self.tr("log_ready") + " · " + (self.tr("admin_ok") if is_admin() else self.tr("admin_no")))
        self.rebuild_ui(snap=True)
        self.place_window()
        self.dark_titlebar()
        self.bind_hotkeys()
        self.root.after(55, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------- Live Thread-Safe State & Config ----------------
    def live(self, key: str):
        with self._state_lock:
            return self.cfg.get(key)

    def set_cfg(self, key: str, val) -> None:
        with self._state_lock:
            self.cfg[key] = val

    def tr(self, k: str) -> str:
        lang = self.live("lang")
        return TEXT.get(lang, TEXT["ru"]).get(k, k)

    def emit(self, k: str, v: object) -> None:
        if k == "cmd" and isinstance(v, str):
            v = (v, time.monotonic())
        self.events.put((k, v))

    def ref(self, r: str | dict) -> str:
        if isinstance(r, dict):
            rkey = r.get("key", "")
            if rkey == "dt_m0_summary":
                parts = [self.tr(pk) for pk in r.get("parts", ())]
                return " + ".join(parts) if parts else "AFK"
            tpl = self.tr(rkey)
            if "m" in r:
                return tpl.format(m=r["m"])
            if "keys" in r:
                kval = r["keys"] if r["keys"] else self.tr("dt_pause")
                return tpl.format(keys=kval)
            return tpl
        return str(r)

    def add_log(self, msg: str) -> None:
        self.log.append((time.strftime("%H:%M:%S"), msg))

    def _load(self) -> None:
        try:
            if not CONFIG.exists():
                return
            d = json.loads(CONFIG.read_text(encoding="utf-8"))
            if d.get("lang") in ("ru", "en"):
                self.cfg["lang"] = d["lang"]
            for k in ("start_key", "stop_key"):
                if isinstance(d.get(k), str) and d[k].strip():
                    self.cfg[k] = d[k].strip().lower()
            # Backward compatibility: old no_method=True migrates cleanly to method=0
            if d.get("no_method"):
                self.cfg["method"] = 0
            elif d.get("method") in (0, 1, 2):
                self.cfg["method"] = int(d["method"])
            for bk in ("safe", "immediate", "human", "swing", "mouse", "space", "walk", "stand", "any_win"):
                if bk in d:
                    self.cfg[bk] = bool(d[bk])
            self.cfg["min"] = int(clamp(int(d.get("min", DEFAULTS["min"])), 1, 180))
            self.cfg["max"] = int(clamp(int(d.get("max", DEFAULTS["max"])), self.cfg["min"], 180))
            self.cfg["turn_px"] = int(clamp(int(d.get("turn_px", DEFAULTS["turn_px"])), 200, 20000))
            if "anim" in d:
                self.cfg["anim"] = bool(d["anim"])
            elif d.get("perf") == "off":
                self.cfg["anim"] = False
        except Exception:
            pass

    def save(self) -> None:
        try:
            with self._state_lock:
                snap = dict(self.cfg)
            snap["no_method"] = snap["method"] == 0
            tmp = CONFIG.with_suffix(".tmp")
            tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CONFIG)
        except Exception:
            pass

    # ---------------- Window Icon & Dark Titlebar ----------------
    def set_icon(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("piratetoken.farm.app")
        except Exception:
            pass
        try:
            ico = ASSETS / "icon.ico"
            if ico.exists():
                self.root.iconbitmap(default=str(ico))
        except Exception:
            pass

    def dark_titlebar(self) -> None:
        try:
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            dwm = ctypes.windll.dwmapi
            v = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
            col = ctypes.c_int(0x00130F0E)  # COLORREF 0x00BBGGRR matching #0E0F13
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(col), 4)
        except Exception:
            pass

    def place_window(self) -> None:
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ww = self.Wp
        wh = int(min(round(self.view_h * self.S), sh - 60))
        x = max(12, (sw - ww) // 2)
        y = max(12, (sh - wh) // 2 - 12)
        self.root.geometry(f"{ww}x{wh}+{x}+{y}")

    # ---------------- PIL Typography & Pre-Baked Sprites ----------------
    def fnt(self, size: float, w: str = "rg", opsz_dp: float | None = None) -> ImageFont.FreeTypeFont:
        op = clamp(opsz_dp if opsz_dp is not None else (size * 0.5 if size > 18.0 else size), 10.0, 32.0)
        key = (round(size * self.S, 1), w, round(op, 1))
        f = self.fonts.get(key)
        if f is None:
            px = max(9, int(round(size * self.S)))
            wght_map = {"rg": 400.0, "md": 530.0, "sb": 600.0, "bd": 660.0}
            for path in font_candidates(w):
                if Path(path).exists():
                    try:
                        cand = ImageFont.truetype(path, px)
                        if Path(path).name.lower() == "seguivar.ttf":
                            try:
                                cand.set_variation_by_axes([wght_map.get(w, 400.0), op])
                            except Exception:
                                pass
                        f = cand
                        break
                    except Exception:
                        pass
            if f is None:
                f = ImageFont.load_default()
            self.fonts[key] = f
        return f

    def text_w(self, font: ImageFont.FreeTypeFont, s: str) -> float:
        try:
            return float(font.getlength(s))
        except Exception:
            try:
                bb = font.getbbox(s)
                return float(bb[2] - bb[0])
            except Exception:
                return float(len(s) * 7)

    def _fit_text(self, text: str, size_dp: float, wt: str, max_w_dp: float) -> str:
        if not text or max_w_dp <= 20.0:
            return text
        ss = 2.0
        R = self.S * ss
        fn = self.fnt(size_dp * ss, wt, opsz_dp=size_dp)
        if self.text_w(fn, text) / R <= max_w_dp:
            return text
        ell = "…"
        lo, hi = 1, len(text)
        best_s = ell
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = text[:mid].rstrip() + ell
            if self.text_w(fn, cand) / R <= max_w_dp:
                best_s = cand
                lo = mid + 1
            else:
                hi = mid - 1
        return best_s

    def _text_sprite(self, text: str, size_dp: float, wt: str, col_rgb: tuple[int, int, int]) -> tuple[Image.Image, ImageTk.PhotoImage]:
        key = (text, round(size_dp, 1), wt, col_rgb, round(self.S, 2))
        cached = self._text_cache.pop(key, None)
        if cached is not None:
            self._text_cache[key] = cached
            return cached
        if not text:
            im = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
            ph = ImageTk.PhotoImage(im, master=self.root)
            res = (im, ph)
            self._text_cache[key] = res
            return res
        ss = 2.0
        R = self.S * ss
        fn = self.fnt(size_dp * ss, wt, opsz_dp=size_dp)
        try:
            bb = fn.getbbox(text, anchor="lm")
            bx0, by0, bx1, by1 = bb
        except Exception:
            bx0, by0, bx1, by1 = 0, -int(size_dp * R * 0.6), int(self.text_w(fn, text)), int(size_dp * R * 0.4)
        pad_x = max(2, -bx0 + int(round(2.5 * R)))
        w_r = max(4, bx1 - min(0, bx0) + int(round(5.0 * R)))
        h_r = max(8, int(math.ceil(size_dp * 1.48 * R)), (by1 - by0) + int(round(4.0 * R)))
        im_2x = Image.new("RGBA", (w_r, h_r), (0, 0, 0, 0))
        d = ImageDraw.Draw(im_2x)
        d.text((pad_x, h_r * 0.5), text, font=fn, fill=col_rgb + (255,), anchor="lm")
        w_1x = max(2, int(round(w_r / ss)))
        h_1x = max(4, int(round(h_r / ss)))
        im_1x = im_2x.resize((w_1x, h_1x), Image.Resampling.LANCZOS)
        ph = ImageTk.PhotoImage(im_1x, master=self.root)
        while len(self._text_cache) >= 256:
            self._text_cache.pop(next(iter(self._text_cache)), None)
        res = (im_1x, ph)
        self._text_cache[key] = res
        return res

    def _draw_rr(self, draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, r: float, fill=None, outline=None, lw: float = 1.0) -> None:
        x0, y0, x1, y1 = int(round(x)), int(round(y)), int(round(x + w)), int(round(y + h))
        rad = max(0, int(round(min(r, w * 0.5, h * 0.5))))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=rad, fill=fill, outline=outline, width=max(1, int(round(lw))))

    @staticmethod
    def _lerp_rgb(c1, c2, t: float) -> tuple[int, int, int]:
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        return (
            int(round(c1[0] + (c2[0] - c1[0]) * t)),
            int(round(c1[1] + (c2[1] - c1[1]) * t)),
            int(round(c1[2] + (c2[2] - c1[2]) * t)),
        )

    def _bake_sprites(self) -> None:
        """Render tiny anti-aliased reusable UI sprites once (0 allocations during interaction)."""
        ss = 2.0
        R = self.S * ss

        def reg_sprite(name: str, im_1x: Image.Image) -> None:
            self._pil_sprites[name] = im_1x
            self.sprites[name] = ImageTk.PhotoImage(im_1x, master=self.root)

        def alias_sprite(alias: str, target: str) -> None:
            self._pil_sprites[alias] = self._pil_sprites[target]
            self.sprites[alias] = self.sprites[target]

        def make_rr_sprite(name: str, w_dp: float, h_dp: float, r_dp: float, fill, border=None, lw_dp: float = 1.0) -> None:
            pw, ph = max(2, int(round(w_dp * self.S))), max(2, int(round(h_dp * self.S)))
            im = Image.new("RGBA", (int(round(pw * ss)), int(round(ph * ss))), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle(
                (int(lw_dp * R * 0.5), int(lw_dp * R * 0.5), im.width - 1 - int(lw_dp * R * 0.5), im.height - 1 - int(lw_dp * R * 0.5)),
                radius=max(1, int(round(r_dp * R))),
                fill=fill,
                outline=border,
                width=max(1, int(round(lw_dp * R))),
            )
            reg_sprite(name, im.resize((pw, ph), Image.Resampling.LANCZOS))

        def make_circle_sprite(name: str, d_dp: float, fill, ring=None, lw_dp: float = 1.5) -> None:
            p = max(4, int(round(d_dp * self.S)))
            im = Image.new("RGBA", (int(round(p * ss)), int(round(p * ss))), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            pad = int(round(lw_dp * R * 0.5)) if ring else 0
            d.ellipse((pad, pad, im.width - 1 - pad, im.height - 1 - pad), fill=fill, outline=ring, width=max(1, int(round(lw_dp * R))) if ring else 0)
            reg_sprite(name, im.resize((p, p), Image.Resampling.LANCZOS))

        # 17-step interpolated switch tracks and thumbs for 60 FPS smooth color + glide
        for i in range(17):
            t = i / 16.0
            trk_f = self._lerp_rgb(C_SWITCH_OFF, C_CTA_BG, t) + (255,)
            trk_b = self._lerp_rgb(C_BORDER_CTRL, C_CTA_BG, t) + (255,)
            make_rr_sprite(f"trk_{i}", 40, 22, 11, trk_f, trk_b, 1.0)
            thm_f = self._lerp_rgb(C_TX2, C_CTA_FG, t) + (255,)
            make_circle_sprite(f"thm_{i}", 16, thm_f)
        alias_sprite("trk_off", "trk_0")
        alias_sprite("trk_on", "trk_16")
        alias_sprite("thm_off", "thm_0")
        alias_sprite("thm_on", "thm_16")

        # 13-step interpolated radio frames (smooth ring brighten + soft dot scale)
        pr = max(8, int(round(18 * self.S)))
        for i in range(13):
            t = i / 12.0
            rim = Image.new("RGBA", (int(round(pr * ss)), int(round(pr * ss))), (0, 0, 0, 0))
            rd = ImageDraw.Draw(rim)
            bd = self._lerp_rgb(C_BORDER_CTRL, C_CTA_BG, t) + (255,)
            rd.ellipse(
                (int(1 * R), int(1 * R), rim.width - 1 - int(1 * R), rim.height - 1 - int(1 * R)),
                fill=C_SWITCH_OFF + (255,),
                outline=bd,
                width=max(1, int(round((1.5 + 0.1 * t) * R))),
            )
            if t > 0.02:
                cx_r = rim.width * 0.5
                max_dr = max(1.0, cx_r - 5 * R)
                dr = max(1.0, max_dr * (0.20 + 0.80 * t))
                dot_c = self._lerp_rgb(C_SWITCH_OFF, C_CTA_BG, min(1.0, 0.30 + 0.70 * t)) + (255,)
                rd.ellipse((cx_r - dr, cx_r - dr, cx_r + dr, cx_r + dr), fill=dot_c)
            reg_sprite(f"rad_{i}", rim.resize((pr, pr), Image.Resampling.LANCZOS))
        alias_sprite("rad_off", "rad_0")
        alias_sprite("rad_on", "rad_12")

        # Header RU/EN sliding thumb, crisp 2x LANCZOS labels & method active card glow
        cw = self.W - 32.0
        make_rr_sprite("seg_thumb", 37.0, 28.0, 6.0, C_CTRL_HOV + (255,), C_BORDER_ACT, 1.0)
        make_rr_sprite("method_act_bg", cw - 20.0, 46.0, 8.0, (175, 190, 225, 22), C_BORDER_ACT, 1.1)
        for lng_k, lbl_txt in (("ru", "RU"), ("en", "EN")):
            for st_tag, col_rgb in (("act", C_TX), ("dim", C_TX2)):
                pw_l, ph_l = max(16, int(round(34.0 * self.S))), max(14, int(round(24.0 * self.S)))
                im_l = Image.new("RGBA", (int(round(pw_l * ss)), int(round(ph_l * ss))), (0, 0, 0, 0))
                dl = ImageDraw.Draw(im_l)
                fn_l = self.fnt(12.0 * ss, "sb", opsz_dp=12.0)
                dl.text((im_l.width * 0.5, im_l.height * 0.5), lbl_txt, font=fn_l, fill=col_rgb + (255,), anchor="mm")
                reg_sprite(f"seg_{lng_k}_{st_tag}", im_l.resize((pw_l, ph_l), Image.Resampling.LANCZOS))

        # 13-step choice chips with integrated 2x LANCZOS text (zero Win32 GDI Arial mismatch)
        chip_defs = (
            ("lmb_swing", "lmb_swings", 132.0, 24.0),
            ("lmb_hold", "lmb_hold", 108.0, 24.0),
            ("pace_norm", "pace_norm", 118.0, 24.0),
            ("pace_stand", "pace_stand", 104.0, 24.0),
            ("anim_on", "anim_on", 128.0, 26.0),
            ("anim_off", "anim_off", 88.0, 26.0),
        )
        for lng in ("ru", "en"):
            for cid, tkey, ch_w, ch_h in chip_defs:
                lbl = TEXT[lng][tkey]
                fn_c = self.fnt(12.0 * ss, "md", opsz_dp=12.0)
                pw, ph = max(2, int(round(ch_w * self.S))), max(2, int(round(ch_h * self.S)))
                for step in range(13):
                    t = step / 12.0
                    cf = self._lerp_rgb(C_SUNK, C_CTRL_HOV, t) + (255,)
                    cb = self._lerp_rgb(C_BORDER_CTRL, C_BORDER_ACT, t) + (255,)
                    ct = self._lerp_rgb(C_TX2, C_TX, t) + (255,)
                    im = Image.new("RGBA", (int(round(pw * ss)), int(round(ph * ss))), (0, 0, 0, 0))
                    d = ImageDraw.Draw(im)
                    d.rounded_rectangle(
                        (int(R * 0.5), int(R * 0.5), im.width - 1 - int(R * 0.5), im.height - 1 - int(R * 0.5)),
                        radius=max(1, int(round(6.0 * R))),
                        fill=cf,
                        outline=cb,
                        width=max(1, int(round(R))),
                    )
                    d.text((im.width * 0.5, im.height * 0.5), lbl, font=fn_c, fill=ct, anchor="mm")
                    reg_sprite(f"chip_{cid}_{lng}_{step}", im.resize((pw, ph), Image.Resampling.LANCZOS))

        # 9-step soft obsidian sub-bar muted scrims (when swing/walk switch is off)
        sub_rw = cw - 20.0
        for step in range(1, 9):
            a = int(round(168 * (step / 8.0)))
            make_rr_sprite(f"sub_scrim_{step}", sub_rw, 26.0, 6.0, C_CARD + (a,), None, 0.0)

        # Rounded CTA / Hotkey sprites matching footer/settings layout geometry
        stop_w = 148.0
        start_w = cw - stop_w - 12.0
        make_rr_sprite("cta_start_idle", start_w, 38.0, 9.0, C_CTA_BG + (255,), C_CTA_BG + (255,), 1.0)
        make_rr_sprite("cta_start_run", start_w, 38.0, 9.0, (91, 94, 102, 255), (91, 94, 102, 255), 1.0)
        make_rr_sprite("cta_stop_idle", stop_w, 38.0, 9.0, (18, 20, 25, 255), (50, 54, 64, 255), 1.0)
        make_rr_sprite("cta_stop_run", stop_w, 38.0, 9.0, C_CTRL + (255,), (120, 126, 140, 255), 1.0)
        make_rr_sprite("bind_idle", 74.0, 30.0, 7.0, C_CTRL + (255,), (104, 110, 125, 255), 1.0)
        make_rr_sprite("bind_cap", 74.0, 30.0, 7.0, C_CTA_BG + (255,), C_CTA_BG + (255,), 1.0)

        # 10-step soft hover highlight overlays
        def make_hover_set(prefix: str, w_dp: float, h_dp: float, r_dp: float, fill_alpha: int = 8, bd_alpha: int = 145, lw_dp: float = 1.0, bd_rgb=None) -> None:
            bcol = bd_rgb if bd_rgb is not None else C_BORDER_ACT[:3]
            for step in range(1, 11):
                frac = step / 10.0
                hf = (255, 255, 255, int(round(fill_alpha * frac)))
                hb = bcol + (int(round(bd_alpha * frac)),)
                make_rr_sprite(f"hov_{prefix}_{step}", w_dp, h_dp, r_dp, hf, hb, lw_dp)

        make_hover_set("row_46", cw - 20.0, 46.0, 8.0)
        make_hover_set("row_44", cw - 20.0, 44.0, 8.0)
        make_hover_set("row_42", cw - 20.0, 42.0, 8.0)
        make_hover_set("row_34", cw - 20.0, 34.0, 8.0)
        make_hover_set("mini_30", 30.0, 30.0, 7.0, fill_alpha=18, bd_alpha=185)
        make_hover_set("nav_btn", 96.0, 34.0, 8.0, fill_alpha=14, bd_alpha=180)
        make_hover_set("bind_btn", 74.0, 30.0, 7.0, fill_alpha=14, bd_alpha=190)
        make_hover_set("undo_btn", 82.0, 24.0, 6.0, fill_alpha=18, bd_alpha=190)
        make_hover_set("lang_half", 37.0, 28.0, 6.0, fill_alpha=10, bd_alpha=125)
        make_hover_set("cta_start", start_w, 38.0, 9.0, fill_alpha=32, bd_alpha=245, lw_dp=1.2, bd_rgb=(255, 255, 255))
        make_hover_set("cta_stop", stop_w, 38.0, 9.0, fill_alpha=14, bd_alpha=185, lw_dp=1.0)
        for ch_w, ch_h in ((132, 24), (108, 24), (118, 24), (104, 24), (128, 26), (88, 26)):
            make_hover_set(f"chip_{ch_w}_{ch_h}", float(ch_w), float(ch_h), 6.0, fill_alpha=12, bd_alpha=175)

        # 32-step cosine breathing pulse halo rings (fluid 42 FPS ring expansion, 0 idle CPU)
        p_size = max(12, int(round(22.0 * self.S)))
        for st_k, col_rgb in (("starting", C_RUN), ("running", C_RUN), ("stopping", C_STOP)):
            for step in range(32):
                t = step / 31.0
                e_t = 1.0 - (1.0 - t) ** 2.2
                pim = Image.new("RGBA", (int(round(p_size * ss)), int(round(p_size * ss))), (0, 0, 0, 0))
                pd = ImageDraw.Draw(pim)
                cx_p = pim.width * 0.5
                rad_p = (3.4 + 6.4 * e_t) * R
                alpha_p = int(round(195 * (1.0 - t) ** 1.45))
                if alpha_p > 0:
                    pd.ellipse(
                        (cx_p - rad_p, cx_p - rad_p, cx_p + rad_p, cx_p + rad_p),
                        outline=col_rgb + (alpha_p,),
                        width=max(1, int(round(1.25 * R))),
                    )
                reg_sprite(f"pulse_{st_k}_{step}", pim.resize((p_size, p_size), Image.Resampling.LANCZOS))

        # Rounded capsule status pills for RU & EN
        pill_styles = {
            "ready": (C_OK, (14, 36, 28, 255), (36, 115, 83, 255)),
            "running": (C_RUN, (16, 30, 51, 255), (54, 101, 161, 255)),
            "starting": (C_RUN, (16, 30, 51, 255), (54, 101, 161, 255)),
            "stopping": (C_STOP, (43, 20, 24, 255), (152, 65, 68, 255)),
        }
        for lng in ("ru", "en"):
            for st_key, (dot_c, bg_c, bd_c) in pill_styles.items():
                st_txt = TEXT[lng][f"st_{st_key}"]
                fn_2x = self.fnt(12.0 * ss, "md", opsz_dp=12.0)
                tw_dp = self.text_w(fn_2x, st_txt) / R
                pw_dp = tw_dp + 32.0
                ph_dp = 22.0
                pw, ph = max(8, int(round(pw_dp * self.S))), max(8, int(round(ph_dp * self.S)))
                pim = Image.new("RGBA", (int(round(pw * ss)), int(round(ph * ss))), (0, 0, 0, 0))
                pd = ImageDraw.Draw(pim)
                pd.rounded_rectangle(
                    (int(0.5 * R), int(0.5 * R), pim.width - 1 - int(0.5 * R), pim.height - 1 - int(0.5 * R)),
                    radius=max(2, int(round(11.0 * R))),
                    fill=bg_c,
                    outline=bd_c,
                    width=max(1, int(round(1.0 * R))),
                )
                dx0, dy0 = int(round(8.5 * R)), int(round(7.5 * R))
                dx1, dy1 = int(round(15.5 * R)), int(round(14.5 * R))
                pd.ellipse((dx0, dy0, dx1, dy1), fill=dot_c + (255,))
                pd.text((21.0 * R, ph_dp * 0.5 * R), st_txt, font=fn_2x, fill=dot_c + (255,), anchor="lm")
                reg_sprite(f"pill_{lng}_{st_key}", pim.resize((pw, ph), Image.Resampling.LANCZOS))

    # ---------------- Static Layer Cache & Dynamic Canvas Construction ----------------
    def _gradient_bg(self, w: int, h: int) -> Image.Image:
        cached = self._grad_cache.get((w, h))
        if cached is not None:
            return cached.copy()
        t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        r = (C_BG_TOP[0] + (C_BG_BOT[0] - C_BG_TOP[0]) * t).clip(0, 255).astype(np.uint8)
        g = (C_BG_TOP[1] + (C_BG_BOT[1] - C_BG_TOP[1]) * t).clip(0, 255).astype(np.uint8)
        b = (C_BG_TOP[2] + (C_BG_BOT[2] - C_BG_TOP[2]) * t).clip(0, 255).astype(np.uint8)
        col = np.dstack([r, g, b])
        arr = np.broadcast_to(col, (h, w, 3)).copy()
        im = Image.fromarray(arr, mode="RGB").convert("RGBA")
        if len(self._grad_cache) > 12:
            self._grad_cache.clear()
        self._grad_cache[(w, h)] = im
        return im.copy()

    def _set_timer_res(self, enable: bool) -> None:
        if HEADLESS or winmm is None:
            return
        if enable and not self._timer_1ms:
            try:
                winmm.timeBeginPeriod(1)
                self._timer_1ms = True
            except Exception:
                pass
        elif not enable and self._timer_1ms:
            try:
                winmm.timeEndPeriod(1)
                self._timer_1ms = False
            except Exception:
                pass

    def _set_root_wh(self, w_px: int, h_px: int) -> None:
        if HEADLESS:
            return
        cur_geo = self.root.geometry()
        parts = cur_geo.split("+")
        if len(parts) == 3:
            self.root.geometry(f"{w_px}x{h_px}+{parts[1]}+{parts[2]}")
        else:
            self.root.geometry(f"{w_px}x{h_px}")

    def _commit_pending_geo(self) -> None:
        """Apply final target window size once expand, collapse or page transition finishes."""
        wh = self._pending_geo_wh
        self._pending_geo_wh = None
        self._geo_anim = None
        if wh is not None and not HEADLESS:
            w_px, h_px = wh
            self.cv.configure(height=h_px)
            self._set_root_wh(w_px, h_px)

    def _place_dyn_text(
        self,
        key: str,
        text: str,
        x_dp: float,
        y_dp: float,
        size_dp: float,
        wt: str,
        col_rgb: tuple[int, int, int],
        anchor: str = "w",
        tags: tuple[str, ...] = ("layer_topbot_fg",),
    ) -> None:
        im_1x, ph = self._text_sprite(text, size_dp, wt, col_rgb)
        self.dyn_photos[key] = ph
        if anchor == "w":
            px_x = int(round((x_dp - 2.5) * self.S))
        elif anchor == "e":
            px_x = int(round((x_dp + 2.5) * self.S))
        else:
            px_x = int(round(x_dp * self.S))
        px_y = int(round(y_dp * self.S))
        self._canvas_items[key] = self.cv.create_image(px_x, px_y, anchor=anchor, image=ph, tags=tags)
        self._dyn_pil[key] = (im_1x, anchor, x_dp, y_dp)

    def _set_dyn_text(self, key: str, text: str, size_dp: float, wt: str, col_rgb: tuple[int, int, int]) -> None:
        iid = self._canvas_items.get(key)
        if not iid:
            return
        im_1x, ph = self._text_sprite(text, size_dp, wt, col_rgb)
        self.dyn_photos[key] = ph
        self.cv.itemconfigure(iid, image=ph)
        prev = self._dyn_pil.get(key)
        if prev is not None:
            self._dyn_pil[key] = (im_1x, prev[1], prev[2], prev[3])

    def _capture_switch_fracs(self) -> dict[str, float]:
        """Capture current visual progress [0.0..1.0] for every switch before rebuild_ui."""
        fracs: dict[str, float] = {}
        for skey, (_, thm_id, tx_off, tx_on) in self._switch_items.items():
            job = self.anim_jobs.get(f"sw:{skey}")
            if job is not None:
                fracs[skey] = float(job.get("cur_t", 1.0 if self.live(skey) else 0.0))
                continue
            try:
                cur_x_dp = self.cv.coords(thm_id)[0] / self.S
                span = max(1e-6, tx_on - tx_off)
                fracs[skey] = clamp((cur_x_dp - tx_off) / span, 0.0, 1.0)
            except Exception:
                fracs[skey] = 1.0 if self.live(skey) else 0.0
        return fracs

    def _snapshot_composite(self) -> Image.Image | None:
        """Return full 1x composite of the current frame for smooth transitions."""
        if not self._headless_meta or "base" not in self._headless_meta:
            return None
        return self.render_headless_preview()

    def rebuild_ui(self, snap: bool = False, anim_spec: dict | None = None) -> None:
        """Build cached obsidian base surface once for current page/accordion/language state."""
        self._commit_pending_geo()
        prev_view_h = float(self.view_h)
        if self._anim_after_id is not None:
            try:
                self.root.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None
        self.anim_jobs.clear()
        self.anim_running = False
        self._set_timer_res(False)

        self.regions.clear()
        self.cv.delete("all")
        self._canvas_items.clear()
        self.dyn_photos.clear()
        self._dyn_pil.clear()
        self._switch_items.clear()
        self._switch_pos.clear()
        self._chip_items.clear()
        self._chip_placements.clear()
        self._radio_items.clear()
        self._method_ys.clear()
        self._hover_rects.clear()
        self._hover_items.clear()
        self._hover_levels.clear()
        self._sub_bounds.clear()
        self._sub_bars.clear()
        self._sub_scrims.clear()
        self._slice_photos.clear()
        self._trans_photos.clear()
        self.hover_id = None

        lang = self.live("lang")
        method = int(self.live("method"))

        # Compute exact layout geometry (dp units) with comfortable vertical breathing room
        pad = 16.0
        cw = self.W - pad * 2
        header_h = 56.0
        footer_h = (118.0 if self.undo_snap is not None else 78.0)

        y = header_h + 9.0
        layout_blocks = []

        if self.page == "main":
            # Card 1: Game Methods + Optional Expanded Params
            m_pad = 10.0
            m_inner = cw - m_pad * 2
            m_y = y + m_pad + 21.0
            method_rects = []
            for mval, tk_t, tk_d in (
                (1, "m1_title", "m1_desc"),
                (2, "m2_title", "m2_desc"),
                (0, "m0_title", "m0_desc"),
            ):
                method_rects.append((mval, tk_t, tk_d, m_y, m_inner, 46.0))
                m_y += 46.0 + 6.0

            params_btn_y = m_y + 2.0
            params_btn_h = 34.0
            m_y = params_btn_y + params_btn_h
            params_box = None
            if self.params_open:
                p_row1_y = m_y + 6.0
                p_row2_y = p_row1_y + 46.0 + 6.0
                m_y = p_row2_y + 44.0
                params_box = (p_row1_y, p_row2_y)

            card1_h = (m_y - y) + m_pad
            layout_blocks.append(("methods", y, card1_h, method_rects, params_btn_y, params_btn_h, params_box))
            y += card1_h + 9.0

            # Card 2: Anti-AFK Behavior (inline sub-bars stay steady; smooth scrim dims when off)
            a_y = y + m_pad + 21.0
            afk_rows = []
            afk_defs = [
                ("immediate", "imm_title", "imm_desc", None),
                ("human", "human_title", "human_desc", None),
                ("swing", "swing_title", "swing_desc", "pickaxe"),
                ("space", "space_title", "space_desc", None),
                ("walk", "walk_title", "walk_desc", "pace"),
            ]
            for idx, (cfg_key, t_k, d_k, sub_kind) in enumerate(afk_defs):
                afk_rows.append((cfg_key, t_k, d_k, a_y, 42.0, sub_kind))
                a_y += 42.0
                if sub_kind:
                    a_y += 29.0
                if idx < len(afk_defs) - 1:
                    a_y += 5.0
            card2_h = (a_y - y) + m_pad
            layout_blocks.append(("afk", y, card2_h, afk_rows))
            y += card2_h + 9.0

            # Card 3: Live Status & Log
            card3_h = 74.0
            layout_blocks.append(("status", y, card3_h))
            y += card3_h + 9.0
        else:
            # Settings Page
            c1_h = 90.0
            layout_blocks.append(("perf", y, c1_h))
            y += c1_h + 12.0

            c2_h = 236.0
            layout_blocks.append(("calib", y, c2_h))
            y += c2_h + 12.0

            c3_h = 90.0
            layout_blocks.append(("about", y, c3_h))
            y += c3_h + 14.0

        footer_y = y
        self._footer_y = footer_y
        self.total_h = footer_y + footer_h
        sh = self.root.winfo_screenheight()
        max_dp_h = (sh - 60) / self.S
        self.view_h = min(self.total_h, max_dp_h)

        # Render static backdrop + card chrome ONCE at 2x AA -> downscale cleanly to 1x
        ss = 2.0
        R = self.S * ss
        Wr = int(round(self.Wp * ss))
        Hr = int(round(self.total_h * self.S * ss))
        base = self._gradient_bg(Wr, Hr)
        draw = ImageDraw.Draw(base, "RGBA")

        def dr_txt(x_dp: float, y_dp: float, s: str, sz: float, wt: str, col: tuple, anchor: str = "lm"):
            fn = self.fnt(sz * ss, wt, opsz_dp=sz)
            draw.text((x_dp * R, y_dp * R), s, font=fn, fill=col + (255,) if len(col) == 3 else col, anchor=anchor)

        def dr_box(x_dp: float, y_dp: float, w_dp: float, h_dp: float, rad_dp: float, fill, outline=None, lw: float = 1.0):
            x0, y0 = x_dp * R, y_dp * R
            x1, y1 = (x_dp + w_dp) * R, (y_dp + h_dp) * R
            draw.rounded_rectangle((x0, y0, x1, y1), radius=max(1, int(round(rad_dp * R))), fill=fill, outline=outline, width=max(1, int(round(lw * R))))

        # Header subtle hairline
        draw.line((0, int(header_h * R), Wr, int(header_h * R)), fill=C_BORDER_SUB, width=max(1, int(R)))
        dr_txt(pad, 19.0, APP_NAME, 16.0, "bd", C_TX, "lm")
        if APP_VERSION:
            title_w = self.text_w(self.fnt(16.0 * ss, "bd", opsz_dp=16.0), APP_NAME) / R
            dr_txt(pad + title_w + 8.0, 20.0, APP_VERSION, 11.5, "md", C_TX3, "lm")
        dr_txt(pad, 39.5, self.tr("sub"), 12.0, "rg", C_TX2, "lm")

        # Header segmented RU/EN pill track
        seg_x, seg_y, seg_w, seg_h = self.W - pad - 186.0, 11.0, 82.0, 34.0
        self._seg_pos = (seg_x, seg_y, seg_w, seg_h)
        dr_box(seg_x, seg_y, seg_w, seg_h, 9.0, C_SUNK + (255,), C_BORDER_CTRL)

        set_x, set_y, set_w, set_h = self.W - pad - 96.0, 11.0, 96.0, 34.0
        dr_box(set_x, set_y, set_w, set_h, 8.0, C_CTRL + (255,), C_BORDER_CTRL)
        set_label = self.tr("back") if self.page == "set" else self.tr("settings")
        dr_txt(set_x + set_w * 0.5, set_y + set_h * 0.5, set_label, 12.5, "md", C_TX, "mm")

        switch_placements: list[tuple[str, float, float]] = []
        radio_placements: list[tuple[int, float, float]] = []
        chip_placements: list[tuple[str, float, float, float, float, str, bool]] = []
        stepper_placements: list[tuple[str, float, float, str, int]] = []
        bind_placements: list[tuple[str, float, float]] = []
        hover_defs: list[tuple[str, str, float, float, float]] = []  # (rid, hov_prefix, x_dp, y_dp, group_y_dp)
        undo_btn_rect = None
        main_action_rects = None
        reset_rect = None

        hover_defs.append(("nav_set", "nav_btn", set_x, set_y, set_y))
        hover_defs.append(("lang_ru", "lang_half", seg_x + 3.0, seg_y + 3.0, seg_y))
        hover_defs.append(("lang_en", "lang_half", seg_x + 42.0, seg_y + 3.0, seg_y))

        for blk in layout_blocks:
            kind = blk[0]
            if kind == "methods":
                _, by, bh, m_rects, pbtn_y, pbtn_h, pbox = blk
                dr_box(pad, by, cw, bh, 13.0, C_CARD + (255,), C_BORDER_SUB)
                dr_txt(pad + 12.0, by + 18.0, self.tr("sec_methods"), 11.5, "sb", C_TX2, "lm")
                self._hint_pos = (pad + cw - 12.0, by + 18.0)

                for mval, tk_t, tk_d, ry, rw, rh in m_rects:
                    rx = pad + 10.0
                    self._method_ys[mval] = ry
                    dr_box(rx, ry, rw, rh, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                    radio_placements.append((mval, rx + 12.0, ry + 14.0))
                    dr_txt(rx + 38.0, ry + 15.0, self.tr(tk_t), 13.5, "md", C_TX, "lm")
                    dr_txt(rx + 38.0, ry + 32.5, self.tr(tk_d), 12.0, "rg", C_TX2, "lm")
                    hover_defs.append((f"m_{mval}", "row_46", rx, ry, ry))

                # Disclosure button: Method parameters
                px = pad + 10.0
                pw = cw - 20.0
                dr_box(px, pbtn_y, pw, pbtn_h, 8.0, C_SUNK + (255,), C_BORDER_CTRL)
                dr_txt(px + 12.0, pbtn_y + pbtn_h * 0.5, self.tr("params_title"), 12.5, "md", C_TX2, "lm")
                ptw = self.text_w(self.fnt(12.5 * ss, "md", opsz_dp=12.5), self.tr("params_title")) / R
                self._params_x_sum = px + 12.0 + ptw + 10.0
                self._params_y_sum = pbtn_y + pbtn_h * 0.5
                self._chev_center = (px + pw - 18.0, pbtn_y + pbtn_h * 0.5)
                self._params_bounds = (pbtn_y + pbtn_h + 2.0, pbtn_y + pbtn_h + 2.0 + 104.0)
                hover_defs.append(("params_btn", "row_34", px, pbtn_y, pbtn_y))

                if pbox is not None:
                    r1y, r2y = pbox
                    dr_box(px, r1y, pw, 46.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                    dr_txt(px + 12.0, r1y + 15.0, self.tr("delay_title"), 13.0, "md", C_TX, "lm")
                    dr_txt(px + 12.0, r1y + 32.5, self.tr("delay_desc"), 11.5, "rg", C_TX2, "lm")
                    s2_x = px + pw - 12.0 - 94.0
                    s1_x = s2_x - 16.0 - 94.0
                    dr_txt(s1_x + 102.0, r1y + 23.0, "–", 12.5, "md", C_TX3, "mm")
                    for skey, sx, sv in (("min", s1_x, int(self.live("min"))), ("max", s2_x, int(self.live("max")))):
                        dr_box(sx, r1y + 8.0, 94.0, 30.0, 7.0, C_CTRL + (255,), C_BORDER_CTRL)
                        dr_txt(sx + 15.0, r1y + 23.0, "−", 14.0, "bd", C_TX, "mm")
                        dr_txt(sx + 79.0, r1y + 23.0, "+", 14.0, "bd", C_TX, "mm")
                        stepper_placements.append((skey, sx, r1y + 8.0, skey, sv))
                        hover_defs.append((f"st_dec_{skey}", "mini_30", sx, r1y + 8.0, r1y + 8.0))
                        hover_defs.append((f"st_inc_{skey}", "mini_30", sx + 64.0, r1y + 8.0, r1y + 8.0))

                    dr_box(px, r2y, pw, 44.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                    dr_txt(px + 12.0, r2y + 14.5, self.tr("safe_title"), 13.0, "md", C_TX, "lm")
                    dr_txt(px + 12.0, r2y + 31.5, self.tr("safe_desc"), 11.5, "rg", C_TX2, "lm")
                    switch_placements.append(("safe", px + pw - 52.0, r2y + 11.0))
                    hover_defs.append(("sw_safe", "row_44", px, r2y, r2y))

            elif kind == "afk":
                _, by, bh, rows = blk
                dr_box(pad, by, cw, bh, 13.0, C_CARD + (255,), C_BORDER_SUB)
                dr_txt(pad + 12.0, by + 18.0, self.tr("sec_afk"), 11.5, "sb", C_TX2, "lm")
                dr_txt(pad + cw - 12.0, by + 18.0, self.tr("afk_safety"), 11.5, "rg", C_TX3, "rm")
                rx = pad + 10.0
                rw = cw - 20.0
                for cfg_k, t_k, d_k, ry, rh, sub in rows:
                    dr_box(rx, ry, rw, rh, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                    dr_txt(rx + 12.0, ry + 14.0, self.tr(t_k), 13.5, "md", C_TX, "lm")
                    dr_txt(rx + 12.0, ry + 30.0, self.tr(d_k), 11.5, "rg", C_TX2, "lm")
                    switch_placements.append((cfg_k, rx + rw - 52.0, ry + 10.0))
                    hover_defs.append((f"sw_{cfg_k}", "row_42", rx, ry, ry))
                    if sub == "pickaxe":
                        sy = ry + rh + 3.0
                        self._sub_bounds["swing"] = (ry + rh, sy + 26.0)
                        self._sub_bars["pickaxe"] = (rx, sy - 1.0, rw, 26.0)
                        draw.line((int((rx + 14.0) * R), int((sy + 2.0) * R), int((rx + 14.0) * R), int((sy + 22.0) * R)), fill=C_BORDER_CTRL, width=max(1, int(round(1.5 * R))))
                        dr_txt(rx + 26.0, sy + 12.0, self.tr("lmb_mode"), 11.5, "rg", C_TX2, "lm")
                        is_hold = bool(self.live("mouse"))
                        w_a, w_b = 132.0, 108.0
                        bx_b = rx + rw - w_b
                        bx_a = bx_b - 8.0 - w_a
                        chip_placements.append(("lmb_swing", bx_a, sy, w_a, 24.0, self.tr("lmb_swings"), not is_hold))
                        chip_placements.append(("lmb_hold", bx_b, sy, w_b, 24.0, self.tr("lmb_hold"), is_hold))
                        hover_defs.append(("lmb_swing", "chip_132_24", bx_a, sy, sy))
                        hover_defs.append(("lmb_hold", "chip_108_24", bx_b, sy, sy))
                    elif sub == "pace":
                        sy = ry + rh + 3.0
                        self._sub_bounds["walk"] = (ry + rh, sy + 26.0)
                        self._sub_bars["pace"] = (rx, sy - 1.0, rw, 26.0)
                        draw.line((int((rx + 14.0) * R), int((sy + 2.0) * R), int((rx + 14.0) * R), int((sy + 22.0) * R)), fill=C_BORDER_CTRL, width=max(1, int(round(1.5 * R))))
                        dr_txt(rx + 26.0, sy + 12.0, self.tr("pace_label"), 11.5, "rg", C_TX2, "lm")
                        is_st = bool(self.live("stand"))
                        w_a, w_b = 118.0, 104.0
                        bx_b = rx + rw - w_b
                        bx_a = bx_b - 8.0 - w_a
                        chip_placements.append(("pace_norm", bx_a, sy, w_a, 24.0, self.tr("pace_norm"), not is_st))
                        chip_placements.append(("pace_stand", bx_b, sy, w_b, 24.0, self.tr("pace_stand"), is_st))
                        hover_defs.append(("pace_norm", "chip_118_24", bx_a, sy, sy))
                        hover_defs.append(("pace_stand", "chip_104_24", bx_b, sy, sy))

            elif kind == "status":
                _, by, bh = blk
                dr_box(pad, by, cw, bh, 13.0, C_SUNK + (255,), C_BORDER_SUB)
                draw.line((int((pad + 12.0) * R), int((by + 36.0) * R), int((pad + cw - 12.0) * R), int((by + 36.0) * R)), fill=C_BORDER_SUB, width=max(1, int(R)))

            elif kind == "perf":
                _, by, bh = blk
                dr_box(pad, by, cw, bh, 13.0, C_CARD + (255,), C_BORDER_SUB)
                dr_txt(pad + 12.0, by + 18.0, self.tr("sec_perf"), 11.5, "sb", C_TX2, "lm")
                dr_txt(pad + cw - 12.0, by + 18.0, self.tr("perf_note"), 11.5, "rg", C_TX3, "rm")
                rx, rw, ry = pad + 10.0, cw - 20.0, by + 32.0
                dr_box(rx, ry, rw, 46.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                dr_txt(rx + 12.0, ry + 15.0, self.tr("anim_title"), 13.5, "md", C_TX, "lm")
                dr_txt(rx + 12.0, ry + 32.5, self.tr("anim_desc"), 11.5, "rg", C_TX2, "lm")
                anim_on = bool(self.live("anim"))
                c_off_x = rx + rw - 98.0
                c_on_x = c_off_x - 8.0 - 128.0
                chip_placements.append(("anim_off", c_off_x, ry + 10.0, 88.0, 26.0, self.tr("anim_off"), not anim_on))
                chip_placements.append(("anim_on", c_on_x, ry + 10.0, 128.0, 26.0, self.tr("anim_on"), anim_on))
                hover_defs.append(("anim_off", "chip_88_26", c_off_x, ry + 10.0, ry + 10.0))
                hover_defs.append(("anim_on", "chip_128_26", c_on_x, ry + 10.0, ry + 10.0))

            elif kind == "calib":
                _, by, bh = blk
                dr_box(pad, by, cw, bh, 13.0, C_CARD + (255,), C_BORDER_SUB)
                dr_txt(pad + 12.0, by + 18.0, self.tr("sec_input"), 11.5, "sb", C_TX2, "lm")
                rx, rw = pad + 10.0, cw - 20.0

                r1y = by + 32.0
                dr_box(rx, r1y, rw, 44.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                dr_txt(rx + 12.0, r1y + 14.5, self.tr("turn_title"), 13.5, "md", C_TX, "lm")
                dr_txt(rx + 12.0, r1y + 31.5, self.tr("turn_desc"), 11.5, "rg", C_TX2, "lm")
                sx = rx + rw - 110.0
                dr_box(sx, r1y + 7.0, 100.0, 30.0, 7.0, C_CTRL + (255,), C_BORDER_CTRL)
                dr_txt(sx + 16.0, r1y + 22.0, "−", 14.0, "bd", C_TX, "mm")
                dr_txt(sx + 84.0, r1y + 22.0, "+", 14.0, "bd", C_TX, "mm")
                stepper_placements.append(("turn_px", sx, r1y + 7.0, "turn_px", int(self.live("turn_px"))))
                hover_defs.append(("st_dec_turn_px", "mini_30", sx, r1y + 7.0, r1y + 7.0))
                hover_defs.append(("st_inc_turn_px", "mini_30", sx + 70.0, r1y + 7.0, r1y + 7.0))

                r2y = r1y + 50.0
                dr_box(rx, r2y, rw, 44.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                dr_txt(rx + 12.0, r2y + 14.5, self.tr("hk_start"), 13.5, "md", C_TX, "lm")
                dr_txt(rx + 12.0, r2y + 31.5, self.tr("hk_start_desc"), 11.5, "rg", C_TX2, "lm")
                bind_placements.append(("start", rx + rw - 84.0, r2y + 7.0))
                hover_defs.append(("bind_start", "bind_btn", rx + rw - 84.0, r2y + 7.0, r2y + 7.0))

                r3y = r2y + 50.0
                dr_box(rx, r3y, rw, 44.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                dr_txt(rx + 12.0, r3y + 14.5, self.tr("hk_stop"), 13.5, "md", C_TX, "lm")
                dr_txt(rx + 12.0, r3y + 31.5, self.tr("hk_stop_desc"), 11.5, "rg", C_TX2, "lm")
                bind_placements.append(("stop", rx + rw - 84.0, r3y + 7.0))
                hover_defs.append(("bind_stop", "bind_btn", rx + rw - 84.0, r3y + 7.0, r3y + 7.0))

                r4y = r3y + 50.0
                dr_box(rx, r4y, rw, 44.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                dr_txt(rx + 12.0, r4y + 14.5, self.tr("any_title"), 13.5, "md", C_TX, "lm")
                dr_txt(rx + 12.0, r4y + 31.5, self.tr("any_desc"), 11.5, "rg", C_TX2, "lm")
                switch_placements.append(("any_win", rx + rw - 52.0, r4y + 11.0))
                hover_defs.append(("sw_any_win", "row_44", rx, r4y, r4y))

            elif kind == "about":
                _, by, bh = blk
                dr_box(pad, by, cw, bh, 13.0, C_CARD + (255,), C_BORDER_SUB)
                dr_txt(pad + 12.0, by + 18.0, self.tr("sec_about"), 11.5, "sb", C_TX2, "lm")
                rx, rw, ry = pad + 10.0, cw - 20.0, by + 32.0
                dr_box(rx, ry, rw, 46.0, 8.0, C_SUNK + (255,), C_BORDER_SUB)
                dr_txt(rx + 12.0, ry + 15.0, self.tr("about_title"), 13.5, "md", C_TX, "lm")
                dr_txt(rx + 12.0, ry + 32.5, self.tr("about_desc"), 11.5, "rg", C_TX2, "lm")

        # Footer action strip
        draw.rectangle((0, int(footer_y * R), Wr, Hr), fill=C_FOOTER_BG + (255,))
        draw.line((0, int(footer_y * R), Wr, int(footer_y * R)), fill=C_BORDER_SUB, width=max(1, int(R)))

        act_y = footer_y + 10.0
        if self.undo_snap is not None:
            dr_box(pad, act_y, cw, 34.0, 8.0, C_CARD + (255,), C_BORDER_CTRL)
            dr_txt(pad + 12.0, act_y + 17.0, self.tr("undo_msg"), 12.0, "rg", C_TX, "lm")
            ux, uw = pad + cw - 92.0, 82.0
            dr_box(ux, act_y + 5.0, uw, 24.0, 6.0, C_CTRL + (255,), C_BORDER_CTRL)
            dr_txt(ux + uw * 0.5, act_y + 17.0, self.tr("undo_btn"), 11.5, "sb", C_TX, "mm")
            undo_btn_rect = (ux, act_y + 5.0, uw, 24.0)
            hover_defs.append(("undo", "undo_btn", ux, act_y + 5.0, act_y + 5.0))
            act_y += 42.0

        stop_w = 148.0
        start_w = cw - stop_w - 12.0
        main_action_rects = (pad, act_y, start_w, 38.0, pad + start_w + 12.0, act_y, stop_w, 38.0)
        hover_defs.append(("cta_start", "cta_start", pad, act_y, act_y))
        hover_defs.append(("cta_stop", "cta_stop", pad + start_w + 12.0, act_y, act_y))

        meta_y = act_y + 45.0
        rlab = self.tr("btn_reset")
        rw_px = self.text_w(self.fnt(12.0 * ss, "md", opsz_dp=12.0), rlab) / R
        dr_txt(pad, meta_y + 7.0, rlab, 12.0, "md", C_TX2, "lm")
        draw.line((int(pad * R), int((meta_y + 16.0) * R), int((pad + rw_px) * R), int((meta_y + 16.0) * R)), fill=C_BORDER_CTRL, width=max(1, int(R)))
        reset_rect = (pad - 4.0, meta_y - 4.0, rw_px + 8.0, 22.0)

        adm_txt = self.tr("admin_ok") if is_admin() else self.tr("admin_no")
        dr_txt(pad + cw, meta_y + 7.0, adm_txt, 11.5, "rg", C_TX3, "rm")

        base_1x = base.resize((self.Wp, int(round(self.total_h * self.S))), Image.Resampling.LANCZOS)
        if HEADLESS:
            self.last_headless_img = base_1x.copy()
        self._bg_photo = ImageTk.PhotoImage(base_1x, master=self.root)

        anim_enabled = bool(self.live("anim")) and not snap
        active_anim = anim_spec if (anim_enabled and anim_spec is not None) else None

        def _group_info(y_dp: float, is_hdr: bool = False) -> tuple[tuple[str, ...], str, str]:
            if is_hdr:
                return (("layer_hdr_fg",), "", "layer_hdr_fg")
            if active_anim is not None:
                ak = active_anim["kind"]
                if ak == "page":
                    grp = "ui_footer" if y_dp >= footer_y - 0.5 else "ui_body"
                    return ((grp, "layer_topbot_fg"), grp, "layer_topbot_fg")
                if ak == "lang":
                    grp = "ui_body" if y_dp >= header_h - 0.5 else "ui_hdr"
                    return ((grp, "layer_topbot_fg"), grp, "layer_topbot_fg")
                if ak == "expand":
                    sy0, sy1 = active_anim["split_y0"], active_anim["split_y1"]
                    if y_dp < sy0 - 0.5:
                        return (("ui_top", "layer_topbot_fg"), "ui_top", "layer_topbot_fg")
                    if y_dp < sy1 - 0.5:
                        return (("ui_mid", "layer_mid_fg"), "ui_mid", "layer_mid_fg")
                    return (("ui_bot", "layer_topbot_fg"), "ui_bot", "layer_topbot_fg")
                if ak == "collapse":
                    sy0 = active_anim["split_y0"]
                    grp = "ui_top" if y_dp < sy0 - 0.5 else "ui_bot"
                    return ((grp, "layer_topbot_fg"), grp, "layer_topbot_fg")
            return (("layer_topbot_fg",), "", "layer_topbot_fg")

        # Place sliced or single backdrop images so structural transitions glide cleanly
        if active_anim is None:
            self._bg_item = self.cv.create_image(0, 0, anchor="nw", image=self._bg_photo, tags=("layer_topbot_bg",))
        elif active_anim["kind"] == "page":
            hy = max(1, int(round(header_h * self.S)))
            fy = max(hy + 1, min(base_1x.height - 1, int(round(footer_y * self.S))))
            hdr_p = ImageTk.PhotoImage(base_1x.crop((0, 0, self.Wp, hy)), master=self.root)
            bdy_p = ImageTk.PhotoImage(base_1x.crop((0, hy, self.Wp, fy)), master=self.root)
            ftr_p = ImageTk.PhotoImage(base_1x.crop((0, fy, self.Wp, base_1x.height)), master=self.root)
            self._slice_photos.extend([hdr_p, bdy_p, ftr_p])
            self._bg_item = self.cv.create_image(0, 0, anchor="nw", image=hdr_p, tags=("layer_hdr_bg",))
            self.cv.create_image(0, hy, anchor="nw", image=bdy_p, tags=("ui_body", "layer_topbot_bg"))
            self.cv.create_image(0, fy, anchor="nw", image=ftr_p, tags=("ui_footer", "layer_topbot_bg"))
        elif active_anim["kind"] == "lang":
            hy = max(1, int(round(header_h * self.S)))
            hdr_p = ImageTk.PhotoImage(base_1x.crop((0, 0, self.Wp, hy)), master=self.root)
            bdy_p = ImageTk.PhotoImage(base_1x.crop((0, hy, self.Wp, base_1x.height)), master=self.root)
            self._slice_photos.extend([hdr_p, bdy_p])
            self._bg_item = self.cv.create_image(0, 0, anchor="nw", image=hdr_p, tags=("layer_hdr_bg",))
            self.cv.create_image(0, hy, anchor="nw", image=bdy_p, tags=("ui_body", "layer_topbot_bg"))
        elif active_anim["kind"] == "expand":
            sy0_px = max(1, min(base_1x.height - 2, int(round(active_anim["split_y0"] * self.S))))
            sy1_px = max(sy0_px + 1, min(base_1x.height - 1, int(round(active_anim["split_y1"] * self.S))))
            top_p = ImageTk.PhotoImage(base_1x.crop((0, 0, self.Wp, sy0_px)), master=self.root)
            mid_p = ImageTk.PhotoImage(base_1x.crop((0, sy0_px, self.Wp, sy1_px)), master=self.root)
            bot_p = ImageTk.PhotoImage(base_1x.crop((0, sy1_px, self.Wp, base_1x.height)), master=self.root)
            self._slice_photos.extend([top_p, mid_p, bot_p])
            self._bg_item = self.cv.create_image(0, 0, anchor="nw", image=top_p, tags=("ui_top", "layer_topbot_bg"))
            self.cv.create_image(0, sy0_px, anchor="nw", image=mid_p, tags=("ui_mid", "layer_mid_bg"))
            self.cv.create_image(0, sy1_px, anchor="nw", image=bot_p, tags=("ui_bot", "layer_topbot_bg"))
        elif active_anim["kind"] == "collapse":
            sy0_px = max(1, min(base_1x.height - 1, int(round(active_anim["split_y0"] * self.S))))
            top_p = ImageTk.PhotoImage(base_1x.crop((0, 0, self.Wp, sy0_px)), master=self.root)
            bot_p = ImageTk.PhotoImage(base_1x.crop((0, sy0_px, self.Wp, base_1x.height)), master=self.root)
            self._slice_photos.extend([top_p, bot_p])
            self._bg_item = self.cv.create_image(0, 0, anchor="nw", image=top_p, tags=("ui_top", "layer_topbot_bg"))
            mid_crop = active_anim.get("mid_crop")
            if mid_crop is not None:
                mid_p = ImageTk.PhotoImage(mid_crop, master=self.root)
                self._slice_photos.append(mid_p)
                self.cv.create_image(0, sy0_px, anchor="nw", image=mid_p, tags=("ui_mid", "layer_mid_bg"))
            self.cv.create_image(0, sy0_px, anchor="nw", image=bot_p, tags=("ui_bot", "layer_topbot_bg"))
        else:
            self._bg_item = self.cv.create_image(0, 0, anchor="nw", image=self._bg_photo, tags=("layer_topbot_bg",))

        for rid, prefix, hx, hy_dp, gy in hover_defs:
            _, grp, lay = _group_info(gy, is_hdr=(gy < header_h))
            self._hover_rects[rid] = (prefix, hx, hy_dp, grp, lay)

        # Register static clickable regions
        self.regions.append(("lang_ru", seg_x + 2, seg_y, seg_x + 40, seg_y + seg_h, lambda: self.set_lang("ru")))
        self.regions.append(("lang_en", seg_x + 40, seg_y, seg_x + seg_w, seg_y + seg_h, lambda: self.set_lang("en")))
        self.regions.append(("nav_set", set_x, set_y, set_x + set_w, set_y + set_h, self.toggle_page))
        if undo_btn_rect:
            ux, uy, uw, uh = undo_btn_rect
            self.regions.append(("undo", ux, uy, ux + uw, uy + uh, self.undo_reset))
        rx0, ry0, rw0, rh0 = reset_rect
        self.regions.append(("reset", rx0, ry0, rx0 + rw0, ry0 + rh0, self.reset_all))

        for blk in layout_blocks:
            if blk[0] == "methods":
                _, _, _, m_rects, pbtn_y, pbtn_h, pbox = blk
                for mval, _, _, ry, rw, rh in m_rects:
                    self.regions.append((f"m_{mval}", pad + 10.0, ry, pad + 10.0 + rw, ry + rh, lambda mv=mval: self.select_method(mv)))
                self.regions.append(("params_btn", pad + 10.0, pbtn_y, pad + cw - 10.0, pbtn_y + pbtn_h, self.toggle_params))
                if pbox is not None:
                    self.regions.append(("sw_safe", pad + 10.0, pbox[1], pad + cw - 10.0, pbox[1] + 44.0, lambda: self.flip("safe")))
            elif blk[0] == "afk":
                for cfg_k, _, _, ry, rh, _ in blk[3]:
                    self.regions.append((f"sw_{cfg_k}", pad + 10.0, ry, pad + cw - 10.0, ry + rh, lambda k=cfg_k: self.flip(k)))
            elif blk[0] == "status":
                self._status_y = blk[1]
            elif blk[0] == "calib":
                _, by, _ = blk
                self.regions.append(("sw_any_win", pad + 10.0, by + 32.0 + 150.0, pad + cw - 10.0, by + 32.0 + 194.0, lambda: self.flip("any_win")))

        # Header sliding RU/EN pill thumb & 2x LANCZOS labels
        seg_tx0 = seg_x + (3.0 if lang == "ru" else 42.0)
        self._canvas_items["seg_thumb"] = self.cv.create_image(
            int(round(seg_tx0 * self.S)), int(round((seg_y + 3.0) * self.S)),
            anchor="nw", image=self.sprites["seg_thumb"], tags=("layer_hdr_fg",),
        )
        self._canvas_items["seg_ru_tx"] = self.cv.create_image(
            int(round((seg_x + 21.5) * self.S)), int(round((seg_y + seg_h * 0.5) * self.S)),
            anchor="center", image=self.sprites[f"seg_ru_{'act' if lang == 'ru' else 'dim'}"], tags=("layer_hdr_fg",),
        )
        self._canvas_items["seg_en_tx"] = self.cv.create_image(
            int(round((seg_x + 60.5) * self.S)), int(round((seg_y + seg_h * 0.5) * self.S)),
            anchor="center", image=self.sprites[f"seg_en_{'act' if lang == 'en' else 'dim'}"], tags=("layer_hdr_fg",),
        )

        # Method card active highlight, hint, params summary & chevron
        if self.page == "main" and self._method_ys:
            m_y_act = self._method_ys.get(method, self._method_ys.get(1, header_h + 41.0))
            m_tags = _group_info(m_y_act)[0]
            self._canvas_items["method_act"] = self.cv.create_image(
                int(round((pad + 10.0) * self.S)), int(round(m_y_act * self.S)),
                anchor="nw", image=self.sprites["method_act_bg"], tags=m_tags,
            )
            hx_dp, hy_dp = self._hint_pos
            h_tags = _group_info(hy_dp)[0]
            self._place_dyn_text(
                "hint_method", self.tr("hint_afk") if method == 0 else self.tr("hint_auto"),
                hx_dp, hy_dp, 11.5, "rg", C_TX3, anchor="e", tags=h_tags,
            )
            ptags = _group_info(self._params_y_sum)[0]
            self._place_dyn_text("params_sum", "", self._params_x_sum, self._params_y_sum, 12.0, "rg", C_TX3, anchor="w", tags=ptags)
            cx0, cy0 = self._chev_center
            if self.params_open:
                cpts = ((cx0 - 4.0) * self.S, (cy0 + 2.0) * self.S, cx0 * self.S, (cy0 - 2.5) * self.S, (cx0 + 4.0) * self.S, (cy0 + 2.0) * self.S)
            else:
                cpts = ((cx0 - 4.0) * self.S, (cy0 - 2.0) * self.S, cx0 * self.S, (cy0 + 2.5) * self.S, (cx0 + 4.0) * self.S, (cy0 - 2.0) * self.S)
            self._canvas_items["params_chev"] = self.cv.create_line(
                *cpts, fill=hexc(C_TX2), width=max(1.5, 1.6 * self.S),
                capstyle="round", joinstyle="round", tags=ptags,
            )

        # Choice chips (baked 13-step 2x LANCZOS sprites)
        chip_map = {
            "lmb_swing": ("mouse", False),
            "lmb_hold": ("mouse", True),
            "pace_norm": ("stand", False),
            "pace_stand": ("stand", True),
            "anim_on": ("anim", True),
            "anim_off": ("anim", False),
        }
        self._chip_placements = list(chip_placements)
        for cid, cx, cy, ch_w, ch_h, _, pressed in chip_placements:
            cfg_k, active_val = chip_map[cid]
            tags = _group_info(cy)[0]
            step = 12 if pressed else 0
            bg_id = self.cv.create_image(
                int(round(cx * self.S)), int(round(cy * self.S)),
                anchor="nw", image=self.sprites[f"chip_{cid}_{lang}_{step}"], tags=tags,
            )
            self._chip_items[cid] = (bg_id, int(ch_w), int(ch_h), f"chip_{cid}_{lang}", f"{cfg_k}:{int(active_val)}")
            self.regions.append((cid, cx, cy, cx + ch_w, cy + ch_h, lambda ck=cfg_k, av=active_val: self.set_bool(ck, av)))

        # Inline sub-bar dimmed scrims (above chips when swing/walk switch is off)
        for sub_k, (sbx, sby, _, _) in self._sub_bars.items():
            parent_on = bool(self.live("swing" if sub_k == "pickaxe" else "walk"))
            sc_step = 0 if parent_on else 8
            sc_tags = _group_info(sby)[0]
            sid = self.cv.create_image(
                int(round(sbx * self.S)), int(round(sby * self.S)),
                anchor="nw",
                image=self.sprites[f"sub_scrim_{max(1, sc_step)}"],
                state="hidden" if sc_step <= 0 else "normal",
                tags=sc_tags,
            )
            self._sub_scrims[sub_k] = (sid, float(sc_step))

        # Dynamic canvas sprite overlays (radios, switches, steppers, binds, status, CTA buttons)
        for mval, rx, ry in radio_placements:
            sp = self.sprites["rad_on"] if method == mval else self.sprites["rad_off"]
            rid_item = self.cv.create_image(int(round(rx * self.S)), int(round(ry * self.S)), anchor="nw", image=sp, tags=_group_info(ry)[0])
            self._radio_items[mval] = rid_item

        sw_from = (active_anim.get("sw_from") if active_anim else None) or {}
        for skey, sx, sy in switch_placements:
            self._switch_pos[skey] = (sx, sy)
            on = bool(self.live(skey))
            target_v = 1.0 if on else 0.0
            start_v = sw_from.get(skey, target_v) if (active_anim and skey in sw_from) else target_v
            s_idx = int(round(clamp(start_v, 0.0, 1.0) * 16.0))
            tx_off = sx + 3.0
            tx_on = sx + 21.0
            tx = tx_off + (tx_on - tx_off) * start_v
            tags = _group_info(sy)[0]
            trk_id = self.cv.create_image(int(round(sx * self.S)), int(round(sy * self.S)), anchor="nw", image=self.sprites[f"trk_{s_idx}"], tags=tags)
            thm_id = self.cv.create_image(int(round(tx * self.S)), int(round((sy + 3.0) * self.S)), anchor="nw", image=self.sprites[f"thm_{s_idx}"], tags=tags)
            self._switch_items[skey] = (trk_id, thm_id, tx_off, tx_on)
            if abs(start_v - target_v) > 0.01:
                self._queue_anim(f"sw:{skey}", {
                    "kind": "switch",
                    "skey": skey,
                    "t0": time.monotonic(),
                    "dur": 0.21,
                    "v0": start_v,
                    "v1": target_v,
                    "cur_t": start_v,
                })

        for skey, sx, sy, _, sval in stepper_placements:
            w_st = 100.0 if skey == "turn_px" else 94.0
            dec_cb = (lambda s=-100: self.bump_turn(s)) if skey == "turn_px" else (lambda k=skey: self.bump_delay(k, -1))
            inc_cb = (lambda s=100: self.bump_turn(s)) if skey == "turn_px" else (lambda k=skey: self.bump_delay(k, 1))
            self.regions.append((f"st_dec_{skey}", sx, sy, sx + 30.0, sy + 30.0, dec_cb))
            self.regions.append((f"st_inc_{skey}", sx + w_st - 30.0, sy, sx + w_st, sy + 30.0, inc_cb))
            self._place_dyn_text(
                f"val_{skey}", str(sval), sx + w_st * 0.5, sy + 15.0,
                13.5, "bd", C_TX, anchor="center", tags=_group_info(sy)[0],
            )

        for which, bx, by in bind_placements:
            self.regions.append((f"bind_{which}", bx, by, bx + 74.0, by + 30.0, lambda w_=which: self.begin_capture(w_)))
            b_tags = _group_info(by)[0]
            self._canvas_items[f"bind_bg_{which}"] = self.cv.create_image(
                int(round(bx * self.S)), int(round(by * self.S)),
                anchor="nw", image=self.sprites["bind_idle"], tags=b_tags,
            )
            self._place_dyn_text(
                f"bind_tx_{which}", "", bx + 37.0, by + 15.0,
                12.5, "bd", C_TX, anchor="center", tags=b_tags,
            )

        if self.page == "main":
            sy = self._status_y
            s_tags = _group_info(sy)[0]
            self._canvas_items["st_pill"] = self.cv.create_image(
                int(round((pad + 12.0) * self.S)), int(round((sy + 7.5) * self.S)),
                anchor="nw", image=self.sprites[f"pill_{lang}_ready"], tags=s_tags,
            )
            self._canvas_items["st_pulse"] = self.cv.create_image(
                int(round((pad + 24.0) * self.S)), int(round((sy + 18.5) * self.S)),
                anchor="center", state="hidden", tags=s_tags,
            )
            self._place_dyn_text("st_detail", "", pad + cw - 12.0, sy + 18.5, 12.0, "rg", C_TX2, anchor="e", tags=s_tags)
            self._place_dyn_text("log_0", "", pad + 12.0, sy + 46.5, 11.5, "rg", C_TX2, anchor="w", tags=s_tags)
            self._place_dyn_text("log_1", "", pad + 12.0, sy + 60.5, 11.5, "rg", C_TX3, anchor="w", tags=s_tags)

        # Primary Start / Stop CTA items (crisp rounded sprites + 2x LANCZOS text)
        sx0, sy0, sw0, sh0, px0, py0, pw0, ph0 = main_action_rects
        self._footer_btn_rects = main_action_rects
        f_tags = _group_info(sy0)[0]
        self._canvas_items["cta_start_bg"] = self.cv.create_image(
            int(round(sx0 * self.S)), int(round(sy0 * self.S)),
            anchor="nw", image=self.sprites["cta_start_idle"], tags=f_tags,
        )
        self._place_dyn_text("cta_start_tx", "", sx0 + sw0 * 0.5, sy0 + sh0 * 0.5, 13.5, "sb", C_CTA_FG, anchor="center", tags=f_tags)
        self._canvas_items["cta_stop_bg"] = self.cv.create_image(
            int(round(px0 * self.S)), int(round(py0 * self.S)),
            anchor="nw", image=self.sprites["cta_stop_idle"], tags=f_tags,
        )
        self._place_dyn_text("cta_stop_tx", "", px0 + pw0 * 0.5, py0 + ph0 * 0.5, 13.5, "md", C_TX, anchor="center", tags=f_tags)
        self.regions.append(("cta_start", sx0, sy0, sx0 + sw0, sy0 + sh0, self.start))
        self.regions.append(("cta_stop", px0, py0, px0 + pw0, py0 + ph0, self.stop))

        # Raise strict clipping z-order: mid < mid_fg < top/bot < top/bot_fg < hdr < hdr_fg
        for ltag in ("layer_mid_bg", "layer_mid_fg", "layer_topbot_bg", "layer_topbot_fg", "layer_hdr_bg", "layer_hdr_fg"):
            if self.cv.find_withtag(ltag):
                self.cv.tag_raise(ltag)

        self._headless_meta = {
            "base": base_1x.copy(),
            "radios": list(radio_placements),
            "switches": list(switch_placements),
            "steppers": list(stepper_placements),
            "binds": list(bind_placements),
            "chips": list(chip_placements),
            "seg": self._seg_pos,
            "method_ys": dict(self._method_ys),
            "hint_pos": self._hint_pos,
            "params_pos": (self._params_x_sum, self._params_y_sum),
            "chev_center": self._chev_center,
            "params_open": bool(self.params_open),
            "cta": main_action_rects,
            "status_y": getattr(self, "_status_y", 0.0),
            "method": method,
            "page": self.page,
        }

        self.refresh_dynamic_items()

        # Configure scroll region & window height BEFORE stamping animation start time (zero DWM frame-skip)
        wh = int(round(self.view_h * self.S))
        prev_wh = int(round(prev_view_h * self.S))
        self.scroll_y = clamp(self.scroll_y, 0.0, max(0.0, self.total_h - self.view_h))
        if self.total_h > 0:
            self.cv.yview_moveto(self.scroll_y / self.total_h)
        if active_anim is not None and active_anim["kind"] in ("expand", "collapse", "page") and prev_wh != wh:
            if not HEADLESS and prev_wh > wh:
                # Shrinking: keep OS window at prev_wh while Canvas slides up smoothly, then shrink once at end
                self.cv.configure(
                    width=self.Wp,
                    height=prev_wh,
                    scrollregion=(0, 0, self.Wp, int(round(self.total_h * self.S))),
                )
                self._set_root_wh(self.Wp, prev_wh)
                self._pending_geo_wh = (self.Wp, wh)
            else:
                # Expanding: resize OS window once up front so no mid-animation WM_SIZE DWM flicker occurs
                self.cv.configure(
                    width=self.Wp,
                    height=wh,
                    scrollregion=(0, 0, self.Wp, int(round(self.total_h * self.S))),
                )
                self._set_root_wh(self.Wp, wh)
                self._pending_geo_wh = None
        else:
            self.cv.configure(
                width=self.Wp,
                height=wh,
                scrollregion=(0, 0, self.Wp, int(round(self.total_h * self.S))),
            )
            self._set_root_wh(self.Wp, wh)

        # Kick off smooth structural transitions (stamp t0 AFTER all PIL/PhotoImage/geometry prep)
        if active_anim is not None:
            ak = active_anim["kind"]
            if ak == "page":
                dx0 = float(active_anim.get("dir", 1.0)) * 22.0
                dy_f = float(active_anim.get("old_footer_y", footer_y)) - footer_y
                old_comp = active_anim.get("old_comp")
                frames: list[ImageTk.PhotoImage] = []
                hy = max(1, int(round(header_h * self.S)))
                if old_comp is not None:
                    old_fy_px = min(old_comp.height, max(hy + 1, int(round(active_anim.get("old_footer_y", footer_y) * self.S))))
                    old_b = old_comp.crop((0, hy, self.Wp, old_fy_px)).convert("RGBA")
                    alpha_ch = old_b.getchannel("A")
                    for k in range(6):
                        t = k / 5.0
                        a_scale = 0.90 * ((1.0 - t) ** 1.4)
                        fr = old_b.copy()
                        fr.putalpha(alpha_ch.point(lambda p, s=a_scale: int(p * s)))
                        frames.append(ImageTk.PhotoImage(fr, master=self.root))
                    self._trans_photos.extend(frames)
                now_t = time.monotonic()
                self._start_group_move("ui_body", dx0, 0.0, 0.21, now_t)
                if abs(dy_f) > 1.0:
                    self._start_group_move("ui_footer", 0.0, dy_f, 0.21, now_t)
                if frames:
                    tid = self.cv.create_image(0, hy, anchor="nw", image=frames[0], tags=("ui_trans",))
                    for ltag in ("ui_footer", "layer_hdr_bg", "layer_hdr_fg"):
                        if self.cv.find_withtag(ltag):
                            self.cv.tag_raise(ltag)
                    self._queue_anim("fade:page", {
                        "kind": "fade_frames",
                        "item": tid,
                        "frames": frames,
                        "last_idx": 0,
                        "t0": now_t,
                        "dur": 0.20,
                        "x0": 0.0,
                        "x1": -dx0 * 0.7,
                        "y0": float(hy) / self.S,
                    })
            elif ak == "lang":
                prev_lng = active_anim.get("prev_lang", lang)
                if prev_lng != lang:
                    px_start = seg_x + (3.0 if prev_lng == "ru" else 42.0)
                    self.cv.coords(self._canvas_items["seg_thumb"], int(round(px_start * self.S)), int(round((seg_y + 3.0) * self.S)))
                    old_comp = active_anim.get("old_comp")
                    new_comp = self.render_headless_preview() if old_comp is not None else None
                    frames = []
                    hy = max(1, int(round(header_h * self.S)))
                    if old_comp is not None and new_comp is not None:
                        mh = min(old_comp.height, new_comp.height)
                        old_b = old_comp.crop((0, hy, self.Wp, mh)).convert("RGBA")
                        new_b = new_comp.crop((0, hy, self.Wp, mh)).convert("RGBA")
                        frames = [
                            ImageTk.PhotoImage(Image.blend(old_b, new_b, (k + 1) / 7.0), master=self.root)
                            for k in range(6)
                        ]
                        self._trans_photos.extend(frames)
                    now_t = time.monotonic()
                    self._queue_anim("item_x:seg_thumb", {
                        "kind": "item_x",
                        "item": self._canvas_items["seg_thumb"],
                        "t0": now_t,
                        "dur": 0.19,
                        "x0": px_start,
                        "x1": seg_tx0,
                    })
                    if frames:
                        tid = self.cv.create_image(0, hy, anchor="nw", image=frames[0], tags=("ui_trans",))
                        for ltag in ("layer_hdr_bg", "layer_hdr_fg"):
                            if self.cv.find_withtag(ltag):
                                self.cv.tag_raise(ltag)
                        self._queue_anim("fade:lang", {
                            "kind": "fade_frames",
                            "item": tid,
                            "frames": frames,
                            "last_idx": 0,
                            "t0": now_t,
                            "dur": 0.18,
                            "x0": 0.0,
                            "x1": 0.0,
                            "y0": float(hy) / self.S,
                        })
            elif ak == "expand":
                now_t = time.monotonic()
                delta = active_anim["split_y1"] - active_anim["split_y0"]
                self._start_group_move("ui_bot", 0.0, -delta, 0.20, now_t)
                self._start_group_move("ui_mid", 0.0, -delta * 0.45, 0.20, now_t)
            elif ak == "collapse":
                now_t = time.monotonic()
                delta = float(active_anim["delta_h"])
                self._start_group_move("ui_bot", 0.0, delta, 0.20, now_t)
                if self.cv.find_withtag("ui_mid"):
                    self._start_group_move("ui_mid", 0.0, -delta * 0.35, 0.20, now_t, delete_on_done=True)

        # Synchronize all queued job start timestamps so frame 1 always begins after rebuild_ui exits
        if self.anim_jobs:
            sync_t = time.monotonic()
            for jkey, job in self.anim_jobs.items():
                if jkey != "pulse":
                    job["t0"] = sync_t

    def refresh_dynamic_items(self) -> None:
        """Update dynamic 2x LANCZOS labels/status/buttons/steppers instantaneously."""
        lang = self.live("lang")
        method = int(self.live("method"))
        for skey in ("min", "max", "turn_px"):
            if f"val_{skey}" in self._canvas_items:
                self._set_dyn_text(f"val_{skey}", str(self.live(skey)), 13.5, "bd", C_TX)

        if self.page == "main":
            if "hint_method" in self._canvas_items:
                self._set_dyn_text(
                    "hint_method",
                    self.tr("hint_afk") if method == 0 else self.tr("hint_auto"),
                    11.5, "rg", C_TX3,
                )
            if "params_sum" in self._canvas_items:
                fb_txt = self.tr("fb_on") if self.live("safe") else self.tr("fb_off")
                summ = f"{self.live('min')}–{self.live('max')} {self.tr('min_word')} · {fb_txt}"
                self._set_dyn_text("params_sum", summ, 12.0, "rg", C_TX3)

        for which in ("start", "stop"):
            bg_id = self._canvas_items.get(f"bind_bg_{which}")
            if bg_id and f"bind_tx_{which}" in self._canvas_items:
                listening = (self.capturing == which)
                key_lbl = self.tr("hk_press") if listening else str(self.live(f"{which}_key")).upper()
                self.cv.itemconfigure(bg_id, image=self.sprites["bind_cap" if listening else "bind_idle"])
                self._set_dyn_text(f"bind_tx_{which}", key_lbl, 12.5, "bd", C_CTA_FG if listening else C_TX)

        if self.page == "main" and "st_pill" in self._canvas_items:
            st = self.state if self.state in ("ready", "running", "starting", "stopping") else "ready"
            self.cv.itemconfigure(self._canvas_items["st_pill"], image=self.sprites[f"pill_{lang}_{st}"])

            cw_card = self.W - 32.0
            det = self.ref(self.detail_ref)
            if isinstance(self.detail_ref, dict) and self.detail_ref.get("key") == "dt_idle":
                det = f"{det} {str(self.live('start_key')).upper()}"
            det = self._fit_text(det, 12.0, "rg", cw_card - 138.0)
            self._set_dyn_text("st_detail", det, 12.0, "rg", C_TX2)

            logs = list(self.log)
            l0 = self._fit_text(f"{logs[-1][0]}  {logs[-1][1]}", 11.5, "rg", cw_card - 24.0) if len(logs) >= 1 else ""
            l1 = self._fit_text(f"{logs[-2][0]}  {logs[-2][1]}", 11.5, "rg", cw_card - 24.0) if len(logs) >= 2 else ""
            self._set_dyn_text("log_0", l0, 11.5, "rg", C_TX2)
            self._set_dyn_text("log_1", l1, 11.5, "rg", C_TX3)
            self._sync_pulse()

        if "cta_start_bg" in self._canvas_items:
            sk = str(self.live("start_key")).upper()
            tk_stop = str(self.live("stop_key")).upper()
            if self.running:
                self.cv.itemconfigure(self._canvas_items["cta_start_bg"], image=self.sprites["cta_start_run"])
                self._set_dyn_text("cta_start_tx", f"{self.tr('btn_running')}  [{sk}]", 13.5, "sb", (18, 20, 25))
                self.cv.itemconfigure(self._canvas_items["cta_stop_bg"], image=self.sprites["cta_stop_run"])
                self._set_dyn_text("cta_stop_tx", f"{self.tr('btn_stop')}  [{tk_stop}]", 13.5, "md", C_TX)
            else:
                self.cv.itemconfigure(self._canvas_items["cta_start_bg"], image=self.sprites["cta_start_idle"])
                self._set_dyn_text("cta_start_tx", f"{self.tr('btn_start')}  [{sk}]", 13.5, "sb", C_CTA_FG)
                self.cv.itemconfigure(self._canvas_items["cta_stop_bg"], image=self.sprites["cta_stop_idle"])
                self._set_dyn_text("cta_stop_tx", f"{self.tr('btn_stop')}  [{tk_stop}]", 13.5, "md", (126, 134, 150))

        if HEADLESS:
            self.last_headless_img = self.render_headless_preview()

    def _chip_active_state(self, cid: str) -> bool:
        if cid == "lmb_swing":
            return not bool(self.live("mouse"))
        if cid == "lmb_hold":
            return bool(self.live("mouse"))
        if cid == "pace_norm":
            return not bool(self.live("stand"))
        if cid == "pace_stand":
            return bool(self.live("stand"))
        if cid == "anim_on":
            return bool(self.live("anim"))
        if cid == "anim_off":
            return not bool(self.live("anim"))
        return False

    def render_headless_preview(self) -> Image.Image | None:
        """Composite complete UI using exact 2x LANCZOS sprites matching Canvas pixels."""
        meta = self._headless_meta
        if not meta or "base" not in meta:
            return self.last_headless_img
        out = meta["base"].copy()
        d = ImageDraw.Draw(out, "RGBA")
        S = self.S
        lang = self.live("lang")
        method = int(self.live("method"))

        def paste_sp(name: str, x_dp: float, y_dp: float, anchor: str = "nw") -> None:
            sp = self._pil_sprites.get(name)
            if sp is None:
                return
            if anchor == "center":
                ox = int(round(x_dp * S - sp.width * 0.5))
                oy = int(round(y_dp * S - sp.height * 0.5))
            else:
                ox = int(round(x_dp * S))
                oy = int(round(y_dp * S))
            out.alpha_composite(sp, (max(0, ox), max(0, oy)))

        def paste_txt(key: str, text: str, x_dp: float, y_dp: float, size_dp: float, wt: str, col_rgb: tuple[int, int, int], anchor: str = "w") -> None:
            im_1x, _ = self._text_sprite(text, size_dp, wt, col_rgb)
            if anchor == "w":
                ox = int(round((x_dp - 2.5) * S))
                oy = int(round(y_dp * S - im_1x.height * 0.5))
            elif anchor == "e":
                ox = int(round((x_dp + 2.5) * S - im_1x.width))
                oy = int(round(y_dp * S - im_1x.height * 0.5))
            else:
                ox = int(round(x_dp * S - im_1x.width * 0.5))
                oy = int(round(y_dp * S - im_1x.height * 0.5))
            if ox >= 0 and oy >= 0:
                out.alpha_composite(im_1x, (ox, oy))

        seg = meta.get("seg")
        if seg:
            seg_x, seg_y, _, seg_h = seg
            paste_sp("seg_thumb", seg_x + (3.0 if lang == "ru" else 42.0), seg_y + 3.0)
            paste_sp(f"seg_ru_{'act' if lang == 'ru' else 'dim'}", seg_x + 21.5, seg_y + seg_h * 0.5, anchor="center")
            paste_sp(f"seg_en_{'act' if lang == 'en' else 'dim'}", seg_x + 60.5, seg_y + seg_h * 0.5, anchor="center")

        m_ys = meta.get("method_ys", {})
        if meta.get("page") == "main" and method in m_ys:
            paste_sp("method_act_bg", 26.0, m_ys[method])
            hx, hy = meta.get("hint_pos", (0.0, 0.0))
            paste_txt("hint_method", self.tr("hint_afk") if method == 0 else self.tr("hint_auto"), hx, hy, 11.5, "rg", C_TX3, anchor="e")
            px_s, py_s = meta.get("params_pos", (0.0, 0.0))
            fb_txt = self.tr("fb_on") if self.live("safe") else self.tr("fb_off")
            paste_txt("params_sum", f"{self.live('min')}–{self.live('max')} {self.tr('min_word')} · {fb_txt}", px_s, py_s, 12.0, "rg", C_TX3, anchor="w")
            cx0, cy0 = meta.get("chev_center", (0.0, 0.0))
            if meta.get("params_open"):
                pts = (((cx0 - 4) * S, (cy0 + 2) * S), (cx0 * S, (cy0 - 2.5) * S), ((cx0 + 4) * S, (cy0 + 2) * S))
            else:
                pts = (((cx0 - 4) * S, (cy0 - 2) * S), (cx0 * S, (cy0 + 2.5) * S), ((cx0 + 4) * S, (cy0 - 2) * S))
            d.line(pts, fill=C_TX2 + (255,), width=max(1, int(round(1.6 * S))), joint="curve")

        for cid, cx, cy, _cw, _ch, _, _ in meta.get("chips", ()):
            pressed = self._chip_active_state(cid)
            paste_sp(f"chip_{cid}_{lang}_{12 if pressed else 0}", cx, cy)

        if meta.get("page") == "main":
            for sub_k, (sbx, sby, _, _) in self._sub_bars.items():
                parent_on = bool(self.live("swing" if sub_k == "pickaxe" else "walk"))
                if not parent_on:
                    paste_sp("sub_scrim_8", sbx, sby)

        for mval, rx, ry in meta["radios"]:
            paste_sp("rad_on" if method == mval else "rad_off", rx, ry)

        for skey, sx, sy in meta["switches"]:
            on = bool(self.live(skey))
            paste_sp("trk_on" if on else "trk_off", sx, sy)
            paste_sp("thm_on" if on else "thm_off", sx + (21.0 if on else 3.0), sy + 3.0)

        for skey, sx, sy, _, _ in meta["steppers"]:
            w_st = 100.0 if skey == "turn_px" else 94.0
            paste_txt(f"val_{skey}", str(self.live(skey)), sx + w_st * 0.5, sy + 15.0, 13.5, "bd", C_TX, anchor="center")

        for which, bx, by in meta["binds"]:
            listening = (self.capturing == which)
            paste_sp("bind_cap" if listening else "bind_idle", bx, by)
            key_lbl = self.tr("hk_press") if listening else str(self.live(f"{which}_key")).upper()
            paste_txt(f"bind_tx_{which}", key_lbl, bx + 37.0, by + 15.0, 12.5, "bd", C_CTA_FG if listening else C_TX, anchor="center")

        if meta["page"] == "main":
            pad = 16.0
            cw = self.W - pad * 2
            sy = meta["status_y"]
            st = self.state if self.state in ("ready", "running", "starting", "stopping") else "ready"
            paste_sp(f"pill_{lang}_{st}", pad + 12.0, sy + 7.5)

            det = self.ref(self.detail_ref)
            if isinstance(self.detail_ref, dict) and self.detail_ref.get("key") == "dt_idle":
                det = f"{det} {str(self.live('start_key')).upper()}"
            det = self._fit_text(det, 12.0, "rg", cw - 138.0)
            paste_txt("st_detail", det, pad + cw - 12.0, sy + 18.5, 12.0, "rg", C_TX2, anchor="e")

            logs = list(self.log)
            if len(logs) >= 1:
                l0 = self._fit_text(f"{logs[-1][0]}  {logs[-1][1]}", 11.5, "rg", cw - 24.0)
                paste_txt("log_0", l0, pad + 12.0, sy + 46.5, 11.5, "rg", C_TX2, anchor="w")
            if len(logs) >= 2:
                l1 = self._fit_text(f"{logs[-2][0]}  {logs[-2][1]}", 11.5, "rg", cw - 24.0)
                paste_txt("log_1", l1, pad + 12.0, sy + 60.5, 11.5, "rg", C_TX3, anchor="w")

        sx0, sy0, sw0, sh0, px0, py0, pw0, ph0 = meta["cta"]
        sk = str(self.live("start_key")).upper()
        tk_stop = str(self.live("stop_key")).upper()
        if self.running:
            paste_sp("cta_start_run", sx0, sy0)
            paste_sp("cta_stop_run", px0, py0)
            paste_txt("cta_start_tx", f"{self.tr('btn_running')}  [{sk}]", sx0 + sw0 * 0.5, sy0 + sh0 * 0.5, 13.5, "sb", (18, 20, 25), anchor="center")
            paste_txt("cta_stop_tx", f"{self.tr('btn_stop')}  [{tk_stop}]", px0 + pw0 * 0.5, py0 + ph0 * 0.5, 13.5, "md", C_TX, anchor="center")
        else:
            paste_sp("cta_start_idle", sx0, sy0)
            paste_sp("cta_stop_idle", px0, py0)
            paste_txt("cta_start_tx", f"{self.tr('btn_start')}  [{sk}]", sx0 + sw0 * 0.5, sy0 + sh0 * 0.5, 13.5, "sb", C_CTA_FG, anchor="center")
            paste_txt("cta_stop_tx", f"{self.tr('btn_stop')}  [{tk_stop}]", px0 + pw0 * 0.5, py0 + ph0 * 0.5, 13.5, "md", (126, 134, 150), anchor="center")
        return out

    # ---------------- Smooth 60 FPS Canvas Animation Engine (0% Idle CPU) ----------------
    def _ensure_anim_loop(self) -> None:
        if self.anim_jobs:
            self._set_timer_res(True)
            if not self.anim_running:
                self.anim_running = True
                ms = 14 if any(k != "pulse" for k in self.anim_jobs) else 24
                self._anim_after_id = self.root.after(ms, self._step_anims)

    def _queue_anim(self, key: str, job: dict) -> None:
        self.anim_jobs[key] = job
        self._ensure_anim_loop()

    def _start_group_move(self, tag: str, dx0: float, dy0: float, dur: float = 0.20, now_t: float | None = None, delete_on_done: bool = False) -> None:
        if f"grp:{tag}" in self.anim_jobs:
            prev = self.anim_jobs.pop(f"grp:{tag}")
            self.cv.move(tag, -int(prev["ap_x"]), -int(prev["ap_y"]))
        px0 = int(round(dx0 * self.S))
        py0 = int(round(dy0 * self.S))
        if px0 != 0 or py0 != 0:
            self.cv.move(tag, px0, py0)
        self._queue_anim(f"grp:{tag}", {
            "kind": "group_move",
            "tag": tag,
            "t0": time.monotonic() if now_t is None else now_t,
            "dur": dur,
            "dx0": dx0,
            "dy0": dy0,
            "ap_x": px0,
            "ap_y": py0,
            "delete_on_done": delete_on_done,
        })

    def _stop_all_anims(self, snap: bool = True) -> None:
        if self._anim_after_id is not None:
            try:
                self.root.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None
        if snap:
            for _, job in list(self.anim_jobs.items()):
                kind = job.get("kind")
                if kind == "group_move":
                    self.cv.move(job["tag"], -int(job["ap_x"]), -int(job["ap_y"]))
                    if job.get("delete_on_done"):
                        self.cv.delete(job["tag"])
                elif kind == "switch":
                    skey = job["skey"]
                    item = self._switch_items.get(skey)
                    if item:
                        trk_id, thm_id, tx_off, tx_on = item
                        on = job["v1"] >= 0.5
                        x = tx_on if on else tx_off
                        y = self.cv.coords(thm_id)[1]
                        self.cv.coords(thm_id, int(round(x * self.S)), int(round(y)))
                        self.cv.itemconfigure(trk_id, image=self.sprites["trk_on" if on else "trk_off"])
                        self.cv.itemconfigure(thm_id, image=self.sprites["thm_on" if on else "thm_off"])
                elif kind == "radio":
                    iid = self._radio_items.get(job["mval"])
                    if iid:
                        self.cv.itemconfigure(iid, image=self.sprites["rad_on" if job["v1"] >= 0.5 else "rad_off"])
                elif kind == "item_x":
                    iid = job["item"]
                    coords = self.cv.coords(iid)
                    if len(coords) >= 2:
                        self.cv.coords(iid, int(round(job["x1"] * self.S)), coords[1])
                elif kind == "item_y":
                    iid = job["item"]
                    coords = self.cv.coords(iid)
                    if len(coords) >= 2:
                        self.cv.coords(iid, coords[0], int(round(job["y1"] * self.S)))
                elif kind == "chip":
                    cinfo = self._chip_items.get(job["cid"])
                    if cinfo:
                        bg_id, _, _, prefix, _ = cinfo
                        on = job["v1"] >= 0.5
                        self.cv.itemconfigure(bg_id, image=self.sprites[f"{prefix}_{12 if on else 0}"])
                elif kind == "sub":
                    sub_k = job["sub_k"]
                    sc = self._sub_scrims.get(sub_k)
                    if sc:
                        sid, _ = sc
                        step = 8 if job["v1"] >= 0.5 else 0
                        if step <= 0:
                            self.cv.itemconfigure(sid, state="hidden")
                        else:
                            self.cv.itemconfigure(sid, state="normal", image=self.sprites[f"sub_scrim_{step}"])
                        self._sub_scrims[sub_k] = (sid, float(step))
                elif kind == "fade_frames":
                    try:
                        self.cv.delete(job["item"])
                    except Exception:
                        pass
                elif kind == "flash":
                    self._set_dyn_text(job["key"], job["text"], job["size_dp"], job["wt"], job["rest_rgb"])
        for hid in list(self._hover_items.values()):
            self.cv.delete(hid)
        self._hover_items.clear()
        self._hover_levels.clear()
        self._trans_photos.clear()
        self.anim_jobs.clear()
        self.anim_running = False
        self._set_timer_res(False)
        self._commit_pending_geo()
        if "st_pulse" in self._canvas_items:
            self.cv.itemconfigure(self._canvas_items["st_pulse"], state="hidden")

    def _sync_pulse(self) -> None:
        want = bool(self.live("anim")) and self.page == "main" and (self.running or self.state != "ready") and ("st_pulse" in self._canvas_items)
        pid = self._canvas_items.get("st_pulse")
        if not want:
            self.anim_jobs.pop("pulse", None)
            if pid:
                self.cv.itemconfigure(pid, state="hidden")
            if not self.anim_jobs:
                if self._anim_after_id is not None:
                    try:
                        self.root.after_cancel(self._anim_after_id)
                    except Exception:
                        pass
                    self._anim_after_id = None
                self.anim_running = False
                self._set_timer_res(False)
            return
        st = "stopping" if self.state == "stopping" else "running"
        if "pulse" not in self.anim_jobs:
            self.cv.itemconfigure(pid, state="normal", image=self.sprites[f"pulse_{st}_0"])
            self._queue_anim("pulse", {"kind": "pulse", "t0": time.monotonic(), "last_ts": 0.0, "last_key": f"pulse_{st}_0"})
        else:
            self.cv.itemconfigure(pid, state="normal")

    def animate_switch(self, skey: str, target_on: bool) -> None:
        item = self._switch_items.get(skey)
        if not item:
            return
        trk_id, thm_id, tx_off, tx_on = item
        if not self.live("anim"):
            self.cv.itemconfigure(trk_id, image=self.sprites["trk_on" if target_on else "trk_off"])
            self.cv.itemconfigure(thm_id, image=self.sprites["thm_on" if target_on else "thm_off"])
            x = tx_on if target_on else tx_off
            y = self.cv.coords(thm_id)[1]
            self.cv.coords(thm_id, int(round(x * self.S)), int(round(y)))
            return
        cur_x_dp = self.cv.coords(thm_id)[0] / self.S
        v0 = clamp((cur_x_dp - tx_off) / max(1e-6, tx_on - tx_off), 0.0, 1.0)
        self._queue_anim(f"sw:{skey}", {
            "kind": "switch",
            "skey": skey,
            "t0": time.monotonic(),
            "dur": 0.21,
            "v0": v0,
            "v1": 1.0 if target_on else 0.0,
            "cur_t": v0,
        })

    def animate_sub_scrim(self, sub_k: str, parent_on: bool) -> None:
        sc = self._sub_scrims.get(sub_k)
        if not sc:
            return
        sid, cur_step = sc
        if not self.live("anim"):
            self.anim_jobs.pop(f"sub:{sub_k}", None)
            if parent_on:
                self.cv.itemconfigure(sid, state="hidden")
                self._sub_scrims[sub_k] = (sid, 0.0)
            else:
                self.cv.itemconfigure(sid, state="normal", image=self.sprites["sub_scrim_8"])
                self.cv.tag_raise(sid)
                self._sub_scrims[sub_k] = (sid, 8.0)
            return
        prev = self.anim_jobs.get(f"sub:{sub_k}")
        v0 = float(prev["cur_t"]) if prev else clamp(cur_step / 8.0, 0.0, 1.0)
        v1 = 0.0 if parent_on else 1.0
        init_step = max(1, int(round(v0 * 8.0)))
        self.cv.itemconfigure(sid, state="normal", image=self.sprites[f"sub_scrim_{init_step}"])
        self.cv.tag_raise(sid)
        self._queue_anim(f"sub:{sub_k}", {
            "kind": "sub",
            "sub_k": sub_k,
            "t0": time.monotonic(),
            "dur": 0.19,
            "v0": v0,
            "v1": v1,
            "cur_t": v0,
        })

    def animate_radio(self, mval: int, target_on: bool) -> None:
        iid = self._radio_items.get(mval)
        if not iid:
            return
        if not self.live("anim"):
            self.cv.itemconfigure(iid, image=self.sprites["rad_on" if target_on else "rad_off"])
            return
        prev = self.anim_jobs.get(f"rad:{mval}")
        v0 = float(prev["cur_t"]) if prev else (0.0 if target_on else 1.0)
        self._queue_anim(f"rad:{mval}", {
            "kind": "radio",
            "mval": mval,
            "t0": time.monotonic(),
            "dur": 0.19,
            "v0": v0,
            "v1": 1.0 if target_on else 0.0,
            "cur_t": v0,
        })

    def animate_method_card(self, old_m: int, new_m: int) -> None:
        iid = self._canvas_items.get("method_act")
        if not iid or new_m not in self._method_ys:
            return
        y1 = self._method_ys[new_m]
        if not self.live("anim"):
            x_px = self.cv.coords(iid)[0]
            self.cv.coords(iid, x_px, int(round(y1 * self.S)))
            return
        y0 = self.cv.coords(iid)[1] / self.S
        self._queue_anim("item_y:method_act", {
            "kind": "item_y",
            "item": iid,
            "t0": time.monotonic(),
            "dur": 0.20,
            "y0": y0,
            "y1": y1,
        })

    def animate_chip_pair(self, cfg_key: str, new_val: bool, snap: bool = False) -> None:
        pair_map = {
            "mouse": ("lmb_swing", "lmb_hold"),
            "stand": ("pace_norm", "pace_stand"),
            "anim": ("anim_off", "anim_on"),
        }
        cids = pair_map.get(cfg_key, ())
        for cid in cids:
            info = self._chip_items.get(cid)
            if not info:
                continue
            bg_id, _, _, prefix, _ = info
            target_on = cid.endswith("_hold") or cid.endswith("_stand") or cid.endswith("_on")
            is_on = (target_on == bool(new_val))
            if snap or not self.live("anim"):
                self.anim_jobs.pop(f"chip:{cid}", None)
                self.cv.itemconfigure(bg_id, image=self.sprites[f"{prefix}_{12 if is_on else 0}"])
            else:
                prev = self.anim_jobs.get(f"chip:{cid}")
                v0 = float(prev["cur_t"]) if prev else (0.0 if is_on else 1.0)
                self._queue_anim(f"chip:{cid}", {
                    "kind": "chip",
                    "cid": cid,
                    "t0": time.monotonic(),
                    "dur": 0.18,
                    "v0": v0,
                    "v1": 1.0 if is_on else 0.0,
                    "cur_t": v0,
                })

    def flash_item(self, canvas_key: str, text_str: str, rest_col=C_TX, size_dp: float = 13.5, wt: str = "bd") -> None:
        if canvas_key not in self._canvas_items or not self.live("anim"):
            return
        self._set_dyn_text(canvas_key, text_str, size_dp, wt, C_CTA_HOV)
        self._queue_anim(f"fl:{canvas_key}", {
            "kind": "flash",
            "key": canvas_key,
            "text": text_str,
            "size_dp": size_dp,
            "wt": wt,
            "t0": time.monotonic(),
            "dur": 0.18,
            "rest_rgb": rest_col,
            "last_q": -1,
        })

    def _set_hover_visual(self, rid: str, frac: float) -> None:
        spec = self._hover_rects.get(rid)
        if not spec:
            return
        prefix, hx, hy, grp, lay = spec
        self._hover_levels[rid] = frac
        step = int(round(clamp(frac, 0.0, 1.0) * 10.0))
        hid = self._hover_items.get(rid)
        if step <= 0:
            if hid:
                self.cv.delete(hid)
                del self._hover_items[rid]
            return
        sp = self.sprites.get(f"hov_{prefix}_{step}")
        if not sp:
            return
        if hid:
            self.cv.itemconfigure(hid, image=sp)
        else:
            tags = (grp, lay) if grp else (lay,)
            hid = self.cv.create_image(int(round(hx * self.S)), int(round(hy * self.S)), anchor="nw", image=sp, tags=tags)
            self._hover_items[rid] = hid
            if grp:
                for k, job in self.anim_jobs.items():
                    if k.startswith("grp:") and job["tag"] == grp:
                        self.cv.move(hid, int(job["ap_x"]), int(job["ap_y"]))
                        break
            # Keep hover overlays strictly below foreground labels/controls while above card/button backgrounds
            if rid in ("cta_start", "cta_stop") and f"{rid}_tx" in self._canvas_items:
                self.cv.tag_raise(self._canvas_items[f"{rid}_tx"])
            elif rid in ("bind_start", "bind_stop"):
                which = rid.split("_", 1)[1]
                if f"bind_tx_{which}" in self._canvas_items:
                    self.cv.tag_raise(self._canvas_items[f"bind_tx_{which}"])
            elif rid in ("lang_ru", "lang_en"):
                for ltk in ("seg_ru_tx", "seg_en_tx"):
                    if ltk in self._canvas_items:
                        self.cv.tag_raise(self._canvas_items[ltk])
            elif rid in self._chip_items:
                for sid, sc_step in self._sub_scrims.values():
                    if sc_step > 0:
                        self.cv.tag_raise(sid)
            else:
                bg_tag = "layer_mid_bg" if lay == "layer_mid_fg" else ("layer_hdr_bg" if lay == "layer_hdr_fg" else "layer_topbot_bg")
                if self.cv.find_withtag(bg_tag):
                    self.cv.tag_raise(hid, bg_tag)
            for ltag in ("layer_hdr_bg", "layer_hdr_fg"):
                if self.cv.find_withtag(ltag):
                    self.cv.tag_raise(ltag)

    def _step_anims(self) -> None:
        self._anim_after_id = None
        if not self.anim_jobs:
            self.anim_running = False
            self._set_timer_res(False)
            self._commit_pending_geo()
            return
        now = time.monotonic()
        done: list[str] = []
        grp_finished = False
        geo_ease: float | None = None
        for key, job in list(self.anim_jobs.items()):
            kind = job["kind"]
            if kind == "pulse":
                if not self.live("anim") or self.page != "main" or (not self.running and self.state == "ready"):
                    done.append(key)
                    continue
                if now - job["last_ts"] >= 0.022:
                    job["last_ts"] = now
                    pid = self._canvas_items.get("st_pulse")
                    if pid:
                        st = "stopping" if self.state == "stopping" else "running"
                        phase = ((now - job["t0"]) % 1.6) / 1.6
                        step = min(31, int(phase * 32.0))
                        sp_k = f"pulse_{st}_{step}"
                        if sp_k != job["last_key"]:
                            job["last_key"] = sp_k
                            self.cv.itemconfigure(pid, image=self.sprites[sp_k])
                continue

            p = clamp((now - job["t0"]) / job["dur"], 0.0, 1.0)
            ease = 1.0 - (1.0 - p) ** 3

            if kind == "switch":
                item = self._switch_items.get(job["skey"])
                if not item:
                    done.append(key)
                    continue
                trk_id, thm_id, tx_off, tx_on = item
                cur_t = job["v0"] + (job["v1"] - job["v0"]) * ease
                job["cur_t"] = cur_t
                nx = tx_off + (tx_on - tx_off) * cur_t
                y = self.cv.coords(thm_id)[1]
                self.cv.coords(thm_id, int(round(nx * self.S)), int(round(y)))
                s_idx = int(round(clamp(cur_t, 0.0, 1.0) * 16.0))
                self.cv.itemconfigure(trk_id, image=self.sprites[f"trk_{s_idx}"])
                self.cv.itemconfigure(thm_id, image=self.sprites[f"thm_{s_idx}"])

            elif kind == "radio":
                iid = self._radio_items.get(job["mval"])
                if not iid:
                    done.append(key)
                    continue
                cur_t = job["v0"] + (job["v1"] - job["v0"]) * ease
                job["cur_t"] = cur_t
                r_idx = int(round(clamp(cur_t, 0.0, 1.0) * 12.0))
                self.cv.itemconfigure(iid, image=self.sprites[f"rad_{r_idx}"])

            elif kind == "item_x":
                iid = job["item"]
                coords = self.cv.coords(iid)
                if len(coords) < 2:
                    done.append(key)
                    continue
                nx = job["x0"] + (job["x1"] - job["x0"]) * ease
                self.cv.coords(iid, int(round(nx * self.S)), coords[1])

            elif kind == "item_y":
                iid = job["item"]
                coords = self.cv.coords(iid)
                if len(coords) < 2:
                    done.append(key)
                    continue
                ny = job["y0"] + (job["y1"] - job["y0"]) * ease
                self.cv.coords(iid, coords[0], int(round(ny * self.S)))

            elif kind == "chip":
                cinfo = self._chip_items.get(job["cid"])
                if not cinfo:
                    done.append(key)
                    continue
                bg_id, _, _, prefix, _ = cinfo
                cur_t = job["v0"] + (job["v1"] - job["v0"]) * ease
                job["cur_t"] = cur_t
                step = int(round(clamp(cur_t, 0.0, 1.0) * 12.0))
                self.cv.itemconfigure(bg_id, image=self.sprites[f"{prefix}_{step}"])

            elif kind == "sub":
                sub_k = job["sub_k"]
                sc = self._sub_scrims.get(sub_k)
                if not sc:
                    done.append(key)
                    continue
                sid, _ = sc
                cur_t = job["v0"] + (job["v1"] - job["v0"]) * ease
                job["cur_t"] = cur_t
                step = int(round(clamp(cur_t, 0.0, 1.0) * 8.0))
                if step <= 0:
                    self.cv.itemconfigure(sid, state="hidden")
                else:
                    self.cv.itemconfigure(sid, state="normal", image=self.sprites[f"sub_scrim_{step}"])
                self._sub_scrims[sub_k] = (sid, float(step))

            elif kind == "fade_frames":
                frames = job["frames"]
                idx = min(len(frames) - 1, int(p * len(frames)))
                if idx != job["last_idx"]:
                    job["last_idx"] = idx
                    self.cv.itemconfigure(job["item"], image=frames[idx])
                if job["x1"] != job["x0"]:
                    nx = job["x0"] + (job["x1"] - job["x0"]) * ease
                    self.cv.coords(job["item"], int(round(nx * self.S)), int(round(job["y0"] * self.S)))

            elif kind == "hover":
                cur_t = job["v0"] + (job["v1"] - job["v0"]) * ease
                self._set_hover_visual(job["rid"], cur_t)

            elif kind == "flash":
                q = int(round(ease * 5.0))
                if p >= 1.0:
                    self._set_dyn_text(job["key"], job["text"], job["size_dp"], job["wt"], job["rest_rgb"])
                elif q != job["last_q"]:
                    job["last_q"] = q
                    rgb = self._lerp_rgb(C_CTA_HOV, job["rest_rgb"], q / 5.0)
                    self._set_dyn_text(job["key"], job["text"], job["size_dp"], job["wt"], rgb)

            elif kind == "group_move":
                rem = (1.0 - p) ** 3
                want_x = int(round(job["dx0"] * rem * self.S))
                want_y = int(round(job["dy0"] * rem * self.S))
                dpx = want_x - int(job["ap_x"])
                dpy = want_y - int(job["ap_y"])
                if dpx != 0 or dpy != 0:
                    self.cv.move(job["tag"], dpx, dpy)
                    job["ap_x"] += dpx
                    job["ap_y"] += dpy
                if job["tag"] in ("ui_bot", "ui_footer", "ui_body"):
                    geo_ease = ease

            if p >= 1.0:
                if kind == "group_move":
                    grp_finished = True
                    if job.get("delete_on_done"):
                        self.cv.delete(job["tag"])
                elif kind == "fade_frames":
                    self.cv.delete(job["item"])
                done.append(key)

        for k in done:
            self.anim_jobs.pop(k, None)
        if not any(job.get("kind") == "fade_frames" for job in self.anim_jobs.values()):
            self._trans_photos.clear()
        if grp_finished and not any(k.startswith("grp:") for k in self.anim_jobs):
            self._commit_pending_geo()
        if self.anim_jobs:
            ms = 14 if any(k != "pulse" for k in self.anim_jobs) else 24
            self._anim_after_id = self.root.after(ms, self._step_anims)
        else:
            self.anim_running = False
            self._set_timer_res(False)

    # ---------------- Interactions & Event Handlers ----------------
    def _hit(self, x_ev: float, y_ev: float):
        px = x_ev / self.S
        py = y_ev / self.S + self.scroll_y
        for r in reversed(self.regions):
            if r[1] <= px <= r[3] and r[2] <= py <= r[4]:
                return r
        return None

    def _is_hover_eligible(self, rid: str | None) -> bool:
        if not rid or rid not in self._hover_rects:
            return False
        if self.running and (rid == "cta_start" or rid.startswith("m_")):
            return False
        if rid in ("lmb_swing", "lmb_hold") and not self.live("swing"):
            return False
        if rid in ("pace_norm", "pace_stand") and not self.live("walk"):
            return False
        lang = self.live("lang")
        if (rid == "lang_ru" and lang == "ru") or (rid == "lang_en" and lang == "en"):
            return False
        return True

    def on_move(self, e) -> None:
        r = self._hit(e.x, e.y)
        rid = r[0] if r else None
        if rid != self.hover_id:
            old_rid = self.hover_id
            self.hover_id = rid
            self.cv.configure(cursor="hand2" if rid else "")
            anim_on = bool(self.live("anim"))
            now_t = time.monotonic()
            if old_rid and old_rid in self._hover_rects:
                if anim_on:
                    v0 = self._hover_levels.get(old_rid, 0.0)
                    if v0 > 0.01:
                        self._queue_anim(f"hov:{old_rid}", {"kind": "hover", "rid": old_rid, "t0": now_t, "dur": 0.18, "v0": v0, "v1": 0.0})
                else:
                    self._set_hover_visual(old_rid, 0.0)
            if self._is_hover_eligible(rid):
                if anim_on:
                    v0 = self._hover_levels.get(rid, 0.0)
                    self._queue_anim(f"hov:{rid}", {"kind": "hover", "rid": rid, "t0": now_t, "dur": 0.13, "v0": v0, "v1": 1.0})
                else:
                    self._set_hover_visual(rid, 1.0)

    def on_leave(self, _e=None) -> None:
        old_rid = self.hover_id
        self.hover_id = None
        self.cv.configure(cursor="")
        if old_rid and old_rid in self._hover_rects:
            if self.live("anim"):
                v0 = self._hover_levels.get(old_rid, 0.0)
                if v0 > 0.01:
                    self._queue_anim(f"hov:{old_rid}", {"kind": "hover", "rid": old_rid, "t0": time.monotonic(), "dur": 0.18, "v0": v0, "v1": 0.0})
            else:
                self._set_hover_visual(old_rid, 0.0)

    def on_click(self, e) -> None:
        r = self._hit(e.x, e.y)
        if self.capturing is not None and (not r or r[0] != f"bind_{self.capturing}"):
            self.end_capture()
        if r and callable(r[5]):
            r[5]()

    def on_wheel(self, e) -> None:
        if self.total_h <= self.view_h:
            return
        step = -1 * (e.delta / 120.0) * 32.0
        self.scroll_y = clamp(self.scroll_y + step, 0.0, max(0.0, self.total_h - self.view_h))
        self.cv.yview_moveto(self.scroll_y / self.total_h)
        if hasattr(e, "x") and hasattr(e, "y") and 0 <= e.x <= self.Wp:
            self.on_move(e)

    def _clear_undo(self) -> bool:
        if self.undo_snap is not None:
            self.undo_snap = None
            return True
        return False

    def set_lang(self, lang: str) -> None:
        if self.live("lang") == lang:
            return
        prev_lang = self.live("lang")
        old_comp = self._snapshot_composite() if self.live("anim") else None
        self._clear_undo()
        self.set_cfg("lang", lang)
        self.save()
        self.rebuild_ui(anim_spec={"kind": "lang", "prev_lang": prev_lang, "old_comp": old_comp})

    def toggle_page(self) -> None:
        if self.capturing:
            self.end_capture()
        old_footer_y = self._footer_y
        old_comp = self._snapshot_composite() if self.live("anim") else None
        self.page = "set" if self.page == "main" else "main"
        self.scroll_y = 0.0
        dir_x = 1.0 if self.page == "set" else -1.0
        self.rebuild_ui(anim_spec={"kind": "page", "dir": dir_x, "old_footer_y": old_footer_y, "old_comp": old_comp})

    def toggle_params(self) -> None:
        anim_on = bool(self.live("anim"))
        was_open = self.params_open
        sw_from = self._capture_switch_fracs() if anim_on else {}
        old_comp = self._snapshot_composite() if (was_open and anim_on) else None
        sy0, sy1 = self._params_bounds
        self.params_open = not was_open
        if not anim_on:
            self.rebuild_ui()
            return
        if not was_open:
            spec = {"kind": "expand", "split_y0": sy0, "split_y1": sy1, "sw_from": sw_from}
        else:
            mid_crop = None
            if old_comp is not None and sy1 > sy0:
                y0_px = max(0, min(old_comp.height - 1, int(round(sy0 * self.S))))
                y1_px = max(y0_px + 1, min(old_comp.height, int(round(sy1 * self.S))))
                mid_crop = old_comp.crop((0, y0_px, self.Wp, y1_px))
            spec = {"kind": "collapse", "split_y0": sy0, "delta_h": sy1 - sy0, "mid_crop": mid_crop, "sw_from": sw_from}
        self.rebuild_ui(anim_spec=spec)

    def select_method(self, m: int) -> None:
        if self.running:
            return
        old_m = int(self.live("method"))
        undo_was = self._clear_undo()
        if old_m == m and not undo_was:
            return
        self.set_cfg("method", m)
        self.save()
        if undo_was:
            self.rebuild_ui()
        if not undo_was:
            self.refresh_dynamic_items()
        if old_m != m:
            if undo_was and self.live("anim") and old_m in self._method_ys:
                self.cv.coords(self._canvas_items["method_act"], int(round((16.0 + 10.0) * self.S)), int(round(self._method_ys[old_m] * self.S)))
                if old_m in self._radio_items:
                    self.cv.itemconfigure(self._radio_items[old_m], image=self.sprites["rad_on"])
                if m in self._radio_items:
                    self.cv.itemconfigure(self._radio_items[m], image=self.sprites["rad_off"])
            self.animate_radio(old_m, False)
            self.animate_radio(m, True)
            self.animate_method_card(old_m, m)

    def flip(self, key: str) -> None:
        undo_was = self._clear_undo()
        sw_from = self._capture_switch_fracs() if self.live("anim") else {}
        new_val = not bool(self.live(key))
        self.set_cfg(key, new_val)
        self.save()
        if undo_was:
            spec = {"kind": "sw_only", "sw_from": sw_from} if self.live("anim") else None
            self.rebuild_ui(anim_spec=spec)
            if self.live("anim"):
                if key == "swing":
                    self.animate_sub_scrim("pickaxe", new_val)
                elif key == "walk":
                    self.animate_sub_scrim("pace", new_val)
            return
        self.refresh_dynamic_items()
        self.animate_switch(key, new_val)
        if key == "swing":
            self.animate_sub_scrim("pickaxe", new_val)
        elif key == "walk":
            self.animate_sub_scrim("pace", new_val)

    def set_bool(self, key: str, val: bool) -> None:
        old_val = bool(self.live(key))
        undo_was = self._clear_undo()
        sw_from = self._capture_switch_fracs() if (undo_was and self.live("anim")) else {}
        auto_swing = (key == "mouse" and not self.live("swing"))
        auto_walk = (key == "stand" and not self.live("walk"))
        self.set_cfg(key, val)
        if auto_swing:
            self.set_cfg("swing", True)
        if auto_walk:
            self.set_cfg("walk", True)
        self.save()
        if key == "anim" and not val:
            self._stop_all_anims(snap=True)
            if undo_was:
                self.rebuild_ui(snap=True)
            else:
                self.animate_chip_pair("anim", False, snap=True)
                self.refresh_dynamic_items()
            return
        if undo_was:
            spec = {"kind": "sw_only", "sw_from": sw_from} if self.live("anim") else None
            self.rebuild_ui(anim_spec=spec)
        elif old_val != bool(val) or auto_swing or auto_walk:
            self.refresh_dynamic_items()
        if old_val != bool(val):
            self.animate_chip_pair(key, bool(val))
        if auto_swing:
            if not undo_was:
                self.animate_switch("swing", True)
            self.animate_sub_scrim("pickaxe", True)
        if auto_walk:
            if not undo_was:
                self.animate_switch("walk", True)
            self.animate_sub_scrim("pace", True)

    def bump_delay(self, which: str, delta: int) -> None:
        undo_was = self._clear_undo()
        lo = int(self.live("min"))
        hi = int(self.live("max"))
        if which == "min":
            lo = int(clamp(lo + delta, 1, 180))
            hi = max(hi, lo)
        else:
            hi = int(clamp(hi + delta, lo, 180))
        self.set_cfg("min", lo)
        self.set_cfg("max", hi)
        self.save()
        if undo_was:
            self.rebuild_ui()
        else:
            self.refresh_dynamic_items()
        self.flash_item(f"val_{which}", str(self.live(which)))

    def bump_turn(self, delta: int) -> None:
        undo_was = self._clear_undo()
        nv = int(clamp(int(self.live("turn_px")) + delta, 200, 20000))
        self.set_cfg("turn_px", nv)
        self.save()
        if undo_was:
            self.rebuild_ui()
        else:
            self.refresh_dynamic_items()
        self.flash_item("val_turn_px", str(nv))

    def reset_all(self) -> None:
        if self.running:
            return
        sw_from = self._capture_switch_fracs() if self.live("anim") else {}
        with self._state_lock:
            self.undo_snap = dict(self.cfg)
            cur_lang = self.cfg["lang"]
            self.cfg = dict(DEFAULTS)
            self.cfg["lang"] = cur_lang
        self.save()
        self.bind_hotkeys()
        self.add_log(self.tr("undo_msg"))
        self.rebuild_ui(anim_spec={"kind": "sw_only", "sw_from": sw_from} if self.live("anim") else None)

    def undo_reset(self) -> None:
        if self.undo_snap is None:
            return
        sw_from = self._capture_switch_fracs() if self.live("anim") else {}
        with self._state_lock:
            self.cfg = dict(self.undo_snap)
            self.undo_snap = None
        self.save()
        self.bind_hotkeys()
        self.add_log(self.tr("undo_done"))
        self.rebuild_ui(anim_spec={"kind": "sw_only", "sw_from": sw_from} if self.live("anim") else None)

    # ---------------- Layout-Independent Hotkeys ----------------
    def bind_hotkeys(self) -> None:
        if not keyboard:
            return
        for h in self.hotkeys:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self.hotkeys.clear()
        for role, cfg_k in (("start", "start_key"), ("stop", "stop_key")):
            try:
                spec = kb_hotkey_spec(str(self.live(cfg_k)))
                self.hotkeys.append(keyboard.add_hotkey(spec, lambda r=role: self.emit("cmd", (r, time.monotonic()))))
            except Exception:
                pass

    def begin_capture(self, which: str) -> None:
        self.capturing = which
        # Disable global keyboard hooks during rebind so pressing existing key doesn't fire Start/Stop
        if keyboard:
            for h in self.hotkeys:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self.hotkeys.clear()
        self.root.bind("<Key>", self.on_key)
        self.root.bind("<FocusOut>", lambda _e: self.end_capture() if self.capturing else None)
        self.root.focus_set()
        self.refresh_dynamic_items()

    def end_capture(self) -> None:
        self.capturing = None
        try:
            self.root.unbind("<Key>")
            self.root.unbind("<FocusOut>")
        except Exception:
            pass
        self.bind_hotkeys()
        self.refresh_dynamic_items()

    def on_key(self, e) -> None:
        if not self.capturing:
            return
        sym = (e.keysym or "").lower()
        if sym == "escape":
            self.end_capture()
            return
        if sym in ("return", "shift_l", "shift_r", "control_l", "control_r", "alt_l", "alt_r", "caps_lock", "tab"):
            return

        # Resolve physical Virtual-Key code cleanly regardless of Cyrillic/non-ASCII keyboard layout
        kc = int(getattr(e, "keycode", 0) or 0)
        key = NAME_BY_VK.get(kc)
        if not key and sym in VK_BY_NAME:
            key = sym
        if not key and len(sym) == 1:
            scan_vk = int(user32.VkKeyScanW(sym)) & 0xFF
            key = NAME_BY_VK.get(scan_vk)
        if not key:
            return

        if key in RESERVED_HOTKEYS:
            self.add_log(self.tr("err_key_res"))
            self.end_capture()
            return

        which = self.capturing
        other = self.live("stop_key" if which == "start" else "start_key")
        if key == other:
            self.add_log(self.tr("err_key_same"))
            self.end_capture()
            return

        self.set_cfg(f"{which}_key", key)
        self._clear_undo()
        self.save()
        self.add_log(f"{self.tr('log_key_set')}{key.upper()}")
        self.end_capture()

    def poll_hardware_hotkeys(self) -> None:
        if self.capturing is not None:
            return
        for role in ("start", "stop"):
            kname = str(self.live(f"{role}_key")).lower()
            vk = VK_BY_NAME.get(kname)
            if not vk:
                continue
            down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            prev = self._vk_prev.get(role, False)
            self._vk_prev[role] = down
            if down and not prev:
                if role == "start" and not self.running:
                    self.start()
                elif role == "stop" and self.running:
                    self.stop()

    # ---------------- Engine Run / Stop & Event Poll ----------------
    def start(self) -> None:
        if self.running:
            return
        method = int(self.live("method"))
        if method == 0 and not any(self.live(k) for k in ("human", "swing", "space", "walk", "mouse")):
            messagebox.showinfo(APP_NAME, self.tr("err_afk_req"))
            return
        try:
            check_templates_exist()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"{self.tr('err_notfound')}{e}")
            return

        if self._clear_undo():
            self.rebuild_ui()
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break

        self.stop_event.clear()
        self.busy_event.clear()
        self.running = True
        self.state = "starting"
        for hrid in list(self._hover_items.keys()):
            if not self._is_hover_eligible(hrid):
                self.anim_jobs.pop(f"hov:{hrid}", None)
                self._set_hover_visual(hrid, 0.0)
        if self.hover_id and not self._is_hover_eligible(self.hover_id):
            self.cv.configure(cursor="")
        self.detail_ref = {"key": "dt_afk_wait" if method == 0 else "dt_wait_game"}
        self.add_log(self.ref(self.detail_ref))
        self.refresh_dynamic_items()

        self.worker = threading.Thread(target=self.worker_run, args=(method,), daemon=True)
        self.worker.start()

    def worker_run(self, method: int) -> None:
        try:
            with mss.MSS() as cap:
                self.engine = Engine(self, cap)
                self.engine.run(method)
        except Exception as e:
            self.emit("error", str(e))
        finally:
            self.engine = None
            self.emit("finished", time.monotonic())

    def stop(self) -> None:
        if not self.running:
            return
        self.state = "stopping"
        self._finished_at = time.monotonic()
        self.stop_event.set()
        if self.engine:
            self.engine.release_all()
        self.refresh_dynamic_items()

    def poll(self) -> None:
        self.poll_hardware_hotkeys()
        changed = False
        try:
            while True:
                k, v = self.events.get_nowait()
                changed = True
                if k == "status":
                    self.state = str(v)
                    if v == "running":
                        self.add_log(self.tr("st_running"))
                elif k == "detail":
                    self.detail_ref = v
                elif k == "log":
                    self.add_log(self.ref(v) if isinstance(v, dict) else str(v))
                elif k == "error":
                    self.add_log(f"{self.tr('log_error')}{v}")
                elif k == "finished":
                    self.running = False
                    self.state = "ready"
                    fin_ts = float(v) if isinstance(v, (int, float)) else time.monotonic()
                    self._finished_at = max(self._finished_at, fin_ts)
                    self.detail_ref = {"key": "dt_idle"}
                    self.add_log(self.tr("st_stopped"))
                elif k == "cmd":
                    if isinstance(v, tuple) and len(v) == 2:
                        act, cmd_ts = str(v[0]), float(v[1])
                    else:
                        act, cmd_ts = str(v), time.monotonic()
                    if act == "start" and not self.running and cmd_ts > self._finished_at:
                        self.start()
                    elif act == "stop" and self.running:
                        self.stop()
        except queue.Empty:
            pass
        if changed:
            self.refresh_dynamic_items()
        self.root.after(55, self.poll)

    def close(self) -> None:
        if self._anim_after_id is not None:
            try:
                self.root.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None
        self.anim_jobs.clear()
        self.anim_running = False
        self._set_timer_res(False)
        self.stop_event.set()
        if self.engine:
            self.engine.release_all()
        self.root.destroy()


_SINGLETON_MUTEX = None


def acquire_single_instance() -> bool:
    """Ensure only one interactive GUI instance runs at a time on Windows."""
    global _SINGLETON_MUTEX
    if HEADLESS or os.environ.get("PIRATE_DUMP_PREVIEW"):
        return True
    try:
        h = kernel32.CreateMutexW(None, False, "Local\\PirateTokenFarmSingleton")
        if h and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            hwnd = user32.FindWindowW(None, APP_NAME)
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
            return False
        _SINGLETON_MUTEX = h
    except Exception:
        pass
    return True


def main() -> None:
    if not acquire_single_instance():
        return
    root = tk.Tk()
    app = App(root)
    if os.environ.get("PIRATE_DUMP_PREVIEW"):
        img = app.render_headless_preview()
        if img is not None:
            img.save(os.environ["PIRATE_DUMP_PREVIEW"])
        app.page = "set"
        app.rebuild_ui(snap=True)
        img2 = app.render_headless_preview()
        if img2 is not None and os.environ.get("PIRATE_DUMP_PREVIEW_SET"):
            img2.save(os.environ["PIRATE_DUMP_PREVIEW_SET"])
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
