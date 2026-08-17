const state = {
  category: 'all',
  role: 'all',
  format: 'all',
  location: 'all',
  query: '',
  sort: 'date'
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function salaryValue(salary) {
  if (!salary) return -1;
  const digits = String(salary).replace(/[^\d]/g, '');
  return digits ? parseInt(digits, 10) : -1;
}

function filterVacancies() {
  return VACANCIES.filter(v => {
    if (state.category !== 'all' && v.category !== state.category) return false;
    if (state.role !== 'all' && v.role !== state.role) return false;
    if (state.format !== 'all' && v.format !== state.format) return false;
    if (state.location !== 'all' && v.location !== state.location) return false;
    if (state.query) {
      const q = state.query.toLowerCase();
      const haystack = [v.title, v.company, ...(v.tags || []), v.aiSummary].join(' ').toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  }).sort((a, b) => {
    if (state.sort === 'date') return (a.dateSort ?? 99) - (b.dateSort ?? 99);
    if (state.sort === 'company') return String(a.company || '').localeCompare(String(b.company || ''), 'ru');
    if (state.sort === 'salary') return salaryValue(b.salary) - salaryValue(a.salary);
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

  return `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener" class="source-badge ${cls}" title="Открыть источник">${icon}${escapeHtml(source.name)}</a>`;
}

function renderTag(tag) {
  let cls = 'tag';
  const t = String(tag).toLowerCase();
  if (t === 'стажировка') cls += ' type-internship';
  else if (t === 'junior') cls += ' type-junior';
  else if (t === 'remote') cls += ' format-remote';
  else if (t === 'hybrid') cls += ' format-hybrid';
  return `<span class="${cls}">${escapeHtml(tag)}</span>`;
}

function renderCard(v) {
  return `
    <article class="card" data-id="${escapeHtml(v.id)}">
      <div class="card-header">
        <div class="card-company">
          <div class="company-logo" style="background:${escapeHtml(v.logoColor)};color:${escapeHtml(v.logoText)}">${escapeHtml(v.logo)}</div>
          <div>
            <div class="company-name">${escapeHtml(v.company)}</div>
            <div class="company-location">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="opacity:.5;vertical-align:middle;margin-right:2px"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
              ${escapeHtml(v.location)}
            </div>
          </div>
        </div>
        <div class="card-meta">
          ${renderSourceBadge(v.source || {})}
          <div class="card-date">${escapeHtml(v.dateLabel)}</div>
        </div>
      </div>

      <h3 class="card-title">${escapeHtml(v.title)}</h3>

      <div class="ai-summary">
        <div class="ai-summary-header">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          ${v.aiEnriched ? 'ИИ-саммари' : 'Кратко из источника'}
        </div>
        <div class="ai-summary-text">${escapeHtml(v.aiSummary)}</div>
      </div>

      <div class="card-tags">
        ${(v.tags || []).map(renderTag).join('')}
      </div>

      <div class="card-footer">
        <div class="card-salary">${escapeHtml(v.salary || 'зарплата не указана')}</div>
        <a href="${escapeHtml(v.url)}" class="card-apply" target="_blank" rel="noopener">
          ${v.source && v.source.type === 'hh' ? 'На hh.ru' : 'Подробнее'}
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
        <div class="empty-title">${VACANCIES.length ? 'Ничего не найдено' : 'Живых вакансий пока нет'}</div>
        <div class="empty-sub">${VACANCIES.length ? 'Попробуй изменить фильтры' : 'Фейковые карточки не подставляем. Обновите страницу после парсинга hh.ru.'}</div>
      </div>`;
  } else {
    grid.innerHTML = filtered.map(renderCard).join('');
  }

  countEl.textContent = `Найдено: ${filtered.length} ${declVacancy(filtered.length)}`;
  document.getElementById('countAll').textContent = VACANCIES.length;
  document.getElementById('countVacancies').textContent = VACANCIES.filter(v => v.category === 'vacancy').length;
  document.getElementById('countInternships').textContent = VACANCIES.filter(v => v.category === 'internship').length;
}

function declVacancy(n) {
  if (n % 10 === 1 && n % 100 !== 11) return 'результат';
  if ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)) return 'результата';
  return 'результатов';
}

function renderNews() {
  const grid = document.getElementById('newsGrid');
  if (!NEWS.length) {
    grid.innerHTML = `
      <article class="news-card">
        <h3 class="news-title">Новостей из Telegram пока нет</h3>
        <p class="news-summary">Показываем только посты с t.me/s/kazanit, it_tatarstan, innopolis_live и school21_kazan. Статику не подмешиваем.</p>
      </article>`;
    return;
  }
  grid.innerHTML = NEWS.map(n => `
    <article class="news-card">
      <div class="news-card-header">
        <div class="news-icon">${escapeHtml(n.icon || '💬')}</div>
        <h3 class="news-title">${escapeHtml(n.title)}</h3>
      </div>
      <p class="news-summary">${escapeHtml(n.summary)}</p>
      <div class="news-footer">
        <div class="news-meta">
          <a class="news-source ${escapeHtml(n.sourceType || 'telegram')}" href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener">${escapeHtml(n.source)}</a>
          <span class="news-date">${escapeHtml(n.dateLabel)}</span>
        </div>
        <div class="news-tags">
          ${(n.tags || []).map(t => `<span class="news-tag">${escapeHtml(t)}</span>`).join('')}
        </div>
      </div>
    </article>
  `).join('');
}

function renderSources(list) {
  const grid = document.querySelector('.sources-grid');
  if (!grid) return;
  const items = list && list.length ? list : SOURCES;
  grid.innerHTML = items.map(s => `
    <div class="source-item">
      <div class="source-icon ${escapeHtml(s.type)}">${s.type === 'telegram' ? 'TG' : 'HH'}</div>
      <span>${escapeHtml(s.name)}</span>
    </div>
  `).join('');
}

function initFilters() {
  document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      const filter = btn.dataset.filter;
      const value = btn.dataset.value;
      document.querySelectorAll(`[data-filter="${filter}"]`).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state[filter] = value;
      renderVacancies();
    });
  });

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

  document.getElementById('sortSelect').addEventListener('change', e => {
    state.sort = e.target.value;
    renderVacancies();
  });
}

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

function openModal(id) {
  document.getElementById(id).classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  document.body.style.overflow = '';
}

function initModals() {
  document.getElementById('loginBtn').addEventListener('click', () => {
    if (!_currentUser) openModal('authModal');
  });
  document.getElementById('authClose').addEventListener('click', () => closeModal('authModal'));

  ['digestBtn', 'digestBannerBtn', 'aiDigestBtn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', () => openModal('digestModal'));
  });
  document.getElementById('digestClose').addEventListener('click', () => closeModal('digestModal'));

  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });

  document.querySelectorAll('#digestRoles .chip').forEach(chip => {
    chip.addEventListener('click', () => chip.classList.toggle('active'));
  });

  document.querySelectorAll('.schedule-option input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.schedule-option').forEach(opt => { opt.style.borderColor = ''; });
      if (radio.checked) radio.closest('.schedule-option').style.borderColor = 'var(--accent)';
    });
  });

  const saveBtn = document.getElementById('digestSaveBtn');
  const sendBtn = document.getElementById('digestSendBtn');
  if (saveBtn) saveBtn.addEventListener('click', saveDigestSettings);
  if (sendBtn) sendBtn.addEventListener('click', sendDigestNow);
}

function selectedDigestRoles() {
  return [...document.querySelectorAll('#digestRoles .chip.active')]
    .map(chip => chip.dataset.role)
    .filter(Boolean);
}

function setDigestStatus(text, isError) {
  const el = document.getElementById('digestStatus');
  if (!el) return;
  el.textContent = text;
  el.style.color = isError ? '#f87171' : 'var(--text2)';
}

async function saveDigestSettings() {
  if (!_currentUser) {
    closeModal('digestModal');
    openModal('authModal');
    return;
  }
  const schedule = (document.querySelector('input[name="schedule"]:checked') || {}).value || 'daily';
  const time = document.getElementById('digestTime').value;
  const roles = selectedDigestRoles();
  if (!roles.length) {
    setDigestStatus('Выберите хотя бы одно направление', true);
    return;
  }
  setDigestStatus('Сохраняем…');
  try {
    const res = await fetch('/api/digest/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schedule, time, roles }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      setDigestStatus(data.error || 'Не удалось сохранить', true);
      return;
    }
    setDigestStatus(data.message || 'Сохранено');
  } catch (err) {
    setDigestStatus('Сервер недоступен', true);
  }
}

async function sendDigestNow() {
  if (!_currentUser) {
    closeModal('digestModal');
    openModal('authModal');
    return;
  }
  setDigestStatus('Отправляем в Telegram…');
  try {
    const res = await fetch('/api/digest/send', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.success) {
      setDigestStatus(data.error || 'Не удалось отправить', true);
      return;
    }
    setDigestStatus(data.empty ? 'Отправлено: в кэше сейчас пусто, так и написали.' : (data.message || 'Отправлено'));
  } catch (err) {
    setDigestStatus('Сервер недоступен', true);
  }
}

function initBurger() {
  const burger = document.getElementById('burger');
  let mobileNav = document.getElementById('mobileNav');

  if (!mobileNav) {
    mobileNav = document.createElement('nav');
    mobileNav.className = 'nav-mobile';
    mobileNav.id = 'mobileNav';
    mobileNav.innerHTML = `
      <a href="#vacancies" class="nav-link" onclick="closeMobileNav()">Вакансии</a>
      <a href="#agent" class="nav-link" onclick="closeMobileNav()">Агент</a>
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

function initHeaderScroll() {
  const header = document.getElementById('header');
  window.addEventListener('scroll', () => {
    header.style.boxShadow = window.scrollY > 10 ? '0 1px 16px rgba(0,0,0,.5)' : '';
  }, { passive: true });
}

function initNavHighlight() {
  const sections = ['vacancies', 'news', 'agent'];
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

function animateCounter(el, target, duration = 1200) {
  if (!el) return;
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
  const vacancyCount = VACANCIES.filter(v => v.category === 'vacancy').length;
  const internshipCount = VACANCIES.filter(v => v.category === 'internship').length;
  const companyCount = new Set(VACANCIES.map(v => v.company)).size;
  const sourceCount = SOURCES.length;

  animateCounter(document.getElementById('statVacancies'), vacancyCount);
  animateCounter(document.getElementById('statInternships'), internshipCount);
  animateCounter(document.getElementById('statCompanies'), companyCount);
  animateCounter(document.getElementById('statSources'), sourceCount);
}

function initCardSave() {
  const grid = document.getElementById('cardsGrid');
  if (!grid) return;
  grid.addEventListener('click', e => {
    const saveBtn = e.target.closest('.card-save');
    if (!saveBtn) return;
    saveBtn.classList.toggle('saved');
  });
}

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
      ? `<img class="user-avatar" src="${escapeHtml(user.photo_url)}" alt="">`
      : `<div class="user-avatar-placeholder">${escapeHtml((user.first_name || '?')[0])}</div>`;
    userBadge.innerHTML = `
      ${avatar}
      <span class="user-name">${escapeHtml(user.first_name)}${user.last_name ? ' ' + escapeHtml(user.last_name) : ''}</span>
      <button class="user-logout" onclick="logout()" title="Выйти">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
      </button>`;
    userBadge.style.display = 'flex';
  } else {
    loginBtn.style.display = '';
    if (userBadge) userBadge.style.display = 'none';
  }
}

function _showCardsLoading() {
  const grid = document.getElementById('cardsGrid');
  const countEl = document.getElementById('resultsCount');
  if (grid) grid.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon" style="font-size:32px">⏳</div>
      <div class="empty-title">Загружаем вакансии…</div>
      <div class="empty-sub">Только hh.ru и публичные Telegram-каналы</div>
    </div>`;
  if (countEl) countEl.textContent = 'Загружаем…';
}

async function loadLiveData() {
  try {
    const [vacRes, newsRes, srcRes] = await Promise.all([
      fetch('/api/live-vacancies?limit=200'),
      fetch('/api/live-news?limit=20'),
      fetch('/api/sources'),
    ]);

    if (srcRes.ok) {
      const srcData = await srcRes.json();
      if (srcData.sources && srcData.sources.length) {
        renderSources(srcData.sources);
      }
    }

    if (vacRes.ok) {
      const vacData = await vacRes.json();
      VACANCIES = vacData.vacancies || [];
      renderVacancies();
      initCounters();
      _showLiveBadge(vacData.lastUpdate, VACANCIES.length, vacData.source, vacData.errors);
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
        <div class="empty-sub">Проверьте соединение и обновите страницу. Статику не подставляем.</div>
      </div>`;
  }
}

function _showLiveBadge(lastUpdate, count, source, errors) {
  const statsBar = document.querySelector('.stats');
  const hero = document.getElementById('heroTagText');
  if (hero) {
    hero.textContent = `${count} живых вакансий · ${SOURCES.length} источников · ${lastUpdate || 'ещё не обновлялось'}`;
  }
  if (!statsBar) return;
  let badge = document.getElementById('liveBadge');
  if (!badge) {
    badge = document.createElement('div');
    badge.id = 'liveBadge';
    badge.style.cssText = 'text-align:center;padding:6px 0 0;font-size:11px;color:var(--text2);';
    statsBar.insertAdjacentElement('afterend', badge);
  }
  const err = (errors && errors.length) ? ` · ошибки: ${errors.join('; ')}` : '';
  const label = source === 'live' ? 'Живые данные' : 'Кэш ещё пуст';
  badge.innerHTML = `<span style="color:var(--accent)">●</span> ${escapeHtml(label)}: ${count} вакансий · обновлено ${escapeHtml(lastUpdate || 'ещё не обновлялось')}${escapeHtml(err)}`;
}

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
    const res = await fetch('/api/ai/agent-advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, skills, goals }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.advice || ('HTTP ' + res.status));

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

    const vacsEl = document.getElementById('agentVacancies');
    if (data.vacancies && data.vacancies.length) {
      vacsEl.innerHTML = data.vacancies.map(v => `
        <div class="agent-vac-card">
          <div class="agent-vac-title">${escapeHtml(v.title)}</div>
          <div class="agent-vac-company">${escapeHtml(v.company)} · ${escapeHtml(v.location)}</div>
          <div class="agent-vac-meta">
            <span class="agent-vac-tag">${escapeHtml(v.format)}</span>
            ${v.salary ? `<span class="agent-vac-tag">${escapeHtml(v.salary)}</span>` : ''}
            <span class="agent-vac-tag">${escapeHtml(v.role)}</span>
          </div>
          <a class="agent-vac-link" href="${escapeHtml(v.url)}" target="_blank" rel="noopener">Открыть источник →</a>
        </div>
      `).join('');
    } else {
      vacsEl.innerHTML = '<p style="color:var(--text2);font-size:13px">hh.ru ничего не вернул — фейковые вакансии не подставляем</p>';
    }

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
  const agentBtn = document.getElementById('agentRunBtn');
  if (agentBtn) agentBtn.addEventListener('click', runCareerAgent);
  checkAuthState();
  _loadTelegramWidget();
  loadLiveData();
});
