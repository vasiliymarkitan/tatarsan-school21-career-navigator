from ai import provider as llm
from ai import yandex


def test_default_provider_is_yandex(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm.configured_provider() == "yandex"


def test_gigachat_remains_switchable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gigachat")
    monkeypatch.setattr(llm.giga, "_ENABLED", False)
    assert llm.configured_provider() == "gigachat"
    status = llm.status()
    assert status["provider"] == "gigachat"
    assert status["enabled"] is False
    assert "GIGACHAT_CREDENTIALS" in status["missing"]


def test_yandex_status_lists_missing_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "yandex")
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)
    status = llm.status()
    assert status["enabled"] is False
    assert "YANDEX_API_KEY" in status["missing"]
    assert "YANDEX_FOLDER_ID" in status["missing"]


def test_yandex_model_uri(monkeypatch):
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1gfolder")
    monkeypatch.setenv("YANDEX_MODEL", "yandexgpt-lite")
    assert yandex._model_uri() == "gpt://b1gfolder/yandexgpt-lite/latest"
