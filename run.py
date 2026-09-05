import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.SELFSEND_HOST,
        port=settings.SELFSEND_PORT,
        log_level=settings.SELFSEND_LOG_LEVEL.lower(),
        server_header=False,
    )


if __name__ == "__main__":
    main()
