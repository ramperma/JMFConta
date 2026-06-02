# AGENTS.md

Compact guide for OpenCode sessions in this repo. Verified against the source on 2026-06-02.

## What this is

PySide6 desktop app (Python 3, SQLite, `src/` layout) that converts the school's
cash-book + bank-statement into a SAGE-format `xlsx` import. Five tabs:
Plan de cuentas, Libro Caja, Banco, Mappings, Pre-Asientos SAGE.

## Run

```bash
# always from repo root
./run.sh                          # sets PYTHONPATH=src and launches
# or:
PYTHONPATH=src ./.venv/bin/python -m jmfconta
```

`PYTHONPATH=src` is required — the package lives in `src/jmfconta/` and is **not**
pip-installed. `run.sh`/`run.bat` already set it; don't `cd src` to "fix" this.

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python tests/smoke_app.py     # NOT a pytest test, run directly
```

- `tests/conftest.py` inserts `src/` into `sys.path`, so pytest works from the
  root without `PYTHONPATH`. Do not add another conftest that fights this.
- `smoke_app.py` is a manual end-to-end script (no `test_` prefix). It uses
  `QT_QPA_PLATFORM=offscreen`, a temp SQLite, and a **hardcoded absolute path**
  `/home/ramon/CodigoGithub/JMFConta/docs`. If the repo is moved, edit the
  `DOCS = ...` line.
- `test_caja_import.py` and `test_plan_cuentas.py` `pytest.skip` when the
  `docs/*.xlsx`/`*.xls` fixtures are missing — they are not optional on dev
  machines, keep them in tree.

## Where things live

```
src/jmfconta/
  __main__.py          entrypoint — resolves data/jmfconta.db relative to src/
  db.py                SQLite schema (cuenta, mapping, movimiento_*, asiento*)
  repository.py        high-level ops: cargar_plan, mappings, generar_asientos_*
  heuristics.py        auto-suggest cuenta from denom/mas_datos + sign of importe
  importers/           xlsx/xls → dataclasses (LineaCaja, LineaBanco)
    plan_cuentas.py    openpyxl
    caja.py            openpyxl, skips "saldo inicial" + trailing explainer section
    banco.py           xlrd (BIFF .xls only — not .xlsx)
  sage/
    rules.py           constants CUENTA_CAJA/BANCO/BARRIDO + generar_desde_*
    exporter.py        xlsx with exact SAGE header (see CABECERA)
  ui/                  PySide6 tabs, theme.py, cuenta_picker.py
data/jmfconta.db       gitignored, auto-created by __main__ on first run
docs/                  the 3 real spreadsheets the app is built around
.knowledge/            doc-manager RAG index of docs/ (gitignored)
```

The picker (`ui/cuenta_picker.py`) persists the last 10 picked accounts via
`QSettings("JMFConta", "Picker")` for the "Recientes" section. On Linux these
live in `~/.config/JMFConta/Picker.conf`.

## Key invariants (don't break)

- **Caja fix account** = `5700000`. **Banco fix account** = `5720002`.
  **Barrido** = `5510436` used when `movimiento == "SCF-TRASPASO FONDOS"`.
- Mapping key: `CAJA` → `denominacion`; `BANCO` → `mas_datos` (contrapartida).
- Bank `SCF-TRASPASO FONDOS` always uses the barrido account; the
  `cuenta_contrapartida` arg is ignored for it (see `test_banco_barrido_ignora_contrapartida`).
- Caja dates are often empty in the source xlsx — the importer inherits the
  previous row's date (`_a_fecha` in `caja.py:44`). The user fills the real
  date in the UI tab; `repository.actualizar_fecha_caja` keeps `periodo` in sync.
- `generar_desde_caja` raises `ValueError` on empty contrapartida. UI must
  block, not silently skip (test asserts this).
- Auto-suggest: `src/jmfconta/heuristics.py` suggests a cuenta at insert time
  when no manual mapping exists. Flag `cuenta_auto=1` means "heuristic, verify".
  User confirmation (picker, "Aprender mapping", "Limpiar") sets `cuenta_auto=0`.
  Yellow background in the table marks auto-suggested rows.

## SAGE export format

Header (row 1, bold) and column order are exact and asserted in
`tests/test_exporter.py:23-26`:
`Asiento | Numerodeperiodo | OrdenMovimiento | CargoAbono | CodigoCuenta | FechaAsiento | ImporteAsiento | Comentario`.
Sheet name = `IMPORTAR A SAGE`. Fecha cell uses `yyyy-mm-dd`; importe `0.00`.

## Style / quality

- No `pyproject.toml`, no linter, no formatter, no typechecker, no CI, no
  pre-commit. Do **not** introduce `ruff`/`black`/`mypy` on your own — confirm
  with the user first. Match the existing style: `from __future__ import
  annotations`, type hints, frozen dataclasses, `db.transaction()` context
  manager for writes.
- Keep dependencies to what's in `requirements.txt` (openpyxl, xlrd, PySide6).

## Setup / gotchas

- `.venv/` already exists and is gitignored. Recreate with
  `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- `data/jmfconta.db` is gitignored but present in the working tree (development
  DB). Don't `git add` it; if a test creates a stray `data/*.db`, delete it
  before committing.
- `xlrd>=2.0` only reads `.xls` (BIFF). The bank file is `.xls`; do not
  "modernize" it to `.xlsx` without checking the importer still works.
- `docs/Ejemplo subida SAGE.xlsx` contains an explainer section at the bottom
  (`"si el importe del asiento es..."` etc.) — `caja.py` `SECCION_BLOQUEO`
  detects it and stops reading. Don't strip that block from the file; the
  importer depends on the detection strings.
- The `doc-manager` RAG index in `.knowledge/` mirrors `docs/`. To reindex, see
  the three `add_doc.py` commands at the bottom of `README.md`.

## Verification loop

After a non-trivial change, run from repo root:

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python tests/smoke_app.py
```

The smoke script exercises the full pipeline (plan → caja → banco → mappings
→ pre-asientos → SAGE xlsx → UI tabs) against a temp DB and prints an 8-row
preview of the SAGE export for human eyeballing.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **JMFConta** (510 symbols, 841 relationships, 32 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/JMFConta/context` | Codebase overview, check index freshness |
| `gitnexus://repo/JMFConta/clusters` | All functional areas |
| `gitnexus://repo/JMFConta/processes` | All execution flows |
| `gitnexus://repo/JMFConta/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
