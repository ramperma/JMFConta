"""Punto de entrada de la aplicación."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jmfconta import db
from jmfconta.ui.main_window import MainWindow
from jmfconta.ui.theme import aplicar_tema


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JMFConta")
    app.setOrganizationName("JMFConta")
    aplicar_tema(app)
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "jmfconta.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db.init_db(db_path)
    conn = db.connect(db_path)
    win = MainWindow(conn)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
