from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

# Scheme that doesn't raise an error when no token is provided
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False
)


async def get_current_user(
    token: str = Depends(oauth2_scheme)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = await UserService.get_user_by_id(user_id)

    if not user:
        raise credentials_exception

    user_dict = user.model_dump(by_alias=True)
    # Ensure both 'id' and '_id' are present for compatibility
    if '_id' in user_dict and 'id' not in user_dict:
        user_dict['id'] = user_dict['_id']
    return user_dict


async def get_current_active_user(
    current_user=Depends(get_current_user)
):
    if current_user.get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return current_user


async def get_optional_user(
    token: str = Depends(oauth2_scheme_optional)
):
    """
    Get the current user if authenticated, otherwise return None.
    Used for endpoints that allow both authenticated and unauthenticated access.
    """
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:
            return None

    except JWTError:
        return None

    user = await UserService.get_user_by_id(user_id)

    if not user:
        return None

    user_dict = user.model_dump(by_alias=True)
    # Ensure both 'id' and '_id' are present for compatibility
    if '_id' in user_dict and 'id' not in user_dict:
        user_dict['id'] = user_dict['_id']
    return user_dict