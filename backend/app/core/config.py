from pydantic import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "GigCrowd"

    MONGODB_URL: str
    DATABASE_NAME: str

    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REDIRECT_URI: str = ""

    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()