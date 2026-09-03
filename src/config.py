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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

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


settings = Settings()
