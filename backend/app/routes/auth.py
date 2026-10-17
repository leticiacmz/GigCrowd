from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import UserCreate, UserResponse
from app.services.user_service import UserService
from fastapi.security import OAuth2PasswordRequestForm
from app.auth.security import create_access_token
from datetime import timedelta
from app.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Create the account and sign the new user in.

    The answer is the same session shape `/auth/login` returns - one access
    token and the user it belongs to - because registering already means the
    person is signed in. It used to answer with the bare user, and a client
    storing that as a session had no token to store: the account was created,
    the response looked successful, and the visitor arrived signed out at the
    page the form sent them to. The token is minted by the same helper login
    uses; there is no second token mechanism here.
    """
    try:
        user = await UserService.create_user(user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    access_token_expires = timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse(
            **user.model_dump()
        )
    }


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends()
):

    user = await UserService.authenticate_user(
        form_data.username,
        form_data.password
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )

    access_token_expires = timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse(
            **user.model_dump()
        )
    }