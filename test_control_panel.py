import unittest
import tempfile
from pathlib import Path
import struct
from control_panel import choose_button, validate_ezd, is_open_menu, open_accelerator_commands


class SelectionTests(unittest.TestCase):
    def test_open_accelerator_excludes_mark_and_other_modifiers(self):
        data = b"".join(struct.pack("<HHHH", *row) for row in [
            (0x0B, ord("O"), 0xE101, 0),
            (3, 113, 0x8038, 0),
            (0x0D, ord("O"), 99, 0),
            (0x19, ord("O"), 100, 0)])
        self.assertEqual(open_accelerator_commands(data), {0xE101})

    def test_unicode_file_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "طرح تست.EZD"
            path.write_bytes(b"fixture")
            self.assertEqual(validate_ezd(path), path.resolve())
            wrong = Path(folder) / "wrong.txt"
            wrong.write_text("test")
            with self.assertRaises(ValueError):
                validate_ezd(wrong)
            with self.assertRaises(OSError):
                validate_ezd(Path(folder) / "missing.ezd")

    def test_only_open_menu_matches(self):
        self.assertTrue(is_open_menu("&Open...\tCtrl+O"))
        for label in ("Save As...", "Reopen", "Open recent", "Mark"):
            self.assertFalse(is_open_menu(label))

    def control(self, text, **kwargs):
        return dict({"class": "Button", "text": text, "enabled": True, "visible": True}, **kwargs)

    def test_red_never_selects_mark(self):
        red = self.control("Red(F1)")
        self.assertIs(choose_button([self.control("Mark(F2)"), red], "red"), red)

    def test_ambiguous_hidden_disabled_and_wrong_labels_rejected(self):
        for controls in ([self.control("Mark(F2)")] * 2,
                         [self.control("Mark(F2)", enabled=False)],
                         [self.control("Mark(F2)", visible=False)],
                         [self.control("Mark")], []):
            with self.assertRaises(RuntimeError):
                choose_button(controls, "mark")


if __name__ == "__main__":
    unittest.main()
