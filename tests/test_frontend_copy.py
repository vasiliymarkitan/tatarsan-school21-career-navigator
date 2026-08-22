from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_index_does_not_claim_telegram_is_off():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "Telegram-авторизация не настроена" not in html
    assert "Топ-5 за день" in html
    assert "ACT · hh.ru" not in html
    assert "ACT · кэш" in html


def test_app_js_agent_uses_cache_copy():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "hh.ru ничего не вернул" not in js
    assert "Живой кэш пуст" in js
    assert "params.set('location'" in js
