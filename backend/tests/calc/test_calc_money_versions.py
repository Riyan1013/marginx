"""M1-1 step 7: Python and Pydantic characterization (I-5, Closure Pack E2).

Pydantic is imported HERE ONLY. ``finance.calc.money`` stays standard-library
only (E1, enforced by test_calc_layering.py).

Two kinds of test, kept apart:

1. VERSION TRIPWIRES: Python must be exactly 3.13.2 and Pydantic exactly
   2.14.1. A failure here means "re-verify I-5", not "there is a bug".
2. BEHAVIOUR CHARACTERIZATION: records what the installed versions actually
   do. The results were observed first (probe run on 3.13.2 / 2.14.1) and are
   pinned here. They are facts, not wishes.

FINDINGS that shape later steps (recorded here so nobody has to rediscover them):

F1. A RAW Pydantic ``Decimal`` field in default (lax) mode ACCEPTS JSON
    numbers (5, 5.5), Python floats, and the strings "1e3", "+5" and " 5".
    It rejects only NaN / Infinity strings and booleans. So "JSON numbers are
    rejected for decimals" is true ONLY with the money grammar in front of the
    field (``BeforeValidator(parse_decimal)``). A raw Decimal field must never
    be used for a money, rate or FX field.
F2. Pydantic serializes a Decimal with ``str()`` semantics: ``Decimal("100.00")``
    -> "100.00" (fine), but ``Decimal("1E+3")`` -> "1E+3" and
    ``Decimal("0.0000001")`` -> "1E-7". Plain output needs an explicit
    serializer built on ``to_plain_string`` (shown below). parse_decimal can
    return such a value (a 7-digit rate such as "0.0000001").
F3. ``DecimalError`` is not a ``ValueError``, so Pydantic does NOT wrap it into
    a ``ValidationError``: it escapes raw. The Pydantic boundary must translate
    it, e.g. into ``PydanticCustomError(code, msg)`` (CA-4 premise, tested).
These are inputs to M1-3 / M2 (Q8). M1-1 changes nothing because of them.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from typing import Annotated

import pydantic
import pytest
from pydantic import (
    BaseModel,
    BeforeValidator,
    PlainSerializer,
    TypeAdapter,
    ValidationError,
)
from pydantic_core import PydanticCustomError

from finance.calc.money import errors as money_errors
from finance.calc.money.grammar import DecimalKind, parse_decimal, to_plain_string

# ---------------------------------------------------------------------------
# 1. Version tripwires
# ---------------------------------------------------------------------------

EXPECTED_PYTHON = (3, 13, 2)
EXPECTED_PYDANTIC = "2.14.1"


def test_python_version_is_the_verified_one() -> None:
    assert sys.version_info[:3] == EXPECTED_PYTHON, (
        f"Python is {sys.version_info[:3]}, I-5 was verified on {EXPECTED_PYTHON}: "
        "re-verify I-5 before trusting these tests"
    )


def test_pydantic_version_is_the_verified_one() -> None:
    assert pydantic.VERSION == EXPECTED_PYDANTIC, (
        f"Pydantic is {pydantic.VERSION}, I-5 was verified on {EXPECTED_PYDANTIC}: "
        "re-verify I-5 before trusting these tests"
    )


# ---------------------------------------------------------------------------
# Test-local models (not production types: Q8 keeps those out of M1-1)
# ---------------------------------------------------------------------------


class RawModel(BaseModel):
    """A raw Decimal field with no money grammar in front of it."""

    x: Decimal


def _money_before(v: object) -> Decimal:
    """Boundary adapter: grammar errors become coded Pydantic errors (F3, CA-4)."""
    try:
        return parse_decimal(v, DecimalKind.MONEY)
    except money_errors.DecimalError as exc:
        raise PydanticCustomError(exc.code, str(exc)) from None


def _rate_before(v: object) -> Decimal:
    try:
        return parse_decimal(v, DecimalKind.RULE_RATE)
    except money_errors.DecimalError as exc:
        raise PydanticCustomError(exc.code, str(exc)) from None


_PLAIN = PlainSerializer(to_plain_string, return_type=str, when_used="json")

MoneyStr = Annotated[Decimal, BeforeValidator(_money_before), _PLAIN]
RateStr = Annotated[Decimal, BeforeValidator(_rate_before), _PLAIN]


class GuardedModel(BaseModel):
    x: MoneyStr


class GuardedRateModel(BaseModel):
    x: RateStr


class GuardedNoSerializer(BaseModel):
    """Grammar in front, default serializer behind: used to pin F2."""

    x: Annotated[Decimal, BeforeValidator(_rate_before)]


class UnadaptedModel(BaseModel):
    """parse_decimal used directly: DecimalError is not wrapped (F3)."""

    x: Annotated[Decimal, BeforeValidator(lambda v: parse_decimal(v, DecimalKind.MONEY))]


def _json_payload(raw_value_json: str) -> str:
    return '{"x": ' + raw_value_json + "}"


# ---------------------------------------------------------------------------
# 2a. F1: a raw Decimal field in lax mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_json, expected",
    [
        ("5", Decimal("5")),
        ("5.5", Decimal("5.5")),
        ('"1e3"', Decimal("1E+3")),
        ('"+5"', Decimal("5")),
        ('" 5"', Decimal("5")),
    ],
)
def test_f1_raw_decimal_field_accepts_what_the_money_grammar_forbids(
    raw_json: str, expected: Decimal
) -> None:
    """F1: lax mode accepts JSON numbers, exponents, signs and spaces."""
    model = RawModel.model_validate_json(_json_payload(raw_json))
    assert model.x == expected
    # Each of these is INVALID under the money grammar (or not a string):
    candidate: object = json.loads(raw_json)
    with pytest.raises(money_errors.InvalidDecimalError):
        parse_decimal(candidate, DecimalKind.MONEY)


def test_f1_a_plain_decimal_string_is_accepted_by_both_raw_and_guarded_fields() -> None:
    """The one input both agree on: a valid decimal string (not an F1 difference)."""
    payload = _json_payload('"5.5"')
    assert RawModel.model_validate_json(payload).x == Decimal("5.5")
    assert GuardedModel.model_validate_json(payload).x == Decimal("5.5")


@pytest.mark.parametrize(
    "raw_json, error_type",
    [
        ('"NaN"', "finite_number"),
        ('"Infinity"', "finite_number"),
        ('"-Infinity"', "finite_number"),
        ("true", "decimal_type"),
    ],
)
def test_f1_raw_decimal_field_rejects_nan_infinity_and_booleans(
    raw_json: str, error_type: str
) -> None:
    with pytest.raises(ValidationError) as info:
        RawModel.model_validate_json(_json_payload(raw_json))
    assert [e["type"] for e in info.value.errors()] == [error_type]


def test_f1_raw_decimal_field_accepts_a_python_float_but_not_a_bool() -> None:
    assert RawModel.model_validate({"x": 5.5}).x == Decimal("5.5")
    with pytest.raises(ValidationError):
        RawModel.model_validate({"x": True})


# ---------------------------------------------------------------------------
# 2b. The grammar in front of the field rejects every MG-X1 bad input
# ---------------------------------------------------------------------------

MG_X1_BAD_JSON = [
    # (json value, expected registry code)
    ('"1e3"', "INVALID_DECIMAL"),
    ('"+5"', "INVALID_DECIMAL"),
    ('"-5"', "INVALID_DECIMAL"),
    ('" 5"', "INVALID_DECIMAL"),
    ('"5 "', "INVALID_DECIMAL"),
    ('".5"', "INVALID_DECIMAL"),
    ('"5."', "INVALID_DECIMAL"),
    ('"NaN"', "INVALID_DECIMAL"),
    ('"Infinity"', "INVALID_DECIMAL"),
    ('"-Infinity"', "INVALID_DECIMAL"),
    ('""', "INVALID_DECIMAL"),
    ("5", "INVALID_DECIMAL"),  # a JSON number (int)
    ("5.5", "INVALID_DECIMAL"),  # a JSON number (float)
    ("true", "INVALID_DECIMAL"),
    ("null", "INVALID_DECIMAL"),
    ('"1.0000001"', "SCALE_EXCEEDED"),
    ('"1000000000000.01"', "AMOUNT_OUT_OF_RANGE"),
]


@pytest.mark.parametrize("raw_json, code", MG_X1_BAD_JSON)
def test_grammar_in_front_rejects_every_bad_input_with_its_registry_code(
    raw_json: str, code: str
) -> None:
    with pytest.raises(ValidationError) as info:
        GuardedModel.model_validate_json(_json_payload(raw_json))
    errors = info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == code
    assert errors[0]["loc"] == ("x",)


@pytest.mark.parametrize(
    "raw_json, expected",
    [
        ('"0"', Decimal("0")),
        ('"007"', Decimal("007")),
        ('"100.00"', Decimal("100.00")),
        ('"1000000000000"', Decimal("1000000000000")),
        ('"0.000001"', Decimal("0.000001")),
    ],
)
def test_grammar_in_front_accepts_valid_strings_and_keeps_scale(
    raw_json: str, expected: Decimal
) -> None:
    model = GuardedModel.model_validate_json(_json_payload(raw_json))
    assert model.x == expected
    assert model.x.as_tuple() == expected.as_tuple()


def test_grammar_in_front_also_rejects_python_values_that_lax_mode_would_take() -> None:
    for bad in (5, 5.5, True, Decimal("5"), None):
        with pytest.raises(ValidationError):
            GuardedModel.model_validate({"x": bad})


# ---------------------------------------------------------------------------
# 2c. F2: serialization to plain strings
# ---------------------------------------------------------------------------


def test_default_serializer_emits_a_plain_string_with_scale_for_ordinary_values() -> None:
    model = RawModel(x=Decimal("100.00"))
    assert model.model_dump_json() == '{"x":"100.00"}'
    assert model.model_dump(mode="json") == {"x": "100.00"}
    assert isinstance(json.loads(model.model_dump_json())["x"], str)


@pytest.mark.parametrize(
    "value, default_text, plain_text",
    [
        (Decimal("1E+3"), "1E+3", "1000"),
        (Decimal("0.0000001"), "1E-7", "0.0000001"),
        (Decimal("1E-10"), "1E-10", "0.0000000001"),
    ],
)
def test_f2_default_serializer_can_emit_an_exponent_the_plain_serializer_never_does(
    value: Decimal, default_text: str, plain_text: str
) -> None:
    raw = RawModel(x=value)
    assert raw.model_dump_json() == json.dumps({"x": default_text}, separators=(",", ":"))
    guarded = GuardedModel.model_construct(x=value)
    assert guarded.model_dump_json() == json.dumps({"x": plain_text}, separators=(",", ":"))
    assert guarded.model_dump(mode="json") == {"x": plain_text}


def test_f2_a_valid_seven_digit_rate_is_serialized_as_an_exponent_without_the_plain_serializer() -> None:
    parsed = GuardedNoSerializer.model_validate_json(_json_payload('"0.0000001"'))
    assert parsed.x == Decimal("0.0000001")
    assert parsed.model_dump_json() == '{"x":"1E-7"}'  # the trap
    fixed = GuardedRateModel.model_validate_json(_json_payload('"0.0000001"'))
    assert fixed.model_dump_json() == '{"x":"0.0000001"}'


def test_plain_serializer_keeps_trailing_zeros_and_json_type_is_string() -> None:
    model = GuardedModel.model_validate_json(_json_payload('"100.00"'))
    text = model.model_dump_json()
    assert text == '{"x":"100.00"}'
    assert json.loads(text) == {"x": "100.00"}


def test_plain_serializer_never_emits_a_signed_zero() -> None:
    for value, expected in [
        (Decimal("-0.00"), "0.00"),
        (Decimal("-0"), "0"),
        (Decimal("-0E-10"), "0.0000000000"),
    ]:
        model = GuardedModel.model_construct(x=value)
        assert model.model_dump_json() == json.dumps({"x": expected}, separators=(",", ":"))
        assert model.model_dump(mode="json") == {"x": expected}


def test_plain_serializer_leaves_python_mode_as_a_decimal() -> None:
    model = GuardedModel.model_validate_json(_json_payload('"100.00"'))
    dumped = model.model_dump()
    assert dumped == {"x": Decimal("100.00")}
    assert isinstance(dumped["x"], Decimal)


def test_json_round_trip_preserves_value_and_scale() -> None:
    for text in ("0", "100.00", "0.000001", "1000000000000", "12.340"):
        model = GuardedModel.model_validate_json(_json_payload(json.dumps(text)))
        again = GuardedModel.model_validate_json(model.model_dump_json())
        assert again.x == model.x
        assert again.x.as_tuple() == model.x.as_tuple()
        assert json.loads(model.model_dump_json())["x"] == text


def test_type_adapter_works_the_same_way() -> None:
    adapter = TypeAdapter(MoneyStr)
    assert adapter.validate_python("100.00") == Decimal("100.00")
    assert adapter.dump_json(Decimal("1E+3")) == b'"1000"'
    with pytest.raises(ValidationError):
        adapter.validate_python(5)


# ---------------------------------------------------------------------------
# 2d. CA-4 premise and F3
# ---------------------------------------------------------------------------


def test_custom_error_code_surfaces_as_the_validation_error_type() -> None:
    """CA-4: a PydanticCustomError(code, ...) becomes errors()[0]['type']."""
    with pytest.raises(ValidationError) as info:
        GuardedModel.model_validate({"x": "NaN"})
    error = info.value.errors()[0]
    assert error["type"] == "INVALID_DECIMAL"
    assert error["loc"] == ("x",)
    assert "NaN" in error["msg"]
    # the code is also what the JSON error list carries
    assert json.loads(info.value.json())[0]["type"] == "INVALID_DECIMAL"


def test_codes_for_all_three_grammar_errors_surface_unchanged() -> None:
    seen = {}
    for raw_json, _ in MG_X1_BAD_JSON:
        with pytest.raises(ValidationError) as info:
            GuardedModel.model_validate_json(_json_payload(raw_json))
        seen[info.value.errors()[0]["type"]] = True
    assert set(seen) == {"INVALID_DECIMAL", "SCALE_EXCEEDED", "AMOUNT_OUT_OF_RANGE"}


def test_f3_money_decimal_error_is_not_wrapped_by_pydantic() -> None:
    """F3: a DecimalError escapes raw, so the boundary must translate it."""
    assert not issubclass(money_errors.DecimalError, ValueError)
    with pytest.raises(money_errors.InvalidDecimalError):
        UnadaptedModel.model_validate({"x": "NaN"})


def test_a_validation_error_from_the_guard_contains_no_input_dump_of_a_float() -> None:
    """The error list stays small and serializable (feeds the M1-2 envelope)."""
    with pytest.raises(ValidationError) as info:
        GuardedModel.model_validate_json(_json_payload("5.5"))
    payload = json.loads(info.value.json())
    assert [e["type"] for e in payload] == ["INVALID_DECIMAL"]
