from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("items_api.security")

INSECURE_JWT_SECRETS = frozenset(
    {
        "change-me-in-production-use-long-random-string",
        "dev-secret-change-in-production-items-api-32chars",
        "secret",
        "changeme",
        "test-secret-key-for-tests-only-32b",
    }
)


def validate_runtime_settings(settings: Any) -> None:
    if not settings.is_production:
        if settings.jwt_secret in INSECURE_JWT_SECRETS or len(settings.jwt_secret) < 32:
            logger.warning(
                "event=weak_jwt_secret environment=%s msg=using_non_production_secret",
                settings.environment,
            )
        return

    errors: list[str] = []
    if settings.jwt_secret in INSECURE_JWT_SECRETS:
        errors.append("JWT_SECRET must not use a known default value in production")
    if len(settings.jwt_secret) < 32:
        errors.append("JWT_SECRET must be at least 32 characters in production")
    if settings.cookie_secure is False:
        errors.append("COOKIE_SECURE cannot be false in production")
    if settings.allow_seed:
        errors.append("ALLOW_SEED must be false in production")
    if not settings.cors_origin_list:
        errors.append("CORS_ORIGINS must list at least one frontend origin in production")
    if errors:
        raise RuntimeError("Insecure production configuration: " + "; ".join(errors))


def log_security_event(
    event: str,
    *,
    request_id: str | None = None,
    email: str | None = None,
    ip: str | None = None,
    user_id: str | None = None,
    detail: str | None = None,
    **extra: Any,
) -> None:
    parts = [
        f"event={event}",
        f"request_id={request_id or '-'}",
        f"ip={ip or '-'}",
        f"email={email or '-'}",
        f"user_id={user_id or '-'}",
        f"detail={detail or '-'}",
    ]
    for key, value in extra.items():
        parts.append(f"{key}={value}")
    logger.warning(" ".join(parts))
