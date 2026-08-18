import asyncio
import base64
from unittest.mock import patch

from parser import yandex_search
from parser.yandex_search import (
    SearchAPIError,
    build_queries,
    decode_raw_data,
    is_allowed_vacancy_url,
    map_search_hits,
    parse_search_xml,
)

SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<yandexsearch version="1.0">
  <response>
    <results>
      <grouping>
        <group>
          <doc>
            <url>https://hh.ru/vacancy/123456</url>
            <title>Junior <hlword>Python</hlword> Developer — ICL Services</title>
            <headline>Стажировка в Казани, Python, FastAPI</headline>
            <domain>hh.ru</domain>
            <passages><passage>от 60 000 ₽</passage></passages>
          </doc>
        </group>
        <group>
          <doc>
            <url></url>
            <title>Стажёр без ссылки</title>
          </doc>
        </group>
        <group>
          <doc>
            <url>https://ru.wikipedia.org/wiki/Python</url>
            <title>Python — Википедия</title>
          </doc>
        </group>
        <group>
          <doc>
            <url>https://hh.ru/employer/99</url>
            <title>ICL Services — работодатель</title>
          </doc>
        </group>
      </grouping>
    </results>
  </response>
</yandexsearch>
"""

EMPTY_XML = """<?xml version="1.0" encoding="utf-8"?>
<yandexsearch><response><error code="15">not found</error></response></yandexsearch>
"""


def test_build_queries_include_role_and_tatarstan_or_remote():
    queries = build_queries("backend")
    blob = " ".join(queries).lower()
    assert queries
    assert all("site:hh.ru" in q for q in queries)
    assert all("lang:ru" in q for q in queries)
    assert "backend" in blob or "python" in blob
    assert "junior" in blob
    assert "стажировка" in blob
    assert "казань" in blob or "татарстан" in blob or "иннополис" in blob
    assert "удалённ" in blob or "удаленн" in blob or "remote" in blob


def test_drop_results_without_http_url_or_non_job_host():
    hits, err = parse_search_xml(SAMPLE_XML)
    assert err is None
    assert len(hits) == 4
    cards = map_search_hits(hits, role="backend")
    assert len(cards) == 1
    assert cards[0]["url"] == "https://hh.ru/vacancy/123456"
    assert cards[0]["source"]["name"] == "Yandex Search → hh.ru"
    assert cards[0]["source"]["type"] == "yandex"


def test_map_does_not_invent_company_or_salary():
    hits = [
        {
            "url": "https://hh.ru/vacancy/9",
            "title": "Junior backend developer",
            "snippet": "Стажировка в Казани, удалённо, Россия",
            "domain": "hh.ru",
        }
    ]
    cards = map_search_hits(hits, role="backend")
    assert len(cards) == 1
    assert cards[0]["company"] == ""
    assert cards[0]["salary"] is None
    assert "Contoso" not in str(cards[0])
    assert cards[0]["aiSummary"] == "Стажировка в Казани, удалённо, Россия"


def test_map_keeps_salary_and_company_only_from_hit():
    hits, _ = parse_search_xml(SAMPLE_XML)
    cards = map_search_hits(hits, role="backend")
    assert cards[0]["company"] == "ICL Services"
    assert cards[0]["salary"] and "60" in cards[0]["salary"]
    assert cards[0]["role"] == "backend"
    assert cards[0]["location"] == "Казань"


def test_allowed_vacancy_url():
    assert is_allowed_vacancy_url("https://hh.ru/vacancy/1")
    assert is_allowed_vacancy_url("https://kazan.hh.ru/vacancy/1")
    assert not is_allowed_vacancy_url("")
    assert not is_allowed_vacancy_url("ftp://hh.ru/vacancy/1")
    assert not is_allowed_vacancy_url("https://hh.ru/vacancies/programmist")
    assert not is_allowed_vacancy_url("https://example.com/vacancy/1")


def test_xml_error_15_is_empty_success():
    hits, err = parse_search_xml(EMPTY_XML)
    assert hits == []
    assert err is None


def test_decode_raw_data_roundtrip():
    raw = base64.b64encode(SAMPLE_XML.encode()).decode()
    assert "hh.ru/vacancy/123456" in decode_raw_data({"rawData": raw})


def test_text_search_rejects_invented_json_hits():
    try:
        decode_raw_data({"title": "Junior", "url": "https://hh.ru/vacancy/1", "snippet": "x"})
        assert False, "expected SearchAPIError"
    except yandex_search.SearchAPIError as exc:
        assert "rawData" in str(exc)


def test_web_search_body_matches_official_proto(monkeypatch):
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1guda0p3tk70m5m13og")
    body = yandex_search.build_web_search_body("site:hh.ru lang:ru junior backend Казань")
    assert body["folderId"] == "b1guda0p3tk70m5m13og"
    assert body["query"]["searchType"] == "SEARCH_TYPE_RU"
    assert body["query"]["page"] == 0
    assert body["groupSpec"]["groupMode"] == "GROUP_MODE_FLAT"
    assert body["groupSpec"]["groupsOnPage"] == 10
    assert body["groupSpec"]["docsInGroup"] == 1
    assert body["maxPassages"] == 3
    assert body["l10n"] == "LOCALIZATION_RU"
    assert body["responseFormat"] == "FORMAT_XML"
    assert "gmail" not in body["userAgent"].lower()
    assert "region" not in body  # region id не угадываем


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ("" if payload is None else str(payload))

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        return self._handler(url, headers, json)


def test_search_client_mocked_http_maps_cards(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "test-search-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1guda0p3tk70m5m13og")
    captured = {}

    def handler(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        raw = base64.b64encode(SAMPLE_XML.encode()).decode()
        return _Resp(200, {"rawData": raw})

    monkeypatch.setattr(yandex_search.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    items, errors = asyncio.run(yandex_search.fetch_yandex_vacancies("backend"))
    assert errors == []
    assert len(items) == 1
    assert items[0]["url"] == "https://hh.ru/vacancy/123456"
    assert captured["url"].endswith("/v2/web/search")
    assert captured["headers"]["Authorization"] == "Api-Key test-search-key"
    assert captured["body"]["folderId"] == "b1guda0p3tk70m5m13og"
    assert captured["body"]["query"]["searchType"] == "SEARCH_TYPE_RU"
    assert captured["body"]["query"]["page"] == 0
    assert captured["body"]["maxPassages"] == 3
    assert captured["body"]["responseFormat"] == "FORMAT_XML"
    assert "site:hh.ru" in captured["body"]["query"]["queryText"]
    assert "lang:ru" in captured["body"]["query"]["queryText"]


def test_search_api_key_override(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "gpt-only-key")
    monkeypatch.setenv("YANDEX_SEARCH_API_KEY", "search-override")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1gfolder")
    captured = {}

    def handler(url, headers, body):
        captured["auth"] = headers["Authorization"]
        raw = base64.b64encode(EMPTY_XML.encode()).decode()
        return _Resp(200, {"rawData": raw})

    monkeypatch.setattr(yandex_search.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    items, errors = asyncio.run(yandex_search.fetch_yandex_vacancies("frontend"))
    assert items == []
    assert errors == []
    assert captured["auth"] == "Api-Key search-override"


def test_search_403_is_honest_error(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "test-search-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1gfolder")

    def handler(url, headers, body):
        return _Resp(403, {"message": "Permission denied"}, text='{"message":"Permission denied"}')

    monkeypatch.setattr(yandex_search.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    items, errors = asyncio.run(yandex_search.fetch_yandex_vacancies("backend"))
    assert items == []
    assert errors
    assert "403" in errors[0]
    assert "search-api.webSearch.user" in errors[0]


def test_unconfigured_search_does_not_call_http(monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_IAM_TOKEN", raising=False)
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)
    with patch.object(yandex_search.httpx, "AsyncClient") as client_cls:
        items, errors = asyncio.run(yandex_search.fetch_yandex_vacancies("backend"))
    client_cls.assert_not_called()
    assert items == []
    assert "Yandex Search не настроен" in errors[0]


def test_web_search_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "test-search-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1gfolder")

    def handler(url, headers, body):
        return _Resp(401, {}, text="unauthorized")

    monkeypatch.setattr(yandex_search.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    try:
        asyncio.run(yandex_search.web_search("site:hh.ru junior backend Казань"))
        assert False, "expected SearchAPIError"
    except SearchAPIError as exc:
        assert "401" in str(exc)
        assert "yc.search-api.execute" in str(exc)
