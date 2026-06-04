"""Persistencia de configuración en la tabla `config` de la BD."""
from __future__ import annotations

import os
import sqlite3

DEFAULTS: dict[str, str] = {
    "gemini_api_key": "",
    "gemini_model": "gemini-1.5-flash",
}

GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def get(conn: sqlite3.Connection, clave: str) -> str:
    row = conn.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    if row:
        return row[0]
    return DEFAULTS.get(clave, "")


def set_value(conn: sqlite3.Connection, clave: str, valor: str) -> None:
    conn.execute(
        "INSERT INTO config(clave, valor) VALUES(?, ?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        (clave, valor),
    )
    conn.commit()


def cargar_en_entorno(conn: sqlite3.Connection) -> None:
    """Vuelca configuración de BD a os.environ para uso inmediato sin reinicio."""
    for clave, default in DEFAULTS.items():
        valor = get(conn, clave)
        env_key = clave.upper()
        if valor:
            os.environ[env_key] = valor
        elif env_key not in os.environ and default:
            os.environ[env_key] = default
