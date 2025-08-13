from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "UPS Dashboard API" 
    SQLALCHEMY_DATABASE_URL: str
    VERSION: str = "1.0.0"  
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 5 
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
