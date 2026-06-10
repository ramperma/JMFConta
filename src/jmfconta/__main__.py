"""Punto de entrada de la aplicación."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from jmfconta import db
from jmfconta import config_store
from jmfconta.ui.main_window import MainWindow
from jmfconta.ui.theme import aplicar_tema


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JMFConta")
    app.setOrganizationName("JMFConta")

    translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(QLocale.Language.Spanish), "qtbase", "_", translations_path):
        app.installTranslator(translator)

    aplicar_tema(app)
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "jmfconta.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db.init_db(db_path)
    conn = db.connect(db_path)
    config_store.cargar_en_entorno(conn)
    win = MainWindow(conn)
    win.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
