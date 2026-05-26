from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str
    webhook_secret: str = ""
    webhook_domain: str = ""

    # AI
    anthropic_api_key: str
    openai_api_key: str

    # Database
    postgres_dsn: str

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Security
    encryption_key: str

    # App
    environment: str = "local"
    allowed_user_ids: list[int] = []

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_user_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        return v

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @property
    def webhook_url(self) -> str:
        return f"https://{self.webhook_domain}/webhook/{self.webhook_secret}"


settings = Settings()  # type: ignore[call-arg]
