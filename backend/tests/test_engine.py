
"""Tests for the pure engine (finance/engine.py).

Float assertion strategy:
* Exact equality is used when intermediate values are exactly
  representable in binary.
* Decimal-derived expectations use pytest.approx.
* The reference-expression test recomputes the expressions in Python.
  It does not execute the TypeScript engine.
"""

import pytest

from finance.engine import (
    BreakEvenImpossible,
    BreakEvenPrice,
    InvalidUnitEconomicsInputError,
    NonFiniteOutputError,
    calculate_unit_economics,
)


def valid_kwargs(**overrides):
    kwargs = {
        "product_cost": 40.0,
        "shipping_cost": 5.0,
        "other_fixed_costs": 3.0,
        "selling_price": 100.0,
        "platform_fee_percent": 10.0,
        "payment_fee_percent": 2.9,
    }
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------
# Golden values
# --------------------------------------------------------------------------

def test_normal_profit_exact():
    result = calculate_unit_economics(
        product_cost=30,
        shipping_cost=5,
        other_fixed_costs=2.5,
        selling_price=100,
        platform_fee_percent=12.5,
        payment_fee_percent=25,
    )
    assert result.total_costs_before_percentage_fees == 37.5
    assert result.platform_fee_amount == 12.5
    assert result.payment_processing_fee_amount == 25.0
    assert result.total_costs == 75.0
    assert result.net_profit_per_unit == 25.0
    assert result.profit_margin_percent == 25.0
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    assert result.break_even_selling_price.price == 60.0


def test_loss_exact():
    result = calculate_unit_economics(
        product_cost=50,
        shipping_cost=12.5,
        other_fixed_costs=0,
        selling_price=50,
        platform_fee_percent=0,
        payment_fee_percent=0,
    )
    assert result.total_costs == 62.5
    assert result.net_profit_per_unit == -12.5
    assert result.profit_margin_percent == -25.0
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    assert result.break_even_selling_price.price == 62.5


def test_zero_fixed_costs():
    result = calculate_unit_economics(
        product_cost=0,
        shipping_cost=0,
        other_fixed_costs=0,
        selling_price=80,
        platform_fee_percent=25,
        payment_fee_percent=12.5,
    )
    assert result.total_costs_before_percentage_fees == 0.0
    assert result.net_profit_per_unit == 50.0
    assert result.profit_margin_percent == 62.5
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    assert result.break_even_selling_price.price == 0.0


def test_all_zero_costs_and_fees_margin_is_100():
    result = calculate_unit_economics(
        product_cost=0,
        shipping_cost=0,
        other_fixed_costs=0,
        selling_price=100,
        platform_fee_percent=0,
        payment_fee_percent=0,
    )
    assert result.net_profit_per_unit == 100.0
    assert result.profit_margin_percent == 100.0
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    assert result.break_even_selling_price.price == 0.0


# --------------------------------------------------------------------------
# Break-even at or above 100% combined fees
# --------------------------------------------------------------------------

def test_break_even_impossible_at_exactly_100_percent():
    result = calculate_unit_economics(
        product_cost=10,
        shipping_cost=0,
        other_fixed_costs=0,
        selling_price=100,
        platform_fee_percent=50,
        payment_fee_percent=50,
    )
    assert isinstance(result.break_even_selling_price, BreakEvenImpossible)
    assert "100" in result.break_even_selling_price.reason
    assert result.net_profit_per_unit == -10.0
    assert result.profit_margin_percent == -10.0


def test_break_even_impossible_above_100_percent():
    result = calculate_unit_economics(
        product_cost=10,
        shipping_cost=0,
        other_fixed_costs=0,
        selling_price=100,
        platform_fee_percent=60,
        payment_fee_percent=60,
    )
    assert isinstance(result.break_even_selling_price, BreakEvenImpossible)


def test_break_even_decision_uses_the_float_percent_sum():
    combined = 33.33 + 66.67
    result = calculate_unit_economics(
        product_cost=10,
        shipping_cost=0,
        other_fixed_costs=0,
        selling_price=100,
        platform_fee_percent=33.33,
        payment_fee_percent=66.67,
    )
    if combined < 100:
        assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    else:
        assert isinstance(result.break_even_selling_price, BreakEvenImpossible)


# --------------------------------------------------------------------------
# Reference expression sequence
# --------------------------------------------------------------------------

def test_engine_matches_reference_expression_sequence():
    # This is a Python-internal consistency check. It does not run TypeScript.
    product, shipping, other = 40.0, 5.0, 3.0
    price, platform_pct, payment_pct = 100.0, 10.0, 2.9

    fixed = product + shipping + other
    platform_fee = (platform_pct / 100) * price
    payment_fee = (payment_pct / 100) * price
    total = fixed + platform_fee + payment_fee
    net = price - total
    margin = (net / price) * 100
    fee_rate = (platform_pct + payment_pct) / 100
    break_even = fixed / (1 - fee_rate)

    result = calculate_unit_economics(
        product_cost=product,
        shipping_cost=shipping,
        other_fixed_costs=other,
        selling_price=price,
        platform_fee_percent=platform_pct,
        payment_fee_percent=payment_pct,
    )
    assert result.total_costs_before_percentage_fees == fixed
    assert result.platform_fee_amount == platform_fee
    assert result.payment_processing_fee_amount == payment_fee
    assert result.total_costs == total
    assert result.net_profit_per_unit == net
    assert result.profit_margin_percent == margin
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    assert result.break_even_selling_price.price == break_even


def test_typescript_doc_example_matches_decimal_math_approximately():
    result = calculate_unit_economics(
        product_cost=40,
        shipping_cost=5,
        other_fixed_costs=3,
        selling_price=100,
        platform_fee_percent=10,
        payment_fee_percent=2.9,
    )
    assert result.platform_fee_amount == pytest.approx(10.0, rel=1e-12)
    assert result.payment_processing_fee_amount == pytest.approx(
        2.9, rel=1e-12
    )
    assert result.total_costs == pytest.approx(60.9, rel=1e-12)
    assert result.net_profit_per_unit == pytest.approx(39.1, rel=1e-12)
    assert result.profit_margin_percent == pytest.approx(39.1, rel=1e-12)
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)
    assert result.break_even_selling_price.price == pytest.approx(
        48 / 0.871, rel=1e-12
    )


def test_net_profit_is_zero_at_break_even_price_within_float_tolerance():
    result = calculate_unit_economics(
        product_cost=40,
        shipping_cost=5,
        other_fixed_costs=3,
        selling_price=100,
        platform_fee_percent=10,
        payment_fee_percent=2.9,
    )
    assert isinstance(result.break_even_selling_price, BreakEvenPrice)

    at_break_even = calculate_unit_economics(
        product_cost=40,
        shipping_cost=5,
        other_fixed_costs=3,
        selling_price=result.break_even_selling_price.price,
        platform_fee_percent=10,
        payment_fee_percent=2.9,
    )
    assert at_break_even.net_profit_per_unit == pytest.approx(
        0.0, abs=1e-9
    )


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field",
    [
        "product_cost",
        "shipping_cost",
        "other_fixed_costs",
        "platform_fee_percent",
        "payment_fee_percent",
    ],
)
@pytest.mark.parametrize(
    "bad_value",
    [-1, -0.5, -1e-9, float("nan"), float("inf"), float("-inf")],
)
def test_rejects_invalid_non_negative_values(field, bad_value):
    with pytest.raises(InvalidUnitEconomicsInputError, match=field):
        calculate_unit_economics(**valid_kwargs(**{field: bad_value}))


@pytest.mark.parametrize(
    "bad_price",
    [0, 0.0, -100, float("nan"), float("inf"), float("-inf")],
)
def test_rejects_invalid_selling_price(bad_price):
    with pytest.raises(
        InvalidUnitEconomicsInputError, match="selling_price"
    ):
        calculate_unit_economics(**valid_kwargs(selling_price=bad_price))


def test_rejects_boolean_and_non_numeric_values():
    with pytest.raises(InvalidUnitEconomicsInputError, match="product_cost"):
        calculate_unit_economics(**valid_kwargs(product_cost=True))

    with pytest.raises(InvalidUnitEconomicsInputError, match="shipping_cost"):
        calculate_unit_economics(**valid_kwargs(shipping_cost="5"))


def test_rejects_integers_too_large_for_float():
    with pytest.raises(InvalidUnitEconomicsInputError, match="product_cost"):
        calculate_unit_economics(**valid_kwargs(product_cost=10**400))


def test_collects_all_validation_problems():
    with pytest.raises(InvalidUnitEconomicsInputError) as exc_info:
        calculate_unit_economics(
            **valid_kwargs(product_cost=-1, selling_price=0)
        )

    message = str(exc_info.value)
    assert "product_cost" in message
    assert "selling_price" in message


# --------------------------------------------------------------------------
# Overflow detection
# --------------------------------------------------------------------------

def test_overflow_in_cost_sum_raises():
    with pytest.raises(
        NonFiniteOutputError, match="total_costs_before_percentage_fees"
    ):
        calculate_unit_economics(
            product_cost=1.7e308,
            shipping_cost=1.7e308,
            other_fixed_costs=0,
            selling_price=100,
            platform_fee_percent=0,
            payment_fee_percent=0,
        )


def test_overflow_in_fee_amount_raises():
    with pytest.raises(NonFiniteOutputError, match="platform_fee_amount"):
        calculate_unit_economics(
            product_cost=0,
            shipping_cost=0,
            other_fixed_costs=0,
            selling_price=1e308,
            platform_fee_percent=1e308,
            payment_fee_percent=0,
        )


def test_overflow_in_total_costs_with_finite_components():
    with pytest.raises(NonFiniteOutputError) as exc_info:
        calculate_unit_economics(
            product_cost=1.7e308,
            shipping_cost=0,
            other_fixed_costs=0,
            selling_price=1.7e308,
            platform_fee_percent=50,
            payment_fee_percent=50,
        )

    message = str(exc_info.value)
    assert "total_costs" in message
    assert "net_profit_per_unit" in message
    assert "profit_margin_percent" in message


def test_overflow_in_profit_margin_with_tiny_selling_price():
    with pytest.raises(
        NonFiniteOutputError, match="profit_margin_percent"
    ):
        calculate_unit_economics(
            product_cost=1e308,
            shipping_cost=0,
            other_fixed_costs=0,
            selling_price=1e-300,
            platform_fee_percent=0,
            payment_fee_percent=0,
        )


def test_overflow_in_break_even_price():
    with pytest.raises(
        NonFiniteOutputError, match="break_even_selling_price"
    ):
        calculate_unit_economics(
            product_cost=1.7e308,
            shipping_cost=0,
            other_fixed_costs=0,
            selling_price=100,
            platform_fee_percent=25,
            payment_fee_percent=25,
        )
