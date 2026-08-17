import hashlib
import hmac
from datetime import datetime, timezone

import api_server
from auth_utils import AUTH_COOKIE, create_jwt


def _tg_payload(token: str) -> dict:
    payload = {
        "id": 77,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "username": "ada",
        "auth_date": int(datetime.now(timezone.utc).timestamp()),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    digest = hmac.new(hashlib.sha256(token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    payload["hash"] = digest
    return payload


def test_health_and_sources_are_honest(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["cached_vacancies"] == 0
    assert "llm" in health
    sources = client.get("/api/sources").json()
    names = {row["name"] for row in sources["sources"]}
    assert names == {"hh.ru", "@kazanit", "@it_tatarstan", "@innopolis_live", "@school21_kazan"}
    assert sources["count"] == 5


def test_vacancies_and_news_do_not_use_static_fallback(client):
    vacs = client.get("/api/live-vacancies").json()
    news = client.get("/api/live-news").json()
    stats = client.get("/api/stats").json()
    assert vacs["vacancies"] == []
    assert vacs["source"] in {"empty", "live"}
    assert news["news"] == []
    assert "KazanExpress" not in str(vacs)
    assert "Digital Tatarstan 2026" not in str(news)
    assert stats["total_vacancies"] == 0
    assert stats["total_sources"] == 5


def test_live_vacancies_return_cache_only(client):
    api_server._cache["vacancies"] = [
        {"id": "hh_1", "title": "Junior Go", "company": "ICL", "category": "vacancy", "role": "backend", "format": "remote", "tags": ["go"]},
        {"id": "hh_2", "title": "QA intern", "company": "X", "category": "internship", "role": "qa", "format": "office", "tags": []},
    ]
    api_server._cache["last_update"] = datetime.now(timezone.utc)
    data = client.get("/api/live-vacancies", params={"role": "backend"}).json()
    assert data["total"] == 1
    assert data["vacancies"][0]["title"] == "Junior Go"
    assert data["source"] == "live"


def test_ai_disabled_is_503_not_fake_advice(client):
    status = client.get("/api/ai/status").json()
    assert status["enabled"] is False
    advice = client.post("/api/ai/career-advice", json={"role": "backend"})
    assert advice.status_code == 503
    assert advice.json()["advice"] is None
    agent = client.post("/api/ai/agent-advice", json={"role": "backend"})
    assert agent.status_code == 503
    assert agent.json()["vacancies"] == []


def test_digest_requires_auth(client):
    denied = client.post("/api/digest/settings", json={"schedule": "daily", "time": "09:00", "roles": ["backend"]})
    assert denied.status_code == 401


def test_telegram_auth_sets_cookie_on_returned_response(client, monkeypatch):
    token = "123456:TESTTOKEN"
    monkeypatch.setattr(api_server, "BOT_TOKEN", token)
    monkeypatch.setattr(api_server, "JWT_SECRET", "ci-test-secret-please-use-32chars!")
    response = client.post("/api/auth/telegram", json=_tg_payload(token))
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert AUTH_COOKIE in response.cookies
    me = client.get("/api/auth/me")
    assert me.json()["authenticated"] is True
    assert me.json()["user"]["first_name"] == "Ada"


def test_weak_jwt_blocks_auth(client, monkeypatch):
    monkeypatch.setattr(api_server, "BOT_TOKEN", "123456:TESTTOKEN")
    monkeypatch.setattr(api_server, "JWT_SECRET", "замени_на_случайную_строку_из_64_символов")
    response = client.post("/api/auth/telegram", json=_tg_payload("123456:TESTTOKEN"))
    assert response.status_code == 503


def test_digest_preview_from_live_cache(client):
    api_server._cache["vacancies"] = [
        {"title": "Junior Python", "company": "ICL", "role": "backend", "url": "https://hh.ru/vacancy/1"}
    ]
    preview = client.get("/api/digest/preview", params={"roles": "backend"}).json()
    assert preview["digest"]["vacancies"][0]["title"] == "Junior Python"
    assert "Junior Python" in preview["text"]


def test_digest_save_and_send_honest_errors(client, monkeypatch):
    secret = "ci-test-secret-please-use-32chars!"
    monkeypatch.setattr(api_server, "JWT_SECRET", secret)
    token = create_jwt({"id": 77, "first_name": "Ada"}, secret)
    client.cookies.set(AUTH_COOKIE, token)

    no_bot = client.post("/api/digest/settings", json={"schedule": "daily", "time": "09:00", "roles": ["backend"]})
    assert no_bot.status_code == 503

    monkeypatch.setattr(api_server.digest_telegram, "is_configured", lambda: True)
    saved = client.post("/api/digest/settings", json={"schedule": "daily", "time": "09:00", "roles": ["backend"]})
    assert saved.status_code == 200
    assert saved.json()["success"] is True

    async def fake_send(chat_id, text):
        assert chat_id == 77
        assert "Junior" in text or "нет" in text.lower()
        return {"ok": False, "error": "chat not found. Напишите боту /start"}

    monkeypatch.setattr(api_server.digest_telegram, "send_message", fake_send)
    sent = client.post("/api/digest/send")
    assert sent.status_code == 502
    assert "start" in sent.json()["error"].lower()


def test_no_fake_register_endpoint(client):
    response = client.post("/api/register", json={"name": "x", "email": "a@b.c", "password": "p"})
    assert response.status_code in {404, 405}
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("success") is not True
