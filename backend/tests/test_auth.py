from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/auth"


async def _register(
    client: AsyncClient, email: str = "user@example.com", org: str = "Acme"
) -> Response:
    return await client.post(
        f"{BASE}/register",
        json={"email": email, "password": "password123", "org_name": org},
    )


async def test_register_success(client: AsyncClient) -> None:
    resp = await _register(client, "register@example.com", "Register Org")
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == "register@example.com"
    assert body["user"]["role"] == "org_admin"


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await _register(client, "dup@example.com", "Dup Org")
    resp = await _register(client, "dup@example.com", "Another Org")
    assert resp.status_code == 409


async def test_register_password_too_short(client: AsyncClient) -> None:
    resp = await client.post(
        f"{BASE}/register",
        json={"email": "short@example.com", "password": "abc", "org_name": "Short Org"},
    )
    assert resp.status_code == 422


async def test_login_success(client: AsyncClient) -> None:
    await _register(client, "login@example.com", "Login Org")
    resp = await client.post(
        f"{BASE}/login", json={"email": "login@example.com", "password": "password123"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert "refresh_token" in resp.cookies


async def test_login_wrong_password(client: AsyncClient) -> None:
    await _register(client, "wrongpw@example.com", "WrongPw Org")
    resp = await client.post(
        f"{BASE}/login", json={"email": "wrongpw@example.com", "password": "wrongpass"}
    )
    assert resp.status_code == 401


async def test_login_unknown_email(client: AsyncClient) -> None:
    resp = await client.post(
        f"{BASE}/login", json={"email": "nobody@example.com", "password": "password123"}
    )
    assert resp.status_code == 401


async def test_protected_without_token(client: AsyncClient) -> None:

    # Use /api/v1/health as a sanity check and test an inline protected route
    # We verify the dependency raises 401 by hitting refresh without a cookie
    resp = await client.post(f"{BASE}/refresh")
    assert resp.status_code == 401


async def test_refresh_token_rotation(client: AsyncClient) -> None:
    await _register(client, "refresh@example.com", "Refresh Org")
    login_resp = await client.post(
        f"{BASE}/login", json={"email": "refresh@example.com", "password": "password123"}
    )
    refresh_cookie = login_resp.cookies["refresh_token"]

    refresh_resp = await client.post(f"{BASE}/refresh", cookies={"refresh_token": refresh_cookie})
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]
    assert new_token != login_resp.json()["access_token"]

    # Old refresh token must be rejected
    second_refresh = await client.post(f"{BASE}/refresh", cookies={"refresh_token": refresh_cookie})
    assert second_refresh.status_code == 401


async def test_logout(client: AsyncClient) -> None:
    await _register(client, "logout@example.com", "Logout Org")
    login_resp = await client.post(
        f"{BASE}/login", json={"email": "logout@example.com", "password": "password123"}
    )
    refresh_cookie = login_resp.cookies["refresh_token"]

    logout_resp = await client.post(f"{BASE}/logout", cookies={"refresh_token": refresh_cookie})
    assert logout_resp.status_code == 204

    # Token should be revoked
    refresh_resp = await client.post(f"{BASE}/refresh", cookies={"refresh_token": refresh_cookie})
    assert refresh_resp.status_code == 401


async def test_password_reset_flow(client: AsyncClient) -> None:
    await _register(client, "reset@example.com", "Reset Org")

    # Request always returns 200 (enumeration prevention)
    resp = await client.post(f"{BASE}/password-reset/request", json={"email": "reset@example.com"})
    assert resp.status_code == 200

    resp_unknown = await client.post(
        f"{BASE}/password-reset/request", json={"email": "unknown@example.com"}
    )
    assert resp_unknown.status_code == 200


async def test_password_reset_confirm_invalid_otp(client: AsyncClient) -> None:
    await _register(client, "resetbad@example.com", "ResetBad Org")
    resp = await client.post(
        f"{BASE}/password-reset/confirm",
        json={"email": "resetbad@example.com", "otp": "000000", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


async def test_expired_token_returns_401(client: AsyncClient) -> None:
    from jose import jwt as jose_jwt

    from backend.core.config import settings

    payload = {
        "sub": "fake-id",
        "org_id": "fake-org",
        "role": "org_admin",
        "exp": datetime.now(UTC) - timedelta(minutes=1),
        "type": "access",
    }
    expired_token = jose_jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    resp = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


async def test_viewer_role_returns_403_on_admin_endpoint(client: AsyncClient) -> None:
    from backend.auth.jwt import create_access_token
    from backend.auth.password import hash_password
    from backend.repositories.user_repo import create_user

    # Register an org first to get a valid org_id
    reg = await _register(client, "owner@viewer-test.com", "Viewer Test Org")
    owner_data = reg.json()
    org_id = owner_data["user"]["org_id"]

    # Create a viewer user directly in the DB via the test session
    from backend.tests.conftest import TestSessionLocal

    async with TestSessionLocal() as db:
        import uuid

        viewer = await create_user(
            db,
            email="viewer@viewer-test.com",
            hashed_pw=hash_password("password123"),
            org_id=uuid.UUID(org_id),
            role="viewer",
        )
        await db.commit()
        viewer_id = str(viewer.id)

    viewer_token = create_access_token(user_id=viewer_id, org_id=org_id, role="viewer")
    resp = await client.get(
        f"{BASE}/admin-only", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_cross_tenant_isolation(client: AsyncClient) -> None:
    from backend.auth.jwt import create_access_token

    # Register two separate orgs
    reg_a = await _register(client, "user@org-a.com", "Org A")
    reg_b = await _register(client, "user@org-b.com", "Org B")

    token_a = reg_a.json()["access_token"]
    org_id_b = reg_b.json()["user"]["org_id"]

    # user from org A uses their own token — should see their own profile
    me_a = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.status_code == 200
    assert me_a.json()["org_id"] != org_id_b

    # Forged token claiming org_b membership but with wrong user_id should not resolve
    import uuid

    forged = create_access_token(user_id=str(uuid.uuid4()), org_id=org_id_b, role="org_admin")
    resp = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
