from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: str = "app/attendance.db"
    matching_threshold: float = 0.65
    cors_origins: list[str] = ["*"]

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 1440

    open_enrollment: bool = True
    admin_recovery_key: str = "NCST-SECURE-RESET-2026"


settings = Settings()
