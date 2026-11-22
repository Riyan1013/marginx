# MarginX: project notes

## What this is
MarginX is a margin and pricing calculator. A Next.js frontend (`app/`, `lib/finance/calculator.ts`) sits on a Python FastAPI backend (`backend/`). The backend has a legacy engine (`backend/finance/engine.py`, `schemas.py`, `routes.py`) and a new, independent calculation package, `backend/finance/calc/`, built milestone by milestone (M1-0, M1-1, ...) under the approved "Phase 0 Closure and M1 Start Pack" (decisions O-1 to O-22, CA-1 to CA-13).

Next.js here has breaking changes: read `node_modules/next/dist/docs/` before writing frontend code (see `AGENTS.md`).

## How to run
All backend commands run from `backend/` with the venv: `.\.venv\Scripts\python.exe`.
- Tests: `.\.venv\Scripts\python.exe -m pytest -q` (do not use bare `pytest`).
- Guards: `.\.venv\Scripts\python.exe tools/check_m1_guards.py` (must print `OK: ...`).
- Python 3.13.2, Pydantic 2.14.1 are pinned by version tripwire tests (I-5).

## Status
- **M1-0 (guards): done.** Sealed manifest `backend/tools/protected_manifest.json` records six legacy file hashes, two guard file hashes and the import boundary.
- **M1-1 (`money`): implemented.** Full suite: 1005 passed, 1 warning, 0 skipped (221 baseline + 784 new). Guard script OK.
- Next: **M1-2 (`errors`, the error registry and envelope).** Not started.

## File map
```
backend/finance/engine.py, schemas.py, routes.py   legacy (PROTECTED, do not edit)
backend/finance/calc/                              new core; no imports from legacy
  __init__.py                                      docstring only
  money/                                           standard library only (E1)
    errors.py     MoneyError family; only INVALID_DECIMAL, SCALE_EXCEEDED, AMOUNT_OUT_OF_RANGE carry codes
    context.py    precision 60, ROUND_HALF_UP, traps; fresh context; mul/div/add/total
    rounding.py   RoundingMode, ModeSource, 4-level resolver, round_amount, round_up_to_increment, ratio/inverse rounding
    grammar.py    DecimalKind (MONEY, RULE_RATE, FX_RATE), parse_decimal, to_plain_string
    currency.py   Currency model, CurrencyProvider protocol, CurrencyTable (NO records)
backend/tests/calc/                                test_calc_*.py (unique basenames: tests/ has no __init__.py)
backend/tools/check_m1_guards.py, protected_manifest.json   sealed guard and manifest
```

## Decisions to keep
- `money` imports the standard library only. Pydantic is used in tests only. Enforced by `test_calc_layering.py` and the guard script.
- Rounding precedence, strongest first: rule, jurisdiction, currency, default (`ModeSource` values exactly `rule`, `jurisdiction`, `currency`, `default`). Supported modes: `ROUND_HALF_UP` (ties away from zero) and `ROUND_HALF_EVEN`.
- Decimal strings only: `[0-9]+(\.[0-9]+)?`. Order of errors: invalid grammar, scale exceeded, out of range. Limits: MONEY 6 fractional digits and at most 10^12; RULE_RATE 16 fractional digits and at most 10; FX_RATE 16 fractional digits and at most 21 total digits (leading zeros not counted).
- A zero never renders with a minus sign; the scale is kept (`-0.004` at 2 places gives `0.00`).
- Currency records are data, not code. `money` defines the model and lookup interface only; INR and USD records come from the reference-data fixture provider in M1-5. A test forbids hardcoded currency records in `money`.
- Never edit the six legacy files, `check_m1_guards.py`, `test_calc_guards.py` or the manifest by hand. Changes to them go through the guard tool's own reset/migrate flow, with a reason.
- No commits or tags unless the owner asks.

## Open to-dos
- **M2 requirement (U9):** FX override values (the `rate` of an `fx_pair` override) must be validated with `DecimalKind.FX_RATE`. Ordinary rule and override rates use `DecimalKind.RULE_RATE` (CA-6, value at most 10). Do not validate an FX override with `RULE_RATE` and do not widen `RULE_RATE`. M2 should decide whether CA-6 needs a written amendment note. Pinned by a test that `"85"` fails as `RULE_RATE` and passes as `FX_RATE`.
- **M1-3 / M2:** Pydantic findings (recorded in `test_calc_money_versions.py`): a raw Pydantic `Decimal` field accepts JSON numbers, `"1e3"`, `"+5"` and `" 5"`, so every money, rate and FX field needs `parse_decimal` in front. Pydantic serializes `0.0000001` as `"1E-7"`, so a plain serializer built on `to_plain_string` is needed. `DecimalError` is not a `ValueError`, so the boundary must translate it to `PydanticCustomError`.
- Shared Pydantic Decimal types: placement decided at M1-3 or M2 (Q8).
- M1-5: supply INR and USD `Currency` records through the fixture provider.
- `test_calc_layering.py`: the E1 table rows other than `money` were rebuilt from scrambled PDF text. Re-check each row against Closure Pack section E1 (pages 22-23) when that package is created.
- Q1 (rounding precedence) was taken from the owner's wording; original Phase 0 section G2 is not in the project.
