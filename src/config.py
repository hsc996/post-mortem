from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET_KEYS = {
    "your_actual_secure_generated_secret_key_here",
    "changeme",
    "secret",
}

class Settings(BaseSettings):
    PROJECT_NAME: str = "PostMortem"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Database connection string
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    CORS_ORIGINS: str = ""

    # Email (invite delivery). Optional so the app still boots without it
    # configured yet — invite creation degrades to "link returned, not
    # emailed" rather than the whole service refusing to start.
    RESEND_API_KEY: str | None = None
    INVITE_FROM_EMAIL: str = "onboarding@resend.dev"
    FRONTEND_URL: str = "http://localhost:5173"
    INVITE_TTL_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        if v.lower() in PLACEHOLDER_SECRET_KEYS:
            raise ValueError("SECRET_KEY is set to a placeholder value — generate a real secret")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
