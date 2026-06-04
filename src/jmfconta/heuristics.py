"""Heurísticas para sugerir cuenta contable cuando no hay mapping previo.

Estrategia:
  1. Reglas por keyword (case-insensitive, prioridad = orden de la lista).
  2. Fallback agresivo: si no hay keyword, sign-of-importe decide
     (ingreso -> 7xx, gasto -> 6xx).

No sustituyen al mapping manual: el flag `cuenta_auto=1` indica "esto es
una sugerencia automática, verifica antes de exportar".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReglaHeuristica:
    keywords: tuple[str, ...]
    cuenta: str
    prioridad: int = 10


# Caja: denominacion completa (proveedor + concepto)
REGLAS_CAJA: tuple[ReglaHeuristica, ...] = (
    # Suministros
    ReglaHeuristica(("IBERDROLA", "ENDESA", "NATURGY", "ENEL", "ELECTRIC", "LUZ", "RECIBO LUZ"), "6280001"),
    ReglaHeuristica(("GAS NATURAL", "GAS", "BUTANO", "PROPANO"), "6280001"),
    ReglaHeuristica(("AGUA", "CANAL DE ISABEL", "CANAL ISABEL"), "6280001"),
    ReglaHeuristica(("GASOLINA", "REPSOL", "CEPSA", "BP ", "COMBUSTIBLE", "DIESEL", "GARRAFA"), "6280001"),
    # Comunicaciones
    ReglaHeuristica(("MOVISTAR", "VODAFONE", "ORANGE", "TELEFONO", "TELEFONIA", "INTERNET", "MASMOVIL", "LOWI", "FINETWORK", "DIGI"), "6290001"),
    # Arrendamientos
    ReglaHeuristica(("ALQUILER", "ARRENDAMIENTO", "RENT", "FURGONETA", "VEHICULO", "VEHÍCULO"), "6210001"),
    # Seguros
    ReglaHeuristica(("SEGURO", "ALLIANZ", "MAPFRE", "MUTUA", "ZURICH", "GENERALI"), "6250001"),
    # Personal
    ReglaHeuristica(("NOMINA", "SUELDO", "SALARIO", "PAGA EXTRA", "FINIQUITO"), "6400001"),
    ReglaHeuristica(("SEG. SOCIAL", "TGSS", "SEGURIDAD SOCIAL", "COTIZACION"), "6420001"),
    # Hacienda
    ReglaHeuristica(("AEAT", "HACIENDA", "IRPF", "IVA", "MODELO 111", "MODELO 115", "MODELO 303", "MODELO 130", "RETENCION"), "4750001"),
    # Material / oficina
    ReglaHeuristica(("AMAZON", "AMZN", "MATERIAL OFICINA", "MATERIAL ESCOLAR", "LIBRERIA"), "6290001"),
    # Proveedores
    ReglaHeuristica(("PROVEEDOR", "ACREEDOR", "FACTURA PROVEEDOR", "FACTURA", "FRA."), "4100001", prioridad=20),
    # Ingresos por ciclo/etapa — prioridad alta para evitar fallback genérico
    ReglaHeuristica(("2 CICLO INFANTIL", "2° CICLO", "2º CICLO", "SEGUNDO CICLO INFANTIL"), "7051002", prioridad=5),
    ReglaHeuristica(("1 CICLO INFANTIL", "1° CICLO INFANTIL", "1º CICLO INFANTIL", "PRIMER CICLO INFANTIL"), "7051002", prioridad=5),
    ReglaHeuristica(("PRIMARIA", "1 CICLO PRIMARIA", "2 CICLO PRIMARIA", "3 CICLO PRIMARIA"), "7051003", prioridad=5),
    ReglaHeuristica(("SECUNDARIA", "EDUCACION SECUNDARIA"), "7051005", prioridad=5),
    ReglaHeuristica(("COMEDOR", "TICKET COMEDOR", "TICKETS COMEDOR"), "7053001", prioridad=5),
    ReglaHeuristica(("GUARDERIA", "GUADERIA", "AULA MATINAL", "MATINAL"), "7053007", prioridad=5),
    ReglaHeuristica(("EXTRAESCOLAR", "ACTIVIDAD EXTRAESCOLAR"), "7055000", prioridad=5),
    ReglaHeuristica(("MATRICULA", "CUOTA", "COLEGIO", "FAMILIA", "ALUMNO", "TUTOR", "RECIBI"), "7053001", prioridad=15),
)

# Banco: mas_datos (contrapartida) o, si falta, el campo movimiento
REGLAS_BANCO: tuple[ReglaHeuristica, ...] = (
    ReglaHeuristica(("IBERDROLA", "ENDESA", "NATURGY", "LUZ", "ELECTRIC"), "6280001"),
    ReglaHeuristica(("GAS", "BUTANO"), "6280001"),
    ReglaHeuristica(("MOVISTAR", "VODAFONE", "ORANGE", "TELEFONO", "INTERNET"), "6290001"),
    ReglaHeuristica(("ALQUILER", "ARRENDAMIENTO"), "6210001"),
    ReglaHeuristica(("NOMINA", "SUELDO", "SALARIO"), "6400001"),
    ReglaHeuristica(("TGSS", "SEG. SOCIAL", "SEGURIDAD SOCIAL"), "6420001"),
    ReglaHeuristica(("AEAT", "HACIENDA", "IRPF", "IVA", "MODELO"), "4750001"),
    ReglaHeuristica(("SEGURO", "ALLIANZ", "MAPFRE"), "6250001"),
    ReglaHeuristica(("PROVEEDOR", "ACREEDOR", "FACTURA", "FRA."), "4100001", prioridad=20),
    ReglaHeuristica(("CLIENTE", "MATRIC", "CUOTA", "COLEGIO", "FAMILIA", "ALUMNO", "TUTOR"), "7053001", prioridad=15),
)

# Fallback agresivo: si nada matchea, sign-of-importe decide.
FALLBACK_CAJA_INGRESO = "7050001"
FALLBACK_CAJA_GASTO = "6280001"
FALLBACK_BANCO_INGRESO = "7053001"
FALLBACK_BANCO_GASTO = "6280001"


def _aplicar_reglas(texto: str, reglas: tuple[ReglaHeuristica, ...]) -> str | None:
    """Primera regla (menor prioridad) cuyo keyword aparezca en `texto`."""
    if not texto:
        return None
    t = texto.upper()
    for r in sorted(reglas, key=lambda x: x.prioridad):
        for kw in r.keywords:
            if kw.upper() in t:
                return r.cuenta
    return None


def sugerir_caja(denominacion: str, importe: float) -> str | None:
    """Sugiere cuenta para una linea de caja. None si ningun keyword matchea."""
    if not denominacion:
        return None
    return _aplicar_reglas(denominacion, REGLAS_CAJA)


def sugerir_banco(movimiento: str, mas_datos: str, importe: float) -> str | None:
    """Sugiere cuenta para un movimiento de banco. None si ningun keyword matchea."""
    texto = mas_datos or movimiento or ""
    if not texto:
        return None
    return _aplicar_reglas(texto, REGLAS_BANCO)
