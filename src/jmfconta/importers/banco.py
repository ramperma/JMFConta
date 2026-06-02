"""Importador de movimientos de cuenta del banco desde xls (BIFF)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import xlrd


@dataclass(frozen=True)
class LineaBanco:
    fecha: date
    fecha_valor: date
    movimiento: str
    mas_datos: str
    importe: float
    saldo: float

    @property
    def signo(self) -> int:
        return 1 if self.importe >= 0 else -1

    @property
    def es_barrido(self) -> bool:
        return self.movimiento.strip().upper() == "SCF-TRASPASO FONDOS"


def _serial_a_fecha(s) -> date | None:
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        try:
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=float(s))).date()
        except (OverflowError, ValueError):
            return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    return None


def importar_movimientos_banco(path: str | Path) -> list[LineaBanco]:
    """Lee el .xls del banco. Cabecera en fila 3 (Fecha | Fecha valor | Movimiento | Más datos | Importe | Saldo)."""
    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    # Localizar fila de cabeceras
    cab_row = None
    for r in range(min(ws.nrows, 20)):
        vals = [str(ws.cell_value(r, c)).strip().lower() for c in range(ws.ncols)]
        if "fecha" in vals and "importe" in vals and "saldo" in vals:
            cab_row = r
            break
    if cab_row is None:
        cab_row = 2  # fallback estándar

    lineas: list[LineaBanco] = []
    for r in range(cab_row + 1, ws.nrows):
        fecha = _serial_a_fecha(ws.cell_value(r, 0))
        fecha_valor = _serial_a_fecha(ws.cell_value(r, 1))
        mov = str(ws.cell_value(r, 2)).strip()
        mas = str(ws.cell_value(r, 3)).strip()
        try:
            importe = float(ws.cell_value(r, 4))
        except (TypeError, ValueError):
            continue
        try:
            saldo = float(ws.cell_value(r, 5))
        except (TypeError, ValueError):
            saldo = 0.0
        if fecha is None:
            continue
        lineas.append(LineaBanco(fecha, fecha_valor or fecha, mov, mas, importe, saldo))
    return lineas
