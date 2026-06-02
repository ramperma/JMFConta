"""Helpers de estilo para celdas de tabla con semántica contable."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont

from .theme import (
    COLOR_DEBE,
    COLOR_GASTO,
    COLOR_HABER,
    COLOR_INGRESO,
    COLOR_SALDO,
    COLOR_TEXT_MUTED,
)


def fuente_mono(bold: bool = False, size: int = 10) -> QFont:
    f = QFont("JetBrains Mono")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    if bold:
        f.setBold(True)
    return f


def set_text(item, text: str, *, bold: bool = False, color: str | None = None,
             align: Qt.AlignmentFlag | None = None, mono: bool = False):
    item.setText(str(text) if text is not None else "")
    if align is not None:
        item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    if color is not None:
        item.setForeground(QBrush(QColor(color)))
    if bold or mono:
        f = item.font()
        if mono:
            f = fuente_mono(bold=bold)
        if bold:
            f.setBold(True)
        item.setFont(f)


def set_importe(item, value: float, *, es_saldo: bool = False):
    """Importe con signo: verde si >0, rojo si <0, azul-teal si es saldo."""
    if value is None:
        item.setText("")
        return
    color = COLOR_SALDO if es_saldo else (COLOR_INGRESO if value > 0 else COLOR_GASTO if value < 0 else COLOR_TEXT_MUTED)
    set_text(item, f"{value:,.2f} €", color=color, align=Qt.AlignmentFlag.AlignRight, mono=True)
    f = item.font()
    f.setBold(es_saldo or value < 0)
    item.setFont(f)


def set_cargo_abono(item, value: str):
    value = (value or "").upper()
    if value == "D":
        set_text(item, "D  Debe", color=COLOR_DEBE, bold=True)
    elif value == "H":
        set_text(item, "H  Haber", color=COLOR_HABER, bold=True)
    else:
        set_text(item, value)


def set_cuenta(item, codigo: str, descripcion: str | None = None, *, auto: bool = False):
    if not codigo:
        item.setText("")
        return
    text = codigo
    if descripcion:
        text = f"{codigo}  {descripcion}"
    set_text(item, text, mono=True)
    f = item.font()
    f.setBold(True)
    item.setFont(f)
    if auto:
        from PySide6.QtGui import QBrush, QColor
        item.setBackground(QBrush(QColor("#fff3cd")))
        item.setToolTip("Sugerencia automática — verifica antes de exportar")
    else:
        item.setToolTip("")
