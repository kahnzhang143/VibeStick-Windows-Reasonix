from __future__ import annotations

import os
import platform
from pathlib import Path


def _app_support_dir() -> Path:
    configured = os.environ.get("VIBE_STICK_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    system = platform.system()
    if system == "Windows":
        # Microsoft Store Python virtualizes parts of AppData for child-process
        # access. A home-directory state folder stays visible to Reasonix/Node.
        return Path.home() / ".vibestick"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "VibeStick"

    xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "vibestick"
    return Path.home() / ".local" / "state" / "vibestick"


APP_SUPPORT_DIR = _app_support_dir()
STATE_PATH = APP_SUPPORT_DIR / "state.json"
QUOTA_PATH = APP_SUPPORT_DIR / "quota.json"
CLAUDE_QUOTA_PATH = APP_SUPPORT_DIR / "claude-quota.json"
RECORDING_PATH = APP_SUPPORT_DIR / "recording.json"
HUD_STATE_PATH = APP_SUPPORT_DIR / "hud-state.json"
RECORDINGS_DIR = APP_SUPPORT_DIR / "Recordings"


def ensure_app_support() -> Path:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    return APP_SUPPORT_DIR
