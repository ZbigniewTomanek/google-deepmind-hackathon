from pydantic_settings import BaseSettings


class PostgresConfig(BaseSettings):
    """PostgreSQL connection configuration."""

    model_config = {"env_prefix": "POSTGRES_", "env_file": ".env", "env_file_encoding": "utf-8"}

    host: str = "localhost"
    port: int = 5432
    user: str = "neocortex"
    password: str = "neocortex"
    database: str = "neocortex"
    min_pool_size: int = 2
    max_pool_size: int = 10

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
