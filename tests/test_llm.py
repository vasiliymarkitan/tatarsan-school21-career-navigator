import asyncio

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


def test_select_cached_vacancies_filters_role_and_geo():
    cache = [
        {"id": "kzn", "title": "Junior Python", "company": "ICL", "role": "backend", "format": "office", "location": "Казань", "tags": ["python"]},
        {"id": "fe", "title": "Junior React", "company": "X", "role": "frontend", "format": "office", "location": "Казань", "tags": []},
        {"id": "msk", "title": "Стажёр, Москва", "company": "Y", "role": "backend", "format": "office", "location": "Москва", "tags": []},
    ]
    picked = llm.select_cached_vacancies(cache, role="backend", skills="Python", plan={})
    assert [item["id"] for item in picked] == ["kzn"]


def test_run_career_agent_empty_cache_is_honest(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "configured_provider", lambda: "yandex")

    async def fake_plan(role, skills, goals):
        return '{"search_query": "junior backend", "prefer_remote": false, "internship_only": false}'

    async def fake_verify(role, skills, goals, vac_list):
        assert vac_list is None
        return "В живом кэше сейчас нет подходящих карточек."

    monkeypatch.setattr(llm.yandex, "plan_search", fake_plan)
    monkeypatch.setattr(llm.yandex, "verify_vacancies", fake_verify)

    async def boom(*_args, **_kwargs):
        raise AssertionError("must not call hh.ru")

    monkeypatch.setattr("parser.hh_parser.fetch_vacancies_by_query", boom)
    result = asyncio.run(llm.run_career_agent("backend", "", "", vacancies=[]))
    assert result["vacancies"] == []
    assert result["vacancies_source"] == "cache_empty"
    assert result["steps"][1]["tool"] == "live_cache"
    assert "Contoso" not in result["advice"]


def test_run_career_agent_returns_cache_cards(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "configured_provider", lambda: "yandex")

    async def fake_plan(role, skills, goals):
        return '{"search_query": "junior backend", "prefer_remote": false, "internship_only": false}'

    async def fake_verify(role, skills, goals, vac_list):
        assert "Junior Python" in (vac_list or "")
        return "подходит"

    monkeypatch.setattr(llm.yandex, "plan_search", fake_plan)
    monkeypatch.setattr(llm.yandex, "verify_vacancies", fake_verify)
    cache = [
        {
            "id": "kzn",
            "title": "Junior Python",
            "company": "ICL",
            "role": "backend",
            "format": "office",
            "location": "Казань",
            "url": "https://hh.ru/vacancy/1",
            "tags": ["python"],
        }
    ]
    result = asyncio.run(llm.run_career_agent("backend", "Python", "стажировка", vacancies=cache))
    assert result["vacancies_source"] == "live_cache"
    assert result["vacancies"][0]["url"] == "https://hh.ru/vacancy/1"
    assert result["vacancies"][0]["title"] == "Junior Python"
