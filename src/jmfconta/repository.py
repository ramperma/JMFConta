"""Operaciones de alto nivel sobre la BD: mappings, movimientos, generación de asientos."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from . import db
from . import heuristics
from .importers.banco import LineaBanco
from .importers.caja import LineaCaja
from .sage.rules import AsientoGenerado, generar_desde_banco, generar_desde_caja


# ---------- Plan de cuentas ----------

def cargar_plan(conn: sqlite3.Connection, cuentas: Iterable[tuple[str, str]]) -> int:
    n = 0
    with db.transaction(conn):
        conn.execute("DELETE FROM cuenta")
        for codigo, desc in cuentas:
            conn.execute(
                "INSERT OR REPLACE INTO cuenta(codigo, descripcion) VALUES(?, ?)",
                (codigo, desc),
            )
            n += 1
    return n


def buscar_cuenta(conn: sqlite3.Connection, texto: str, limit: int = 50) -> list[tuple[str, str]]:
    texto = (texto or "").strip()
    if not texto:
        rows = conn.execute("SELECT codigo, descripcion FROM cuenta ORDER BY codigo LIMIT ?", (limit,)).fetchall()
    else:
        like = f"%{texto.upper()}%"
        rows = conn.execute(
            "SELECT codigo, descripcion FROM cuenta WHERE UPPER(descripcion) LIKE ? OR codigo LIKE ? ORDER BY codigo LIMIT ?",
            (like, like, limit),
        ).fetchall()
    return [(r["codigo"], r["descripcion"]) for r in rows]


# ---------- Mappings denominación -> cuenta ----------

def get_mapping(conn: sqlite3.Connection, origen: str, clave: str) -> str | None:
    row = conn.execute(
        "SELECT cuenta FROM mapping WHERE origen = ? AND UPPER(clave) = UPPER(?)",
        (origen, clave),
    ).fetchone()
    return row["cuenta"] if row else None


def resolver_cuenta(conn: sqlite3.Connection, codigo: str | None) -> str | None:
    """Si `codigo` existe en el plan, lo devuelve. Si no, intenta el genérico
    del mismo padre (6280001 -> 6280000), o cualquier subcuenta con el mismo
    prefijo de 3 dígitos. Devuelve None si nada encaja."""
    if not codigo:
        return None
    row = conn.execute("SELECT 1 FROM cuenta WHERE codigo=?", (codigo,)).fetchone()
    if row:
        return codigo
    generico = codigo[:3] + "0000"
    row = conn.execute("SELECT 1 FROM cuenta WHERE codigo=?", (generico,)).fetchone()
    if row:
        return generico
    row = conn.execute(
        "SELECT codigo FROM cuenta WHERE codigo LIKE ? ORDER BY codigo LIMIT 1",
        (codigo[:3] + "%",),
    ).fetchone()
    return row["codigo"] if row else None


def set_mapping(conn: sqlite3.Connection, origen: str, clave: str, cuenta: str, notas: str = "") -> None:
    with db.transaction(conn):
        conn.execute(
            """INSERT INTO mapping(origen, clave, cuenta, notas, updated_at)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(origen, clave) DO UPDATE SET
                   cuenta = excluded.cuenta,
                   notas = excluded.notas,
                   updated_at = excluded.updated_at""",
            (origen, clave.strip(), cuenta, notas, datetime.now().isoformat(timespec="seconds")),
        )


def listar_mappings(conn: sqlite3.Connection, origen: str | None = None) -> list[sqlite3.Row]:
    if origen:
        return conn.execute(
            "SELECT m.origen, m.clave, m.cuenta, c.descripcion AS cuenta_desc, m.notas, m.updated_at "
            "FROM mapping m LEFT JOIN cuenta c ON c.codigo = m.cuenta "
            "WHERE m.origen = ? ORDER BY m.clave", (origen,)
        ).fetchall()
    return conn.execute(
        "SELECT m.origen, m.clave, m.cuenta, c.descripcion AS cuenta_desc, m.notas, m.updated_at "
        "FROM mapping m LEFT JOIN cuenta c ON c.codigo = m.cuenta "
        "ORDER BY m.origen, m.clave"
    ).fetchall()


def eliminar_mapping(conn: sqlite3.Connection, origen: str, clave: str) -> None:
    with db.transaction(conn):
        conn.execute("DELETE FROM mapping WHERE origen = ? AND clave = ?", (origen, clave))


# ---------- Movimientos Caja ----------

def insertar_movimientos_caja(conn: sqlite3.Connection, lineas: Iterable[LineaCaja]) -> int:
    n = 0
    now = datetime.now().isoformat(timespec="seconds")
    with db.transaction(conn):
        for l in lineas:
            mapping_cuenta = get_mapping(conn, "CAJA", l.denominacion)
            if mapping_cuenta:
                cuenta = mapping_cuenta
                auto = 0
            else:
                sugerida = heuristics.sugerir_caja(l.denominacion, l.importe)
                cuenta = resolver_cuenta(conn, sugerida)
                auto = 1 if cuenta else 0
            conn.execute(
                """INSERT INTO movimiento_caja
                   (fecha, denominacion, importe, observaciones, cuenta_sugerida,
                    cuenta_auto, comentario_asiento, periodo, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    l.fecha.isoformat() if l.fecha else None,
                    l.denominacion,
                    float(l.importe),
                    l.observaciones,
                    cuenta,
                    auto,
                    l.denominacion,
                    l.fecha.month if l.fecha else None,
                    now,
                ),
            )
            n += 1
    return n


def vaciar_movimientos_caja(conn: sqlite3.Connection) -> None:
    with db.transaction(conn):
        conn.execute("DELETE FROM movimiento_caja")


def listar_movimientos_caja(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM movimiento_caja ORDER BY fecha, id"
    ).fetchall()


def actualizar_cuenta_caja(conn: sqlite3.Connection, mov_id: int, cuenta: str | None) -> None:
    with db.transaction(conn):
        conn.execute("UPDATE movimiento_caja SET cuenta_sugerida = ? WHERE id = ?", (cuenta, mov_id))


def confirmar_cuenta_caja(conn: sqlite3.Connection, mov_id: int) -> None:
    """Marca la cuenta como confirmada por el usuario (cuenta_auto=0)."""
    with db.transaction(conn):
        conn.execute("UPDATE movimiento_caja SET cuenta_auto = 0 WHERE id = ?", (mov_id,))


def actualizar_comentario_caja(conn: sqlite3.Connection, mov_id: int, comentario: str) -> None:
    with db.transaction(conn):
        conn.execute("UPDATE movimiento_caja SET comentario_asiento = ? WHERE id = ?", (comentario, mov_id))


def actualizar_fecha_caja(conn: sqlite3.Connection, mov_id: int, fecha: str | None) -> None:
    with db.transaction(conn):
        if fecha:
            periodo = int(fecha.split("-")[1])
            conn.execute(
                "UPDATE movimiento_caja SET fecha = ?, periodo = ? WHERE id = ?",
                (fecha, periodo, mov_id),
            )
        else:
            conn.execute(
                "UPDATE movimiento_caja SET fecha = NULL, periodo = NULL WHERE id = ?",
                (mov_id,),
            )


# ---------- Movimientos Banco ----------

def insertar_movimientos_banco(conn: sqlite3.Connection, lineas: Iterable[LineaBanco]) -> int:
    n = 0
    now = datetime.now().isoformat(timespec="seconds")
    with db.transaction(conn):
        for l in lineas:
            # La clave de mapping para banco es el campo 'mas_datos' (contrapartida)
            mapping_cuenta = get_mapping(conn, "BANCO", l.mas_datos) if l.mas_datos else None
            if mapping_cuenta:
                cuenta = mapping_cuenta
                auto = 0
            else:
                sugerida = heuristics.sugerir_banco(l.movimiento, l.mas_datos, l.importe)
                cuenta = resolver_cuenta(conn, sugerida)
                auto = 1 if cuenta else 0
            conn.execute(
                """INSERT INTO movimiento_banco
                   (fecha, fecha_valor, movimiento, mas_datos, importe, saldo,
                    cuenta_sugerida, cuenta_auto, comentario_asiento, periodo, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    l.fecha.isoformat(),
                    l.fecha_valor.isoformat() if l.fecha_valor else None,
                    l.movimiento,
                    l.mas_datos,
                    float(l.importe),
                    float(l.saldo),
                    cuenta,
                    auto,
                    l.mas_datos or l.movimiento,
                    l.fecha.month,
                    now,
                ),
            )
            n += 1
    return n


def vaciar_movimientos_banco(conn: sqlite3.Connection) -> None:
    with db.transaction(conn):
        conn.execute("DELETE FROM movimiento_banco")


def listar_movimientos_banco(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM movimiento_banco ORDER BY fecha, id"
    ).fetchall()


def actualizar_cuenta_banco(conn: sqlite3.Connection, mov_id: int, cuenta: str | None) -> None:
    with db.transaction(conn):
        conn.execute("UPDATE movimiento_banco SET cuenta_sugerida = ? WHERE id = ?", (cuenta, mov_id))


def confirmar_cuenta_banco(conn: sqlite3.Connection, mov_id: int) -> None:
    """Marca la cuenta como confirmada por el usuario (cuenta_auto=0)."""
    with db.transaction(conn):
        conn.execute("UPDATE movimiento_banco SET cuenta_auto = 0 WHERE id = ?", (mov_id,))


def actualizar_comentario_banco(conn: sqlite3.Connection, mov_id: int, comentario: str) -> None:
    with db.transaction(conn):
        conn.execute("UPDATE movimiento_banco SET comentario_asiento = ? WHERE id = ?", (comentario, mov_id))


# ---------- Pre-asientos (generación desde movimientos) ----------

def generar_asientos_caja(conn: sqlite3.Connection) -> list[AsientoGenerado]:
    rows = listar_movimientos_caja(conn)
    asientos: list[AsientoGenerado] = []
    for r in rows:
        if not r["cuenta_sugerida"] or not r["fecha"]:
            continue
        try:
            a = generar_desde_caja(
                fecha=date.fromisoformat(r["fecha"]),
                importe=r["importe"],
                cuenta_contrapartida=r["cuenta_sugerida"],
                comentario=r["comentario_asiento"] or r["denominacion"],
            )
            asientos.append(a)
        except ValueError:
            continue
    return asientos


def generar_asientos_banco(conn: sqlite3.Connection) -> list[AsientoGenerado]:
    rows = listar_movimientos_banco(conn)
    asientos: list[AsientoGenerado] = []
    for r in rows:
        try:
            a = generar_desde_banco(
                fecha=date.fromisoformat(r["fecha"]),
                importe=r["importe"],
                movimiento=r["movimiento"],
                cuenta_contrapartida=r["cuenta_sugerida"] or "",
                comentario=r["comentario_asiento"] or r["mas_datos"] or r["movimiento"],
            )
            asientos.append(a)
        except ValueError:
            continue
    return asientos
