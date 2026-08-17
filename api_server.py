"""
Карьерный Навигатор 21 — FastAPI backend
Запуск: uvicorn api_server:app --reload --port 8000
"""

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, Query, Request, Response, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel

import httpx

from parser.hh_parser import fetch_hh_vacancies
from parser.tg_parser import fetch_tg_news
from ai.giga import enrich_vacancies, get_career_advice, run_career_agent, summarize_vacancy, _ENABLED as GIGA_ENABLED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

REFRESH_INTERVAL = 30 * 60  # 30 минут

# ── Telegram Auth ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
AUTH_COOKIE = "cn21_session"

_bot_username: str = os.getenv("BOT_USERNAME", "")  # берём из env; getMe — fallback

# ── Кэш живых данных ─────────────────────────────────────────────────────────
_cache: dict = {
    "vacancies": [],
    "news": [],
    "last_update": None,   # datetime UTC
    "fetch_error": None,
}

# ── Статические вакансии (резервная база) ─────────────────────────────────────
STATIC_VACANCIES = [
    {"id": "s1", "title": "Python Backend Developer (Junior)", "company": "KazanExpress", "logo": "KE", "logoColor": "#FF6B00", "logoText": "#fff", "category": "vacancy", "role": "backend", "format": "hybrid", "location": "Казань", "salary": "от 60 000 ₽", "source": {"type": "website", "name": "krecruitment.kazanexpress.ru", "url": "https://krecruitment.kazanexpress.ru/"}, "dateLabel": "1 ч. назад", "dateSort": 1, "tags": ["junior", "Python", "Django", "hybrid", "Казань"], "aiSummary": "KazanExpress ищет junior-разработчика в команду бэкенда маркетплейса. Ключевые требования — Django/FastAPI и базовое понимание PostgreSQL.", "url": "https://krecruitment.kazanexpress.ru/"},
    {"id": "s2", "title": "Data Engineer — стажировка", "company": "Татнефть", "logo": "ТН", "logoColor": "#003D82", "logoText": "#fff", "category": "internship", "role": "data", "format": "office", "location": "Альметьевск", "salary": "от 25 000 ₽", "source": {"type": "website", "name": "tatneft.ru", "url": "https://career.tatneft.ru"}, "dateLabel": "1 день назад", "dateSort": 2, "tags": ["стажировка", "Data", "SQL", "Spark", "Альметьевск"], "aiSummary": "Стажировка в дата-инженерии крупного нефтяного холдинга. Работа с промышленными данными, Spark, SQL.", "url": "https://career.tatneft.ru"},
    {"id": "s3", "title": "Frontend Developer (React)", "company": "ICL Services", "logo": "ICL", "logoColor": "#1a1a2e", "logoText": "#00D97E", "category": "vacancy", "role": "frontend", "format": "remote", "location": "Казань", "salary": "от 80 000 ₽", "source": {"type": "website", "name": "icl-services.com", "url": "https://icl-services.com/career/"}, "dateLabel": "3 ч. назад", "dateSort": 1, "tags": ["junior", "React", "TypeScript", "remote", "Казань"], "aiSummary": "ICL Services ищет фронтенд-разработчика. Требования: React, TypeScript, REST API. Полная удалёнка.", "url": "https://icl-services.com/career/"},
    {"id": "s4", "title": "DevOps Engineer (Junior)", "company": "Иннополис", "logo": "IN", "logoColor": "#7B2FBE", "logoText": "#fff", "category": "vacancy", "role": "devops", "format": "hybrid", "location": "Иннополис", "salary": "от 70 000 ₽", "source": {"type": "website", "name": "innopolis.com", "url": "https://innopolis.com/en/life/vacancies"}, "dateLabel": "2 дня назад", "dateSort": 3, "tags": ["junior", "DevOps", "Kubernetes", "Docker", "Иннополис"], "aiSummary": "Позиция для желающих работать в экосистеме технограда. Docker, CI/CD, Linux.", "url": "https://innopolis.com/en/life/vacancies"},
    {"id": "s5", "title": "ML Engineer — стажировка", "company": "Bars Group", "logo": "BG", "logoColor": "#0066CC", "logoText": "#fff", "category": "internship", "role": "data", "format": "hybrid", "location": "Казань", "salary": "от 20 000 ₽", "source": {"type": "telegram", "name": "@bars_hr", "url": "https://t.me/bars_hr"}, "dateLabel": "5 ч. назад", "dateSort": 1, "tags": ["стажировка", "ML", "Python", "NLP", "Казань"], "aiSummary": "Bars Group ищет стажёра в ML-команду для NLP-задач в e-gov проектах.", "url": "https://bars.group/careers/"},
]

STATIC_NEWS = [
    {"id": "sn1", "title": "Хакатон «Digital Tatarstan 2026» стартует 5 июля в Казани", "source": "@it_tatarstan", "sourceType": "telegram", "dateLabel": "Сегодня", "dateSort": 0, "tags": ["хакатон", "ИТ-парк", "призы"], "summary": "ИТ-парк Казань объявил регистрацию на ежегодный хакатон. 48 часов, призовой фонд 700 000 ₽. Треки: GovTech, AI, Fintech, AgriTech.", "icon": "💻"},
    {"id": "sn2", "title": "Минцифры РТ запустило летнюю программу стажировок", "source": "mincifry.tatarstan.ru", "sourceType": "website", "dateLabel": "Вчера", "dateSort": 1, "tags": ["стажировка", "гостех", "Минцифры"], "summary": "Министерство цифрового развития Татарстана открыло 30 оплачиваемых стажёрских мест. Направления: Backend, Data, DevOps. Срок — июль–август 2026.", "icon": "🏛️"},
    {"id": "sn3", "title": "Иннополис вошёл в топ-5 технопарков России 2025", "source": "@innopolis_live", "sourceType": "telegram", "dateLabel": "2 дня назад", "dateSort": 2, "tags": ["Иннополис", "рейтинг"], "summary": "По данным рейтинга РВК за 2025 год Иннополис поднялся с 7-го на 5-е место. Число резидентов превысило 400 компаний.", "icon": "🏆"},
    {"id": "sn4", "title": "KazanExpress запустил внутреннюю AI-платформу", "source": "@kazanit", "sourceType": "telegram", "dateLabel": "3 дня назад", "dateSort": 3, "tags": ["KazanExpress", "AI", "вакансии"], "summary": "Маркетплейс представил платформу генеративного AI для персонализации. Открыт набор ML-инженеров и Python-разработчиков.", "icon": "🤖"},
]


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
    hh_vacancies, tg_news = await asyncio.gather(
        fetch_hh_vacancies(),
        fetch_tg_news(),
        return_exceptions=True,
    )

    if isinstance(hh_vacancies, Exception):
        logger.error("hh.ru parser error: %s", hh_vacancies)
        hh_vacancies = []
    if isinstance(tg_news, Exception):
        logger.error("Telegram parser error: %s", tg_news)
        tg_news = []

    if GIGA_ENABLED and hh_vacancies:
        try:
            hh_vacancies = await enrich_vacancies(hh_vacancies, limit=5)
            logger.info("GigaChat: enriched top-5 vacancy summaries")
        except Exception as e:
            logger.warning("GigaChat enrich failed: %s", e)

    _cache["vacancies"] = hh_vacancies
    _cache["news"] = tg_news if tg_news else STATIC_NEWS
    _cache["last_update"] = datetime.now(timezone.utc)
    _cache["fetch_error"] = None
    logger.info(
        "Парсинг завершён: %d вакансий с hh.ru, %d новостей из Telegram",
        len(hh_vacancies), len(tg_news),
    )


async def _refresh_loop():
    while True:
        try:
            await _refresh()
        except Exception as e:
            logger.error("Refresh loop error: %s", e)
            _cache["fetch_error"] = str(e)
        await asyncio.sleep(REFRESH_INTERVAL)


async def _fetch_bot_username() -> str:
    if not BOT_TOKEN:
        return ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
            data = r.json()
            return data.get("result", {}).get("username", "")
    except Exception as e:
        logger.warning("Не удалось получить username бота: %s", e)
        return ""


def _verify_telegram_hash(data: dict) -> bool:
    """Проверяет подпись Telegram Login Widget по алгоритму из документации."""
    if not BOT_TOKEN:
        return False
    received_hash = data.get("hash", "")
    check_data = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_hash, received_hash)


def _check_auth_date(auth_date: int, max_age: int = 86400) -> bool:
    now = int(datetime.now(timezone.utc).timestamp())
    return (now - auth_date) <= max_age


def _create_jwt(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username", ""),
        "photo_url": user.get("photo_url", ""),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_username
    if not _bot_username:
        _bot_username = await _fetch_bot_username()
    if _bot_username:
        logger.info("Telegram бот: @%s", _bot_username)
    else:
        logger.warning("BOT_USERNAME и TELEGRAM_BOT_TOKEN не заданы — Telegram-авторизация отключена")
    asyncio.create_task(_refresh_loop())
    yield


# ── Приложение ────────────────────────────────────────────────────────────────
app = FastAPI(title="Карьерный Навигатор 21 API", version="2.0.0", lifespan=lifespan)


# ── Модели ────────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    roles: List[str] = []


class DigestSettings(BaseModel):
    schedule: str   # daily | weekdays | twice
    time: str       # "09:00"
    roles: List[str]
    channels: List[str]  # email | telegram


# ── Роуты ─────────────────────────────────────────────────────────────────────

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
    """Свежие вакансии с hh.ru (парсинг каждые 30 мин)."""
    data = list(_cache["vacancies"])  # копия

    if not data:
        # Если парсер ещё не отработал или упал — отдаём статику
        data = STATIC_VACANCIES.copy()

    if category and category != "all":
        data = [v for v in data if v.get("category") == category]
    if role and role != "all":
        data = [v for v in data if v.get("role") == role]
    if format and format != "all":
        data = [v for v in data if v.get("format") == format]
    if q:
        q_lower = q.lower()
        data = [
            v for v in data
            if q_lower in (
                v.get("title", "") + " " + v.get("company", "") + " " + " ".join(v.get("tags", []))
            ).lower()
        ]

    total = len(data)
    return JSONResponse({
        "total": total,
        "vacancies": data[offset: offset + limit],
        "has_more": offset + limit < total,
        "lastUpdate": _last_update_label(),
        "source": "live" if _cache["vacancies"] else "static",
    })


@app.get("/api/live-news")
async def get_live_news(limit: int = Query(20, le=50)):
    """Свежие новости из Telegram-каналов."""
    news = _cache["news"] if _cache["news"] else STATIC_NEWS
    return JSONResponse({
        "news": news[:limit],
        "lastUpdate": _last_update_label(),
        "source": "live" if _cache["news"] else "static",
    })


@app.post("/api/refresh")
async def manual_refresh():
    """Ручной запуск парсинга (для демонстрации)."""
    asyncio.create_task(_refresh())
    return JSONResponse({"status": "refresh_started", "message": "Парсинг запущен в фоне"})


@app.get("/api/stats")
async def get_stats():
    vacs = _cache["vacancies"] or STATIC_VACANCIES
    live_count = len(vacs)
    internship_count = sum(1 for v in vacs if v.get("category") == "internship")
    company_count = len({v.get("company", "") for v in vacs})
    return JSONResponse({
        "total_vacancies": live_count - internship_count,
        "total_internships": internship_count,
        "total_companies": company_count,
        "total_sources": 12,
        "last_updated": _last_update_label(),
        "live": bool(_cache["vacancies"]),
    })


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "Карьерный Навигатор 21",
        "cached_vacancies": len(_cache["vacancies"]),
        "cached_news": len(_cache["news"]),
        "last_update": _last_update_label(),
        "fetch_error": _cache["fetch_error"],
    }


@app.post("/api/register")
async def register(user: UserRegister):
    return JSONResponse({
        "success": True,
        "message": f"Аккаунт для {user.email} создан!",
        "user_id": 1,
    })


@app.post("/api/digest/settings")
async def save_digest(settings: DigestSettings):
    return JSONResponse({"success": True, "message": "Настройки дайджеста сохранены"})


# ── Telegram авторизация ──────────────────────────────────────────────────────

class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


@app.get("/api/auth/bot-info")
async def bot_info():
    """Отдаёт username бота для инициализации виджета на фронте."""
    return JSONResponse({
        "username": _bot_username,
        "enabled": bool(_bot_username),
    })


@app.post("/api/auth/telegram")
async def telegram_auth(data: TelegramAuthData, response: Response):
    """
    Принимает данные от Telegram Login Widget,
    проверяет подпись и свежесть, выдаёт httpOnly JWT-cookie.
    """
    payload = data.model_dump()

    if not _verify_telegram_hash(payload):
        return JSONResponse({"success": False, "error": "Неверная подпись Telegram"}, status_code=401)

    if not _check_auth_date(data.auth_date):
        return JSONResponse({"success": False, "error": "Токен авторизации устарел"}, status_code=401)

    token = _create_jwt(payload)

    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_EXPIRE_DAYS * 86400,
        secure=False,   # True когда будет HTTPS
    )
    logger.info("Telegram auth: @%s (id=%d)", data.username or "—", data.id)
    return JSONResponse({
        "success": True,
        "user": {
            "id": data.id,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "username": data.username,
            "photo_url": data.photo_url,
        },
    })


@app.get("/api/auth/me")
async def auth_me(cn21_session: Optional[str] = Cookie(default=None)):
    """Проверяет текущую сессию по httpOnly cookie."""
    if not cn21_session:
        return JSONResponse({"authenticated": False})
    payload = _decode_jwt(cn21_session)
    if not payload:
        return JSONResponse({"authenticated": False})
    return JSONResponse({
        "authenticated": True,
        "user": {
            "id": payload["sub"],
            "first_name": payload.get("first_name", ""),
            "last_name": payload.get("last_name", ""),
            "username": payload.get("username", ""),
            "photo_url": payload.get("photo_url", ""),
        },
    })


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE)
    return JSONResponse({"success": True})


# ── GigaChat AI ───────────────────────────────────────────────────────────────

class CareerAdviceRequest(BaseModel):
    role: Optional[str] = None       # backend / frontend / data / devops / …
    skills: Optional[str] = None     # "Python, SQL, базы данных"
    goals: Optional[str] = None      # "первая работа в Казани"


class SummarizeRequest(BaseModel):
    title: str
    company: str
    requirement: Optional[str] = ""
    responsibility: Optional[str] = ""


@app.get("/api/ai/status")
async def ai_status():
    return JSONResponse({"enabled": GIGA_ENABLED})


@app.post("/api/ai/career-advice")
async def ai_career_advice(req: CareerAdviceRequest):
    """Персональные рекомендации от GigaChat для IT-студента."""
    advice = await get_career_advice(
        role=req.role or "",
        skills=req.skills or "",
        goals=req.goals or "",
    )
    return JSONResponse({"advice": advice, "ai": "GigaChat"})


@app.post("/api/ai/agent-advice")
async def ai_agent_advice(req: CareerAdviceRequest):
    """Агентный карьерный консультант: план → поиск hh.ru → анализ результатов."""
    result = await run_career_agent(
        role=req.role or "",
        skills=req.skills or "",
        goals=req.goals or "",
    )
    if not result["vacancies"]:
        role = req.role or ""
        pool = _cache["vacancies"] or STATIC_VACANCIES
        filtered = [v for v in pool if not role or v.get("role") == role]
        result["vacancies"] = (filtered or pool)[:5]
        result["vacancies_source"] = "static"
    return JSONResponse(result)


@app.post("/api/ai/summarize")
async def ai_summarize(req: SummarizeRequest):
    """AI-саммари одной вакансии по запросу."""
    summary = await summarize_vacancy(
        title=req.title,
        company=req.company,
        requirement=req.requirement or "",
        responsibility=req.responsibility or "",
    )
    if not summary:
        return JSONResponse({"summary": None, "ai": None}, status_code=503)
    return JSONResponse({"summary": summary, "ai": "GigaChat"})


# ── Устаревший эндпоинт для обратной совместимости ───────────────────────────
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


# ── Статика (последней, чтобы не перекрыть /api/) ────────────────────────────
app.mount("/", StaticFiles(directory="web", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
