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
from parser.hh_parser import fetch_hh_vacancies
from parser.tg_parser import CHANNELS, fetch_tg_news

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


async def _refresh():
    logger.info("Запуск парсинга источников…")
    source_errors: list[str] = []
    hh_vacancies, tg_news = await asyncio.gather(
        fetch_hh_vacancies(),
        fetch_tg_news(),
        return_exceptions=True,
    )

    if isinstance(hh_vacancies, Exception):
        logger.error("hh.ru parser error: %s", hh_vacancies)
        source_errors.append(f"hh.ru: {hh_vacancies}")
        hh_vacancies = []
    if isinstance(tg_news, Exception):
        logger.error("Telegram parser error: %s", tg_news)
        source_errors.append(f"telegram: {tg_news}")
        tg_news = []

    hh_vacancies = dedup_vacancies(hh_vacancies)
    tg_news = dedup_news(tg_news)

    if llm.is_enabled() and hh_vacancies:
        try:
            hh_vacancies = await llm.enrich_vacancies(hh_vacancies, limit=5)
            logger.info("%s: enriched top-5 vacancy summaries", llm.status()["provider"])
        except Exception as exc:
            logger.warning("LLM enrich failed: %s", exc)
            source_errors.append(f"llm: {exc}")

    _cache["vacancies"] = hh_vacancies
    _cache["news"] = tg_news
    _cache["last_update"] = datetime.now(timezone.utc)
    _cache["fetch_error"] = "; ".join(source_errors) if source_errors else None
    _cache["source_errors"] = source_errors
    logger.info(
        "Парсинг завершён: %d вакансий с hh.ru, %d новостей из Telegram",
        len(hh_vacancies),
        len(tg_news),
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


app = FastAPI(title="Карьерный Навигатор 21 API", version="2.1.0", lifespan=lifespan)


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
    return JSONResponse(_vacancy_payload(category, role, format, q, limit, offset))


@app.get("/api/live-news")
async def get_live_news(limit: int = Query(20, le=50)):
    news = list(_cache["news"])
    return JSONResponse(
        {
            "news": news[:limit],
            "lastUpdate": _last_update_label(),
            "source": "live" if _cache["last_update"] else "empty",
            "live": bool(news),
            "errors": list(_cache["source_errors"]),
        }
    )


@app.get("/api/sources")
async def get_sources():
    return JSONResponse(
        {
            "sources": REAL_SOURCES,
            "count": len(REAL_SOURCES),
            "note": "Только эти источники реально опрашиваются. Сайты компаний и неподключённые каналы не подмешиваются.",
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
    return {
        "status": "ok",
        "service": "Карьерный Навигатор 21",
        "cached_vacancies": len(_cache["vacancies"]),
        "cached_news": len(_cache["news"]),
        "last_update": _last_update_label(),
        "fetch_error": _cache["fetch_error"],
        "jwt_configured": is_jwt_secret_configured(JWT_SECRET),
        "telegram_auth_configured": bool(BOT_TOKEN and _bot_username),
        "digest_configured": digest_telegram.is_configured(),
        "llm": llm_status,
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
