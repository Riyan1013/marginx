"""Tests for finance.calc.money.currency (M1-1 step 5).

All currency records in this file are TEST DATA. The money package itself
contains no currency records (Q5): the real records arrive through the
reference-data fixture provider in M1-5.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from finance.calc.money import currency as currency_module
from finance.calc.money.currency import Currency, CurrencyProvider, CurrencyTable
from finance.calc.money.errors import MoneyError, UnknownCurrencyError
from finance.calc.money.rounding import (
    ModeSource,
    RoundingMode,
    resolve_rounding_mode,
    round_amount,
)

MONEY_DIR = Path(currency_module.__file__).resolve().parent

A = RoundingMode.HALF_UP
B = RoundingMode.HALF_EVEN


# ---------------------------------------------------------------- test data
def make_currency(
    code: str = "AAA",
    minor_units: int = 2,
    rounding_mode: RoundingMode | None = None,
    price_increment: Decimal = Decimal("0.01"),
) -> Currency:
    """Test-local record. Not business data."""
    return Currency(
        code=code,
        minor_units=minor_units,
        rounding_mode=rounding_mode,
        price_increment=price_increment,
    )


TEST_AAA = make_currency("AAA", 2, None, Decimal("0.01"))
TEST_BBB = make_currency("BBB", 0, RoundingMode.HALF_EVEN, Decimal("1"))
TEST_CCC = make_currency("CCC", 3, RoundingMode.HALF_UP, Decimal("0.005"))


# ------------------------------------------------------------ valid Currency
def test_currency_has_exactly_the_four_approved_fields():
    names = [f.name for f in dataclasses.fields(Currency)]
    assert names == ["code", "minor_units", "rounding_mode", "price_increment"]


def test_valid_currency_exposes_all_fields():
    cur = Currency("AAA", 2, RoundingMode.HALF_EVEN, Decimal("0.05"))
    assert cur.code == "AAA"
    assert cur.minor_units == 2
    assert cur.rounding_mode is RoundingMode.HALF_EVEN
    assert cur.price_increment == Decimal("0.05")


def test_all_fields_are_required():
    with pytest.raises(TypeError):
        Currency("AAA", 2, RoundingMode.HALF_UP)  # type: ignore[call-arg]


@pytest.mark.parametrize("units", [0, 1, 2, 3, 8])
def test_minor_units_zero_or_more_accepted(units):
    assert make_currency(minor_units=units).minor_units == units


@pytest.mark.parametrize("mode", [None, A, B])
def test_rounding_mode_none_or_a_roundingmode_is_accepted(mode):
    """U1: None means 'no currency-level setting'."""
    assert make_currency(rounding_mode=mode).rounding_mode is mode


@pytest.mark.parametrize(
    "increment",
    [Decimal("0.01"), Decimal("1"), Decimal("0.05"), Decimal("0.0000000001"), Decimal("1E+3")],
)
def test_positive_increments_accepted_and_kept_as_given(increment):
    cur = make_currency(price_increment=increment)
    assert cur.price_increment == increment
    assert cur.price_increment.as_tuple() == increment.as_tuple()


def test_currency_is_frozen():
    cur = make_currency()
    for field in ("code", "minor_units", "rounding_mode", "price_increment"):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(cur, field, getattr(cur, field))


def test_currency_equality_and_hash_follow_the_fields():
    one = make_currency("AAA", 2, A, Decimal("0.01"))
    same = make_currency("AAA", 2, A, Decimal("0.01"))
    other = make_currency("AAA", 2, B, Decimal("0.01"))
    assert one == same and hash(one) == hash(same)
    assert one != other
    assert len({one, same, other}) == 2


def test_replace_revalidates():
    cur = make_currency()
    assert dataclasses.replace(cur, minor_units=0).minor_units == 0
    with pytest.raises(ValueError):
        dataclasses.replace(cur, minor_units=-1)
    with pytest.raises(ValueError):
        dataclasses.replace(cur, code="aaa")


# ----------------------------------------------------------- invalid Currency
@pytest.mark.parametrize(
    ("code", "error"),
    [
        ("aaa", ValueError),  # lowercase
        ("Aaa", ValueError),
        ("AA", ValueError),
        ("AAAA", ValueError),
        ("", ValueError),
        ("A1A", ValueError),
        ("A-A", ValueError),
        (" AAA", ValueError),
        ("AAA ", ValueError),
        ("AAA\n", ValueError),  # fullmatch, not match with $
        ("\u0391\u0391\u0391", ValueError),  # Greek capital alpha, not ASCII
        ("\u0130NR", ValueError),  # dotted capital I
        (None, TypeError),
        (123, TypeError),
        (b"AAA", TypeError),
        (["AAA"], TypeError),
    ],
)
def test_invalid_code_rejected(code, error):
    with pytest.raises(error):
        make_currency(code=code)


def test_str_subclass_code_rejected():
    class Code(str):
        pass

    with pytest.raises(TypeError):
        make_currency(code=Code("AAA"))


@pytest.mark.parametrize(
    ("units", "error"),
    [
        (-1, ValueError),
        (-100, ValueError),
        (True, TypeError),  # bool is not an acceptable int here
        (False, TypeError),
        (2.0, TypeError),
        ("2", TypeError),
        (None, TypeError),
        (Decimal(2), TypeError),
    ],
)
def test_invalid_minor_units_rejected(units, error):
    with pytest.raises(error):
        make_currency(minor_units=units)


@pytest.mark.parametrize("mode", ["ROUND_HALF_UP", "half_up", 1, 0, Decimal(1), True, A.value])
def test_invalid_rounding_mode_rejected(mode):
    """Only a RoundingMode or None. A plain string is rejected, as in the resolver."""
    with pytest.raises(TypeError):
        make_currency(rounding_mode=mode)


@pytest.mark.parametrize(
    ("increment", "error"),
    [
        (Decimal("0"), ValueError),
        (Decimal("0.00"), ValueError),
        (Decimal("-0"), ValueError),
        (Decimal("-0.01"), ValueError),
        (Decimal("NaN"), ValueError),
        (Decimal("sNaN"), ValueError),
        (Decimal("Infinity"), ValueError),
        (Decimal("-Infinity"), ValueError),
        (0.01, TypeError),
        (1, TypeError),
        ("0.01", TypeError),
        (None, TypeError),
        (True, TypeError),
    ],
)
def test_invalid_price_increment_rejected(increment, error):
    with pytest.raises(error):
        make_currency(price_increment=increment)


# --------------------------------------------------------------- CurrencyTable
def test_table_returns_the_supplied_records():
    table = CurrencyTable([TEST_AAA, TEST_BBB, TEST_CCC])
    assert table.get("AAA") is TEST_AAA
    assert table.get("BBB") is TEST_BBB
    assert table.get("CCC") is TEST_CCC
    assert len(table) == 3


def test_table_accepts_any_iterable():
    assert CurrencyTable(iter([TEST_AAA])).get("AAA") is TEST_AAA
    assert CurrencyTable((c for c in [TEST_BBB])).get("BBB") is TEST_BBB
    assert CurrencyTable(frozenset([TEST_CCC])).get("CCC") is TEST_CCC


def test_empty_table_is_allowed_and_knows_nothing():
    table = CurrencyTable([])
    assert len(table) == 0
    assert "AAA" not in table
    with pytest.raises(UnknownCurrencyError):
        table.get("AAA")


def test_duplicate_codes_rejected():
    clash = make_currency("AAA", 0, None, Decimal("1"))
    with pytest.raises(ValueError, match="AAA"):
        CurrencyTable([TEST_AAA, TEST_BBB, clash])


def test_identical_duplicate_record_still_rejected():
    with pytest.raises(ValueError):
        CurrencyTable([TEST_AAA, TEST_AAA])


@pytest.mark.parametrize("bad", [None, "AAA", 1, {"code": "AAA"}, ("AAA", 2, None, Decimal("1"))])
def test_non_currency_record_rejected(bad):
    with pytest.raises(TypeError):
        CurrencyTable([TEST_AAA, bad])  # type: ignore[list-item]


def test_non_iterable_records_rejected():
    with pytest.raises(TypeError):
        CurrencyTable(None)  # type: ignore[arg-type]


@pytest.mark.parametrize("code", ["ZZZ", "aaa", "Aaa", " AAA", "AAA ", "AAA\n", "", "AA"])
def test_unknown_code_raises_unknowncurrencyerror(code):
    table = CurrencyTable([TEST_AAA])
    with pytest.raises(UnknownCurrencyError):
        table.get(code)


@pytest.mark.parametrize("code", [None, 1, b"AAA", ["AAA"], object()])
def test_non_str_code_is_unknown_not_a_crash(code):
    table = CurrencyTable([TEST_AAA])
    with pytest.raises(UnknownCurrencyError):
        table.get(code)  # type: ignore[arg-type]


def test_unknown_currency_error_is_internal_and_has_no_registry_code():
    table = CurrencyTable([TEST_AAA])
    with pytest.raises(UnknownCurrencyError) as info:
        table.get("ZZZ")
    assert isinstance(info.value, MoneyError)
    assert info.value.code is None
    assert "ZZZ" in str(info.value)


def test_contains_matches_exact_codes_only():
    table = CurrencyTable([TEST_AAA, TEST_BBB])
    assert "AAA" in table and "BBB" in table
    assert "CCC" not in table
    assert "aaa" not in table
    assert "AAA " not in table
    assert None not in table
    assert 1 not in table
    assert b"AAA" not in table
    assert TEST_AAA not in table  # a record is not a code


def test_table_is_a_snapshot_of_its_input():
    source = [TEST_AAA]
    table = CurrencyTable(source)
    source.append(TEST_BBB)
    source.clear()
    assert len(table) == 1
    assert table.get("AAA") is TEST_AAA
    assert "BBB" not in table


def test_table_cannot_be_mutated_after_construction():
    table = CurrencyTable([TEST_AAA])
    with pytest.raises(AttributeError):
        table._records = {}  # type: ignore[misc]
    with pytest.raises(AttributeError):
        table.extra = 1  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        del table._records
    with pytest.raises(TypeError):
        table._records["BBB"] = TEST_BBB  # read-only mapping view
    with pytest.raises(TypeError):
        del table._records["AAA"]
    assert not hasattr(table, "__dict__")
    assert not any(hasattr(table, n) for n in ("add", "put", "set", "remove", "update", "register"))
    assert len(table) == 1 and table.get("AAA") is TEST_AAA


def test_two_tables_do_not_share_state():
    one = CurrencyTable([TEST_AAA])
    two = CurrencyTable([TEST_BBB])
    assert "AAA" in one and "AAA" not in two
    assert "BBB" in two and "BBB" not in one


# ------------------------------------------------------------ provider interface
def test_table_satisfies_the_provider_protocol():
    assert isinstance(CurrencyTable([TEST_AAA]), CurrencyProvider)


def test_any_object_with_get_satisfies_the_provider_protocol():
    class OneCurrency:
        def get(self, code: str) -> Currency:
            if code == "AAA":
                return TEST_AAA
            raise UnknownCurrencyError(code)

    provider: CurrencyProvider = OneCurrency()
    assert isinstance(provider, CurrencyProvider)
    assert provider.get("AAA") is TEST_AAA


def test_object_without_get_is_not_a_provider():
    assert not isinstance(object(), CurrencyProvider)
    assert not isinstance([TEST_AAA], CurrencyProvider)
    assert not isinstance(("AAA", TEST_AAA), CurrencyProvider)


def test_provider_check_is_structural_by_name_only():
    """runtime_checkable looks only for a 'get' attribute, not its signature.

    A dict therefore passes isinstance. That is a known limit of the
    protocol check, not a guarantee: only get(code) -> Currency raising
    UnknownCurrencyError is the contract, and CurrencyTable is the
    implementation that honours it.
    """
    assert isinstance({"AAA": TEST_AAA}, CurrencyProvider)


# ------------------------------------------- currency mode feeds the resolver (Q1)
def test_currency_mode_feeds_the_currency_level():
    assert resolve_rounding_mode(currency=TEST_BBB.rounding_mode) == (B, ModeSource.CURRENCY)
    assert resolve_rounding_mode(currency=TEST_CCC.rounding_mode) == (A, ModeSource.CURRENCY)


def test_currency_without_a_mode_falls_through_to_default():
    assert TEST_AAA.rounding_mode is None
    assert resolve_rounding_mode(currency=TEST_AAA.rounding_mode) == (A, ModeSource.DEFAULT)


def test_stronger_levels_beat_the_currency_mode():
    cur = make_currency(rounding_mode=B)
    assert resolve_rounding_mode(rule=A, currency=cur.rounding_mode) == (A, ModeSource.RULE)
    assert resolve_rounding_mode(jurisdiction=A, currency=cur.rounding_mode) == (
        A,
        ModeSource.JURISDICTION,
    )


def test_none_mode_does_not_override_a_weaker_level_it_does_not_have():
    """A None currency mode lets the default through; it never forces a mode."""
    none_cur = make_currency(rounding_mode=None)
    assert resolve_rounding_mode(currency=none_cur.rounding_mode)[1] is ModeSource.DEFAULT


def test_resolved_currency_mode_applies_when_rounding():
    mode, _ = resolve_rounding_mode(currency=TEST_BBB.rounding_mode)
    # 0.5 at the currency's minor units (0): half-even gives 0, half-up gives 1.
    assert round_amount(Decimal("0.5"), TEST_BBB.minor_units, mode) == Decimal("0")
    default_mode, _ = resolve_rounding_mode(currency=TEST_AAA.rounding_mode)
    assert round_amount(Decimal("0.5"), TEST_BBB.minor_units, default_mode) == Decimal("1")


def test_minor_units_drive_the_rounding_scale():
    for cur, expected in ((TEST_AAA, "1.23"), (TEST_BBB, "1"), (TEST_CCC, "1.235")):
        mode, _ = resolve_rounding_mode(currency=cur.rounding_mode)
        assert str(round_amount(Decimal("1.2345"), cur.minor_units, mode)) == expected


# ------------------------------------------ no hardcoded business data (Q5)
def _money_sources() -> list[Path]:
    files = sorted(MONEY_DIR.glob("*.py"))
    assert files, "no money source files found"
    return files


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of the string constants that are docstrings."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def test_money_package_has_no_currency_code_constants():
    pattern = re.compile(r"\b(INR|USD)\b", re.IGNORECASE)
    offenders = []
    for path in _money_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and pattern.search(node.value)
            ):
                offenders.append(f"{path.name}:{node.lineno}: {node.value!r}")
    assert offenders == []


def test_money_package_never_constructs_a_currency_or_a_table():
    """Records come from the caller (M1-5). Nothing in money builds one."""
    offenders = []
    for path in _money_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name in {"Currency", "CurrencyTable"}:
                    offenders.append(f"{path.name}:{node.lineno}: {name}(...)")
    assert offenders == []


def test_currency_module_has_no_module_level_instances_or_collections():
    tree = ast.parse(Path(currency_module.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            assert not isinstance(value, (ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp))
            assert not isinstance(value, ast.Call) or (
                isinstance(value.func, ast.Attribute) and value.func.attr == "compile"
            )


def test_currency_module_public_surface_has_no_data_objects():
    public = [n for n in vars(currency_module) if not n.startswith("_")]
    for name in public:
        obj = getattr(currency_module, name)
        assert not isinstance(obj, (Currency, CurrencyTable)), name
        assert not isinstance(obj, (list, tuple, dict, set, frozenset)), name


def test_scan_helpers_would_catch_a_hardcoded_record():
    """The scan is not vacuous: it flags a deliberately bad source."""
    bad = ast.parse('RECORDS = [Currency("INR", 2, None, Decimal("0.01"))]\n')
    calls = [n for n in ast.walk(bad) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Name) and c.func.id == "Currency" for c in calls)
    strings = [
        n.value for n in ast.walk(bad) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    assert any(re.search(r"\b(INR|USD)\b", s, re.IGNORECASE) for s in strings)


# ------------------------------------------------------------------ imports
def test_currency_module_imports_only_stdlib_and_its_package():
    tree = ast.parse(Path(currency_module.__file__).read_text(encoding="utf-8"))
    allowed_relative = {"errors", "rounding"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in sys.stdlib_module_names, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert (node.module or "").split(".")[0] in sys.stdlib_module_names, node.module
            else:
                assert node.level == 1 and node.module in allowed_relative, node.module
