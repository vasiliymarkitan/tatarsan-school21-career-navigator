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
