"""Pestaña de Mappings denom/mas_datos -> cuenta."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import repository
from .cuenta_picker import CuentaPickerDialog


class MappingsTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._build()
        self._refill()

    def _build(self):
        titulo = QLabel("Mappings denominación → cuenta")
        titulo.setProperty("role", "title")
        subtitulo = QLabel(
            "Las asignaciones que el programa aprende al pulsar 'Aprender mapping' en Caja o Banco. "
            "También puedes crear, editar o eliminar mappings manualmente."
        )
        subtitulo.setProperty("role", "muted")
        subtitulo.setWordWrap(True)

        self.filtro = QComboBox()
        self.filtro.addItems(["Todos", "Caja", "Banco"])
        self.filtro.currentTextChanged.connect(self._on_filtro)

        self.btn_nuevo = QPushButton("Nuevo mapping…")
        self.btn_nuevo.setProperty("primary", True)
        self.btn_nuevo.clicked.connect(self._nuevo)
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_eliminar.setProperty("danger", True)
        self.btn_eliminar.clicked.connect(self._eliminar)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Origen:"))
        top.addWidget(self.filtro)
        top.addStretch(1)
        top.addWidget(self.btn_nuevo)
        top.addWidget(self.btn_eliminar)

        cols = ["Origen", "Clave (denominación / mas_datos)", "Cuenta", "Descripción", "Notas", "Actualizado"]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

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

    def _on_filtro(self, texto: str):
        self._refill()

    def _refill(self):
        origen = None
        f = self.filtro.currentText()
        if f == "Caja":
            origen = "CAJA"
        elif f == "Banco":
            origen = "BANCO"
        rows = repository.listar_mappings(self._conn, origen)
        self.tabla.setRowCount(len(rows))
        for r, row in enumerate(rows):
            # Origen con color semántico
            it0 = QTableWidgetItem("Caja" if row["origen"] == "CAJA" else "Banco")
            color = "#1d4ed8" if row["origen"] == "CAJA" else "#b45309"
            from PySide6.QtGui import QBrush, QColor
            it0.setForeground(QBrush(QColor(color)))
            f0 = it0.font()
            f0.setBold(True)
            it0.setFont(f0)
            self.tabla.setItem(r, 0, it0)
            # Clave
            self.tabla.setItem(r, 1, QTableWidgetItem(row["clave"]))
            # Cuenta mono bold
            it2 = QTableWidgetItem(row["cuenta"])
            f2 = QFont("JetBrains Mono")
            f2.setStyleHint(QFont.StyleHint.Monospace)
            f2.setBold(True)
            it2.setFont(f2)
            self.tabla.setItem(r, 2, it2)
            self.tabla.setItem(r, 3, QTableWidgetItem(row["cuenta_desc"] or ""))
            self.tabla.setItem(r, 4, QTableWidgetItem(row["notas"] or ""))
            self.tabla.setItem(r, 5, QTableWidgetItem(row["updated_at"]))
        self.lbl_resumen.setText(f"{len(rows)} mapping(s)")

    def _nuevo(self):
        items = ["Caja", "Banco"]
        origen_label, ok = QInputDialog.getItem(self, "Origen", "Origen del mapping:", items, 0, False)
        if not ok:
            return
        origen = "CAJA" if origen_label == "Caja" else "BANCO"
        clave, ok = QInputDialog.getText(self, "Clave", "Denominación o mas_datos:")
        if not ok or not clave.strip():
            return
        dlg = CuentaPickerDialog(self._conn, self)
        if dlg.exec() == CuentaPickerDialog.DialogCode.Accepted and dlg.cuenta:
            repository.set_mapping(self._conn, origen, clave.strip(), dlg.cuenta)
            self._refill()

    def _eliminar(self):
        rows = self.tabla.selectionModel().selectedRows()
        if not rows:
            return
        if QMessageBox.question(self, "Eliminar", f"¿Borrar {len(rows)} mapping(s)?") != QMessageBox.StandardButton.Yes:
            return
        for r in rows:
            origen = "CAJA" if self.tabla.item(r.row(), 0).text() == "Caja" else "BANCO"
            clave = self.tabla.item(r.row(), 1).text()
            repository.eliminar_mapping(self._conn, origen, clave)
        self._refill()
