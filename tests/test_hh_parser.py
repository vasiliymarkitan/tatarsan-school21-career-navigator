import asyncio

from parser import hh_parser


SAMPLE = {
    "id": "123",
    "name": "Junior Python Developer",
    "alternate_url": "https://hh.ru/vacancy/123",
    "published_at": "2026-08-17T10:00:00+03:00",
    "employer": {"id": "99", "name": "ICL Services"},
    "area": {"name": "Казань"},
    "salary": {"from": 60000, "to": None, "currency": "RUR"},
    "schedule": {"id": "remote"},
    "experience": {"id": "noExperience"},
    "snippet": {"requirement": "Python, FastAPI", "responsibility": "Писать API"},
}


def test_map_vacancy_points_to_vacancy_not_employer():
    mapped = hh_parser._map_vacancy(SAMPLE, 0)
    assert mapped["url"] == "https://hh.ru/vacancy/123"
    assert mapped["source"]["url"] == "https://hh.ru/vacancy/123"
    assert mapped["role"] == "backend"
    assert mapped["format"] == "remote"
    assert mapped["salary"].startswith("от")


def test_user_agent_has_no_personal_email():
    headers = hh_parser.request_headers()
    blob = " ".join(headers.values()).lower()
    assert "alina251201" not in blob
    assert "@gmail.com" not in blob
    assert "careernavigator21" in blob.lower() or "career-navigator" in blob.lower()


def test_fallback_summary_is_honest_when_snippet_empty():
    item = dict(SAMPLE)
    item["snippet"] = {}
    mapped = hh_parser._map_vacancy(item, 0)
    assert "hh.ru" in mapped["aiSummary"]
    assert "KazanExpress" not in mapped["aiSummary"]


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        return self._handler(url, params)


def test_hh_forbidden_is_reported_not_silent_empty(monkeypatch):
    def handler(url, params):
        return _Resp(403, {}, text='{"description":"bad_user_agent"}')

    monkeypatch.setattr(hh_parser.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    items, errors = asyncio.run(hh_parser.fetch_hh_vacancies())
    assert items == []
    assert errors
    assert "403" in errors[0]
    assert "bad_user_agent" in errors[0]


def test_hh_200_empty_is_success_without_error(monkeypatch):
    def handler(url, params):
        return _Resp(200, {"items": []})

    monkeypatch.setattr(hh_parser.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    items, errors = asyncio.run(hh_parser.fetch_hh_vacancies())
    assert items == []
    assert errors == []
