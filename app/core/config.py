from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_documents: str = "documents"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # Caching
    cache_ttl_seconds: int = 30
    rate_limit_requests: int = 60  # per tenant per minute

    # App
    app_env: str = "development"
    debug: bool = False


settings = Settings()
