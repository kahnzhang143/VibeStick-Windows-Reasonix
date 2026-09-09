import os
import unittest
from pathlib import Path
from unittest import mock

from vibe_stick.config import paths


class ConfigPathTests(unittest.TestCase):
    def test_explicit_data_dir_wins(self) -> None:
        with mock.patch.dict(os.environ, {"VIBE_STICK_DATA_DIR": "C:\\VibeStickData"}):
            self.assertEqual(paths._app_support_dir(), Path("C:\\VibeStickData"))

    def test_windows_uses_home_state_directory(self) -> None:
        with mock.patch.object(paths.platform, "system", return_value="Windows"):
            with mock.patch.object(paths.Path, "home", return_value=Path("C:\\Users\\tester")):
                self.assertEqual(paths._app_support_dir(), Path("C:\\Users\\tester") / ".vibestick")


if __name__ == "__main__":
    unittest.main()
