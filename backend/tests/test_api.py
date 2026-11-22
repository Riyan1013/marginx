"""HTTP-level tests for POST /api/v1/unit-economics.

These tests build a private FastAPI app around the router instead of
importing main.py, keeping them independent of other application routes.

The test app registers the same safe RequestValidationError handler as
the production app in main.py. FastAPI's default handler echoes the raw
invalid `input` value inside its 422 response; when that value is a
non-finite float (NaN, Infinity, -Infinity, or 1e400 parsing to inf),
Starlette's JSONResponse cannot serialize the body and raises
"ValueError: Out of range float values are not JSON compliant", turning
a clean validation rejection into a server error.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from finance.routes import router

ENDPOINT = "/api/v1/unit-economics"

VALID_PAYLOAD = {
    "productCost": 30,
    "shippingCost": 5,
    "otherFixedCosts": 2.5,
    "sellingPrice": 100,
    "platformFeePercent": 12.5,
    "paymentFeePercent": 25,
}

app = FastAPI()
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def safe_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Test-app mirror of the custom handler in backend/main.py.

    FastAPI's default RequestValidationError handler embeds each error's
    `input` and `ctx` in the 422 body. `input` may be a non-finite float,
    which json.dumps (allow_nan=False, as used by Starlette's
    JSONResponse) refuses to serialize -- the exact cause of the five
    failures this handler fixes. `ctx` may hold non-JSON-serializable
    objects such as the ValueError raised by a field validator. Removing
    both keeps the response serializable; the remaining keys (type, loc,
    msg, and optionally url) are always JSON-safe.
    """
    safe_errors = []
    for error in exc.errors():
        safe = dict(error)
        safe.pop("input", None)
        safe.pop("ctx", None)
        safe_errors.append(safe)
    return JSONResponse(status_code=422, content={"detail": safe_errors})


client = TestClient(app)


# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------

def test_normal_profit_returns_exact_camelcase_body():
    response = client.post(ENDPOINT, json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {
        "totalCostsBeforePercentageFees": 37.5,
        "platformFeeAmount": 12.5,
        "paymentProcessingFeeAmount": 25.0,
        "totalCosts": 75.0,
        "netProfitPerUnit": 25.0,
        "profitMarginPercent": 25.0,
        "breakEvenSellingPrice": {"possible": True, "price": 60.0},
    }


def test_loss_returns_negative_profit_and_margin():
    response = client.post(
        ENDPOINT,
        json={
            "productCost": 50,
            "shippingCost": 12.5,
            "otherFixedCosts": 0,
            "sellingPrice": 50,
            "platformFeePercent": 0,
            "paymentFeePercent": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["netProfitPerUnit"] == -12.5
    assert body["profitMarginPercent"] == -25.0
    assert body["breakEvenSellingPrice"] == {
        "possible": True,
        "price": 62.5,
    }


def test_zero_fixed_costs_break_even_is_zero():
    response = client.post(
        ENDPOINT,
        json={
            "productCost": 0,
            "shippingCost": 0,
            "otherFixedCosts": 0,
            "sellingPrice": 80,
            "platformFeePercent": 25,
            "paymentFeePercent": 12.5,
        },
    )

    assert response.status_code == 200
    assert response.json()["breakEvenSellingPrice"] == {
        "possible": True,
        "price": 0.0,
    }


def test_unknown_fields_are_ignored_like_the_ts_engine():
    response = client.post(
        ENDPOINT,
        json={**VALID_PAYLOAD, "unexpected": 123},
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Combined fees at or above 100%
# --------------------------------------------------------------------------

def test_combined_fees_at_100_percent_report_impossible_with_reason():
    response = client.post(
        ENDPOINT,
        json={
            "productCost": 10,
            "shippingCost": 0,
            "otherFixedCosts": 0,
            "sellingPrice": 100,
            "platformFeePercent": 50,
            "paymentFeePercent": 50,
        },
    )

    assert response.status_code == 200
    break_even = response.json()["breakEvenSellingPrice"]
    assert break_even["possible"] is False
    assert isinstance(break_even["reason"], str) and break_even["reason"]


def test_combined_fees_above_100_percent_report_impossible():
    response = client.post(
        ENDPOINT,
        json={
            "productCost": 10,
            "shippingCost": 0,
            "otherFixedCosts": 0,
            "sellingPrice": 100,
            "platformFeePercent": 60,
            "paymentFeePercent": 60,
        },
    )

    assert response.status_code == 200
    assert response.json()["breakEvenSellingPrice"]["possible"] is False


# --------------------------------------------------------------------------
# Invalid inputs
# --------------------------------------------------------------------------

MISSING_PRODUCT_COST = {
    key: value
    for key, value in VALID_PAYLOAD.items()
    if key != "productCost"
}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        MISSING_PRODUCT_COST,
        {**VALID_PAYLOAD, "productCost": -1},
        {**VALID_PAYLOAD, "shippingCost": -0.01},
        {**VALID_PAYLOAD, "otherFixedCosts": -100},
        {**VALID_PAYLOAD, "platformFeePercent": -5},
        {**VALID_PAYLOAD, "paymentFeePercent": -0.001},
        {**VALID_PAYLOAD, "sellingPrice": 0},
        {**VALID_PAYLOAD, "sellingPrice": -100},
        {**VALID_PAYLOAD, "productCost": "not a number"},
        {**VALID_PAYLOAD, "otherFixedCosts": None},
        {**VALID_PAYLOAD, "productCost": True},
    ],
)
def test_invalid_payloads_return_422(payload):
    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], (list, str))


# --------------------------------------------------------------------------
# Non-finite JSON values
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_body",
    [
        b'{"productCost": NaN, "shippingCost": 5, "otherFixedCosts": 3, '
        b'"sellingPrice": 100, "platformFeePercent": 10, "paymentFeePercent": 2.9}',
        b'{"productCost": 40, "shippingCost": 5, "otherFixedCosts": 3, '
        b'"sellingPrice": 100, "platformFeePercent": Infinity, "paymentFeePercent": 2.9}',
        b'{"productCost": 40, "shippingCost": 5, "otherFixedCosts": 3, '
        b'"sellingPrice": 100, "platformFeePercent": 10, "paymentFeePercent": -Infinity}',
        b'{"productCost": 40, "shippingCost": 5, "otherFixedCosts": 3, '
        b'"sellingPrice": Infinity, "platformFeePercent": 10, "paymentFeePercent": 2.9}',
        b'{"productCost": 1e400, "shippingCost": 5, "otherFixedCosts": 3, '
        b'"sellingPrice": 100, "platformFeePercent": 10, "paymentFeePercent": 2.9}',
    ],
)

def test_non_finite_json_values_return_422(raw_body):
    # Send the raw JSON bytes directly so the test client does not
    # try to serialize NaN or Infinity as Python float values.
    response = client.post(
        ENDPOINT,
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    # The 422 body must itself be valid, serializable JSON with error
    # details -- the original failure was exactly this body failing to
    # serialize because it echoed the non-finite input value.
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail


# --------------------------------------------------------------------------
# Overflow
# --------------------------------------------------------------------------

def test_floating_point_overflow_returns_422():
    response = client.post(
        ENDPOINT,
        json={
            **VALID_PAYLOAD,
            "productCost": 1.7e308,
            "shippingCost": 1.7e308,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]


def test_margin_overflow_returns_422():
    # Huge fixed costs and a tiny selling price overflow the profit margin.
    response = client.post(
        ENDPOINT,
        json={
            "productCost": 1e308,
            "shippingCost": 0,
            "otherFixedCosts": 0,
            "sellingPrice": 1e-300,
            "platformFeePercent": 0,
            "paymentFeePercent": 0,
        },
    )

    assert response.status_code == 422
    assert "profit_margin_percent" in response.json()["detail"]