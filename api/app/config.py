import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Kapita Distributed ML API"
    APP_ENV: str = "production"
    API_V1_PREFIX: str = "/api/v1"

    # Database Configuration (CQRS / Read-Write Separation)
    # Primary Node for Write operations (INSERT, UPDATE, DELETE)
    DB_PRIMARY_HOST: str = os.getenv("DB_PRIMARY_HOST", "postgres-primary")
    DB_PRIMARY_PORT: int = int(os.getenv("DB_PRIMARY_PORT", "5432"))
    DB_PRIMARY_USER: str = os.getenv("DB_PRIMARY_USER", "app_user")
    DB_PRIMARY_PASSWORD: str = os.getenv("DB_PRIMARY_PASSWORD", "app_password")
    DB_PRIMARY_NAME: str = os.getenv("DB_PRIMARY_NAME", "app_db")

    # Read-Replica Node for Read operations (SELECT)
    DB_REPLICA_HOST: str = os.getenv("DB_REPLICA_HOST", "postgres-replica")
    DB_REPLICA_PORT: int = int(os.getenv("DB_REPLICA_PORT", "5432"))
    DB_REPLICA_USER: str = os.getenv("DB_REPLICA_USER", "app_user")
    DB_REPLICA_PASSWORD: str = os.getenv("DB_REPLICA_PASSWORD", "app_password")
    DB_REPLICA_NAME: str = os.getenv("DB_REPLICA_NAME", "app_db")

    # Identity Provider / SSO (Keycloak)
    KEYCLOAK_INTERNAL_URL: str = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")
    KEYCLOAK_EXTERNAL_URL: str = os.getenv("KEYCLOAK_EXTERNAL_URL", "http://localhost:8080")
    KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", "kapita-realm")
    KEYCLOAK_CLIENT_ID: str = os.getenv("KEYCLOAK_CLIENT_ID", "api-client")
    KEYCLOAK_CLIENT_SECRET: str = os.getenv("KEYCLOAK_CLIENT_SECRET", "api-client-secret-12345")

    # Machine Learning Model
    MODEL_PATH: str = os.getenv("MODEL_PATH", "model/model.joblib")

    @property
    def primary_db_url(self) -> str:
        return f"postgresql+psycopg2://{self.DB_PRIMARY_USER}:{self.DB_PRIMARY_PASSWORD}@{self.DB_PRIMARY_HOST}:{self.DB_PRIMARY_PORT}/{self.DB_PRIMARY_NAME}"

    @property
    def replica_db_url(self) -> str:
        return f"postgresql+psycopg2://{self.DB_REPLICA_USER}:{self.DB_REPLICA_PASSWORD}@{self.DB_REPLICA_HOST}:{self.DB_REPLICA_PORT}/{self.DB_REPLICA_NAME}"

    @property
    def keycloak_issuer_internal(self) -> str:
        return f"{self.KEYCLOAK_INTERNAL_URL}/realms/{self.KEYCLOAK_REALM}"

    @property
    def keycloak_issuer_external(self) -> str:
        return f"{self.KEYCLOAK_EXTERNAL_URL}/realms/{self.KEYCLOAK_REALM}"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.KEYCLOAK_INTERNAL_URL}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect/certs"

    @property
    def keycloak_token_url(self) -> str:
        return f"{self.KEYCLOAK_INTERNAL_URL}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect/token"

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

