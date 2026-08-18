"""
Yandex Cloud Search API v2 — live vacancy pages, no invented cards.

Endpoint (verified against public Search API docs / SearXNG / official MCP):
  POST https://searchapi.api.cloud.yandex.net/v2/web/search
  Authorization: Api-Key <key>
  body.folderId + query.searchType=SEARCH_TYPE_RU, responseFormat=FORMAT_XML
  response: {"rawData": "<base64 XML>"}

The existing YANDEX_API_KEY is reused. If that key lacks Search API scope,
set YANDEX_SEARCH_API_KEY (do not commit it). IAM:
  API key scope: yc.search-api.execute
  service-account roles: search-api.webSearch.user and/or search-api.executor

We do not call AI Studio chat/completions with a web_search tool: that
endpoint only accepts type=function, and an LLM-shaped answer can invent
companies and salaries. This client maps title/snippet/url from the hit only.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urlparse

import httpx

from parser.dedup import dedup_vacancies, normalize_url
from parser.hh_parser import (
    INTERNSHIP_PATTERNS,
    ROLE_PATTERNS,
    _detect_category,
    _detect_format,
    _make_logo,
)

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
SEARCH_TYPE_RU = "SEARCH_TYPE_RU"
LOCALIZATION_RU = "LOCALIZATION_RU"

# Demo roles from the hero chips. Queries always include junior/стажировка
# plus Tatarstan / Innopolis / remote Russia, constrained to public job sites.
ROLE_TERMS = {
    "backend": "backend OR python OR java OR golang OR «разработчик»",
    "frontend": "frontend OR react OR vue OR typescript OR «фронтенд»",
    "data": "«data engineer» OR «data scientist» OR «machine learning» OR «дата-инженер»",
    "devops": "devops OR kubernetes OR sre OR «системный администратор»",
    "mobile": "android OR ios OR flutter OR kotlin OR swift OR «мобильный разработчик»",
    "qa": "qa OR тестировщик OR «test engineer»",
    "analytics": "«data analyst» OR «бизнес-аналитик» OR «аналитик данных»",
    "design": "«ux/ui» OR «product designer» OR «веб-дизайнер»",
    "pm": "«product manager» OR «project manager» OR «продакт»",
}

DEMO_ROLES = ("backend", "frontend", "data", "devops", "mobile")

JOB_HOST_SUFFIXES = (
    "hh.ru",
    "superjob.ru",
    "rabota.ru",
    "trudvsem.ru",
    "career.habr.com",
    "avito.ru",
)

VACANCY_PATH_MARKERS = (
    "/vacancy/",
    "/vacancy?",
    "/vacancies/",
    "/vakans",
    "/job/",
    "/jobs/",
    "/intern",
)

_HL_RE = re.compile(r"</?hlword>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_SALARY_RE = re.compile(
    r"(?:от\s*)?(\d[\d\s]{2,8})\s*(?:[–\-—]|до)\s*(\d[\d\s]{2,8})\s*(₽|руб\.?|RUR|RUB)?"
    r"|от\s*(\d[\d\s]{2,8})\s*(₽|руб\.?|RUR|RUB)"
    r"|до\s*(\d[\d\s]{2,8})\s*(₽|руб\.?|RUR|RUB)",
    re.I,
)

MISSING_SCOPE_HINT = (
    "Нужны scope yc.search-api.execute на API-ключе и роль "
    "search-api.webSearch.user (или search-api.executor) на сервисном аккаунте. "
    "Если текущий YANDEX_API_KEY только для YandexGPT, задайте отдельный "
    "YANDEX_SEARCH_API_KEY."
)


class SearchAPIError(RuntimeError):
    """Raised when Yandex Search API cannot be called or returns a hard failure."""


def search_api_key() -> str:
    return (
        os.getenv("YANDEX_SEARCH_API_KEY")
        or os.getenv("YANDEX_API_KEY")
        or os.getenv("YANDEX_IAM_TOKEN")
        or ""
    ).strip()


def folder_id() -> str:
    return (os.getenv("YANDEX_FOLDER_ID") or "").strip()


def search_endpoint() -> str:
    override = (os.getenv("YANDEX_SEARCH_API_URL") or "").strip()
    if override:
        if override.endswith("/v2/web/search"):
            return override
        return override.rstrip("/") + "/v2/web/search"
    return DEFAULT_SEARCH_URL


def is_configured() -> bool:
    return bool(search_api_key() and folder_id())


def missing_settings() -> list[str]:
    missing: list[str] = []
    if not search_api_key():
        missing.append("YANDEX_API_KEY или YANDEX_SEARCH_API_KEY")
    if not folder_id():
        missing.append("YANDEX_FOLDER_ID")
    return missing


def status() -> dict:
    key_source = "none"
    if (os.getenv("YANDEX_SEARCH_API_KEY") or "").strip():
        key_source = "YANDEX_SEARCH_API_KEY"
    elif (os.getenv("YANDEX_API_KEY") or "").strip():
        key_source = "YANDEX_API_KEY"
    elif (os.getenv("YANDEX_IAM_TOKEN") or "").strip():
        key_source = "YANDEX_IAM_TOKEN"
    return {
        "configured": is_configured(),
        "endpoint": search_endpoint(),
        "key_source": key_source,
        "missing": missing_settings(),
        "iam": {
            "api_key_scope": "yc.search-api.execute",
            "roles": ["search-api.webSearch.user", "search-api.executor"],
        },
    }


def disabled_message() -> str:
    missing = ", ".join(missing_settings()) or "credentials"
    return f"Yandex Search не настроен — задайте {missing}. {MISSING_SCOPE_HINT}"


def _auth_header() -> str:
    override = (os.getenv("YANDEX_SEARCH_API_KEY") or "").strip()
    if override:
        return f"Api-Key {override}"
    raw = (os.getenv("YANDEX_API_KEY") or "").strip()
    if raw:
        return f"Api-Key {raw}"
    iam = (os.getenv("YANDEX_IAM_TOKEN") or "").strip()
    if iam:
        return f"Bearer {iam}"
    return ""


def _clean_text(value: Optional[str]) -> str:
    text = _HL_RE.sub("", value or "")
    text = _TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).replace("\xa0", " ").strip()


def _element_text(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""
    return _clean_text("".join(node.itertext()))


def is_http_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def listing_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # kazan.hh.ru → hh.ru
    if host.endswith(".hh.ru") or host == "hh.ru":
        return "hh.ru"
    if host.endswith(".superjob.ru") or host == "superjob.ru":
        return "superjob.ru"
    if host.endswith(".rabota.ru") or host == "rabota.ru":
        return "rabota.ru"
    if host.endswith(".avito.ru") or host == "avito.ru":
        return "avito.ru"
    return host


def is_allowed_vacancy_url(url: str) -> bool:
    if not is_http_url(url):
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").lower()
    allowed_host = any(host == suffix or host.endswith("." + suffix) for suffix in JOB_HOST_SUFFIXES)
    if not allowed_host:
        return False
    if host.endswith("hh.ru"):
        return "/vacancy/" in path
    if host.endswith("avito.ru"):
        return "vakans" in path or "vacanc" in path
    return any(marker in path for marker in VACANCY_PATH_MARKERS)


def build_queries(role: Optional[str] = None) -> list[str]:
    roles = [role] if role and role in ROLE_TERMS else list(DEMO_ROLES if not role or role == "all" else [])
    if role and role not in ROLE_TERMS and role != "all":
        roles = [role]
    if not roles:
        roles = list(DEMO_ROLES)

    queries: list[str] = []
    for item in roles:
        terms = ROLE_TERMS.get(item, item)
        queries.append(
            f"site:hh.ru (junior OR стажировка OR intern) ({terms}) "
            f"(Казань OR Татарстан OR Иннополис)"
        )
        queries.append(
            f"site:hh.ru (junior OR стажировка OR intern) ({terms}) "
            f"(удалённ* OR удаленн* OR remote) (Россия OR РФ)"
        )
    # De-dup while keeping order; Search API rejects queryText > 400 chars.
    seen: set[str] = set()
    compact: list[str] = []
    for query in queries:
        query = query[:400]
        if query not in seen:
            seen.add(query)
            compact.append(query)
    return compact


def parse_search_xml(xml_text: str) -> tuple[list[dict], Optional[str]]:
    """Return (hits, error_message). Code 15 is 'nothing found' — not an error."""
    if not (xml_text or "").strip():
        return [], "Yandex Search: пустой XML"
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return [], f"Yandex Search: не разобрали XML ({exc})"

    error = root.find(".//error")
    if error is not None:
        code = error.get("code") or ""
        if code == "15":
            return [], None
        message = _clean_text(error.text) or "ошибка поиска"
        return [], f"Yandex Search: XML error {code} {message}".strip()

    hits: list[dict] = []
    for doc in root.iter("doc"):
        url = _element_text(doc.find("url"))
        title = _element_text(doc.find("title"))
        snippet = _element_text(doc.find("headline"))
        passages = doc.find("passages")
        if passages is not None:
            passage_text = " ".join(
                _element_text(p) for p in passages.findall("passage") if _element_text(p)
            )
            if passage_text:
                snippet = f"{snippet} {passage_text}".strip()
        domain = _element_text(doc.find("domain"))
        hits.append({"url": url, "title": title, "snippet": snippet, "domain": domain})
    return hits, None


def decode_raw_data(payload: dict) -> str:
    raw = payload.get("rawData")
    if not raw:
        raise SearchAPIError("Yandex Search: в ответе нет rawData")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    try:
        return base64.b64decode(raw).decode("utf-8", errors="replace")
    except Exception as exc:
        raise SearchAPIError(f"Yandex Search: не декодировали rawData ({exc})") from exc


_NOT_COMPANY = {
    "казани",
    "казань",
    "иннополисе",
    "иннополис",
    "татарстане",
    "татарстан",
    "россии",
    "россия",
    "москве",
    "москва",
    "офисе",
    "офис",
    "компании",
    "команду",
    "штат",
}


def _looks_like_company(name: str) -> bool:
    cleaned = name.strip(" ·|-«»\"'")
    if not (1 < len(cleaned) <= 80):
        return False
    if "http" in cleaned.lower() or cleaned.endswith("."):
        return False
    if cleaned.casefold().replace("ё", "е") in _NOT_COMPANY:
        return False
    if cleaned.count(" ") > 6:
        return False
    return True


def _extract_company(title: str, snippet: str) -> str:
    """Company only if it is already written in the hit. Never invent a name."""
    for text in (title, snippet):
        for sep in (" — ", " – ", " - ", " / "):
            if sep in text:
                right = text.rsplit(sep, 1)[-1].strip(" ·|-")
                if _looks_like_company(right):
                    return right
        match = re.search(r"\bв\s+([A-ZА-ЯЁ][\w.&+«»\"'\- ]{1,60})", text)
        if match:
            name = match.group(1).strip(" ·|-«»\"'")
            # "в Казани" / "в компании X" are locations or filler, not a firm.
            if name.casefold().startswith("компани"):
                name = name.split(None, 1)[1] if " " in name else ""
            if name and _looks_like_company(name):
                return name
    return ""


def _extract_salary(text: str) -> Optional[str]:
    match = _SALARY_RE.search(text or "")
    if not match:
        return None
    return _clean_text(match.group(0))


def _extract_location(text: str) -> str:
    lowered = (text or "").lower()
    if "иннополис" in lowered:
        return "Иннополис"
    if "казан" in lowered:
        return "Казань"
    if "альметьев" in lowered:
        return "Альметьевск"
    if "татарстан" in lowered:
        return "Татарстан"
    if any(token in lowered for token in ("удалён", "удален", "remote", "удаленн")):
        return "Remote РФ"
    return "не указано"


def _extract_format(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ("удалён", "удален", "remote")):
        return "remote"
    if any(token in lowered for token in ("гибрид", "hybrid")):
        return "hybrid"
    if any(token in lowered for token in ("офис", "office", "казан", "иннополис")):
        return "office"
    return _detect_format("")


def _detect_role_optional(title: str, snippet: str) -> Optional[str]:
    combined = (title + " " + snippet).lower()
    for role, patterns in ROLE_PATTERNS.items():
        if any(p in combined for p in patterns):
            return role
    return None


def map_search_hits(hits: list[dict], *, role: Optional[str] = None) -> list[dict]:
    """Map Yandex hits to vacancy cards. Drop rows without a real http(s) job URL."""
    cards: list[dict] = []
    for idx, hit in enumerate(hits):
        url = (hit.get("url") or "").strip()
        if not is_allowed_vacancy_url(url):
            continue
        title = _clean_text(hit.get("title") or "")
        snippet = _clean_text(hit.get("snippet") or "")
        if not title:
            continue
        host = listing_host(url)
        combined = f"{title} {snippet}"
        company = _extract_company(title, snippet)
        salary = _extract_salary(combined)
        location = _extract_location(combined)
        fmt = _extract_format(combined)
        detected = _detect_role_optional(title, snippet)
        card_role = detected or (role if role and role != "all" else None) or "backend"
        category = _detect_category(title, "")
        if category == "vacancy" and any(p in title.lower() for p in INTERNSHIP_PATTERNS):
            category = "internship"
        logo, logo_color, logo_text = _make_logo(company or title, idx)
        summary = snippet or f"{title}. Страница вакансии: {url}"
        tags = [
            "стажировка" if category == "internship" else "junior",
            card_role,
            fmt,
            location,
        ]
        digest = hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:12]
        cards.append(
            {
                "id": f"ys_{digest}",
                "title": title,
                "company": company,
                "logo": logo,
                "logoColor": logo_color,
                "logoText": logo_text,
                "category": category,
                "role": card_role,
                "format": fmt,
                "location": location,
                "salary": salary,
                "source": {
                    "type": "yandex",
                    "name": f"Yandex Search → {host}",
                    "url": url,
                },
                "dateLabel": "из поиска",
                "dateSort": 50,
                "tags": tags,
                "aiSummary": summary,
                "url": url,
            }
        )
    return cards


def _permission_message(status_code: int, body: str) -> str:
    snippet = _SPACE_RE.sub(" ", (body or "")[:240]).strip()
    base = f"Yandex Search: HTTP {status_code}"
    if snippet:
        base = f"{base} {snippet}"
    if status_code in {401, 403}:
        return f"{base}. {MISSING_SCOPE_HINT}"
    return base


async def web_search(query: str, *, timeout: float = 20) -> list[dict]:
    """One Search API request → list of raw hits. Raises SearchAPIError on failure."""
    if not is_configured():
        raise SearchAPIError(disabled_message())
    if not query or len(query) > 400:
        raise SearchAPIError("Yandex Search: пустой или слишком длинный запрос")

    payload = {
        "query": {
            "searchType": SEARCH_TYPE_RU,
            "queryText": query,
            "familyMode": "FAMILY_MODE_NONE",
            "page": "0",
        },
        "groupSpec": {
            "groupMode": "GROUP_MODE_FLAT",
            "groupsOnPage": "10",
            "docsInGroup": "1",
        },
        "l10n": LOCALIZATION_RU,
        "folderId": folder_id(),
        "responseFormat": "FORMAT_XML",
    }
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "User-Agent": (
            "CareerNavigator21/1.0 "
            "(+https://github.com/vasiliymarkitan/tatarsan-school21-career-navigator)"
        ),
    }
    folder = folder_id()
    if folder:
        headers["x-folder-id"] = folder

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(search_endpoint(), headers=headers, json=payload)

    if response.status_code >= 400:
        raise SearchAPIError(_permission_message(response.status_code, response.text))

    try:
        data = response.json()
    except Exception as exc:
        raise SearchAPIError(f"Yandex Search: ответ не JSON ({exc})") from exc

    xml_text = decode_raw_data(data)
    hits, xml_error = parse_search_xml(xml_text)
    if xml_error:
        raise SearchAPIError(xml_error)
    return hits


async def fetch_yandex_vacancies(role: Optional[str] = None) -> tuple[list[dict], list[str]]:
    """Search public vacancy pages for a role (or the demo role set)."""
    if not is_configured():
        return [], [disabled_message()]

    queries = build_queries(role)
    errors: list[str] = []
    hits: list[dict] = []

    async def _one(query: str) -> tuple[list[dict], Optional[str]]:
        try:
            return await web_search(query), None
        except SearchAPIError as exc:
            return [], str(exc)
        except Exception as exc:
            return [], f"Yandex Search: {exc}"

    results = await asyncio.gather(*[_one(q) for q in queries])
    seen_urls: set[str] = set()
    for batch, error in results:
        if error:
            errors.append(error)
            continue
        for hit in batch:
            url = normalize_url(hit.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            hits.append(hit)

    cards = dedup_vacancies(map_search_hits(hits, role=role))
    uniq_errors: list[str] = []
    seen_err: set[str] = set()
    for message in errors:
        if message and message not in seen_err:
            seen_err.add(message)
            uniq_errors.append(message)
    errors = uniq_errors
    logger.info("Yandex Search role=%s: %d hits → %d cards, %d errors", role, len(hits), len(cards), len(errors))
    if not cards and not errors:
        # Successful empty search is not a transport failure.
        logger.info("Yandex Search role=%s: пустая выдача без ошибки API", role)
    return cards, errors
