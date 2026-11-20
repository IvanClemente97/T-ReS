import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from t_res.dashboard.widgets import RaceMapWidget


class DashboardWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_map_target_rect_fits_pixmap_without_qsize_conversion_errors(self):
        widget = RaceMapWidget()
        widget.resize(640, 480)
        widget._pixmap = QPixmap(100, 50)

        target = widget._target_rect()

        self.assertEqual(target.width(), 608)
        self.assertEqual(target.height(), 304)
        self.assertEqual(target.center().x(), 320)
        self.assertEqual(target.center().y(), 240)


if __name__ == "__main__":
    unittest.main()
