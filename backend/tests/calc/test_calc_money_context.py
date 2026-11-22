"""M1-1 step 2: the money calculation context (CA-1, O-16, CL-06).

Run from ``backend/`` as ``python -m pytest``. Nothing here touches project
files; the only global state used is the ambient ``decimal`` context, which
every test that changes it restores.
"""

from __future__ import annotations

import decimal
from decimal import (
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    localcontext,
)

import pytest

from finance.calc.money import context as money_context
from finance.calc.money.context import (
    PRECISION,
    add,
    calc_context,
    div,
    make_context,
    mul,
    total,
)

ALL_SIGNALS = (
    decimal.Clamped,
    decimal.DivisionByZero,
    decimal.Inexact,
    decimal.InvalidOperation,
    decimal.Overflow,
    decimal.Rounded,
    decimal.Subnormal,
    decimal.Underflow,
    decimal.FloatOperation,
)
TRAPPED = (InvalidOperation, DivisionByZero, Overflow)


@pytest.fixture
def hostile_ambient():
    """A deliberately wrong ambient context, restored afterwards."""
    with localcontext(Context(prec=5, rounding=ROUND_HALF_EVEN, traps=[])) as ctx:
        yield ctx


# --------------------------------------------------------------------------
# make_context
# --------------------------------------------------------------------------


def test_precision_constant_is_60():
    assert PRECISION == 60


def test_make_context_precision_and_rounding():
    ctx = make_context()
    assert isinstance(ctx, Context)
    assert ctx.prec == 60
    assert ctx.rounding == ROUND_HALF_UP


@pytest.mark.parametrize("signal", TRAPPED)
def test_make_context_traps_the_three_signals(signal):
    assert make_context().traps[signal] is True


def test_make_context_traps_exactly_the_three_signals():
    ctx = make_context()
    trapped = {s for s in ALL_SIGNALS if ctx.traps[s]}
    assert trapped == set(TRAPPED)


def test_make_context_does_not_trap_inexact():
    # 100.00 / 3 is inexact by design; it is rounded later.
    ctx = make_context()
    assert ctx.traps[Inexact] is False
    ctx.divide(Decimal("100.00"), Decimal(3))  # must not raise


def test_make_context_starts_with_clear_flags():
    ctx = make_context()
    assert not any(ctx.flags[s] for s in ALL_SIGNALS)


def test_make_context_returns_a_distinct_object_each_time():
    a, b = make_context(), make_context()
    assert a is not b


def test_make_context_objects_do_not_share_state():
    a, b = make_context(), make_context()
    a.prec = 7
    a.rounding = ROUND_HALF_EVEN
    a.traps[Overflow] = False
    assert b.prec == 60
    assert b.rounding == ROUND_HALF_UP
    assert b.traps[Overflow] is True
    assert make_context().prec == 60


def test_make_context_ignores_a_hostile_ambient_context(hostile_ambient):
    ctx = make_context()
    assert ctx.prec == 60
    assert ctx.rounding == ROUND_HALF_UP
    assert {s for s in ALL_SIGNALS if ctx.traps[s]} == set(TRAPPED)


# --------------------------------------------------------------------------
# trap behaviour
# --------------------------------------------------------------------------


def test_division_by_zero_raises():
    with pytest.raises(DivisionByZero):
        div(Decimal("1"), Decimal("0"))


def test_zero_over_zero_raises_invalid_operation():
    with pytest.raises(InvalidOperation):
        div(Decimal("0"), Decimal("0"))


def test_overflow_raises():
    with pytest.raises(Overflow):
        mul(Decimal("1E999999"), Decimal("10"))


def test_invalid_operation_raises_on_nan_arithmetic_with_signalling_nan():
    with pytest.raises(InvalidOperation):
        add(Decimal("sNaN"), Decimal("1"))


# --------------------------------------------------------------------------
# helpers run on an explicit context and ignore the ambient one
# --------------------------------------------------------------------------


def test_div_uses_precision_60():
    result = div(Decimal("100.00"), Decimal("3"))
    assert result == Decimal("33.3333333333333333333333333333333333333333333333333333333333")
    assert len(result.as_tuple().digits) == 60


def test_helpers_ignore_a_hostile_ambient_context(hostile_ambient):
    assert div(Decimal("1"), Decimal("3")) == Decimal("0." + "3" * 60)
    assert mul(Decimal("123456789"), Decimal("987654321")) == Decimal("121932631112635269")
    assert add(Decimal("1234567890.12"), Decimal("0.01")) == Decimal("1234567890.13")
    assert total([Decimal("1234567.89"), Decimal("0.01")]) == Decimal("1234567.90")


def test_helpers_do_not_change_the_ambient_context(hostile_ambient):
    before = (hostile_ambient.prec, hostile_ambient.rounding)
    flags_before = {s: hostile_ambient.flags[s] for s in ALL_SIGNALS}

    div(Decimal("100.00"), Decimal("3"))
    mul(Decimal("1.5"), Decimal("2.5"))
    add(Decimal("1"), Decimal("2"))
    total([Decimal("1"), Decimal("2")])

    after = decimal.getcontext()
    assert after is hostile_ambient
    assert (after.prec, after.rounding) == before
    assert {s: after.flags[s] for s in ALL_SIGNALS} == flags_before


def test_helpers_use_an_explicit_context_when_given():
    ctx = Context(prec=5, rounding=ROUND_HALF_EVEN, traps=[])
    assert mul(Decimal("1.23456"), Decimal("1"), ctx) == Decimal("1.2346")
    # The explicit context, not the default 60-digit one, is what ran:
    assert div(Decimal("1"), Decimal("3"), ctx) == Decimal("0.33333")
    # ... and the default is unchanged afterwards.
    assert div(Decimal("1"), Decimal("3")) == Decimal("0." + "3" * 60)


def test_helpers_do_not_change_the_settings_of_an_explicit_context():
    ctx = make_context()
    mul(Decimal("2"), Decimal("3"), ctx)
    assert ctx.prec == 60 and ctx.rounding == ROUND_HALF_UP


# --------------------------------------------------------------------------
# calc_context
# --------------------------------------------------------------------------


def test_calc_context_installs_a_fresh_calculation_context():
    with localcontext(Context(prec=5, rounding=ROUND_HALF_EVEN, traps=[])):
        with calc_context() as ctx:
            current = decimal.getcontext()
            assert current.prec == 60
            assert current.rounding == ROUND_HALF_UP
            assert ctx.prec == 60
            assert Decimal(1) / Decimal(3) == Decimal("0." + "3" * 60)


def test_calc_context_restores_the_previous_context():
    with localcontext(Context(prec=5, rounding=ROUND_HALF_EVEN, traps=[])) as outer:
        with calc_context():
            pass
        restored = decimal.getcontext()
        assert restored.prec == 5
        assert restored.rounding == ROUND_HALF_EVEN
        assert restored is outer


def test_calc_context_restores_the_previous_context_after_an_error():
    with localcontext(Context(prec=5, rounding=ROUND_HALF_EVEN, traps=[])):
        with pytest.raises(DivisionByZero):
            with calc_context():
                Decimal(1) / Decimal(0)
        assert decimal.getcontext().prec == 5


def test_calc_context_yields_a_new_context_each_time():
    with calc_context() as a:
        pass
    with calc_context() as b:
        pass
    assert a is not b


# --------------------------------------------------------------------------
# arithmetic helpers
# --------------------------------------------------------------------------


def test_mul_is_exact_and_keeps_scale():
    assert mul(Decimal("1.50"), Decimal("2.0")) == Decimal("3.000")
    assert str(mul(Decimal("1.50"), Decimal("2.0"))) == "3.000"


def test_add_keeps_the_larger_scale():
    assert str(add(Decimal("1.00"), Decimal("2.5"))) == "3.50"


def test_total_of_nothing_is_zero():
    assert total([]) == Decimal("0")


def test_total_keeps_scale_and_does_not_round():
    # MG-R2 context: three rounded lines add up to 3.00.
    lines = [Decimal("1.00"), Decimal("1.00"), Decimal("1.00")]
    assert str(total(lines)) == "3.00"
    # Unrounded values are summed exactly.
    assert total([Decimal("1.004")] * 3) == Decimal("3.012")


def test_total_accepts_any_iterable():
    assert total(Decimal(i) for i in range(5)) == Decimal(10)


@pytest.mark.parametrize("bad", [1, 1.5, "1", None, True])
def test_helpers_reject_non_decimal_operands(bad):
    with pytest.raises(TypeError):
        mul(bad, Decimal("1"))
    with pytest.raises(TypeError):
        mul(Decimal("1"), bad)
    with pytest.raises(TypeError):
        div(bad, Decimal("1"))
    with pytest.raises(TypeError):
        add(Decimal("1"), bad)
    with pytest.raises(TypeError):
        total([Decimal("1"), bad])


# --------------------------------------------------------------------------
# CL-06: exact multiplication of a 19-digit amount by a 21-digit FX rate
# --------------------------------------------------------------------------


def _from_integer(n: int, exponent: int) -> Decimal:
    """Build n * 10**exponent from its digits, independent of any context.

    ``Decimal(n)`` and ``scaleb`` would round to the ambient precision (28),
    which would make the expected value in these tests wrong.
    """
    return Decimal((0, tuple(int(d) for d in str(n)), exponent))


def test_cl06_nineteen_digit_amount_times_21_digit_fx_rate_is_exact():
    amount = Decimal("1234567890123.123456")  # 13 + 6 = 19 digits (money limit)
    rate = Decimal("12345.1234567890123456")  # 5 + 16 = 21 digits (FX limit)
    assert len(amount.as_tuple().digits) == 19
    assert len(rate.as_tuple().digits) == 21

    ctx = make_context()
    result = mul(amount, rate, ctx)

    expected_int = 1234567890123123456 * 123451234567890123456
    expected = _from_integer(expected_int, -(6 + 16))
    assert result == expected
    assert result.as_tuple().digits == expected.as_tuple().digits
    assert result.as_tuple().exponent == -22
    assert ctx.flags[Inexact] is False


def test_cl06_maximum_in_limit_operands_stay_exact():
    amount = Decimal("9" * 13 + "." + "9" * 6)
    rate = Decimal("9" * 5 + "." + "9" * 16)
    ctx = make_context()
    result = mul(amount, rate, ctx)
    assert result == _from_integer(int("9" * 19) * int("9" * 21), -22)
    assert ctx.flags[Inexact] is False
    assert len(result.as_tuple().digits) <= PRECISION


def test_division_sets_the_inexact_flag_on_its_own_context():
    ctx = make_context()
    div(Decimal("100.00"), Decimal("3"), ctx)
    assert ctx.flags[Inexact] is True


# --------------------------------------------------------------------------
# module surface
# --------------------------------------------------------------------------


def test_module_imports_only_the_standard_library():
    import ast
    import sys
    from pathlib import Path

    tree = ast.parse(Path(money_context.__file__).read_text(encoding="utf-8"))
    stdlib = sys.stdlib_module_names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports expected in context.py"
            roots = [(node.module or "").split(".")[0]]
        else:
            continue
        for root in roots:
            assert root in stdlib, f"{root} is not standard library"
