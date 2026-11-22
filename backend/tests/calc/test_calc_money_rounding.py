"""M1-1 step 3: rounding, the four-level mode resolver and the round-up helper.

Covers the gate probes MG-R1, MG-R1o, MG-R2 and MG-A1, the four-level
precedence (Q1) with ``mode_source`` at each level, the negative-zero rules
(Q6) and ``round_up_to_increment`` (Q7, U6).

Every numeric input is a ``Decimal`` built from a string, never a float, except
the tests that prove a float is rejected.

Plain-string rendering lives in ``grammar.to_plain_string`` (step 4), so the
checks here render with ``format(value, "f")``; the ``to_plain_string`` side of
the negative-zero rules is tested in the grammar tests.

Run from ``backend/`` as ``python -m pytest``. Nothing here touches project
files; tests that change the ambient ``decimal`` context restore it.
"""

from __future__ import annotations

import ast
import itertools
import math
from decimal import ROUND_HALF_EVEN as D_HALF_EVEN
from decimal import ROUND_HALF_UP as D_HALF_UP
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from finance.calc.money import rounding
from finance.calc.money.context import add, div, mul, total
from finance.calc.money.errors import MoneyError, RoundingModeError
from finance.calc.money.rounding import (
    DEFAULT_MODE,
    INVERSE_RATE_PLACES,
    MODE_PRECEDENCE,
    RATIO_PLACES,
    ModeSource,
    RoundingMode,
    resolve_rounding_mode,
    round_amount,
    round_inverse_rate,
    round_ratio,
    round_up_to_increment,
)

D = Decimal
A = RoundingMode.HALF_UP
B = RoundingMode.HALF_EVEN


def plain(value: Decimal) -> str:
    return format(value, "f")


def exponent(value: Decimal) -> int:
    return value.as_tuple().exponent  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Enum names and constants
# --------------------------------------------------------------------------


class TestNames:
    def test_mode_source_values_are_exact(self):
        assert {m.value for m in ModeSource} == {
            "rule",
            "jurisdiction",
            "currency",
            "default",
        }

    def test_policy_default_does_not_exist(self):
        assert not hasattr(ModeSource, "POLICY_DEFAULT")
        assert "policy_default" not in {m.value for m in ModeSource}

    def test_mode_source_members(self):
        assert ModeSource.RULE.value == "rule"
        assert ModeSource.JURISDICTION.value == "jurisdiction"
        assert ModeSource.CURRENCY.value == "currency"
        assert ModeSource.DEFAULT.value == "default"

    def test_precedence_is_strongest_first(self):
        assert MODE_PRECEDENCE == (
            ModeSource.RULE,
            ModeSource.JURISDICTION,
            ModeSource.CURRENCY,
        )
        assert ModeSource.DEFAULT not in MODE_PRECEDENCE

    def test_rounding_modes_are_the_two_approved(self):
        assert {m.value for m in RoundingMode} == {"ROUND_HALF_UP", "ROUND_HALF_EVEN"}

    def test_default_mode_is_half_up(self):
        assert DEFAULT_MODE is RoundingMode.HALF_UP

    def test_fixed_places(self):
        assert RATIO_PLACES == 10
        assert INVERSE_RATE_PLACES == 16


# --------------------------------------------------------------------------
# Gate probes
# --------------------------------------------------------------------------


class TestGateProbes:
    @pytest.mark.parametrize(
        ("raw", "places", "expected"),
        [
            ("2.345", 2, "2.35"),
            ("2.355", 2, "2.36"),
            ("0.005", 2, "0.01"),
            ("0.015", 2, "0.02"),
            ("1234.5", 0, "1235"),
            ("1235.5", 0, "1236"),
        ],
    )
    def test_mg_r1_half_up(self, raw, places, expected):
        assert plain(round_amount(D(raw), places, RoundingMode.HALF_UP)) == expected

    @pytest.mark.parametrize(
        ("raw", "places", "expected"),
        [
            ("2.345", 2, "2.34"),
            ("2.355", 2, "2.36"),
            ("0.005", 2, "0.00"),
            ("0.015", 2, "0.02"),
            ("1234.5", 0, "1234"),
            ("1235.5", 0, "1236"),
        ],
    )
    def test_mg_r1o_half_even(self, raw, places, expected):
        assert plain(round_amount(D(raw), places, RoundingMode.HALF_EVEN)) == expected

    def test_mg_r1o_jurisdiction_override_selects_half_even(self):
        mode, source = resolve_rounding_mode(jurisdiction=RoundingMode.HALF_EVEN)
        assert (mode, source) == (RoundingMode.HALF_EVEN, ModeSource.JURISDICTION)
        assert plain(round_amount(D("2.345"), 2, mode)) == "2.34"

    def test_mg_r1_default_is_half_up(self):
        mode, source = resolve_rounding_mode()
        assert (mode, source) == (RoundingMode.HALF_UP, ModeSource.DEFAULT)
        assert plain(round_amount(D("2.345"), 2)) == "2.35"

    def test_mg_r2_round_each_line_then_total(self):
        lines = [D("1.004"), D("1.004"), D("1.004")]
        rounded = [round_amount(x, 2) for x in lines]
        assert [plain(x) for x in rounded] == ["1.00", "1.00", "1.00"]
        assert plain(total(rounded)) == "3.00"
        # Rounding the unrounded total would give a different answer.
        assert plain(round_amount(total(lines), 2)) == "3.01"

    def test_mg_a1_division_uses_unrounded_value_and_leaves_input_alone(self):
        amount = D("100.00")
        per_unit_exact = div(amount, D(3))
        per_unit = round_amount(per_unit_exact, 2)
        assert plain(per_unit) == "33.33"
        assert plain(amount) == "100.00"  # the input is untouched
        # The exact quotient is kept at full precision; only the display value
        # is rounded.
        assert per_unit_exact != per_unit
        assert plain(per_unit_exact).startswith("33.3333333333")
        # No residue is distributed: three rounded units are simply 99.99.
        assert plain(total([per_unit, per_unit, per_unit])) == "99.99"


# --------------------------------------------------------------------------
# Four-level precedence (Q1)
# --------------------------------------------------------------------------


def expected_resolution(rule, jurisdiction, currency):
    """Independent strongest-first loop, written separately from the resolver."""
    for source, value in (
        ("rule", rule),
        ("jurisdiction", jurisdiction),
        ("currency", currency),
    ):
        if value is not None:
            return value, ModeSource(source)
    return RoundingMode.HALF_UP, ModeSource.DEFAULT


class TestResolver:
    def test_each_level_alone(self):
        assert resolve_rounding_mode(rule=B) == (B, ModeSource.RULE)
        assert resolve_rounding_mode(jurisdiction=B) == (B, ModeSource.JURISDICTION)
        assert resolve_rounding_mode(currency=B) == (B, ModeSource.CURRENCY)
        assert resolve_rounding_mode() == (A, ModeSource.DEFAULT)

    @pytest.mark.parametrize("strong", [A, B])
    def test_rule_beats_jurisdiction(self, strong):
        weak = B if strong is A else A
        assert resolve_rounding_mode(rule=strong, jurisdiction=weak) == (
            strong,
            ModeSource.RULE,
        )

    @pytest.mark.parametrize("strong", [A, B])
    def test_rule_beats_currency(self, strong):
        weak = B if strong is A else A
        assert resolve_rounding_mode(rule=strong, currency=weak) == (
            strong,
            ModeSource.RULE,
        )

    @pytest.mark.parametrize("strong", [A, B])
    def test_jurisdiction_beats_currency(self, strong):
        weak = B if strong is A else A
        assert resolve_rounding_mode(jurisdiction=strong, currency=weak) == (
            strong,
            ModeSource.JURISDICTION,
        )

    def test_three_way_conflict_rule_wins(self):
        # Only two modes exist, so a value must repeat; the rule differs from
        # both weaker levels in each arrangement.
        assert resolve_rounding_mode(rule=B, jurisdiction=A, currency=A) == (
            B,
            ModeSource.RULE,
        )
        assert resolve_rounding_mode(rule=A, jurisdiction=B, currency=B) == (
            A,
            ModeSource.RULE,
        )

    def test_fall_through_without_rule(self):
        assert resolve_rounding_mode(jurisdiction=B, currency=A) == (
            B,
            ModeSource.JURISDICTION,
        )
        assert resolve_rounding_mode(jurisdiction=A, currency=B) == (
            A,
            ModeSource.JURISDICTION,
        )

    def test_fall_through_without_rule_and_jurisdiction(self):
        assert resolve_rounding_mode(currency=B) == (B, ModeSource.CURRENCY)
        assert resolve_rounding_mode(currency=A) == (A, ModeSource.CURRENCY)

    def test_source_is_the_supplier_not_the_value(self):
        # A supplied value equal to the default still reports its own level.
        assert resolve_rounding_mode(rule=A) == (A, ModeSource.RULE)
        assert resolve_rounding_mode(jurisdiction=A) == (A, ModeSource.JURISDICTION)
        assert resolve_rounding_mode(currency=A) == (A, ModeSource.CURRENCY)
        # Same value at several levels: the strongest is reported.
        assert resolve_rounding_mode(rule=A, jurisdiction=A, currency=A) == (
            A,
            ModeSource.RULE,
        )
        assert resolve_rounding_mode(jurisdiction=B, currency=B) == (
            B,
            ModeSource.JURISDICTION,
        )

    @pytest.mark.parametrize(
        ("rule", "jurisdiction", "currency"),
        list(itertools.product([None, A, B], repeat=3)),
    )
    def test_exhaustive_27_combinations(self, rule, jurisdiction, currency):
        assert len(list(itertools.product([None, A, B], repeat=3))) == 27
        assert resolve_rounding_mode(
            rule=rule, jurisdiction=jurisdiction, currency=currency
        ) == expected_resolution(rule, jurisdiction, currency)

    @pytest.mark.parametrize(
        "bad", ["ROUND_HALF_UP", "half_up", 1, 0, True, D("1"), 1.5, object()]
    )
    @pytest.mark.parametrize("level", ["rule", "jurisdiction", "currency"])
    def test_rejects_non_modes_at_every_level(self, level, bad):
        with pytest.raises(RoundingModeError):
            resolve_rounding_mode(**{level: bad})

    def test_rejects_a_bad_value_even_when_a_stronger_level_wins(self):
        with pytest.raises(RoundingModeError):
            resolve_rounding_mode(rule=A, currency="ROUND_HALF_EVEN")
        with pytest.raises(RoundingModeError):
            resolve_rounding_mode(rule=A, jurisdiction="x")

    def test_arguments_are_keyword_only(self):
        with pytest.raises(TypeError):
            resolve_rounding_mode(A)  # type: ignore[misc]
        with pytest.raises(TypeError):
            resolve_rounding_mode(A, B, A)  # type: ignore[misc]

    def test_unknown_keyword_is_rejected(self):
        with pytest.raises(TypeError):
            resolve_rounding_mode(policy_default=A)  # type: ignore[call-arg]

    def test_rounding_mode_error_is_internal(self):
        assert issubclass(RoundingModeError, MoneyError)
        assert RoundingModeError.code is None

    @pytest.mark.parametrize(
        ("rule", "jurisdiction", "currency", "expected_text", "source"),
        [
            (None, None, None, "2.35", ModeSource.DEFAULT),
            (A, B, B, "2.35", ModeSource.RULE),
            (B, A, A, "2.34", ModeSource.RULE),
            (None, B, A, "2.34", ModeSource.JURISDICTION),
            (None, A, B, "2.35", ModeSource.JURISDICTION),
            (None, None, B, "2.34", ModeSource.CURRENCY),
            (None, None, A, "2.35", ModeSource.CURRENCY),
        ],
    )
    def test_resolved_mode_is_the_one_that_rounds(
        self, rule, jurisdiction, currency, expected_text, source
    ):
        mode, got_source = resolve_rounding_mode(
            rule=rule, jurisdiction=jurisdiction, currency=currency
        )
        assert got_source is source
        assert plain(round_amount(D("2.345"), 2, mode)) == expected_text


# --------------------------------------------------------------------------
# round_amount
# --------------------------------------------------------------------------


class TestRoundAmount:
    def test_negative_ties_go_away_from_zero(self):
        assert plain(round_amount(D("-2.345"), 2)) == "-2.35"
        assert plain(round_amount(D("-0.005"), 2)) == "-0.01"

    def test_negative_ties_half_even(self):
        assert plain(round_amount(D("-2.345"), 2, B)) == "-2.34"
        assert plain(round_amount(D("-0.015"), 2, B)) == "-0.02"
        assert plain(round_amount(D("-0.025"), 2, B)) == "-0.02"

    def test_value_at_scale_is_unchanged(self):
        value = D("12.34")
        result = round_amount(value, 2)
        assert result == value and exponent(result) == -2

    def test_scale_is_extended_when_shorter(self):
        assert plain(round_amount(D("1.2"), 2)) == "1.20"
        assert plain(round_amount(D("1"), 2)) == "1.00"

    def test_result_has_exactly_the_requested_scale(self):
        for places in (0, 1, 2, 6, 10, 16):
            assert exponent(round_amount(D("3.14159"), places)) == -places

    @pytest.mark.parametrize(
        "raw",
        [
            "999999999999.999999",  # the MONEY maximum with 6 fractional digits
            "1000000000000",
            "12345.1234567890123456",  # 21 digits, the FX_RATE shape
            "0.0000000000000001",
        ],
    )
    def test_quantizing_never_raises_on_in_limit_values(self, raw):
        for places in (0, 2, 6, 10, 16):
            round_amount(D(raw), places)

    def test_money_maximum_rounds_up_to_the_cap(self):
        assert plain(round_amount(D("999999999999.999999"), 2)) == "1000000000000.00"

    @pytest.mark.parametrize("bad", [-0.004, 1, "1.00", True, None, b"1"])
    def test_rejects_non_decimal_values(self, bad):
        with pytest.raises(TypeError):
            round_amount(bad, 2)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ["NaN", "sNaN", "Infinity", "-Infinity"])
    def test_rejects_non_finite_values(self, bad):
        with pytest.raises(ValueError):
            round_amount(D(bad), 2)

    @pytest.mark.parametrize("bad", [-1, True, False, 1.0, 2.5, "2", None, 61])
    def test_rejects_bad_places(self, bad):
        with pytest.raises(ValueError):
            round_amount(D("1.234"), bad)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad", ["ROUND_HALF_UP", D_HALF_UP, D_HALF_EVEN, None, 1]
    )
    def test_rejects_bad_modes(self, bad):
        with pytest.raises(RoundingModeError):
            round_amount(D("1.234"), 2, bad)  # type: ignore[arg-type]

    def test_input_is_not_modified(self):
        value = D("2.345")
        round_amount(value, 2)
        assert plain(value) == "2.345"

    def test_early_smoke_fx_conversion(self):
        # Not the gate: a small end-to-end check of multiply then round.
        converted = mul(D("7.4655"), D("85"))
        assert plain(converted) == "634.5675"
        assert plain(round_amount(converted, 2)) == "634.57"
        assert plain(round_amount(D("7.4655"), 2)) == "7.47"


# --------------------------------------------------------------------------
# Negative zero and scale (Q6)
# --------------------------------------------------------------------------

TINY_NEGATIVES = ["-0.001", "-0.004", "-0.0049", "-0.00001", "-0.0000000001"]


class TestNegativeZero:
    @pytest.mark.parametrize("raw", ["-0.004", "-0.001", "-0.0049"])
    def test_rounds_to_zero_half_up(self, raw):
        assert plain(round_amount(D(raw), 2)) == "0.00"

    @pytest.mark.parametrize("raw", ["-0.004", "-0.005"])
    def test_rounds_to_zero_half_even(self, raw):
        # The tie -0.005 goes to the even neighbour, which is zero.
        assert plain(round_amount(D(raw), 2, RoundingMode.HALF_EVEN)) == "0.00"

    @pytest.mark.parametrize("mode", [A, B])
    @pytest.mark.parametrize("raw", TINY_NEGATIVES)
    def test_never_minus_zero(self, raw, mode):
        text = plain(round_amount(D(raw), 2, mode))
        assert text == "0.00"
        assert text != "-0.00"
        assert text != "-0"
        assert not text.startswith("-")

    def test_scale_is_preserved_at_two_places(self):
        result = round_amount(D("-0.004"), 2)
        assert exponent(result) == -2
        assert plain(result) == "0.00"  # not shortened to "0"

    def test_scale_is_preserved_at_zero_places(self):
        result = round_amount(D("-0.4"), 0)
        assert exponent(result) == 0
        assert plain(result) == "0"

    def test_scale_is_preserved_at_three_places(self):
        result = round_amount(D("-0.0004"), 3)
        assert exponent(result) == -3
        assert plain(result) == "0.000"

    def test_value_is_positive_zero(self):
        result = round_amount(D("-0.004"), 2)
        assert result.is_signed() is False
        assert result.is_zero()
        assert result == D("0")

    def test_arithmetic_can_produce_a_signed_zero_which_rounding_clears(self):
        signed = mul(D("-1"), D("0.00"))
        assert signed.is_signed() is True  # the hazard exists upstream
        assert plain(signed) == "-0.00"
        cleared = round_amount(signed, 2)
        assert cleared.is_signed() is False
        assert plain(cleared) == "0.00"

    def test_negative_zero_input_is_cleared_at_any_scale(self):
        assert plain(round_amount(D("-0"), 2)) == "0.00"
        assert plain(round_amount(D("-0.00"), 2)) == "0.00"
        assert plain(round_amount(D("-0E-10"), 0)) == "0"

    def test_non_zero_negatives_keep_their_sign(self):
        assert plain(round_amount(D("-0.01"), 2)) == "-0.01"
        assert plain(round_amount(D("-0.005"), 2)) == "-0.01"  # ties away from zero
        assert plain(round_amount(D("-0.0051"), 2)) == "-0.01"
        assert round_amount(D("-0.01"), 2).is_signed() is True

    def test_positive_zero_is_unchanged(self):
        result = round_amount(D("0.00"), 2)
        assert plain(result) == "0.00" and exponent(result) == -2

    def test_ratio_and_inverse_rate_also_clear_the_sign(self):
        assert round_ratio(D("-0.00000000001")).is_signed() is False
        assert plain(round_ratio(D("-0.00000000001"))) == "0." + "0" * 10
        assert round_inverse_rate(D("-1E-20")).is_signed() is False
        assert plain(round_inverse_rate(D("-1E-20"))) == "0." + "0" * 16

    def test_round_up_to_increment_clears_the_sign(self):
        result = round_up_to_increment(D("-0.001"), D("0.01"))
        assert result.is_signed() is False
        assert plain(result) == "0.00"


# --------------------------------------------------------------------------
# round_up_to_increment (Q7, U6)
# --------------------------------------------------------------------------


class TestRoundUpToIncrement:
    def test_rounds_up_to_the_next_multiple(self):
        assert plain(round_up_to_increment(D("4090.1554"), D("0.01"))) == "4090.16"

    def test_exact_multiple_is_unchanged(self):
        result = round_up_to_increment(D("4090.16"), D("0.01"))
        assert result == D("4090.16") and plain(result) == "4090.16"

    def test_a_tiny_excess_still_rounds_up(self):
        assert plain(round_up_to_increment(D("4090.1600001"), D("0.01"))) == "4090.17"

    def test_never_rounds_down(self):
        assert plain(round_up_to_increment(D("4090.1511"), D("0.01"))) == "4090.16"

    def test_negative_values_round_towards_positive_infinity(self):
        assert plain(round_up_to_increment(D("-4090.1554"), D("0.01"))) == "-4090.15"
        assert plain(round_up_to_increment(D("-4090.16"), D("0.01"))) == "-4090.16"

    def test_larger_increments(self):
        assert plain(round_up_to_increment(D("4090.1554"), D("0.05"))) == "4090.20"
        assert plain(round_up_to_increment(D("4090.1"), D("0.5"))) == "4090.5"
        assert plain(round_up_to_increment(D("4090.1554"), D("1"))) == "4091"
        assert plain(round_up_to_increment(D("4090.1554"), D("10"))) == "4100"

    def test_result_carries_the_increment_scale(self):
        assert exponent(round_up_to_increment(D("5"), D("0.01"))) == -2
        assert plain(round_up_to_increment(D("5"), D("0.01"))) == "5.00"
        assert exponent(round_up_to_increment(D("5.1"), D("1"))) == 0

    def test_zero_value(self):
        assert plain(round_up_to_increment(D("0"), D("0.01"))) == "0.00"

    @pytest.mark.parametrize("bad", ["0", "0.00", "-0.01", "-1"])
    def test_rejects_increment_not_above_zero(self, bad):
        with pytest.raises(ValueError):
            round_up_to_increment(D("1.5"), D(bad))

    @pytest.mark.parametrize("bad", ["NaN", "Infinity"])
    def test_rejects_non_finite_increment(self, bad):
        with pytest.raises(ValueError):
            round_up_to_increment(D("1.5"), D(bad))

    @pytest.mark.parametrize("bad", [0.01, 1, "0.01", None])
    def test_rejects_non_decimal_increment(self, bad):
        with pytest.raises(TypeError):
            round_up_to_increment(D("1.5"), bad)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", [1.5, 1, "1.5", None])
    def test_rejects_non_decimal_value(self, bad):
        with pytest.raises(TypeError):
            round_up_to_increment(bad, D("0.01"))  # type: ignore[arg-type]

    def test_rejects_non_finite_value(self):
        with pytest.raises(ValueError):
            round_up_to_increment(D("NaN"), D("0.01"))

    def test_quotient_just_above_an_integer_is_not_lost(self):
        # 1.000...01 over 1 is just above 1: the ceiling is 2. A rounded
        # division could collapse this to 1.
        value = D("1." + "0" * 38 + "1")
        assert plain(round_up_to_increment(value, D("1"))) == "2"

    def test_agrees_with_an_independent_fraction_calculation(self):
        values = ["0", "0.001", "0.01", "0.0099", "1.005", "-0.001", "-1.005",
                  "4090.1554", "-4090.1554", "999999999999.999999", "7.25", "7.2500001"]
        increments = ["0.01", "0.05", "0.5", "1", "2.50", "0.0001", "10", "0.000001"]
        for raw_value, raw_inc in itertools.product(values, increments):
            value, inc = D(raw_value), D(raw_inc)
            expected = Fraction(math.ceil(Fraction(value) / Fraction(inc))) * Fraction(inc)
            got = round_up_to_increment(value, inc)
            assert Fraction(got) == expected, (raw_value, raw_inc)
            assert exponent(got) == exponent(inc)

    def test_result_is_never_below_the_value_and_less_than_one_step_above(self):
        inc = D("0.05")
        for raw in ["0.01", "0.049", "0.05", "0.051", "123.456", "-0.049", "-0.06"]:
            value = D(raw)
            got = round_up_to_increment(value, inc)
            assert got >= value
            assert got - value < inc


# --------------------------------------------------------------------------
# Ratio and inverse-rate helpers (CA-1)
# --------------------------------------------------------------------------


class TestFixedScaleHelpers:
    def test_ratio_has_ten_places(self):
        result = round_ratio(div(D(1), D(3)))
        assert exponent(result) == -10
        assert plain(result) == "0.3333333333"

    def test_ratio_rounds_half_up(self):
        assert plain(round_ratio(D("0.00000000005"))) == "0.0000000001"
        assert plain(round_ratio(D("0.00000000004"))) == "0.0000000000"

    def test_inverse_rate_has_sixteen_places(self):
        result = round_inverse_rate(div(D(1), D(85)))
        assert exponent(result) == -16
        assert plain(result) == "0.0117647058823529"

    def test_inverse_rate_rounds_half_up(self):
        assert plain(round_inverse_rate(D("0.00000000000000005"))) == "0.0000000000000001"
        assert plain(round_inverse_rate(D("0.00000000000000004"))) == "0.0000000000000000"

    def test_fx_rate_value_at_the_digit_limit_is_unchanged(self):
        value = D("12345.1234567890123456")  # 21 digits, 16 fractional
        assert round_inverse_rate(value) == value


# --------------------------------------------------------------------------
# Independence from the ambient context, and the stdlib-only rule
# --------------------------------------------------------------------------


class TestAmbientContextIndependence:
    def test_hostile_ambient_context_changes_no_result(self):
        values = [D("2.345"), D("12345.675"), D("-2.345"), D("999999999999.999999")]
        before = [(plain(round_amount(v, 2)), plain(round_amount(v, 2, B))) for v in values]
        with localcontext(Context(prec=5, rounding=D_HALF_EVEN)):
            during = [(plain(round_amount(v, 2)), plain(round_amount(v, 2, B))) for v in values]
            up = plain(round_up_to_increment(D("4090.1554"), D("0.01")))
            ratio = plain(round_ratio(div(D(1), D(3))))
            inverse = plain(round_inverse_rate(div(D(1), D(85))))
        assert during == before
        assert up == "4090.16"
        assert ratio == "0.3333333333"
        assert inverse == "0.0117647058823529"

    def test_ambient_context_is_left_unchanged(self):
        ambient = Context(prec=7, rounding=D_HALF_EVEN)
        with localcontext(ambient) as ctx:
            round_amount(D("2.345"), 2)
            round_up_to_increment(D("1.234"), D("0.01"))
            assert ctx.prec == 7
            assert ctx.rounding == D_HALF_EVEN

    def test_mode_comes_from_the_argument_not_the_ambient_rounding(self):
        with localcontext(Context(prec=28, rounding=D_HALF_EVEN)):
            assert plain(round_amount(D("2.345"), 2, A)) == "2.35"
        with localcontext(Context(prec=28, rounding=D_HALF_UP)):
            assert plain(round_amount(D("2.345"), 2, B)) == "2.34"


class TestImportsAreStandardLibraryOnly:
    def test_rounding_module_imports_only_stdlib_and_its_package(self):
        import sys

        tree = ast.parse(Path(rounding.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue  # relative import inside finance.calc.money
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] not in sys.stdlib_module_names:
                    offenders.append(name)
        assert offenders == []

    def test_unused_helper_imports_stay_available(self):
        # add is part of the context API that rounding callers combine with.
        assert plain(add(D("1.10"), D("2.20"))) == "3.30"
