from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_err = errors[0] if errors else {}
    field = ".".join(str(loc) for loc in first_err.get("loc", []) if loc != "body")
    msg = first_err.get("msg", "Invalid input")
    detail_message = f"Field '{field}': {msg}" if field else msg

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": detail_message,
            }
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        content = exc.detail
    else:
        code = "UNAUTHORIZED" if exc.status_code == 401 else (
            "NOT_FOUND" if exc.status_code == 404 else (
                "FORBIDDEN" if exc.status_code == 403 else (
                    "CONFLICT" if exc.status_code == 409 else "REQUEST_ERROR"
                )
            )
        )
        content = {
            "error": {
                "code": code,
                "message": str(exc.detail),
            }
        }

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )


async def global_exception_handler(request: Request, exc: Exception):
    print(f"[Unhandled Exception] {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
            }
        },
    )
