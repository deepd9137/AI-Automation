import re
from datetime import UTC, datetime, timedelta

import resend
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt import create_access_token, create_refresh_token, decode_token
from backend.auth.password import generate_otp, hash_password, hash_token, verify_password
from backend.core.config import settings
from backend.models.user import User
from backend.repositories import user_repo
from backend.schemas.auth import RegisterRequest


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:100]


async def register(db: AsyncSession, data: RegisterRequest) -> tuple[str, User]:
    existing = await user_repo.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    base_slug = _slugify(data.org_name)
    slug = base_slug
    counter = 1
    while await user_repo.get_org_by_slug(db, slug):
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = await user_repo.create_organization(db, name=data.org_name, slug=slug)
    hashed = hash_password(data.password)
    user = await user_repo.create_user(db, email=data.email, hashed_pw=hashed, org_id=org.id)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(
        user_id=str(user.id), org_id=str(user.org_id), role=user.role
    )
    return access_token, user


async def login(db: AsyncSession, email: str, password: str) -> tuple[str, str, User]:
    user = await user_repo.get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_pw):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account inactive")

    access_token = create_access_token(
        user_id=str(user.id), org_id=str(user.org_id), role=user.role
    )
    raw_refresh = create_refresh_token(user_id=str(user.id))
    token_hash = hash_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await user_repo.create_refresh_token(
        db, user_id=user.id, token_hash=token_hash, expires_at=expires_at
    )
    await db.commit()

    return access_token, raw_refresh, user


async def refresh_tokens(db: AsyncSession, raw_refresh: str) -> tuple[str, str]:
    try:
        payload = decode_token(raw_refresh)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    token_hash = hash_token(raw_refresh)
    stored = await user_repo.get_refresh_token_by_hash(db, token_hash)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired"
        )

    user = await user_repo.get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    await user_repo.revoke_refresh_token(db, token_hash)

    new_access = create_access_token(user_id=str(user.id), org_id=str(user.org_id), role=user.role)
    new_raw_refresh = create_refresh_token(user_id=str(user.id))
    new_hash = hash_token(new_raw_refresh)
    new_expires = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await user_repo.create_refresh_token(
        db, user_id=user.id, token_hash=new_hash, expires_at=new_expires
    )
    await db.commit()

    return new_access, new_raw_refresh


async def logout(db: AsyncSession, raw_refresh: str) -> None:
    token_hash = hash_token(raw_refresh)
    await user_repo.revoke_refresh_token(db, token_hash)
    await db.commit()


async def request_password_reset(db: AsyncSession, email: str) -> None:
    user = await user_repo.get_user_by_email(db, email)
    if not user:
        return  # prevent enumeration

    otp = generate_otp()
    otp_hash = hash_token(otp)
    expires_at = datetime.now(UTC) + timedelta(minutes=15)

    await user_repo.create_password_reset_otp(
        db, user_id=user.id, otp_hash=otp_hash, expires_at=expires_at
    )
    await db.commit()

    if settings.RESEND_API_KEY:
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send(
            {
                "from": settings.EMAIL_FROM,
                "to": email,
                "subject": "Your password reset code",
                "text": (
                    f"Your one-time password reset code is: {otp}\n\n"
                    "This code expires in 15 minutes."
                ),
            }
        )


async def confirm_password_reset(db: AsyncSession, email: str, otp: str, new_password: str) -> None:
    user = await user_repo.get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code"
        )

    otp_hash = hash_token(otp)
    stored_otp = await user_repo.get_valid_otp(db, user_id=user.id, otp_hash=otp_hash)
    if not stored_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code"
        )

    await user_repo.mark_otp_used(db, stored_otp)
    await user_repo.update_user_password(db, user, hash_password(new_password))
    await user_repo.revoke_all_user_refresh_tokens(db, user.id)
    await db.commit()
