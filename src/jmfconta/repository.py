"""Operaciones de alto nivel sobre la BD: mappings, movimientos, generación de asientos."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from . import db
from . import heuristics
from . import ai_suggester
from .importers.banco import LineaBanco
from .importers.caja import LineaCaja
from .sage.rules import AsientoGenerado, generar_desde_banco, generar_desde_caja


# ---------- Helpers internos ----------

def _cuentas_para_ai(conn: sqlite3.Connection, importe: float) -> list[tuple[str, str]]:
    """Devuelve cuentas del plan filtradas por signo de importe para el prompt de Gemini."""
    prefijos = ai_suggester._prefijos_por_signo(importe)
    placeholders = ",".join("?" for _ in prefijos)
    like_clauses = " OR ".join(f"codigo LIKE ?" for _ in prefijos)
    rows = conn.execute(
        f"SELECT codigo, descripcion FROM cuenta WHERE {like_clauses} ORDER BY codigo",
        tuple(p + "%" for p in prefijos),
    ).fetchall()
    return [(r["codigo"], r["descripcion"]) for r in rows]


def _ahora() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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


def descripciones_cuentas(conn: sqlite3.Connection) -> dict[str, str]:
    """Diccionario codigo -> descripcion de todo el plan (para caches de UI)."""
    return {
        r["codigo"]: r["descripcion"]
        for r in conn.execute("SELECT codigo, descripcion FROM cuenta")
    }


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


# ---------- Sugerencia rápida (sin IA, para UI) ----------

def sugerir_cuenta_rapida_caja(conn: sqlite3.Connection, denominacion: str, importe: float) -> str | None:
    """Mapping + heurísticas solo. Sin Gemini. Para respuesta inmediata en UI."""
    mapping = get_mapping(conn, "CAJA", denominacion)
    if mapping:
        return resolver_cuenta(conn, mapping)
    sugerida = heuristics.sugerir_caja(denominacion, importe)
    return resolver_cuenta(conn, sugerida)


def cuentas_para_ai(conn: sqlite3.Connection, importe: float) -> list[tuple[str, str]]:
    """Devuelve cuentas filtradas por signo para el prompt de Gemini."""
    return _cuentas_para_ai(conn, importe)


def insertar_movimiento_caja_uno(
    conn: sqlite3.Connection,
    fecha: str | None,
    denominacion: str,
    importe: float,
    observaciones: str,
    cuenta: str | None,
    cuenta_auto: int = 0,
) -> int:
    """Inserta una sola línea de caja. Devuelve el id generado."""
    now = datetime.now().isoformat(timespec="seconds")
    periodo = int(fecha.split("-")[1]) if fecha else None
    with db.transaction(conn):
        cur = conn.execute(
            """INSERT INTO movimiento_caja
               (fecha, denominacion, importe, observaciones, cuenta_sugerida,
                cuenta_auto, comentario_asiento, periodo, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, denominacion, float(importe), observaciones or "",
             cuenta or None, cuenta_auto, denominacion, periodo, now),
        )
    return cur.lastrowid


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
                if not cuenta:
                    cuentas_ai = _cuentas_para_ai(conn, l.importe)
                    sugerida_ai = ai_suggester.sugerir_con_gemini(
                        l.denominacion, l.importe, "CAJA", cuentas_ai
                    )
                    cuenta = resolver_cuenta(conn, sugerida_ai)
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


def eliminar_movimientos_caja(conn: sqlite3.Connection, ids: Iterable[int]) -> int:
    ids = list(ids)
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with db.transaction(conn):
        cur = conn.execute(
            f"DELETE FROM movimiento_caja WHERE id IN ({placeholders})", tuple(ids)
        )
    return cur.rowcount


def listar_movimientos_caja(conn: sqlite3.Connection, solo_pendientes: bool = False) -> list[sqlite3.Row]:
    where = "WHERE exported_at IS NULL" if solo_pendientes else ""
    return conn.execute(
        f"SELECT * FROM movimiento_caja {where} ORDER BY fecha, id"
    ).fetchall()


def actualizar_cuenta_caja(conn: sqlite3.Connection, mov_id: int, cuenta: str | None) -> None:
    with db.transaction(conn):
        conn.execute(
            "UPDATE movimiento_caja SET cuenta_sugerida = ?, updated_at = ? WHERE id = ?",
            (cuenta, _ahora(), mov_id),
        )


def confirmar_cuenta_caja(conn: sqlite3.Connection, mov_id: int) -> None:
    """Marca la cuenta como confirmada por el usuario (cuenta_auto=0)."""
    with db.transaction(conn):
        conn.execute(
            "UPDATE movimiento_caja SET cuenta_auto = 0, updated_at = ? WHERE id = ?",
            (_ahora(), mov_id),
        )


def actualizar_comentario_caja(conn: sqlite3.Connection, mov_id: int, comentario: str) -> None:
    with db.transaction(conn):
        conn.execute(
            "UPDATE movimiento_caja SET comentario_asiento = ?, updated_at = ? WHERE id = ?",
            (comentario, _ahora(), mov_id),
        )


def actualizar_fecha_caja(conn: sqlite3.Connection, mov_id: int, fecha: str | None) -> None:
    with db.transaction(conn):
        if fecha:
            periodo = int(fecha.split("-")[1])
            conn.execute(
                "UPDATE movimiento_caja SET fecha = ?, periodo = ?, updated_at = ? WHERE id = ?",
                (fecha, periodo, _ahora(), mov_id),
            )
        else:
            conn.execute(
                "UPDATE movimiento_caja SET fecha = NULL, periodo = NULL, updated_at = ? WHERE id = ?",
                (_ahora(), mov_id),
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
                if not cuenta:
                    texto_ai = l.mas_datos or l.movimiento
                    cuentas_ai = _cuentas_para_ai(conn, l.importe)
                    sugerida_ai = ai_suggester.sugerir_con_gemini(
                        texto_ai, l.importe, "BANCO", cuentas_ai
                    )
                    cuenta = resolver_cuenta(conn, sugerida_ai)
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


def eliminar_movimientos_banco(conn: sqlite3.Connection, ids: Iterable[int]) -> int:
    ids = list(ids)
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with db.transaction(conn):
        cur = conn.execute(
            f"DELETE FROM movimiento_banco WHERE id IN ({placeholders})", tuple(ids)
        )
    return cur.rowcount


def listar_movimientos_banco(conn: sqlite3.Connection, solo_pendientes: bool = False) -> list[sqlite3.Row]:
    where = "WHERE exported_at IS NULL" if solo_pendientes else ""
    return conn.execute(
        f"SELECT * FROM movimiento_banco {where} ORDER BY fecha, id"
    ).fetchall()


def actualizar_cuenta_banco(conn: sqlite3.Connection, mov_id: int, cuenta: str | None) -> None:
    with db.transaction(conn):
        conn.execute(
            "UPDATE movimiento_banco SET cuenta_sugerida = ?, updated_at = ? WHERE id = ?",
            (cuenta, _ahora(), mov_id),
        )


def confirmar_cuenta_banco(conn: sqlite3.Connection, mov_id: int) -> None:
    """Marca la cuenta como confirmada por el usuario (cuenta_auto=0)."""
    with db.transaction(conn):
        conn.execute(
            "UPDATE movimiento_banco SET cuenta_auto = 0, updated_at = ? WHERE id = ?",
            (_ahora(), mov_id),
        )


def actualizar_comentario_banco(conn: sqlite3.Connection, mov_id: int, comentario: str) -> None:
    with db.transaction(conn):
        conn.execute(
            "UPDATE movimiento_banco SET comentario_asiento = ?, updated_at = ? WHERE id = ?",
            (comentario, _ahora(), mov_id),
        )


# ---------- Pre-asientos (generación desde movimientos) ----------

def limpiar_asientos_no_exportados(conn: sqlite3.Connection) -> None:
    """Elimina asientos y sus líneas que aún no han sido exportados."""
    with db.transaction(conn):
        conn.execute(
            "DELETE FROM asiento_linea WHERE asiento_id IN ("
            "  SELECT id FROM asiento WHERE exported_at IS NULL"
            ")"
        )
        conn.execute("DELETE FROM asiento WHERE exported_at IS NULL")
        conn.execute(
            "UPDATE movimiento_caja SET asiento_id = NULL "
            "WHERE asiento_id IS NOT NULL AND asiento_id NOT IN "
            "(SELECT id FROM asiento WHERE exported_at IS NOT NULL)"
        )
        conn.execute(
            "UPDATE movimiento_banco SET asiento_id = NULL "
            "WHERE asiento_id IS NOT NULL AND asiento_id NOT IN "
            "(SELECT id FROM asiento WHERE exported_at IS NOT NULL)"
        )


def _persistir_asientos(
    conn: sqlite3.Connection,
    asientos: list[AsientoGenerado],
    origen: str,
) -> int:
    """Persiste asientos en las tablas asiento/asiento_linea y enlaza movimientos."""
    n = 0
    with db.transaction(conn):
        for ast in asientos:
            cur = conn.execute(
                "INSERT INTO asiento(numero, periodo, fecha, descripcion) VALUES(?, ?, ?, ?)",
                (n + 1, ast.periodo, ast.fecha.isoformat(), ast.descripcion),
            )
            asiento_id = cur.lastrowid
            for linea in ast.lineas:
                conn.execute(
                    """INSERT INTO asiento_linea
                       (asiento_id, orden, cargo_abono, cuenta, importe,
                        comentario, fuente_id, fuente_tipo)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asiento_id, linea.orden, linea.cargo_abono,
                        linea.cuenta, linea.importe,
                        linea.comentario or ast.descripcion,
                        ast.fuente_id, ast.fuente_tipo,
                    ),
                )
            if origen == "CAJA":
                conn.execute(
                    "UPDATE movimiento_caja SET asiento_id = ? WHERE id = ?",
                    (asiento_id, ast.fuente_id),
                )
            elif origen == "BANCO":
                conn.execute(
                    "UPDATE movimiento_banco SET asiento_id = ? WHERE id = ?",
                    (asiento_id, ast.fuente_id),
                )
            n += 1
    return n


def marcar_exportados_caja(conn: sqlite3.Connection, ts: str | None = None) -> int:
    """Marca como exportados todos los movimientos de caja listos (con cuenta y fecha)."""
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE movimiento_caja SET exported_at = ? "
        "WHERE exported_at IS NULL AND cuenta_sugerida IS NOT NULL AND fecha IS NOT NULL",
        (ts,),
    )
    conn.execute(
        "UPDATE asiento SET exported_at = ? "
        "WHERE id IN (SELECT asiento_id FROM movimiento_caja WHERE exported_at = ?)",
        (ts, ts),
    )
    conn.commit()
    return cur.rowcount


def marcar_exportados_banco(conn: sqlite3.Connection, ts: str | None = None) -> int:
    """Marca como exportados todos los movimientos de banco listos (con cuenta)."""
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE movimiento_banco SET exported_at = ? "
        "WHERE exported_at IS NULL AND cuenta_sugerida IS NOT NULL",
        (ts,),
    )
    conn.execute(
        "UPDATE asiento SET exported_at = ? "
        "WHERE id IN (SELECT asiento_id FROM movimiento_banco WHERE exported_at = ?)",
        (ts, ts),
    )
    conn.commit()
    return cur.rowcount


def generar_asientos_caja(conn: sqlite3.Connection) -> list[AsientoGenerado]:
    rows = listar_movimientos_caja(conn, solo_pendientes=True)
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
            object.__setattr__(a, "fuente_id", r["id"])
            object.__setattr__(a, "fuente_tipo", "CAJA")
            asientos.append(a)
        except ValueError:
            continue
    return asientos


def generar_asientos_banco(conn: sqlite3.Connection) -> list[AsientoGenerado]:
    rows = listar_movimientos_banco(conn, solo_pendientes=True)
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
            object.__setattr__(a, "fuente_id", r["id"])
            object.__setattr__(a, "fuente_tipo", "BANCO")
            asientos.append(a)
        except ValueError:
            continue
    return asientos


# ---------- Consulta de asientos desde BD (historial) ----------

def listar_asientos_db(
    conn: sqlite3.Connection,
    solo_pendientes: bool = False,
    periodo: int | None = None,
) -> list[sqlite3.Row]:
    where = []
    params: list = []
    if solo_pendientes:
        where.append("a.exported_at IS NULL")
    if periodo is not None:
        where.append("a.periodo = ?")
        params.append(periodo)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return conn.execute(
        f"SELECT a.* FROM asiento a {clause} ORDER BY a.fecha, a.id",
        tuple(params),
    ).fetchall()


def listar_asiento_lineas(conn: sqlite3.Connection, asiento_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM asiento_linea WHERE asiento_id = ? ORDER BY orden",
        (asiento_id,),
    ).fetchall()


# ---------- Historial de importación / exportación ----------

def registrar_importacion(
    conn: sqlite3.Connection,
    origen: str,
    archivo: str,
    filas: int,
) -> None:
    conn.execute(
        "INSERT INTO historial_importacion(origen, archivo, filas, created_at) "
        "VALUES(?, ?, ?, ?)",
        (origen, archivo, filas, _ahora()),
    )
    conn.commit()


def listar_historial_importacion(
    conn: sqlite3.Connection,
    origen: str | None = None,
) -> list[sqlite3.Row]:
    if origen:
        return conn.execute(
            "SELECT * FROM historial_importacion WHERE origen = ? ORDER BY created_at DESC",
            (origen,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM historial_importacion ORDER BY created_at DESC"
    ).fetchall()


def registrar_exportacion(
    conn: sqlite3.Connection,
    archivo: str,
    n_asientos: int,
    n_lineas: int,
    n_caja: int,
    n_banco: int,
    periodo: int | None = None,
    ts: str | None = None,
) -> str:
    if ts is None:
        ts = _ahora()
    conn.execute(
        "INSERT INTO historial_exportacion(archivo, periodo, n_asientos, "
        "n_lineas, n_caja, n_banco, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (archivo, periodo, n_asientos, n_lineas, n_caja, n_banco, ts),
    )
    conn.commit()
    return ts


def listar_historial_exportacion(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM historial_exportacion ORDER BY created_at DESC"
    ).fetchall()


def deshacer_exportacion(conn: sqlite3.Connection, export_id: int) -> tuple[int, int]:
    """Revierte una exportación: los movimientos vuelven a estar pendientes y se
    elimina el registro del historial. Devuelve (n_caja, n_banco) revertidos."""
    hist = conn.execute(
        "SELECT created_at FROM historial_exportacion WHERE id = ?", (export_id,)
    ).fetchone()
    if not hist:
        return (0, 0)
    ts = hist["created_at"]
    with db.transaction(conn):
        cur_caja = conn.execute(
            "UPDATE movimiento_caja SET exported_at = NULL WHERE exported_at = ?", (ts,)
        )
        cur_banco = conn.execute(
            "UPDATE movimiento_banco SET exported_at = NULL WHERE exported_at = ?", (ts,)
        )
        conn.execute(
            "UPDATE asiento SET exported_at = NULL WHERE exported_at = ?", (ts,)
        )
        conn.execute("DELETE FROM historial_exportacion WHERE id = ?", (export_id,))
    return (cur_caja.rowcount, cur_banco.rowcount)
