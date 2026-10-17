from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="backend/.env", extra="ignore")

    supabase_url: str
    supabase_service_role_key: SecretStr
    twilio_account_sid: str
    twilio_auth_token: SecretStr
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_webhook_url: str
    twilio_morning_content_sid: str = ""
    twilio_evening_content_sid: str = ""
    ai_base_url: str = ""
    ai_service_token: SecretStr = SecretStr("")
    worker_poll_seconds: float = Field(default=5, ge=1, le=60)

    @field_validator("supabase_url", "twilio_webhook_url")
    @classmethod
    def https_url(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("A public HTTPS URL is required")
        return value

    @field_validator("supabase_service_role_key", "twilio_auth_token")
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("A nonempty credential is required")
        return value
