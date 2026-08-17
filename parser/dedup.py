"""Honest vacancy/news dedup: id, URL, title+company, near-duplicate titles."""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse, urlunparse

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_TITLE_NOISE = (
    "junior",
    "middle",
    "senior",
    "стажёр",
    "стажер",
    "стажировка",
    "intern",
    "internship",
)


def normalize_text(value: str) -> str:
    text = (value or "").casefold().replace("ё", "е")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


def _tokens(value: str) -> set[str]:
    return {t for t in normalize_text(value).split() if t and t not in _TITLE_NOISE}


def title_similarity(a: str, b: str) -> float:
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def vacancy_identity_keys(item: dict) -> tuple[str, ...]:
    keys: list[str] = []
    vid = str(item.get("id") or "").strip()
    if vid:
        keys.append(f"id:{vid}")
    url = normalize_url(str(item.get("url") or ""))
    if url:
        keys.append(f"url:{url}")
    source = item.get("source") or {}
    source_url = normalize_url(str(source.get("url") or ""))
    if source_url and source_url != url:
        keys.append(f"url:{source_url}")
    title = normalize_text(str(item.get("title") or ""))
    company = normalize_text(str(item.get("company") or ""))
    if title and company:
        keys.append(f"pair:{company}|{title}")
    return tuple(keys)


def _source_rank(item: dict) -> int:
    source_type = str((item.get("source") or {}).get("type") or "")
    # Prefer a first-party page over an aggregator copy of the same role.
    return {"website": 0, "telegram": 1, "hh": 2}.get(source_type, 3)


def is_near_duplicate(left: dict, right: dict, threshold: float = 0.75) -> bool:
    left_company = normalize_text(str(left.get("company") or ""))
    right_company = normalize_text(str(right.get("company") or ""))
    if not left_company or left_company != right_company:
        return False
    return title_similarity(str(left.get("title") or ""), str(right.get("title") or "")) >= threshold


def dedup_vacancies(items: Iterable[dict], threshold: float = 0.75) -> list[dict]:
    """Drop exact and near duplicates. Keeps the higher-ranked source, then the newer card."""
    kept: list[dict] = []
    seen: set[str] = set()

    ordered = sorted(
        items,
        key=lambda item: (
            _source_rank(item),
            int(item.get("dateSort") if item.get("dateSort") is not None else 99),
        ),
    )

    for item in ordered:
        keys = vacancy_identity_keys(item)
        if any(key in seen for key in keys):
            continue
        if any(is_near_duplicate(item, existing, threshold=threshold) for existing in kept):
            continue
        kept.append(item)
        seen.update(keys)

    return kept


def news_identity_keys(item: dict) -> tuple[str, ...]:
    keys: list[str] = []
    nid = str(item.get("id") or "").strip()
    if nid:
        keys.append(f"id:{nid}")
    url = normalize_url(str(item.get("url") or ""))
    if url:
        keys.append(f"url:{url}")
    title = normalize_text(str(item.get("title") or ""))
    source = normalize_text(str(item.get("source") or ""))
    if title and source:
        keys.append(f"pair:{source}|{title}")
    return tuple(keys)


def dedup_news(items: Iterable[dict], threshold: float = 0.85) -> list[dict]:
    kept: list[dict] = []
    seen: set[str] = set()
    ordered = sorted(items, key=lambda item: int(item.get("dateSort") if item.get("dateSort") is not None else 99))

    for item in ordered:
        keys = news_identity_keys(item)
        if any(key in seen for key in keys):
            continue
        if any(
            normalize_text(str(item.get("source") or "")) == normalize_text(str(existing.get("source") or ""))
            and title_similarity(str(item.get("title") or ""), str(existing.get("title") or "")) >= threshold
            for existing in kept
        ):
            continue
        kept.append(item)
        seen.update(keys)
    return kept
