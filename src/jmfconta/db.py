"""Capa de acceso a datos SQLite."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS cuenta (
    codigo TEXT PRIMARY KEY,
    descripcion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mapping (
    origen TEXT NOT NULL,           -- 'CAJA' o 'BANCO'
    clave TEXT NOT NULL,            -- denominación o mas_datos
    cuenta TEXT NOT NULL,
    notas TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (origen, clave),
    FOREIGN KEY (cuenta) REFERENCES cuenta(codigo)
);

CREATE TABLE IF NOT EXISTS movimiento_caja (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT,                    -- ISO; puede ser NULL: el usuario la rellena en la UI
    denominacion TEXT NOT NULL,
    importe REAL NOT NULL,
    saldo REAL,                    -- calculado en la UI a partir de saldo_inicial
    saldo_inicial REAL NOT NULL DEFAULT 0,  -- saldo de arranque de este movimiento
    observaciones TEXT,
    cuenta_sugerida TEXT,
    cuenta_auto INTEGER NOT NULL DEFAULT 0,  -- 1 = sugerida por heurística, sin confirmar
    comentario_asiento TEXT,
    periodo INTEGER,               -- mes 1-12 derivado de fecha
    asiento_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (cuenta_sugerida) REFERENCES cuenta(codigo)
);

CREATE TABLE IF NOT EXISTS movimiento_banco (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    fecha_valor TEXT,               -- se conserva aunque no se exporta a SAGE
    movimiento TEXT NOT NULL,       -- 'TRANSFER INMEDIATA', 'SCF-TRASPASO FONDOS', etc.
    mas_datos TEXT,                 -- contrapartida
    importe REAL NOT NULL,
    saldo REAL,
    cuenta_sugerida TEXT,
    cuenta_auto INTEGER NOT NULL DEFAULT 0,  -- 1 = sugerida por heurística, sin confirmar
    comentario_asiento TEXT,
    periodo INTEGER,
    asiento_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (cuenta_sugerida) REFERENCES cuenta(codigo)
);

CREATE TABLE IF NOT EXISTS asiento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,        -- correlativo dentro del periodo
    periodo INTEGER NOT NULL,       -- mes 1-12
    fecha TEXT NOT NULL,
    descripcion TEXT,
    exported_at TEXT
);

CREATE TABLE IF NOT EXISTS asiento_linea (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_id INTEGER NOT NULL,
    orden INTEGER NOT NULL,         -- 1 o 2
    cargo_abono TEXT NOT NULL,      -- 'D' o 'H'
    cuenta TEXT NOT NULL,
    importe REAL NOT NULL,
    comentario TEXT,
    fuente_id INTEGER,              -- id en movimiento_caja o movimiento_banco
    fuente_tipo TEXT,               -- 'CAJA' o 'BANCO'
    FOREIGN KEY (asiento_id) REFERENCES asiento(id) ON DELETE CASCADE,
    FOREIGN KEY (cuenta) REFERENCES cuenta(codigo)
);

CREATE INDEX IF NOT EXISTS idx_movcaja_fecha ON movimiento_caja(fecha);
CREATE INDEX IF NOT EXISTS idx_movbanco_fecha ON movimiento_banco(fecha);
CREATE INDEX IF NOT EXISTS idx_asiento_periodo ON asiento(periodo);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _asegurar_columna(conn: sqlite3.Connection, tabla: str, columna: str, definicion: str) -> None:
    """Añade `columna` a `tabla` si la BD existente no la tiene. Idempotente."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if columna not in cols:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def init_db(db_path: str | Path) -> None:
    """Crea el esquema si no existe y migra columnas nuevas en BD preexistentes."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _asegurar_columna(conn, "movimiento_caja", "cuenta_auto", "INTEGER NOT NULL DEFAULT 0")
        _asegurar_columna(conn, "movimiento_banco", "cuenta_auto", "INTEGER NOT NULL DEFAULT 0")
        conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
