from dataclasses import asdict
from datetime import date

import pytest

from jmfconta.sage.rules import (
    CUENTA_BANCO,
    CUENTA_BARRIDO,
    CUENTA_CAJA,
    generar_desde_banco,
    generar_desde_caja,
    periodo_de,
)


def _l(asiento, i):
    """Convierte linea a dict para comparación estable."""
    return asdict(asiento.lineas[i])


def test_caja_ingreso_positivo():
    a = generar_desde_caja(date(2026, 5, 14), 100.0, "7053001", "SERV. COMPLE")
    assert a.periodo == 5
    assert _l(a, 0) == {"orden": 1, "cargo_abono": "D", "cuenta": CUENTA_CAJA, "importe": 100.0, "comentario": "SERV. COMPLE"}
    assert _l(a, 1) == {"orden": 2, "cargo_abono": "H", "cuenta": "7053001", "importe": 100.0, "comentario": "SERV. COMPLE"}


def test_caja_gasto_negativo():
    a = generar_desde_caja(date(2026, 5, 14), -24.0, "6280001", "GASOLINA")
    assert _l(a, 0) == {"orden": 1, "cargo_abono": "D", "cuenta": "6280001", "importe": 24.0, "comentario": "GASOLINA"}
    assert _l(a, 1) == {"orden": 2, "cargo_abono": "H", "cuenta": CUENTA_CAJA, "importe": 24.0, "comentario": "GASOLINA"}


def test_caja_sin_cuenta_falla():
    with pytest.raises(ValueError):
        generar_desde_caja(date(2026, 5, 14), 10.0, "")


def test_banco_ingreso_positivo():
    a = generar_desde_banco(date(2026, 5, 18), 60.0, "TRANSFER INMEDIATA", "4300001", "LAURA GARCIA")
    assert _l(a, 0) == {"orden": 1, "cargo_abono": "D", "cuenta": CUENTA_BANCO, "importe": 60.0, "comentario": "LAURA GARCIA"}
    assert _l(a, 1) == {"orden": 2, "cargo_abono": "H", "cuenta": "4300001", "importe": 60.0, "comentario": "LAURA GARCIA"}


def test_banco_gasto_negativo():
    a = generar_desde_banco(date(2026, 5, 20), -307.28, "MAQUINAS Y EQUIP.", "4100000", "")
    assert _l(a, 0) == {"orden": 1, "cargo_abono": "H", "cuenta": "4100000", "importe": 307.28, "comentario": ""}
    assert _l(a, 1) == {"orden": 2, "cargo_abono": "D", "cuenta": CUENTA_BANCO, "importe": 307.28, "comentario": ""}


def test_banco_barrido_positivo():
    a = generar_desde_banco(date(2026, 5, 18), 60.0, "SCF-TRASPASO FONDOS", "", "TRASPASO")
    assert _l(a, 0) == {"orden": 1, "cargo_abono": "D", "cuenta": CUENTA_BANCO, "importe": 60.0, "comentario": "TRASPASO"}
    assert _l(a, 1) == {"orden": 2, "cargo_abono": "H", "cuenta": CUENTA_BARRIDO, "importe": 60.0, "comentario": "TRASPASO"}


def test_banco_barrido_negativo():
    a = generar_desde_banco(date(2026, 5, 19), -58.8, "SCF-TRASPASO FONDOS", "", "")
    assert _l(a, 0) == {"orden": 1, "cargo_abono": "D", "cuenta": CUENTA_BARRIDO, "importe": 58.8, "comentario": ""}
    assert _l(a, 1) == {"orden": 2, "cargo_abono": "H", "cuenta": CUENTA_BANCO, "importe": 58.8, "comentario": ""}


def test_banco_barrido_ignora_contrapartida():
    a = generar_desde_banco(date(2026, 5, 19), 100.0, "SCF-TRASPASO FONDOS", "IGNORADA", "")
    assert a.lineas[1].cuenta == CUENTA_BARRIDO


def test_periodo():
    assert periodo_de(date(2026, 1, 1)) == 1
    assert periodo_de(date(2026, 12, 31)) == 12
    assert periodo_de(date(2026, 5, 14)) == 5
