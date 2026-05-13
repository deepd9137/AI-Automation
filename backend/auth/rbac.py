from backend.auth.dependencies import get_current_user
from backend.models.user import User
from fastapi import Depends, HTTPException, status

ROLE_HIERARCHY = ["viewer", "agent", "org_admin", "super_admin"]


def require_role(*roles: str):  # type: ignore[no-untyped-def]
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return checker
