"""YandexGPT Lite via AI Studio (OpenAI-compatible chat completions)."""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://ai.api.cloud.yandex.net/v1"
DEFAULT_MODEL = "yandexgpt-lite"


def _api_key() -> str:
    return (os.getenv("YANDEX_API_KEY") or os.getenv("YANDEX_IAM_TOKEN") or "").strip()


def _folder_id() -> str:
    return (os.getenv("YANDEX_FOLDER_ID") or "").strip()


def _model_uri() -> str:
    model = (os.getenv("YANDEX_MODEL") or DEFAULT_MODEL).strip()
    if model.startswith("gpt://") or model.startswith("ds://"):
        return model
    folder = _folder_id()
    if folder:
        return f"gpt://{folder}/{model}/latest"
    return model


def is_configured() -> bool:
    return bool(_api_key() and _folder_id())


def missing_settings() -> list[str]:
    missing: list[str] = []
    if not _api_key():
        missing.append("YANDEX_API_KEY")
    if not _folder_id():
        missing.append("YANDEX_FOLDER_ID")
    return missing


def _auth_header() -> str:
    raw = (os.getenv("YANDEX_API_KEY") or "").strip()
    if raw:
        return f"Api-Key {raw}"
    iam = (os.getenv("YANDEX_IAM_TOKEN") or "").strip()
    return f"Bearer {iam}"


async def complete(prompt: str, *, temperature: float = 0.3, max_tokens: int = 800) -> str:
    if not is_configured():
        raise RuntimeError("YandexGPT is not configured: " + ", ".join(missing_settings()))

    base = (os.getenv("YANDEX_API_BASE") or DEFAULT_BASE).rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": _model_uri(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }
    folder = _folder_id()
    if folder:
        headers["x-folder-id"] = folder

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        logger.warning("YandexGPT HTTP %s: %s", response.status_code, response.text[:300])
        raise RuntimeError(f"YandexGPT HTTP {response.status_code}")

    data = response.json()
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if content:
            return content
    # Legacy completion shape, just in case the gateway wraps it.
    result = data.get("result") or {}
    alternatives = result.get("alternatives") or []
    if alternatives:
        text = ((alternatives[0].get("message") or {}).get("text") or "").strip()
        if text:
            return text
    raise RuntimeError("YandexGPT returned an empty completion")


async def summarize_vacancy(title: str, company: str, requirement: str, responsibility: str) -> str:
    prompt = (
        f"Вакансия «{title}» в компании {company}.\n"
        f"Обязанности: {responsibility or '—'}\n"
        f"Требования: {requirement or '—'}\n\n"
        "Напиши саммари для студента IT-специальности (2 предложения): "
        "что делать, ключевые технологии, почему интересно. Не выдумывай факты, которых нет во входе."
    )
    try:
        return await complete(prompt, max_tokens=220)
    except Exception as exc:
        logger.warning("YandexGPT summarize error: %s", exc)
        return ""


async def get_career_advice(role: str, skills: str, goals: str) -> str:
    prompt = (
        "Ты — карьерный консультант для IT-студентов Татарстана.\n"
        f"Направление: {role or 'любое IT'}\n"
        f"Навыки: {skills or 'начинающий'}\n"
        f"Цели: {goals or 'первая работа / стажировка'}\n\n"
        "Дай 4–5 конкретных шагов: что изучить, какие компании рассмотреть "
        "(Казань, Иннополис, удалёнка РФ), как составить резюме. Отвечай по-русски. "
        "Не ссылайся на мессенджер MAX."
    )
    return await complete(prompt, max_tokens=700)


async def plan_search(role: str, skills: str, goals: str) -> str:
    prompt = (
        "Ты — карьерный агент для IT-студентов Татарстана.\n"
        f"Профиль пользователя: направление={role or 'любое IT'}, "
        f"навыки={skills or 'начинающий'}, цели={goals or 'стажировка'}.\n\n"
        "Шаг PLAN: определи параметры поиска вакансий на hh.ru.\n"
        "Ответь СТРОГО JSON без пояснений:\n"
        '{"search_query": "...", "prefer_remote": true|false, "internship_only": true|false}'
    )
    return await complete(prompt, temperature=0.1, max_tokens=200)


async def verify_vacancies(role: str, skills: str, goals: str, vac_list: Optional[str]) -> str:
    if vac_list:
        prompt = (
            "Ты — карьерный агент для IT-студентов Татарстана.\n"
            f"Профиль: направление={role or 'любое IT'}, "
            f"навыки={skills or 'начинающий'}, цели={goals or 'стажировка'}.\n\n"
            f"Шаг VERIFY: агент нашёл вакансии на hh.ru:\n{vac_list}\n\n"
            "Задача:\n"
            "1. Оцени соответствие каждой вакансии профилю (подходит / частично / не подходит).\n"
            "2. Выдели ТОП-3 наиболее подходящих с пояснением.\n"
            "3. Для каждой из ТОП-3 — что нужно подготовить перед откликом.\n"
            "4. Дай 2–3 конкретных следующих шага. По-русски, без воды. Не выдумывай вакансии."
        )
    else:
        prompt = (
            "Ты — карьерный агент для IT-студентов Татарстана.\n"
            f"Профиль: направление={role or 'любое IT'}, "
            f"навыки={skills or 'начинающий'}, цели={goals or 'стажировка'}.\n\n"
            "Поиск вакансий не дал результатов. Дай 4–5 конкретных шагов: "
            "что изучить, какие компании рассмотреть (Казань, Иннополис, удалёнка), "
            "как составить резюме. По-русски, конкретно. Не выдумывай открытые вакансии."
        )
    return await complete(prompt, max_tokens=800)
