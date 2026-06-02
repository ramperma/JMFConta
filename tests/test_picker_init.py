"""Smoke test del picker con Qt offscreen: buscar, cuenta_actual, limpiar."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jmfconta import db  # noqa: E402
from jmfconta.ui.cuenta_picker import (  # noqa: E402
    CuentaPickerDialog,
    _cargar_recientes,
    _guardar_recientes,
)


def _ensure_app():
    return QApplication.instance() or QApplication(sys.argv)


def test_picker_buscar_filtra():
    app = _ensure_app()  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.db"
        db.init_db(p)
        conn = db.connect(p)
        conn.executemany(
            "INSERT INTO cuenta(codigo, descripcion) VALUES (?, ?)",
            [
                ("6280001", "Suministros electricos"),
                ("7053001", "Matriculas alumnos"),
                ("4750001", "HP Acreedor por retenciones"),
            ],
        )
        conn.commit()

        dlg = CuentaPickerDialog(conn)
        # Por defecto la lista muestra todas las cuentas
        textos_iniciales = [dlg.lista.item(i).text() for i in range(dlg.lista.count())]
        assert any("6280001" in t for t in textos_iniciales)
        assert any("7053001" in t for t in textos_iniciales)
        # Al escribir en el search, filtra
        dlg.search.setText("MATRICULAS")
        textos = [dlg.lista.item(i).text() for i in range(dlg.lista.count())]
        assert any("7053001" in t for t in textos), f"debe filtrar por 'MATRICULAS': {textos}"
        assert not any("6280001" in t for t in textos), "no debe mostrar Suministros"


def test_picker_preselecciona_cuenta_actual():
    app = _ensure_app()  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.db"
        db.init_db(p)
        conn = db.connect(p)
        conn.executemany(
            "INSERT INTO cuenta(codigo, descripcion) VALUES (?, ?)",
            [("6280001", "A"), ("7053001", "B"), ("4750001", "C")],
        )
        conn.commit()

        dlg = CuentaPickerDialog(conn, cuenta_actual="7053001")
        current = dlg.lista.currentItem()
        assert current is not None
        assert current.data(Qt.ItemDataRole.UserRole) == "7053001"


def test_picker_limpiar_devuelve_resultado_especial():
    app = _ensure_app()  # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.db"
        db.init_db(p)
        conn = db.connect(p)
        conn.execute("INSERT INTO cuenta(codigo, descripcion) VALUES ('6280001', 'X')")
        conn.commit()

        dlg = CuentaPickerDialog(conn, cuenta_actual="6280001")
        dlg._on_limpiar()
        assert dlg.cuenta == ""
        assert dlg.limpiar is True


def test_picker_recientes_persisten_via_qsettings(tmp_path: Path, monkeypatch):
    """Los recientes se guardan en QSettings, sobreviven a reinicios de la app."""
    app = _ensure_app()  # noqa: F841
    # Redirigir QSettings a un archivo temporal
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _guardar_recientes(["6280001", "7053001"])
    rec = _cargar_recientes()
    assert rec[:2] == ["6280001", "7053001"]


def test_picker_recientes_se_actualizan_al_aceptar():
    app = _ensure_app()  # noqa: F841
    # Limpiar settings previas
    QSettings("JMFConta", "Picker").remove("recientes")
    _guardar_recientes([])
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.db"
        db.init_db(p)
        conn = db.connect(p)
        conn.execute("INSERT INTO cuenta(codigo, descripcion) VALUES ('6280001', 'X')")
        conn.commit()

        dlg = CuentaPickerDialog(conn, cuenta_actual="")
        dlg._seleccion = "6280001"
        dlg.accept()  # registra reciente
        rec = _cargar_recientes()
        assert "6280001" in rec
