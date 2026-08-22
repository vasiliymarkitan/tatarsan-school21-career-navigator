"""Tatarstan / remote geography — classify and filter live cards. Never invent jobs."""

from __future__ import annotations

from typing import Iterable

RT_HINTS = ("казан", "татарстан", "иннополис", "альметьев", "набережн")
REMOTE_HINTS = ("удалён", "удален", "remote", "удаленн")
OFF_REGION_HINTS = (
    "москв",
    "минск",
    "екатеринбург",
    "новосибирск",
    "санкт-петербург",
    "петербург",
    "спб",
    "питер",
    "краснодар",
    "нижний новгород",
    "самар",
    "ростов-на-дону",
    "воронеж",
    "челябинск",
    "пермь",
)

_RT_LABELS = (
    ("иннополис", "Иннополис"),
    ("казан", "Казань"),
    ("альметьев", "Альметьевск"),
    ("набережн", "Набережные Челны"),
    ("татарстан", "Татарстан"),
)
_OFF_LABELS = (
    ("москв", "Москва"),
    ("минск", "Минск"),
    ("екатеринбург", "Екатеринбург"),
    ("новосибирск", "Новосибирск"),
    ("санкт-петербург", "Санкт-Петербург"),
    ("петербург", "Санкт-Петербург"),
    ("спб", "Санкт-Петербург"),
    ("питер", "Санкт-Петербург"),
)

_LOCATION_ALIASES = {
    "казань": "казан",
    "иннополис": "иннополис",
    "альметьевск": "альметьев",
    "набережные челны": "набережн",
    "татарстан": "татарстан",
    "remote": "remote",
    "remote рф": "remote",
    "удалёнка": "remote",
    "удаленка": "remote",
}


def _fold(value: str) -> str:
    return (value or "").casefold().replace("ё", "е")


def vacancy_blob(item: dict) -> str:
    tags = item.get("tags") or []
    return _fold(
        " ".join(
            [
                str(item.get("location") or ""),
                str(item.get("title") or ""),
                str(item.get("aiSummary") or ""),
                str(item.get("company") or ""),
                " ".join(str(tag) for tag in tags),
            ]
        )
    )


def classify_geo(text: str, *, format_hint: str = "") -> str:
    """Return rt | remote | off_region | unknown. RT wins over an off-region city name."""
    lowered = _fold(text)
    fmt = _fold(format_hint)
    has_rt = any(hint in lowered for hint in RT_HINTS)
    has_remote = fmt == "remote" or any(hint in lowered for hint in REMOTE_HINTS)
    has_off = any(hint in lowered for hint in OFF_REGION_HINTS)
    if has_rt:
        return "rt"
    if has_remote:
        return "remote"
    if has_off:
        return "off_region"
    return "unknown"


def extract_location(text: str) -> str:
    lowered = _fold(text)
    for hint, label in _RT_LABELS:
        if hint in lowered:
            return label
    if any(hint in lowered for hint in REMOTE_HINTS):
        return "Remote РФ"
    for hint, label in _OFF_LABELS:
        if hint in lowered:
            return label
    return "не указано"


def is_off_region_office(item: dict) -> bool:
    """Moscow/Minsk/… office noise. Remote jobs stay even if the firm sits in Moscow."""
    fmt = str(item.get("format") or "")
    if fmt == "remote":
        return False
    return classify_geo(vacancy_blob(item), format_hint=fmt) == "off_region"


def scope_default_stream(items: Iterable[dict]) -> list[dict]:
    """Default vacancy stream: Tatarstan, remote, unknown. Drop off-region office."""
    return [item for item in items if not is_off_region_office(item)]


def matches_location(item: dict, location: str) -> bool:
    wanted = (location or "").strip()
    if not wanted or wanted == "all":
        return not is_off_region_office(item)
    alias = _LOCATION_ALIASES.get(_fold(wanted), _fold(wanted))
    if alias == "remote":
        fmt = str(item.get("format") or "")
        return fmt == "remote" or classify_geo(vacancy_blob(item), format_hint=fmt) == "remote"
    return alias in vacancy_blob(item)


def prefer_tatarstan(items: list[dict]) -> list[dict]:
    """Bias live cards toward Kazan / RT / Innopolis, then remote, then the rest."""

    def rank(item: dict) -> tuple[int, int]:
        geo = classify_geo(vacancy_blob(item), format_hint=str(item.get("format") or ""))
        region = {"rt": 0, "remote": 1, "unknown": 2, "off_region": 3}.get(geo, 2)
        date_sort = item.get("dateSort")
        return (region, int(date_sort) if date_sort is not None else 99)

    return sorted(items, key=rank)
