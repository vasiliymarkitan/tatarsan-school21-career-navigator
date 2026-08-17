// Live data comes from the API. This file only holds empty defaults
// and the list of sources that the backend actually polls.
let VACANCIES = [];
let NEWS = [];

const SOURCES = [
  { type: "hh", name: "hh.ru", desc: "Публичный API вакансий, area=88 + remote" },
  { type: "telegram", name: "@kazanit", desc: "Публичный t.me/s/kazanit" },
  { type: "telegram", name: "@it_tatarstan", desc: "Публичный t.me/s/it_tatarstan" },
  { type: "telegram", name: "@innopolis_live", desc: "Публичный t.me/s/innopolis_live" },
  { type: "telegram", name: "@school21_kazan", desc: "Публичный t.me/s/school21_kazan" },
];
