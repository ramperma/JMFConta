"""Pestaña de Pre-Asientos: previsualización y exportación a Excel SAGE."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import repository
from ..sage.exporter import exportar_sage
from ..sage.rules import AsientoGenerado
from .estilos import set_cargo_abono, set_cuenta, set_importe, set_text
from .theme import COLOR_TEXT_MUTED


COL_AS, COL_PER, COL_FECHA, COL_ORDEN, COL_DH, COL_CUENTA, COL_IMP, COL_COM = range(8)


class PreAsientosTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._asientos: list[AsientoGenerado] = []
        self._build()

    def _build(self):
        titulo = QLabel("Pre-Asientos SAGE")
        titulo.setProperty("role", "title")
        subtitulo = QLabel(
            "Genera la previsualización a partir de Caja + Banco y exporta el Excel con el formato "
            "que espera SAGE para importar asientos."
        )
        subtitulo.setProperty("role", "muted")
        subtitulo.setWordWrap(True)

        # Tarjeta de resumen
        self.resumen_frame = QFrame()
        self.resumen_frame.setObjectName("resumenFrame")
        rl = QHBoxLayout(self.resumen_frame)
        rl.setContentsMargins(16, 12, 16, 12)
        self.lbl_asientos = QLabel("0 asientos")
        self.lbl_lineas = QLabel("0 líneas")
        self.lbl_total = QLabel("0,00 €")
        for lbl in (self.lbl_asientos, self.lbl_lineas, self.lbl_total):
            f = lbl.font()
            f.setPointSize(11)
            f.setBold(True)
            lbl.setFont(f)
        rl.addWidget(self.lbl_asientos)
        rl.addSpacing(24)
        rl.addWidget(self.lbl_lineas)
        rl.addStretch(1)
        rl.addWidget(self.lbl_total)

        self.btn_generar = QPushButton("Generar previsualización")
        self.btn_generar.setProperty("primary", True)
        self.btn_generar.clicked.connect(self._generar)
        self.btn_exportar = QPushButton("Exportar a Excel SAGE…")
        self.btn_exportar.setProperty("primary", True)
        self.btn_exportar.setEnabled(False)
        self.btn_exportar.clicked.connect(self._exportar)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.btn_generar)
        btns.addWidget(self.btn_exportar)
        btns.addStretch(1)

        cols = ["Asiento", "Periodo", "Fecha", "Ord.", "D/H", "Cuenta", "Importe", "Comentario"]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(COL_AS, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_PER, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_FECHA, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_ORDEN, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_DH, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_CUENTA, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_IMP, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_COM, QHeaderView.ResizeMode.Stretch)

        self.lbl_info = QLabel("Pulsa 'Generar previsualización' para crear los asientos desde los movimientos.")
        self.lbl_info.setProperty("role", "muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addWidget(self.resumen_frame)
        layout.addLayout(btns)
        layout.addWidget(self.tabla, 1)
        layout.addWidget(self.lbl_info)

    def _generar(self):
        self._asientos = repository.generar_asientos_caja(self._conn) + repository.generar_asientos_banco(self._conn)
        self._asientos.sort(key=lambda a: (a.fecha, a.descripcion))

        total = len(self._asientos)
        total_lineas = sum(len(a.lineas) for a in self._asientos)
        total_imp = sum(sum(l.importe for l in a.lineas) for a in self._asientos)
        self.lbl_asientos.setText(f"{total} asientos")
        self.lbl_lineas.setText(f"{total_lineas} líneas")
        self.lbl_total.setText(f"{total_imp:,.2f} €")

        self.tabla.setRowCount(total_lineas)
        r = 0
        for n, ast in enumerate(self._asientos, start=1):
            for linea in ast.lineas:
                it_as = QTableWidgetItem(str(n))
                f = it_as.font()
                f.setBold(True)
                it_as.setFont(f)
                it_as.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(r, COL_AS, it_as)

                set_text(self._cell(r, COL_PER), ast.periodo, align=Qt.AlignmentFlag.AlignCenter)
                set_text(self._cell(r, COL_FECHA), ast.fecha.isoformat())
                set_text(self._cell(r, COL_ORDEN), linea.orden, align=Qt.AlignmentFlag.AlignCenter)
                set_cargo_abono(self._cell(r, COL_DH), linea.cargo_abono)
                set_cuenta(self._cell(r, COL_CUENTA), linea.cuenta)
                set_importe(self._cell(r, COL_IMP), linea.importe)
                set_text(self._cell(r, COL_COM), linea.comentario or ast.descripcion,
                         color=COLOR_TEXT_MUTED if not linea.comentario else None)
                r += 1

        self.lbl_info.setText(
            f"{total} asiento(s) generado(s). Revisa las cuentas y comentarios antes de exportar."
        )
        self.btn_exportar.setEnabled(total > 0)

    def _cell(self, row, col):
        item = self.tabla.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tabla.setItem(row, col, item)
        return item

    def _exportar(self):
        if not self._asientos:
            return
        default_name = f"asientos_sage_{self._asientos[0].fecha.isoformat()[:7]}.xlsx"
        out, _ = QFileDialog.getSaveFileName(
            self, "Guardar Excel SAGE", default_name, "Excel (*.xlsx)"
        )
        if not out:
            return
        if not out.lower().endswith(".xlsx"):
            out += ".xlsx"
        try:
            exportar_sage(self._asientos, out)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        n_caja = repository.marcar_exportados_caja(self._conn)
        n_banco = repository.marcar_exportados_banco(self._conn)
        self._asientos = []
        self.btn_exportar.setEnabled(False)
        self.lbl_info.setText(
            f"✓ Exportado. {n_caja} mov. caja + {n_banco} mov. banco marcados como generados."
        )
        QMessageBox.information(self, "Exportado", f"Archivo guardado en:\n{out}")
