"""Money primitives for the calculation package (M1-1).

Standard library only (E1). Pydantic appears in tests only.

Contents:
  * errors   - MoneyError and subclasses; three decimal errors carry registry codes.
  * context  - the fixed Decimal context (precision 60, ROUND_HALF_UP) and
               exact arithmetic helpers.
  * rounding - RoundingMode, the four-level mode resolver, round_amount,
               round_up_to_increment, ratio and inverse-rate rounding.
  * grammar  - parse_decimal (MONEY, RULE_RATE, FX_RATE) and to_plain_string.
  * currency - the Currency model and lookup interface. No currency records:
               they arrive as data (M1-5).

M2 requirement (U9): FX override values must be validated with
DecimalKind.FX_RATE; ordinary rule and override rates use DecimalKind.RULE_RATE.
"""

from .context import (
    CONTEXT_ROUNDING,
    PRECISION,
    add,
    calc_context,
    div,
    make_context,
    mul,
    total,
)
from .currency import Currency, CurrencyProvider, CurrencyTable
from .errors import (
    AMOUNT_OUT_OF_RANGE,
    INVALID_DECIMAL,
    SCALE_EXCEEDED,
    AmountOutOfRangeError,
    DecimalError,
    InvalidDecimalError,
    MoneyError,
    RoundingModeError,
    ScaleExceededError,
    UnknownCurrencyError,
)
from .grammar import (
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
from .rounding import (
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

__all__ = [
    # errors
    "AMOUNT_OUT_OF_RANGE",
    "INVALID_DECIMAL",
    "SCALE_EXCEEDED",
    "AmountOutOfRangeError",
    "DecimalError",
    "InvalidDecimalError",
    "MoneyError",
    "RoundingModeError",
    "ScaleExceededError",
    "UnknownCurrencyError",
    # context
    "CONTEXT_ROUNDING",
    "PRECISION",
    "add",
    "calc_context",
    "div",
    "make_context",
    "mul",
    "total",
    # rounding
    "DEFAULT_MODE",
    "INVERSE_RATE_PLACES",
    "MODE_PRECEDENCE",
    "RATIO_PLACES",
    "ModeSource",
    "RoundingMode",
    "resolve_rounding_mode",
    "round_amount",
    "round_inverse_rate",
    "round_ratio",
    "round_up_to_increment",
    # grammar
    "FX_RATE_MAX_FRACTION_DIGITS",
    "FX_RATE_MAX_TOTAL_DIGITS",
    "MONEY_MAX_FRACTION_DIGITS",
    "MONEY_MAX_VALUE",
    "RULE_RATE_MAX_FRACTION_DIGITS",
    "RULE_RATE_MAX_VALUE",
    "DecimalKind",
    "parse_decimal",
    "to_plain_string",
    # currency
    "Currency",
    "CurrencyProvider",
    "CurrencyTable",
]
