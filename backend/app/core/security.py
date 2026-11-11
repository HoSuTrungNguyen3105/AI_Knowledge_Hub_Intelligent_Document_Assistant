import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.core.config import Settings
from app.models.base import utcnow

ACCESS_COOKIE = "kh_access"
REFRESH_COOKIE = "kh_refresh"
ACCESS_PATH = "/api/v1"
REFRESH_PATH = "/api/v1/auth"
JWT_ISSUER = "knowledge-hub"
JWT_AUDIENCE = "knowledge-hub-api"
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: UUID, session_id: UUID, settings: Settings) -> str:
    now = utcnow()
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": secrets.token_hex(16),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(
    token: str, settings: Settings, *, allow_expired: bool = False
) -> tuple[UUID, UUID] | None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={
                "require": ["sub", "sid", "type", "iat", "exp", "iss", "aud", "jti"],
                "verify_exp": not allow_expired,
            },
        )
        if claims["type"] != "access":
            return None
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        return None


def set_auth_cookies(response: Response, access: str, refresh: str, settings: Settings) -> None:
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        path=ACCESS_PATH,
        max_age=settings.access_token_minutes * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        path=REFRESH_PATH,
        max_age=settings.refresh_token_days * 86400,
        **common,
    )
    response.headers["Cache-Control"] = "no-store"


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name, path in [(ACCESS_COOKIE, ACCESS_PATH), (REFRESH_COOKIE, REFRESH_PATH)]:
        response.delete_cookie(
            name, path=path, httponly=True, secure=settings.cookie_secure, samesite="lax"
        )
    response.headers["Cache-Control"] = "no-store"
