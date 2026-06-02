from datetime import date
from pathlib import Path

import pytest

from jmfconta.importers.caja import importar_libro_caja
from jmfconta.importers.banco import importar_movimientos_banco


def test_caja_estructura_basica():
    ruta = Path("/home/ramon/CodigoGithub/JMFConta/docs/Ejemplo subida SAGE.xlsx")
    if not ruta.exists():
        pytest.skip("excel de ejemplo no presente")
    lineas = importar_libro_caja(ruta)
    assert any(l.importe > 0 for l in lineas)
    assert any(l.importe < 0 for l in lineas)
    denoms = {l.denominacion for l in lineas}
    assert any("SERV" in d for d in denoms), f"denoms={denoms}"
    # No debe leer líneas de la sección explicativa ("D", "H" sueltas)
    assert "D" not in denoms
    assert "H" not in denoms
    # Fechas heredadas: aunque el excel las deja vacías, el importador rellena
    fechas = {l.fecha for l in lineas}
    assert len(fechas) >= 1


def test_banco_estructura_basica():
    ruta = Path("/home/ramon/CodigoGithub/JMFConta/docs/Movimientos_cuenta_banco.xls")
    if not ruta.exists():
        pytest.skip("xls de ejemplo no presente")
    movs = importar_movimientos_banco(ruta)
    assert len(movs) >= 10
    # SCF-TRASPASO FONDOS debe detectarse
    assert any(m.es_barrido for m in movs)
    # Fechas en rango razonable
    assert all(m.fecha.year >= 2024 for m in movs)
