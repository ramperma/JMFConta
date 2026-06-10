"""Reglas de generación de asientos SAGE.

Reglas detectadas de la hoja "Ejemplo subida SAGE.xlsx":

Libro Caja (cuenta fija 5700000):
    importe > 0 -> 1) D 5700000, 2) H <cuenta ingreso>
    importe < 0 -> 1) D <cuenta gasto>, 2) H 5700000

Banco (cuenta fija 5720002 La Caixa):
    importe > 0                              -> 1) D 5720002, 2) H <cuenta ingreso>
    importe < 0                              -> 1) H <cuenta gasto/proveedor>, 2) D 5720002
    movimiento == 'SCF-TRASPASO FONDOS' > 0  -> 1) D 5720002, 2) H 5510436
    movimiento == 'SCF-TRASPASO FONDOS' < 0  -> 1) D 5510436, 2) H 5720002
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

CargoAbono = Literal["D", "H"]
Origen = Literal["CAJA", "BANCO"]

CUENTA_CAJA = "5700000"
CUENTA_BANCO = "5720002"
CUENTA_BARRIDO = "5510436"
MOV_BARRIDO = "SCF-TRASPASO FONDOS"


@dataclass(frozen=True)
class LineaAsiento:
    orden: int
    cargo_abono: CargoAbono
    cuenta: str
    importe: float
    comentario: str = ""


@dataclass(frozen=True)
class AsientoGenerado:
    fecha: date
    periodo: int
    descripcion: str
    lineas: tuple[LineaAsiento, ...]
    fuente_id: int | None = None
    fuente_tipo: str | None = None


def periodo_de(fecha: date) -> int:
    return fecha.month


def generar_desde_caja(
    fecha: date,
    importe: float,
    cuenta_contrapartida: str,
    comentario: str = "",
) -> AsientoGenerado:
    """Genera un asiento a partir de un movimiento de caja.

    `cuenta_contrapartida` es la cuenta del ingreso (importe>0) o del gasto (importe<0).
    """
    if not cuenta_contrapartida:
        raise ValueError("Falta cuenta contrapartida para movimiento de caja")
    abs_imp = abs(importe)
    if importe > 0:
        lineas = (
            LineaAsiento(1, "D", CUENTA_CAJA, abs_imp, comentario),
            LineaAsiento(2, "H", cuenta_contrapartida, abs_imp, comentario),
        )
    else:
        lineas = (
            LineaAsiento(1, "D", cuenta_contrapartida, abs_imp, comentario),
            LineaAsiento(2, "H", CUENTA_CAJA, abs_imp, comentario),
        )
    return AsientoGenerado(fecha, periodo_de(fecha), "Caja", lineas)


def generar_desde_banco(
    fecha: date,
    importe: float,
    movimiento: str,
    cuenta_contrapartida: str,
    comentario: str = "",
) -> AsientoGenerado:
    """Genera un asiento a partir de un movimiento bancario.

    Reglas:
      - SCF-TRASPASO FONDOS -> contrapartida fija 5510436 (barrido)
      - resto -> `cuenta_contrapartida` proporcionada
    """
    abs_imp = abs(importe)
    mov = (movimiento or "").strip().upper()

    if mov == MOV_BARRIDO:
        if importe > 0:
            lineas = (
                LineaAsiento(1, "D", CUENTA_BANCO, abs_imp, comentario),
                LineaAsiento(2, "H", CUENTA_BARRIDO, abs_imp, comentario),
            )
        else:
            lineas = (
                LineaAsiento(1, "D", CUENTA_BARRIDO, abs_imp, comentario),
                LineaAsiento(2, "H", CUENTA_BANCO, abs_imp, comentario),
            )
        return AsientoGenerado(fecha, periodo_de(fecha), "Traspaso fondos", lineas)

    if not cuenta_contrapartida:
        raise ValueError("Falta cuenta contrapartida para movimiento de banco")

    if importe > 0:
        lineas = (
            LineaAsiento(1, "D", CUENTA_BANCO, abs_imp, comentario),
            LineaAsiento(2, "H", cuenta_contrapartida, abs_imp, comentario),
        )
    else:
        lineas = (
            LineaAsiento(1, "H", cuenta_contrapartida, abs_imp, comentario),
            LineaAsiento(2, "D", CUENTA_BANCO, abs_imp, comentario),
        )
    return AsientoGenerado(fecha, periodo_de(fecha), "Banco", lineas)
