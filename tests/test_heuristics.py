"""Tests del sugeridor heuristico de cuentas."""
from jmfconta import heuristics


def test_caja_proveedor_luz():
    assert heuristics.sugerir_caja("IBERDROLA PAGO FACTURA", -50.0) == "6280001"
    assert heuristics.sugerir_caja("ENDESA ENERGIA SA", -120.0) == "6280001"
    assert heuristics.sugerir_caja("Recibo luz Mayo", -75.0) == "6280001"


def test_caja_proveedor_gas():
    assert heuristics.sugerir_caja("GAS NATURAL SDG", -45.0) == "6280001"
    assert heuristics.sugerir_caja("BUTANO SA", -15.0) == "6280001"


def test_caja_gasolina():
    assert heuristics.sugerir_caja("REPSOL GASOLINA", -60.0) == "6280001"
    assert heuristics.sugerir_caja("CEPSA COMBUSTIBLE", -55.0) == "6280001"


def test_caja_telecom():
    assert heuristics.sugerir_caja("MOVISTAR FIJO", -30.0) == "6290001"
    assert heuristics.sugerir_caja("VODAFONE INTERNET", -25.0) == "6290001"


def test_caja_ingreso_matricula():
    assert heuristics.sugerir_caja("MATRICULA ALUMNO GARCIA", 500.0) == "7053001"
    assert heuristics.sugerir_caja("CUOTA COLEGIO MAYO", 250.0) == "7053001"


def test_caja_nomina_y_ss():
    assert heuristics.sugerir_caja("NOMINA PROFESOR PEREZ", -1500.0) == "6400001"
    assert heuristics.sugerir_caja("TGSS CUOTA ABRIL", -500.0) == "6420001"
    assert heuristics.sugerir_caja("SEG. SOCIAL", -300.0) == "6420001"


def test_caja_aeat():
    assert heuristics.sugerir_caja("AEAT MODELO 111", -200.0) == "4750001"
    assert heuristics.sugerir_caja("IRPF 1T", -100.0) == "4750001"


def test_caja_fallback_ingreso():
    """Sin keyword conocido pero importe positivo -> 7050001."""
    assert heuristics.sugerir_caja("CONCEPTO RARO DESCONOCIDO", 100.0) == "7050001"


def test_caja_fallback_gasto():
    """Sin keyword conocido pero importe negativo -> 6280001."""
    assert heuristics.sugerir_caja("CONCEPTO RARO DESCONOCIDO", -50.0) == "6280001"


def test_caja_texto_vacio():
    assert heuristics.sugerir_caja("", 100.0) is None
    assert heuristics.sugerir_caja("", -50.0) is None


def test_caja_prioridad_keywords_gana_fallback():
    """'LUZ' es keyword, asi que 6280001 gana sobre el fallback por signo."""
    assert heuristics.sugerir_caja("RECIBO LUZ", 50.0) == "6280001"
    assert heuristics.sugerir_caja("RECIBO LUZ", -50.0) == "6280001"


def test_banco_iberdrola():
    assert heuristics.sugerir_banco("TRANSFER", "IBERDROLA SA", -120.0) == "6280001"


def test_banco_cliente_matricula():
    assert heuristics.sugerir_banco("TRANSFER", "FAMILIA GARCIA MATRICULA", 500.0) == "7053001"


def test_banco_mas_datos_prevalece_sobre_movimiento():
    """Si mas_datos no matchea pero movimiento si, debe usar movimiento como fallback."""
    # mas_datos vacio, movimiento = "RECIBO MOVISTAR"
    assert heuristics.sugerir_banco("RECIBO MOVISTAR", "", -30.0) == "6290001"


def test_banco_mas_datos_vacio_y_movimiento_vacio():
    assert heuristics.sugerir_banco("", "", 100.0) is None


def test_banco_fallback():
    assert heuristics.sugerir_banco("ALGO RARO", "CONCEPTO RARO", -10.0) == "6280001"
    assert heuristics.sugerir_banco("ALGO RARO", "CONCEPTO RARO", 10.0) == "7053001"


def test_banco_prioridad_cliente_sobre_otros():
    """'CLIENTE' debe ganar a 'FACTURA' en prioridad."""
    cuenta = heuristics.sugerir_banco("TRANSFER", "CLIENTE FACTURA", 100.0)
    assert cuenta == "7053001"


def test_no_falsos_positivos_cortos():
    """Keywords cortos como 'GAS' no deben matchear dentro de palabras mas largas
    de forma que sugieran incorrectamente. ('GASOLINA' contiene 'GAS' -> ambas
    son 628, asi que esto verifica coherencia, no discriminacion.)"""
    # 'GASOLINA' contiene 'GAS' pero ambas reglas son 6280001 -> indistinguible
    assert heuristics.sugerir_caja("GASOLINA REPSOL", -40.0) == "6280001"
