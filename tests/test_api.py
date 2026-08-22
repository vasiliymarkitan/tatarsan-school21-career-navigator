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
    assert names == {
        "hh.ru",
        "Yandex Search → hh.ru",
        "@kazanit",
        "@it_tatarstan",
        "@innopolis_live",
        "@school21_kazan",
    }
    assert sources["count"] == 6
    assert "yandex_search" in health
    assert health["errors"] == []


def test_vacancies_and_news_do_not_use_static_fallback(client, monkeypatch):
    async def empty_hh(role=None):
        return [], []

    async def empty_ys(role=None):
        return [], []

    async def empty_news():
        return [], []

    async def empty_tg():
        return [], []

    monkeypatch.setattr(api_server, "fetch_hh_vacancies_for_role", empty_hh)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_vacancies", empty_ys)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_news", empty_news)
    monkeypatch.setattr(api_server, "fetch_tg_news", empty_tg)

    vacs = client.get("/api/live-vacancies").json()
    news = client.get("/api/live-news").json()
    stats = client.get("/api/stats").json()
    assert vacs["vacancies"] == []
    assert vacs["source"] in {"empty", "live"}
    assert news["news"] == []
    assert "KazanExpress" not in str(vacs)
    assert "Digital Tatarstan 2026" not in str(news)
    assert stats["total_vacancies"] == 0
    assert stats["total_sources"] == 6


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


def test_empty_hh_plus_mocked_search_returns_cards(client, monkeypatch):
    card = {
        "id": "ys_abc",
        "title": "Junior Backend — ICL Services",
        "company": "ICL Services",
        "role": "backend",
        "category": "vacancy",
        "format": "remote",
        "url": "https://hh.ru/vacancy/123456",
        "tags": ["junior", "backend"],
        "source": {"type": "yandex", "name": "Yandex Search → hh.ru", "url": "https://hh.ru/vacancy/123456"},
    }

    async def fake_hh(role):
        return [], ["hh.ru: HTTP 403 forbidden"]

    async def fake_ys(role=None):
        assert role == "backend"
        return [card], []

    monkeypatch.setattr(api_server, "fetch_hh_vacancies_for_role", fake_hh)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_vacancies", fake_ys)
    response = client.get("/api/live-vacancies", params={"role": "backend"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["vacancies"][0]["url"] == "https://hh.ru/vacancy/123456"
    assert body["vacancies"][0]["source"]["name"] == "Yandex Search → hh.ru"
    assert body["live"] is True


def test_role_search_503_when_hh_and_yandex_fail(client, monkeypatch):
    async def fake_hh(role):
        return [], ["hh.ru: HTTP 403 forbidden"]

    async def fake_ys(role=None):
        return [], ["Yandex Search: HTTP 403 Permission denied. Нужны scope yc.search-api.execute"]

    monkeypatch.setattr(api_server, "fetch_hh_vacancies_for_role", fake_hh)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_vacancies", fake_ys)
    response = client.get("/api/live-vacancies", params={"role": "frontend"})
    assert response.status_code == 503
    body = response.json()
    assert body["vacancies"] == []
    assert body["errors"]
    assert any("403" in err for err in body["errors"])
    health = client.get("/api/health").json()
    assert health["fetch_error"]
    assert health["cached_vacancies"] == 0
    assert health["errors"]


def test_role_search_does_not_wait_for_warm_cache(client, monkeypatch):
    calls = {"n": 0}

    async def fake_hh(role):
        return [], []

    async def fake_ys(role=None):
        calls["n"] += 1
        return [
            {
                "id": "ys_on_demand",
                "title": "Стажёр frontend",
                "company": "",
                "role": "frontend",
                "category": "internship",
                "format": "office",
                "url": "https://hh.ru/vacancy/777",
                "tags": [],
                "source": {"type": "yandex", "name": "Yandex Search → hh.ru", "url": "https://hh.ru/vacancy/777"},
            }
        ], []

    monkeypatch.setattr(api_server, "fetch_hh_vacancies_for_role", fake_hh)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_vacancies", fake_ys)
    first = client.get("/api/live-vacancies", params={"role": "frontend"})
    assert first.status_code == 200
    assert first.json()["vacancies"][0]["id"] == "ys_on_demand"
    second = client.get("/api/live-vacancies", params={"role": "frontend"})
    assert second.status_code == 200
    assert calls["n"] == 1


def test_vacancies_without_role_trigger_live_search(client, monkeypatch):
    calls = {"hh": 0, "ys": 0}

    async def fake_hh(role):
        calls["hh"] += 1
        assert role is None
        return [
            {
                "id": "hh_all",
                "title": "Junior Python",
                "company": "ICL",
                "role": "backend",
                "category": "vacancy",
                "format": "office",
                "url": "https://hh.ru/vacancy/1",
                "tags": [],
                "source": {"type": "hh", "name": "hh.ru", "url": "https://hh.ru/vacancy/1"},
            }
        ], []

    async def fake_ys(role=None):
        calls["ys"] += 1
        assert role is None
        return [], []

    monkeypatch.setattr(api_server, "fetch_hh_vacancies_for_role", fake_hh)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_vacancies", fake_ys)
    first = client.get("/api/live-vacancies")
    assert first.status_code == 200
    assert first.json()["vacancies"][0]["id"] == "hh_all"
    assert first.json()["vacancies"][0]["url"] == "https://hh.ru/vacancy/1"
    second = client.get("/api/live-vacancies")
    assert second.status_code == 200
    assert calls["hh"] == 1
    assert calls["ys"] == 1


def test_live_news_from_yandex_search(client, monkeypatch):
    calls = {"n": 0}
    card = {
        "id": "ys_news_1",
        "title": "Хакатон в Иннополисе",
        "source": "@innopolis_live",
        "sourceType": "telegram",
        "url": "https://t.me/innopolis_live/10",
        "summary": "Регистрация открыта",
        "tags": ["хакатон"],
        "icon": "💻",
        "dateLabel": "из поиска",
        "dateSort": 50,
    }

    async def fake_tg():
        return [], []

    async def fake_ys_news():
        calls["n"] += 1
        return [card], []

    monkeypatch.setattr(api_server, "fetch_tg_news", fake_tg)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_news", fake_ys_news)
    first = client.get("/api/live-news")
    assert first.status_code == 200
    body = first.json()
    assert body["news"][0]["url"] == "https://t.me/innopolis_live/10"
    assert body["news"][0]["source"] == "@innopolis_live"
    assert "KazanExpress" not in str(body)
    assert "Digital Tatarstan 2026" not in str(body)
    second = client.get("/api/live-news")
    assert second.status_code == 200
    assert calls["n"] == 1


def test_live_news_503_when_sources_fail(client, monkeypatch):
    async def fake_tg():
        return [], ["telegram @kazanit: HTTP 403"]

    async def fake_ys_news():
        return [], ["Yandex Search: HTTP 403 Permission denied"]

    monkeypatch.setattr(api_server, "fetch_tg_news", fake_tg)
    monkeypatch.setattr(api_server.yandex_search, "fetch_yandex_news", fake_ys_news)
    response = client.get("/api/live-news")
    assert response.status_code == 503
    body = response.json()
    assert body["news"] == []
    assert body["errors"]
    assert any("403" in err for err in body["errors"])


def test_no_fake_register_endpoint(client):
    response = client.post("/api/register", json={"name": "x", "email": "a@b.c", "password": "p"})
    assert response.status_code in {404, 405}
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("success") is not True
