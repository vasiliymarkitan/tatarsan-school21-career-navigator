import asyncio
import base64
from unittest.mock import patch

from parser import yandex_search
from parser.yandex_search import (
    SearchAPIError,
    build_news_queries,
    build_news_queries_for,
    build_queries,
    decode_raw_data,
    is_allowed_news_url,
    is_allowed_vacancy_url,
    is_telegram_chrome_title,
    map_news_hits,
    map_search_hits,
    news_channel_from_url,
    news_title_from_hit,
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

SAMPLE_NEWS_XML = """<?xml version="1.0" encoding="utf-8"?>
<yandexsearch version="1.0">
  <response>
    <results>
      <grouping>
        <group>
          <doc>
            <url>https://t.me/kazanit/42</url>
            <title>Хакатон в Казани: ищем разработчиков</title>
            <headline>IT-парк, стажировки, Иннополис</headline>
            <domain>t.me</domain>
          </doc>
        </group>
        <group>
          <doc>
            <url>https://t.me/durov/1</url>
            <title>Чужой канал</title>
          </doc>
        </group>
        <group>
          <doc>
            <url>https://lenta.ru/news/it</url>
            <title>Новость с другого сайта</title>
          </doc>
        </group>
        <group>
          <doc>
            <url></url>
            <title>Пост без ссылки</title>
          </doc>
        </group>
      </grouping>
    </results>
  </response>
</yandexsearch>
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


def test_map_drops_moscow_office_keeps_remote_and_kazan():
    hits = [
        {
            "url": "https://hh.ru/vacancy/1",
            "title": "Стажёр Python, Москва",
            "snippet": "офис в Москве",
            "domain": "hh.ru",
        },
        {
            "url": "https://hh.ru/vacancy/2",
            "title": "Junior Python remote Москва",
            "snippet": "удалённо, Россия",
            "domain": "hh.ru",
        },
        {
            "url": "https://hh.ru/vacancy/3",
            "title": "Junior Python, Казань",
            "snippet": "офис",
            "domain": "hh.ru",
        },
    ]
    cards = map_search_hits(hits, role="backend")
    urls = [card["url"] for card in cards]
    assert "https://hh.ru/vacancy/1" not in urls
    assert "https://hh.ru/vacancy/2" in urls
    assert "https://hh.ru/vacancy/3" in urls


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


def test_build_news_queries_for_one_channel():
    queries = build_news_queries_for("kazanit")
    blob = " ".join(queries)
    assert "url:t.me/kazanit/*" in blob
    assert "it_tatarstan" not in blob
    assert "hh.ru" not in blob


def test_telegram_chrome_title_is_detected():
    assert is_telegram_chrome_title("Telegram: View @it_tatarstan", "it_tatarstan")
    assert is_telegram_chrome_title("Telegram", "kazanit")
    assert not is_telegram_chrome_title("Хакатон Школы 21 в Казани", "it_tatarstan")
    assert news_title_from_hit(
        "Telegram: View @it_tatarstan",
        "Хакатон Школы 21 в Казани откроется в сентябре",
        "it_tatarstan",
    ).startswith("Хакатон")


def test_map_news_uses_snippet_when_title_is_chrome():
    hits = [
        {
            "url": "https://t.me/it_tatarstan/99",
            "title": "Telegram: View @it_tatarstan",
            "snippet": "Хакатон Школы 21 в Казани откроется в сентябре",
            "domain": "t.me",
        },
        {
            "url": "https://t.me/it_tatarstan",
            "title": "Telegram: View @it_tatarstan",
            "snippet": "",
            "domain": "t.me",
        },
    ]
    cards = map_news_hits(hits)
    assert len(cards) == 1
    assert cards[0]["url"] == "https://t.me/it_tatarstan/99"
    assert "Хакатон" in cards[0]["title"]
    assert "Telegram: View" not in cards[0]["title"]


def test_build_news_queries_only_assigned_channels():
    queries = build_news_queries()
    blob = " ".join(queries).lower()
    assert queries
    assert all(len(query) <= 400 for query in queries)
    for channel in ("kazanit", "it_tatarstan", "innopolis_live", "school21_kazan"):
        assert f"url:t.me/{channel}/*" in blob
        assert f"@{channel} site:t.me" in blob
    assert "site:t.me/kazanit" not in blob  # path-site is a no-op in Search API
    assert "lenta.ru" not in blob
    assert "site:hh.ru" not in blob
    assert "business-gazeta" not in blob
    assert "хакатон" not in blob  # extra AND keywords zeroed the live index


def test_news_url_allows_only_four_channels():
    assert is_allowed_news_url("https://t.me/kazanit/1")
    assert is_allowed_news_url("https://t.me/s/it_tatarstan/2")
    assert is_allowed_news_url("https://telegram.me/innopolis_live/3")
    assert is_allowed_news_url("https://t.me/school21_kazan")
    assert news_channel_from_url("https://t.me/s/kazanit/42") == "kazanit"
    assert not is_allowed_news_url("https://t.me/durov/1")
    assert not is_allowed_news_url("https://example.com/news")
    assert not is_allowed_news_url("https://hh.ru/vacancy/1")
    assert not is_allowed_news_url("")


def test_map_news_hits_drops_other_hosts_and_does_not_invent():
    hits, err = parse_search_xml(SAMPLE_NEWS_XML)
    assert err is None
    cards = map_news_hits(hits)
    assert len(cards) == 1
    assert cards[0]["url"] == "https://t.me/kazanit/42"
    assert cards[0]["source"] == "@kazanit"
    assert cards[0]["sourceType"] == "telegram"
    assert "Contoso" not in str(cards[0])
    assert "KazanExpress" not in str(cards[0])
    assert cards[0]["summary"] == "IT-парк, стажировки, Иннополис"


def test_fetch_yandex_news_mocked_http(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "test-search-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1guda0p3tk70m5m13og")
    captured = {"queries": []}

    def handler(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["queries"].append(body["query"]["queryText"])
        raw = base64.b64encode(SAMPLE_NEWS_XML.encode()).decode()
        return _Resp(200, {"rawData": raw})

    monkeypatch.setattr(yandex_search.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    items, errors = asyncio.run(yandex_search.fetch_yandex_news())
    assert errors == []
    assert len(items) == 1
    assert items[0]["url"] == "https://t.me/kazanit/42"
    assert captured["url"].endswith("/v2/web/search")
    assert captured["headers"]["Authorization"] == "Api-Key test-search-key"
    assert any("url:t.me/kazanit/*" in query for query in captured["queries"])
    assert any("@kazanit site:t.me" in query for query in captured["queries"])
    assert all("site:hh.ru" not in query for query in captured["queries"])
    assert all("site:t.me/kazanit" not in query for query in captured["queries"])


def test_news_channels_queried_independently(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "test-search-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "b1gfolder")

    async def fake_collect(queries):
        blob = " ".join(queries)
        if "kazanit" in blob:
            return [], ["Yandex Search: HTTP 403 Permission denied"]
        if "it_tatarstan" in blob:
            return [
                {
                    "url": "https://t.me/it_tatarstan/5",
                    "title": "Telegram: View @it_tatarstan",
                    "snippet": "Набор в Школу 21: стажировки в Казани",
                    "domain": "t.me",
                }
            ], []
        return [], []

    monkeypatch.setattr(yandex_search, "_collect_hits", fake_collect)
    items, errors = asyncio.run(yandex_search.fetch_yandex_news())
    assert len(items) == 1
    assert items[0]["url"] == "https://t.me/it_tatarstan/5"
    assert "Набор" in items[0]["title"]
    assert "Telegram: View" not in items[0]["title"]
    assert errors
    assert any("403" in err for err in errors)


def test_unconfigured_news_search_does_not_call_http(monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_IAM_TOKEN", raising=False)
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)
    with patch.object(yandex_search.httpx, "AsyncClient") as client_cls:
        items, errors = asyncio.run(yandex_search.fetch_yandex_news())
    client_cls.assert_not_called()
    assert items == []
    assert "Yandex Search не настроен" in errors[0]
