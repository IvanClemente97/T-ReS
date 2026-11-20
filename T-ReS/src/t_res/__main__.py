"""T-ReS executable entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from t_res.dashboard.window import TReSWindow


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("T-ReS")
    application.setOrganizationName("T-ReS")
    window = TReSWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
