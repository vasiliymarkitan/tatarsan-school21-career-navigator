from parser.geo import (
    classify_geo,
    extract_location,
    is_off_region_office,
    matches_location,
    prefer_tatarstan,
    scope_default_stream,
)


def test_classify_rt_wins_over_moscow_mention():
    assert classify_geo("Стажировка в Казани, офис также в Москве") == "rt"
    assert classify_geo("Junior Python, удалённо, Москва", format_hint="office") == "remote"
    assert classify_geo("Стажёр Python, Москва") == "off_region"
    assert classify_geo("Junior Go") == "unknown"


def test_extract_location_labels():
    assert extract_location("офис в Иннополисе") == "Иннополис"
    assert extract_location("Казань, Python") == "Казань"
    assert extract_location("удалённо по РФ") == "Remote РФ"
    assert extract_location("офис Москва") == "Москва"
    assert extract_location("без города") == "не указано"


def test_scope_drops_office_noise_keeps_remote():
    items = [
        {"id": "kzn", "title": "Junior", "location": "Казань", "format": "office"},
        {"id": "msk", "title": "Стажёр, Москва", "location": "Москва", "format": "office"},
        {"id": "remote", "title": "Junior remote Москва", "location": "Москва", "format": "remote"},
        {"id": "minsk", "title": "Стажёр, Минск", "location": "Минск", "format": "office"},
    ]
    scoped = scope_default_stream(items)
    assert [item["id"] for item in scoped] == ["kzn", "remote"]
    assert is_off_region_office(items[1]) is True
    assert is_off_region_office(items[2]) is False


def test_matches_location_and_prefer():
    items = [
        {"id": "inn", "title": "Frontend", "location": "Иннополис", "format": "office", "dateSort": 2},
        {"id": "kzn", "title": "Backend Казань", "location": "Казань", "format": "office", "dateSort": 1},
        {"id": "rem", "title": "QA remote", "location": "Remote РФ", "format": "remote", "dateSort": 0},
    ]
    assert [item["id"] for item in prefer_tatarstan(items)] == ["kzn", "inn", "rem"]
    assert [item["id"] for item in items if matches_location(item, "Казань")] == ["kzn"]
    assert [item["id"] for item in items if matches_location(item, "remote")] == ["rem"]
