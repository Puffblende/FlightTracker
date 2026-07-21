import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


class PresetLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_save_preset_impl_reloads_saved_preset(self) -> None:
        win = MainWindow()
        calls: list[str] = []
        win._load_preset_by_name = lambda name: calls.append(name)  # type: ignore[assignment]

        win._save_preset_impl('demo-preset')

        self.assertEqual(calls, ['demo-preset'])


if __name__ == '__main__':
    unittest.main()
