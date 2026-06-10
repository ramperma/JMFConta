"""Pestaña del plan de cuentas."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import repository
from ..importers.plan_cuentas import importar_plan_cuentas


class PlanCuentasTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._build()
        self._refill("")

    def _build(self):
        titulo = QLabel("Plan de Cuentas")
        titulo.setProperty("role", "title")
        subtitulo = QLabel("Carga el plan desde el Excel y búscalo por código o descripción.")
        subtitulo.setProperty("role", "muted")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por código o descripción… (ej. 628, IBERDROLA, COMEDOR)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refill)

        self.btn_cargar = QPushButton("Cargar desde Excel…")
        self.btn_cargar.setProperty("primary", True)
        self.btn_cargar.clicked.connect(self._cargar_desde_excel)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.search, 1)
        top.addWidget(self.btn_cargar)

        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(["Código", "Descripción"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        f = QFont("JetBrains Mono")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(10)
        self.tabla.setFont(f)

        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setProperty("role", "resumen")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addLayout(top)
        layout.addWidget(self.tabla, 1)
        layout.addWidget(self.lbl_resumen)

    def _refill(self, texto: str):
        filas = repository.buscar_cuenta(self._conn, texto, limit=2000)
        self.tabla.setRowCount(len(filas))
        for r, (codigo, desc) in enumerate(filas):
            it0 = QTableWidgetItem(codigo)
            f = it0.font()
            f.setBold(True)
            it0.setFont(f)
            self.tabla.setItem(r, 0, it0)
            self.tabla.setItem(r, 1, QTableWidgetItem(desc))
        total = self._conn.execute("SELECT COUNT(*) c FROM cuenta").fetchone()["c"]
        self.lbl_resumen.setText(
            f"{len(filas)} resultado(s)  ·  total en plan: {total} cuentas"
        )

    def _cargar_desde_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar plan de cuentas", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            cuentas = importar_plan_cuentas(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer el archivo:\n{e}")
            return
        if not cuentas:
            QMessageBox.warning(self, "Aviso", "El archivo no contiene cuentas.")
            return
        n = repository.cargar_plan(self._conn, cuentas)
        repository.registrar_importacion(self._conn, "PLAN", Path(path).name, n)
        QMessageBox.information(self, "Plan cargado", f"{n} cuentas importadas.")
        self._refill(self.search.text())
