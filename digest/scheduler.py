"""Lightweight digest scheduler. Sends only when live cache has data."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from digest import builder, store, telegram

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")


def should_send(settings: dict, now: datetime) -> bool:
    if not settings.get("enabled"):
        return False
    if settings.get("time") != now.strftime("%H:%M"):
        return False
    today = now.date().isoformat()
    if settings.get("last_sent_date") == today:
        return False
    schedule = settings.get("schedule")
    weekday = now.weekday()  # Mon=0
    if schedule == "daily":
        return True
    if schedule == "weekdays":
        return weekday < 5
    if schedule == "twice":
        return weekday in {1, 4}  # Tue, Fri
    return False


async def tick(vacancies: list[dict], news: list[dict], now: datetime | None = None) -> list[dict]:
    current = now or datetime.now(MSK)
    results: list[dict] = []
    if not telegram.is_configured():
        return results
    for settings in store.all_enabled():
        if not should_send(settings, current):
            continue
        digest = builder.build_digest(vacancies, news, roles=settings.get("roles") or [])
        text = builder.format_telegram(digest)
        sent = await telegram.send_message(int(settings["telegram_id"]), text)
        if sent.get("ok"):
            store.mark_sent(str(settings["user_id"]), current.date().isoformat())
        else:
            logger.warning("Digest send failed for %s: %s", settings.get("user_id"), sent.get("error"))
        results.append({"user_id": settings["user_id"], **sent})
    return results
