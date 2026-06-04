"""Sugeridor de cuentas via Gemini. Fallback cuando heurísticas no matchean.

Requiere variable de entorno GEMINI_API_KEY.
Si no está configurada, las funciones devuelven None sin error.
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

_MODELO_DEFAULT = "gemini-1.5-flash"

_PROMPT_TEMPLATE = """\
Eres un contable español experto en contabilidad de colegios privados.

Fuente: {origen}
Descripción del movimiento: {descripcion}
Importe: {importe}€  ({signo})

Cuentas contables disponibles (codigo: descripcion):
{cuentas_str}

Selecciona el código de cuenta más apropiado para este movimiento.
Responde ÚNICAMENTE con el código numérico (ejemplo: 6280001). Sin texto adicional.\
"""


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai  # type: ignore
        return genai.Client(api_key=api_key)
    except ImportError:
        logger.warning("google-genai no instalado. Instala con: pip install google-genai")
        return None


def sugerir_con_gemini(
    descripcion: str,
    importe: float,
    origen: str,
    cuentas: list[tuple[str, str]],
) -> str | None:
    """Devuelve codigo de cuenta o None si no disponible / error."""
    if not descripcion or not cuentas:
        return None

    client = _get_client()
    if client is None:
        return None

    signo = "ingreso" if importe > 0 else "gasto"
    cuentas_str = "\n".join(f"{codigo}: {desc}" for codigo, desc in cuentas)
    prompt = _PROMPT_TEMPLATE.format(
        origen=origen,
        descripcion=descripcion,
        importe=abs(importe),
        signo=signo,
        cuentas_str=cuentas_str,
    )

    try:
        modelo = os.environ.get("GEMINI_MODEL", _MODELO_DEFAULT)
        response = client.models.generate_content(model=modelo, contents=prompt)
        codigo = response.text.strip().strip(".").strip()
        valid = {c for c, _ in cuentas}
        if codigo in valid:
            return codigo
        logger.debug("Gemini devolvió código no válido: %r", codigo)
        return None
    except Exception as exc:
        logger.warning("Error llamando a Gemini: %s", exc)
        return None


def _prefijos_por_signo(importe: float) -> tuple[str, ...]:
    if importe > 0:
        return ("7", "4")
    elif importe < 0:
        return ("6", "4")
    return ("6", "7", "4")
