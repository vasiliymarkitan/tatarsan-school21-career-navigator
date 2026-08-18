"""
Парсер вакансий с hh.ru через публичный API (без токена).
Документация: https://api.hh.ru/openapi/redoc
"""
import os
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from parser.dedup import dedup_vacancies

logger = logging.getLogger(__name__)

HH_API = "https://api.hh.ru/vacancies"

# Contact must not leak a personal mailbox. Override via HH_USER_AGENT if hh.ru asks for one.
DEFAULT_UA = (
    "CareerNavigator21/1.0 "
    "(+https://github.com/vasiliymarkitan/tatarsan-school21-career-navigator)"
)


def request_headers() -> dict[str, str]:
    ua = (os.getenv("HH_USER_AGENT") or DEFAULT_UA).strip()
    return {
        "User-Agent": ua,
        "HH-User-Agent": ua,
        "Accept-Language": "ru-RU,ru;q=0.9",
    }


HEADERS = request_headers()

# Поисковые запросы: Татарстан + удалённая Россия
SEARCHES = [
    {"text": "junior разработчик OR junior developer", "area": "88", "experience": "noExperience", "per_page": "20"},
    {"text": "стажировка программист OR стажёр разработчик", "area": "88", "per_page": "20"},
    {"text": "junior developer OR junior разработчик", "schedule": "remote", "experience": "noExperience", "per_page": "15"},
    {"text": "стажировка IT OR intern developer", "schedule": "remote", "per_page": "15"},
]

ROLE_PATTERNS = {
    "frontend": ["frontend", "react", "vue", "angular", "javascript", "typescript", "html/css", "верстальщик", "фронтенд"],
    "mobile":   ["android", "ios", "mobile", "kotlin", "swift", "flutter", "react native", "xamarin"],
    "devops":   ["devops", "sre ", "kubernetes", "k8s", "ansible", "terraform", "ci/cd", "linux-администратор", "системный администратор"],
    "data":     ["data engineer", "data scientist", "machine learning", "ml engineer", "нейро", "spark", "hadoop", "дата-инженер", "ml-разработчик"],
    "qa":       ["qa ", "тестировщик", "test engineer", "quality assurance", "selenium", "автоматизатор тестирования", "qa инженер"],
    "analytics": ["аналитик данных", "бизнес-аналитик", "data analyst", "business analyst", "bi разработчик", "power bi"],
    "design":   ["ux/ui", "ux-дизайнер", "ui-дизайнер", "product designer", "web-дизайнер"],
    "pm":       ["product manager", "project manager", "продакт менеджер", "scrum master", "agile coach"],
    "backend":  ["backend", "python", "java ", "golang", "go-разработчик", "php", "ruby", "node.js", "spring", "django", "fastapi", "бэкенд", "серверный разработчик", ".net", "c# разработчик", "c++ разработчик"],
}

INTERNSHIP_PATTERNS = [
    "стажировка", "стажёр", "стажер", "intern", "практика", "практикант",
    "summer internship", "без опыта", "учебная практика",
]

LOGO_COLORS = [
    "#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa",
    "#00897b", "#e91e63", "#3949ab", "#00acc1", "#7cb342",
]


def _detect_role(title: str, snippet_text: str) -> str:
    combined = (title + " " + snippet_text).lower()
    for role, patterns in ROLE_PATTERNS.items():
        if any(p in combined for p in patterns):
            return role
    return "backend"


def _detect_category(title: str, experience_id: str) -> str:
    title_lower = title.lower()
    if any(p in title_lower for p in INTERNSHIP_PATTERNS):
        return "internship"
    if experience_id in ("noExperience",):
        # не всегда стажировка, но может быть
        if any(p in title_lower for p in ["стаж", "intern", "практик"]):
            return "internship"
    return "vacancy"


def _detect_format(schedule_id: str) -> str:
    return {"remote": "remote", "flexible": "hybrid"}.get(schedule_id, "office")


def _format_salary(salary: Optional[dict]) -> Optional[str]:
    if not salary:
        return None
    frm = salary.get("from")
    to = salary.get("to")
    cur = "₽" if salary.get("currency") == "RUR" else salary.get("currency", "₽")
    if frm and to:
        return f"{frm:,} – {to:,} {cur}".replace(",", " ")
    if frm:
        return f"от {frm:,} {cur}".replace(",", " ")
    if to:
        return f"до {to:,} {cur}".replace(",", " ")
    return None


def _time_ago(published_at: str) -> tuple[str, int]:
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours = int((now - dt).total_seconds() / 3600)
        if hours < 1:
            return "только что", 0
        if hours < 24:
            return f"{hours} ч. назад", 0
        days = hours // 24
        if days == 1:
            return "1 день назад", 1
        if days < 5:
            return f"{days} дня назад", days
        if days < 14:
            return f"{days} дней назад", days
        return dt.strftime("%d.%m.%Y"), days
    except Exception:
        return "недавно", 99


def _generate_summary(title: str, employer: str, snippet: dict) -> str:
    raw_req = snippet.get("requirement") or ""
    raw_resp = snippet.get("responsibility") or ""
    req = re.sub(r"<[^>]+>", "", raw_req).strip()[:250]
    resp = re.sub(r"<[^>]+>", "", raw_resp).strip()[:250]
    parts = []
    if resp:
        parts.append(resp.rstrip(".") + ".")
    if req:
        parts.append(f"Требования: {req.rstrip('.')}.")
    if parts:
        return " ".join(parts)
    return f"Вакансия {title} от компании {employer}. Подробности на hh.ru."


def _make_logo(name: str, idx: int) -> tuple[str, str, str]:
    words = [w for w in re.split(r"\s+", name) if w]
    if len(words) >= 2:
        abbr = (words[0][0] + words[1][0]).upper()
    else:
        abbr = name[:2].upper()
    color = LOGO_COLORS[idx % len(LOGO_COLORS)]
    return abbr, color, "#fff"


def _map_vacancy(item: dict, idx: int) -> dict:
    vid = f"hh_{item['id']}"
    title = item.get("name", "")
    employer = item.get("employer", {})
    company = employer.get("name", "Компания")
    area = item.get("area", {}).get("name", "Россия")
    published_at = item.get("published_at", "")
    salary = _format_salary(item.get("salary"))
    schedule_id = item.get("schedule", {}).get("id", "fullDay")
    experience_id = item.get("experience", {}).get("id", "between1And3")
    snippet = item.get("snippet", {})
    snippet_text = (snippet.get("requirement") or "") + " " + (snippet.get("responsibility") or "")

    role = _detect_role(title, snippet_text)
    category = _detect_category(title, experience_id)
    fmt = _detect_format(schedule_id)
    date_label, date_sort = _time_ago(published_at)
    summary = _generate_summary(title, company, snippet)
    logo, logo_color, logo_text = _make_logo(company, idx)

    # Карточка ведёт на саму вакансию, не на витрину работодателя.
    card_url = item.get("alternate_url") or (f"https://hh.ru/vacancy/{item.get('id')}" if item.get("id") else "")
    source_url = card_url or "https://hh.ru"

    tags = [
        "стажировка" if category == "internship" else "junior",
        role,
        fmt,
        area,
    ]
    # добавляем языки/фреймворки из названия
    techs = re.findall(r"\b(Python|Java|Go|Golang|Kotlin|Swift|React|Vue|Angular|TypeScript|JavaScript|PHP|Ruby|Rust|C\+\+|C#|\.NET|Flutter|Spark|SQL)\b", title, re.I)
    tags += [t.strip() for t in techs]

    return {
        "id": vid,
        "title": title,
        "company": company,
        "logo": logo,
        "logoColor": logo_color,
        "logoText": logo_text,
        "category": category,
        "role": role,
        "format": fmt,
        "location": area,
        "salary": salary,
        "source": {
            "type": "hh",
            "name": "hh.ru",
            "url": source_url,
        },
        "dateLabel": date_label,
        "dateSort": date_sort,
        "tags": tags,
        "aiSummary": summary,
        "url": card_url,
    }


ROLE_SEARCH_TEXT = {
    "backend": "junior backend OR junior python OR стажировка python OR стажёр backend",
    "frontend": "junior frontend OR junior react OR стажировка frontend",
    "data": "junior data OR стажировка data scientist OR junior ML",
    "devops": "junior devops OR стажировка devops",
    "mobile": "junior android OR junior ios OR стажировка mobile",
    "qa": "junior qa OR стажировка тестировщик",
    "analytics": "junior аналитик данных OR стажировка аналитик",
    "design": "junior ux/ui OR стажировка дизайнер",
    "pm": "junior product manager OR стажировка project manager",
}


def _hh_error_text(resp) -> str:
    snippet = ""
    try:
        snippet = (resp.text or "").replace("\n", " ")[:180].strip()
    except Exception:
        snippet = ""
    if snippet:
        return f"hh.ru: HTTP {resp.status_code} {snippet}"
    return f"hh.ru: HTTP {resp.status_code}"


async def _hh_collect(params_list: list[dict]) -> tuple[list[dict], list[str]]:
    """Run hh.ru searches and surface HTTP/network failures instead of swallowing them."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    results: list[dict] = []
    idx = 0

    async with httpx.AsyncClient(headers=request_headers(), timeout=15) as client:
        responses = await asyncio.gather(
            *[client.get(HH_API, params=params) for params in params_list],
            return_exceptions=True,
        )

    for resp in responses:
        if isinstance(resp, Exception):
            logger.warning("hh.ru request failed: %s", resp)
            errors.append(f"hh.ru: {resp}")
            continue
        if resp.status_code != 200:
            message = _hh_error_text(resp)
            logger.warning("%s", message)
            errors.append(message)
            continue
        try:
            data = resp.json()
        except Exception as exc:
            errors.append(f"hh.ru: ответ не JSON ({exc})")
            continue
        for item in data.get("items", []):
            hh_id = item.get("id")
            if not hh_id or hh_id in seen_ids:
                continue
            seen_ids.add(hh_id)
            try:
                results.append(_map_vacancy(item, idx))
                idx += 1
            except Exception as exc:
                logger.warning("Failed to map vacancy %s: %s", hh_id, exc)

    results = dedup_vacancies(results)
    logger.info("hh.ru: fetched %d vacancies after dedup, %d errors", len(results), len(errors))
    return results, errors


async def fetch_vacancies_by_query(
    text: str,
    area: str = "88",
    schedule: str | None = None,
    per_page: int = 15,
) -> list[dict]:
    """Targeted hh.ru search for the career agent."""
    params: dict = {
        "text": text,
        "area": area,
        "per_page": str(per_page),
        "experience": "noExperience",
    }
    if schedule:
        params["schedule"] = schedule
    items, _errors = await _hh_collect([params])
    logger.info("Agent hh.ru search '%s': %d results", text, len(items))
    return items


async def fetch_hh_vacancies() -> tuple[list[dict], list[str]]:
    return await _hh_collect(SEARCHES)


async def fetch_hh_vacancies_for_role(role: str | None) -> tuple[list[dict], list[str]]:
    if not role or role == "all":
        return await fetch_hh_vacancies()
    text = ROLE_SEARCH_TEXT.get(role, f"junior {role} OR стажировка {role}")
    params = [
        {"text": text, "area": "88", "experience": "noExperience", "per_page": "20"},
        {"text": text, "schedule": "remote", "experience": "noExperience", "per_page": "15"},
    ]
    return await _hh_collect(params)
