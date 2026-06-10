"""Pestaña Libro de Caja — entrada directa movimiento a movimiento + importación Excel."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCompleter,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pathlib import Path

from .. import repository
from ..importers.caja import importar_libro_caja
from .cuenta_picker import CuentaPickerDialog
from .estilos import set_cuenta, set_importe, set_text
from .theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_SUCCESS,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
)

COL_FECHA, COL_DENOM, COL_IMPORTE, COL_SALDO, COL_CUENTA, COL_COMENT, COL_OBS = range(7)


# ---------------------------------------------------------------------------
# Worker asíncrono para sugerencia Gemini (no bloquea la UI)
# ---------------------------------------------------------------------------

class _GeminiWorker(QThread):
    resultado = Signal(str, str)  # (denominacion_original, cuenta_code_o_vacio)

    def __init__(self, denominacion: str, importe: float, cuentas: list[tuple[str, str]]):
        super().__init__()
        self._denom = denominacion
        self._importe = importe
        self._cuentas = cuentas

    def run(self):
        try:
            from .. import ai_suggester
            code = ai_suggester.sugerir_con_gemini(
                self._denom, self._importe, "CAJA", self._cuentas
            )
            self.resultado.emit(self._denom, code or "")
        except Exception:
            self.resultado.emit(self._denom, "")


class _ImportWorker(QThread):
    progreso = Signal(str)
    terminado = Signal(int, str, str, str, int)

    def __init__(self, db_path: str, path: str):
        super().__init__()
        self._db_path = db_path
        self._path = path

    def run(self):
        from .. import db as db_mod
        conn = db_mod.connect(self._db_path)
        timer = QElapsedTimer()
        timer.start()
        try:
            self.progreso.emit("Leyendo hoja de cálculo…")
            lineas = importar_libro_caja(self._path)
        except Exception as e:
            conn.close()
            self.terminado.emit(0, self._path, str(e), "", timer.elapsed())
            return
        if not lineas:
            conn.close()
            self.terminado.emit(0, self._path, "", "No se detectaron líneas.", timer.elapsed())
            return
        self.progreso.emit(f"Importando {len(lineas)} apuntes y consultando IA…")
        n = repository.insertar_movimientos_caja(conn, lineas)
        repository.registrar_importacion(conn, "CAJA", Path(self._path).name, n)
        conn.close()
        self.terminado.emit(n, self._path, "", "", timer.elapsed())


# ---------------------------------------------------------------------------
# Pestaña principal
# ---------------------------------------------------------------------------

class CajaTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._cache_desc: dict[str, str] = {}
        self._cuenta_seleccionada: str | None = None
        self._cuenta_auto: bool = False
        self._solo_pendientes: bool = True
        self._gemini_worker: _GeminiWorker | None = None
        self._import_worker: _ImportWorker | None = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(600)
        self._debounce.timeout.connect(self._sugerir_cuenta)
        self._build()
        self._refill()

    # ------------------------------------------------------------------
    # Construcción UI
    # ------------------------------------------------------------------

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        titulo = QLabel("Libro de Caja")
        titulo.setProperty("role", "title")
        layout.addWidget(titulo)

        layout.addWidget(self._build_entry_card())
        layout.addWidget(self._build_controls_bar())
        self._lbl_cargando = QLabel("IMPORTANDO LOS APUNTES DE LA HOJA DE CÁLCULO…")
        self._lbl_cargando.setStyleSheet(
            f"color: {COLOR_SUCCESS}; font-weight: bold; font-size: 20pt;"
        )
        self._lbl_cargando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_cargando.setVisible(False)
        self._lbl_opacity = QGraphicsOpacityEffect()
        self._lbl_opacity.setOpacity(1.0)
        self._lbl_cargando.setGraphicsEffect(self._lbl_opacity)
        self._pulse_anim = QPropertyAnimation(self._lbl_opacity, b"opacity", self)
        self._pulse_anim.setDuration(900)
        self._pulse_anim.setStartValue(1.0)
        self._pulse_anim.setKeyValueAt(0.5, 0.35)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        layout.addWidget(self._lbl_cargando)
        layout.addWidget(self._build_tabla(), 1)
        layout.addWidget(self._build_footer())

    def _build_entry_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: white; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
        )
        vl = QVBoxLayout(card)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(10)

        # Cabecera card
        hdr = QLabel("Nueva entrada")
        hdr.setStyleSheet(
            f"font-weight: 600; font-size: 11pt; color: {COLOR_ACCENT}; border: none;"
        )
        vl.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {COLOR_BORDER}; border: none; max-height: 1px;")
        vl.addWidget(sep)

        # Fila 1: Fecha + Importe
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        fecha_lbl = QLabel("Fecha:")
        fecha_lbl.setFixedWidth(70)
        fecha_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._fecha_edit = QDateEdit()
        self._fecha_edit.setCalendarPopup(True)
        self._fecha_edit.setDate(QDate.currentDate())
        self._fecha_edit.setDisplayFormat("dd/MM/yyyy")
        self._fecha_edit.setFixedWidth(130)

        imp_lbl = QLabel("Importe:")
        imp_lbl.setFixedWidth(70)
        imp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._importe_spin = QDoubleSpinBox()
        self._importe_spin.setDecimals(2)
        self._importe_spin.setRange(-999999.99, 999999.99)
        self._importe_spin.setSuffix(" €")
        self._importe_spin.setFixedWidth(140)
        self._importe_spin.setToolTip("Positivo = ingreso  ·  Negativo = gasto")

        row1.addWidget(fecha_lbl)
        row1.addWidget(self._fecha_edit)
        row1.addSpacing(24)
        row1.addWidget(imp_lbl)
        row1.addWidget(self._importe_spin)
        row1.addStretch(1)
        vl.addLayout(row1)

        # Fila 2: Denominación
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        denom_lbl = QLabel("Denominación:")
        denom_lbl.setFixedWidth(100)
        denom_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._denom_edit = QLineEdit()
        self._denom_edit.setPlaceholderText("Descripción del movimiento…")
        self._denom_edit.textChanged.connect(self._on_denom_changed)
        self._denom_edit.returnPressed.connect(lambda: self._obs_edit.setFocus())
        self._setup_autocomplete()
        row2.addWidget(denom_lbl)
        row2.addWidget(self._denom_edit, 1)
        vl.addLayout(row2)

        # Fila 3: Cuenta sugerida
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        cuenta_lbl = QLabel("Cuenta:")
        cuenta_lbl.setFixedWidth(100)
        cuenta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._cuenta_lbl = QLabel("—")
        self._cuenta_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-style: italic;")
        self._cuenta_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._btn_cambiar_cuenta = QPushButton("Buscar cuenta…")
        self._btn_cambiar_cuenta.clicked.connect(self._picker_cuenta_nueva)
        row3.addWidget(cuenta_lbl)
        row3.addWidget(self._cuenta_lbl, 1)
        row3.addWidget(self._btn_cambiar_cuenta)
        vl.addLayout(row3)

        # Fila 4: Observaciones
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        obs_lbl = QLabel("Observaciones:")
        obs_lbl.setFixedWidth(100)
        obs_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._obs_edit = QLineEdit()
        self._obs_edit.setPlaceholderText("Opcional…")
        self._obs_edit.returnPressed.connect(self._añadir)
        row4.addWidget(obs_lbl)
        row4.addWidget(self._obs_edit, 1)
        vl.addLayout(row4)

        # Fila 5: Botón añadir
        row5 = QHBoxLayout()
        row5.addStretch(1)
        self._btn_añadir = QPushButton("  ✚  Añadir entrada")
        self._btn_añadir.setProperty("primary", "true")
        self._btn_añadir.setMinimumWidth(160)
        self._btn_añadir.setMinimumHeight(36)
        self._btn_añadir.clicked.connect(self._añadir)
        row5.addWidget(self._btn_añadir)
        vl.addLayout(row5)

        # Enter avanza al campo siguiente en lugar de submitir
        self._fecha_edit.installEventFilter(self)
        self._importe_spin.installEventFilter(self)

        # Tab order: fecha → importe → denominación → observaciones → botón
        card.setTabOrder(self._fecha_edit, self._importe_spin)
        card.setTabOrder(self._importe_spin, self._denom_edit)
        card.setTabOrder(self._denom_edit, self._obs_edit)
        card.setTabOrder(self._obs_edit, self._btn_añadir)

        return card

    def _build_controls_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        btn_importar = QPushButton("Importar Excel…")
        btn_importar.setProperty("primary", True)
        btn_importar.clicked.connect(self._importar)
        btn_importar.setToolTip("Importar movimientos desde Excel (secundario)")

        btn_aprender = QPushButton("Aprender mapping")
        btn_aprender.clicked.connect(self._aprender)
        btn_aprender.setToolTip("Guardar cuenta de la fila seleccionada para futuras ocurrencias")

        self._btn_filtro = QPushButton("Ver todos")
        self._btn_filtro.setToolTip("Mostrar también movimientos ya exportados a SAGE")
        self._btn_filtro.clicked.connect(self._toggle_filtro)

        btn_eliminar = QPushButton("Eliminar fila(s)")
        btn_eliminar.setProperty("danger", "true")
        btn_eliminar.setToolTip("Borrar las filas seleccionadas (también con tecla Supr)")
        btn_eliminar.clicked.connect(self._eliminar_seleccion)

        btn_vaciar = QPushButton("Vaciar tabla")
        btn_vaciar.setProperty("danger", "true")
        btn_vaciar.clicked.connect(self._vaciar)

        self._search_edit = QLineEdit()
        self._search_edit.setProperty("search", "true")
        self._search_edit.setPlaceholderText("🔍 Filtrar…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(200)
        self._search_edit.setToolTip("Filtra por denominación, cuenta, comentario u observaciones")
        self._search_edit.textChanged.connect(self._aplicar_filtro_texto)

        saldo_lbl = QLabel("Saldo inicial:")
        saldo_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.saldo_inicial = QDoubleSpinBox()
        self.saldo_inicial.setDecimals(2)
        self.saldo_inicial.setRange(-1e9, 1e9)
        self.saldo_inicial.setSuffix(" €")
        self.saldo_inicial.setFixedWidth(130)
        self.saldo_inicial.valueChanged.connect(self._refill)

        fecha_lbl = QLabel("Fecha por defecto:")
        fecha_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.fecha_default = QDateEdit()
        self.fecha_default.setCalendarPopup(True)
        self.fecha_default.setDate(QDate.currentDate())
        self.fecha_default.setDisplayFormat("dd/MM/yyyy")
        self.fecha_default.setFixedWidth(120)

        btn_aplicar_fecha = QPushButton("Aplicar fecha a sin fecha")
        btn_aplicar_fecha.setToolTip("Pone esta fecha en todas las filas que aún no tienen fecha")
        btn_aplicar_fecha.clicked.connect(self._aplicar_fecha)

        bar.addWidget(btn_importar)
        bar.addWidget(btn_aprender)
        bar.addWidget(self._btn_filtro)
        bar.addWidget(btn_eliminar)
        bar.addWidget(btn_vaciar)
        bar.addSpacing(12)
        bar.addWidget(self._search_edit)
        bar.addSpacing(16)
        bar.addWidget(saldo_lbl)
        bar.addWidget(self.saldo_inicial)
        bar.addSpacing(16)
        bar.addWidget(fecha_lbl)
        bar.addWidget(self.fecha_default)
        bar.addWidget(btn_aplicar_fecha)
        bar.addStretch(1)

        # Wrap in a widget so it can be added to QVBoxLayout
        w = QWidget()
        w.setLayout(bar)
        return w

    def _build_tabla(self) -> QTableWidget:
        cols = ["Fecha", "Denominación", "Importe", "Saldo", "Cuenta", "Comentario", "Obs."]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setDefaultSectionSize(44)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(COL_FECHA, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_DENOM, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_IMPORTE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_SALDO, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_CUENTA, QHeaderView.ResizeMode.Interactive)
        self.tabla.setColumnWidth(COL_CUENTA, 280)
        h.setSectionResizeMode(COL_COMENT, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_OBS, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.itemChanged.connect(self._on_item_changed)
        self.tabla.cellDoubleClicked.connect(self._on_double_click)
        atajo_supr = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.tabla)
        atajo_supr.setContext(Qt.ShortcutContext.WidgetShortcut)
        atajo_supr.activated.connect(self._eliminar_seleccion)
        return self.tabla

    def _build_footer(self) -> QLabel:
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setProperty("role", "resumen")
        return self.lbl_resumen

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter
        ):
            if obj is self._fecha_edit:
                self._importe_spin.setFocus()
                self._importe_spin.selectAll()
                return True
            if obj is self._importe_spin:
                self._denom_edit.setFocus()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Autocomplete denominaciones
    # ------------------------------------------------------------------

    def _setup_autocomplete(self):
        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._denom_edit.setCompleter(self._completer)

    def _actualizar_completer(self):
        rows = self._conn.execute(
            "SELECT DISTINCT denominacion FROM movimiento_caja ORDER BY denominacion"
        ).fetchall()
        words = [r[0] for r in rows]
        self._completer.model().setStringList(words)

    # ------------------------------------------------------------------
    # Sugerencia de cuenta (formulario nueva entrada)
    # ------------------------------------------------------------------

    def _on_denom_changed(self, texto: str):
        self._debounce.stop()
        if len(texto.strip()) < 3:
            self._set_cuenta_form(None, estado="vacio")
            return
        self._debounce.start()

    def _sugerir_cuenta(self):
        denom = self._denom_edit.text().strip()
        importe = self._importe_spin.value()
        if not denom:
            return

        # Rápido: mapping + heurísticas (síncrono)
        cuenta = repository.sugerir_cuenta_rapida_caja(self._conn, denom, importe)
        if cuenta:
            self._set_cuenta_form(cuenta, estado="auto")
            return

        # Lento: Gemini (asíncrono)
        import os
        if not os.environ.get("GEMINI_API_KEY"):
            self._set_cuenta_form(None, estado="sin_ia")
            return

        self._set_cuenta_form(None, estado="buscando")
        cuentas_ai = repository.cuentas_para_ai(self._conn, importe)

        if self._gemini_worker and self._gemini_worker.isRunning():
            self._gemini_worker.terminate()

        self._gemini_worker = _GeminiWorker(denom, importe, cuentas_ai)
        self._gemini_worker.resultado.connect(self._on_gemini_resultado)
        self._gemini_worker.start()

    def _on_gemini_resultado(self, denom_orig: str, cuenta: str):
        if self._denom_edit.text().strip() != denom_orig:
            return  # usuario cambió mientras esperábamos
        if cuenta:
            # Validate cuenta exists in plan
            cuenta_res = repository.resolver_cuenta(self._conn, cuenta)
            self._set_cuenta_form(cuenta_res, estado="ai")
        else:
            self._set_cuenta_form(None, estado="no_encontrado")

    def _set_cuenta_form(self, cuenta: str | None, estado: str = "auto"):
        self._cuenta_seleccionada = cuenta
        self._cuenta_auto = estado in ("auto", "ai")

        if estado == "vacio":
            self._cuenta_lbl.setText("—")
            self._cuenta_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-style: italic; border: none;")
        elif estado == "buscando":
            self._cuenta_lbl.setText("🔍 Consultando IA…")
            self._cuenta_lbl.setStyleSheet(f"color: {COLOR_WARNING}; font-style: italic; border: none;")
        elif estado == "sin_ia":
            self._cuenta_lbl.setText("Sin sugerencia — busca manualmente o configura Gemini")
            self._cuenta_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-style: italic; border: none;")
        elif estado == "no_encontrado":
            self._cuenta_lbl.setText("No encontrado — busca manualmente")
            self._cuenta_lbl.setStyleSheet(f"color: {COLOR_WARNING}; font-style: italic; border: none;")
        elif cuenta:
            desc = self._desc_cuenta(cuenta)
            icono = "✦ " if estado == "ai" else "◈ " if estado == "auto" else "✓ "
            color = COLOR_ACCENT if estado in ("auto", "ai") else COLOR_SUCCESS
            self._cuenta_lbl.setText(f"{icono}{cuenta}  {desc}")
            self._cuenta_lbl.setStyleSheet(f"color: {color}; font-weight: 500; border: none;")

    def _desc_cuenta(self, codigo: str) -> str:
        if codigo not in self._cache_desc:
            row = self._conn.execute(
                "SELECT descripcion FROM cuenta WHERE codigo=?", (codigo,)
            ).fetchone()
            self._cache_desc[codigo] = row[0] if row else ""
        return self._cache_desc.get(codigo, "")

    def _picker_cuenta_nueva(self):
        dlg = CuentaPickerDialog(self._conn, self, cuenta_actual=self._cuenta_seleccionada or "")
        if dlg.exec() == CuentaPickerDialog.DialogCode.Accepted and dlg.cuenta:
            self._set_cuenta_form(dlg.cuenta, estado="manual")

    # ------------------------------------------------------------------
    # Añadir nueva entrada
    # ------------------------------------------------------------------

    def _añadir(self):
        denom = self._denom_edit.text().strip()
        if not denom:
            self._denom_edit.setFocus()
            return

        qd = self._fecha_edit.date()
        fecha = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        importe = self._importe_spin.value()
        obs = self._obs_edit.text().strip()
        cuenta = self._cuenta_seleccionada
        cuenta_auto = 1 if self._cuenta_auto else 0

        if importe == 0:
            QMessageBox.warning(self, "Importe cero", "Introduce un importe distinto de cero.")
            self._importe_spin.setFocus()
            return

        repository.insertar_movimiento_caja_uno(
            self._conn, fecha, denom, importe, obs, cuenta, cuenta_auto
        )

        # Aprender mapping si el usuario eligió cuenta manualmente
        if cuenta and not self._cuenta_auto:
            repository.set_mapping(self._conn, "CAJA", denom, cuenta)

        self._actualizar_completer()
        self._refill()
        self._limpiar_form()

    def _aplicar_fecha(self):
        qd = self.fecha_default.date()
        iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        sin_fecha = [r["id"] for r in repository.listar_movimientos_caja(self._conn) if not r["fecha"]]
        for mov_id in sin_fecha:
            repository.actualizar_fecha_caja(self._conn, mov_id, iso)
        self._refill()

    def _limpiar_form(self):
        self._denom_edit.clear()
        self._importe_spin.setValue(0.0)
        self._obs_edit.clear()
        self._set_cuenta_form(None, estado="vacio")
        self._denom_edit.setFocus()

    # ------------------------------------------------------------------
    # Tabla
    # ------------------------------------------------------------------

    def _toggle_filtro(self):
        self._solo_pendientes = not self._solo_pendientes
        self._btn_filtro.setText("Solo pendientes" if not self._solo_pendientes else "Ver todos")
        self._refill()

    def _aplicar_filtro_texto(self):
        texto = self._search_edit.text().strip().upper()
        cols = (COL_DENOM, COL_CUENTA, COL_COMENT, COL_OBS)
        for r in range(self.tabla.rowCount()):
            if not texto:
                self.tabla.setRowHidden(r, False)
                continue
            visible = any(
                texto in (self.tabla.item(r, c).text().upper() if self.tabla.item(r, c) else "")
                for c in cols
            )
            self.tabla.setRowHidden(r, not visible)

    def _refill(self):
        rows = repository.listar_movimientos_caja(self._conn, solo_pendientes=self._solo_pendientes)
        self._precarga_desc_cache()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(rows))
        saldo = float(self.saldo_inicial.value())
        sin_fecha = sin_cuenta = 0

        for r, row in enumerate(rows):
            exportado = bool(row["exported_at"])
            saldo += row["importe"]
            if not row["fecha"]:
                sin_fecha += 1
            if not row["cuenta_sugerida"]:
                sin_cuenta += 1

            fecha_v = row["fecha"] or ""
            it = QTableWidgetItem(fecha_v)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            if not fecha_v:
                it.setForeground(QColor(COLOR_DANGER))
            it.setData(Qt.ItemDataRole.UserRole, row["id"])
            it.setData(Qt.ItemDataRole.UserRole + 1, exportado)
            self.tabla.setItem(r, COL_FECHA, it)

            set_text(self._cell(r, COL_DENOM), row["denominacion"])
            set_importe(self._cell(r, COL_IMPORTE), row["importe"])
            set_importe(self._cell(r, COL_SALDO), saldo, es_saldo=True)
            set_cuenta(
                self._cell(r, COL_CUENTA),
                row["cuenta_sugerida"] or "",
                self._cache_desc.get(row["cuenta_sugerida"] or ""),
                auto=bool(row["cuenta_auto"]),
            )
            set_text(self._cell(r, COL_COMENT), row["comentario_asiento"] or "")
            set_text(
                self._cell(r, COL_OBS),
                row["observaciones"] or "",
                color=COLOR_TEXT_MUTED if not row["observaciones"] else None,
            )

            if exportado:
                _gris = QColor("#9ca3af")
                for col in range(self.tabla.columnCount()):
                    item = self.tabla.item(r, col)
                    if item:
                        item.setForeground(_gris)

        self.tabla.blockSignals(False)
        n = len(rows)
        n_total = self._conn.execute("SELECT COUNT(*) FROM movimiento_caja").fetchone()[0]
        n_export = n_total - self._conn.execute(
            "SELECT COUNT(*) FROM movimiento_caja WHERE exported_at IS NULL"
        ).fetchone()[0]
        export_txt = f"  ·  {n_export} exportados" if n_export else ""
        self.lbl_resumen.setText(
            f"{n} entradas{export_txt}  ·  {sin_fecha} sin fecha  ·  {sin_cuenta} sin cuenta  ·  "
            f"saldo final: {saldo:,.2f} €"
        )
        self._aplicar_filtro_texto()

    def _cell(self, row: int, col: int) -> QTableWidgetItem:
        item = self.tabla.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.tabla.setItem(row, col, item)
        return item

    def _precarga_desc_cache(self):
        self._cache_desc.update(repository.descripciones_cuentas(self._conn))

    # ------------------------------------------------------------------
    # Edición en tabla
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        id_item = self.tabla.item(row, COL_FECHA)
        if not id_item:
            return
        mov_id = int(id_item.data(Qt.ItemDataRole.UserRole))
        col = item.column()
        if col == COL_FECHA:
            texto = item.text().strip()
            if not texto:
                repository.actualizar_fecha_caja(self._conn, mov_id, None)
                item.setForeground(QColor(COLOR_DANGER))
            else:
                parsed = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        parsed = datetime.strptime(texto, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    QMessageBox.warning(self, "Fecha inválida", f"'{texto}' no es fecha válida.")
                    self.tabla.blockSignals(True)
                    item.setText("")
                    self.tabla.blockSignals(False)
                    return
                repository.actualizar_fecha_caja(self._conn, mov_id, parsed.isoformat())
                item.setForeground(QColor(COLOR_TEXT))
        elif col == COL_COMENT:
            repository.actualizar_comentario_caja(self._conn, mov_id, item.text())

    def _on_double_click(self, row: int, col: int):
        if col == COL_CUENTA:
            self._asignar_cuenta_tabla(row)

    def _asignar_cuenta_tabla(self, row: int):
        id_item = self.tabla.item(row, COL_FECHA)
        if not id_item:
            return
        mov_id = int(id_item.data(Qt.ItemDataRole.UserRole))
        rows = repository.listar_movimientos_caja(self._conn)
        mov = next((r for r in rows if r["id"] == mov_id), None)
        if not mov:
            return
        dlg = CuentaPickerDialog(self._conn, self, cuenta_actual=mov["cuenta_sugerida"] or "")
        result = dlg.exec()
        if dlg.limpiar:
            repository.actualizar_cuenta_caja(self._conn, mov_id, None)
            repository.confirmar_cuenta_caja(self._conn, mov_id)
            self._refill()
            return
        if result == CuentaPickerDialog.DialogCode.Accepted and dlg.cuenta:
            repository.actualizar_cuenta_caja(self._conn, mov_id, dlg.cuenta)
            repository.confirmar_cuenta_caja(self._conn, mov_id)
            self._refill()

    def _selected_id(self) -> int | None:
        items = self.tabla.selectedItems()
        if not items:
            return None
        first = self.tabla.item(items[0].row(), COL_FECHA)
        return int(first.data(Qt.ItemDataRole.UserRole)) if first else None

    # ------------------------------------------------------------------
    # Acciones secundarias
    # ------------------------------------------------------------------

    def _importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar libro de caja", "", "Excel (*.xlsx)")
        if not path:
            return
        self._lbl_cargando.setText("IMPORTANDO LOS APUNTES DE LA HOJA DE CÁLCULO…")
        self._lbl_cargando.setVisible(True)
        self._pulse_anim.start()
        db_path = self._conn.execute("PRAGMA database_list").fetchone()[2]
        self._import_worker = _ImportWorker(db_path, path)
        self._import_worker.progreso.connect(self._on_import_progreso)
        self._import_worker.terminado.connect(self._on_import_terminado)
        self._import_worker.start()

    def _on_import_progreso(self, msg: str):
        self._lbl_cargando.setText(msg)

    def _on_import_terminado(self, n: int, path: str, error: str, warning: str, elapsed: int):
        self._finish_importar(n, path, error=error, warning=warning, elapsed=elapsed)

    def _finish_importar(self, n: int, path: str, *, error: str = "", warning: str = "", elapsed: int = 0):
        MIN_MS = 1500
        remaining = max(0, MIN_MS - elapsed)
        def _done():
            self._pulse_anim.stop()
            self._lbl_opacity.setOpacity(1.0)
            self._lbl_cargando.setVisible(False)
            if error:
                QMessageBox.critical(self, "Error", f"No se pudo leer:\n{error}")
            elif warning:
                QMessageBox.warning(self, "Aviso", warning)
            else:
                QMessageBox.information(self, "Importado", f"{n} líneas importadas.")
            self._actualizar_completer()
            self._refill()
        if remaining > 0:
            QTimer.singleShot(remaining, _done)
        else:
            _done()

    def _vaciar(self):
        if QMessageBox.question(
            self, "Vaciar", "¿Borrar todos los movimientos de caja?"
        ) != QMessageBox.StandardButton.Yes:
            return
        repository.vaciar_movimientos_caja(self._conn)
        self._refill()

    def _eliminar_seleccion(self):
        filas = sorted({i.row() for i in self.tabla.selectedItems()})
        ids = []
        exportados = 0
        for r in filas:
            it = self.tabla.item(r, COL_FECHA)
            if not it:
                continue
            ids.append(int(it.data(Qt.ItemDataRole.UserRole)))
            if it.data(Qt.ItemDataRole.UserRole + 1):
                exportados += 1
        if not ids:
            QMessageBox.information(self, "Aviso", "Selecciona una o más filas en la tabla.")
            return
        msg = f"¿Borrar {len(ids)} movimiento(s) de caja?"
        if exportados:
            msg += f"\n\nAtención: {exportados} ya fueron exportados a SAGE."
        if QMessageBox.question(self, "Eliminar", msg) != QMessageBox.StandardButton.Yes:
            return
        repository.eliminar_movimientos_caja(self._conn, ids)
        self._refill()

    def _aprender(self):
        mov_id = self._selected_id()
        if mov_id is None:
            QMessageBox.information(self, "Aviso", "Selecciona una fila en la tabla.")
            return
        rows = repository.listar_movimientos_caja(self._conn)
        row = next((r for r in rows if r["id"] == mov_id), None)
        if not row or not row["cuenta_sugerida"]:
            QMessageBox.information(self, "Aviso", "Asigna primero una cuenta a esa fila.")
            return
        actualizadas = 0
        for r in rows:
            if r["denominacion"].upper() == row["denominacion"].upper() and not r["cuenta_sugerida"]:
                repository.actualizar_cuenta_caja(self._conn, r["id"], row["cuenta_sugerida"])
                repository.confirmar_cuenta_caja(self._conn, r["id"])
                actualizadas += 1
        repository.set_mapping(self._conn, "CAJA", row["denominacion"], row["cuenta_sugerida"])
        QMessageBox.information(
            self, "Mapping aprendido",
            f"Guardado para '{row['denominacion']}'. Aplicado a {actualizadas} fila(s)."
        )
        self._refill()
