from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .database import engine
from .errors import ApiError, api_error_handler, validation_error_handler
from .routers import admin, auth, participant, vendor

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_app_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(participant.router, prefix="/api/v1")
app.include_router(vendor.router, prefix="/api/v1")


@app.get("/health", include_in_schema=False)
def health() -> dict:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}

