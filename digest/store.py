"""File-backed digest settings. No fake 'saved' without a write."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()

ALLOWED_SCHEDULES = {"daily", "weekdays", "twice"}
ALLOWED_ROLES = {
    "backend",
    "frontend",
    "data",
    "devops",
    "mobile",
    "qa",
    "pm",
    "analytics",
    "design",
}
ALLOWED_TIMES = {"09:00", "12:00", "18:00", "20:00"}


def store_path() -> Path:
    raw = os.getenv("DIGEST_STORE_PATH") or "data/digest_settings.json"
    return Path(raw)


def _empty() -> dict[str, Any]:
    return {"users": {}}


def load_all() -> dict[str, Any]:
    path = store_path()
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
        return _empty()
    return data


def get_settings(user_id: str) -> Optional[dict[str, Any]]:
    return load_all()["users"].get(str(user_id))


def save_settings(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    schedule = payload.get("schedule") or "daily"
    if schedule not in ALLOWED_SCHEDULES:
        raise ValueError("unsupported schedule")
    time_value = (payload.get("time") or "09:00").strip()
    if time_value not in ALLOWED_TIMES:
        raise ValueError("unsupported time")
    roles = [role for role in (payload.get("roles") or []) if role in ALLOWED_ROLES]
    if not roles:
        raise ValueError("at least one role is required")

    record = {
        "user_id": str(user_id),
        "telegram_id": int(payload.get("telegram_id") or user_id),
        "username": payload.get("username") or "",
        "schedule": schedule,
        "time": time_value,
        "roles": roles,
        "channel": "telegram",
        "enabled": True,
        "last_sent_date": payload.get("last_sent_date"),
    }

    path = store_path()
    with _LOCK:
        data = load_all()
        data["users"][str(user_id)] = record
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return record


def mark_sent(user_id: str, sent_date: str) -> None:
    path = store_path()
    with _LOCK:
        data = load_all()
        user = data["users"].get(str(user_id))
        if not user:
            return
        user["last_sent_date"] = sent_date
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def all_enabled() -> list[dict[str, Any]]:
    return [row for row in load_all()["users"].values() if row.get("enabled")]
