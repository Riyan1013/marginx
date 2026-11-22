"""Rounding modes, the four-level mode resolver and rounding helpers.

Standard library plus the sibling ``context`` and ``errors`` modules only.

Decisions: CA-1 (``ROUND_HALF_UP`` default, 10 decimals for ratios, 16 for
inverted FX rates), CA-3 (round-up primitive), Q1 (four-level precedence),
Q6 (a zero never carries a minus sign, scale is preserved), Q7, U2, U6, U8.

Rounding mode precedence, strongest first, with the ``ModeSource`` that is
reported for the level that supplied the mode:

1. rule-level ``rounding.mode``            -> ``rule``
2. corridor or jurisdiction override       -> ``jurisdiction``
3. currency setting                        -> ``currency``
4. default ``ROUND_HALF_UP``               -> ``default``

This module does not read rules, corridors or currency records. Callers pass
the values they already extracted (for example ``currency.rounding_mode``).

``ROUND_HALF_UP`` means a tie goes away from zero (``-2.345`` -> ``-2.35``),
as in Python's ``decimal`` module (U8).
"""

from __future__ import annotations

import decimal
from decimal import Context, Decimal
from enum import Enum

from .context import PRECISION, make_context
from .errors import RoundingModeError


class RoundingMode(str, Enum):
    """Supported rounding modes (U2). The value is the ``decimal`` constant name."""

    HALF_UP = "ROUND_HALF_UP"
    HALF_EVEN = "ROUND_HALF_EVEN"


class ModeSource(str, Enum):
    """Which level supplied the rounding mode (Q1, CL-08). Exact names."""

    RULE = "rule"
    JURISDICTION = "jurisdiction"
    CURRENCY = "currency"
    DEFAULT = "default"


#: Levels that can supply a mode, strongest first. ``DEFAULT`` is the fallback
#: when none of them supplies one, so it is not part of this tuple.
MODE_PRECEDENCE: tuple[ModeSource, ...] = (
    ModeSource.RULE,
    ModeSource.JURISDICTION,
    ModeSource.CURRENCY,
)

#: The mode used when no level supplies one (CA-1).
DEFAULT_MODE = RoundingMode.HALF_UP

#: Fixed scales (CA-1): ratios and exact break-even, and inverted FX rates.
RATIO_PLACES = 10
INVERSE_RATE_PLACES = 16

_DECIMAL_ROUNDING = {
    RoundingMode.HALF_UP: decimal.ROUND_HALF_UP,
    RoundingMode.HALF_EVEN: decimal.ROUND_HALF_EVEN,
}


def _require_mode(name: str, value: object) -> RoundingMode:
    """Accept only a ``RoundingMode``; a plain string is rejected on purpose."""
    if not isinstance(value, RoundingMode):
        raise RoundingModeError(
            f"{name} must be a RoundingMode, not {type(value).__name__}"
        )
    return value


def resolve_rounding_mode(
    *,
    rule: RoundingMode | None = None,
    jurisdiction: RoundingMode | None = None,
    currency: RoundingMode | None = None,
) -> tuple[RoundingMode, ModeSource]:
    """Return ``(mode, mode_source)`` using the four-level precedence (Q1).

    The first level in ``MODE_PRECEDENCE`` that is not ``None`` wins. With none
    supplied the result is ``(ROUND_HALF_UP, ModeSource.DEFAULT)``. The source
    names the level that **supplied** the mode, even when its value equals a
    weaker level or the default.

    Arguments are keyword-only so the levels cannot be swapped by position.
    A value that is neither ``None`` nor a ``RoundingMode`` raises
    ``RoundingModeError``, whatever the level, even when a stronger level
    would have won.
    """
    supplied = {
        ModeSource.RULE: rule,
        ModeSource.JURISDICTION: jurisdiction,
        ModeSource.CURRENCY: currency,
    }
    for source, value in supplied.items():
        if value is not None:
            _require_mode(source.value, value)
    for source in MODE_PRECEDENCE:
        value = supplied[source]
        if value is not None:
            return value, source
    return DEFAULT_MODE, ModeSource.DEFAULT


def _require_decimal(name: str, value: object) -> Decimal:
    """Reject anything that is not a finite ``Decimal`` (no float, int, str, bool)."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, not {value}")
    return value


def _require_places(places: object) -> int:
    if type(places) is not int:
        raise ValueError(f"places must be an int, not {type(places).__name__}")
    if not 0 <= places <= PRECISION:
        raise ValueError(f"places must be between 0 and {PRECISION}, not {places}")
    return places


def _positive_zero(value: Decimal) -> Decimal:
    """Drop the sign of a zero and keep its exponent (Q6). Others unchanged."""
    if value.is_zero() and value.is_signed():
        return value.copy_abs()
    return value


def round_amount(
    value: Decimal,
    places: int,
    mode: RoundingMode = RoundingMode.HALF_UP,
    ctx: Context | None = None,
) -> Decimal:
    """Round ``value`` to ``places`` decimal places with ``mode``.

    The result always has exactly ``places`` fractional digits, so the monetary
    scale is preserved (``0.00`` stays ``0.00``, never ``0``). A result of zero
    is returned as **positive** zero at that scale: ``-0.004`` at 2 places is
    ``Decimal("0.00")``, never ``Decimal("-0.00")`` (Q6).

    ``value`` must be a finite ``Decimal``: floats, ints and strings raise
    ``TypeError``; NaN and infinities raise ``ValueError``.
    """
    value = _require_decimal("value", value)
    places = _require_places(places)
    mode = _require_mode("mode", mode)
    ctx = ctx if ctx is not None else make_context()
    exponent = Decimal((0, (1,), -places))
    rounded = value.quantize(exponent, rounding=_DECIMAL_ROUNDING[mode], context=ctx)
    return _positive_zero(rounded)


def round_up_to_increment(
    value: Decimal, increment: Decimal, ctx: Context | None = None
) -> Decimal:
    """Round ``value`` up to the next multiple of ``increment`` (``ROUND_CEILING``).

    The primitive behind CA-3. It rounds towards positive infinity, also for
    negative values (U6): ``4090.1554`` at ``0.01`` is ``4090.16`` and
    ``-4090.1554`` at ``0.01`` is ``-4090.15``. A value that already is a
    multiple is returned with the same value. The result carries the scale of
    ``increment``. The increment must be greater than zero. Like
    ``round_amount``, a zero result is positive zero.

    The computation is exact: it uses an integer quotient and remainder, never
    a rounded division, so a quotient just above an integer is never lost.
    """
    value = _require_decimal("value", value)
    increment = _require_decimal("increment", increment)
    if not increment > 0:
        raise ValueError(f"increment must be greater than zero, not {increment}")
    ctx = ctx if ctx is not None else make_context()
    quotient, remainder = ctx.divmod(value, increment)
    if remainder > 0:
        quotient = ctx.add(quotient, Decimal(1))
    return _positive_zero(ctx.multiply(quotient, increment))


def round_ratio(value: Decimal, ctx: Context | None = None) -> Decimal:
    """Round a ratio or break-even quantity to 10 places, ``ROUND_HALF_UP`` (CA-1)."""
    return round_amount(value, RATIO_PLACES, RoundingMode.HALF_UP, ctx)


def round_inverse_rate(value: Decimal, ctx: Context | None = None) -> Decimal:
    """Round an inverted FX rate to 16 places, ``ROUND_HALF_UP`` (CA-1)."""
    return round_amount(value, INVERSE_RATE_PLACES, RoundingMode.HALF_UP, ctx)
