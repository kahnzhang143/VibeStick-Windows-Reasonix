from __future__ import annotations

import ctypes
import platform
import subprocess
import time
from dataclasses import dataclass
from ctypes import wintypes
from typing import Protocol


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [
        ("mi", _MouseInput),
        ("ki", _KeyboardInput),
        ("hi", _HardwareInput),
    ]


class _Input(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _InputUnion),
    ]


@dataclass
class PasteResult:
    success: bool
    message: str


class PasteInjector(Protocol):
    def paste(self, text: str, press_enter: bool = False) -> PasteResult:
        ...


def create_paste_injector() -> PasteInjector:
    system = platform.system()
    if system == "Darwin":
        return MacPasteInjector()
    if system == "Windows":
        return WindowsPasteInjector()
    return UnsupportedPasteInjector(system)


class UnsupportedPasteInjector:
    def __init__(self, system: str) -> None:
        self.system = system or "unknown"

    def paste(self, text: str, press_enter: bool = False) -> PasteResult:
        del text, press_enter
        return PasteResult(False, f"Automatic paste is not available on {self.system}")


class MacPasteInjector:
    def paste(self, text: str, press_enter: bool = False) -> PasteResult:
        text = text.strip()
        if not text:
            return PasteResult(False, "No text to paste")
        if platform.system() != "Darwin":
            return PasteResult(False, "Automatic paste is only available on macOS")

        previous_text = self._read_clipboard()
        set_result = self._set_clipboard(text)
        if not set_result.success:
            return set_result

        script = [
            'tell application "System Events" to keystroke "v" using command down',
        ]
        if press_enter:
            script.extend([
                "delay 0.12",
                'tell application "System Events" to key code 36',
            ])

        args = ["osascript"]
        for line in script:
            args.extend(["-e", line])
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=5)
        time.sleep(0.2)
        if previous_text is not None:
            self._set_clipboard(previous_text)

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "macOS paste failed").strip()
            return PasteResult(False, message)
        return PasteResult(True, "Pasted into the focused app")

    def _read_clipboard(self) -> str | None:
        try:
            result = subprocess.run(
                ["pbpaste"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return result.stdout

    def _set_clipboard(self, text: str) -> PasteResult:
        try:
            result = subprocess.run(
                ["pbcopy"],
                input=text,
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return PasteResult(False, f"Clipboard write failed: {exc}")
        if result.returncode != 0:
            message = (result.stderr or "Clipboard write failed").strip()
            return PasteResult(False, message)
        return PasteResult(True, "Clipboard updated")


class WindowsPasteInjector:
    _INPUT_KEYBOARD = 1
    _KEYEVENTF_UNICODE = 0x0004
    _KEYEVENTF_KEYUP = 0x0002
    _VK_RETURN = 0x0D

    def paste(self, text: str, press_enter: bool = False) -> PasteResult:
        text = text.strip()
        if not text:
            return PasteResult(False, "No text to paste")
        if platform.system() != "Windows":
            return PasteResult(False, "Windows paste is only available on Windows")

        try:
            self._send_unicode_text(text)
            if press_enter:
                time.sleep(0.12)
                self._send_key(self._VK_RETURN)
        except OSError as exc:
            return PasteResult(False, f"Windows input injection failed: {exc}")

        return PasteResult(True, "Typed into the focused app")

    def _send_unicode_text(self, text: str) -> None:
        user32 = ctypes.windll.user32
        encoded = text.encode("utf-16-le")
        units = [
            int.from_bytes(encoded[index:index + 2], "little")
            for index in range(0, len(encoded), 2)
        ]
        if not units:
            return

        events: list[_Input] = []
        for unit in units:
            events.append(
                _Input(
                    type=self._INPUT_KEYBOARD,
                    ki=_KeyboardInput(0, unit, self._KEYEVENTF_UNICODE, 0, 0),
                )
            )
            events.append(
                _Input(
                    type=self._INPUT_KEYBOARD,
                    ki=_KeyboardInput(
                        0,
                        unit,
                        self._KEYEVENTF_UNICODE | self._KEYEVENTF_KEYUP,
                        0,
                        0,
                    ),
                )
            )
        event_array = (_Input * len(events))(*events)
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        sent = user32.SendInput(len(events), event_array, ctypes.sizeof(_Input))
        if sent != len(events):
            raise OSError(f"SendInput sent {sent} of {len(events)} Unicode keyboard events")

    def _send_key(self, key: int) -> None:
        self._send_key_event(key, key_up=False)
        self._send_key_event(key, key_up=True)

    def _send_key_event(self, key: int, *, key_up: bool) -> None:
        user32 = ctypes.windll.user32
        user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, wintypes.WPARAM]
        user32.keybd_event.restype = None
        flags = self._KEYEVENTF_KEYUP if key_up else 0
        user32.keybd_event(key, 0, flags, 0)
