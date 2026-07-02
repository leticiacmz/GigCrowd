from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "GigCrowd API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "gigcrowd"
    
    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Media Upload (Images only for MongoDB Atlas optimization)
    MAX_IMAGE_SIZE_MB: int = 2  # Reduced for production
    UPLOAD_DIR: str = "uploads"
    
    # Cloudinary (External image storage - saves MongoDB space)
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    
    # External APIs
    BANDSINTOWN_APP_ID: Optional[str] = None
    SETLIST_FM_API_KEY: Optional[str] = None
    TICKETMASTER_CONSUMER_KEY: Optional[str] = None
    TICKETMASTER_CONSUMER_SECRET: Optional[str] = None
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_SECRET: Optional[str] = None
    
    # Cache Configuration
    CACHE_TTL_SECONDS: int = 604800  # 7 days for cached events
    
    # CORS
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:8000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
