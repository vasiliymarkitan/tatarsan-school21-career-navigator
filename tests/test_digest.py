from datetime import datetime
from zoneinfo import ZoneInfo

from digest.builder import build_digest, format_telegram
from digest.scheduler import should_send
from digest.store import get_settings, save_settings


def test_builder_uses_only_matching_live_items():
    vacancies = [
        {"title": "Python intern", "company": "ICL", "role": "backend", "url": "https://hh.ru/vacancy/1", "salary": "от 20 000 ₽"},
        {"title": "React junior", "company": "X", "role": "frontend", "url": "https://hh.ru/vacancy/2"},
    ]
    news = [{"title": "Хакатон", "source": "@kazanit", "url": "https://t.me/kazanit/1"}]
    digest = build_digest(vacancies, news, roles=["backend"])
    assert digest["total_matched"] == 1
    assert digest["vacancies"][0]["title"] == "Python intern"
    assert digest["empty"] is False
    text = format_telegram(digest)
    assert "Python intern" in text
    assert "KazanExpress" not in text


def test_builder_empty_is_honest():
    digest = build_digest([], [], roles=["qa"])
    assert digest["empty"] is True
    assert "нет" in format_telegram(digest).lower()


def test_store_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "digest.json"
    monkeypatch.setenv("DIGEST_STORE_PATH", str(path))
    from digest import store as digest_store

    monkeypatch.setattr(digest_store, "store_path", lambda: path)
    saved = save_settings("100", {"telegram_id": 100, "schedule": "weekdays", "time": "09:00", "roles": ["backend"]})
    assert saved["channel"] == "telegram"
    loaded = get_settings("100")
    assert loaded["roles"] == ["backend"]


def test_scheduler_twice_week_and_dedup_same_day():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=ZoneInfo("Europe/Moscow"))  # Tuesday
    settings = {"enabled": True, "schedule": "twice", "time": "09:00", "last_sent_date": None}
    assert should_send(settings, now) is True
    settings["last_sent_date"] = "2026-08-18"
    assert should_send(settings, now) is False
    monday = datetime(2026, 8, 17, 9, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    settings["last_sent_date"] = None
    assert should_send(settings, monday) is False
