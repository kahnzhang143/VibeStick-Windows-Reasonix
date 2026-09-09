from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TextIO

from vibe_stick.server.app import main

_LOG_STREAM: TextIO | None = None


def _configure_stdio_logging() -> None:
    global _LOG_STREAM
    log_path = os.environ.get("VIBE_STICK_LOG_FILE", "").strip()
    if not log_path:
        return
    path = Path(log_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOG_STREAM = path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = _LOG_STREAM
    sys.stderr = _LOG_STREAM


if __name__ == "__main__":
    _configure_stdio_logging()
    main()
