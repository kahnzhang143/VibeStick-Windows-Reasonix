import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vibe_stick import __main__


class MainLoggingTests(unittest.TestCase):
    def test_logging_is_unchanged_without_configuration(self) -> None:
        stdout = __main__.sys.stdout
        with mock.patch.dict(os.environ, {}, clear=True):
            __main__._configure_stdio_logging()

        self.assertIs(__main__.sys.stdout, stdout)

    def test_logging_opens_configured_utf8_file(self) -> None:
        original_stdout = __main__.sys.stdout
        original_stderr = __main__.sys.stderr
        original_stream = __main__._LOG_STREAM
        try:
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "bridge.log"
                with mock.patch.dict(os.environ, {"VIBE_STICK_LOG_FILE": str(log_path)}):
                    __main__._configure_stdio_logging()
                    print("中文日志", flush=True)
                __main__._LOG_STREAM.close()
                self.assertIn("中文日志", log_path.read_text(encoding="utf-8"))
        finally:
            __main__.sys.stdout = original_stdout
            __main__.sys.stderr = original_stderr
            __main__._LOG_STREAM = original_stream


if __name__ == "__main__":
    unittest.main()
