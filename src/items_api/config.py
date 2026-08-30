from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config — prefer `.env` / environment variables over code defaults.

    Required (must be set in env): mongo, redis URL, CORS origins, JWT secret,
    default user password. Optional fields keep safe local defaults and can still
    be overridden via env (see `.env.example`).
    """

    mongo_uri: str
    mongo_db_name: str
    mongo_max_pool_size: int = Field(default=50, ge=1, le=500)
    mongo_min_pool_size: int = Field(default=0, ge=0, le=100)
    mongo_max_idle_time_ms: int = Field(default=60_000, ge=0)
    mongo_server_selection_timeout_ms: int = Field(default=5_000, ge=100)

    redis_url: str
    use_redis: bool = False

    cors_origins: str
    cors_allow_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str = (
        "Authorization,Content-Type,Idempotency-Key,X-Request-ID,X-CSRF-Token"
    )
    cors_expose_headers: str = (
        "X-RateLimit-Limit,X-RateLimit-Remaining,X-Idempotent-Replay,X-Request-ID"
    )
    cors_max_age_seconds: int = 600

    api_prefix: str = "/api/v1"
    app_name: str = "Items API"
    app_version: str = "0.3.0"

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_export_requests: int = 10
    rate_limit_seed_requests: int = 5
    idempotency_ttl_seconds: int = 300
    export_max_rows: int = 50000

    environment: str = "development"
    allow_seed: bool = True

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "items-api"
    jwt_audience: str = "items-api-clients"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    # Concurrent page reloads can replay the previous refresh cookie briefly.
    # Within this window, return the same rotated token instead of treating it as theft.
    refresh_reuse_grace_seconds: int = Field(default=30, ge=0, le=300)

    login_max_failures: int = Field(default=5, ge=1, le=50)
    login_lockout_window_seconds: int = Field(default=900, ge=60)
    login_lockout_seconds: int = Field(default=900, ge=60)

    default_user_password: str

    trusted_proxies: str = ""

    cookie_secure: bool | None = None
    cookie_samesite: str = "lax"
    cookie_domain: str = ""
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_path: str = "/api/v1/auth"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    csrf_enabled: bool = True

    enable_security_headers: bool = True
    frame_options: str = "DENY"
    content_security_policy: str = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    referrer_policy: str = "no-referrer"
    permissions_policy: str = "camera=(), microphone=(), geolocation=()"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = value.strip() or "/api/v1"
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/api/v1"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cookie_secure_flag(self) -> bool:
        if self.is_production:
            return True
        if self.cookie_secure is not None:
            return self.cookie_secure
        return False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_methods_list(self) -> list[str]:
        return [m.strip().upper() for m in self.cors_allow_methods.split(",") if m.strip()]

    @property
    def cors_headers_list(self) -> list[str]:
        return [h.strip() for h in self.cors_allow_headers.split(",") if h.strip()]

    @property
    def cors_expose_list(self) -> list[str]:
        return [h.strip() for h in self.cors_expose_headers.split(",") if h.strip()]

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def cookie_domain_or_none(self) -> str | None:
        domain = self.cookie_domain.strip()
        return domain or None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
