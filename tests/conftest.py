import os
from pathlib import Path

os.environ.setdefault("CN21_DISABLE_BACKGROUND", "1")
os.environ.setdefault("JWT_SECRET", "ci-test-secret-please-use-32chars!")
os.environ.setdefault("LLM_PROVIDER", "yandex")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("BOT_USERNAME", "")
os.environ.setdefault("YANDEX_API_KEY", "")
os.environ.setdefault("YANDEX_SEARCH_API_KEY", "")
os.environ.setdefault("YANDEX_FOLDER_ID", "")
os.environ.setdefault("GIGACHAT_CREDENTIALS", "")
os.environ["DIGEST_STORE_PATH"] = str(Path(__file__).resolve().parent / "_tmp_digest.json")

import pytest
from fastapi.testclient import TestClient

from api_server import app, _cache


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_cache(tmp_path, monkeypatch):
    _cache["vacancies"] = []
    _cache["news"] = []
    _cache["last_update"] = None
    _cache["fetch_error"] = None
    _cache["source_errors"] = []
    _cache["vacancy_errors"] = []
    _cache["news_errors"] = []
    store = tmp_path / "digest_settings.json"
    monkeypatch.setenv("DIGEST_STORE_PATH", str(store))
    from digest import store as digest_store

    monkeypatch.setattr(digest_store, "store_path", lambda: store)
    yield
    if store.exists():
        store.unlink()
