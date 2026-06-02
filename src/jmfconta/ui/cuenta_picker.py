"""Diálogo modal para buscar y seleccionar una cuenta del plan."""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .. import repository


_RESULT_LIMPIAR = 2
_MAX_RECIENTES = 10
_LIST_FONT_PT = 12


def _cargar_recientes() -> list[str]:
    s = QSettings("JMFConta", "Picker")
    raw = s.value("recientes", "", type=str) or ""
    return [c for c in raw.split(",") if c]


def _guardar_recientes(codigos: list[str]) -> None:
    s = QSettings("JMFConta", "Picker")
    s.setValue("recientes", ",".join(codigos[:_MAX_RECIENTES]))


def _registrar_reciente(codigo: str) -> None:
    codigo = codigo.strip()
    if not codigo:
        return
    actuales = _cargar_recientes()
    if codigo in actuales:
        actuales.remove(codigo)
    actuales.insert(0, codigo)
    _guardar_recientes(actuales)


def _descripcion_cuenta(conn: sqlite3.Connection, codigo: str) -> str:
    row = conn.execute("SELECT descripcion FROM cuenta WHERE codigo=?", (codigo,)).fetchone()
    return row["descripcion"] if row else ""


def _make_item(codigo: str, desc: str, marker: str = "") -> QListWidgetItem:
    suffix = f"   ← {marker}" if marker else ""
    it = QListWidgetItem(f"{codigo}    {desc}{suffix}")
    f = QFont("JetBrains Mono")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(_LIST_FONT_PT)
    it.setFont(f)
    it.setData(Qt.ItemDataRole.UserRole, codigo)
    it.setSizeHint(it.sizeHint().expandedTo(__import__("PySide6").QtCore.QSize(0, 34)))
    return it


def _header_item(text: str) -> QListWidgetItem:
    it = QListWidgetItem(text)
    it.setFlags(Qt.ItemFlag.NoItemFlags)
    it.setForeground(QColor("#6b7280"))
    f = it.font()
    f.setBold(True)
    f.setPointSize(10)
    it.setFont(f)
    return it


class CuentaPickerDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None, *,
                 cuenta_actual: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar cuenta")
        self.resize(720, 640)
        self._conn = conn
        self._seleccion: Optional[str] = None
        self._cuenta_actual = cuenta_actual

        titulo = QLabel("Seleccionar cuenta del plan")
        titulo.setProperty("role", "title")
        subtitulo = QLabel(
            "Escribe para filtrar (código o descripción). Enter acepta. Esc cancela."
        )
        subtitulo.setProperty("role", "muted")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por código o descripción… (ej. 628, IBERDROLA)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refill)

        self.lista = QListWidget()
        self.lista.setAlternatingRowColors(True)
        self.lista.setUniformItemSizes(False)
        self.lista.setSpacing(2)
        self.lista.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lista.itemDoubleClicked.connect(self._accept_item)
        # Enter sobre la lista acepta
        self.lista.itemActivated.connect(self._accept_item)
        self.lista.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Botones: Aceptar / Cancelar / Limpiar
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_limpiar = QPushButton("Limpiar cuenta")
        self.btn_limpiar.setProperty("danger", True)
        self.btn_limpiar.clicked.connect(self._on_limpiar)
        btns.addButton(self.btn_limpiar, QDialogButtonBox.ButtonRole.DestructiveRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addWidget(self.search)
        layout.addWidget(self.lista, 1)
        layout.addWidget(btns)

        # Mostrar la lista (vacía por ahora); el usuario decide si busca
        self._refill("")
        # Foco en la lista para que Enter acepte el item resaltado
        self.lista.setFocus()

    def _refill(self, texto: str):
        self.lista.clear()
        recientes = _cargar_recientes()
        # Seccion recientes solo si busqueda vacia
        if not texto and recientes:
            self.lista.addItem(_header_item("— Recientes —"))
            for codigo in recientes:
                desc = _descripcion_cuenta(self._conn, codigo)
                marker = "actual" if codigo == self._cuenta_actual else ""
                self.lista.addItem(_make_item(codigo, desc, marker))
            self.lista.addItem(_header_item("— Todas —"))

        filas = repository.buscar_cuenta(self._conn, texto, limit=1000)
        for codigo, desc in filas:
            marker = "actual" if codigo == self._cuenta_actual else ""
            self.lista.addItem(_make_item(codigo, desc, marker))

        # Pre-seleccionar la cuenta actual (la del medio en la lista completa)
        if self._cuenta_actual:
            for i in range(self.lista.count()):
                it = self.lista.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == self._cuenta_actual:
                    self.lista.setCurrentItem(it)
                    self.lista.scrollToItem(it, QAbstractItemView.ScrollHint.PositionAtCenter)
                    break
        elif self.lista.count() > 0:
            # Si no hay cuenta actual, seleccionar el primer item "real" (saltando headers)
            for i in range(self.lista.count()):
                if self.lista.item(i).data(Qt.ItemDataRole.UserRole):
                    self.lista.setCurrentRow(i)
                    break

    def _accept_item(self, item: QListWidgetItem):
        codigo = item.data(Qt.ItemDataRole.UserRole)
        if not codigo:
            return
        self._seleccion = codigo
        self.accept()

    def accept(self):
        item = self.lista.currentItem()
        if item:
            codigo = item.data(Qt.ItemDataRole.UserRole)
            if codigo:
                self._seleccion = codigo
        if self._seleccion:
            _registrar_reciente(self._seleccion)
        super().accept()

    def _on_limpiar(self):
        self._seleccion = ""
        self.done(_RESULT_LIMPIAR)

    def keyPressEvent(self, event):
        # Esc cancela
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        # Ctrl+L limpia la busqueda
        if event.key() == Qt.Key.Key_L and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.search.clear()
            return
        super().keyPressEvent(event)

    @property
    def cuenta(self) -> Optional[str]:
        return self._seleccion

    @property
    def limpiar(self) -> bool:
        return self.result() == _RESULT_LIMPIAR
