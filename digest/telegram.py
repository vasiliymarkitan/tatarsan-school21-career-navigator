"""Send digest via Telegram Bot API. Honest errors, no fake success."""

from __future__ import annotations

import os
from typing import Any

import httpx


def bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def is_configured() -> bool:
    return bool(bot_token())


async def send_message(chat_id: int, text: str) -> dict[str, Any]:
    token = bot_token()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN не задан"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=payload)
        data = response.json()
    except Exception as exc:
        return {"ok": False, "error": f"Telegram API недоступен: {exc}"}

    if not data.get("ok"):
        description = data.get("description") or f"HTTP {response.status_code}"
        hint = ""
        if "chat not found" in str(description).lower() or "bot can't initiate" in str(description).lower():
            hint = " Напишите боту /start, иначе Telegram не даст отправить сообщение."
        return {"ok": False, "error": f"{description}.{hint}".strip()}
    return {"ok": True, "message_id": (data.get("result") or {}).get("message_id")}
