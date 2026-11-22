"""Decimal-string grammar, limits and plain-string output (standard library only).

Decisions: CA-1 (plain strings), CA-6 (grammar and limits), Q2 to Q4 and Q6.

Grammar (``parse_decimal``)
---------------------------
A decimal is a JSON **string** that matches ``[0-9]+(\\.[0-9]+)?`` in ASCII.

* Accepted: ``0``, ``0.00``, ``007`` (leading zeros), ``100.00``.
* Rejected as ``INVALID_DECIMAL``: ``.5``, ``5.``, a sign (also ``-0``),
  exponent notation, whitespace (also a trailing newline), non-ASCII digits,
  ``NaN``, ``Infinity``, and every value that is not exactly a ``str``
  (``bool``, ``int``, ``float``, ``Decimal``, ``None``, ``bytes``).

Validation order (Q4): invalid grammar, then ``SCALE_EXCEEDED``, then
``AMOUNT_OUT_OF_RANGE``. A value that breaks several rules reports the first.

The parsed ``Decimal`` keeps the scale it was written with (``"100.00"`` stays
``Decimal("100.00")``). Zero is valid grammar for every kind; a "greater than
zero" rule belongs to the request layer, not here.

Limits per kind
---------------
==========  ===================  ==============================================
Kind        Fractional digits    Value limit
==========  ===================  ==============================================
MONEY       at most 6            value at most 1,000,000,000,000        (CA-6)
RULE_RATE   at most 16           value at most 10                       (CA-6)
FX_RATE     at most 16           at most 21 total digits                (Q2, U4)
==========  ===================  ==============================================

FX digit count (U4): leading zeros of the integer part are not counted, so the
count is ``len(integer digits without leading zeros) + len(fractional digits)``
and a zero integer part counts as 0 digits. ``007.5`` counts as 2 digits.
Every limit failure (a value above 10, more than 21 FX digits, a money amount
above the cap) is ``AMOUNT_OUT_OF_RANGE`` (U3).

The checks are done on the string first, so a huge input never reaches
``Decimal`` arithmetic. Comparisons use exact ``Decimal`` values and need no
calculation context.

Plain-string output (``to_plain_string``)
-----------------------------------------
No exponent, never quantized, scale preserved (CA-1). A zero of any scale
renders without a minus sign (Q6): ``Decimal("-0.00")`` gives ``"0.00"`` and
``Decimal("-0")`` gives ``"0"``. A non-zero negative keeps its sign.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .errors import (
    AmountOutOfRangeError,
    InvalidDecimalError,
    ScaleExceededError,
)

# --- Limits (CA-6, Q2) ------------------------------------------------------

#: MONEY: at most this many fractional digits.
MONEY_MAX_FRACTION_DIGITS = 6
#: MONEY: the value must not exceed this amount (inclusive).
MONEY_MAX_VALUE = Decimal(10**12)  # int argument: exact, no context involved

#: RULE_RATE: at most this many fractional digits.
RULE_RATE_MAX_FRACTION_DIGITS = 16
#: RULE_RATE: the value must not exceed this (inclusive). CA-6.
RULE_RATE_MAX_VALUE = Decimal(10)

#: FX_RATE: at most this many fractional digits (Q2).
FX_RATE_MAX_FRACTION_DIGITS = 16
#: FX_RATE: at most this many total digits, leading zeros not counted (Q2, U4).
FX_RATE_MAX_TOTAL_DIGITS = 21


class DecimalKind(Enum):
    """What a decimal string is used for. Each kind has its own limits.

    **Requirement for M2 (decision U9, not implemented in M1-1):**

    * An FX override value (the ``rate`` parameter of an ``fx_pair`` override)
      **must** be validated with ``FX_RATE``.
    * Ordinary rule rates and ordinary override rates **must** use
      ``RULE_RATE``, subject to CA-6 (value at most 10).
    * M2 must **not** validate an FX override with ``RULE_RATE``: that would
      reject a valid USD/INR rate near 85. M2 must **not** widen ``RULE_RATE``
      to fix it either; the two kinds stay separate.

    The test that ``"85"`` fails as ``RULE_RATE`` and passes as ``FX_RATE``
    pins this behaviour.
    """

    MONEY = "money"
    RULE_RATE = "rule_rate"
    FX_RATE = "fx_rate"


@dataclass(frozen=True)
class _Limits:
    max_fraction_digits: int
    max_value: Decimal | None = None
    max_total_digits: int | None = None


_LIMITS: dict[DecimalKind, _Limits] = {
    DecimalKind.MONEY: _Limits(
        max_fraction_digits=MONEY_MAX_FRACTION_DIGITS,
        max_value=MONEY_MAX_VALUE,
    ),
    DecimalKind.RULE_RATE: _Limits(
        max_fraction_digits=RULE_RATE_MAX_FRACTION_DIGITS,
        max_value=RULE_RATE_MAX_VALUE,
    ),
    DecimalKind.FX_RATE: _Limits(
        max_fraction_digits=FX_RATE_MAX_FRACTION_DIGITS,
        max_total_digits=FX_RATE_MAX_TOTAL_DIGITS,
    ),
}

# ASCII digits only; fullmatch (not match/$) so a trailing newline fails.
_GRAMMAR = re.compile(r"[0-9]+(?:\.[0-9]+)?")

# Every valid value of every kind has far fewer integer digits than this, so a
# longer integer part is out of range without building a Decimal.
_MAX_INTEGER_DIGITS = 22


def _shown(value: str) -> str:
    """A short, safe rendering of an input for an error message."""
    return repr(value if len(value) <= 40 else value[:37] + "...")


def parse_decimal(value: object, kind: DecimalKind) -> Decimal:
    """Parse ``value`` as a decimal string of ``kind``.

    Raises ``InvalidDecimalError``, ``ScaleExceededError`` or
    ``AmountOutOfRangeError``, in that order of precedence (Q4). Returns an
    exact ``Decimal`` that keeps the written scale.
    """
    if not isinstance(kind, DecimalKind):
        raise TypeError(f"kind must be a DecimalKind, not {type(kind).__name__}")
    limits = _LIMITS[kind]

    # 1. Grammar: exactly a str, ASCII digits, optional fraction.
    if type(value) is not str:
        raise InvalidDecimalError(
            f"a decimal must be a JSON string, not {type(value).__name__}"
        )
    if _GRAMMAR.fullmatch(value) is None:
        raise InvalidDecimalError(f"not a valid decimal string: {_shown(value)}")

    integer, _, fraction = value.partition(".")

    # 2. Scale.
    if len(fraction) > limits.max_fraction_digits:
        raise ScaleExceededError(
            f"{kind.value} allows at most {limits.max_fraction_digits} "
            f"fractional digits, got {len(fraction)}"
        )

    # 3. Range.
    significant_integer = integer.lstrip("0")
    if len(significant_integer) > _MAX_INTEGER_DIGITS:
        raise AmountOutOfRangeError(f"{kind.value} is out of range")
    if limits.max_total_digits is not None:
        digits = len(significant_integer) + len(fraction)
        if digits > limits.max_total_digits:
            raise AmountOutOfRangeError(
                f"{kind.value} allows at most {limits.max_total_digits} "
                f"digits, got {digits}"
            )
    result = Decimal(value)  # exact: the constructor never rounds
    if limits.max_value is not None and result > limits.max_value:
        raise AmountOutOfRangeError(
            f"{kind.value} must not exceed {to_plain_string(limits.max_value)}"
        )
    return result


def to_plain_string(value: Decimal) -> str:
    """Render ``value`` as a plain decimal string (no exponent, scale kept).

    A zero of any scale loses its sign (Q6). Raises ``TypeError`` for anything
    that is not a ``Decimal`` and ``ValueError`` for NaN or Infinity (an
    internal fault: parsed input can never produce them).
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"value must be a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError("cannot render a non-finite Decimal")
    if value.is_zero():
        value = value.copy_abs()
    return format(value, "f")
