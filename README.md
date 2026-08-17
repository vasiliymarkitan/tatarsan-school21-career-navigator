# Карьерный Навигатор 21

ИИ-дайджест стажировок и junior-вакансий для участников Школы 21 и начинающих IT-специалистов Татарстана.

Сервис **реально** опрашивает hh.ru и четыре публичных Telegram-канала, снимает дубли и не подставляет статичные «демо-карточки». Персональный дайджест уходит в Telegram. MAX не подключён и не обещается.

## Что честно работает

- Вакансии: публичный API hh.ru (Татарстан `area=88` + remote junior/стажировки).
- Новости: HTML-превью `t.me/s/kazanit`, `it_tatarstan`, `innopolis_live`, `school21_kazan`.
- Дедуп: id, URL, пара «компания + название», близкие заголовки одной компании.
- Авторизация: Telegram Login Widget → httpOnly JWT. Слабый/пустой `JWT_SECRET` сессии не выдаёт.
- Дайджест: сохранение расписания + ручная отправка + планировщик по МСК. Email нет.
- LLM на демо: **YandexGPT Lite (AI Studio)**. GigaChat оставлен переключаемым (`LLM_PROVIDER=gigachat`).

Если источник молчит, API отдаёт пустой список и ошибку источника — не фейковые вакансии.

## Быстрый старт (локально)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# заполните JWT_SECRET (32+ символов). Остальное можно оставить пустым для просмотра вакансий.

CN21_DISABLE_BACKGROUND=1 pytest -q

uvicorn api_server:app --reload --port 8000
```

Сайт: http://localhost:8000

Без `YANDEX_API_KEY` + `YANDEX_FOLDER_ID` карточки и парсер работают, AI-эндпоинты отвечают 503.

## Docker / публичное демо

Порт хоста **8083**. Порты 80 и 443 этот compose не занимает.

```bash
cp .env.example .env
# обязателен JWT_SECRET; для дайджеста — TELEGRAM_BOT_TOKEN и BOT_USERNAME
# для AI на демо — YANDEX_API_KEY, YANDEX_FOLDER_ID, LLM_PROVIDER=yandex
docker compose up --build -d
```

Открыть: http://localhost:8083  
Health: http://localhost:8083/api/health

### Выкладка координатором на общий VPS

SSH и выкладку делает координатор. Агент на чужие машины ничего не копирует.

- Хост: `135.106.187.7`
- Каталог: `/opt/tatarsan/school21`
- Порт: `8083`

```bash
# на VPS, от координатора
sudo mkdir -p /opt/tatarsan/school21
# синхронизировать этот репозиторий в /opt/tatarsan/school21
cd /opt/tatarsan/school21
cp -n .env.example .env
# вписать секреты в .env, не коммитить
docker compose up --build -d
```

Демо: `http://135.106.187.7:8083`

`COOKIE_SECURE=true` ставить только когда перед сервисом появится HTTPS. На голом `:8083` оставить `false`.

Один worker uvicorn: кэш вакансий и планировщик дайджеста живут в памяти процесса.

## Переменные окружения

| Переменная | Обязательная | Описание |
|---|---|---|
| `JWT_SECRET` | для входа | ≥32 символа, не плейсхолдер из примера |
| `TELEGRAM_BOT_TOKEN` | для входа и дайджеста | токен @BotFather |
| `BOT_USERNAME` | для виджета | username без `@` |
| `LLM_PROVIDER` | нет | `yandex` (по умолчанию) или `gigachat` |
| `YANDEX_API_KEY` | для AI на демо | API-ключ AI Studio |
| `YANDEX_FOLDER_ID` | для AI на демо | folder id, модель `gpt://<folder>/yandexgpt-lite/latest` |
| `YANDEX_MODEL` | нет | по умолчанию `yandexgpt-lite` |
| `YANDEX_API_BASE` | нет | `https://ai.api.cloud.yandex.net/v1` |
| `GIGACHAT_CREDENTIALS` | только если `LLM_PROVIDER=gigachat` | ключ Сбера |
| `COOKIE_SECURE` | нет | `true` только за HTTPS |
| `HH_USER_AGENT` | нет | свой UA без личного email |

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/live-vacancies` | Живые вакансии hh.ru после дедупа |
| GET | `/api/live-news` | Живые посты Telegram |
| GET | `/api/sources` | Только реально опрашиваемые источники |
| GET | `/api/stats` | Счётчики по кэшу, без статики |
| GET | `/api/health` | Кэш, JWT, Telegram, LLM |
| POST | `/api/refresh` | Ручной парсинг |
| POST | `/api/auth/telegram` | Telegram Login → httpOnly JWT |
| GET | `/api/auth/me` | Текущая сессия |
| POST | `/api/auth/logout` | Выход |
| GET/POST | `/api/digest/settings` | Настройки дайджеста (нужна сессия) |
| GET | `/api/digest/preview` | Текст дайджеста из живого кэша |
| POST | `/api/digest/send` | Отправить дайджест в Telegram сейчас |
| GET | `/api/ai/status` | Провайдер и чего не хватает |
| POST | `/api/ai/career-advice` | Совет модели |
| POST | `/api/ai/agent-advice` | План → hh.ru → разбор |
| POST | `/api/ai/summarize` | Саммари одной вакансии |

## Тесты

```bash
pip install -r requirements-dev.txt
CN21_DISABLE_BACKGROUND=1 pytest -q
```

CI: `.github/workflows/ci.yml` гоняет тот же набор на Python 3.11.

## Чего нет

- Мессенджер MAX — не реализован и не обещается.
- Email-дайджест — не реализован.
- Парсинг карьерных сайтов компаний — в источниках не числится, пока его нет.
- `main.py` — старый каркас aiogram-бота без модулей `db/` / `bot/`. Рабочий путь — FastAPI + compose.

## Структура

```
api_server.py          FastAPI
auth_utils.py          JWT + проверка Telegram
ai/provider.py         фасад LLM (yandex | gigachat)
ai/yandex.py           YandexGPT Lite / AI Studio
ai/giga.py             GigaChat, переключаемый
parser/hh_parser.py    hh.ru
parser/tg_parser.py    t.me/s/
parser/dedup.py        дедуп вакансий и новостей
digest/                настройки, превью, Bot API, планировщик
web/                   статичный фронт
docker-compose.yml     nginx :8083 → app :8000
tests/                 pytest
```
