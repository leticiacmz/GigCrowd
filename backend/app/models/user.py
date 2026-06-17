from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30)
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None


class UserInDB(UserBase):
    id: str = Field(alias="_id")
    hashed_password: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    followers_count: int = 0
    following_count: int = 0
    shows_attended: int = 0  # Total shows attended
    artists_seen: list = []  # List of artist IDs seen
    favorite_genres: list = []  # List of favorite music genres
    favorite_artists: list = []  # List of favorite artist IDs
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None
    role: UserRole
    followers_count: int
    following_count: int
    shows_attended: int
    artists_seen: list
    favorite_genres: list
    favorite_artists: list
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
