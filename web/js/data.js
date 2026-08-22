// Live data comes from the API. This file only holds empty defaults
// and the list of sources that the backend actually polls.
let VACANCIES = [];
let NEWS = [];

const SOURCES = [
  { type: "hh", name: "hh.ru", desc: "Публичный API вакансий, area=88 + remote" },
  { type: "yandex", name: "Yandex Search → hh.ru", desc: "Search API v2, запросы site:hh.ru" },
  { type: "telegram", name: "@kazanit", desc: "Yandex Search site:t.me/kazanit" },
  { type: "telegram", name: "@it_tatarstan", desc: "Yandex Search site:t.me/it_tatarstan" },
  { type: "telegram", name: "@innopolis_live", desc: "Yandex Search site:t.me/innopolis_live" },
  { type: "telegram", name: "@school21_kazan", desc: "Yandex Search site:t.me/school21_kazan" },
];
