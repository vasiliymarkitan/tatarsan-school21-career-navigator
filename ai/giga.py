"""
GigaChat async utility — summarize vacancies + career advice + career agent.
Needs GIGACHAT_CREDENTIALS and GIGACHAT_SCOPE in env.
"""

import json
import logging
import os
import re

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

logger = logging.getLogger(__name__)

GIGACHAT_CREDENTIALS: str = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

_ENABLED = bool(GIGACHAT_CREDENTIALS)


def _client() -> GigaChat:
    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False,
        timeout=30,
    )


async def summarize_vacancy(title: str, company: str, requirement: str, responsibility: str) -> str:
    """Return AI-generated 2-sentence vacancy summary in Russian. Falls back to '' on error."""
    if not _ENABLED:
        return ""
    prompt = (
        f"Вакансия «{title}» в компании {company}.\n"
        f"Обязанности: {responsibility or '—'}\n"
        f"Требования: {requirement or '—'}\n\n"
        "Напиши саммари для студента IT-специальности (2 предложения): "
        "что делать, ключевые технологии, почему интересно."
    )
    try:
        async with _client() as giga:
            resp = await giga.achat(
                Chat(messages=[Messages(role=MessagesRole.USER, content=prompt)])
            )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("GigaChat summarize error: %s", e)
        return ""


async def get_career_advice(role: str, skills: str, goals: str) -> str:
    """Return personalised career advice for an IT student in Tatarstan."""
    if not _ENABLED:
        return "GigaChat не настроен — задайте GIGACHAT_CREDENTIALS в .env"
    prompt = (
        "Ты — карьерный консультант для IT-студентов Татарстана.\n"
        f"Направление: {role or 'любое IT'}\n"
        f"Навыки: {skills or 'начинающий'}\n"
        f"Цели: {goals or 'первая работа / стажировка'}\n\n"
        "Дай 4–5 конкретных шагов: что изучить, какие компании рассмотреть "
        "(Казань, Иннополис, удалёнка РФ), как составить резюме. Отвечай по-русски."
    )
    try:
        async with _client() as giga:
            resp = await giga.achat(
                Chat(messages=[Messages(role=MessagesRole.USER, content=prompt)])
            )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("GigaChat career_advice error: %s", e)
        return f"Ошибка AI: {e}"


async def run_career_agent(role: str, skills: str, goals: str, vacancies: list | None = None) -> dict:
    """
    ReAct-style career agent: plan → act (live cache) → verify.
    Returns {advice, vacancies, steps, agent}. Never invents jobs or calls hh.ru.
    """
    cached = list(vacancies or [])
    if not _ENABLED:
        return {
            "advice": "GigaChat не настроен — задайте GIGACHAT_CREDENTIALS в .env",
            "vacancies": [],
            "steps": [],
            "agent": None,
            "vacancies_source": "none",
            "cache_size": len(cached),
        }

    steps: list[dict] = []

    # ── STEP 1: PLAN ─────────────────────────────────────────────────────────
    plan_prompt = (
        "Ты — карьерный агент для IT-студентов Татарстана.\n"
        f"Профиль пользователя: направление={role or 'любое IT'}, "
        f"навыки={skills or 'начинающий'}, цели={goals or 'стажировка'}.\n\n"
        "Шаг PLAN: определи параметры отбора вакансий из живого кэша "
        "(Татарстан / удалёнка РФ). Не придумывай вакансии.\n"
        "Ответь СТРОГО JSON без пояснений:\n"
        '{"search_query": "...", "prefer_remote": true|false, "internship_only": true|false}'
    )
    plan: dict = {
        "search_query": f"junior {role or 'разработчик'} {skills or ''}".strip(),
        "prefer_remote": False,
        "internship_only": False,
    }
    try:
        async with _client() as giga:
            resp = await giga.achat(Chat(messages=[Messages(role=MessagesRole.USER, content=plan_prompt)]))
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if m:
            plan = json.loads(m.group())
    except Exception as e:
        logger.warning("Agent PLAN step error: %s", e)
    steps.append({"step": "plan", "tool": "search_vacancies", "params": plan})

    # ── STEP 2: ACT — live cache only ────────────────────────────────────────
    selected = list(cached)
    role_key = (role or "").strip().lower()
    if role_key and role_key != "all":
        selected = [item for item in selected if str(item.get("role") or "") == role_key]
    if plan.get("internship_only"):
        intern = [item for item in selected if item.get("category") == "internship"]
        if intern:
            selected = intern
    if plan.get("prefer_remote"):
        remote = [item for item in selected if item.get("format") == "remote"]
        if remote:
            selected = remote
    steps.append({"step": "act", "tool": "live_cache", "found": len(selected), "cache_size": len(cached)})

    # ── STEP 3: VERIFY ────────────────────────────────────────────────────────
    if selected:
        vac_list = "\n".join(
            f"  {i + 1}. «{v['title']}» — {v['company']} "
            f"({v['format']}, {v['location']})"
            f"{', ' + v['salary'] if v.get('salary') else ''}"
            for i, v in enumerate(selected[:8])
        )
        verify_prompt = (
            "Ты — карьерный агент для IT-студентов Татарстана.\n"
            f"Профиль: направление={role or 'любое IT'}, "
            f"навыки={skills or 'начинающий'}, цели={goals or 'стажировка'}.\n\n"
            f"Шаг VERIFY: агент взял карточки из живого кэша:\n{vac_list}\n\n"
            "Задача:\n"
            "1. Оцени соответствие каждой вакансии профилю (подходит / частично / не подходит).\n"
            "2. Выдели ТОП-3 наиболее подходящих с пояснением.\n"
            "3. Для каждой из ТОП-3 — что нужно подготовить перед откликом.\n"
            "4. Дай 2–3 конкретных следующих шага. По-русски, без воды. Не выдумывай вакансии."
        )
    else:
        verify_prompt = (
            "Ты — карьерный агент для IT-студентов Татарстана.\n"
            f"Профиль: направление={role or 'любое IT'}, "
            f"навыки={skills or 'начинающий'}, цели={goals or 'стажировка'}.\n\n"
            "В живом кэше сейчас нет подходящих карточек. Не выдумывай вакансии. "
            "Дай 4–5 конкретных шагов: что изучить, какие компании рассмотреть "
            "(Казань, Иннополис, удалёнка), как составить резюме. По-русски, конкретно."
        )
    advice = ""
    try:
        async with _client() as giga:
            resp = await giga.achat(Chat(messages=[Messages(role=MessagesRole.USER, content=verify_prompt)]))
        advice = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Agent VERIFY step error: %s", e)
        advice = f"Ошибка AI: {e}"
    steps.append({"step": "verify", "tool": "generate_advice", "ok": bool(advice)})

    return {
        "advice": advice,
        "vacancies": selected[:5],
        "steps": steps,
        "agent": "GigaChat",
        "vacancies_source": "live_cache" if selected else ("cache_no_match" if cached else "cache_empty"),
        "cache_size": len(cached),
    }


async def enrich_vacancies(vacancies: list[dict], limit: int = 5) -> list[dict]:
    """Add real AI summary to the first `limit` vacancies (in-place, returns list)."""
    if not _ENABLED:
        return vacancies
    for v in vacancies[:limit]:
        summary = v.get("aiSummary", "")
        # Only overwrite dumb fallback summaries (short or contains "Вакансия X от компании")
        if "от компании" in summary or len(summary) < 80:
            ai = await summarize_vacancy(
                title=v.get("title", ""),
                company=v.get("company", ""),
                requirement="",
                responsibility=summary,
            )
            if ai:
                v["aiSummary"] = ai
                v["aiEnriched"] = True
    return vacancies
