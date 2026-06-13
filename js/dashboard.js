/* ── dashboard.js — Stripe Verif Bot Dashboard ── */
'use strict';

// ══════════════════════════════════════════════════════════
// AUTH — Firebase Auth
// ══════════════════════════════════════════════════════════
let currentUser   = null; // { id, first_name, username, role, email, ... }
let currentSection = 'overview';
let ringChart, lineChart;
let currentUrlFilter = '';

function decodeToken(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

function initAuth() {
  const token = localStorage.getItem('token');
  if (token) {
    const payload = decodeToken(token);
    if (payload && payload.exp * 1000 > Date.now()) {
      currentUser = {
        id:         payload.user_id,
        first_name: payload.full_name || 'User',
        last_name:  '',
        username:   payload.username || '',
        role:       payload.role,
        email:      payload.email
      };
      showDashboard();
    } else {
      localStorage.removeItem('token');
      currentUser = null;
      showLoginScreen();
    }
  } else {
    currentUser = null;
    showLoginScreen();
  }
}

function showLoginScreen() {
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
}

function toggleAuthMode(event, mode) {
  if (event) event.preventDefault();
  showLoginError('');
  if (mode === 'signup') {
    document.getElementById('signin-form').style.display = 'none';
    document.getElementById('signup-form').style.display = 'flex';
  } else {
    document.getElementById('signin-form').style.display = 'flex';
    document.getElementById('signup-form').style.display = 'none';
  }
}

async function handleSignIn(event) {
  event.preventDefault();
  const email = document.getElementById('signin-email').value.trim();
  const password = document.getElementById('signin-password').value;

  showLoginError('');
  showLoginLoading(true);

  try {
    const res = await fetch(`${API_URL}/api/auth/signin`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Gagal masuk.');
    }
    localStorage.setItem('token', data.token);
    currentUser = {
      id:         data.user.user_id,
      first_name: data.user.full_name || 'User',
      last_name:  '',
      username:   data.user.username || '',
      role:       data.user.role,
      email:      data.user.email
    };
    showLoginLoading(false);
    await showDashboard();
  } catch (err) {
    console.error('Sign in error:', err);
    showLoginError(`❌ ${err.message}`);
    showLoginLoading(false);
  }
}

async function handleSignUp(event) {
  event.preventDefault();
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const confirmPassword = document.getElementById('signup-confirm-password').value;

  showLoginError('');

  if (password.length < 6) {
    showLoginError('❌ Password minimal harus 6 karakter.');
    return;
  }

  if (password !== confirmPassword) {
    showLoginError('❌ Password dan Konfirmasi Password tidak cocok.');
    return;
  }

  showLoginLoading(true);

  try {
    const res = await fetch(`${API_URL}/api/auth/signup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Gagal mendaftar.');
    }

    document.getElementById('signup-form').reset();
    toggleAuthMode(null, 'signin');
    showLoginError('✅ Pendaftaran berhasil! Silakan masuk.');
    showLoginLoading(false);
  } catch (err) {
    console.error('Sign up error:', err);
    showLoginError(`❌ ${err.message}`);
    showLoginLoading(false);
  }
}

async function showDashboard() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'contents';

  const name = esc(currentUser.first_name);
  document.getElementById('sidebar-user').innerHTML =
    `<strong>${name}</strong><br><small style="color:var(--text-secondary)">` +
    `${currentUser.username ? '@' + esc(currentUser.username) + ' · ' : ''}` +
    `<span class="badge badge-${currentUser.role}">${currentUser.role}</span></small>`;

  if (currentUser.role === 'dev') {
    document.querySelectorAll('.nav-dev-only').forEach(el => el.style.display = 'flex');
  } else {
    document.querySelectorAll('.nav-dev-only').forEach(el => el.style.display = 'none');
  }

  if (['dev', 'admin'].includes(currentUser.role)) {
    document.querySelectorAll('.nav-admin-only').forEach(el => el.style.display = 'flex');
  } else {
    document.querySelectorAll('.nav-admin-only').forEach(el => el.style.display = 'none');
  }

  initDashboard();
}

function showLoginError(msg) {
  const el = document.getElementById('login-error');
  el.textContent = msg;
  el.style.display = msg ? 'block' : 'none';
}

function showLoginLoading(on) {
  const forms = ['signin-form', 'signup-form'];
  forms.forEach(fId => {
    const form = document.getElementById(fId);
    if (form) {
      const els = form.querySelectorAll('input, button');
      els.forEach(el => el.disabled = on);
    }
  });
}

document.getElementById('logoutBtn').addEventListener('click', () => {
  localStorage.removeItem('token');
  window.location.reload();
});

// ══════════════════════════════════════════════════════════
// DASHBOARD INIT
// ══════════════════════════════════════════════════════════
function initDashboard() {
  const datePicker = document.getElementById('datePicker');
  datePicker.value = todayStr();
  datePicker.addEventListener('change', () => loadSection(currentSection));

  updateClock();
  setInterval(updateClock, 1000);
  setInterval(() => loadSection(currentSection), 60_000);

  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
      el.classList.add('active');
      document.getElementById('pageTitle').textContent = el.textContent.trim();
      loadSection(el.dataset.section);
    });
  });

  document.getElementById('sidebarToggle').addEventListener('click', () =>
    document.getElementById('sidebar').classList.toggle('open')
  );
  document.getElementById('refreshBtn').addEventListener('click', () => loadSection(currentSection));
  document.getElementById('btn-filter-url').addEventListener('click', () => {
    currentUrlFilter = document.getElementById('filter-status').value;
    loadUrlLog(document.getElementById('datePicker').value);
  });
  document.getElementById('btn-load-taskuser').addEventListener('click', () => {
    const uid = document.getElementById('user-select').value;
    if (uid) loadTaskUser(uid);
  });

  // Role filter tabs (User Management)
  document.querySelectorAll('.role-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.role-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadUserMgmt(btn.dataset.role);
    });
  });

  loadSection('overview');
}

// ── Helpers ───────────────────────────────────────────────
function todayStr() {
  // Gunakan WIB (Asia/Jakarta) agar konsisten dengan backend & Google Sheets
  const now = new Date();
  const wib = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' }));
  const y = wib.getFullYear();
  const m = String(wib.getMonth() + 1).padStart(2, '0');
  const d = String(wib.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function updateClock() {
  document.getElementById('clock').textContent =
    new Date().toLocaleTimeString('id-ID', { timeZone: 'Asia/Jakarta', hour12: false });
}

function setStatus(ok) {
  const dot = document.getElementById('statusDot');
  dot.style.background = ok ? 'var(--success)' : 'var(--danger)';
  dot.style.boxShadow  = `0 0 6px ${ok ? 'var(--success)' : 'var(--danger)'}`;
}

function loadSection(sec) {
  if (currentUser.role === 'staff' && ['staff', 'analytics', 'usermgmt'].includes(sec)) {
    sec = 'overview';
  }
  if (currentUser.role === 'admin' && ['usermgmt'].includes(sec)) {
    sec = 'overview';
  }

  currentSection = sec;

  document.querySelectorAll('.nav-item').forEach(x => {
    if (x.dataset.section === sec) {
      x.classList.add('active');
      document.getElementById('pageTitle').textContent = x.textContent.trim();
    } else {
      x.classList.remove('active');
    }
  });

  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById(`section-${sec}`).classList.add('active');
  const d = document.getElementById('datePicker').value;
  if (sec === 'overview')  loadOverview(d);
  if (sec === 'tasks')     loadTasks(d);
  if (sec === 'staff')     loadStaff(d);
  if (sec === 'taskuser')  initTaskUserSection();
  if (sec === 'urllog')    loadUrlLog(d);
  if (sec === 'analytics') loadAnalytics();
  if (sec === 'taskmgmt' && currentUser?.role === 'dev') loadTaskMgmt();
  if (sec === 'usermgmt' && currentUser?.role === 'dev') loadUserMgmt('');
}

// ══════════════════════════════════════════════════════════
// FIRESTORE HELPERS
// ══════════════════════════════════════════════════════════
async function countDocs(collectionPath, conditions = []) {
  try {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_URL}/api/count`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ collectionPath, conditions })
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('token');
        window.location.reload();
      }
      throw new Error(data.detail || 'Gagal menghitung dokumen.');
    }
    setStatus(true);
    return data.count;
  } catch (err) {
    console.error('countDocs error:', err);
    setStatus(false);
    throw err;
  }
}

async function getDocs(collectionPath, conditions = [], orderByField = null,
                        orderDir = 'desc', limitN = null) {
  try {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_URL}/api/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ collectionPath, conditions, orderByField, orderDir, limitN })
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('token');
        window.location.reload();
      }
      throw new Error(data.detail || 'Gagal mengambil dokumen.');
    }
    setStatus(true);
    return data.results;
  } catch (err) {
    console.error('getDocs error:', err);
    setStatus(false);
    throw err;
  }
}

// ══════════════════════════════════════════════════════════
// OVERVIEW
// ══════════════════════════════════════════════════════════
async function loadOverview(d) {
  try {
    if (currentUser.role === 'staff') {
      const progs = await getDocs('task_progress', [['user_id', '==', parseInt(currentUser.id)], ['date', '==', d]]);
      let totalSubmitted = 0, totalOk = 0, totalFail = 0;
      for (const p of progs) {
        totalSubmitted += p.submitted || 0;
        totalOk += p.verified_ok || 0;
        totalFail += p.verified_fail || 0;
      }
      
      const pct = totalSubmitted > 0 ? Math.round(totalOk / totalSubmitted * 100 * 10) / 10 : 0;
      const tasks = await countDocs('tasks', [['status', '==', 'active']]);

      document.querySelector('.stat-card:nth-child(1) .stat-label').textContent = 'My Total Submitted';
      document.getElementById('val-total').textContent = totalSubmitted;

      document.querySelector('.stat-card:nth-child(2) .stat-label').textContent = 'My Verified OK';
      document.getElementById('val-ok').textContent = totalOk;

      document.querySelector('.stat-card:nth-child(3) .stat-label').textContent = 'My Failed';
      document.getElementById('val-fail').textContent = totalFail;

      document.getElementById('card-pending-wrap').style.display = 'none';
      document.getElementById('card-staff-wrap').style.display = 'none';

      document.getElementById('val-tasks').textContent = tasks;
      document.getElementById('ring-pct').textContent = pct;
      renderRing(pct);
      
      document.querySelector('.overview-progress-card .card-header').textContent = '📊 Completion Rate Saya Hari Ini';

    } else {
      document.querySelector('.stat-card:nth-child(1) .stat-label').textContent = 'Total URL';
      document.querySelector('.stat-card:nth-child(2) .stat-label').textContent = 'Verified OK';
      document.querySelector('.stat-card:nth-child(3) .stat-label').textContent = 'Failed';
      document.getElementById('card-pending-wrap').style.display = 'flex';
      document.getElementById('card-staff-wrap').style.display = 'flex';
      document.querySelector('.overview-progress-card .card-header').textContent = '📊 Completion Rate Hari Ini';

      const [staffList, urls] = await Promise.all([
        getDocs('users', [['role', '==', 'staff']]),
        getDocs('sheet_urls', [['date', '==', d]]),
      ]);
      const staffIds = new Set(staffList.map(s => String(s.user_id)));
      
      let total = 0, ok = 0, pending = 0, fail = 0;
      for (const u of urls) {
        const uid = String(u.assigned_to || '');
        if (!uid || !staffIds.has(uid)) continue;
        
        total++;
        if (u.status === 'OK') {
          ok++;
        } else if (u.status === 'PENDING') {
          pending++;
        } else {
          fail++;
        }
      }
      
      const pct   = total > 0 ? Math.round(ok / total * 100 * 10) / 10 : 0;
      const tasks  = await countDocs('tasks', [['status', '==', 'active']]);
      const staff  = staffList.length;

      document.getElementById('val-total').textContent   = total;
      document.getElementById('val-ok').textContent      = ok;
      document.getElementById('val-fail').textContent    = fail;
      document.getElementById('val-pending').textContent = pending;
      document.getElementById('val-tasks').textContent   = tasks;
      document.getElementById('val-staff').textContent   = staff;
      document.getElementById('ring-pct').textContent    = pct;
      renderRing(pct);
    }
    setStatus(true);
  } catch (e) {
    console.error('Overview error:', e);
    setStatus(false);
  }
}

function renderRing(pct) {
  const ctx = document.getElementById('ringChart').getContext('2d');
  if (ringChart) ringChart.destroy();
  ringChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [pct, 100 - pct],
        backgroundColor: ['#6366f1', 'rgba(255,255,255,0.06)'],
        borderWidth: 0,
      }]
    },
    options: {
      cutout: '78%',
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      animation: { duration: 800 },
    }
  });
}

// ══════════════════════════════════════════════════════════
// TASKS
// ══════════════════════════════════════════════════════════
async function loadTasks(d) {
  const tasks = await getDocs('tasks');
  const tbody = document.getElementById('task-tbody');
  if (!tasks.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="loading-row">📭 Tidak ada task</td></tr>';
    return;
  }
  const rows = await Promise.all(tasks.map(async t => {
    const total = await countDocs('sheet_urls', [['task_id','==',t.task_id],['date','==',d]]);
    const ok    = await countDocs('sheet_urls', [['task_id','==',t.task_id],['date','==',d],['status','==','OK']]);
    const pct   = total > 0 ? Math.round(ok / total * 100) : 0;
    return `<tr>
      <td><code>${esc(t.task_id)}</code></td>
      <td>${esc(t.title)}</td>
      <td>${esc(t.sheet_tab||'-')}</td>
      <td>
        <div class="prog-wrap">
          <div class="prog-bar-bg"><div class="prog-bar-fill" style="width:${pct}%"></div></div>
          <span class="prog-text">${ok}/${total||t.quota_total||0} (${pct}%)</span>
        </div>
      </td>
      <td>${t.deadline ? t.deadline.slice(11,16)+' WIB' : '—'}</td>
      <td>${esc(t.repeat_type||'')}</td>
      <td><span class="badge ${statusBadge(t.status)}">${t.status}</span></td>
    </tr>`;
  }));
  tbody.innerHTML = rows.join('');
}

// ══════════════════════════════════════════════════════════
// STAFF MONITOR
// ══════════════════════════════════════════════════════════
async function loadStaff(d) {
  // Tampilkan label tanggal di header
  const dateLabel = document.getElementById('staff-date-label');
  if (dateLabel) dateLabel.textContent = `— ${d}`;

  const [staffList, urls] = await Promise.all([
    getDocs('users', [['role','==','staff']]),
    getDocs('sheet_urls', [['date','==',d]]),
  ]);

  // Group URLs by assigned staff (assigned_to = immutable field, tidak ditimpa oleh verify_all)
  const byUser = {};
  for (const u of urls) {
    const uid = String(u.assigned_to || '');
    if (!uid) continue;
    if (!byUser[uid]) byUser[uid] = { total: 0, ok: 0, fail: 0 };
    byUser[uid].total++;
    if (u.status === 'OK') byUser[uid].ok++;
    else byUser[uid].fail++;
  }

  // Sort by OK count descending
  const sorted = staffList.sort((a, b) =>
    (byUser[String(b.user_id)]?.ok || 0) - (byUser[String(a.user_id)]?.ok || 0)
  );

  const tbody = document.getElementById('staff-tbody');
  if (!sorted.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="loading-row">📭 Tidak ada staff</td></tr>';
    return;
  }
  tbody.innerHTML = sorted.map((s, i) => {
    const stat = byUser[String(s.user_id)] || { total: 0, ok: 0, fail: 0 };
    const rate = stat.total > 0 ? Math.round(stat.ok / stat.total * 100) : 0;
    return `<tr>
      <td><strong>${i+1}</strong></td>
      <td>
        <div class="user-info">
          <div class="avatar">${(s.full_name||'?')[0].toUpperCase()}</div>
          <div class="user-info-text">
            <span class="user-info-name">${esc(s.full_name||'N/A')}</span>
          </div>
        </div>
      </td>
      <td>${s.username ? '@'+esc(s.username) : '-'}</td>
      <td>${stat.total}</td>
      <td style="color:var(--success)">${stat.ok}</td>
      <td style="color:var(--danger)">${stat.fail}</td>
      <td>
        <div class="prog-wrap">
          <div class="prog-bar-bg">
            <div class="prog-bar-fill" style="width:${rate}%;background:${rate>80?'var(--success)':rate>50?'var(--warning)':'var(--danger)'}"></div>
          </div>
          <span class="prog-text">${rate}% (${stat.ok}/${stat.total})</span>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════
// TASK PER USER
// ══════════════════════════════════════════════════════════
async function initTaskUserSection() {
  const select = document.getElementById('user-select');
  const selectorWrap = document.querySelector('.user-selector-wrap');

  if (currentUser.role === 'staff') {
    selectorWrap.style.display = 'none';
    loadTaskUser(currentUser.id);
    return;
  }

  selectorWrap.style.display = 'flex';
  if (select.options.length > 1) return; // sudah diisi

  const staffList = await getDocs('users', [['role','==','staff']]);
  staffList.forEach(u => {
    const opt = document.createElement('option');
    opt.value = u.user_id;
    opt.textContent = (u.full_name || 'N/A') + (u.username ? ' (@'+u.username+')' : '');
    select.appendChild(opt);
  });
}

async function loadTaskUser(userId) {
  if (currentUser.role === 'staff' && String(userId) !== String(currentUser.id)) {
    userId = currentUser.id;
  }
  const tbody = document.getElementById('taskuser-tbody');
  const summary = document.getElementById('task-user-summary');
  tbody.innerHTML = '<tr><td colspan="6" class="loading-row">⏳ Memuat data lifetime...</td></tr>';
  summary.style.display = 'none';

  try {
    const [tasks, urls] = await Promise.all([
      getDocs('tasks'),
      getDocs('sheet_urls', [['assigned_to','==', String(userId)]], null, 'desc', 5000),
    ]);

    // Group by task_id (semua tanggal, lifetime)
    const byTask = {};
    for (const u of urls) {
      const tid = u.task_id;
      if (!byTask[tid]) byTask[tid] = { total: 0, ok: 0, fail: 0 };
      byTask[tid].total++;
      if (u.status === 'OK') byTask[tid].ok++;
      else byTask[tid].fail++;
    }

    let grandTotal = 0, grandOk = 0, grandFail = 0;

    const rows = tasks.map(t => {
      const stat = byTask[t.task_id] || { total: 0, ok: 0, fail: 0 };
      const rate = stat.total > 0 ? Math.round(stat.ok / stat.total * 100) : 0;
      grandTotal += stat.total; grandOk += stat.ok; grandFail += stat.fail;

      const hasActivity = stat.total > 0;
      return `<tr style="opacity:${hasActivity ? 1 : 0.45}">
        <td>${esc(t.title)}</td>
        <td><code>${esc(t.sheet_tab||'-')}</code></td>
        <td>${stat.total}</td>
        <td style="color:var(--success)">${stat.ok}</td>
        <td style="color:var(--danger)">${stat.fail}</td>
        <td>
          <div class="prog-wrap">
            <div class="prog-bar-bg">
              <div class="prog-bar-fill" style="width:${rate}%;background:${rate>80?'var(--success)':rate>50?'var(--warning)':'var(--danger)'}"></div>
            </div>
            <span class="prog-text">${rate}% (${stat.ok}/${stat.total})</span>
          </div>
        </td>
      </tr>`;
    });

    tbody.innerHTML = rows.length
      ? rows.join('')
      : '<tr><td colspan="6" class="loading-row">📭 Tidak ada task</td></tr>';

    const grandRate = grandTotal > 0 ? Math.round(grandOk / grandTotal * 100) : 0;
    summary.style.display = 'flex';
    summary.innerHTML = `
      <span class="tus-chip">🔗 ${grandTotal} Submitted (Lifetime)</span>
      <span class="tus-chip ok">✅ ${grandOk} OK</span>
      <span class="tus-chip fail">❌ ${grandFail} Gagal</span>
      <span class="tus-chip ${grandRate > 80 ? 'ok' : grandRate > 50 ? '' : 'fail'}">📈 ${grandRate}% (${grandOk}/${grandTotal})</span>
    `;

  } catch (err) {
    console.error('TaskUser error:', err);
    tbody.innerHTML = '<tr><td colspan="6" class="loading-row">⚠️ Gagal memuat data</td></tr>';
  }
}

// ══════════════════════════════════════════════════════════
// URL LOG
// ══════════════════════════════════════════════════════════
const URL_PAGE_SIZE = 50;
let urlAllDocs = [];

async function loadUrlLog(d) {
  const conditions = [['date','==',d]];
  if (currentUrlFilter) conditions.push(['status','==',currentUrlFilter]);
  let docs = await getDocs('sheet_urls', conditions, 'created_at', 'desc', 500);
  if (currentUser.role === 'staff') {
    docs = docs.filter(r => String(r.verified_by) === String(currentUser.id));
  }
  urlAllDocs = docs;
  renderUrlPage(1);
}

function renderUrlPage(page) {
  const start = (page - 1) * URL_PAGE_SIZE;
  const slice = urlAllDocs.slice(start, start + URL_PAGE_SIZE);
  const tbody = document.getElementById('url-tbody');

  if (!slice.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="loading-row">📭 Tidak ada data</td></tr>';
    document.getElementById('url-pagination').innerHTML = '';
    return;
  }

  tbody.innerHTML = slice.map((r, i) => `
    <tr>
      <td>${start + i + 1}</td>
      <td><code>${esc(r.task_id||'-')}</code></td>
      <td>${esc(r.account||'-')}</td>
      <td class="url-cell"><a href="${esc(r.payment_url)}" target="_blank" rel="noopener">${esc(r.payment_url)}</a></td>
      <td><span class="badge ${urlStatusBadge(r.status)}">${r.status}</span></td>
      <td>${r.http_code||'—'}</td>
      <td>${r.verified_by ? '@'+esc(r.verified_by) : '—'}</td>
      <td>${r.verified_at ? r.verified_at.slice(0,16).replace('T',' ') : '—'}</td>
    </tr>
  `).join('');

  const totalPages = Math.ceil(urlAllDocs.length / URL_PAGE_SIZE);
  renderPagination('url-pagination', page, totalPages);
}

function renderPagination(containerId, current, total) {
  const el = document.getElementById(containerId);
  if (total <= 1) { el.innerHTML = ''; return; }
  const pages = [];
  for (let p = Math.max(1, current-2); p <= Math.min(total, current+2); p++) pages.push(p);
  el.innerHTML = pages.map(p =>
    `<button class="page-btn ${p===current?'active':''}" onclick="renderUrlPage(${p})">${p}</button>`
  ).join('');
}

// ══════════════════════════════════════════════════════════
// ANALYTICS — 7 hari terakhir
// ══════════════════════════════════════════════════════════
async function loadAnalytics() {
  const labels = [], okData = [], failData = [];
  const today = new Date();

  const staffList = await getDocs('users', [['role', '==', 'staff']]);
  const staffIds = new Set(staffList.map(s => String(s.user_id)));

  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    // Gunakan WIB agar konsisten dengan backend
    const wibD = new Date(d.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' }));
    const dateStr = wibD.getFullYear() + '-' +
      String(wibD.getMonth()+1).padStart(2,'0') + '-' +
      String(wibD.getDate()).padStart(2,'0');
    labels.push(dateStr.slice(5));

    const urls = await getDocs('sheet_urls', [['date','==',dateStr]]);
    let ok = 0, total = 0;
    for (const u of urls) {
      const uid = String(u.assigned_to || '');
      if (uid && staffIds.has(uid)) {
        total++;
        if (u.status === 'OK') ok++;
      }
    }
    okData.push(ok);
    failData.push(Math.max(0, total - ok));
  }

  const ctx = document.getElementById('lineChart').getContext('2d');
  if (lineChart) lineChart.destroy();
  lineChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '✅ OK',     data: okData,   backgroundColor: 'rgba(99,102,241,0.7)', borderRadius: 6 },
        { label: '❌ Failed', data: failData,  backgroundColor: 'rgba(239,68,68,0.5)',  borderRadius: 6 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,.05)' } },
        y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,.05)' }, beginAtZero: true },
      },
    },
  });
}

// ══════════════════════════════════════════════════════════
// USER MANAGEMENT (dev only)
// ══════════════════════════════════════════════════════════
async function loadUserMgmt(roleFilter) {
  const tbody = document.getElementById('usermgmt-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="loading-row">⏳ Memuat data...</td></tr>';

  try {
    const allUsers = await getDocs('users');

    // Hitung statistik
    document.getElementById('ustat-total').textContent    = allUsers.length;
    document.getElementById('ustat-dev').textContent     = allUsers.filter(u => u.role==='dev').length;
    document.getElementById('ustat-staff').textContent   = allUsers.filter(u => u.role==='staff').length;
    document.getElementById('ustat-pending').textContent = allUsers.filter(u => u.role==='pending').length;
    document.getElementById('ustat-inactive').textContent= allUsers.filter(u => !u.is_active).length;

    const filtered = roleFilter ? allUsers.filter(u => u.role === roleFilter) : allUsers;

    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="loading-row">📭 Tidak ada user</td></tr>';
      return;
    }

    tbody.innerHTML = filtered.map(u => {
      const initial = (u.full_name || u.username || '?')[0].toUpperCase();
      const joined  = u.joined_at ? u.joined_at.slice(0,10) : '—';
      const activeBadge = u.is_active
        ? '<span class="badge badge-ok">Aktif</span>'
        : '<span class="badge badge-fail">Nonaktif</span>';
      const roleBadge = {
        dev:     '<span class="badge badge-dev">Dev</span>',
        staff:   '<span class="badge badge-staff">Staff</span>',
        pending: '<span class="badge badge-pending">Pending</span>',
      }[u.role] || `<span class="badge badge-pending">${esc(u.role)}</span>`;

      return `<tr>
        <td>
          <div class="user-info">
            <div class="avatar">${initial}</div>
            <div class="user-info-text">
              <span class="user-info-name">${esc(u.full_name||'N/A')}</span>
              <span class="user-info-sub">@${esc(u.username||'N/A')}</span>
            </div>
          </div>
        </td>
        <td>${u.email ? esc(u.email) : '<span style="color:var(--text-secondary);font-style:italic">Belum diatur</span>'}</td>
        <td><code>${u.user_id}</code></td>
        <td>${roleBadge}</td>
        <td>${activeBadge}</td>
        <td>${joined}</td>
        <td>${u.approved_by ? '<code>'+esc(String(u.approved_by))+'</code>' : '—'}</td>
        <td>
          <button
            onclick="openEditModal('${u.user_id}', '${esc(u.full_name||u.username||'User')}', '${u.role}', ${!!u.is_active})"
            style="padding:5px 10px;background:#6366f1;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:.78rem;">
            ✏️ Edit
          </button>
        </td>
      </tr>`;
    }).join('');

  } catch (err) {
    console.error('UserMgmt error:', err);
    tbody.innerHTML = '<tr><td colspan="8" class="loading-row">⚠️ Gagal memuat data</td></tr>';
  }
}

// ══════════════════════════════════════════════════════════
// EDIT USER MODAL
// ══════════════════════════════════════════════════════════
let _editUserId = null;

function openEditModal(userId, name, role, isActive) {
  _editUserId = String(userId);
  document.getElementById('edit-user-name').textContent = name + ' • ID: ' + userId;
  document.getElementById('edit-role').value   = role;
  document.getElementById('edit-active').value = String(isActive);
  document.getElementById('edit-modal-msg').textContent = '';
  document.getElementById('edit-user-modal').style.display = 'flex';
}

function closeEditModal() {
  document.getElementById('edit-user-modal').style.display = 'none';
  _editUserId = null;
}

async function saveEditUser() {
  if (!_editUserId) return;
  const newRole  = document.getElementById('edit-role').value;
  const isActive = document.getElementById('edit-active').value === 'true';
  const msgEl    = document.getElementById('edit-modal-msg');
  msgEl.style.color = '#94a3b8';
  msgEl.textContent = '⏳ Menyimpan...';

  try {
    const users = await getDocs('users', [['user_id', '==', parseInt(_editUserId)]], null, 'desc', 1);
    if (users.length === 0) {
      msgEl.style.color = '#ef4444';
      msgEl.textContent = '❌ User tidak ditemukan.';
      return;
    }
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_URL}/api/update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        collectionPath: 'users',
        docId: _editUserId.toString(),
        updateData: { role: newRole, is_active: isActive }
      })
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || 'Gagal menyimpan.');
    }
    msgEl.style.color = '#22c55e';
    msgEl.textContent = '✅ Berhasil disimpan!';
    setTimeout(() => {
      closeEditModal();
      const activeTab = document.querySelector('.role-tab.active');
      loadUserMgmt(activeTab ? activeTab.dataset.role : '');
    }, 800);
  } catch (err) {
    console.error('saveEditUser error:', err);
    msgEl.style.color = '#ef4444';
    msgEl.textContent = '❌ Gagal: ' + err.message;
  }
}

document.getElementById('edit-user-modal').addEventListener('click', function(e) {
  if (e.target === this) closeEditModal();
});

// ══════════════════════════════════════════════════════════
// TASK MANAGEMENT (dev only)
// ══════════════════════════════════════════════════════════
let _editTaskId = null; // null = create mode, string = edit mode

async function loadTaskMgmt() {
  const tbody = document.getElementById('taskmgmt-tbody');
  tbody.innerHTML = '<tr><td colspan="8" class="loading-row">⏳ Memuat task...</td></tr>';
  try {
    const tasks = await getDocs('tasks');
    if (!tasks.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="loading-row">📫 Belum ada task. Klik "Buat Task Baru".</td></tr>';
      return;
    }
    tbody.innerHTML = tasks.map(t => {
      const deadline = t.deadline ? t.deadline.slice(0, 16).replace('T', ' ') + ' WIB' : '—';
      const repeatLabel = { none: '—', daily: '🔄 Daily', weekly: '🗓️ Weekly' }[t.repeat_type] || (t.repeat_type || '—');
      const pauseOrResume = t.status === 'paused'
        ? `<button class="btn-action resume" onclick="quickSetTaskStatus('${t.task_id}','active')">▶ Resume</button>`
        : t.status === 'active'
          ? `<button class="btn-action pause" onclick="quickSetTaskStatus('${t.task_id}','paused')">⏸ Pause</button>`
          : '';
      return `<tr>
        <td><code>${esc(t.task_id)}</code></td>
        <td><strong>${esc(t.title)}</strong>${t.description ? `<br><small style="color:var(--text-secondary)">${esc(t.description)}</small>` : ''}</td>
        <td>${esc(t.sheet_tab || '-')}</td>
        <td>${t.quota_total || '—'}</td>
        <td style="white-space:nowrap">${deadline}</td>
        <td>${repeatLabel}</td>
        <td><span class="badge ${statusBadge(t.status)}">${t.status}</span></td>
        <td>
          <div class="action-group">
            <button class="btn-action edit" onclick="openTaskModal('${t.task_id}')">✏️ Edit</button>
            ${pauseOrResume}
            ${t.status !== 'archived' ? `<button class="btn-action archive" onclick="quickSetTaskStatus('${t.task_id}','archived')">🗃 Arsip</button>` : ''}
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch (err) {
    console.error('TaskMgmt load error:', err);
    tbody.innerHTML = '<tr><td colspan="8" class="loading-row">⚠️ Gagal memuat task</td></tr>';
  }
}

async function openTaskModal(taskId = null) {
  _editTaskId = taskId;
  const titleEl    = document.getElementById('task-modal-title');
  const subtitleEl = document.getElementById('task-modal-subtitle');
  const msgEl      = document.getElementById('task-modal-msg');
  msgEl.textContent = '';

  if (taskId) {
    titleEl.textContent    = '✏️ Edit Task';
    subtitleEl.textContent = 'ID: ' + taskId;
    try {
      const tasks = await getDocs('tasks', [['task_id', '==', taskId]], null, 'desc', 1);
      const t = tasks[0] || {};
      document.getElementById('tm-title').value     = t.title || '';
      document.getElementById('tm-sheet-tab').value = t.sheet_tab || '';
      document.getElementById('tm-quota').value      = t.quota_total || '';
      document.getElementById('tm-deadline').value   = t.deadline ? t.deadline.slice(0, 16) : '';
      document.getElementById('tm-repeat').value     = t.repeat_type || 'none';
      document.getElementById('tm-status').value     = t.status || 'active';
      document.getElementById('tm-desc').value       = t.description || '';
    } catch (e) {
      console.error('openTaskModal fetch error:', e);
    }
  } else {
    titleEl.textContent    = '➕ Buat Task Baru';
    subtitleEl.textContent = 'Task baru akan langsung aktif setelah disimpan.';
    document.getElementById('tm-title').value     = '';
    document.getElementById('tm-sheet-tab').value = '';
    document.getElementById('tm-quota').value      = '';
    document.getElementById('tm-deadline').value   = '';
    document.getElementById('tm-repeat').value     = 'none';
    document.getElementById('tm-status').value     = 'active';
    document.getElementById('tm-desc').value       = '';
  }
  document.getElementById('task-modal').style.display = 'flex';
}

function closeTaskModal() {
  document.getElementById('task-modal').style.display = 'none';
  _editTaskId = null;
}

async function saveTask() {
  const msgEl = document.getElementById('task-modal-msg');
  const title = document.getElementById('tm-title').value.trim();
  if (!title) {
    msgEl.style.color = '#ef4444';
    msgEl.textContent = '❌ Judul task tidak boleh kosong.';
    return;
  }
  msgEl.style.color = '#94a3b8';
  msgEl.textContent = '⏳ Menyimpan...';

  const payload = {
    title,
    sheet_tab:   document.getElementById('tm-sheet-tab').value.trim(),
    quota_total: parseInt(document.getElementById('tm-quota').value) || 0,
    deadline:    document.getElementById('tm-deadline').value || null,
    repeat_type: document.getElementById('tm-repeat').value,
    status:      document.getElementById('tm-status').value,
    description: document.getElementById('tm-desc').value.trim() || null,
  };

  try {
    const token = localStorage.getItem('token');
    let res;
    if (_editTaskId) {
      // UPDATE existing task
      res = await fetch(`${API_URL}/api/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ collectionPath: 'tasks', docId: _editTaskId, updateData: payload })
      });
    } else {
      // CREATE new task
      res = await fetch(`${API_URL}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload)
      });
    }
    if (!res.ok) {
      const d = await res.json();
      throw new Error(d.detail || 'Gagal menyimpan task.');
    }
    msgEl.style.color = '#22c55e';
    msgEl.textContent = '✅ Berhasil disimpan!';
    setTimeout(() => { closeTaskModal(); loadTaskMgmt(); }, 800);
  } catch (err) {
    console.error('saveTask error:', err);
    msgEl.style.color = '#ef4444';
    msgEl.textContent = '❌ ' + err.message;
  }
}

async function quickSetTaskStatus(taskId, newStatus) {
  const token = localStorage.getItem('token');
  try {
    const res = await fetch(`${API_URL}/api/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ collectionPath: 'tasks', docId: taskId, updateData: { status: newStatus } })
    });
    if (!res.ok) throw new Error('Gagal update status.');
    loadTaskMgmt();
  } catch (err) {
    console.error('quickSetTaskStatus error:', err);
    alert('⚠️ Gagal mengubah status task: ' + err.message);
  }
}

document.getElementById('task-modal').addEventListener('click', function(e) {
  if (e.target === this) closeTaskModal();
});

// ── Helpers ─────────────────────────────────────────────────

function esc(str) {
  return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function statusBadge(s) {
  return { active:'badge-active', paused:'badge-warn', completed:'badge-ok', archived:'badge-pending' }[s]||'badge-pending';
}
function urlStatusBadge(s) {
  if (s==='OK') return 'badge-ok';
  if (s==='PENDING') return 'badge-pending';
  if (['HTTP_ERR','TIMEOUT'].includes(s)) return 'badge-warn';
  return 'badge-fail';
}

// ── Bootstrap ──────────────────────────────────────────────
initAuth();
