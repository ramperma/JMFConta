from pathlib import Path

from jmfconta.importers.plan_cuentas import importar_plan_cuentas


def test_plan_cuentas_carga():
    ruta = Path("/home/ramon/CodigoGithub/JMFConta/docs/PLAN DE CUENTAS JM.xlsx")
    if not ruta.exists():
        return  # skip implícito
    cuentas = importar_plan_cuentas(ruta)
    assert len(cuentas) >= 400
    # códigos tienen 7 dígitos
    assert all(c[0].isdigit() and len(c[0]) == 7 for c in cuentas)
    # 5700000 y 5720002 y 5510436 deben estar
    codigos = {c[0] for c in cuentas}
    assert "5700000" in codigos
    assert "5720002" in codigos
    assert "5510436" in codigos
