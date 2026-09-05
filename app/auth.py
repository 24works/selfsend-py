import secrets

from fastapi import Request

from .config import get_settings
from .errors import ApiError
from .rate_limit import rate_limiter


def key_fingerprint(key: str) -> str:
    if len(key) > 12:
        return f"{key[:6]}...{key[-4:]}"
    return key[:6]


async def require_api_key(request: Request) -> str:
    settings = get_settings()

    valid_keys = settings.api_keys
    if not valid_keys:
        raise ApiError(
            500,
            "service_misconfigured",
            "no API keys configured on the server (SELFSEND_API_KEYS is empty)",
        )

    header = request.headers.get("authorization")
    if not header:
        raise ApiError(401, "missing_api_key", "missing Authorization header")

    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ApiError(
            401,
            "invalid_api_key",
            "Authorization header must be 'Bearer <api key>'",
        )

    token = parts[1].strip()
    matched_key = next(
        (key for key in valid_keys if secrets.compare_digest(token, key)),
        None,
    )
    if matched_key is None:
        raise ApiError(401, "invalid_api_key", "invalid API key")

    if not rate_limiter.check(
        f"key:{matched_key}",
        settings.SELFSEND_RATE_LIMIT_PER_MINUTE,
    ):
        raise ApiError(
            429,
            "rate_limit_exceeded",
            f"rate limit exceeded ({settings.SELFSEND_RATE_LIMIT_PER_MINUTE} requests/minute)",
        )

    request.state.api_key_fingerprint = key_fingerprint(matched_key)
    return matched_key
