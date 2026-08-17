"""
Парсер публичных Telegram-каналов через web-превью t.me/s/<channel>.
Не требует токенов — использует публичный HTML-рендер.
"""
import re
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; career-navigator-bot/1.0)",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Публичные каналы для парсинга новостей
CHANNELS = [
    ("kazanit",          "@kazanit",         "tg"),
    ("it_tatarstan",     "@it_tatarstan",    "tg"),
    ("innopolis_live",   "@innopolis_live",  "tg"),
    ("school21_kazan",   "@school21_kazan",  "tg"),
]

# Ключевые слова для фильтрации IT-релевантных постов
IT_KEYWORDS = [
    "вакансия", "вакансии", "стажировка", "стажёр", "стажер",
    "хакатон", "hackathon", "набор", "нанимаем", "ищем", "hiring",
    "разработчик", "developer", "программист", "it ", "ит ", "цифровой",
    "иннополис", "it-парк", "itpark", "минцифры", "технопарк",
    "kazanexpress", "icl", "bars group", "школа 21", "school21",
    "python", "java", "backend", "frontend", "data science",
    "искусственный интеллект", "ai ", " ии ", "нейросет", "нейро",
    "стартап", "startup", "акселератор", "vc ", "инвестиц",
]

NEWS_ICONS = {
    "хакатон": "💻", "стажировка": "🎯", "вакансия": "💼",
    "набор": "📢", "школа 21": "🎓", "иннополис": "🏛️",
    "искусственный интеллект": "🤖", "ai ": "🤖", "нейро": "🤖",
    "стартап": "🚀", "акселератор": "🚀", "инвестиц": "💰",
    "рейтинг": "🏆", "топ-": "🏆", "минцифры": "🏛️",
}

MAX_POSTS_PER_CHANNEL = 5


def _time_ago(dt_str: str) -> tuple[str, int]:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours = int((now - dt).total_seconds() / 3600)
        if hours < 1:
            return "только что", 0
        if hours < 24:
            return f"{hours} ч. назад", 0
        days = hours // 24
        if days == 1:
            return "Вчера", 1
        if days < 7:
            return f"{days} дня назад" if days < 5 else f"{days} дней назад", days
        return dt.strftime("%d.%m.%Y"), days
    except Exception:
        return "недавно", 99


def _pick_icon(text: str) -> str:
    text_lower = text.lower()
    for keyword, icon in NEWS_ICONS.items():
        if keyword in text_lower:
            return icon
    return "💬"


def _extract_tags(text: str) -> list[str]:
    # Берём хэштеги из поста
    hashtags = re.findall(r"#(\w+)", text)
    # Добавляем ключевые найденные слова
    found = []
    for word in ["хакатон", "стажировка", "вакансия", "AI", "Иннополис", "Казань", "IT"]:
        if word.lower() in text.lower() and word not in found:
            found.append(word)
    tags = [h for h in hashtags[:4] if len(h) > 2]
    for f in found[:3]:
        if f not in tags:
            tags.append(f)
    return tags[:5]


def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in IT_KEYWORDS)


def _parse_channel(html: str, channel_handle: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    posts = []

    messages = soup.select(".tgme_widget_message")
    # Берём последние сообщения первыми
    for msg in reversed(messages):
        text_el = msg.select_one(".tgme_widget_message_text")
        if not text_el:
            continue
        raw_text = text_el.get_text(separator="\n", strip=True)
        if len(raw_text) < 30:
            continue
        if not _is_relevant(raw_text):
            continue

        time_el = msg.select_one("time")
        dt_str = time_el.get("datetime", "") if time_el else ""
        date_label, date_sort = _time_ago(dt_str)

        post_link_el = msg.select_one(".tgme_widget_message_date")
        post_url = post_link_el.get("href", f"https://t.me/{channel_handle}") if post_link_el else f"https://t.me/{channel_handle}"

        # Первая строка или первые 80 символов — заголовок
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        title = lines[0][:90] if lines else raw_text[:90]
        if len(title) < 20 and len(lines) > 1:
            title = (lines[0] + " " + lines[1])[:90]

        summary = raw_text[:300].strip()
        if len(raw_text) > 300:
            summary += "…"

        tags = _extract_tags(raw_text)
        icon = _pick_icon(raw_text)

        # ID поста из ссылки
        post_id = re.search(r"/(\d+)$", post_url)
        uid = f"tg_{channel_handle}_{post_id.group(1) if post_id else len(posts)}"

        posts.append({
            "id": uid,
            "title": title,
            "source": channel_handle,
            "sourceType": "telegram",
            "dateLabel": date_label,
            "dateSort": date_sort,
            "tags": tags,
            "summary": summary,
            "icon": icon,
            "url": post_url,
        })

        if len(posts) >= MAX_POSTS_PER_CHANNEL:
            break

    return posts


async def fetch_tg_news() -> list[dict]:
    all_news: list[dict] = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        tasks = [
            client.get(f"https://t.me/s/{channel_id}")
            for channel_id, _, _ in CHANNELS
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    for (channel_id, handle, _), resp in zip(CHANNELS, responses):
        if isinstance(resp, Exception):
            logger.warning("Telegram scrape failed for %s: %s", handle, resp)
            continue
        if resp.status_code != 200:
            logger.warning("Telegram %s returned %d", handle, resp.status_code)
            continue
        try:
            posts = _parse_channel(resp.text, handle)
            all_news.extend(posts)
            logger.info("Telegram %s: %d posts", handle, len(posts))
        except Exception as e:
            logger.warning("Parse error for %s: %s", handle, e)

    # Сортируем по дате (свежее сначала)
    all_news.sort(key=lambda x: x.get("dateSort", 99))
    return all_news[:20]
