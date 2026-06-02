# JMFConta

Generador de asientos contables en formato **SAGE** a partir del libro de caja
y los movimientos bancarios del colegio. Aplicación de escritorio en Python + SQLite + PySide6.

## Funcionalidad

1. **Plan de cuentas** — carga inicial desde `docs/PLAN DE CUENTAS JM.xlsx`, búsqueda por código/descripción.
2. **Libro Caja** — importa `docs/Ejemplo subida SAGE.xlsx` (hoja "LIBRO CAJA"). El usuario rellena las fechas (no incluidas en el Excel original) y asigna cuentas a cada movimiento. Saldo acumulado configurable.
3. **Movimientos Banco** — importa `docs/Movimientos_cuenta_banco.xls`. Detecta automáticamente traspasos `SCF-TRASPASO FONDOS` que usan la cuenta de barrido `5510436`.
4. **Mappings** — la 1ª vez que asignas una cuenta a un movimiento, el programa aprende y autocompleta las siguientes con la misma denominación (o `mas_datos` en el banco).
5. **Pre-Asientos SAGE** — genera la previsualización aplicando las reglas contables y exporta a `xlsx` con el formato exacto que espera SAGE:
   `Asiento | Numerodeperiodo | OrdenMovimiento | CargoAbono | CodigoCuenta | FechaAsiento | ImporteAsiento | Comentario`.

## Reglas contables implementadas

| Origen | Importe | Línea 1 (D/H) | Línea 2 (D/H) |
|---|---|---|---|
| Caja (5700000) | + | D 5700000 | H cuenta ingreso |
| Caja (5700000) | − | D cuenta gasto | H 5700000 |
| Banco (5720002) | + | D 5720002 | H cuenta ingreso |
| Banco (5720002) | − | H cuenta gasto/proveedor | D 5720002 |
| Banco `SCF-TRASPASO FONDOS` | + | D 5720002 | H 5510436 (barrido) |
| Banco `SCF-TRASPASO FONDOS` | − | D 5510436 | H 5720002 |

## Instalación

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Uso

```bash
.venv/bin/python -m jmfconta         # desde la raíz del proyecto
# o equivalentemente:
PYTHONPATH=src .venv/bin/python -m jmfconta
```

La base de datos SQLite se crea automáticamente en `data/jmfconta.db`.

## Flujo recomendado

1. **Plan de cuentas** → *Cargar desde Excel…* → seleccionar `docs/PLAN DE CUENTAS JM.xlsx`.
2. **Libro Caja** → *Importar Excel…* → seleccionar el libro de caja del mes.
   - Rellenar las **fechas** (en rojo) y la **fecha por defecto** aplica a todas.
   - Asignar **cuenta** a cada fila (botón "Asignar cuenta…") y *Aprender mapping* para que las denominaciones repetidas se autocompleten.
3. **Movimientos Banco** → *Importar .xls del banco…* → seleccionar el extracto.
   - Las filas con `mas_datos` repetido aprenden la cuenta automáticamente.
4. **Pre-Asientos SAGE** → *Generar previsualización* → revisar → *Exportar a Excel SAGE…*.
5. Importar el xlsx resultante en SAGE.

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python tests/smoke_app.py    # end-to-end con los excels de ejemplo (BD temp)
```

## Estructura

```
src/jmfconta/
├── db.py              Esquema y conexión SQLite
├── repository.py      Operaciones de alto nivel (mappings, movimientos, generación)
├── importers/
│   ├── plan_cuentas.py
│   ├── caja.py
│   └── banco.py
├── sage/
│   ├── rules.py       Reglas de generación de asientos
│   └── exporter.py    Exportador xlsx en formato SAGE
└── ui/
    ├── main_window.py
    ├── plan_cuentas_tab.py
    ├── caja_tab.py
    ├── banco_tab.py
    ├── mappings_tab.py
    ├── pre_asientos_tab.py
    └── cuenta_picker.py
```

## Documentación indexada

`doc-manager` indexa los 3 excels de `docs/` en `.knowledge/` para búsqueda RAG:

```
.knowledge/
├── docs/Movimientos_cuenta_banco.xls   [banco]
├── docs/PLAN DE CUENTAS JM.xlsx        [cuentas]
└── docs/Ejemplo subida SAGE.xlsx       [sage]
```

Reindexar:

```bash
python3 ~/.claude/skills/doc-manager/scripts/add_doc.py "docs/Ejemplo subida SAGE.xlsx" --name "Ejemplo subida SAGE" --tag sage
python3 ~/.claude/skills/doc-manager/scripts/add_doc.py "docs/PLAN DE CUENTAS JM.xlsx" --name "Plan de Cuentas JM" --tag cuentas
python3 ~/.claude/skills/doc-manager/scripts/add_doc.py "docs/Movimientos_cuenta_banco.xls" --name "Movimientos cuenta banco" --tag banco
```
