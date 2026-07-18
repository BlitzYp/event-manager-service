from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        raise exc
    return JSONResponse(
        content={"error": {"code": exc.code, "message": exc.message}},
        status_code=exc.status,
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    fields = [
        {"path": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request.",
                "fields": fields,
            }
        },
        status_code=422,
    )
