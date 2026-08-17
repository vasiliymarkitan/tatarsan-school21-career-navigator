from parser.tg_parser import CHANNELS, _parse_channel


HTML = """
<html><body>
<div class="tgme_widget_message">
  <div class="tgme_widget_message_text">Хакатон Digital Tatarstan: ищем разработчиков Python и frontend в Казани. Призовой фонд и стажировки.</div>
  <time datetime="2026-08-16T12:00:00+00:00"></time>
  <a class="tgme_widget_message_date" href="https://t.me/kazanit/42"></a>
</div>
<div class="tgme_widget_message">
  <div class="tgme_widget_message_text">Сегодня хорошая погода и вкусный чай в парке.</div>
  <time datetime="2026-08-16T11:00:00+00:00"></time>
  <a class="tgme_widget_message_date" href="https://t.me/kazanit/41"></a>
</div>
</body></html>
"""


def test_parse_keeps_only_relevant_it_posts():
    posts = _parse_channel(HTML, "@kazanit")
    assert len(posts) == 1
    assert posts[0]["id"] == "tg_@kazanit_42"
    assert posts[0]["url"] == "https://t.me/kazanit/42"
    assert "хакатон" in posts[0]["title"].lower() or "хакатон" in posts[0]["summary"].lower()


def test_channels_are_the_real_ones_only():
    handles = [handle for _, handle, _ in CHANNELS]
    assert handles == ["@kazanit", "@it_tatarstan", "@innopolis_live", "@school21_kazan"]
