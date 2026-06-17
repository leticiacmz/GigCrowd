from app.database.connection import get_database
from app.models.user import UserCreate, UserInDB, UserUpdate
from app.auth.security import get_password_hash, verify_password
from datetime import datetime
from bson import ObjectId
from typing import Optional


class UserService:
    @staticmethod
    async def create_user(user_data: UserCreate) -> UserInDB:
        """Create a new user"""
        db = await get_database()
        
        # Check if email already exists
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise ValueError("Email already registered")
        
        # Check if username already exists
        existing_username = await db.users.find_one({"username": user_data.username})
        if existing_username:
            raise ValueError("Username already taken")
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        user_dict = user_data.model_dump(exclude={"password"})
        user_dict["hashed_password"] = hashed_password
        user_dict["role"] = "user"
        user_dict["is_active"] = True
        user_dict["followers_count"] = 0
        user_dict["following_count"] = 0
        user_dict["created_at"] = datetime.utcnow()
        user_dict["updated_at"] = datetime.utcnow()
        
        result = await db.users.insert_one(user_dict)
        user_dict["_id"] = str(result.inserted_id)
        
        return UserInDB(**user_dict)
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
        """Get a user by ID"""
        db = await get_database()
        user = await db.users.find_one({"_id": user_id})
        if user:
            return UserInDB(**user)
        return None
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[UserInDB]:
        """Get a user by email"""
        db = await get_database()
        user = await db.users.find_one({"email": email})
        if user:
            return UserInDB(**user)
        return None
    
    @staticmethod
    async def get_user_by_username(username: str) -> Optional[UserInDB]:
        """Get a user by username"""
        db = await get_database()
        user = await db.users.find_one({"username": username})
        if user:
            return UserInDB(**user)
        return None
    
    @staticmethod
    async def update_user(user_id: str, user_data: UserUpdate) -> Optional[UserInDB]:
        """Update a user"""
        db = await get_database()
        
        update_dict = user_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await UserService.get_user_by_id(user_id)
        
        update_dict["updated_at"] = datetime.utcnow()
        
        await db.users.update_one(
            {"_id": user_id},
            {"$set": update_dict}
        )
        
        return await UserService.get_user_by_id(user_id)
    
    @staticmethod
    async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
        """Authenticate a user with email and password"""
        user = await UserService.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    @staticmethod
    async def increment_followers_count(user_id: str) -> None:
        """Increment the followers count for a user"""
        db = await get_database()
        await db.users.update_one(
            {"_id": user_id},
            {"$inc": {"followers_count": 1}}
        )
    
    @staticmethod
    async def decrement_followers_count(user_id: str) -> None:
        """Decrement the followers count for a user"""
        db = await get_database()
        await db.users.update_one(
            {"_id": user_id},
            {"$inc": {"followers_count": -1}}
        )
    
    @staticmethod
    async def increment_following_count(user_id: str) -> None:
        """Increment the following count for a user"""
        db = await get_database()
        await db.users.update_one(
            {"_id": user_id},
            {"$inc": {"following_count": 1}}
        )
    
    @staticmethod
    async def decrement_following_count(user_id: str) -> None:
        """Decrement the following count for a user"""
        db = await get_database()
        await db.users.update_one(
            {"_id": user_id},
            {"$inc": {"following_count": -1}}
        )
