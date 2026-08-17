"""LLM facade: YandexGPT Lite by default, GigaChat remains switchable."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ai import giga, yandex

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "yandex"


def configured_provider() -> str:
    raw = (os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if raw in {"gigachat", "giga", "sber"}:
        return "gigachat"
    return "yandex"


def is_enabled() -> bool:
    provider = configured_provider()
    if provider == "gigachat":
        return bool(giga._ENABLED)
    return yandex.is_configured()


def status() -> dict[str, Any]:
    provider = configured_provider()
    if provider == "gigachat":
        return {
            "enabled": bool(giga._ENABLED),
            "provider": "gigachat",
            "model": "GigaChat",
            "missing": [] if giga._ENABLED else ["GIGACHAT_CREDENTIALS"],
        }
    missing = yandex.missing_settings()
    return {
        "enabled": not missing,
        "provider": "yandex",
        "model": os.getenv("YANDEX_MODEL") or yandex.DEFAULT_MODEL,
        "missing": missing,
    }


def disabled_message() -> str:
    info = status()
    if info["enabled"]:
        return ""
    missing = ", ".join(info["missing"]) or "credentials"
    if info["provider"] == "gigachat":
        return f"GigaChat не настроен — задайте {missing} в .env"
    return f"YandexGPT не настроен — задайте {missing} в .env"


async def summarize_vacancy(title: str, company: str, requirement: str, responsibility: str) -> str:
    if configured_provider() == "gigachat":
        return await giga.summarize_vacancy(title, company, requirement, responsibility)
    return await yandex.summarize_vacancy(title, company, requirement, responsibility)


async def get_career_advice(role: str, skills: str, goals: str) -> str:
    if not is_enabled():
        return disabled_message()
    if configured_provider() == "gigachat":
        return await giga.get_career_advice(role, skills, goals)
    try:
        return await yandex.get_career_advice(role, skills, goals)
    except Exception as exc:
        logger.warning("YandexGPT career_advice error: %s", exc)
        return f"Ошибка AI: {exc}"


def _default_plan(role: str, skills: str) -> dict[str, Any]:
    return {
        "search_query": f"junior {role or 'разработчик'} {skills or ''}".strip(),
        "prefer_remote": False,
        "internship_only": False,
    }


def _parse_plan(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    match = re.search(r"\{[^{}]+\}", raw or "", re.DOTALL)
    if not match:
        return fallback
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    plan = dict(fallback)
    if parsed.get("search_query"):
        plan["search_query"] = str(parsed["search_query"])
    if "prefer_remote" in parsed:
        plan["prefer_remote"] = bool(parsed["prefer_remote"])
    if "internship_only" in parsed:
        plan["internship_only"] = bool(parsed["internship_only"])
    return plan


async def run_career_agent(role: str, skills: str, goals: str) -> dict[str, Any]:
    provider = configured_provider()
    agent_name = "GigaChat" if provider == "gigachat" else "YandexGPT Lite"

    if not is_enabled():
        return {
            "advice": disabled_message(),
            "vacancies": [],
            "steps": [],
            "agent": None,
            "vacancies_source": "none",
        }

    if provider == "gigachat":
        result = await giga.run_career_agent(role, skills, goals)
        result.setdefault("vacancies_source", "hh" if result.get("vacancies") else "none")
        return result

    steps: list[dict[str, Any]] = []
    plan = _default_plan(role, skills)
    try:
        raw_plan = await yandex.plan_search(role, skills, goals)
        plan = _parse_plan(raw_plan, plan)
    except Exception as exc:
        logger.warning("Agent PLAN step error: %s", exc)
    steps.append({"step": "plan", "tool": "search_vacancies", "params": plan})

    from parser.hh_parser import fetch_vacancies_by_query

    vacancies: list[dict] = []
    try:
        schedule = "remote" if plan.get("prefer_remote") else None
        query = plan.get("search_query") or f"junior {role} {skills}".strip()
        vacancies = await fetch_vacancies_by_query(query, schedule=schedule, per_page=12)
    except Exception as exc:
        logger.warning("Agent ACT step error: %s", exc)
    steps.append({"step": "act", "tool": "hh_api", "found": len(vacancies)})

    if vacancies:
        vac_list = "\n".join(
            f"  {i + 1}. «{v['title']}» — {v['company']} "
            f"({v['format']}, {v['location']})"
            f"{', ' + v['salary'] if v.get('salary') else ''}"
            for i, v in enumerate(vacancies[:8])
        )
    else:
        vac_list = None

    advice = ""
    try:
        advice = await yandex.verify_vacancies(role, skills, goals, vac_list)
    except Exception as exc:
        logger.warning("Agent VERIFY step error: %s", exc)
        advice = f"Ошибка AI: {exc}"
    steps.append({"step": "verify", "tool": "generate_advice", "ok": bool(advice)})

    return {
        "advice": advice,
        "vacancies": vacancies[:5],
        "steps": steps,
        "agent": agent_name,
        "vacancies_source": "hh" if vacancies else "none",
    }


async def enrich_vacancies(vacancies: list[dict], limit: int = 5) -> list[dict]:
    if not is_enabled():
        return vacancies
    for item in vacancies[:limit]:
        summary = item.get("aiSummary", "")
        if "от компании" in summary or len(summary) < 80:
            ai_text = await summarize_vacancy(
                title=item.get("title", ""),
                company=item.get("company", ""),
                requirement="",
                responsibility=summary,
            )
            if ai_text:
                item["aiSummary"] = ai_text
                item["aiEnriched"] = True
    return vacancies
