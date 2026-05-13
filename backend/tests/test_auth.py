import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/auth"


async def _register(  # type: ignore[return]
    client: AsyncClient, email: str = "user@example.com", org: str = "Acme"
) -> dict:  # type: ignore[type-arg]
    resp = await client.post(
        f"{BASE}/register",
        json={"email": email, "password": "password123", "org_name": org},
    )
    return resp


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

    refresh_resp = await client.post(
        f"{BASE}/refresh", cookies={"refresh_token": refresh_cookie}
    )
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]
    assert new_token != login_resp.json()["access_token"]

    # Old refresh token must be rejected
    second_refresh = await client.post(
        f"{BASE}/refresh", cookies={"refresh_token": refresh_cookie}
    )
    assert second_refresh.status_code == 401


async def test_logout(client: AsyncClient) -> None:
    await _register(client, "logout@example.com", "Logout Org")
    login_resp = await client.post(
        f"{BASE}/login", json={"email": "logout@example.com", "password": "password123"}
    )
    refresh_cookie = login_resp.cookies["refresh_token"]

    logout_resp = await client.post(
        f"{BASE}/logout", cookies={"refresh_token": refresh_cookie}
    )
    assert logout_resp.status_code == 204

    # Token should be revoked
    refresh_resp = await client.post(
        f"{BASE}/refresh", cookies={"refresh_token": refresh_cookie}
    )
    assert refresh_resp.status_code == 401


async def test_password_reset_flow(client: AsyncClient) -> None:
    await _register(client, "reset@example.com", "Reset Org")

    # Request always returns 200 (enumeration prevention)
    resp = await client.post(
        f"{BASE}/password-reset/request", json={"email": "reset@example.com"}
    )
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
