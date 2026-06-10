"""Pestaña de Pre-Asientos: previsualización, exportación a Excel SAGE e historial."""
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
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import repository
from ..sage.exporter import exportar_sage
from ..sage.rules import AsientoGenerado, LineaAsiento
from .estilos import set_cargo_abono, set_cuenta, set_importe, set_text
from .theme import COLOR_TEXT_MUTED

COL_AS, COL_PER, COL_FECHA, COL_ORDEN, COL_DH, COL_CUENTA, COL_IMP, COL_COM = range(8)

_HIST_COL_FECHA, _HIST_COL_ARCHIVO, _HIST_COL_ASIENTOS, _HIST_COL_LINEAS, _HIST_COL_ACCION = range(5)


class PreAsientosTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._asientos: list[AsientoGenerado] = []
        self._historial_visible = False
        self._build()
        self._refill_historial()

    def _build(self):
        titulo = QLabel("Pre-Asientos SAGE")
        titulo.setProperty("role", "title")
        subtitulo = QLabel(
            "Genera la previsualización a partir de Caja + Banco y exporta el Excel con el formato "
            "que espera SAGE para importar asientos."
        )
        subtitulo.setProperty("role", "muted")
        subtitulo.setWordWrap(True)

        self.resumen_frame = QFrame()
        self.resumen_frame.setObjectName("resumenFrame")
        rl = QHBoxLayout(self.resumen_frame)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(12)
        self.lbl_asientos = QLabel("0 asientos")
        self.lbl_asientos.setProperty("chip", "blue")
        self.lbl_lineas = QLabel("0 líneas")
        self.lbl_lineas.setProperty("chip", "gray")
        self.lbl_total = QLabel("0,00 €")
        self.lbl_total.setProperty("chip", "green")
        rl.addWidget(self.lbl_asientos)
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

        self.lbl_info = QLabel(
            "Pulsa 'Generar previsualización' para crear los asientos desde los movimientos."
        )
        self.lbl_info.setProperty("role", "muted")

        # Historial colapsable
        self.btn_historial = QPushButton("▼ Historial")
        self.btn_historial.clicked.connect(self._toggle_historial)
        self.btn_historial.setToolTip("Mostrar historial de exportaciones anteriores")

        self.lbl_hist_vacio = QLabel("Todavía no hay exportaciones registradas.")
        self.lbl_hist_vacio.setProperty("role", "muted")
        self.lbl_hist_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hist_cols = ["Fecha", "Archivo", "Asientos", "Líneas", "Acción"]
        self.tabla_hist = QTableWidget(0, len(hist_cols))
        self.tabla_hist.setHorizontalHeaderLabels(hist_cols)
        self.tabla_hist.verticalHeader().setVisible(False)
        self.tabla_hist.setAlternatingRowColors(True)
        self.tabla_hist.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_hist.verticalHeader().setDefaultSectionSize(44)
        hh = self.tabla_hist.horizontalHeader()
        hh.setSectionResizeMode(_HIST_COL_FECHA, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_HIST_COL_ARCHIVO, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_HIST_COL_ASIENTOS, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_HIST_COL_LINEAS, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_HIST_COL_ACCION, QHeaderView.ResizeMode.Fixed)
        self.tabla_hist.setColumnWidth(_HIST_COL_ACCION, 280)
        self.tabla_hist.setVisible(False)
        self.lbl_hist_vacio.setVisible(False)
        self.tabla_hist.setMaximumHeight(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addWidget(self.resumen_frame)
        layout.addLayout(btns)
        layout.addWidget(self.tabla, 1)
        layout.addWidget(self.lbl_info)
        layout.addWidget(self.btn_historial)
        layout.addWidget(self.lbl_hist_vacio)
        layout.addWidget(self.tabla_hist)

    def _toggle_historial(self):
        self._historial_visible = not self._historial_visible
        self.btn_historial.setText("▲ Historial" if self._historial_visible else "▼ Historial")
        if self._historial_visible:
            self._refill_historial()
        else:
            self.tabla_hist.setVisible(False)
            self.lbl_hist_vacio.setVisible(False)

    def _refill_historial(self):
        rows = repository.listar_historial_exportacion(self._conn)
        tiene_datos = len(rows) > 0
        self.tabla_hist.setVisible(self._historial_visible and tiene_datos)
        self.lbl_hist_vacio.setVisible(self._historial_visible and not tiene_datos)

        self.tabla_hist.setRowCount(len(rows))
        for r, row in enumerate(rows):
            ts = row["created_at"]
            fecha_txt = ts[:10] if ts else ""
            set_text(self._cell_hist(r, _HIST_COL_FECHA), fecha_txt)
            set_text(self._cell_hist(r, _HIST_COL_ARCHIVO), row["archivo"])
            set_text(
                self._cell_hist(r, _HIST_COL_ASIENTOS),
                str(row["n_asientos"]),
                align=Qt.AlignmentFlag.AlignCenter,
            )
            set_text(
                self._cell_hist(r, _HIST_COL_LINEAS),
                str(row["n_lineas"]),
                align=Qt.AlignmentFlag.AlignCenter,
            )

            acciones = QWidget()
            al = QHBoxLayout(acciones)
            al.setContentsMargins(4, 2, 4, 2)
            al.setSpacing(4)
            btn_recu = QPushButton("Recuperar")
            btn_recu.setStyleSheet("QPushButton { padding: 4px 10px; border-radius: 3px; }")
            btn_recu.setToolTip("Cargar los asientos de esta exportación en la tabla")
            btn_recu.clicked.connect(
                lambda checked, export_id=row["id"]: self._recuperar_exportacion(export_id)
            )
            al.addWidget(btn_recu, 1)
            btn_undo = QPushButton("Deshacer")
            btn_undo.setProperty("danger", True)
            btn_undo.setStyleSheet("QPushButton { padding: 4px 10px; border-radius: 3px; }")
            btn_undo.setToolTip("Revertir esta exportación: los movimientos vuelven a estar pendientes")
            btn_undo.clicked.connect(
                lambda checked, export_id=row["id"]: self._deshacer_exportacion(export_id)
            )
            al.addWidget(btn_undo, 1)
            self.tabla_hist.setCellWidget(r, _HIST_COL_ACCION, acciones)

    def _cell_hist(self, row: int, col: int) -> QTableWidgetItem:
        item = self.tabla_hist.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tabla_hist.setItem(row, col, item)
        return item

    def _generar(self):
        repository.limpiar_asientos_no_exportados(self._conn)

        asientos_caja = repository.generar_asientos_caja(self._conn)
        asientos_banco = repository.generar_asientos_banco(self._conn)

        self._asientos = asientos_caja + asientos_banco
        self._asientos.sort(key=lambda a: (a.fecha, a.descripcion))

        # Contar cuantos movimientos totales hay en BD para diagnóstico
        total_caja_db = self._conn.execute("SELECT COUNT(*) FROM movimiento_caja WHERE exported_at IS NULL").fetchone()[0]
        total_banco_db = self._conn.execute("SELECT COUNT(*) FROM movimiento_banco WHERE exported_at IS NULL").fetchone()[0]

        try:
            repository._persistir_asientos(self._conn, asientos_caja, "CAJA")
            repository._persistir_asientos(self._conn, asientos_banco, "BANCO")
        except Exception as e:
            QMessageBox.warning(
                self, "Aviso",
                f"Los asientos se generaron pero no se pudieron guardar en BD:\n{e}\n\n"
                "Revisa que todas las cuentas del plan de cuentas existan "
                "(5700000, 5720002, y las contrapartidas de tus movimientos)."
            )

        self._llenar_tabla(self._asientos, len(asientos_caja), len(asientos_banco), total_caja_db, total_banco_db)
        self.btn_exportar.setEnabled(len(self._asientos) > 0)

    def _llenar_tabla(self, asientos: list[AsientoGenerado], n_gen_caja: int = 0, n_gen_banco: int = 0, total_caja: int = 0, total_banco: int = 0):
        total = len(asientos)
        total_lineas = sum(len(a.lineas) for a in asientos)
        total_imp = sum(sum(l.importe for l in a.lineas) for a in asientos)
        self.lbl_asientos.setText(f"{total} asientos")
        self.lbl_lineas.setText(f"{total_lineas} líneas")
        self.lbl_total.setText(f"{total_imp:,.2f} €")

        # Determinar si cada asiento ya fue exportado (por su fuente)
        exportado_cache: dict[int, bool] = {}
        for a in asientos:
            if a.fuente_id is not None and a.fuente_tipo:
                tabla = "movimiento_caja" if a.fuente_tipo == "CAJA" else "movimiento_banco"
                row_export = self._conn.execute(
                    f"SELECT exported_at FROM {tabla} WHERE id = ?", (a.fuente_id,)
                ).fetchone()
                exportado_cache[a.fuente_id] = bool(row_export and row_export["exported_at"])

        self.tabla.setRowCount(total_lineas)
        r = 0
        for n, ast in enumerate(asientos, start=1):
            fue_exportado = exportado_cache.get(ast.fuente_id, False)
            for linea in ast.lineas:
                it_as = QTableWidgetItem(str(n))
                f_as = it_as.font()
                f_as.setBold(True)
                it_as.setFont(f_as)
                it_as.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(r, COL_AS, it_as)

                set_text(self._cell(r, COL_PER), ast.periodo, align=Qt.AlignmentFlag.AlignCenter)
                set_text(self._cell(r, COL_FECHA), ast.fecha.isoformat())
                set_text(self._cell(r, COL_ORDEN), linea.orden, align=Qt.AlignmentFlag.AlignCenter)
                set_cargo_abono(self._cell(r, COL_DH), linea.cargo_abono)
                set_cuenta(self._cell(r, COL_CUENTA), linea.cuenta)
                set_importe(self._cell(r, COL_IMP), linea.importe)
                set_text(
                    self._cell(r, COL_COM),
                    linea.comentario or ast.descripcion,
                    color=COLOR_TEXT_MUTED if not linea.comentario else None,
                )

                if fue_exportado:
                    _gris = QColor("#9ca3af")
                    for col in range(self.tabla.columnCount()):
                        item = self.tabla.item(r, col)
                        if item:
                            item.setForeground(_gris)

                r += 1

        n_exported = sum(1 for v in exportado_cache.values() if v)
        info = f"{total} asiento(s) generado(s)"
        if n_gen_caja or n_gen_banco:
            info += f" ({n_gen_caja} caja + {n_gen_banco} banco)"
        info += "."
        if n_exported:
            info += f" {n_exported} ya exportados anteriormente."
        if total_caja > n_gen_caja or total_banco > n_gen_banco:
            saltos_caja = total_caja - n_gen_caja
            saltos_banco = total_banco - n_gen_banco
            partes = []
            if saltos_caja: partes.append(f"{saltos_caja} caja")
            if saltos_banco: partes.append(f"{saltos_banco} banco")
            info += f" {', '.join(partes)} movimiento(s) omitido(s) — sin cuenta asignada o sin fecha."
        else:
            info += " Revisa las cuentas y comentarios antes de exportar."
        self.lbl_info.setText(info)
        self._refill_historial()

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

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        n_caja = repository.marcar_exportados_caja(self._conn, ts)
        n_banco = repository.marcar_exportados_banco(self._conn, ts)

        n_lineas = sum(len(a.lineas) for a in self._asientos)
        periodo = self._asientos[0].periodo if self._asientos else None
        repository.registrar_exportacion(
            self._conn,
            archivo=Path(out).name,
            n_asientos=len(self._asientos),
            n_lineas=n_lineas,
            n_caja=n_caja,
            n_banco=n_banco,
            periodo=periodo,
            ts=ts,
        )

        self._asientos = []
        self.btn_exportar.setEnabled(False)
        self.lbl_info.setText(
            f"✓ Exportado a {Path(out).name}. "
            f"{n_caja} mov. caja + {n_banco} mov. banco marcados como exportados."
        )
        self._refill_historial()
        if not self._historial_visible:
            self._toggle_historial()
        QMessageBox.information(self, "Exportado", f"Archivo guardado en:\n{out}")

    def _deshacer_exportacion(self, export_id: int):
        hist = self._conn.execute(
            "SELECT archivo, n_caja, n_banco FROM historial_exportacion WHERE id = ?",
            (export_id,),
        ).fetchone()
        if not hist:
            return
        resp = QMessageBox.question(
            self,
            "Deshacer exportación",
            f"¿Revertir la exportación '{hist['archivo']}'?\n\n"
            f"{hist['n_caja']} mov. de caja y {hist['n_banco']} de banco volverán "
            "a estar pendientes y se eliminará del historial.\n"
            "El archivo Excel ya generado NO se borra del disco.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        n_caja, n_banco = repository.deshacer_exportacion(self._conn, export_id)
        self.lbl_info.setText(
            f"↩ Exportación deshecha: {n_caja} mov. caja + {n_banco} mov. banco "
            "vuelven a estar pendientes."
        )
        self._refill_historial()

    def _recuperar_exportacion(self, export_id: int):
        """Carga en la tabla los asientos correspondientes a una exportación histórica."""
        hist = self._conn.execute(
            "SELECT * FROM historial_exportacion WHERE id = ?", (export_id,)
        ).fetchone()
        if not hist:
            return

        ts = hist["created_at"]
        asientos_db = self._conn.execute(
            "SELECT * FROM asiento WHERE exported_at = ? ORDER BY fecha, id",
            (ts,),
        ).fetchall()

        if not asientos_db:
            QMessageBox.information(self, "Historial", "No se encontraron asientos para esta exportación.")
            return

        self._asientos = []
        for adb in asientos_db:
            lineas_rows = repository.listar_asiento_lineas(self._conn, adb["id"])
            lineas = tuple(
                LineaAsiento(
                    orden=lr["orden"],
                    cargo_abono=lr["cargo_abono"],
                    cuenta=lr["cuenta"],
                    importe=lr["importe"],
                    comentario=lr["comentario"] or "",
                )
                for lr in lineas_rows
            )
            from datetime import date as dt_date
            a = AsientoGenerado(
                fecha=dt_date.fromisoformat(adb["fecha"]),
                periodo=adb["periodo"],
                descripcion=adb["descripcion"] or "",
                lineas=lineas,
                fuente_id=lineas_rows[0]["fuente_id"] if lineas_rows else None,
                fuente_tipo=lineas_rows[0]["fuente_tipo"] if lineas_rows else None,
            )
            self._asientos.append(a)

        self._asientos.sort(key=lambda a: (a.fecha, a.descripcion))
        self._llenar_tabla(self._asientos)
        self.btn_exportar.setEnabled(False)
        self.lbl_info.setText(
            f"Historial recuperado: {len(self._asientos)} asiento(s) de la exportación del "
            f"{hist['created_at'][:10]}."
        )
