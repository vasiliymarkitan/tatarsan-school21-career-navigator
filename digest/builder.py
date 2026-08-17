"""Build a digest only from live cached vacancies/news. Never invent cards."""

from __future__ import annotations

from typing import Any, Iterable


def _matches_roles(item: dict, roles: Iterable[str]) -> bool:
    wanted = {role for role in roles if role}
    if not wanted:
        return True
    return str(item.get("role") or "") in wanted


def build_digest(
    vacancies: list[dict],
    news: list[dict],
    *,
    roles: list[str],
    limit: int = 5,
) -> dict[str, Any]:
    matched = [item for item in vacancies if _matches_roles(item, roles)]
    top = matched[:limit]
    headlines = news[:3]
    return {
        "roles": list(roles),
        "vacancies": top,
        "news": headlines,
        "total_matched": len(matched),
        "empty": not top and not headlines,
    }


def format_telegram(digest: dict[str, Any]) -> str:
    roles = ", ".join(digest.get("roles") or []) or "все направления"
    lines = [
        "Карьерный Навигатор 21 — дайджест",
        f"Роли: {roles}",
        "",
    ]
    vacancies = digest.get("vacancies") or []
    if vacancies:
        lines.append("Вакансии и стажировки:")
        for index, item in enumerate(vacancies, start=1):
            salary = f" · {item['salary']}" if item.get("salary") else ""
            url = item.get("url") or ""
            lines.append(f"{index}. {item.get('title')} — {item.get('company')}{salary}")
            if url:
                lines.append(url)
        lines.append("")
    else:
        lines.append("Подходящих вакансий в живом кэше сейчас нет.")
        lines.append("")

    news = digest.get("news") or []
    if news:
        lines.append("IT-новости из Telegram:")
        for item in news:
            title = item.get("title") or ""
            source = item.get("source") or ""
            url = item.get("url") or ""
            lines.append(f"• {title} ({source})")
            if url:
                lines.append(url)

    lines.append("")
    lines.append("Источники: hh.ru и публичные t.me/s/ каналы. Дубли уже сняты.")
    return "\n".join(lines).strip()
