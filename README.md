# Карьерный Навигатор 21

ИИ-дайджест стажировок и junior-вакансий для участников Школы 21 и начинающих IT-специалистов Татарстана.

Сервис **реально** опрашивает hh.ru Public API и Yandex Search API (страницы вакансий, в запросе `site:hh.ru`), плюс четыре публичных Telegram-канала для новостей. Дубли снимаются, статичные «демо-карточки» не подставляются. Поиск вакансий по роли работает без входа. Персональный дайджест в Telegram опционален. MAX не подключён и не обещается.

## Что честно работает

- Вакансии: публичный API hh.ru (Татарстан `area=88` + remote junior/стажировки) **и** Yandex Cloud Search API v2 (`POST /v2/web/search`) по запросам junior/стажировка + Казань/Татарстан/Иннополис/удалёнка РФ.
- Анонимный поиск: без выбранной роли сразу ищем IT junior/стажировки Казань/Татарстан/Иннополис и удалёнку РФ. Роль сужает выдачу. Telegram не нужен. Если кэш пуст, сервер ищет сразу, не ждёт 30-минутный цикл.
- Карточка только при живом `http(s)` URL из выдачи. Компания и зарплата — только если они уже есть в заголовке/сниппете. Источник: `Yandex Search → hh.ru`, не выдуманный сайт.
- Новости: Yandex Search по `site:t.me/kazanit`, `it_tatarstan`, `innopolis_live`, `school21_kazan` (плюс HTML-превью `t.me/s/`, если оно отвечает). Другие сайты не добавляем.
- Дедуп: id, URL, пара «компания + название», близкие заголовки одной компании.
- Авторизация: Telegram Login Widget → httpOnly JWT. Слабый/пустой `JWT_SECRET` сессии не выдаёт. На просмотр вакансий не влияет.
- Дайджест: сохранение расписания + ручная отправка + планировщик по МСК. Email нет. Если бот не настроен — так и пишем.
- LLM на демо: **YandexGPT Lite (AI Studio)**. GigaChat оставлен переключаемым (`LLM_PROVIDER=gigachat`).

Если и hh.ru, и Yandex Search падают, `GET /api/live-vacancies?role=…` отвечает **503**, а `/api/health` кладёт текст в `fetch_error` и `errors[]`. Пустой успешный ответ API — это «ничего не нашли», а не скрытый 403.

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
# поиск вакансий: тот же ключ, если у него есть yc.search-api.execute;
# иначе YANDEX_SEARCH_API_KEY + роль search-api.webSearch.user
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
| `YANDEX_API_KEY` | для AI и поиска | API-ключ. Для GPT — scope языковых моделей; для поиска вакансий — ещё `yc.search-api.execute` |
| `YANDEX_FOLDER_ID` | для AI и поиска | folder id (`b1g…`), модель `gpt://<folder>/yandexgpt-lite/latest` |
| `YANDEX_SEARCH_API_KEY` | нет | отдельный ключ Search API, если `YANDEX_API_KEY` не умеет поиск. Не выдумывать и не коммитить |
| `YANDEX_SEARCH_API_URL` | нет | по умолчанию `https://searchapi.api.cloud.yandex.net` |
| `YANDEX_MODEL` | нет | по умолчанию `yandexgpt-lite` |
| `YANDEX_API_BASE` | нет | `https://ai.api.cloud.yandex.net/v1` |
| `GIGACHAT_CREDENTIALS` | только если `LLM_PROVIDER=gigachat` | ключ Сбера |
| `COOKIE_SECURE` | нет | `true` только за HTTPS |
| `HH_USER_AGENT` | нет | свой UA без личного email |

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/live-vacancies` | Живые вакансии. Без `role` и с `?role=backend` при пустом кэше сразу ищет hh.ru + Yandex Search |
| GET | `/api/live-news` | Живые посты назначенных каналов через Yandex Search (+ t.me/s, если доступен) |
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
- Парсинг карьерных сайтов компаний — в источниках не числится, пока его нет. Если Yandex вернул URL SuperJob/Habr Career, карточка помечается `Yandex Search → <хост>`, сам сайт в список источников не добавляется.
- Инструмент Web Search у агента AI Studio (модель сама вызывает tool) ≠ сырой Search API. Карточки строим из Search API + XML, не из ответа модели.
- `main.py` — старый каркас aiogram-бота без модулей `db/` / `bot/`. Рабочий путь — FastAPI + compose.

## Yandex Search API (демо на VPS)

Документация: [Search API concepts](https://aistudio.yandex.ru/docs/ru/search-api/concepts/), [quickstart](https://aistudio.yandex.ru/docs/ru/search-api/).  
Схема запроса — официальный proto `WebSearchRequest` / `WebSearchResponse` в [cloudapi search_service.proto](https://github.com/yandex-cloud/cloudapi/blob/master/yandex/cloud/searchapi/v2/search_service.proto). Python SDK семейства `yandex-cloud-ml-sdk` / `yandex-ai-studio-sdk` тот же API; в сервисе зовём REST напрямую, чтобы CI мокал HTTP.

**Синхронный текст:** `POST https://searchapi.api.cloud.yandex.net/v2/web/search`  
**Отложенный:** `POST …/v2/web/searchAsync` (Operation + poll) — для демо не используем.

Тело (поля proto, JSON camelCase): `query.searchType`, `query.queryText` (≤400), `query.familyMode`, `query.page`, `groupSpec.{groupMode,groupsOnPage,docsInGroup}`, `maxPassages` (1–5), `l10n`, `folderId`, `responseFormat=FORMAT_XML`, `userAgent`. `region` не подставляем — id региона не угадываем, география в `queryText` (`Казань|Татарстан|Иннополис` / удалёнка РФ) плюс операторы `site:` и `lang:ru`.

Ответ текстового поиска: `{ "rawData": "<base64 XML или HTML>" }`. Это **не** JSON `{title,url,snippet}`. Парсим XML: `<doc>` → `<url>`, `<title>`, `<passages>` / `<headline>`. Готовый JSON есть у image search by image, не у `/v2/web/search`.

Auth: `Authorization: Api-Key <YANDEX_API_KEY>`, `folderId` в теле. IAM `Bearer` — запасной путь (`YANDEX_IAM_TOKEN`). К каталогу должен быть привязан биллинг-аккаунт, иначе запросы не пойдут. Документация AI Studio: ключ студии уже может нести нужные роли.

Если всё же 401/403 — честный `errors[]` / HTTP 503, без фейковых карточек. Тогда на сервисе:

1. Роль `search-api.webSearch.user` и/или `search-api.executor`
2. Scope ключа `yc.search-api.execute`
3. При отдельном ключе — `YANDEX_SEARCH_API_KEY` только на VPS, не в git

## Структура

```
api_server.py          FastAPI
auth_utils.py          JWT + проверка Telegram
ai/provider.py         фасад LLM (yandex | gigachat)
ai/yandex.py           YandexGPT Lite / AI Studio
ai/giga.py             GigaChat, переключаемый
parser/hh_parser.py        hh.ru (ошибки HTTP больше не глотаются)
parser/yandex_search.py    Yandex Search API v2 → карточки с живым URL
parser/tg_parser.py        t.me/s/
parser/dedup.py            дедуп вакансий и новостей
digest/                настройки, превью, Bot API, планировщик
web/                   статичный фронт
docker-compose.yml     nginx :8083 → app :8000
tests/                 pytest
```
