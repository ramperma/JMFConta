"""Pestaña de Movimientos de Banco."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
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
from ..importers.banco import importar_movimientos_banco
from .cuenta_picker import CuentaPickerDialog
from .estilos import set_cuenta, set_importe, set_text
from .theme import COLOR_TEXT_MUTED


COL_FECHA, COL_FVALOR, COL_MOV, COL_MAS, COL_IMPORTE, COL_SALDO, COL_CUENTA, COL_COMENT = range(8)


class BancoTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._cache_desc: dict[str, str] = {}
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

        btns_mid = QHBoxLayout()
        btns_mid.setSpacing(8)
        btns_mid.addWidget(self.btn_asignar)
        btns_mid.addWidget(self.btn_aprender)
        btns_mid.addStretch(1)
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setProperty("role", "resumen")
        btns_mid.addWidget(self.lbl_resumen, 1)

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addLayout(btns_top)
        layout.addLayout(btns_mid)
        layout.addWidget(self.tabla, 1)

    def _refill(self):
        rows = repository.listar_movimientos_banco(self._conn)
        self._precarga_desc_cache()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(rows))
        ingresos = 0.0
        gastos = 0.0
        for r, row in enumerate(rows):
            if row["importe"] > 0:
                ingresos += row["importe"]
            else:
                gastos += row["importe"]
            # Fila: id en col 0
            it = QTableWidgetItem(row["fecha"])
            it.setData(Qt.ItemDataRole.UserRole, row["id"])
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
        self.tabla.blockSignals(False)
        self.lbl_resumen.setText(
            f"{len(rows)} movimientos  ·  ingresos {ingresos:,.2f} €  ·  gastos {gastos:,.2f} €  ·  neto {ingresos + gastos:,.2f} €"
        )

    def _cell(self, row, col):
        item = self.tabla.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tabla.setItem(row, col, item)
        return item

    def _precarga_desc_cache(self):
        for r in repository.listar_movimientos_banco(self._conn):
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
        if item.column() == COL_COMENT:
            repository.actualizar_comentario_banco(self._conn, mov_id, item.text())

    def _importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar movimientos del banco", "", "Excel 97-2003 (*.xls)")
        if not path:
            return
        try:
            lineas = importar_movimientos_banco(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer:\n{e}")
            return
        if not lineas:
            QMessageBox.warning(self, "Aviso", "No se detectaron movimientos.")
            return
        n = repository.insertar_movimientos_banco(self._conn, lineas)
        QMessageBox.information(self, "Importado", f"{n} movimientos importados.")
        self._refill()

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
            if r_clave.upper() == clave.upper() and not r["cuenta_sugerida"]:
                repository.actualizar_cuenta_banco(self._conn, r["id"], row["cuenta_sugerida"])
                repository.confirmar_cuenta_banco(self._conn, r["id"])
                actualizadas += 1
        repository.set_mapping(self._conn, "BANCO", clave, row["cuenta_sugerida"])
        QMessageBox.information(self, "Mapping aprendido",
                                f"Aplicado a {actualizadas} fila(s) y guardado.")
        self._refill()
