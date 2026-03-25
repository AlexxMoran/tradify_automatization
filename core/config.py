from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8080, alias="PORT")
    api_key: str = Field(default="", alias="API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")
    description_generation_mode: str = Field(
        default="hybrid",
        alias="DESCRIPTION_GENERATION_MODE",
    )
    baselinker_api_token: str = Field(default="", alias="BASELINKER_API_TOKEN")
    baselinker_api_url: str = Field(
        default="https://api.baselinker.com/connector.php",
        alias="BASELINKER_API_URL",
    )
    baselinker_timeout_seconds: float = Field(
        default=30.0,
        alias="BASELINKER_TIMEOUT_SECONDS",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
