import os


def main() -> None:
    import uvicorn

    from items_api.config import get_settings

    settings = get_settings()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("UVICORN_WORKERS", "1")))

    if settings.is_production:
        uvicorn.run(
            "items_api.main:app",
            host=host,
            port=port,
            workers=max(1, workers),
            reload=False,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    else:
        uvicorn.run(
            "items_api.main:app",
            host=host,
            port=port,
            reload=True,
        )
