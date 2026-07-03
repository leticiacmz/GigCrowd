from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    
    APP_NAME: str
    APP_VERSION: str
    DEBUG: bool

    MONGODB_URL: str
    DATABASE_NAME: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int

    MAX_IMAGE_SIZE_MB: int
    UPLOAD_DIR: str

    CLOUDINARY_CLOUD_NAME: Optional[str]
    CLOUDINARY_API_KEY: Optional[str]
    CLOUDINARY_API_SECRET: Optional[str]

    BANDSINTOWN_APP_ID: str

    SPOTIFY_CLIENT_ID: str
    SPOTIFY_CLIENT_SECRET: str
    SPOTIFY_REDIRECT_URI: str

    CORS_ORIGINS: List[str]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()