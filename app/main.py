import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .auth import require_api_key
from .config import get_settings
from .errors import ApiError
from .schemas import SendEmailRequest
from .smtp_service import send_email

logger = logging.getLogger("selfsend")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.SELFSEND_LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not settings.api_keys:
        logger.warning("SELFSEND_API_KEYS is empty, all requests will be rejected")
    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST is empty, email delivery will fail")
    logger.info(
        "selfsend listening on %s:%s (smtp=%s:%s starttls=%s ssl=%s, rate_limit=%s/min)",
        settings.SELFSEND_HOST,
        settings.SELFSEND_PORT,
        settings.SMTP_HOST or "unset",
        settings.SMTP_PORT,
        settings.SMTP_STARTTLS,
        settings.SMTP_SSL,
        settings.SELFSEND_RATE_LIMIT_PER_MINUTE,
    )
    yield


app = FastAPI(
    title="selfsend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"name": exc.name, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    summary = "; ".join(
        f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
        for error in exc.errors()[:5]
    )
    return JSONResponse(
        status_code=422,
        content={"name": "validation_error", "message": summary},
    )


@app.middleware("http")
async def request_guard(request: Request, call_next):
    settings = get_settings()
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > settings.SELFSEND_MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"name": "payload_too_large", "message": "request body too large"},
        )
    started = time.monotonic()
    response = await call_next(request)
    logger.info(
        "%s %s -> %s (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - started) * 1000,
    )
    return response


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "smtp_configured": bool(settings.SMTP_HOST),
        "auth_configured": bool(settings.api_keys),
    }


@app.post("/emails")
async def post_emails(payload: SendEmailRequest, _: str = Depends(require_api_key)):
    email_id = await send_email(payload)
    return {"id": email_id, "object": "email"}
