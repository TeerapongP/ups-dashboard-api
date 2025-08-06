from pydantic import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 *5 # Default to 5 hours
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"

settings = Settings()
