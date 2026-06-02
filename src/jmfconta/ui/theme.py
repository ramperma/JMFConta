"""Tema visual: hoja de estilos QSS + constantes de paleta.

Se aplica globalmente a la QApplication en __main__.py.
"""
from __future__ import annotations

# Paleta inspirada en interfaces contables modernas (gris suave + acentos).
COLOR_BG = "#f5f6f8"
COLOR_BG_ALT = "#ffffff"
COLOR_BORDER = "#d8dde3"
COLOR_BORDER_STRONG = "#b8c0c9"
COLOR_TEXT = "#1f2937"
COLOR_TEXT_MUTED = "#6b7280"
COLOR_ACCENT = "#2563eb"
COLOR_ACCENT_HOVER = "#1d4ed8"
COLOR_ACCENT_PRESSED = "#1e40af"
COLOR_DANGER = "#dc2626"
COLOR_WARNING = "#d97706"
COLOR_SUCCESS = "#15803d"

# Semántica contable:
COLOR_DEBE = "#1d4ed8"   # D en azul (entrada típica de gasto/banco)
COLOR_HABER = "#b45309"  # H en ámbar (entrada típica de ingreso)
COLOR_INGRESO = "#15803d"
COLOR_GASTO = "#b91c1c"
COLOR_SALDO = "#0f766e"
COLOR_FILA_ALT = "#f8fafc"
COLOR_HOVER = "#eef2f7"
COLOR_SELECTION = "#dbeafe"
COLOR_SELECTION_TEXT = "#0b1320"

FONT_FAMILY = "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
FONT_MONO = "'JetBrains Mono', 'Consolas', 'Courier New', monospace"

QSS = f"""
QWidget {{
    background: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: {FONT_FAMILY};
    font-size: 10pt;
}}

QMainWindow {{
    background: {COLOR_BG};
}}

/* Pestañas */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    background: {COLOR_BG_ALT};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    padding: 9px 18px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {COLOR_TEXT};
    background: {COLOR_HOVER};
}}
QTabBar::tab:selected {{
    background: {COLOR_BG_ALT};
    color: {COLOR_ACCENT};
    border-color: {COLOR_BORDER};
    border-bottom: 2px solid {COLOR_ACCENT};
    font-weight: 600;
}}

/* Botones */
QPushButton {{
    background: {COLOR_BG_ALT};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {COLOR_HOVER};
    border-color: {COLOR_ACCENT};
}}
QPushButton:pressed {{
    background: {COLOR_BORDER};
}}
QPushButton:disabled {{
    color: {COLOR_TEXT_MUTED};
    background: {COLOR_BG};
    border-color: {COLOR_BORDER};
}}
QPushButton[primary="true"] {{
    background: {COLOR_ACCENT};
    color: white;
    border-color: {COLOR_ACCENT};
}}
QPushButton[primary="true"]:hover {{
    background: {COLOR_ACCENT_HOVER};
    border-color: {COLOR_ACCENT_HOVER};
}}
QPushButton[primary="true"]:pressed {{
    background: {COLOR_ACCENT_PRESSED};
}}
QPushButton[danger="true"] {{
    color: {COLOR_DANGER};
    border-color: {COLOR_DANGER};
}}
QPushButton[danger="true"]:hover {{
    background: {COLOR_DANGER};
    color: white;
}}

/* Inputs */
QLineEdit, QDateEdit, QDoubleSpinBox, QSpinBox, QComboBox, QInputDialog QLineEdit {{
    background: {COLOR_BG_ALT};
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: {COLOR_SELECTION};
    selection-color: {COLOR_SELECTION_TEXT};
}}
QLineEdit:focus, QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {COLOR_ACCENT};
}}
QLineEdit::placeholder {{
    color: {COLOR_TEXT_MUTED};
}}

/* Tablas */
QTableWidget, QTableView {{
    background: {COLOR_BG_ALT};
    alternate-background-color: {COLOR_FILA_ALT};
    gridline-color: {COLOR_BORDER};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    selection-background-color: {COLOR_SELECTION};
    selection-color: {COLOR_SELECTION_TEXT};
    font-size: 11pt;
}}
QHeaderView::section {{
    background: #eef0f4;
    color: {COLOR_TEXT};
    padding: 10px 12px;
    border: none;
    border-right: 1px solid {COLOR_BORDER};
    border-bottom: 2px solid {COLOR_ACCENT};
    font-weight: 600;
    font-size: 11pt;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 10px 10px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {COLOR_SELECTION};
    color: {COLOR_SELECTION_TEXT};
}}

/* Listas */
QListWidget {{
    background: {COLOR_BG_ALT};
    alternate-background-color: {COLOR_FILA_ALT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
}}
QListWidget::item:hover {{
    background: {COLOR_HOVER};
}}
QListWidget::item:selected {{
    background: {COLOR_SELECTION};
    color: {COLOR_SELECTION_TEXT};
}}

/* Diálogos */
QDialog {{
    background: {COLOR_BG};
}}
QMessageBox {{
    background: {COLOR_BG_ALT};
}}

/* Scrollbars finos */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER_STRONG};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER_STRONG};
    border-radius: 5px;
    min-width: 24px;
}}

/* Labels auxiliares */
QLabel[role="muted"] {{
    color: {COLOR_TEXT_MUTED};
    font-size: 9pt;
}}
QLabel[role="title"] {{
    font-size: 14pt;
    font-weight: 600;
    color: {COLOR_TEXT};
    padding: 4px 0 8px 0;
}}
QLabel[role="resumen"] {{
    color: {COLOR_TEXT_MUTED};
    font-size: 9pt;
    padding: 4px 0;
}}
"""


def aplicar_tema(app) -> None:
    """Carga QSS y fija font family en la QApplication."""
    app.setStyleSheet(QSS)
    app.setStyle("Fusion")  # estilo base más consistente entre plataformas
