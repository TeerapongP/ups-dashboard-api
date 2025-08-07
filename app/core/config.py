from pydantic import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 5 
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"


settings = Settings()
