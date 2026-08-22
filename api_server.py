"""
Карьерный Навигатор 21 — FastAPI backend
Запуск: uvicorn api_server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Cookie, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from ai import provider as llm
from auth_utils import (
    AUTH_COOKIE,
    JWT_EXPIRE_DAYS,
    check_auth_date,
    create_jwt,
    decode_jwt,
    is_jwt_secret_configured,
    verify_telegram_hash,
)
from digest import builder as digest_builder
from digest import scheduler as digest_scheduler
from digest import store as digest_store
from digest import telegram as digest_telegram
from parser.dedup import dedup_news, dedup_vacancies
from parser.hh_parser import fetch_hh_vacancies_for_role
from parser.tg_parser import CHANNELS, fetch_tg_news
from parser import yandex_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL_SEC") or 30 * 60)
DIGEST_TICK_SEC = 60
DISABLE_BACKGROUND = os.getenv("CN21_DISABLE_BACKGROUND", "").strip() in {"1", "true", "yes"}

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}
_bot_username: str = os.getenv("BOT_USERNAME", "").strip()

REAL_SOURCES = [
    {"type": "hh", "name": "hh.ru", "url": "https://api.hh.ru/vacancies", "kind": "vacancies"},
    {
        "type": "yandex",
        "name": "Yandex Search → hh.ru",
        "url": yandex_search.DEFAULT_SEARCH_URL,
        "kind": "vacancies",
    },
    *[
        {
            "type": "telegram",
            "name": handle,
            "url": f"https://t.me/s/{channel_id}",
            "kind": "news",
        }
        for channel_id, handle, _ in CHANNELS
    ],
]

_role_locks: dict[str, asyncio.Lock] = {}
_news_lock = asyncio.Lock()

_cache: dict = {
    "vacancies": [],
    "news": [],
    "last_update": None,
    "fetch_error": None,
    "source_errors": [],
}


def _last_update_label() -> str:
    dt = _cache["last_update"]
    if not dt:
        return "ещё не обновлялось"
    now = datetime.now(timezone.utc)
    mins = int((now - dt).total_seconds() / 60)
    if mins < 1:
        return "только что"
    if mins < 60:
        return f"{mins} мин. назад"
    hours = mins // 60
    return f"{hours} ч. назад"


def _lock_for(role: str) -> asyncio.Lock:
    lock = _role_locks.get(role)
    if lock is None:
        lock = asyncio.Lock()
        _role_locks[role] = lock
    return lock


def _unpack_fetch(result, label: str) -> tuple[list, list[str]]:
    if isinstance(result, Exception):
        logger.error("%s parser error: %s", label, result)
        return [], [f"{label}: {result}"]
    if isinstance(result, tuple) and len(result) == 2:
        items, errors = result
        return list(items or []), list(errors or [])
    if isinstance(result, list):
        return result, []
    return [], [f"{label}: unexpected result"]


def _store_errors(source_errors: list[str]) -> None:
    # Preserve unique messages, keep order.
    seen: set[str] = set()
    unique: list[str] = []
    for item in source_errors:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    _cache["source_errors"] = unique
    _cache["fetch_error"] = "; ".join(unique) if unique else None


def _cache_has_role(role: Optional[str]) -> bool:
    vacancies = _cache["vacancies"]
    if not vacancies:
        return False
    if not role or role == "all":
        return True
    return any(item.get("role") == role for item in vacancies)


async def _ingest_role(role: Optional[str]) -> tuple[list[dict], list[str]]:
    """hh.ru (if it works) + Yandex Search for one role or the demo set."""
    hh_out, ys_out = await asyncio.gather(
        fetch_hh_vacancies_for_role(role),
        yandex_search.fetch_yandex_vacancies(role),
        return_exceptions=True,
    )
    hh_items, hh_errors = _unpack_fetch(hh_out, "hh.ru")
    ys_items, ys_errors = _unpack_fetch(ys_out, "Yandex Search")
    merged = dedup_vacancies(list(hh_items) + list(ys_items))
    return merged, hh_errors + ys_errors


async def _ensure_role_vacancies(role: Optional[str]) -> tuple[list[dict], list[str], bool]:
    """On-demand search when the cache has no cards for this role (or no role at all)."""
    key = (role or "all").strip().lower() or "all"
    if _cache_has_role(key if key != "all" else None):
        return list(_cache["vacancies"]), list(_cache["source_errors"]), False

    async with _lock_for(key):
        if _cache_has_role(key if key != "all" else None):
            return list(_cache["vacancies"]), list(_cache["source_errors"]), False
        items, errors = await _ingest_role(None if key == "all" else key)
        _cache["vacancies"] = dedup_vacancies(list(_cache["vacancies"]) + items)
        _cache["last_update"] = datetime.now(timezone.utc)
        _store_errors(errors)
        return list(_cache["vacancies"]), list(_cache["source_errors"]), True


async def _ingest_news() -> tuple[list[dict], list[str]]:
    """t.me/s preview (if reachable) + Yandex Search over the same four channels."""
    tg_out, ys_out = await asyncio.gather(
        fetch_tg_news(),
        yandex_search.fetch_yandex_news(),
        return_exceptions=True,
    )
    tg_items, tg_errors = _unpack_fetch(tg_out, "telegram")
    ys_items, ys_errors = _unpack_fetch(ys_out, "Yandex Search")
    merged = dedup_news(list(tg_items) + list(ys_items))
    merged.sort(key=lambda item: item.get("dateSort", 99))
    return merged[:20], tg_errors + ys_errors


async def _ensure_news() -> tuple[list[dict], list[str], bool]:
    """On-demand news search when the cache is still empty."""
    if _cache["news"]:
        return list(_cache["news"]), list(_cache["source_errors"]), False

    async with _news_lock:
        if _cache["news"]:
            return list(_cache["news"]), list(_cache["source_errors"]), False
        items, errors = await _ingest_news()
        _cache["news"] = items
        _cache["last_update"] = datetime.now(timezone.utc)
        _store_errors(list(_cache["source_errors"]) + errors)
        return list(_cache["news"]), list(_cache["source_errors"]), True


async def _refresh():
    logger.info("Запуск парсинга источников…")
    vac_out, news_out = await asyncio.gather(
        _ingest_role(None),
        _ingest_news(),
        return_exceptions=True,
    )

    vacancies, vac_errors = _unpack_fetch(vac_out, "vacancies")
    news, news_errors = _unpack_fetch(news_out, "news")
    source_errors = vac_errors + news_errors

    if llm.is_enabled() and vacancies:
        try:
            vacancies = await llm.enrich_vacancies(vacancies, limit=5)
            logger.info("%s: enriched top-5 vacancy summaries", llm.status()["provider"])
        except Exception as exc:
            logger.warning("LLM enrich failed: %s", exc)
            source_errors.append(f"llm: {exc}")

    _cache["vacancies"] = vacancies
    _cache["news"] = news
    _cache["last_update"] = datetime.now(timezone.utc)
    _store_errors(source_errors)
    logger.info(
        "Парсинг завершён: %d вакансий (hh.ru + Yandex Search), %d новостей (t.me/s + Yandex Search)",
        len(vacancies),
        len(news),
    )


async def _refresh_loop():
    while True:
        try:
            await _refresh()
        except Exception as exc:
            logger.error("Refresh loop error: %s", exc)
            _cache["fetch_error"] = str(exc)
        await asyncio.sleep(REFRESH_INTERVAL)


async def _digest_loop():
    while True:
        try:
            await digest_scheduler.tick(_cache["vacancies"], _cache["news"])
        except Exception as exc:
            logger.warning("Digest tick error: %s", exc)
        await asyncio.sleep(DIGEST_TICK_SEC)


async def _fetch_bot_username() -> str:
    if not BOT_TOKEN:
        return ""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
            data = response.json()
            return data.get("result", {}).get("username", "") or ""
    except Exception as exc:
        logger.warning("Не удалось получить username бота: %s", exc)
        return ""


def _current_user(cn21_session: Optional[str]) -> Optional[dict]:
    if not cn21_session or not is_jwt_secret_configured(JWT_SECRET):
        return None
    return decode_jwt(cn21_session, JWT_SECRET)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_username
    if not is_jwt_secret_configured(JWT_SECRET):
        logger.warning("JWT_SECRET не задан или слабый — Telegram-сессии отключены")
    if not _bot_username:
        _bot_username = await _fetch_bot_username()
    if _bot_username:
        logger.info("Telegram бот: @%s", _bot_username)
    else:
        logger.warning("BOT_USERNAME и TELEGRAM_BOT_TOKEN не заданы — Telegram-авторизация отключена")
    if not DISABLE_BACKGROUND:
        asyncio.create_task(_refresh_loop())
        asyncio.create_task(_digest_loop())
    yield


app = FastAPI(title="Карьерный Навигатор 21 API", version="2.2.0", lifespan=lifespan)


class CareerAdviceRequest(BaseModel):
    role: Optional[str] = None
    skills: Optional[str] = None
    goals: Optional[str] = None


class SummarizeRequest(BaseModel):
    title: str
    company: str
    requirement: Optional[str] = ""
    responsibility: Optional[str] = ""


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class DigestSettingsIn(BaseModel):
    schedule: str
    time: str
    roles: List[str] = Field(default_factory=list)


def _vacancy_payload(category, role, fmt, q, limit, offset):
    data = list(_cache["vacancies"])
    if category and category != "all":
        data = [v for v in data if v.get("category") == category]
    if role and role != "all":
        data = [v for v in data if v.get("role") == role]
    if fmt and fmt != "all":
        data = [v for v in data if v.get("format") == fmt]
    if q:
        q_lower = q.lower()
        data = [
            v
            for v in data
            if q_lower
            in (v.get("title", "") + " " + v.get("company", "") + " " + " ".join(v.get("tags", []))).lower()
        ]
    total = len(data)
    return {
        "total": total,
        "vacancies": data[offset : offset + limit],
        "has_more": offset + limit < total,
        "lastUpdate": _last_update_label(),
        "source": "live" if _cache["last_update"] else "empty",
        "live": bool(_cache["vacancies"]),
        "errors": list(_cache["source_errors"]),
    }


@app.get("/")
async def root():
    return FileResponse("web/index.html")


@app.get("/api/live-vacancies")
async def get_live_vacancies(
    category: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    role_key = (role or "").strip().lower() or None
    if role_key == "all":
        role_key = None
    if not _cache_has_role(role_key):
        _items, errors, _attempted = await _ensure_role_vacancies(role_key)
        payload = _vacancy_payload(category, role, format, q, limit, offset)
        payload["errors"] = list(errors)
        if not payload["vacancies"] and errors:
            payload["live"] = False
            payload["source"] = "error"
            return JSONResponse(payload, status_code=503)
        return JSONResponse(payload)
    return JSONResponse(_vacancy_payload(category, role, format, q, limit, offset))


@app.get("/api/live-news")
async def get_live_news(limit: int = Query(20, le=50)):
    news, errors, _attempted = await _ensure_news()
    payload = {
        "news": news[:limit],
        "lastUpdate": _last_update_label(),
        "source": "live" if news else ("error" if errors else ("live" if _cache["last_update"] else "empty")),
        "live": bool(news),
        "errors": list(errors),
    }
    if not news and errors:
        payload["live"] = False
        payload["source"] = "error"
        return JSONResponse(payload, status_code=503)
    return JSONResponse(payload)


@app.get("/api/sources")
async def get_sources():
    return JSONResponse(
        {
            "sources": REAL_SOURCES,
            "count": len(REAL_SOURCES),
            "note": (
                "Опрашиваются hh.ru Public API и Yandex Search API (вакансии: site:hh.ru; "
                "новости: site:t.me/<канал> по четырём назначенным каналам). "
                "Карточка ведёт на URL из выдачи. Сайты компаний и неподключённые каналы не числятся источниками."
            ),
        }
    )


@app.post("/api/refresh")
async def manual_refresh():
    asyncio.create_task(_refresh())
    return JSONResponse({"status": "refresh_started", "message": "Парсинг запущен в фоне"})


@app.get("/api/stats")
async def get_stats():
    vacs = list(_cache["vacancies"])
    internship_count = sum(1 for v in vacs if v.get("category") == "internship")
    company_count = len({v.get("company", "") for v in vacs if v.get("company")})
    return JSONResponse(
        {
            "total_vacancies": max(len(vacs) - internship_count, 0),
            "total_internships": internship_count,
            "total_companies": company_count,
            "total_sources": len(REAL_SOURCES),
            "last_updated": _last_update_label(),
            "live": bool(vacs),
        }
    )


@app.get("/api/health")
async def health():
    llm_status = llm.status()
    errors = list(_cache["source_errors"])
    return {
        "status": "ok",
        "service": "Карьерный Навигатор 21",
        "cached_vacancies": len(_cache["vacancies"]),
        "cached_news": len(_cache["news"]),
        "last_update": _last_update_label(),
        "fetch_error": _cache["fetch_error"],
        "errors": errors,
        "jwt_configured": is_jwt_secret_configured(JWT_SECRET),
        "telegram_auth_configured": bool(BOT_TOKEN and _bot_username),
        "digest_configured": digest_telegram.is_configured(),
        "llm": llm_status,
        "yandex_search": yandex_search.status(),
    }


@app.get("/api/auth/bot-info")
async def bot_info():
    return JSONResponse(
        {
            "username": _bot_username,
            "enabled": bool(_bot_username and BOT_TOKEN and is_jwt_secret_configured(JWT_SECRET)),
        }
    )


@app.post("/api/auth/telegram")
async def telegram_auth(data: TelegramAuthData):
    if not BOT_TOKEN:
        return JSONResponse({"success": False, "error": "TELEGRAM_BOT_TOKEN не задан"}, status_code=503)
    if not is_jwt_secret_configured(JWT_SECRET):
        return JSONResponse({"success": False, "error": "JWT_SECRET не задан или слишком слабый"}, status_code=503)

    payload = data.model_dump()
    if not verify_telegram_hash(payload, BOT_TOKEN):
        return JSONResponse({"success": False, "error": "Неверная подпись Telegram"}, status_code=401)
    if not check_auth_date(data.auth_date):
        return JSONResponse({"success": False, "error": "Токен авторизации устарел"}, status_code=401)

    token = create_jwt(payload, JWT_SECRET)
    body = {
        "success": True,
        "user": {
            "id": data.id,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "username": data.username,
            "photo_url": data.photo_url,
        },
    }
    response = JSONResponse(body)
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_EXPIRE_DAYS * 86400,
        secure=COOKIE_SECURE,
    )
    logger.info("Telegram auth: @%s (id=%d)", data.username or "—", data.id)
    return response


@app.get("/api/auth/me")
async def auth_me(cn21_session: Optional[str] = Cookie(default=None)):
    payload = _current_user(cn21_session)
    if not payload:
        return JSONResponse({"authenticated": False})
    return JSONResponse(
        {
            "authenticated": True,
            "user": {
                "id": payload["sub"],
                "first_name": payload.get("first_name", ""),
                "last_name": payload.get("last_name", ""),
                "username": payload.get("username", ""),
                "photo_url": payload.get("photo_url", ""),
            },
        }
    )


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"success": True})
    response.delete_cookie(AUTH_COOKIE)
    return response


@app.get("/api/digest/settings")
async def get_digest_settings(cn21_session: Optional[str] = Cookie(default=None)):
    user = _current_user(cn21_session)
    if not user:
        return JSONResponse({"success": False, "error": "Нужна авторизация через Telegram"}, status_code=401)
    settings = digest_store.get_settings(str(user["sub"]))
    return JSONResponse({"success": True, "settings": settings})


@app.post("/api/digest/settings")
async def save_digest(settings: DigestSettingsIn, cn21_session: Optional[str] = Cookie(default=None)):
    user = _current_user(cn21_session)
    if not user:
        return JSONResponse({"success": False, "error": "Нужна авторизация через Telegram"}, status_code=401)
    if not digest_telegram.is_configured():
        return JSONResponse(
            {"success": False, "error": "TELEGRAM_BOT_TOKEN не задан — дайджест отправить нельзя"},
            status_code=503,
        )
    try:
        record = digest_store.save_settings(
            str(user["sub"]),
            {
                "telegram_id": int(user["sub"]),
                "username": user.get("username") or "",
                "schedule": settings.schedule,
                "time": settings.time,
                "roles": settings.roles,
            },
        )
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    return JSONResponse(
        {
            "success": True,
            "settings": record,
            "message": "Настройки сохранены. Напишите боту /start, иначе Telegram не доставит дайджест.",
        }
    )


@app.get("/api/digest/preview")
async def digest_preview(
    cn21_session: Optional[str] = Cookie(default=None),
    roles: Optional[str] = Query(None),
):
    user = _current_user(cn21_session)
    stored = digest_store.get_settings(str(user["sub"])) if user else None
    role_list = [r for r in (roles.split(",") if roles else (stored or {}).get("roles") or []) if r]
    digest = digest_builder.build_digest(_cache["vacancies"], _cache["news"], roles=role_list)
    return JSONResponse(
        {
            "digest": digest,
            "text": digest_builder.format_telegram(digest),
            "authenticated": bool(user),
        }
    )


@app.post("/api/digest/send")
async def digest_send(cn21_session: Optional[str] = Cookie(default=None)):
    user = _current_user(cn21_session)
    if not user:
        return JSONResponse({"success": False, "error": "Нужна авторизация через Telegram"}, status_code=401)
    settings = digest_store.get_settings(str(user["sub"]))
    if not settings:
        return JSONResponse({"success": False, "error": "Сначала сохраните настройки дайджеста"}, status_code=400)
    digest = digest_builder.build_digest(_cache["vacancies"], _cache["news"], roles=settings.get("roles") or [])
    sent = await digest_telegram.send_message(int(user["sub"]), digest_builder.format_telegram(digest))
    if not sent.get("ok"):
        return JSONResponse({"success": False, "error": sent.get("error")}, status_code=502)
    return JSONResponse({"success": True, "message": "Дайджест отправлен в Telegram", "empty": digest["empty"]})


@app.get("/api/ai/status")
async def ai_status():
    return JSONResponse(llm.status())


@app.post("/api/ai/career-advice")
async def ai_career_advice(req: CareerAdviceRequest):
    if not llm.is_enabled():
        return JSONResponse({"advice": None, "ai": None, "error": llm.disabled_message()}, status_code=503)
    advice = await llm.get_career_advice(req.role or "", req.skills or "", req.goals or "")
    return JSONResponse({"advice": advice, "ai": llm.status()["model"]})


@app.post("/api/ai/agent-advice")
async def ai_agent_advice(req: CareerAdviceRequest):
    if not llm.is_enabled():
        return JSONResponse(
            {
                "advice": llm.disabled_message(),
                "vacancies": [],
                "steps": [],
                "agent": None,
                "vacancies_source": "none",
            },
            status_code=503,
        )
    result = await llm.run_career_agent(req.role or "", req.skills or "", req.goals or "")
    return JSONResponse(result)


@app.post("/api/ai/summarize")
async def ai_summarize(req: SummarizeRequest):
    if not llm.is_enabled():
        return JSONResponse({"summary": None, "ai": None, "error": llm.disabled_message()}, status_code=503)
    summary = await llm.summarize_vacancy(
        title=req.title,
        company=req.company,
        requirement=req.requirement or "",
        responsibility=req.responsibility or "",
    )
    if not summary:
        return JSONResponse({"summary": None, "ai": None, "error": "Модель не вернула саммари"}, status_code=503)
    return JSONResponse({"summary": summary, "ai": llm.status()["model"]})


@app.get("/api/vacancies")
async def get_vacancies_legacy(
    category: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    return await get_live_vacancies(category=category, role=role, format=format, q=q, limit=limit, offset=offset)


@app.get("/api/news")
async def get_news_legacy(limit: int = Query(20, le=50)):
    return await get_live_news(limit=limit)


app.mount("/", StaticFiles(directory="web", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
