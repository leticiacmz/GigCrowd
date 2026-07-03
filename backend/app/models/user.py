from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


# =========================================================
# BASE (auth + profile juntos)
# =========================================================
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30)

    # --- profile fields ---
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None


# =========================================================
# CREATE
# =========================================================
class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        return value


# =========================================================
# UPDATE (perfil editável)
# =========================================================
class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None


# =========================================================
# DB MODEL
# =========================================================
class UserInDB(UserBase):
    id: str = Field(alias="_id")
    hashed_password: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# =========================================================
# RESPONSE (o que vai pro frontend)
# =========================================================
class UserResponse(UserBase):
    id: str
    role: UserRole
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True