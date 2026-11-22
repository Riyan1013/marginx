"""Pydantic v2 request/response models for the unit-economics endpoint.

The JSON contract uses camelCase keys to match the TypeScript
``UnitEconomicsInput`` / ``UnitEconomicsResult`` types exactly. Models use
snake_case field names internally with ``to_camel`` aliases.
"""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from .engine import BreakEvenImpossible, BreakEvenPrice, UnitEconomicsResult

_FIELDS = (
    "product_cost",
    "shipping_cost",
    "other_fixed_costs",
    "selling_price",
    "platform_fee_percent",
    "payment_fee_percent",
)


class _CamelModel(BaseModel):
    """Base model: snake_case fields, camelCase JSON aliases."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UnitEconomicsRequest(_CamelModel):
    """Per-unit inputs (JSON keys: productCost, shippingCost, ...). All required."""

    product_cost: float = Field(ge=0, description="Cost to produce or acquire one unit.")
    shipping_cost: float = Field(ge=0, description="Shipping cost for one unit.")
    other_fixed_costs: float = Field(
        ge=0, description="Other per-unit fixed costs (packaging, handling, ...)."
    )
    selling_price: float = Field(
        gt=0, description="Selling price of one unit; margin is undefined at 0."
    )
    platform_fee_percent: float = Field(
        ge=0, description="Platform fee in percent of the selling price."
    )
    payment_fee_percent: float = Field(
        ge=0, description="Payment processing fee in percent of the selling price."
    )

    @field_validator(*_FIELDS, mode="before")
    @classmethod
    def _reject_booleans(cls, value: object) -> object:
        # JSON true/false must not become 1.0/0.0: the TypeScript engine
        # rejects booleans (Number.isFinite(true) is false).
        if isinstance(value, bool):
            raise ValueError("must be a number, not a boolean")
        return value

    @field_validator(*_FIELDS)
    @classmethod
    def _reject_non_finite(cls, value: float) -> float:
        # The ge/gt bounds already reject NaN and -Infinity; this also
        # rejects +Infinity (JSON 1e400, the non-standard Infinity token,
        # or a string like "inf" if lax coercion ever produces one).
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value


class BreakEvenPriceResponse(_CamelModel):
    """A finite, nonnegative break-even price exists."""

    possible: Literal[True] = True
    price: float


class BreakEvenImpossibleResponse(_CamelModel):
    """Combined percentage fees are >= 100%; break-even is impossible."""

    possible: Literal[False] = False
    reason: str


class UnitEconomicsResponse(_CamelModel):
    """Per-unit outputs, unrounded (JSON keys are camelCase)."""

    total_costs_before_percentage_fees: float
    platform_fee_amount: float
    payment_processing_fee_amount: float
    total_costs: float
    net_profit_per_unit: float
    profit_margin_percent: float
    break_even_selling_price: BreakEvenPriceResponse | BreakEvenImpossibleResponse

    @classmethod
    def from_engine(cls, result: UnitEconomicsResult) -> "UnitEconomicsResponse":
        """Map the pure engine result onto the response contract."""
        break_even = result.break_even_selling_price
        mapped: BreakEvenPriceResponse | BreakEvenImpossibleResponse
        if isinstance(break_even, BreakEvenPrice):
            mapped = BreakEvenPriceResponse(price=break_even.price)
        else:
            mapped = BreakEvenImpossibleResponse(reason=break_even.reason)

        return cls(
            total_costs_before_percentage_fees=result.total_costs_before_percentage_fees,
            platform_fee_amount=result.platform_fee_amount,
            payment_processing_fee_amount=result.payment_processing_fee_amount,
            total_costs=result.total_costs,
            net_profit_per_unit=result.net_profit_per_unit,
            profit_margin_percent=result.profit_margin_percent,
            break_even_selling_price=mapped,
        )