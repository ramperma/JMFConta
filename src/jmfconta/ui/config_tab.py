"""Pestaña de configuración: IA (Gemini) y preferencias generales."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import config_store
from .theme import COLOR_ACCENT, COLOR_BORDER, COLOR_SUCCESS, COLOR_DANGER, COLOR_TEXT_MUTED


class ConfigTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._build()
        self._cargar()

    # ------------------------------------------------------------------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(24)

        # Título
        title = QLabel("Configuración")
        title.setProperty("role", "title")
        outer.addWidget(title)

        # Tarjeta Gemini
        card = self._card("🤖  Google Gemini")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(12)
        form.setContentsMargins(0, 12, 0, 0)

        # API Key
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("AIza…")
        self._key_edit.setMinimumWidth(380)
        self._btn_toggle = QPushButton("👁")
        self._btn_toggle.setFixedWidth(36)
        self._btn_toggle.setToolTip("Mostrar / ocultar")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._key_edit, 1)
        key_row.addWidget(self._btn_toggle)
        form.addRow("API Key:", key_row)

        # Modelo
        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(300)
        self._model_combo.setPlaceholderText("— cargar modelos —")
        self._btn_load_models = QPushButton("↺ Cargar modelos")
        self._btn_load_models.setToolTip("Obtiene la lista de modelos disponibles para tu API key")
        self._btn_load_models.clicked.connect(self._cargar_modelos)
        model_row.addWidget(self._model_combo, 1)
        model_row.addWidget(self._btn_load_models)
        form.addRow("Modelo:", model_row)

        card.layout().addLayout(form)

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self._btn_test = QPushButton("Probar conexión")
        self._btn_test.clicked.connect(self._test_connection)
        btn_row.addWidget(self._btn_test)

        self._btn_save = QPushButton("Guardar")
        self._btn_save.setProperty("primary", "true")
        self._btn_save.clicked.connect(self._guardar)
        btn_row.addWidget(self._btn_save)

        card.layout().addLayout(btn_row)

        # Status
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 9pt;")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        card.layout().addWidget(self._lbl_status)

        outer.addWidget(card)

        # Tarjeta Sincronización
        sync_card = self._card("🔄  Sincronización con repositorio")

        sync_warn = QLabel(
            "Descarga los últimos cambios del repositorio remoto. "
            "Si hay conflictos locales, el remoto gana (git reset --hard)."
        )
        sync_warn.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 9pt; border: none;")
        sync_warn.setWordWrap(True)
        sync_card.layout().addWidget(sync_warn)

        self._btn_sync = QPushButton("↓  Sincronizar con remoto")
        self._btn_sync.setProperty("primary", "true")
        self._btn_sync.setFixedWidth(220)
        self._btn_sync.clicked.connect(self._sincronizar)
        sync_card.layout().addWidget(self._btn_sync)

        self._sync_output = QTextEdit()
        self._sync_output.setReadOnly(True)
        self._sync_output.setFixedHeight(200)
        self._sync_output.setStyleSheet(
            "QTextEdit { background: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 9pt; border-radius: 6px; padding: 8px; }"
        )
        sync_card.layout().addWidget(self._sync_output)

        outer.addWidget(sync_card)
        outer.addStretch(1)

        # Nota de seguridad
        note = QLabel(
            "La API key se guarda en la base de datos local (datos/jmfconta.db). "
            "El archivo no se sincroniza ni se sube a ningún servidor."
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        outer.addWidget(note)

    def _card(self, titulo: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: white; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(8)
        lbl = QLabel(titulo)
        lbl.setStyleSheet(
            f"font-weight: 600; font-size: 11pt; color: {COLOR_ACCENT}; border: none;"
        )
        vl.addWidget(lbl)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {COLOR_BORDER}; border: none; max-height: 1px;")
        vl.addWidget(sep)
        return card

    # ------------------------------------------------------------------
    def _cargar(self):
        key = config_store.get(self._conn, "gemini_api_key")
        self._key_edit.setText(key)
        self._modelo_guardado = config_store.get(self._conn, "gemini_model")
        if key:
            self._cargar_modelos(silencioso=True)

    def _cargar_modelos(self, silencioso: bool = False):
        key = self._key_edit.text().strip()
        if not key:
            if not silencioso:
                self._lbl_status.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 9pt;")
                self._lbl_status.setText("✗ Introduce una API Key primero")
            return
        try:
            from google import genai  # type: ignore
            client = genai.Client(api_key=key)
            modelos = [
                m.name.replace("models/", "")
                for m in client.models.list()
                if "generateContent" in (getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or [])
            ]
            modelos.sort()
            self._model_combo.clear()
            for m in modelos:
                self._model_combo.addItem(m)
            guardado = getattr(self, "_modelo_guardado", "")
            idx = self._model_combo.findText(guardado)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
            if not silencioso:
                self._lbl_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 9pt;")
                self._lbl_status.setText(f"✓ {len(modelos)} modelos cargados")
        except Exception as exc:
            if not silencioso:
                self._lbl_status.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 9pt;")
                self._lbl_status.setText(f"✗ Error: {exc}")

    def _toggle_key_visibility(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._key_edit.setEchoMode(mode)

    def _guardar(self):
        key = self._key_edit.text().strip()
        model = self._model_combo.currentText()
        config_store.set_value(self._conn, "gemini_api_key", key)
        config_store.set_value(self._conn, "gemini_model", model)
        config_store.cargar_en_entorno(self._conn)
        self._lbl_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 9pt;")
        self._lbl_status.setText("✓ Configuración guardada")

    def _test_connection(self):
        key = self._key_edit.text().strip()
        model = self._model_combo.currentText()
        if not key:
            QMessageBox.warning(self, "Sin API Key", "Introduce una API Key antes de probar.")
            return

        self._lbl_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 9pt;")
        self._lbl_status.setText("Probando conexión…")

        try:
            from google import genai  # type: ignore
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(model=model, contents="Di solo: OK")
            texto = resp.text.strip()
            self._lbl_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 9pt;")
            self._lbl_status.setText(f"✓ Conexión OK · respuesta: {texto[:40]}")
        except Exception as exc:
            self._lbl_status.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 9pt;")
            self._lbl_status.setText(f"✗ Error: {exc}")

    # ------------------------------------------------------------------
    def _sincronizar(self):
        resp = QMessageBox.question(
            self,
            "Sincronizar",
            "Se descargarán los cambios del repositorio remoto.\n"
            "Los cambios locales no confirmados se perderán.\n\n"
            "¿Continuar?",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self._sync_output.clear()
        self._btn_sync.setEnabled(False)
        self._append_terminal("$ git fetch origin && git reset --hard origin/main\n", "#6b7280")

        repo_root = str(Path(__file__).resolve().parent.parent.parent.parent)
        cmd = "git fetch origin && git reset --hard origin/main"

        self._process = QProcess(self)
        self._process.setWorkingDirectory(repo_root)
        self._process.readyReadStandardOutput.connect(self._on_sync_stdout)
        self._process.readyReadStandardError.connect(self._on_sync_stderr)
        self._process.finished.connect(self._on_sync_finished)

        if sys.platform == "win32":
            self._process.start("cmd", ["/c", cmd])
        else:
            self._process.start("bash", ["-c", cmd])

    def _append_terminal(self, text: str, color: str = "#d4d4d4"):
        cursor = self._sync_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self._sync_output.setTextCursor(cursor)
        self._sync_output.ensureCursorVisible()

    def _on_sync_stdout(self):
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._append_terminal(data, "#4ade80")

    def _on_sync_stderr(self):
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._append_terminal(data, "#f59e0b")

    def _on_sync_finished(self, exit_code: int, _exit_status):
        self._btn_sync.setEnabled(True)
        if exit_code == 0:
            self._append_terminal("\n✓ Sincronización completada.\n", "#4ade80")
        else:
            self._append_terminal(f"\n✗ Error (código {exit_code}).\n", "#f87171")
