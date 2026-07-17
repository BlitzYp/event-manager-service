from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.status, {"error": {"code": exc.code, "message": exc.message}})


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {"path": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        422,
        {"error": {"code": "validation_error", "message": "Invalid request.", "fields": fields}},
    )

