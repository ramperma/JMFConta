"""Pestaña de Libro Caja: importar xlsx, ver grid, asignar cuentas y fechas."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
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
from ..importers.caja import importar_libro_caja
from .cuenta_picker import CuentaPickerDialog
from .estilos import set_cuenta, set_importe, set_text
from .theme import COLOR_DANGER, COLOR_TEXT_MUTED


COL_FECHA, COL_DENOM, COL_IMPORTE, COL_SALDO, COL_CUENTA, COL_COMENT, COL_OBS = range(7)


class CajaTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._cache_desc: dict[str, str] = {}
        self._build()
        self._refill()

    def _build(self):
        # Cabecera de la pestaña
        titulo = QLabel("Libro de Caja")
        titulo.setProperty("role", "title")
        subtitulo = QLabel(
            "Importa el Excel de caja, asigna fechas (en rojo si faltan) y cuentas. "
            "Pulsa 'Aprender mapping' para recordar la cuenta por denominación."
        )
        subtitulo.setProperty("role", "muted")
        subtitulo.setWordWrap(True)

        # Barra de configuración
        cfg_frame = QFrame()
        cfg_frame.setObjectName("cfgFrame")
        cfg = QFormLayout(cfg_frame)
        cfg.setContentsMargins(12, 12, 12, 12)
        cfg.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        cfg.setHorizontalSpacing(12)
        cfg.setVerticalSpacing(8)

        self.saldo_inicial = QDoubleSpinBox()
        self.saldo_inicial.setDecimals(2)
        self.saldo_inicial.setRange(-1e9, 1e9)
        self.saldo_inicial.setSingleStep(10.0)
        self.saldo_inicial.setSuffix(" €")
        self.saldo_inicial.setValue(0.0)
        self.saldo_inicial.valueChanged.connect(self._refill)
        cfg.addRow("Saldo inicial:", self.saldo_inicial)

        self.fecha_default = QDateEdit()
        self.fecha_default.setCalendarPopup(True)
        self.fecha_default.setDate(QDate.currentDate())
        self.fecha_default.setDisplayFormat("yyyy-MM-dd")
        cfg.addRow("Fecha por defecto:", self.fecha_default)

        # Botones
        self.btn_importar = QPushButton("Importar Excel…")
        self.btn_importar.setProperty("primary", True)
        self.btn_importar.clicked.connect(self._importar)
        self.btn_aplicar_fecha = QPushButton("Aplicar fecha a todas")
        self.btn_aplicar_fecha.clicked.connect(self._aplicar_fecha)
        self.btn_vaciar = QPushButton("Vaciar tabla")
        self.btn_vaciar.setProperty("danger", True)
        self.btn_vaciar.clicked.connect(self._vaciar)
        self.btn_asignar = QPushButton("Asignar cuenta…")
        self.btn_asignar.clicked.connect(self._asignar_cuenta)
        self.btn_aprender = QPushButton("Aprender mapping")
        self.btn_aprender.clicked.connect(self._aprender)

        btns_top = QHBoxLayout()
        btns_top.setSpacing(8)
        btns_top.addWidget(self.btn_importar)
        btns_top.addWidget(self.btn_vaciar)
        btns_top.addStretch(1)
        btns_top.addWidget(self.btn_aplicar_fecha)

        btns_mid = QHBoxLayout()
        btns_mid.setSpacing(8)
        btns_mid.addWidget(self.btn_asignar)
        btns_mid.addWidget(self.btn_aprender)
        btns_mid.addStretch(1)
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setProperty("role", "resumen")
        btns_mid.addWidget(self.lbl_resumen, 1)

        # Tabla
        cols = ["Fecha", "Denominación", "Importe", "Saldo", "Cuenta", "Comentario", "Observaciones"]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setDefaultSectionSize(50)
        h = self.tabla.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(COL_FECHA, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_DENOM, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_IMPORTE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_SALDO, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_CUENTA, QHeaderView.ResizeMode.Interactive)
        self.tabla.setColumnWidth(COL_CUENTA, 300)
        h.setSectionResizeMode(COL_COMENT, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_OBS, QHeaderView.ResizeMode.Stretch)
        self.tabla.itemChanged.connect(self._on_item_changed)
        self.tabla.cellDoubleClicked.connect(self._on_double_click)

        # Layout principal: dos columnas (config | tabla)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(cfg_frame, 0)
        top.addLayout(self._col_botones(btns_top, btns_mid), 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addLayout(top)
        layout.addWidget(self.tabla, 1)

    def _col_botones(self, btns_top, btns_mid) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addLayout(btns_top)
        col.addLayout(btns_mid)
        col.addStretch(1)
        return col

    def _refill(self):
        rows = repository.listar_movimientos_caja(self._conn)
        self._precarga_desc_cache()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(rows))
        saldo = float(self.saldo_inicial.value())
        sin_fecha = 0
        sin_cuenta = 0
        for r, row in enumerate(rows):
            saldo += row["importe"]
            if not row["fecha"]:
                sin_fecha += 1
            if not row["cuenta_sugerida"]:
                sin_cuenta += 1
            fecha_v = row["fecha"] or ""
            # Col 0 Fecha
            it = QTableWidgetItem(fecha_v)
            if not fecha_v:
                it.setForeground(QColor(COLOR_DANGER))
            it.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.tabla.setItem(r, COL_FECHA, it)
            # Col 1 Denominación
            set_text(self._cell(r, COL_DENOM), row["denominacion"])
            # Col 2 Importe
            set_importe(self._cell(r, COL_IMPORTE), row["importe"])
            # Col 3 Saldo
            set_importe(self._cell(r, COL_SALDO), saldo, es_saldo=True)
            # Col 4 Cuenta
            set_cuenta(self._cell(r, COL_CUENTA), row["cuenta_sugerida"] or "",
                       self._cache_desc.get(row["cuenta_sugerida"] or ""),
                       auto=bool(row["cuenta_auto"]))
            # Col 5 Comentario
            set_text(self._cell(r, COL_COMENT), row["comentario_asiento"] or "")
            # Col 6 Observaciones
            set_text(self._cell(r, COL_OBS), row["observaciones"] or "",
                     color=COLOR_TEXT_MUTED if not row["observaciones"] else None)
        self.tabla.blockSignals(False)
        self.lbl_resumen.setText(
            f"{len(rows)} filas  ·  {sin_fecha} sin fecha  ·  {sin_cuenta} sin cuenta  ·  "
            f"saldo final: {saldo:,.2f} €"
        )

    def _cell(self, row: int, col: int) -> QTableWidgetItem:
        item = self.tabla.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tabla.setItem(row, col, item)
        return item

    def _precarga_desc_cache(self):
        for r in repository.listar_movimientos_caja(self._conn):
            c = r["cuenta_sugerida"]
            if c and c not in self._cache_desc:
                row = self._conn.execute("SELECT descripcion FROM cuenta WHERE codigo=?", (c,)).fetchone()
                self._cache_desc[c] = row["descripcion"] if row else ""

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        id_item = self.tabla.item(row, COL_FECHA)
        if not id_item:
            return
        mov_id = int(id_item.data(Qt.ItemDataRole.UserRole))
        col = item.column()
        if col == COL_FECHA:
            texto = item.text().strip()
            if not texto:
                repository.actualizar_fecha_caja(self._conn, mov_id, None)
                item.setForeground(QColor(COLOR_DANGER))
            else:
                parsed = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        parsed = datetime.strptime(texto, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    QMessageBox.warning(self, "Fecha inválida", f"'{texto}' no es fecha válida (YYYY-MM-DD).")
                    self.tabla.blockSignals(True)
                    item.setText("")
                    self.tabla.blockSignals(False)
                    return
                repository.actualizar_fecha_caja(self._conn, mov_id, parsed.isoformat())
                item.setForeground(QColor("#1f2937"))
        elif col == COL_COMENT:
            repository.actualizar_comentario_caja(self._conn, mov_id, item.text())

    def _aplicar_fecha(self):
        qd = self.fecha_default.date()
        iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        for r in repository.listar_movimientos_caja(self._conn):
            repository.actualizar_fecha_caja(self._conn, r["id"], iso)
        self._refill()

    def _importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar libro de caja", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            lineas = importar_libro_caja(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer:\n{e}")
            return
        if not lineas:
            QMessageBox.warning(self, "Aviso", "No se detectaron líneas de caja.")
            return
        n = repository.insertar_movimientos_caja(self._conn, lineas)
        QMessageBox.information(self, "Importado", f"{n} líneas importadas. Rellena las fechas (en rojo).")
        self._refill()

    def _vaciar(self):
        if QMessageBox.question(self, "Vaciar", "¿Borrar todos los movimientos de caja?") != QMessageBox.StandardButton.Yes:
            return
        repository.vaciar_movimientos_caja(self._conn)
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
        rows = repository.listar_movimientos_caja(self._conn)
        row = next((r for r in rows if r["id"] == mov_id), None)
        if row is None:
            return
        dlg = CuentaPickerDialog(
            self._conn, self,
            cuenta_actual=row["cuenta_sugerida"] or "",
        )
        result = dlg.exec()
        if dlg.limpiar:
            repository.actualizar_cuenta_caja(self._conn, mov_id, None)
            repository.confirmar_cuenta_caja(self._conn, mov_id)
            self._refill()
            return
        if result == CuentaPickerDialog.DialogCode.Accepted and dlg.cuenta:
            repository.actualizar_cuenta_caja(self._conn, mov_id, dlg.cuenta)
            repository.confirmar_cuenta_caja(self._conn, mov_id)
            self._refill()

    def _aprender(self):
        mov_id = self._selected_id()
        if mov_id is None:
            QMessageBox.information(self, "Aviso", "Selecciona una fila.")
            return
        rows = repository.listar_movimientos_caja(self._conn)
        row = next((r for r in rows if r["id"] == mov_id), None)
        if not row or not row["cuenta_sugerida"]:
            QMessageBox.information(self, "Aviso", "Asigna primero una cuenta a esta fila.")
            return
        actualizadas = 0
        for r in rows:
            if r["denominacion"].upper() == row["denominacion"].upper() and not r["cuenta_sugerida"]:
                repository.actualizar_cuenta_caja(self._conn, r["id"], row["cuenta_sugerida"])
                repository.confirmar_cuenta_caja(self._conn, r["id"])
                actualizadas += 1
        repository.set_mapping(self._conn, "CAJA", row["denominacion"], row["cuenta_sugerida"])
        QMessageBox.information(self, "Mapping aprendido",
                                f"Aplicado a {actualizadas} fila(s) y guardado.")
        self._refill()
