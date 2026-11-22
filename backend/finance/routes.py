"""HTTP surface for the per-unit economics engine.

Kept separate from main.py so the existing application file only needs a
one-line change to register this router.
"""

from fastapi import APIRouter, HTTPException

from .engine import (
    InvalidUnitEconomicsInputError,
    NonFiniteOutputError,
    calculate_unit_economics,
)
from .schemas import UnitEconomicsRequest, UnitEconomicsResponse

router = APIRouter(prefix="/api/v1", tags=["unit-economics"])


@router.post(
    "/unit-economics",
    response_model=UnitEconomicsResponse,
    response_model_by_alias=True,  # camelCase JSON, matching the TS contract
)
def compute_unit_economics(request: UnitEconomicsRequest) -> UnitEconomicsResponse:
    """Compute per-unit economics for one product unit."""
    try:
        result = calculate_unit_economics(
            product_cost=request.product_cost,
            shipping_cost=request.shipping_cost,
            other_fixed_costs=request.other_fixed_costs,
            selling_price=request.selling_price,
            platform_fee_percent=request.platform_fee_percent,
            payment_fee_percent=request.payment_fee_percent,
        )
    except (InvalidUnitEconomicsInputError, NonFiniteOutputError) as exc:
        # InvalidUnitEconomicsInputError should be unreachable here (Pydantic
        # validates first); catching it anyway keeps API behavior stable if
        # the two validation layers ever drift apart.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UnitEconomicsResponse.from_engine(result)