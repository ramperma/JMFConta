"""Ventana principal con cabecera y pestañas."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .banco_tab import BancoTab
from .caja_tab import CajaTab
from .config_tab import ConfigTab
from .mappings_tab import MappingsTab
from .plan_cuentas_tab import PlanCuentasTab
from .pre_asientos_tab import PreAsientosTab
from .theme import COLOR_ACCENT, COLOR_TEXT_MUTED


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JMFConta — Generador de asientos SAGE")
        self.resize(1280, 820)
        self._conn = conn
        self._build()

    def _build(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Cabecera
        header = QFrame()
        header.setObjectName("appHeader")
        header.setStyleSheet(
            f"QFrame#appHeader {{ background: white; border-bottom: 1px solid #d8dde3; }}"
        )
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 16)
        hl.setSpacing(12)

        # Logo "chip" cuadrado con iniciales
        logo = QLabel("JM")
        logo.setFixedSize(42, 42)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"background: {COLOR_ACCENT}; color: white; border-radius: 10px; "
            f"font-weight: 800; font-size: 14pt; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )

        titles = QVBoxLayout()
        titles.setSpacing(0)
        t1 = QLabel("JMFConta")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        t1.setFont(f)
        t1.setStyleSheet("color: #1f2937;")
        t2 = QLabel("Generador de asientos SAGE · Libro de Caja y Banco")
        t2.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 9pt;")
        titles.addWidget(t1)
        titles.addWidget(t2)

        btn_salir = QPushButton("✕  Salir")
        btn_salir.setToolTip("Cerrar la aplicación")
        btn_salir.setStyleSheet(
            "QPushButton { color: #6b7280; border: 1px solid #d8dde3; border-radius: 6px; "
            "padding: 6px 14px; font-size: 9pt; background: white; }"
            "QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }"
        )
        btn_salir.clicked.connect(self.close)

        hl.addWidget(logo)
        hl.addLayout(titles, 1)
        hl.addWidget(btn_salir)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self._mappings_tab = MappingsTab(self._conn)
        self.tabs.addTab(PlanCuentasTab(self._conn), "📋  Plan de cuentas")
        self.tabs.addTab(CajaTab(self._conn, on_mapping_learned=self._mappings_tab._refill), "💵  Libro Caja")
        self.tabs.addTab(BancoTab(self._conn, on_mapping_learned=self._mappings_tab._refill), "🏦  Banco")
        self.tabs.addTab(self._mappings_tab, "🔗  Mappings")
        self.tabs.addTab(PreAsientosTab(self._conn), "📤  Pre-Asientos SAGE")
        self.tabs.addTab(ConfigTab(self._conn), "⚙️  Configuración")
        self.tabs.currentChanged.connect(self._actualizar_footer)

        # Footer
        footer = QFrame()
        footer.setStyleSheet(
            f"QFrame {{ background: #eef0f4; border-top: 1px solid #d8dde3; }}"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 6, 24, 6)
        self.lbl_footer = QLabel("Base de datos SQLite local · datos/jmfconta.db")
        self.lbl_footer.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        fl.addWidget(self.lbl_footer)
        fl.addStretch(1)
        self.lbl_periodo = QLabel("")
        self.lbl_periodo.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        fl.addWidget(self.lbl_periodo)

        root_layout.addWidget(header)
        root_layout.addWidget(self.tabs, 1)
        root_layout.addWidget(footer)

        self.setCentralWidget(root)
        self._actualizar_footer()

    def _actualizar_footer(self, *_):
        try:
            pend_caja = self._conn.execute(
                "SELECT COUNT(*) FROM movimiento_caja WHERE exported_at IS NULL"
            ).fetchone()[0]
            pend_banco = self._conn.execute(
                "SELECT COUNT(*) FROM movimiento_banco WHERE exported_at IS NULL"
            ).fetchone()[0]
        except sqlite3.Error:
            return
        if pend_caja or pend_banco:
            self.lbl_periodo.setText(
                f"Pendientes de exportar: {pend_caja} caja · {pend_banco} banco"
            )
        else:
            self.lbl_periodo.setText("Sin movimientos pendientes de exportar")

    def closeEvent(self, event):
        resp = QMessageBox.question(
            self,
            "Salir",
            "¿Cerrar JMFConta?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()
