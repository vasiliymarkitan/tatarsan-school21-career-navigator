// Data is loaded from the API — see loadLiveData() in app.js
let VACANCIES = [];
let NEWS = [];

const SOURCES = [
  { type: "telegram", name: "@kazanit",          desc: "IT-новости Казани" },
  { type: "telegram", name: "@innopolis_live",   desc: "Новости Иннополиса" },
  { type: "telegram", name: "@it_tatarstan",     desc: "IT Татарстан" },
  { type: "telegram", name: "@kazan_dev_jobs",   desc: "Вакансии разработчиков" },
  { type: "telegram", name: "@school21_kazan",   desc: "Школа 21 Казань" },
  { type: "telegram", name: "@tatarstan_digital",desc: "Цифровой Татарстан" },
  { type: "website",  name: "kazanexpress.ru",   desc: "KazanExpress карьера" },
  { type: "website",  name: "innopolis.ru",      desc: "Вакансии Иннополиса" },
  { type: "website",  name: "tatneft.ru",        desc: "Татнефть работа" },
  { type: "website",  name: "icl-services.com",  desc: "ICL Services вакансии" },
  { type: "website",  name: "bars.group",        desc: "Bars Group карьера" },
  { type: "website",  name: "cft.ru",            desc: "ЦФТ вакансии" },
  { type: "hh",       name: "hh.ru",             desc: "Агрегатор вакансий" },
];

const DIRECT_SOURCE_ROLE_KEYS = new Set();
