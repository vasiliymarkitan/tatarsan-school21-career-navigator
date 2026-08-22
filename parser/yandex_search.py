"""
Yandex Search API (AI Studio docs) — live vacancy pages, no invented cards.

Official text-search contract (cloudapi proto, not guessed):
  yandex/cloud/searchapi/v2/search_service.proto
  Docs: https://aistudio.yandex.ru/docs/ru/search-api/concepts/

Sync REST:  POST https://searchapi.api.cloud.yandex.net/v2/web/search
Deferred:   POST …/v2/web/searchAsync  (Operation + poll; not used here)

Auth: Authorization: Api-Key <key>  (AI Studio key + folderId in the body).
IAM Bearer is an alternative. The folder must have a billing account.

Text web search returns WebSearchResponse.raw_data = XML or HTML bytes
(REST JSON wraps that as base64 "rawData"). There is NO {title,url,snippet}
JSON for text search. Structured JSON exists on image-by-image search,
not on /v2/web/search.

Parse only Yandex XML: <doc> → <url>, <title>, <passages>/<headline>.
Query operators site: / host: / lang: are supported.

The AI Studio agent Web Search *tool* (model calls a tool) is a different
product. Cards are built from Search API XML + real URLs only.

If YANDEX_API_KEY cannot call Search API (401/403), return honest errors[].
Roles/scope if the key is GPT-only: search-api.webSearch.user and/or
search-api.executor; API key scope yc.search-api.execute.
Optional override: YANDEX_SEARCH_API_KEY (do not commit).
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

from parser.dedup import dedup_news, dedup_vacancies, normalize_url
from parser.hh_parser import (
    INTERNSHIP_PATTERNS,
    ROLE_PATTERNS,
    _detect_category,
    _detect_format,
    _make_logo,
)
from parser.tg_parser import CHANNELS, _extract_tags, _pick_icon

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
SEARCH_TYPE_RU = "SEARCH_TYPE_RU"
LOCALIZATION_RU = "LOCALIZATION_RU"
# Proto: max_passages = 1-5; groups_on_page = 1-100; docs_in_group = 1-3
MAX_PASSAGES = 3
GROUPS_ON_PAGE = 10
DOCS_IN_GROUP = 1
DEFAULT_UA = (
    "CareerNavigator21/1.0 "
    "(+https://github.com/vasiliymarkitan/tatarsan-school21-career-navigator)"
)

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

# Assigned IT news sources from the brief / repo — not extra websites.
NEWS_CHANNEL_IDS = tuple(channel_id for channel_id, _handle, _kind in CHANNELS)
NEWS_HANDLE_BY_ID = {channel_id: handle for channel_id, handle, _kind in CHANNELS}
TELEGRAM_NEWS_HOSTS = ("t.me", "telegram.me")

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
    "Ключ AI Studio часто уже умеет Search API (Authorization: Api-Key, folderId в теле). "
    "Если ответ 401/403: на сервисе нужны роли search-api.webSearch.user и/или "
    "search-api.executor, у ключа — scope yc.search-api.execute; к каталогу должен "
    "быть привязан биллинг-аккаунт. Отдельный ключ — YANDEX_SEARCH_API_KEY (не коммитить)."
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


def news_channel_from_url(url: str) -> Optional[str]:
    """Return assigned channel id (kazanit, …) or None. No extra hosts."""
    if not is_http_url(url):
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in TELEGRAM_NEWS_HOSTS:
        return None
    parts = [part for part in (parsed.path or "").split("/") if part]
    if not parts:
        return None
    if parts[0].lower() == "s":
        if len(parts) < 2:
            return None
        channel = parts[1].lower()
    else:
        channel = parts[0].lower()
    if channel.startswith("@"):
        channel = channel[1:]
    if channel in NEWS_CHANNEL_IDS:
        return channel
    return None


def is_allowed_news_url(url: str) -> bool:
    return news_channel_from_url(url) is not None


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
            f"site:hh.ru lang:ru (junior OR стажировка OR intern) ({terms}) "
            f"(Казань OR Татарстан OR Иннополис)"
        )
        queries.append(
            f"site:hh.ru lang:ru (junior OR стажировка OR intern) ({terms}) "
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


def build_news_queries() -> list[str]:
    """Search the four assigned channels. No extra hosts.

    Live Search API (22 Aug 2026): ``site:t.me/<channel>`` plus AND-keywords
    returned 0 hits / 0 errors. Official query language uses ``url:host/path/*``
    for a URL prefix and ``site:t.me`` only as a host. Extra AND tokens and
    ``lang:ru`` over-constrain Telegram pages that the API may not tag as ru.
    Cards are still filtered to these four channels after the search.
    """
    queries: list[str] = []
    seen: set[str] = set()
    for channel_id in NEWS_CHANNEL_IDS:
        variants = (
            f"url:t.me/{channel_id}/*",
            f"url:t.me/s/{channel_id}/*",
            f"@{channel_id} site:t.me",
        )
        for query in variants:
            query = query[:400]
            if query not in seen:
                seen.add(query)
                queries.append(query)
    return queries


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
    """Text search returns rawData (base64 XML/HTML), not a JSON hit list."""
    if not isinstance(payload, dict):
        raise SearchAPIError("Yandex Search: ответ не объект JSON-обёртки rawData")
    if "title" in payload and "url" in payload and "rawData" not in payload:
        raise SearchAPIError(
            "Yandex Search: текстовый поиск не отдаёт JSON {title,url,snippet}; "
            "ожидали rawData (XML)"
        )
    raw = payload.get("rawData")
    if not raw:
        raise SearchAPIError("Yandex Search: в ответе нет rawData (текстовый поиск = XML/HTML)")
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        try:
            text = base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception as exc:
            raise SearchAPIError(f"Yandex Search: не декодировали rawData ({exc})") from exc
    stripped = text.lstrip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        raise SearchAPIError(
            "Yandex Search: пришёл HTML (FORMAT_HTML). Для карточек нужен FORMAT_XML."
        )
    return text


def build_web_search_body(query: str) -> dict:
    """WebSearchRequest JSON as in search_service.proto (camelCase REST)."""
    return {
        "query": {
            "searchType": SEARCH_TYPE_RU,
            "queryText": query,
            "familyMode": "FAMILY_MODE_NONE",
            "page": 0,
        },
        "groupSpec": {
            "groupMode": "GROUP_MODE_FLAT",
            "groupsOnPage": GROUPS_ON_PAGE,
            "docsInGroup": DOCS_IN_GROUP,
        },
        "maxPassages": MAX_PASSAGES,
        "l10n": LOCALIZATION_RU,
        "folderId": folder_id(),
        "responseFormat": "FORMAT_XML",
        "userAgent": DEFAULT_UA,
    }


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


def map_news_hits(hits: list[dict]) -> list[dict]:
    """Map Yandex hits to news cards. Only the four assigned t.me channels."""
    cards: list[dict] = []
    for hit in hits:
        url = (hit.get("url") or "").strip()
        channel_id = news_channel_from_url(url)
        if not channel_id:
            continue
        title = _clean_text(hit.get("title") or "")
        snippet = _clean_text(hit.get("snippet") or "")
        if not title:
            continue
        handle = NEWS_HANDLE_BY_ID[channel_id]
        combined = f"{title} {snippet}"
        digest = hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:12]
        summary = snippet or title
        if len(summary) > 300:
            summary = summary[:300].rstrip() + "…"
        cards.append(
            {
                "id": f"ys_news_{digest}",
                "title": title[:90],
                "source": handle,
                "sourceType": "telegram",
                "dateLabel": "из поиска",
                "dateSort": 50,
                "tags": _extract_tags(combined),
                "summary": summary,
                "icon": _pick_icon(combined),
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

    payload = build_web_search_body(query)
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "User-Agent": DEFAULT_UA,
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


async def _collect_hits(queries: list[str]) -> tuple[list[dict], list[str]]:
    """Run Search API queries, merge unique hits, collect honest errors."""
    if not is_configured():
        return [], [disabled_message()]

    async def _one(query: str) -> tuple[list[dict], Optional[str]]:
        try:
            return await web_search(query), None
        except SearchAPIError as exc:
            return [], str(exc)
        except Exception as exc:
            return [], f"Yandex Search: {exc}"

    results = await asyncio.gather(*[_one(query) for query in queries])
    hits: list[dict] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    seen_err: set[str] = set()
    for batch, error in results:
        if error:
            if error not in seen_err:
                seen_err.add(error)
                errors.append(error)
            continue
        for hit in batch:
            url = normalize_url(hit.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            hits.append(hit)
    return hits, errors


async def fetch_yandex_vacancies(role: Optional[str] = None) -> tuple[list[dict], list[str]]:
    """Search public vacancy pages for a role (or the demo role set)."""
    hits, errors = await _collect_hits(build_queries(role))
    cards = dedup_vacancies(map_search_hits(hits, role=role))
    logger.info("Yandex Search role=%s: %d hits → %d cards, %d errors", role, len(hits), len(cards), len(errors))
    if not cards and not errors:
        # Successful empty search is not a transport failure.
        logger.info("Yandex Search role=%s: пустая выдача без ошибки API", role)
    return cards, errors


async def fetch_yandex_news() -> tuple[list[dict], list[str]]:
    """Search the four assigned Telegram channels via Yandex Search API."""
    queries = build_news_queries()
    logger.info("Yandex Search news queries=%d first=%s", len(queries), queries[0] if queries else "")
    hits, errors = await _collect_hits(queries)
    cards = dedup_news(map_news_hits(hits))
    cards.sort(key=lambda item: item.get("dateSort", 99))
    cards = cards[:20]
    logger.info("Yandex Search news: %d hits → %d cards, %d errors", len(hits), len(cards), len(errors))
    if not cards and not errors:
        logger.info("Yandex Search news: пустая выдача без ошибки API")
    return cards, errors
