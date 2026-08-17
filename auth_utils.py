"""JWT and Telegram Login Widget verification — no silent weak secrets."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
AUTH_COOKIE = "cn21_session"

WEAK_JWT_SECRETS = {
    "",
    "замени_на_случайную_строку_из_64_символов",
    "change-me",
    "changeme",
    "secret",
    "jwt_secret",
    "your-secret",
}


def is_jwt_secret_configured(secret: Optional[str]) -> bool:
    if secret is None:
        return False
    value = secret.strip()
    if value in WEAK_JWT_SECRETS:
        return False
    return len(value) >= 32


def verify_telegram_hash(data: dict[str, Any], bot_token: str) -> bool:
    """Telegram Login Widget HMAC-SHA256 check from the official docs."""
    if not bot_token:
        return False
    received_hash = str(data.get("hash") or "")
    if not received_hash:
        return False
    check_data = {k: v for k, v in data.items() if k != "hash" and v is not None}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_hash, received_hash)


def check_auth_date(auth_date: int, max_age: int = 86400, now: Optional[int] = None) -> bool:
    current = now if now is not None else int(datetime.now(timezone.utc).timestamp())
    try:
        issued = int(auth_date)
    except (TypeError, ValueError):
        return False
    return 0 <= (current - issued) <= max_age


def create_jwt(user: dict[str, Any], secret: str) -> str:
    if not is_jwt_secret_configured(secret):
        raise RuntimeError("JWT_SECRET is missing or too weak")
    payload = {
        "sub": str(user["id"]),
        "first_name": user.get("first_name") or "",
        "last_name": user.get("last_name") or "",
        "username": user.get("username") or "",
        "photo_url": user.get("photo_url") or "",
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str, secret: str) -> Optional[dict[str, Any]]:
    if not token or not is_jwt_secret_configured(secret):
        return None
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
