from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = [
    "hh.ru и Yandex Search",
    "Yandex Search по четырём назначенным каналам",
    "url:t.me/",
    "site:hh.ru",
    "site:t.me",
    "hh.ru Public API",
    "t.me/s/",
    "Фейковых карточек нет",
    "без фейковых",
    "не подставляет фейки",
    "не подставляем фейки",
    "без выдуманных карточек",
    "без статичных карточек",
    "живой кэш",
    "живого кэша",
    "из живого кэша",
    "Загружаем топ-5 из живого кэша",
    "Email и MAX не подключены",
    "После сохранения напишите боту /start — иначе Bot API не доставит сообщение",
    "План → живой кэш вакансий",
    "ACT · кэш",
    "ACT · hh.ru",
]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_index_keeps_product_surface():
    html = _read("web", "index.html")
    assert "Telegram-авторизация не настроена" not in html
    assert "Топ-5 за день" in html
    assert "Подобрать вакансии" in html
    assert "Вакансии с hh.ru · новости IT Татарстана" in html
    assert "Источники" not in html
    assert ">PLAN<" not in html
    assert ">VERIFY<" not in html


def test_visitor_copy_has_no_engineering_internals():
    blob = "\n".join(
        [
            _read("web", "index.html"),
            _read("web", "js", "app.js"),
            _read("web", "js", "data.js"),
        ]
    )
    lower = blob.lower()
    for phrase in FORBIDDEN:
        assert phrase.lower() not in lower, phrase


def test_app_js_keeps_filters_and_product_empty_states():
    js = _read("web", "js", "app.js")
    assert "hh.ru ничего не вернул" not in js
    assert "Живой кэш пуст" not in js
    assert "params.set('location'" in js
    assert "Подобрать снова" in js


def test_readme_has_no_missing_features_block():
    readme = _read("README.md")
    assert "Чего нет и не обещаем" not in readme
    assert "чего не сделали" not in readme.lower()
