from pydantic import SecretStr
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables when available."""

    app_name: str = "Morshidi API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    frontend_url: str = "http://localhost:3000"
    supabase_url: str | None = None
    supabase_secret_key: SecretStr | None = None
    advisor_llm_api_key: SecretStr | None = None
    advisor_llm_model: str | None = None
    policy_embedding_api_key: SecretStr | None = None
    policy_embedding_model: str = "text-embedding-3-large"
    policy_embedding_dimensions: int = 1536
    mock_registration_minimum_disclosure_group_size: int = 3
    mock_registration_max_intents: int = 1000
    mock_registration_max_catalog_courses: int = 10000
    academic_compute_max_concurrent: int = Field(default=1, ge=1, le=4)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
