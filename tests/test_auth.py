import hashlib
import hmac

from auth_utils import (
    check_auth_date,
    create_jwt,
    decode_jwt,
    is_jwt_secret_configured,
    verify_telegram_hash,
)


def test_rejects_missing_and_placeholder_jwt_secrets():
    assert is_jwt_secret_configured(None) is False
    assert is_jwt_secret_configured("") is False
    assert is_jwt_secret_configured("secret") is False
    assert is_jwt_secret_configured("замени_на_случайную_строку_из_64_символов") is False
    assert is_jwt_secret_configured("short") is False
    assert is_jwt_secret_configured("a" * 32) is True


def test_telegram_hash_roundtrip():
    token = "123456:ABC"
    payload = {"id": 7, "first_name": "Vasya", "auth_date": 1_700_000_000}
    check = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    digest = hmac.new(hashlib.sha256(token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    assert verify_telegram_hash({**payload, "hash": digest}, token) is True
    assert verify_telegram_hash({**payload, "hash": "deadbeef"}, token) is False
    assert verify_telegram_hash({**payload, "hash": digest}, "") is False


def test_auth_date_window():
    now = 1_700_000_100
    assert check_auth_date(1_700_000_000, now=now) is True
    assert check_auth_date(1_699_000_000, now=now) is False
    assert check_auth_date("bad", now=now) is False


def test_jwt_roundtrip_and_wrong_secret():
    secret = "a" * 32
    token = create_jwt({"id": 42, "first_name": "Ada", "username": "ada"}, secret)
    payload = decode_jwt(token, secret)
    assert payload["sub"] == "42"
    assert payload["first_name"] == "Ada"
    assert decode_jwt(token, "b" * 32) is None
    assert decode_jwt("not-a-jwt", secret) is None
