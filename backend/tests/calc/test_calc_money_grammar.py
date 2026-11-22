"""Step 4 tests: decimal-string grammar, limits, kinds, order, plain output.

Covers gate probe MG-X1, decisions Q2 (FX rate), Q3 (grammar), Q4 (order),
Q6 (negative zero, plain-string layer) and U3/U4/U9. Run from ``backend/``
with ``python -m pytest``.

Every numeric input is a string or a ``Decimal``; floats appear only where a
float must be rejected, and are labelled.
"""

from __future__ import annotations

import ast
import sys
from decimal import ROUND_HALF_UP as D_HALF_UP
from decimal import Context, Decimal, localcontext
from pathlib import Path

import pytest

from finance.calc.money import grammar
from finance.calc.money.context import mul
from finance.calc.money.errors import (
    AmountOutOfRangeError,
    DecimalError,
    InvalidDecimalError,
    MoneyError,
    ScaleExceededError,
)
from finance.calc.money.grammar import (
    FX_RATE_MAX_FRACTION_DIGITS,
    FX_RATE_MAX_TOTAL_DIGITS,
    MONEY_MAX_FRACTION_DIGITS,
    MONEY_MAX_VALUE,
    RULE_RATE_MAX_FRACTION_DIGITS,
    RULE_RATE_MAX_VALUE,
    DecimalKind,
    parse_decimal,
    to_plain_string,
)
from finance.calc.money.rounding import RoundingMode, round_amount

D = Decimal
MONEY = DecimalKind.MONEY
RULE = DecimalKind.RULE_RATE
FX = DecimalKind.FX_RATE
ALL_KINDS = [MONEY, RULE, FX]

INVALID = "INVALID_DECIMAL"
SCALE = "SCALE_EXCEEDED"
RANGE = "AMOUNT_OUT_OF_RANGE"


def fails_with(value, kind, error_type, code):
    with pytest.raises(DecimalError) as info:
        parse_decimal(value, kind)
    assert type(info.value) is error_type
    assert info.value.code == code
    return info.value


# --- MG-X1 gate probe --------------------------------------------------------


class TestMGX1:
    def test_accepted_at_the_money_cap(self):
        assert parse_decimal("1000000000000", MONEY) == D("1000000000000")

    def test_amount_out_of_range(self):
        fails_with("1000000000000.01", MONEY, AmountOutOfRangeError, RANGE)

    def test_scale_exceeded_with_seven_fractional_digits(self):
        fails_with("1.1234567", MONEY, ScaleExceededError, SCALE)

    @pytest.mark.parametrize(
        "bad",
        ["1e3", "+5", "-5", " 1", "NaN", "Infinity"],
    )
    def test_invalid_decimal_strings(self, bad):
        fails_with(bad, MONEY, InvalidDecimalError, INVALID)

    def test_json_number_is_rejected(self):
        # A float is what a JSON number becomes; it must be rejected on purpose.
        fails_with(1000.5, MONEY, InvalidDecimalError, INVALID)

    def test_json_true_is_rejected(self):
        fails_with(True, MONEY, InvalidDecimalError, INVALID)


# --- Q3: grammar -------------------------------------------------------------

BAD_GRAMMAR = [
    "",
    ".5",
    "5.",
    ".",
    "..",
    "1.2.3",
    "+5",
    "-5",
    "-0",
    "+0",
    "-0.00",
    "1e3",
    "1E3",
    "1e+3",
    "1e-3",
    "0x10",
    "1,000",
    "1_000",
    " 1",
    "1 ",
    "1 1",
    "\t1",
    "\n1",
    "1\n",
    "1.5\n",
    "\u00a01",  # no-break space
    "\u0661\u0662\u0663",  # Arabic-Indic digits
    "\uff11\uff12",  # fullwidth digits
    "1\u0660",  # ASCII digit followed by an Arabic-Indic zero
    "1.\u0665",
    "NaN",
    "nan",
    "sNaN",
    "Infinity",
    "-Infinity",
    "inf",
    "INF",
]


class TestGrammar:
    @pytest.mark.parametrize("kind", ALL_KINDS)
    @pytest.mark.parametrize("bad", BAD_GRAMMAR)
    def test_bad_grammar_is_invalid_decimal(self, bad, kind):
        fails_with(bad, kind, InvalidDecimalError, INVALID)

    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_leading_zeros_are_accepted(self, kind):
        assert parse_decimal("007", kind) == D("7")
        assert parse_decimal("007.5", kind) == D("7.5")
        assert parse_decimal("00.5", kind) == D("0.5")

    @pytest.mark.parametrize("kind", ALL_KINDS)
    @pytest.mark.parametrize("zero", ["0", "00", "0.0", "0.00", "0.000000"])
    def test_zero_is_valid_grammar(self, zero, kind):
        result = parse_decimal(zero, kind)
        assert result == 0
        assert not result.is_signed()

    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_scale_is_preserved(self, kind):
        result = parse_decimal("1.50", kind)
        assert result == D("1.50")
        assert result.as_tuple().exponent == -2
        assert to_plain_string(result) == "1.50"

    def test_money_keeps_trailing_zeros(self):
        result = parse_decimal("100.00", MONEY)
        assert result.as_tuple() == D("100.00").as_tuple()
        assert to_plain_string(result) == "100.00"

    def test_leading_zero_value_loses_only_the_zeros(self):
        assert to_plain_string(parse_decimal("007", MONEY)) == "7"
        assert to_plain_string(parse_decimal("007.50", MONEY)) == "7.50"

    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_result_is_a_decimal(self, kind):
        assert type(parse_decimal("1", kind)) is Decimal

    def test_a_fraction_may_be_all_zeros(self):
        assert parse_decimal("5.000000", MONEY) == D("5")


class TestNonStrings:
    class StrSubclass(str):
        pass

    @pytest.mark.parametrize("kind", ALL_KINDS)
    @pytest.mark.parametrize(
        "bad",
        [
            True,
            False,
            0,
            1,
            1.5,  # float on purpose: must be rejected
            float("nan"),
            float("inf"),
            D("1"),
            D("NaN"),
            None,
            b"1",
            bytearray(b"1"),
            [],
            ["1"],
            {},
            object(),
            StrSubclass("1"),
        ],
        ids=lambda v: type(v).__name__ + ":" + repr(v)[:20],
    )
    def test_not_a_str_is_invalid_decimal(self, bad, kind):
        fails_with(bad, kind, InvalidDecimalError, INVALID)

    def test_kind_must_be_a_decimal_kind(self):
        for bad in ("money", None, 1, "MONEY"):
            with pytest.raises(TypeError):
                parse_decimal("1", bad)


# --- Q4: validation order ----------------------------------------------------


class TestValidationOrder:
    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_grammar_comes_before_range(self, kind):
        # 1e30 would be out of range; it is invalid grammar first.
        fails_with("1e30", kind, InvalidDecimalError, INVALID)

    def test_grammar_comes_before_scale(self):
        fails_with("-1.12345678", MONEY, InvalidDecimalError, INVALID)
        fails_with("1.12345678e5", MONEY, InvalidDecimalError, INVALID)

    def test_scale_comes_before_range_money(self):
        fails_with("1000000000001.1234567", MONEY, ScaleExceededError, SCALE)

    def test_scale_comes_before_range_rule_rate(self):
        fails_with("11.12345678901234567", RULE, ScaleExceededError, SCALE)

    def test_scale_comes_before_range_fx(self):
        fails_with("12345678.12345678901234567", FX, ScaleExceededError, SCALE)

    def test_range_is_reported_when_scale_is_fine(self):
        fails_with("1000000000001.123456", MONEY, AmountOutOfRangeError, RANGE)

    def test_all_three_errors_are_distinct_registry_codes(self):
        codes = {INVALID, SCALE, RANGE}
        assert codes == {
            InvalidDecimalError.code,
            ScaleExceededError.code,
            AmountOutOfRangeError.code,
        }
        assert len(codes) == 3


# --- Limits per kind ---------------------------------------------------------


class TestMoneyLimits:
    def test_constants(self):
        assert MONEY_MAX_FRACTION_DIGITS == 6
        assert MONEY_MAX_VALUE == D("1000000000000")

    @pytest.mark.parametrize(
        "ok",
        [
            "0",
            "0.000001",
            "1.123456",
            "999999999999.999999",
            "1000000000000",
            "1000000000000.0",
            "1000000000000.000000",
        ],
    )
    def test_accepted(self, ok):
        assert parse_decimal(ok, MONEY) == D(ok)

    @pytest.mark.parametrize(
        "over",
        [
            "1000000000000.000001",
            "1000000000000.01",
            "1000000000001",
            "9999999999999",
            "10000000000000",
        ],
    )
    def test_out_of_range(self, over):
        fails_with(over, MONEY, AmountOutOfRangeError, RANGE)

    @pytest.mark.parametrize("over", ["0.0000001", "1.1234567", "1.0000000"])
    def test_scale_exceeded(self, over):
        fails_with(over, MONEY, ScaleExceededError, SCALE)

    def test_huge_input_is_out_of_range_without_arithmetic(self):
        fails_with("9" * 5000, MONEY, AmountOutOfRangeError, RANGE)
        fails_with("1" + "0" * 5000 + ".5", MONEY, AmountOutOfRangeError, RANGE)

    def test_leading_zeros_do_not_count_toward_range(self):
        assert parse_decimal("0" * 30 + "5", MONEY) == D("5")


class TestRuleRateLimits:
    def test_constants(self):
        assert RULE_RATE_MAX_FRACTION_DIGITS == 16
        assert RULE_RATE_MAX_VALUE == D("10")

    @pytest.mark.parametrize(
        "ok",
        [
            "0",
            "0.1234567890123456",
            "9.9999999999999999",
            "10",
            "10.0",
            "10.0000000000000000",
        ],
    )
    def test_accepted(self, ok):
        assert parse_decimal(ok, RULE) == D(ok)

    @pytest.mark.parametrize(
        "over",
        ["10.0000000000000001", "10.1", "11", "85", "100", "1000000000000"],
    )
    def test_out_of_range(self, over):
        fails_with(over, RULE, AmountOutOfRangeError, RANGE)

    def test_seventeenth_fractional_digit_is_scale_exceeded(self):
        fails_with("10.00000000000000001", RULE, ScaleExceededError, SCALE)
        fails_with("0.12345678901234567", RULE, ScaleExceededError, SCALE)

    def test_cap_is_inclusive_only_at_exactly_ten(self):
        assert parse_decimal("10.0000000000000000", RULE) == 10
        fails_with("10.0000000000000001", RULE, AmountOutOfRangeError, RANGE)


class TestFxRateLimits:
    def test_constants(self):
        assert FX_RATE_MAX_FRACTION_DIGITS == 16
        assert FX_RATE_MAX_TOTAL_DIGITS == 21

    @pytest.mark.parametrize(
        "ok",
        [
            "85",
            "85.5",
            "85.1234567890123456",
            "0.0000000000000001",
            "1",
            "10.0000000000000001",  # above the rule-rate cap, fine for FX
            "12345.1234567890123456",  # 5 + 16 = 21 digits: the boundary
            "123456789012345678901",  # 21 integer digits: the boundary
            "123456789012345.123456",  # 15 + 6 = 21
        ],
    )
    def test_accepted(self, ok):
        assert parse_decimal(ok, FX) == D(ok)

    @pytest.mark.parametrize(
        "over",
        [
            "123456.1234567890123456",  # 6 + 16 = 22 digits
            "1234567890123456789012",  # 22 integer digits
            "123456789012345.1234567",  # 15 + 7 = 22
            "9" * 22,
        ],
    )
    def test_over_21_digits_is_out_of_range(self, over):
        fails_with(over, FX, AmountOutOfRangeError, RANGE)

    def test_seventeenth_fractional_digit_is_scale_exceeded(self):
        fails_with("1.12345678901234567", FX, ScaleExceededError, SCALE)
        fails_with("0.00000000000000001", FX, ScaleExceededError, SCALE)

    def test_leading_zeros_are_not_counted(self):
        # U4: 007.5 is 1 integer digit + 1 fractional digit = 2 digits.
        assert parse_decimal("007.5", FX) == D("7.5")
        assert parse_decimal("0" * 24 + ".5", FX) == D("0.5")
        # 24 leading zeros do not push a 21-digit value over the limit.
        assert parse_decimal("0" * 24 + "12345.1234567890123456", FX) == D(
            "12345.1234567890123456"
        )

    def test_zero_integer_part_counts_as_zero_digits(self):
        # 0 integer digits + 16 fractional digits = 16.
        assert parse_decimal("0.1234567890123456", FX) == D("0.1234567890123456")
        assert parse_decimal("0.0000000000000000", FX) == 0

    def test_fractional_zeros_are_counted(self):
        # 5 integer digits + 16 fractional zeros = 21 (ok); 6 + 16 = 22 (over).
        assert parse_decimal("12345.0000000000000000", FX) == D("12345")
        fails_with("123456.0000000000000000", FX, AmountOutOfRangeError, RANGE)

    def test_fx_has_no_cap_of_ten(self):
        assert parse_decimal("1000000", FX) == D("1000000")

    def test_huge_input_is_out_of_range_without_arithmetic(self):
        fails_with("9" * 5000, FX, AmountOutOfRangeError, RANGE)


class TestKindsAreSeparate:
    """U9: a rate must never be checked against the wrong kind's cap."""

    def test_85_is_rejected_as_rule_rate_and_accepted_as_fx_rate(self):
        fails_with("85", RULE, AmountOutOfRangeError, RANGE)
        assert parse_decimal("85", FX) == D("85")

    def test_usd_inr_like_rate_is_valid_only_as_fx_rate(self):
        rate = "85.1234567890123456"
        assert parse_decimal(rate, FX) == D(rate)
        fails_with(rate, RULE, AmountOutOfRangeError, RANGE)

    def test_the_three_kinds_exist_and_are_distinct(self):
        assert {k.name for k in DecimalKind} == {"MONEY", "RULE_RATE", "FX_RATE"}
        assert len({MONEY, RULE, FX}) == 3

    def test_money_and_rate_scale_limits_differ(self):
        assert parse_decimal("1.1234567890", RULE) == D("1.1234567890")
        fails_with("1.1234567890", MONEY, ScaleExceededError, SCALE)

    def test_rule_rate_cap_was_not_widened(self):
        assert grammar.RULE_RATE_MAX_VALUE == D("10")
        fails_with("10.1", RULE, AmountOutOfRangeError, RANGE)

    def test_kind_docstring_records_the_m2_requirement(self):
        doc = DecimalKind.__doc__ or ""
        assert "fx_pair" in doc
        assert "FX_RATE" in doc and "RULE_RATE" in doc
        assert "must" in doc and "M2" in doc


class TestErrors:
    def test_errors_are_money_errors(self):
        err = fails_with("x", MONEY, InvalidDecimalError, INVALID)
        assert isinstance(err, DecimalError)
        assert isinstance(err, MoneyError)

    def test_message_does_not_echo_a_huge_input(self):
        err = fails_with("x" * 10_000, MONEY, InvalidDecimalError, INVALID)
        assert len(str(err)) < 200

    def test_message_is_never_empty(self):
        for value, kind in [("x", MONEY), ("1.1234567", MONEY), ("11", RULE)]:
            with pytest.raises(DecimalError) as info:
                parse_decimal(value, kind)
            assert str(info.value)


# --- Plain-string output and Q6 ---------------------------------------------


class TestToPlainString:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (D("1E+3"), "1000"),
            (D("1.5E+2"), "150"),
            (D("1E-10"), "0.0000000001"),
            (D("100.00"), "100.00"),
            (D("100"), "100"),
            (D("0.00"), "0.00"),
            (D("0"), "0"),
            (D("-0.01"), "-0.01"),
            (D("-1E+3"), "-1000"),
            (D("123456789012345678901234567890.123456789"),
             "123456789012345678901234567890.123456789"),
        ],
    )
    def test_plain_rendering(self, value, expected):
        assert to_plain_string(value) == expected

    @pytest.mark.parametrize(
        "value",
        [D("1E+30"), D("1E-30"), D("-1E+30"), D("12345E+10"), D("0.000001E-5")],
    )
    def test_never_uses_an_exponent(self, value):
        text = to_plain_string(value)
        assert "E" not in text and "e" not in text
        assert D(text) == value

    def test_never_quantizes(self):
        value = D("1.123456789012345678901234567890123456789")
        assert to_plain_string(value) == "1.123456789012345678901234567890123456789"

    @pytest.mark.parametrize("bad", [1.5, 1, "1", None, True, b"1"])
    def test_rejects_non_decimals(self, bad):
        # 1.5 is a float on purpose.
        with pytest.raises(TypeError):
            to_plain_string(bad)

    @pytest.mark.parametrize("bad", [D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity")])
    def test_rejects_non_finite(self, bad):
        with pytest.raises(ValueError):
            to_plain_string(bad)

    def test_round_trips_every_parsed_value(self):
        for text in ["0", "0.00", "7", "100.00", "999999999999.999999", "1.500000"]:
            parsed = parse_decimal(text, MONEY)
            assert to_plain_string(parsed) == text


class TestNegativeZeroPlainStringLayer:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (D("-0"), "0"),
            (D("-0.00"), "0.00"),
            (D("-0.000"), "0.000"),
            (D("-0E-10"), "0.0000000000"),
            (D("0.00"), "0.00"),
            (D("0"), "0"),
        ],
    )
    def test_zero_never_has_a_minus_sign(self, value, expected):
        assert to_plain_string(value) == expected

    def test_input_value_is_not_mutated(self):
        value = D("-0.00")
        to_plain_string(value)
        assert value.is_signed()

    def test_arithmetic_source_of_negative_zero(self):
        product = mul(D("-1"), D("0.00"))
        assert product.is_signed() and product == 0  # a signed zero internally
        assert to_plain_string(product) == "0.00"

    def test_non_zero_negatives_keep_the_sign(self):
        assert to_plain_string(D("-0.01")) == "-0.01"
        assert to_plain_string(D("-0.000001")) == "-0.000001"
        assert to_plain_string(D("-100.50")) == "-100.50"

    @pytest.mark.parametrize(
        "tiny",
        [D("-0.0001"), D("-0.001"), D("-0.004"), D("-0.0049"), D("-0.0000001")],
    )
    def test_tiny_negatives_rounded_to_zero_never_render_minus(self, tiny):
        text = to_plain_string(round_amount(tiny, 2))
        assert text == "0.00"
        assert text != "-0.00" and not text.startswith("-")

    def test_half_even_tie_to_zero_renders_without_sign(self):
        text = to_plain_string(round_amount(D("-0.005"), 2, RoundingMode.HALF_EVEN))
        assert text == "0.00"

    def test_negative_just_above_a_cent_keeps_its_sign(self):
        assert to_plain_string(round_amount(D("-0.005"), 2)) == "-0.01"  # HALF_UP
        assert to_plain_string(round_amount(D("-0.0051"), 2)) == "-0.01"

    @pytest.mark.parametrize("kind", ALL_KINDS)
    @pytest.mark.parametrize("signed_zero", ["-0", "-0.0", "-0.00", "+0", "+0.00"])
    def test_input_grammar_never_yields_a_signed_zero(self, signed_zero, kind):
        fails_with(signed_zero, kind, InvalidDecimalError, INVALID)


# --- Context independence and imports ---------------------------------------


class TestAmbientContext:
    def test_hostile_ambient_context_changes_nothing(self):
        text = "12345.1234567890123456"
        with localcontext(Context(prec=5, rounding=D_HALF_UP)):
            assert parse_decimal(text, FX) == D(text)
            assert to_plain_string(parse_decimal(text, FX)) == text
            assert to_plain_string(D("-0.00")) == "0.00"
            fails_with("1000000000000.000001", MONEY, AmountOutOfRangeError, RANGE)
            assert parse_decimal("1000000000000", MONEY) == D("1000000000000")

    def test_parsed_value_is_exact_beyond_ambient_precision(self):
        digits = "9" * 12 + "." + "9" * 6
        with localcontext(Context(prec=5)):
            assert to_plain_string(parse_decimal(digits, MONEY)) == digits


class TestImportsAreStandardLibraryOnly:
    def test_grammar_module_imports_only_stdlib_and_its_package(self):
        tree = ast.parse(Path(grammar.__file__).read_text(encoding="utf-8"))
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

    def test_relative_imports_stay_inside_the_money_package(self):
        tree = ast.parse(Path(grammar.__file__).read_text(encoding="utf-8"))
        relative = [
            (node.level, node.module)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level > 0
        ]
        assert relative == [(1, "errors")]
