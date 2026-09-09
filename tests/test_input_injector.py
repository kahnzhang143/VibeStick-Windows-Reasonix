import ctypes
import unittest
from unittest import mock

from vibe_stick.paste import input_injector


class PasteInjectorTests(unittest.TestCase):
    def test_windows_input_structure_has_native_size(self) -> None:
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(input_injector._Input), expected)

    def test_factory_selects_windows_injector(self) -> None:
        with mock.patch.object(input_injector.platform, "system", return_value="Windows"):
            injector = input_injector.create_paste_injector()

        self.assertIsInstance(injector, input_injector.WindowsPasteInjector)

    def test_factory_selects_mac_injector(self) -> None:
        with mock.patch.object(input_injector.platform, "system", return_value="Darwin"):
            injector = input_injector.create_paste_injector()

        self.assertIsInstance(injector, input_injector.MacPasteInjector)

    def test_windows_paste_sends_unicode_without_clipboard(self) -> None:
        injector = input_injector.WindowsPasteInjector()
        with mock.patch.object(input_injector.platform, "system", return_value="Windows"):
            with mock.patch.object(injector, "_send_unicode_text") as send_unicode:
                result = injector.paste("中文语音")

        self.assertTrue(result.success)
        send_unicode.assert_called_once_with("中文语音")


if __name__ == "__main__":
    unittest.main()
