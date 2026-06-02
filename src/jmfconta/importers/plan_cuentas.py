"""Importador del plan de cuentas desde xlsx."""
from __future__ import annotations

from pathlib import Path

import openpyxl


def importar_plan_cuentas(path: str | Path) -> list[tuple[str, str]]:
    """Devuelve lista de (codigo, descripcion) leídos del xlsx del plan.

    El archivo tiene dos columnas: 'Código cuenta' y 'Descripción'.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    cuentas: list[tuple[str, str]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        codigo, desc = row[0], row[1]
        if codigo is None or desc is None:
            continue
        codigo_s = str(codigo).strip()
        desc_s = str(desc).strip()
        if not codigo_s or not desc_s:
            continue
        cuentas.append((codigo_s, desc_s))
    return cuentas
