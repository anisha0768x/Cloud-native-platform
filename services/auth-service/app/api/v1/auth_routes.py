import uuid

from fastapi import APIRouter, Depends, status

from platform_common.exceptions import NotFoundError
from platform_common.security import TokenPayload

from app.core.dependencies import get_auth_service, get_current_user_token, get_user_repository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, auth_service: AuthService = Depends(get_auth_service)):
    user = await auth_service.register(email=body.email, password=body.password, full_name=body.full_name)
    return AuthService.to_user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, auth_service: AuthService = Depends(get_auth_service)):
    _, tokens = await auth_service.login(email=body.email, password=body.password)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)):
    return await auth_service.refresh(raw_refresh_token=body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, auth_service: AuthService = Depends(get_auth_service)):
    await auth_service.logout(raw_refresh_token=body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(
    token: TokenPayload = Depends(get_current_user_token),
    user_repo: UserRepository = Depends(get_user_repository),
):
    user = await user_repo.get_by_id(uuid.UUID(token.sub))
    if user is None:
        raise NotFoundError("User not found")
    return AuthService.to_user_response(user)
