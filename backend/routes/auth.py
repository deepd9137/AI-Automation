from backend.database.session import get_db
from backend.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmBody,
    PasswordResetRequestBody,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserOut,
)
from backend.services import auth_service
from fastapi import APIRouter, Cookie, Depends, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

REFRESH_COOKIE = "refresh_token"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days in seconds


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    access_token, user = await auth_service.register(db, request)
    return RegisterResponse(
        access_token=access_token,
        user=UserOut(
            id=str(user.id),
            email=user.email,
            role=user.role,
            org_id=str(user.org_id),
        ),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    access_token, raw_refresh, _ = await auth_service.login(db, request.email, request.password)
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_refresh,
        httponly=True,
        samesite="strict",
        secure=True,
        max_age=COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    from fastapi import HTTPException

    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    new_access, new_refresh = await auth_service.refresh_tokens(db, refresh_token)
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=new_refresh,
        httponly=True,
        samesite="strict",
        secure=True,
        max_age=COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )
    return TokenResponse(access_token=new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> None:
    if refresh_token:
        await auth_service.logout(db, refresh_token)
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/password-reset/request", status_code=status.HTTP_200_OK)
async def password_reset_request(
    body: PasswordResetRequestBody,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await auth_service.request_password_reset(db, body.email)
    return {"message": "If that email is registered, a reset code has been sent."}


@router.post("/password-reset/confirm", status_code=status.HTTP_200_OK)
async def password_reset_confirm(
    body: PasswordResetConfirmBody,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await auth_service.confirm_password_reset(db, body.email, body.otp, body.new_password)
    return {"message": "Password updated successfully."}
