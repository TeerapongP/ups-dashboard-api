from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "UPS Dashboard API"
    SQLALCHEMY_DATABASE_URL: str
    VERSION: str = "1.0.0"
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
