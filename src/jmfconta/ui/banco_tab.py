"""Pestaña de Movimientos de Banco."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
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
from ..importers.banco import importar_movimientos_banco
from .cuenta_picker import CuentaPickerDialog
from .estilos import set_cuenta, set_importe, set_text
from .theme import COLOR_TEXT_MUTED


COL_FECHA, COL_FVALOR, COL_MOV, COL_MAS, COL_IMPORTE, COL_SALDO, COL_CUENTA, COL_COMENT = range(8)


class _ImportWorker(QThread):
    progreso = Signal(str)
    terminado = Signal(int, str, str, str, int)

    def __init__(self, db_path: str, path: str):
        super().__init__()
        self._db_path = db_path
        self._path = path

    def run(self):
        from .. import db as db_mod
        conn = db_mod.connect(self._db_path)
        timer = QElapsedTimer()
        timer.start()
        try:
            self.progreso.emit("Leyendo extracto bancario…")
            lineas = importar_movimientos_banco(self._path)
        except Exception as e:
            conn.close()
            self.terminado.emit(0, self._path, str(e), "", timer.elapsed())
            return
        if not lineas:
            conn.close()
            self.terminado.emit(0, self._path, "", "No se detectaron movimientos.", timer.elapsed())
            return
        self.progreso.emit(f"Importando {len(lineas)} movimientos y consultando IA…")
        n = repository.insertar_movimientos_banco(conn, lineas)
        repository.registrar_importacion(conn, "BANCO", Path(self._path).name, n)
        conn.close()
        self.terminado.emit(n, self._path, "", "", timer.elapsed())


class BancoTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._cache_desc: dict[str, str] = {}
        self._solo_pendientes: bool = True
        self._import_worker: _ImportWorker | None = None
        self._build()
        self._refill()

    def _build(self):
        titulo = QLabel("Movimientos de Banco")
        titulo.setProperty("role", "title")
        subtitulo = QLabel(
            "Importa el extracto .xls del banco. La cuenta 5720002 (La Caixa) y los traspasos "
            "SCF-TRASPASO FONDOS (→ 5510436) se gestionan automáticamente."
        )
        subtitulo.setProperty("role", "muted")
        subtitulo.setWordWrap(True)

        self.btn_importar = QPushButton("Importar .xls del banco…")
        self.btn_importar.setProperty("primary", True)
        self.btn_importar.clicked.connect(self._importar)
        self.btn_asignar = QPushButton("Asignar cuenta…")
        self.btn_asignar.clicked.connect(self._asignar_cuenta)
        self.btn_aprender = QPushButton("Aprender mapping")
        self.btn_aprender.clicked.connect(self._aprender)
        self.btn_filtro = QPushButton("Ver todos")
        self.btn_filtro.setToolTip("Mostrar también movimientos ya exportados a SAGE")
        self.btn_filtro.clicked.connect(self._toggle_filtro)
        self.btn_eliminar = QPushButton("Eliminar fila(s)")
        self.btn_eliminar.setProperty("danger", True)
        self.btn_eliminar.setToolTip("Borrar las filas seleccionadas (también con tecla Supr)")
        self.btn_eliminar.clicked.connect(self._eliminar_seleccion)
        self.btn_vaciar = QPushButton("Vaciar tabla")
        self.btn_vaciar.setProperty("danger", True)
        self.btn_vaciar.clicked.connect(self._vaciar)

        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", "true")
        self._search_edit.setPlaceholderText("🔍 Filtrar…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(200)
        self._search_edit.setToolTip("Filtra por movimiento, más datos, cuenta o comentario")
        self._search_edit.textChanged.connect(self._aplicar_filtro_texto)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.btn_importar)
        btns.addWidget(self.btn_asignar)
        btns.addWidget(self.btn_aprender)
        btns.addWidget(self.btn_filtro)
        btns.addWidget(self.btn_eliminar)
        btns.addWidget(self.btn_vaciar)
        btns.addSpacing(12)
        btns.addWidget(self._search_edit)
        btns.addStretch(1)
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setProperty("role", "resumen")
        btns.addWidget(self.lbl_resumen)

        cols = ["Fecha", "F.Valor", "Movimiento", "Más datos", "Importe", "Saldo", "Cuenta", "Comentario"]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setDefaultSectionSize(50)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(COL_FECHA, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_FVALOR, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_MOV, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_MAS, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_IMPORTE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_SALDO, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_CUENTA, QHeaderView.ResizeMode.Interactive)
        self.tabla.setColumnWidth(COL_CUENTA, 300)
        h.setSectionResizeMode(COL_COMENT, QHeaderView.ResizeMode.Stretch)
        self.tabla.itemChanged.connect(self._on_item_changed)
        self.tabla.cellDoubleClicked.connect(self._on_double_click)
        atajo_supr = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.tabla)
        atajo_supr.setContext(Qt.ShortcutContext.WidgetShortcut)
        atajo_supr.activated.connect(self._eliminar_seleccion)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addLayout(btns)
        self._lbl_cargando = QLabel("IMPORTANDO LOS APUNTES DE LA HOJA DE CÁLCULO…")
        self._lbl_cargando.setStyleSheet(
            f"color: #16a34a; font-weight: bold; font-size: 20pt;"
        )
        self._lbl_cargando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_cargando.setVisible(False)
        self._lbl_opacity = QGraphicsOpacityEffect()
        self._lbl_opacity.setOpacity(1.0)
        self._lbl_cargando.setGraphicsEffect(self._lbl_opacity)
        self._pulse_anim = QPropertyAnimation(self._lbl_opacity, b"opacity", self)
        self._pulse_anim.setDuration(900)
        self._pulse_anim.setStartValue(1.0)
        self._pulse_anim.setKeyValueAt(0.5, 0.35)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        layout.addWidget(self._lbl_cargando)
        layout.addWidget(self.tabla, 1)

    def _toggle_filtro(self):
        self._solo_pendientes = not self._solo_pendientes
        self.btn_filtro.setText("Solo pendientes" if not self._solo_pendientes else "Ver todos")
        self._refill()

    def _aplicar_filtro_texto(self):
        texto = self._search_edit.text().strip().upper()
        cols = (COL_MOV, COL_MAS, COL_CUENTA, COL_COMENT)
        for r in range(self.tabla.rowCount()):
            if not texto:
                self.tabla.setRowHidden(r, False)
                continue
            visible = any(
                texto in (self.tabla.item(r, c).text().upper() if self.tabla.item(r, c) else "")
                for c in cols
            )
            self.tabla.setRowHidden(r, not visible)

    def _eliminar_seleccion(self):
        filas = sorted({i.row() for i in self.tabla.selectedItems()})
        ids = []
        exportados = 0
        for r in filas:
            it = self.tabla.item(r, COL_FECHA)
            if not it:
                continue
            ids.append(int(it.data(Qt.ItemDataRole.UserRole)))
            if it.data(Qt.ItemDataRole.UserRole + 1):
                exportados += 1
        if not ids:
            QMessageBox.information(self, "Aviso", "Selecciona una o más filas en la tabla.")
            return
        msg = f"¿Borrar {len(ids)} movimiento(s) del banco?"
        if exportados:
            msg += f"\n\nAtención: {exportados} ya fueron exportados a SAGE."
        if QMessageBox.question(self, "Eliminar", msg) != QMessageBox.StandardButton.Yes:
            return
        repository.eliminar_movimientos_banco(self._conn, ids)
        self._refill()

    def _refill(self):
        rows = repository.listar_movimientos_banco(self._conn, solo_pendientes=self._solo_pendientes)
        self._precarga_desc_cache()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(rows))
        ingresos = 0.0
        gastos = 0.0
        for r, row in enumerate(rows):
            exportado = bool(row["exported_at"])
            if row["importe"] > 0:
                ingresos += row["importe"]
            else:
                gastos += row["importe"]
            # Fila: id en col 0
            it = QTableWidgetItem(row["fecha"])
            it.setData(Qt.ItemDataRole.UserRole, row["id"])
            it.setData(Qt.ItemDataRole.UserRole + 1, exportado)
            self.tabla.setItem(r, COL_FECHA, it)
            set_text(self._cell(r, COL_FVALOR), row["fecha_valor"] or "", color=COLOR_TEXT_MUTED)
            set_text(self._cell(r, COL_MOV), row["movimiento"])
            set_text(self._cell(r, COL_MAS), row["mas_datos"] or "", color=COLOR_TEXT_MUTED if not row["mas_datos"] else None)
            set_importe(self._cell(r, COL_IMPORTE), row["importe"])
            set_importe(self._cell(r, COL_SALDO), row["saldo"], es_saldo=True)
            set_cuenta(self._cell(r, COL_CUENTA), row["cuenta_sugerida"] or "",
                       self._cache_desc.get(row["cuenta_sugerida"] or ""),
                       auto=bool(row["cuenta_auto"]))
            set_text(self._cell(r, COL_COMENT), row["comentario_asiento"] or "")

            if exportado:
                _gris = QColor("#9ca3af")
                for col in range(self.tabla.columnCount()):
                    item = self.tabla.item(r, col)
                    if item:
                        item.setForeground(_gris)

        self.tabla.blockSignals(False)
        n_export = self._conn.execute(
            "SELECT COUNT(*) FROM movimiento_banco WHERE exported_at IS NOT NULL"
        ).fetchone()[0]
        export_txt = f"  ·  {n_export} exportados" if n_export else ""
        self.lbl_resumen.setText(
            f"{len(rows)} movimientos{export_txt}  ·  "
            f"ingresos {ingresos:,.2f} €  ·  gastos {gastos:,.2f} €  ·  neto {ingresos + gastos:,.2f} €"
        )
        self._aplicar_filtro_texto()

    def _cell(self, row, col):
        item = self.tabla.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tabla.setItem(row, col, item)
        return item

    def _precarga_desc_cache(self):
        self._cache_desc.update(repository.descripciones_cuentas(self._conn))

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        id_item = self.tabla.item(row, COL_FECHA)
        if not id_item:
            return
        mov_id = int(id_item.data(Qt.ItemDataRole.UserRole))
        if item.column() == COL_COMENT:
            repository.actualizar_comentario_banco(self._conn, mov_id, item.text())

    def _importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar movimientos del banco", "", "Excel 97-2003 (*.xls)")
        if not path:
            return
        self._lbl_cargando.setText("IMPORTANDO LOS APUNTES DEL BANCO…")
        self._lbl_cargando.setVisible(True)
        self._pulse_anim.start()
        db_path = self._conn.execute("PRAGMA database_list").fetchone()[2]
        self._import_worker = _ImportWorker(db_path, path)
        self._import_worker.progreso.connect(self._on_import_progreso)
        self._import_worker.terminado.connect(self._on_import_terminado)
        self._import_worker.start()

    def _on_import_progreso(self, msg: str):
        self._lbl_cargando.setText(msg)

    def _on_import_terminado(self, n: int, path: str, error: str, warning: str, elapsed: int):
        self._finish_importar(n, path, error=error, warning=warning, elapsed=elapsed)

    def _finish_importar(self, n: int, path: str, *, error: str = "", warning: str = "", elapsed: int = 0):
        MIN_MS = 1500
        remaining = max(0, MIN_MS - elapsed)
        def _done():
            self._pulse_anim.stop()
            self._lbl_opacity.setOpacity(1.0)
            self._lbl_cargando.setVisible(False)
            if error:
                QMessageBox.critical(self, "Error", f"No se pudo leer:\n{error}")
            elif warning:
                QMessageBox.warning(self, "Aviso", warning)
            else:
                QMessageBox.information(self, "Importado", f"{n} movimientos importados.")
            self._refill()
        if remaining > 0:
            QTimer.singleShot(remaining, _done)
        else:
            _done()

    def _vaciar(self):
        if QMessageBox.question(self, "Vaciar", "¿Borrar todos los movimientos del banco?") != QMessageBox.StandardButton.Yes:
            return
        repository.vaciar_movimientos_banco(self._conn)
        self._refill()

    def _selected_id(self) -> int | None:
        items = self.tabla.selectedItems()
        if not items:
            return None
        first = self.tabla.item(items[0].row(), COL_FECHA)
        return int(first.data(Qt.ItemDataRole.UserRole)) if first else None

    def _on_double_click(self, row: int, col: int):
        if col == COL_CUENTA:
            self._asignar_cuenta()

    def _asignar_cuenta(self):
        mov_id = self._selected_id()
        if mov_id is None:
            QMessageBox.information(self, "Aviso", "Selecciona una fila.")
            return
        rows = repository.listar_movimientos_banco(self._conn)
        row = next((r for r in rows if r["id"] == mov_id), None)
        if row is None:
            return
        dlg = CuentaPickerDialog(
            self._conn, self,
            cuenta_actual=row["cuenta_sugerida"] or "",
        )
        result = dlg.exec()
        if dlg.limpiar:
            repository.actualizar_cuenta_banco(self._conn, mov_id, None)
            repository.confirmar_cuenta_banco(self._conn, mov_id)
            self._refill()
            return
        if result == CuentaPickerDialog.DialogCode.Accepted and dlg.cuenta:
            repository.actualizar_cuenta_banco(self._conn, mov_id, dlg.cuenta)
            repository.confirmar_cuenta_banco(self._conn, mov_id)
            self._refill()

    def _aprender(self):
        mov_id = self._selected_id()
        if mov_id is None:
            QMessageBox.information(self, "Aviso", "Selecciona una fila.")
            return
        rows = repository.listar_movimientos_banco(self._conn)
        row = next((r for r in rows if r["id"] == mov_id), None)
        if not row or not row["cuenta_sugerida"]:
            QMessageBox.information(self, "Aviso", "Asigna primero una cuenta a esta fila.")
            return
        clave = row["mas_datos"] or row["movimiento"]
        actualizadas = 0
        for r in rows:
            r_clave = r["mas_datos"] or r["movimiento"]
            if r_clave.upper() == clave.upper() and (not r["cuenta_sugerida"] or r.get("cuenta_auto", 0) == 1):
                repository.actualizar_cuenta_banco(self._conn, r["id"], row["cuenta_sugerida"])
                repository.confirmar_cuenta_banco(self._conn, r["id"])
                actualizadas += 1
        repository.set_mapping(self._conn, "BANCO", clave, row["cuenta_sugerida"])
        QMessageBox.information(self, "Mapping aprendido",
                                f"Aplicado a {actualizadas} fila(s) y guardado.")
        self._refill()
