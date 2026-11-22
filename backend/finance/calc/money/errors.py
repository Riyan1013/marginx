"""Errors raised by the money package (standard library only).

Only the three decimal-grammar errors carry a registry code (decision U5,
CA-4). The error registry and envelope themselves belong to M1-2; these
codes are plain strings that M1-2 will register.

``RoundingModeError`` and ``UnknownCurrencyError`` are internal: they have no
registry code.
"""

from __future__ import annotations

# Registry codes for the decimal grammar (CA-4, CA-6).
INVALID_DECIMAL = "INVALID_DECIMAL"
SCALE_EXCEEDED = "SCALE_EXCEEDED"
AMOUNT_OUT_OF_RANGE = "AMOUNT_OUT_OF_RANGE"


class MoneyError(Exception):
    """Base class for every error raised by the money package."""

    #: Registry code, or ``None`` for an internal error.
    code: str | None = None


class DecimalError(MoneyError):
    """A decimal string failed grammar or limit validation.

    Subclasses set ``code``; this base class is never raised directly.
    """

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code or "")


class InvalidDecimalError(DecimalError):
    """The value is not a string in the accepted decimal grammar."""

    code = INVALID_DECIMAL


class ScaleExceededError(DecimalError):
    """The value has more fractional digits than its kind allows."""

    code = SCALE_EXCEEDED


class AmountOutOfRangeError(DecimalError):
    """The value is above the limit for its kind."""

    code = AMOUNT_OUT_OF_RANGE


class RoundingModeError(MoneyError):
    """A rounding mode is not a supported ``RoundingMode`` (internal)."""


class UnknownCurrencyError(MoneyError):
    """A currency code is not known to the provider (internal)."""
