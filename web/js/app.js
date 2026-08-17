// ===== STATE =====
const state = {
  category: 'all',
  role: 'all',
  format: 'all',
  location: 'all',
  query: '',
  sort: 'date'
};

// ===== FILTER & RENDER =====
function filterVacancies() {
  return VACANCIES.filter(v => {
    // дедупликация: скрываем hh.ru-вакансию, если компания уже есть в прямых источниках
    if (v.source.type === 'hh' && DIRECT_SOURCE_ROLE_KEYS.has(v.company.toLowerCase() + '::' + v.role)) return false;

    if (state.category !== 'all' && v.category !== state.category) return false;
    if (state.role !== 'all' && v.role !== state.role) return false;
    if (state.format !== 'all' && v.format !== state.format) return false;
    if (state.location !== 'all' && v.location !== state.location) return false;
    if (state.query) {
      const q = state.query.toLowerCase();
      const haystack = [v.title, v.company, ...v.tags, v.aiSummary].join(' ').toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  }).sort((a, b) => {
    if (state.sort === 'date') return a.dateSort - b.dateSort;
    if (state.sort === 'company') return a.company.localeCompare(b.company, 'ru');
    return 0;
  });
}

function renderSourceBadge(source) {
  const type = source.type;
  let cls, icon;

  if (type === 'telegram') {
    cls = 'tg';
    icon = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>`;
  } else if (type === 'hh') {
    cls = 'hh';
    icon = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v3h4V8h2v8h-2v-3h-4v3z"/></svg>`;
  } else {
    cls = 'web';
    icon = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`;
  }

  return `<a href="${source.url}" target="_blank" rel="noopener" class="source-badge ${cls}" title="Открыть источник">${icon}${source.name}</a>`;
}

function renderTag(tag) {
  let cls = 'tag';
  const t = tag.toLowerCase();
  if (t === 'стажировка') cls += ' type-internship';
  else if (t === 'junior') cls += ' type-junior';
  else if (t === 'remote') cls += ' format-remote';
  else if (t === 'hybrid') cls += ' format-hybrid';
  return `<span class="${cls}">${tag}</span>`;
}

function renderCard(v) {
  return `
    <article class="card" data-id="${v.id}">
      <div class="card-header">
        <div class="card-company">
          <div class="company-logo" style="background:${v.logoColor};color:${v.logoText}">${v.logo}</div>
          <div>
            <div class="company-name">${v.company}</div>
            <div class="company-location">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="opacity:.5;vertical-align:middle;margin-right:2px"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
              ${v.location}
            </div>
          </div>
        </div>
        <div class="card-meta">
          ${renderSourceBadge(v.source)}
          <div class="card-date">${v.dateLabel}</div>
        </div>
      </div>

      <h3 class="card-title">${v.title}</h3>

      <div class="ai-summary">
        <div class="ai-summary-header">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          ИИ-саммари
        </div>
        <div class="ai-summary-text">${v.aiSummary}</div>
      </div>

      <div class="card-tags">
        ${v.tags.map(renderTag).join('')}
      </div>

      <div class="card-footer">
        <div class="card-salary">${v.salary}</div>
        <a href="${v.url}" class="card-apply" target="_blank">
          ${v.source.type === 'hh' ? 'На hh.ru' : 'Подробнее'}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      </div>
    </article>
  `;
}

function renderVacancies() {
  const grid = document.getElementById('cardsGrid');
  const filtered = filterVacancies();
  const countEl = document.getElementById('resultsCount');

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">Ничего не найдено</div>
        <div class="empty-sub">Попробуй изменить фильтры или поисковый запрос</div>
      </div>`;
  } else {
    grid.innerHTML = filtered.map(renderCard).join('');
  }

  const total = filtered.length;
  countEl.textContent = `Найдено: ${total} ${declVacancy(total)}`;

  // update tab counts
  document.getElementById('countAll').textContent = VACANCIES.length;
  document.getElementById('countVacancies').textContent = VACANCIES.filter(v => v.category === 'vacancy').length;
  document.getElementById('countInternships').textContent = VACANCIES.filter(v => v.category === 'internship').length;
}

function declVacancy(n) {
  if (n % 10 === 1 && n % 100 !== 11) return 'результат';
  if ([2,3,4].includes(n % 10) && ![12,13,14].includes(n % 100)) return 'результата';
  return 'результатов';
}

// ===== NEWS =====
function renderNews() {
  const grid = document.getElementById('newsGrid');
  grid.innerHTML = NEWS.map(n => `
    <article class="news-card">
      <div class="news-card-header">
        <div class="news-icon">${n.icon}</div>
        <h3 class="news-title">${n.title}</h3>
      </div>
      <p class="news-summary">${n.summary}</p>
      <div class="news-footer">
        <div class="news-meta">
          <span class="news-source ${n.sourceType}">${n.source}</span>
          <span class="news-date">${n.dateLabel}</span>
        </div>
        <div class="news-tags">
          ${n.tags.map(t => `<span class="news-tag">${t}</span>`).join('')}
        </div>
      </div>
    </article>
  `).join('');
}

// ===== SOURCES =====
function renderSources() {
  const grid = document.querySelector('.sources-grid');
  if (!grid) return;
  grid.innerHTML = SOURCES.map(s => `
    <div class="source-item">
      <div class="source-icon ${s.type}">${s.type === 'telegram' ? 'TG' : 'WEB'}</div>
      <span>${s.name}</span>
    </div>
  `).join('');
}

// ===== FILTERS =====
function initFilters() {
  document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      const filter = btn.dataset.filter;
      const value = btn.dataset.value;

      // deactivate siblings
      document.querySelectorAll(`[data-filter="${filter}"]`).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      state[filter] = value;
      renderVacancies();
    });
  });

  // Quick tags in hero
  document.querySelectorAll('.quick-tag').forEach(btn => {
    btn.addEventListener('click', () => {
      const role = btn.dataset.role;
      state.role = role;
      document.querySelectorAll('[data-filter="role"]').forEach(b => {
        b.classList.toggle('active', b.dataset.value === role);
      });
      renderVacancies();
      document.getElementById('vacancies').scrollIntoView({ behavior: 'smooth' });
    });
  });

  // Sort
  document.getElementById('sortSelect').addEventListener('change', e => {
    state.sort = e.target.value;
    renderVacancies();
  });
}

// ===== SEARCH =====
let searchTimer;
function initSearch() {
  const input = document.getElementById('searchInput');
  input.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = input.value.trim();
      renderVacancies();
    }, 250);
  });

  document.querySelector('.search-btn').addEventListener('click', () => {
    state.query = input.value.trim();
    renderVacancies();
    document.getElementById('vacancies').scrollIntoView({ behavior: 'smooth' });
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      state.query = input.value.trim();
      renderVacancies();
      document.getElementById('vacancies').scrollIntoView({ behavior: 'smooth' });
    }
  });
}

// ===== MODALS =====
function openModal(id) {
  document.getElementById(id).classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  document.body.style.overflow = '';
}

function initModals() {
  // Auth modal — открывать только если не залогинен
  document.getElementById('loginBtn').addEventListener('click', () => {
    if (!_currentUser) openModal('authModal');
  });
  document.getElementById('authClose').addEventListener('click', () => closeModal('authModal'));

  // Digest modals
  ['digestBtn', 'digestBannerBtn', 'aiDigestBtn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', () => openModal('digestModal'));
  });
  document.getElementById('digestClose').addEventListener('click', () => closeModal('digestModal'));

  // Close on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });

  // Modal tabs (auth)
  document.querySelectorAll('.modal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.modal-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(target + 'Form').classList.add('active');
    });
  });

  // Interest chips in modal (toggle)
  document.querySelectorAll('.interest-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => chip.classList.toggle('active'));
  });

  // Schedule options
  document.querySelectorAll('.schedule-option input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.schedule-option').forEach(opt => opt.style.borderColor = '');
      if (radio.checked) radio.closest('.schedule-option').style.borderColor = 'var(--accent)';
    });
  });
}

// ===== BURGER MENU =====
function initBurger() {
  const burger = document.getElementById('burger');
  let mobileNav = document.getElementById('mobileNav');

  if (!mobileNav) {
    mobileNav = document.createElement('nav');
    mobileNav.className = 'nav-mobile';
    mobileNav.id = 'mobileNav';
    mobileNav.innerHTML = `
      <a href="#vacancies" class="nav-link" onclick="closeMobileNav()">Вакансии</a>
      <a href="#" class="nav-link" onclick="openModal('digestModal');closeMobileNav()">Дайджест</a>
      <a href="#news" class="nav-link" onclick="closeMobileNav()">IT-новости</a>
      <hr style="border-color:var(--border);margin:8px 0">
      <button class="btn btn-primary" onclick="openModal('authModal');closeMobileNav()">Войти</button>
    `;
    document.body.appendChild(mobileNav);
  }

  burger.addEventListener('click', () => {
    mobileNav.classList.toggle('open');
  });

  window.closeMobileNav = () => mobileNav.classList.remove('open');
}

// ===== HEADER SCROLL =====
function initHeaderScroll() {
  const header = document.getElementById('header');
  window.addEventListener('scroll', () => {
    header.style.boxShadow = window.scrollY > 10 ? '0 1px 16px rgba(0,0,0,.5)' : '';
  }, { passive: true });
}

// ===== NAV ACTIVE =====
function initNavHighlight() {
  const sections = ['vacancies', 'news'];
  const navLinks = document.querySelectorAll('.nav-link[data-section]');

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(l => l.classList.toggle('active', l.dataset.section === entry.target.id));
      }
    });
  }, { threshold: 0.3 });

  sections.forEach(id => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
}

// ===== COUNTER ANIMATION =====
function animateCounter(el, target, duration = 1200) {
  let start = 0;
  const step = timestamp => {
    if (!start) start = timestamp;
    const progress = Math.min((timestamp - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.floor(eased * target);
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = target;
  };
  requestAnimationFrame(step);
}

function initCounters() {
  // считаем из реальных данных (с учётом дедупликации hh.ru)
  const visible = VACANCIES.filter(v =>
    !(v.source.type === 'hh' && DIRECT_SOURCE_ROLE_KEYS.has(v.company.toLowerCase() + '::' + v.role))
  );
  const vacancyCount = visible.filter(v => v.category === 'vacancy').length;
  const internshipCount = visible.filter(v => v.category === 'internship').length;
  const companyCount = new Set(visible.map(v => v.company)).size;
  const sourceCount = new Set(visible.map(v => v.source.name)).size;

  // обновляем статику сразу, потом анимируем
  const elV = document.getElementById('statVacancies');
  const elI = document.getElementById('statInternships');
  const elC = document.querySelector('.stat:nth-child(3) .stat-num');
  const elS = document.querySelector('.stat:nth-child(4) .stat-num');

  const counters = [
    { el: elV, target: vacancyCount },
    { el: elI, target: internshipCount },
    { el: elC, target: companyCount },
    { el: elS, target: sourceCount },
  ];

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        counters.forEach(c => { if (c.el) animateCounter(c.el, c.target); });
        observer.disconnect();
      }
    });
  }, { threshold: 0.5 });
  const stats = document.querySelector('.stats');
  if (stats) observer.observe(stats);
}

// ===== CARD SAVE (demo) =====
function initCardSave() {
  document.getElementById('cardsGrid').addEventListener('click', e => {
    const saveBtn = e.target.closest('.card-save');
    if (!saveBtn) return;
    saveBtn.classList.toggle('saved');
    saveBtn.innerHTML = saveBtn.classList.contains('saved')
      ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>`
      : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`;
  });
}

// ===== TELEGRAM AUTH =====
let _currentUser = null;

window.onTelegramAuth = async function(tgUser) {
  try {
    const res = await fetch('/api/auth/telegram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tgUser),
    });
    const data = await res.json();
    if (data.success) {
      _currentUser = data.user;
      closeModal('authModal');
      _updateHeaderAuth(_currentUser);
    } else {
      alert('Ошибка авторизации: ' + (data.error || 'неизвестная ошибка'));
    }
  } catch (e) {
    alert('Не удалось подключиться к серверу');
  }
};

async function _loadTelegramWidget() {
  try {
    const res = await fetch('/api/auth/bot-info');
    const info = await res.json();
    const loading = document.getElementById('tgAuthLoading');
    const disabled = document.getElementById('tgAuthDisabled');
    const container = document.getElementById('telegramWidgetContainer');

    if (!info.enabled || !info.username) {
      if (loading) loading.style.display = 'none';
      if (disabled) disabled.style.display = 'block';
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', info.username);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.setAttribute('data-request-access', 'write');
    script.setAttribute('data-lang', 'ru');
    script.async = true;
    script.onload = () => { if (loading) loading.style.display = 'none'; };
    if (container) container.appendChild(script);
  } catch (_) {}
}

async function checkAuthState() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (data.authenticated) {
      _currentUser = data.user;
      _updateHeaderAuth(_currentUser);
    }
  } catch (_) {}
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  _currentUser = null;
  _updateHeaderAuth(null);
}

function _updateHeaderAuth(user) {
  const loginBtn = document.getElementById('loginBtn');
  let userBadge = document.getElementById('userBadge');

  if (user) {
    loginBtn.style.display = 'none';
    if (!userBadge) {
      userBadge = document.createElement('div');
      userBadge.id = 'userBadge';
      userBadge.className = 'user-badge';
      loginBtn.parentElement.insertBefore(userBadge, loginBtn);
    }
    const avatar = user.photo_url
      ? `<img class="user-avatar" src="${user.photo_url}" alt="">`
      : `<div class="user-avatar-placeholder">${(user.first_name || '?')[0]}</div>`;
    userBadge.innerHTML = `
      ${avatar}
      <span class="user-name">${user.first_name}${user.last_name ? ' ' + user.last_name : ''}</span>
      <button class="user-logout" onclick="logout()" title="Выйти">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
      </button>`;
    userBadge.style.display = 'flex';
  } else {
    loginBtn.style.display = '';
    if (userBadge) userBadge.style.display = 'none';
  }
}

// ===== DATA FROM API =====
function _showCardsLoading() {
  const grid = document.getElementById('cardsGrid');
  const countEl = document.getElementById('resultsCount');
  if (grid) grid.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon" style="font-size:32px">⏳</div>
      <div class="empty-title">Загружаем вакансии…</div>
      <div class="empty-sub">Получаем свежие данные с hh.ru и Telegram</div>
    </div>`;
  if (countEl) countEl.textContent = 'Загружаем…';
}

async function loadLiveData() {
  try {
    const [vacRes, newsRes] = await Promise.all([
      fetch('/api/live-vacancies?limit=200'),
      fetch('/api/live-news?limit=20'),
    ]);

    if (vacRes.ok) {
      const vacData = await vacRes.json();
      VACANCIES = vacData.vacancies || [];

      // Пересчитываем ключи дедупликации (website/telegram vs hh.ru)
      DIRECT_SOURCE_ROLE_KEYS.clear();
      VACANCIES
        .filter(v => v.source.type !== 'hh')
        .forEach(v => DIRECT_SOURCE_ROLE_KEYS.add(v.company.toLowerCase() + '::' + v.role));

      renderVacancies();
      initCounters();
      _showLiveBadge(vacData.lastUpdate, VACANCIES.length, vacData.source);
    }

    if (newsRes.ok) {
      const newsData = await newsRes.json();
      NEWS = newsData.news || [];
      renderNews();
    }

  } catch (_) {
    const grid = document.getElementById('cardsGrid');
    if (grid && !VACANCIES.length) grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <div class="empty-title">Не удалось загрузить данные</div>
        <div class="empty-sub">Проверьте соединение и обновите страницу</div>
      </div>`;
  }
}

function _showLiveBadge(lastUpdate, count, source) {
  const statsBar = document.querySelector('.stats');
  if (!statsBar) return;
  let badge = document.getElementById('liveBadge');
  if (!badge) {
    badge = document.createElement('div');
    badge.id = 'liveBadge';
    badge.style.cssText = 'text-align:center;padding:6px 0 0;font-size:11px;color:var(--text2);';
    statsBar.insertAdjacentElement('afterend', badge);
  }
  const label = source === 'live' ? 'Живые данные с hh.ru' : 'Данные';
  badge.innerHTML = `<span style="color:var(--accent)">●</span> ${label}: ${count} вакансий · обновлено ${lastUpdate || 'только что'}`;
}

// ===== AI CAREER AGENT =====
function _setStep(id, status, text) {
  const el = document.getElementById(id);
  const statusEl = document.getElementById(id + 'Status');
  if (!el || !statusEl) return;
  el.className = 'agent-step ' + (status === 'running' ? 'active' : status === 'ok' ? 'done' : '');
  statusEl.className = 'step-status ' + status;
  statusEl.textContent = text;
}

async function runCareerAgent() {
  const role = document.getElementById('agentRole').value;
  const skills = document.getElementById('agentSkills').value.trim();
  const goals = document.getElementById('agentGoals').value.trim();

  const btn = document.getElementById('agentRunBtn');
  const stepsEl = document.getElementById('agentSteps');
  const resultsEl = document.getElementById('agentResults');

  btn.disabled = true;
  btn.textContent = 'Агент работает…';
  stepsEl.style.display = 'flex';
  resultsEl.style.display = 'none';

  _setStep('stepPlan', 'running', 'определяет параметры…');
  _setStep('stepAct', '', 'ожидание');
  _setStep('stepVerify', '', 'ожидание');

  try {
    // Animate step transitions while waiting for server response
    const planTimer = setTimeout(() => {
      _setStep('stepPlan', 'ok', 'готово');
      _setStep('stepAct', 'running', 'ищет на hh.ru…');
    }, 1200);

    const actTimer = setTimeout(() => {
      _setStep('stepAct', 'ok', 'найдено');
      _setStep('stepVerify', 'running', 'анализирует…');
    }, 3500);

    const res = await fetch('/api/ai/agent-advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, skills, goals }),
    });

    clearTimeout(planTimer);
    clearTimeout(actTimer);

    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();

    // Update steps from real server data
    const steps = data.steps || [];
    const planStep = steps.find(s => s.step === 'plan');
    const actStep = steps.find(s => s.step === 'act');
    const verifyStep = steps.find(s => s.step === 'verify');

    if (planStep) {
      const q = planStep.params?.search_query || '';
      _setStep('stepPlan', 'ok', q ? `"${q.substring(0, 28)}…"` : 'готово');
    }
    if (actStep) {
      _setStep('stepAct', 'ok', `найдено: ${actStep.found}`);
    }
    if (verifyStep) {
      _setStep('stepVerify', 'ok', verifyStep.ok ? 'анализ готов' : 'ошибка');
    }

    // Render found vacancies
    const vacsEl = document.getElementById('agentVacancies');
    if (data.vacancies && data.vacancies.length) {
      vacsEl.innerHTML = data.vacancies.map(v => `
        <div class="agent-vac-card">
          <div class="agent-vac-title">${v.title}</div>
          <div class="agent-vac-company">${v.company} · ${v.location}</div>
          <div class="agent-vac-meta">
            <span class="agent-vac-tag">${v.format}</span>
            ${v.salary ? `<span class="agent-vac-tag">${v.salary}</span>` : ''}
            <span class="agent-vac-tag">${v.role}</span>
          </div>
          <a class="agent-vac-link" href="${v.url}" target="_blank" rel="noopener">Открыть на hh.ru →</a>
        </div>
      `).join('');
    } else {
      vacsEl.innerHTML = '<p style="color:var(--text2);font-size:13px">Вакансии не найдены — агент всё равно даст совет</p>';
    }

    // Render advice
    document.getElementById('agentAdviceText').textContent = data.advice || 'Нет ответа от агента';
    resultsEl.style.display = 'flex';

  } catch (e) {
    _setStep('stepVerify', '', 'ошибка');
    document.getElementById('agentAdviceText').textContent = 'Ошибка: ' + e.message;
    document.getElementById('agentResults').style.display = 'flex';
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> Запустить снова`;
  }
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
  _showCardsLoading();
  renderSources();
  initFilters();
  initSearch();
  initModals();
  initBurger();
  initHeaderScroll();
  initNavHighlight();
  initCardSave();
  checkAuthState();
  _loadTelegramWidget();
  loadLiveData();
});
