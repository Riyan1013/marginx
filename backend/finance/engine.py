
"""Pure per-unit economics engine -- Python port of the TypeScript calculator
(``lib/finance/calculator.ts``).

Framework-free: no FastAPI, no Pydantic, no I/O, no rounding. Rounding is the
presentation layer's job.

FORMULAS
--------
With::

    C = product_cost + shipping_cost + other_fixed_costs
    x = selling_price

the outputs are::

    total_costs_before_percentage_fees = C
    platform_fee_amount                 = (platform_fee_percent / 100) * x
    payment_processing_fee_amount       = (payment_fee_percent / 100) * x
    total_costs                         = C + platform_fee_amount
                                          + payment_processing_fee_amount
    net_profit_per_unit                 = x - total_costs
    profit_margin_percent               = (net_profit_per_unit / x) * 100

Break-even: because both fees scale with the price, the break-even price is
not "costs plus fees" (that is circular); it solves::

    x * (1 - p - q) - C = 0    =>    x* = C / (1 - p - q)

where p and q are the fee fractions. A finite, nonnegative solution exists
only when the combined percentage fees are strictly below 100%; at or above
100% the engine reports the break-even price as impossible.

PARITY NOTE
-----------
The expression order mirrors the TypeScript engine expression by expression.
Both languages use IEEE-754 binary64 doubles, so identical expressions on
identical input doubles are expected to yield identical results. This is an
expectation to verify through testing, not a guarantee. Cross-language bit
equality should be checked against actual TypeScript outputs, for example
using golden values exported from the TypeScript engine.

Do not algebraically simplify expressions (e.g.
``platform_fee_percent * selling_price / 100``), because different grouping
can change the last bit.

``total_costs`` is summed in reporting order so it equals the sum of the
three reported components bit-for-bit within this Python implementation.
"""

import math
from dataclasses import dataclass


class InvalidUnitEconomicsInputError(ValueError):
    """An input violates the validation rules (mirrors the TS TypeError)."""


class NonFiniteOutputError(ValueError):
    """Finite inputs produced non-finite outputs (mirrors the TS RangeError)."""


@dataclass(frozen=True)
class BreakEvenPrice:
    """A finite, nonnegative break-even selling price exists."""

    price: float


@dataclass(frozen=True)
class BreakEvenImpossible:
    """Combined percentage fees are >= 100%; no finite break-even price."""

    reason: str


@dataclass(frozen=True)
class UnitEconomicsResult:
    """Per-unit outputs. All floats are unrounded."""

    total_costs_before_percentage_fees: float
    platform_fee_amount: float
    payment_processing_fee_amount: float
    total_costs: float
    net_profit_per_unit: float
    profit_margin_percent: float
    break_even_selling_price: BreakEvenPrice | BreakEvenImpossible


def calculate_unit_economics(
    *,
    product_cost: float,
    shipping_cost: float,
    other_fixed_costs: float,
    selling_price: float,
    platform_fee_percent: float,
    payment_fee_percent: float,
) -> UnitEconomicsResult:
    """Compute per-unit economics.

    Usage::

        result = calculate_unit_economics(
            product_cost=40, shipping_cost=5, other_fixed_costs=3,
            selling_price=100, platform_fee_percent=10, payment_fee_percent=2.9,
        )
        # Decimal-exact values (floats may differ in the last bits):
        #   total_costs_before_percentage_fees = 48
        #   platform_fee_amount                 = 10
        #   payment_processing_fee_amount       = 2.9
        #   total_costs                         = 60.9
        #   net_profit_per_unit                 = 39.1
        #   profit_margin_percent               = 39.1
        #   break_even_selling_price            = 48 / 0.871 (about 55.10907)

    :raises InvalidUnitEconomicsInputError: if any cost or fee percentage is
        negative or non-finite, or if ``selling_price`` is non-finite or <= 0.
    :raises NonFiniteOutputError: if finite inputs overflow into non-finite
        outputs.
    """
    _validate_inputs(
        product_cost=product_cost,
        shipping_cost=shipping_cost,
        other_fixed_costs=other_fixed_costs,
        selling_price=selling_price,
        platform_fee_percent=platform_fee_percent,
        payment_fee_percent=payment_fee_percent,
    )

    # Fixed costs before percentage-based fees (C).
    total_costs_before_percentage_fees = (
        product_cost + shipping_cost + other_fixed_costs
    )

    # Percentage-based fees are charged on the selling price.
    platform_fee_amount = (platform_fee_percent / 100) * selling_price
    payment_processing_fee_amount = (payment_fee_percent / 100) * selling_price

    # Summed in reporting order so total_costs equals the sum of the three
    # reported components bit-for-bit within this Python implementation.
    total_costs = (
        total_costs_before_percentage_fees
        + platform_fee_amount
        + payment_processing_fee_amount
    )

    net_profit_per_unit = selling_price - total_costs
    profit_margin_percent = (net_profit_per_unit / selling_price) * 100

    result = UnitEconomicsResult(
        total_costs_before_percentage_fees=total_costs_before_percentage_fees,
        platform_fee_amount=platform_fee_amount,
        payment_processing_fee_amount=payment_processing_fee_amount,
        total_costs=total_costs,
        net_profit_per_unit=net_profit_per_unit,
        profit_margin_percent=profit_margin_percent,
        break_even_selling_price=_break_even_selling_price(
            total_costs_before_percentage_fees,
            platform_fee_percent,
            payment_fee_percent,
        ),
    )

    _assert_finite_outputs(result)
    return result


def _is_finite_number(value: object) -> bool:
    """True for int/float (not bool) values that are finite as floats.

    ``bool`` is rejected explicitly: it is a subclass of ``int`` in Python,
    while the TypeScript engine rejects booleans (``Number.isFinite(true)``
    is ``false``). Ints too large for a float make ``math.isfinite`` raise
    ``OverflowError``; those count as non-finite. Other numeric types
    (``Decimal``, ``Fraction``, ...) are not accepted -- the engine is a
    float engine, matching the TS implementation.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False

    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _validate_inputs(
    *,
    product_cost: float,
    shipping_cost: float,
    other_fixed_costs: float,
    selling_price: float,
    platform_fee_percent: float,
    payment_fee_percent: float,
) -> None:
    """Reject invalid inputs, collecting every problem into one error."""
    problems: list[str] = []

    for name, value in (
        ("product_cost", product_cost),
        ("shipping_cost", shipping_cost),
        ("other_fixed_costs", other_fixed_costs),
        ("platform_fee_percent", platform_fee_percent),
        ("payment_fee_percent", payment_fee_percent),
    ):
        if not _is_finite_number(value):
            problems.append(
                f"{name} must be a finite number (received {value!r})"
            )
        elif value < 0:
            problems.append(f"{name} must be >= 0 (received {value!r})")

    if not _is_finite_number(selling_price):
        problems.append(
            f"selling_price must be a finite number (received {selling_price!r})"
        )
    elif selling_price <= 0:
        problems.append(f"selling_price must be > 0 (received {selling_price!r})")

    if problems:
        raise InvalidUnitEconomicsInputError(
            "Invalid unit economics input: " + "; ".join(problems) + "."
        )


def _break_even_selling_price(
    fixed_costs: float,
    platform_fee_percent: float,
    payment_fee_percent: float,
) -> BreakEvenPrice | BreakEvenImpossible:
    """x* = C / (1 - (p + q)), possible only when p + q < 100%."""

    # Sum percentages before dividing by 100, matching the TypeScript
    # expression order. Cross-language bit equality remains an expectation
    # to verify by testing, not a guarantee.
    #
    # If this sum overflows to infinity, both inputs are still finite, but
    # their true sum is necessarily above 100%. The impossible result remains
    # correct; its reason text may display "inf%", a cosmetic limitation.
    combined_fee_percent = platform_fee_percent + payment_fee_percent

    if combined_fee_percent >= 100:
        return BreakEvenImpossible(
            reason=(
                f"Combined percentage fees are {combined_fee_percent}% (>= 100%). "
                "Net profit is sellingPrice * (1 - feeRate) - fixedCosts, so with "
                "feeRate >= 1 no positive selling price can cover the fixed costs; "
                "a finite, nonnegative break-even price is impossible."
            )
        )

    fee_rate = combined_fee_percent / 100
    return BreakEvenPrice(price=fixed_costs / (1 - fee_rate))


def _assert_finite_outputs(result: UnitEconomicsResult) -> None:
    """Guarantee the engine never returns NaN or +/-Infinity."""
    outputs: dict[str, float] = {
        "total_costs_before_percentage_fees": (
            result.total_costs_before_percentage_fees
        ),
        "platform_fee_amount": result.platform_fee_amount,
        "payment_processing_fee_amount": result.payment_processing_fee_amount,
        "total_costs": result.total_costs,
        "net_profit_per_unit": result.net_profit_per_unit,
        "profit_margin_percent": result.profit_margin_percent,
    }

    if isinstance(result.break_even_selling_price, BreakEvenPrice):
        outputs["break_even_selling_price.price"] = (
            result.break_even_selling_price.price
        )

    non_finite = [
        name for name, value in outputs.items()
        if not _is_finite_number(value)
    ]

    if non_finite:
        raise NonFiniteOutputError(
            "Finite inputs produced non-finite outputs (floating-point overflow): "
            + ", ".join(non_finite)
            + "."
        )
