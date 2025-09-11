from fastapi import Request, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .logger import get_logger

log = get_logger(__name__)

def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        log.error(f"Validation error on {request.url}: {exc.errors()}")
        return JSONResponse(status_code=422, content={"detail": exc.errors()})
