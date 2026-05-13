import uuid
from datetime import UTC, datetime

from backend.models.organization import Organization
from backend.models.token import PasswordResetOtp, RefreshToken
from backend.models.user import User
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email, User.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_org_by_slug(db: AsyncSession, slug: str) -> Organization | None:
    result = await db.execute(
        select(Organization).where(Organization.slug == slug, Organization.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def create_organization(db: AsyncSession, name: str, slug: str) -> Organization:
    org = Organization(name=name, slug=slug)
    db.add(org)
    await db.flush()
    return org


async def create_user(
    db: AsyncSession, email: str, hashed_pw: str, org_id: uuid.UUID, role: str = "org_admin"
) -> User:
    user = User(email=email, hashed_pw=hashed_pw, org_id=org_id, role=role)
    db.add(user)
    await db.flush()
    return user


async def create_refresh_token(
    db: AsyncSession, user_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> RefreshToken:
    rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(rt)
    await db.flush()
    return rt


async def get_refresh_token_by_hash(db: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token_hash: str) -> None:
    await db.execute(
        update(RefreshToken).where(RefreshToken.token_hash == token_hash).values(revoked=True)
    )


async def revoke_all_user_refresh_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )


async def create_password_reset_otp(
    db: AsyncSession, user_id: uuid.UUID, otp_hash: str, expires_at: datetime
) -> PasswordResetOtp:
    otp = PasswordResetOtp(user_id=user_id, otp_hash=otp_hash, expires_at=expires_at)
    db.add(otp)
    await db.flush()
    return otp


async def get_valid_otp(
    db: AsyncSession, user_id: uuid.UUID, otp_hash: str
) -> PasswordResetOtp | None:
    result = await db.execute(
        select(PasswordResetOtp).where(
            PasswordResetOtp.user_id == user_id,
            PasswordResetOtp.otp_hash == otp_hash,
            PasswordResetOtp.used.is_(False),
            PasswordResetOtp.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def mark_otp_used(db: AsyncSession, otp: PasswordResetOtp) -> None:
    otp.used = True
    await db.flush()


async def update_user_password(db: AsyncSession, user: User, hashed_pw: str) -> None:
    user.hashed_pw = hashed_pw
    await db.flush()
