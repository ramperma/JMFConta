"""Tests de la integracion heuristica <-> repository."""
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest

from jmfconta import db, repository
from jmfconta.importers.caja import LineaCaja


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.db"
        db.init_db(p)
        c = db.connect(p)
        # Cuentas mínimas que usan los tests (FK constraint)
        c.executemany(
            "INSERT INTO cuenta(codigo, descripcion) VALUES (?, ?)",
            [
                ("5700000", "Caja"),
                ("5720002", "Bancos"),
                ("5510436", "Barrido"),
                ("6280001", "Suministros"),
                ("6280002", "Suministros otros"),
                ("6290000", "Otros servicios generico"),
                ("6290001", "Otros servicios"),
                ("6400001", "Sueldos"),
                ("6420001", "Seguridad Social"),
                ("4750001", "HP Acreedor retenciones"),
                ("4100001", "Proveedores"),
                ("7050001", "Prestaciones generica"),
                ("7053001", "Matriculas"),
            ],
        )
        c.commit()
        yield c


def test_resolver_cuenta(conn: sqlite3.Connection):
    from jmfconta.repository import resolver_cuenta
    assert resolver_cuenta(conn, "6280001") == "6280001"  # existe exacto
    assert resolver_cuenta(conn, "6289999") == "6280001"  # primer match del prefijo
    assert resolver_cuenta(conn, "6299999") == "6290000"  # el genérico existe
    assert resolver_cuenta(conn, "9999999") is None
    assert resolver_cuenta(conn, None) is None
    assert resolver_cuenta(conn, "") is None


def test_insertar_caja_sin_mapping_usa_heuristica(conn: sqlite3.Connection):
    lineas = [
        LineaCaja(date(2026, 5, 14), "IBERDROLA FACTURA MAYO", -50.0, ""),
        LineaCaja(date(2026, 5, 14), "MATRICULA GARCIA", 500.0, ""),
    ]
    repository.insertar_movimientos_caja(conn, lineas)
    rows = repository.listar_movimientos_caja(conn)
    assert len(rows) == 2
    for r in rows:
        assert r["cuenta_sugerida"], f"sin sugerencia para {r['denominacion']}"
        assert r["cuenta_auto"] == 1, f"cuenta_auto no marcado para {r['denominacion']}"
    by_denom = {r["denominacion"]: r for r in rows}
    assert by_denom["IBERDROLA FACTURA MAYO"]["cuenta_sugerida"] == "6280001"
    assert by_denom["MATRICULA GARCIA"]["cuenta_sugerida"] == "7053001"


def test_insertar_caja_con_mapping_ya_existente_gana_a_heuristica(conn: sqlite3.Connection):
    """Si ya hay mapping para una denominacion, debe ganar sobre la heuristica."""
    repository.set_mapping(conn, "CAJA", "IBERDROLA FACTURA MAYO", "6280002")
    lineas = [LineaCaja(date(2026, 5, 14), "IBERDROLA FACTURA MAYO", -50.0, "")]
    repository.insertar_movimientos_caja(conn, lineas)
    rows = repository.listar_movimientos_caja(conn)
    assert len(rows) == 1
    assert rows[0]["cuenta_sugerida"] == "6280002"
    assert rows[0]["cuenta_auto"] == 0  # viene de mapping, no es auto


def test_insertar_caja_sin_match_y_sin_signo_no_sugiere(conn: sqlite3.Connection):
    lineas = [LineaCaja(date(2026, 5, 14), "ALGO RARO", 0.0, "")]
    repository.insertar_movimientos_caja(conn, lineas)
    rows = repository.listar_movimientos_caja(conn)
    assert rows[0]["cuenta_sugerida"] is None
    assert rows[0]["cuenta_auto"] == 0


def test_confirmar_cuenta_caja_pone_auto_a_cero(conn: sqlite3.Connection):
    lineas = [LineaCaja(date(2026, 5, 14), "IBERDROLA", -50.0, "")]
    repository.insertar_movimientos_caja(conn, lineas)
    mov_id = repository.listar_movimientos_caja(conn)[0]["id"]
    # Sanity: arranca auto=1
    assert repository.listar_movimientos_caja(conn)[0]["cuenta_auto"] == 1
    repository.confirmar_cuenta_caja(conn, mov_id)
    assert repository.listar_movimientos_caja(conn)[0]["cuenta_auto"] == 0


def test_insertar_banco_sin_mapping_usa_heuristica(conn: sqlite3.Connection):
    from jmfconta.importers.banco import LineaBanco
    lineas = [
        LineaBanco(date(2026, 5, 18), date(2026, 5, 18), "TRANSFER", "IBERDROLA", -120.0, 1000.0),
        LineaBanco(date(2026, 5, 19), date(2026, 5, 19), "TRANSFER", "FAMILIA LOPEZ MATRICULA", 500.0, 1500.0),
    ]
    repository.insertar_movimientos_banco(conn, lineas)
    rows = repository.listar_movimientos_banco(conn)
    assert len(rows) == 2
    for r in rows:
        assert r["cuenta_sugerida"]
        assert r["cuenta_auto"] == 1
    by_mas = {r["mas_datos"]: r for r in rows}
    assert by_mas["IBERDROLA"]["cuenta_sugerida"] == "6280001"
    assert by_mas["FAMILIA LOPEZ MATRICULA"]["cuenta_sugerida"] == "7053001"


def test_insertar_banco_con_mapping_existente_gana(conn: sqlite3.Connection):
    from jmfconta.importers.banco import LineaBanco
    repository.set_mapping(conn, "BANCO", "IBERDROLA", "6280002")
    lineas = [LineaBanco(date(2026, 5, 18), date(2026, 5, 18), "TRANSFER", "IBERDROLA", -120.0, 1000.0)]
    repository.insertar_movimientos_banco(conn, lineas)
    rows = repository.listar_movimientos_banco(conn)
    assert rows[0]["cuenta_sugerida"] == "6280002"
    assert rows[0]["cuenta_auto"] == 0


def test_init_db_migra_bd_sin_columna_cuenta_auto(tmp_path: Path):
    """Si una BD existente no tiene la columna, init_db la añade."""
    p = tmp_path / "legacy.db"
    schema_sin_auto = """
    CREATE TABLE cuenta (codigo TEXT PRIMARY KEY, descripcion TEXT NOT NULL);
    CREATE TABLE movimiento_caja (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT, denominacion TEXT NOT NULL, importe REAL NOT NULL,
        saldo REAL, saldo_inicial REAL NOT NULL DEFAULT 0,
        observaciones TEXT, cuenta_sugerida TEXT, comentario_asiento TEXT,
        periodo INTEGER, asiento_id INTEGER, created_at TEXT NOT NULL
    );
    CREATE TABLE movimiento_banco (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL, fecha_valor TEXT, movimiento TEXT NOT NULL,
        mas_datos TEXT, importe REAL NOT NULL, saldo REAL,
        cuenta_sugerida TEXT, comentario_asiento TEXT,
        periodo INTEGER, asiento_id INTEGER, created_at TEXT NOT NULL
    );
    """
    with db.connect(p) as c:
        c.executescript(schema_sin_auto)
        c.commit()
    db.init_db(p)
    with db.connect(p) as c:
        cols_caja = {row[1] for row in c.execute("PRAGMA table_info(movimiento_caja)").fetchall()}
        cols_banco = {row[1] for row in c.execute("PRAGMA table_info(movimiento_banco)").fetchall()}
    assert "cuenta_auto" in cols_caja
    assert "cuenta_auto" in cols_banco


def test_insertar_caja_usando_cuenta_que_no_existe_no_falla_por_fk(conn: sqlite3.Connection):
    """Sin keyword y sin Gemini configurado -> cuenta_sugerida queda None (sin fallback agresivo)."""
    lineas = [LineaCaja(date(2026, 5, 14), "CONCEPTO DESCONOCIDO", -50.0, "")]
    repository.insertar_movimientos_caja(conn, lineas)
    rows = repository.listar_movimientos_caja(conn)
    assert rows[0]["cuenta_sugerida"] is None
    assert rows[0]["cuenta_auto"] == 0
