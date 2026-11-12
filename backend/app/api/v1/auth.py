from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, response: Response, db: Database, settings: AppSettings
) -> AuthResponse:
    result = await AuthService(db, settings).register(payload)
    set_auth_cookies(response, result.access_token, result.refresh_token, settings)
    return AuthResponse(user=UserResponse.model_validate(result.user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest, response: Response, db: Database, settings: AppSettings
) -> AuthResponse:
    result = await AuthService(db, settings).login(payload)
    set_auth_cookies(response, result.access_token, result.refresh_token, settings)
    return AuthResponse(user=UserResponse.model_validate(result.user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request, response: Response, db: Database, settings: AppSettings
) -> AuthResponse:
    result = await AuthService(db, settings).refresh(request.cookies.get(REFRESH_COOKIE))
    set_auth_cookies(response, result.access_token, result.refresh_token, settings)
    return AuthResponse(user=UserResponse.model_validate(result.user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: Database, settings: AppSettings) -> Response:
    await AuthService(db, settings).logout(
        request.cookies.get(ACCESS_COOKIE), request.cookies.get(REFRESH_COOKIE)
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)