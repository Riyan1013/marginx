
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from finance.routes import router as finance_router


app = FastAPI(
    title="MarginX API",
    description="Financial intelligence backend for MarginX",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    safe_errors = [
        {
            key: value
            for key, value in error.items()
            if key not in {"input", "ctx"}
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors},
    )


app.include_router(finance_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to MarginX API",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "MarginX API",
    }
