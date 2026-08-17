from parser.dedup import dedup_news, dedup_vacancies, normalize_text, title_similarity


def test_exact_id_and_url_dedup():
    items = [
        {"id": "hh_1", "title": "Junior Python", "company": "ICL", "url": "https://hh.ru/vacancy/1", "source": {"type": "hh"}, "dateSort": 0},
        {"id": "hh_1", "title": "Junior Python", "company": "ICL", "url": "https://hh.ru/vacancy/1?query=1", "source": {"type": "hh"}, "dateSort": 0},
    ]
    assert len(dedup_vacancies(items)) == 1


def test_near_duplicate_title_same_company():
    items = [
        {"id": "a", "title": "Junior Python Developer", "company": "ICL Services", "url": "https://hh.ru/vacancy/1", "source": {"type": "hh"}, "dateSort": 1},
        {"id": "b", "title": "Python Developer Junior", "company": "ICL Services", "url": "https://hh.ru/vacancy/2", "source": {"type": "hh"}, "dateSort": 0},
    ]
    kept = dedup_vacancies(items)
    assert len(kept) == 1


def test_different_companies_are_kept():
    items = [
        {"id": "a", "title": "Junior Python", "company": "ICL", "url": "https://hh.ru/vacancy/1", "source": {"type": "hh"}, "dateSort": 0},
        {"id": "b", "title": "Junior Python", "company": "Bars", "url": "https://hh.ru/vacancy/2", "source": {"type": "hh"}, "dateSort": 0},
    ]
    assert len(dedup_vacancies(items)) == 2


def test_website_wins_over_hh_copy():
    items = [
        {"id": "hh_9", "title": "Frontend React", "company": "KazanExpress", "url": "https://hh.ru/vacancy/9", "source": {"type": "hh"}, "dateSort": 0},
        {"id": "web_1", "title": "Frontend React", "company": "KazanExpress", "url": "https://career.example/1", "source": {"type": "website"}, "dateSort": 0},
    ]
    kept = dedup_vacancies(items)
    assert len(kept) == 1
    assert kept[0]["source"]["type"] == "website"


def test_news_dedup_by_url_and_title():
    items = [
        {"id": "tg_a_1", "title": "Хакатон в Казани", "source": "@kazanit", "url": "https://t.me/kazanit/10", "dateSort": 0},
        {"id": "tg_a_2", "title": "Хакатон в Казани!", "source": "@kazanit", "url": "https://t.me/kazanit/10", "dateSort": 1},
    ]
    assert len(dedup_news(items)) == 1


def test_normalize_and_similarity_helpers():
    assert normalize_text("Ёлка, Junior!") == "елка junior"
    assert title_similarity("Junior Python Developer", "Python Developer Junior") > 0.7
