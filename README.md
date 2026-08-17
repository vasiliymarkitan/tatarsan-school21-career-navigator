# Карьерный Навигатор 21

ИИ-дайджест стажировок и junior-вакансий для IT-специалистов Татарстана.  
Парсит hh.ru и Telegram-каналы, генерирует саммари через GigaChat, авторизует через Telegram Login Widget.

## Технический стек

### Backend
| Компонент | Технология |
|---|---|
| REST API | FastAPI 0.110+ (async) |
| ASGI-сервер | uvicorn[standard] |
| Валидация | Pydantic 2.0+ |
| JWT-сессии | python-jose[cryptography] |

### AI / LLM
| Компонент | Технология |
|---|---|
| Модель | **GigaChat** (Сбер) |
| SDK | gigachat 0.2.1 |
| Scope | `GIGACHAT_API_PERS` / `GIGACHAT_API_CORP` |
| Сценарии | Саммари вакансий · Карьерные советы · AI-агент plan→act→verify |

### Парсинг данных
| Компонент | Технология |
|---|---|
| HTTP-клиент | httpx 0.27+ (async) |
| HTML-парсинг | BeautifulSoup4 + lxml |
| Вакансии | hh.ru Public API (без токена, area=88 Татарстан) |
| Новости | Telegram HTML scraping (`t.me/s/<channel>`) |

### Авторизация
| Компонент | Технология |
|---|---|
| Вход | Telegram Login Widget |
| Верификация | HMAC-SHA256 (подпись Telegram) |
| Сессии | httpOnly JWT cookie (30 дней) |

### Инфраструктура
| Компонент | Технология |
|---|---|
| Контейнеризация | Docker + docker-compose |
| Reverse proxy | nginx:alpine (80 → uvicorn :8000) |

### Frontend
- Vanilla JS (без фреймворков)
- CSS custom properties, тёмная тема
- Google Fonts: Inter + JetBrains Mono

### Источники данных
| Источник | Метод |
|---|---|
| hh.ru | Public REST API |
| @kazanit | HTML scraping |
| @it_tatarstan | HTML scraping |
| @innopolis_live | HTML scraping |
| @school21_kazan | HTML scraping |

## Быстрый старт (Docker)

```bash
# 1. Клонировать репозиторий
git clone ssh://git@tatarsan.space/Dinara/career_navigator_21school.git
cd career_navigator_21school

# 2. Создать .env из примера и заполнить переменные
cp .env.example .env
nano .env

# 3. Поднять проект
docker compose up --build -d
```

Сайт доступен на **http://localhost**.

---

## Переменные окружения (`.env`)

| Переменная | Обязательная | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | да | Токен бота от @BotFather |
| `BOT_USERNAME` | да | Username бота без @ (например `my_bot`) |
| `JWT_SECRET` | да | Случайная строка для подписи JWT — `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `GIGACHAT_CREDENTIALS` | нет | Authorization Key из [developers.sber.ru/studio](https://developers.sber.ru/studio) (base64 ClientID:ClientSecret) |
| `GIGACHAT_SCOPE` | нет | `GIGACHAT_API_PERS` (физлицо) или `GIGACHAT_API_CORP` |

Без `GIGACHAT_CREDENTIALS` AI-функции отключаются, остальное работает.

---

## Локальный запуск без Docker

Требования: Python 3.11+

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_web.txt

cp .env.example .env
# заполнить .env

uvicorn api_server:app --reload --port 8000
```

Сайт: **http://localhost:8000**

---

## Структура проекта

```
.
├── api_server.py        # FastAPI backend — все роуты
├── ai/
│   └── giga.py          # GigaChat: саммари вакансий, карьерные советы
├── parser/
│   ├── hh_parser.py     # Парсер hh.ru API
│   └── tg_parser.py     # Парсер публичных Telegram-каналов
├── web/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js       # Логика UI, фильтры, авторизация
│       └── data.js      # Статические данные (резерв)
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
└── requirements_web.txt
```

---

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/live-vacancies` | Вакансии с hh.ru (с фильтрами `category`, `role`, `format`, `q`) |
| GET | `/api/live-news` | Новости из Telegram-каналов |
| GET | `/api/stats` | Счётчики: вакансии, стажировки, компании |
| GET | `/api/health` | Состояние кэша и парсера |
| POST | `/api/refresh` | Ручной запуск парсинга |
| POST | `/api/auth/telegram` | Авторизация через Telegram Login Widget |
| GET | `/api/auth/me` | Текущий пользователь по cookie |
| POST | `/api/auth/logout` | Выход |
| GET | `/api/ai/status` | Включён ли GigaChat |
| POST | `/api/ai/career-advice` | Персональные советы (`role`, `skills`, `goals`) |
| POST | `/api/ai/agent-advice` | **AI-агент** plan→act→verify: планирует поиск, ищет на hh.ru, анализирует результаты |
| POST | `/api/ai/summarize` | AI-саммари вакансии (`title`, `company`, `requirement`, `responsibility`) |

### Пример: карьерный совет

```bash
curl -X POST http://localhost:8000/api/ai/career-advice \
  -H "Content-Type: application/json" \
  -d '{"role":"backend","skills":"Python, SQL","goals":"стажировка в Казани"}'
```

---

## AI-disclosure

Проект использует **GigaChat** (Сбер) в трёх сценариях:

| Задача | Модуль | Как проверяли корректность |
|--------|--------|---------------------------|
| Саммари вакансии (2 предложения) | `ai/giga.py:summarize_vacancy` | Ручное сравнение с оригинальным текстом вакансии на hh.ru; галлюцинации (выдуманные требования) отклонялись |
| Персональный карьерный совет | `ai/giga.py:get_career_advice` | Проверка реальности названных компаний и технологий; ответы сравнивались с актуальными страницами карьеры компаний |
| **AI-агент** plan→act→verify | `ai/giga.py:run_career_agent` | Агент сначала планирует запрос, затем делает реальный поиск hh.ru API (верифицируемые данные), затем оценивает найденные вакансии — результат привязан к реальным объявлениям, что исключает выдумывание позиций |

**Модель**: GigaChat (GIGACHAT_API_PERS / GIGACHAT_API_CORP)  
**Что НЕ генерируется AI**: вакансии, компании, зарплаты — всё парсится с hh.ru и Telegram напрямую.

---

## Деплой на сервер

```bash
# На сервере: обновить файлы и пересобрать контейнер
git pull origin develop
docker compose up --build -d
```

Nginx слушает порт 80, проксирует на uvicorn :8000.  
Для HTTPS — добавить certbot и поменять `secure=False` на `secure=True` в `api_server.py:347`.
