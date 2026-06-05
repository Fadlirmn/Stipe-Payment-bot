# 📋 PRD — Stripe Verif URL Bot (Telegram)

> **Versi:** 1.0.0  
> **Tanggal:** 2026-06-05  
> **Status:** Draft  
> **Author:** Team Stripe-Binder  

---

## 1. Overview & Tujuan

### 1.1 Ringkasan Produk
Bot Telegram untuk manajemen dan verifikasi URL Stripe secara terpusat, dilengkapi sistem task harian yang dapat dikonfigurasi, kontrol akses berbasis role, dan dashboard monitoring real-time.

### 1.2 Masalah yang Diselesaikan
| Masalah | Solusi |
|---|---|
| Verifikasi URL Stripe dilakukan manual tanpa tracking | Task terstruktur dengan status & log otomatis |
| Tidak ada pembagian tugas antar tim | Role-based access: Dev / Admin / Staff |
| Tidak ada visibilitas progress harian | Dashboard monitoring terpusat |
| Konfigurasi task tidak fleksibel | Task harian dapat diatur lewat bot |

### 1.3 Target Pengguna
- **Dev** — Developer yang membangun & mengelola sistem
- **Admin** — Operator yang mengatur task dan memantau progress
- **Staff** — Eksekutor yang menjalankan verifikasi URL harian

---

## 2. Scope

### 2.1 In Scope (v1.0)
- [x] Sistem autentikasi & manajemen role
- [x] Task harian yang dapat dikonfigurasi
- [x] Verifikasi URL Stripe (format + reachability check)
- [x] Antarmuka command bot berbasis inline keyboard menu
- [x] Dashboard web monitoring task
- [x] Notifikasi otomatis (reminder, deadline, summary)
- [x] Log audit setiap aksi

### 2.2 Out of Scope (v1.0)
- [ ] Integrasi langsung ke Stripe API (payment processing)
- [ ] Mobile app terpisah
- [ ] Multi-bahasa UI

---

## 3. Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────┐
│                    TELEGRAM INTERFACE                        │
│           Inline Keyboard Menu + Command Handler             │
└───────────────────────────┬─────────────────────────────────┘
                            │ Webhook / Long Polling
┌───────────────────────────▼─────────────────────────────────┐
│                      BOT SERVER (Python)                     │
│  python-telegram-bot / aiogram                               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Auth Module  │  │ Task Engine  │  │  URL Verifier     │  │
│  │ (Role Guard) │  │ (Scheduler)  │  │  (HTTP + Regex)   │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└───────────┬───────────────────────────────────┬─────────────┘
            │                                   │
┌───────────▼──────────┐            ┌───────────▼─────────────┐
│    DATABASE          │            │    DASHBOARD SERVER      │
│    SQLite / Postgres │            │    FastAPI + React/HTML  │
│  - users             │◄──────────►│  - Real-time monitoring  │
│  - tasks             │            │  - Charts & stats        │
│  - task_logs         │            │  - Task management UI    │
│  - url_submissions   │            └─────────────────────────┘
│  - daily_configs     │
└──────────────────────┘
```

---

## 4. Role & Permission Matrix

| Fitur | Dev | Admin | Staff |
|---|:---:|:---:|:---:|
| `/start` — Masuk bot | ✅ | ✅ | ✅ |
| `/menu` — Lihat menu utama | ✅ | ✅ | ✅ |
| `/task` — Lihat task hari ini | ✅ | ✅ | ✅ |
| `/submit` — Submit URL verifikasi | ✅ | ✅ | ✅ |
| `/history` — Lihat riwayat task sendiri | ✅ | ✅ | ✅ |
| `/config_task` — Buat/edit task harian | ✅ | ✅ | ❌ |
| `/assign` — Assign task ke staff | ✅ | ✅ | ❌ |
| `/report` — Lihat laporan lengkap tim | ✅ | ✅ | ❌ |
| `/users` — Manajemen user & role | ✅ | ❌ | ❌ |
| `/broadcast` — Kirim pesan ke semua | ✅ | ❌ | ❌ |
| `/dashboard` — Akses link dashboard | ✅ | ✅ | ❌ |
| `/logs` — Lihat audit log | ✅ | ❌ | ❌ |
| `/set_reminder` — Atur jadwal reminder | ✅ | ✅ | ❌ |

---

## 5. Fitur Utama

### 5.1 🔐 Sistem Autentikasi & Role

**Flow Registrasi:**
```
User /start → Bot cek whitelist → 
  ├─ Baru → Tampilkan form pendaftaran → Admin approve → Role assigned
  └─ Existing → Tampilkan menu sesuai role
```

**Commands:**
```
/start          — Inisiasi & registrasi
/me             — Info profil & role saya
/users          — [Dev] Daftar semua user
/setrole @user [dev|admin|staff]  — [Dev] Ubah role user
/approve @user  — [Admin/Dev] Approve user baru
```

---

### 5.2 📋 Task Harian yang Dapat Dikonfigurasi

**Struktur Task:**
```json
{
  "task_id": "TASK-20260605-001",
  "title": "Verifikasi URL Checkout Stripe",
  "description": "Periksa 20 URL checkout, pastikan redirect benar",
  "url_target": "https://checkout.stripe.com/...",
  "quota_per_staff": 20,
  "total_quota": 100,
  "deadline": "2026-06-05T23:59:00+07:00",
  "assigned_to": ["all_staff"],
  "repeat": "daily",
  "status": "active"
}
```

**Commands Konfigurasi Task:**
```
/config_task new          — Buat task baru (form wizard)
/config_task edit [id]    — Edit task
/config_task delete [id]  — Hapus task
/config_task list         — Daftar semua template task
/config_task set_quota    — Atur kuota per staff
/config_task set_repeat   — Atur pengulangan (daily/weekly/custom)
/config_task set_deadline — Atur batas waktu
```

**Pengulangan Task (Repeat Options):**
| Opsi | Deskripsi |
|---|---|
| `daily` | Reset otomatis setiap hari jam 00:00 WIB |
| `weekly` | Reset setiap Senin |
| `custom` | Pilih hari spesifik (Mon, Tue, ...) |
| `once` | Task sekali jalan, tidak berulang |

---

### 5.3 🔗 Verifikasi URL Stripe

**Proses Verifikasi:**
```
Staff input URL → 
  1. Validasi format URL (regex)
  2. Cek domain whitelist (stripe.com, *.stripe.com)
  3. HTTP HEAD request → cek status code
  4. Screenshot opsional (via Playwright)
  5. Log hasil → Update progress task
  6. Notif ke staff (sukses/gagal)
```

**Status Verifikasi:**
| Status | Kode | Warna |
|---|---|---|
| Pending | `PENDING` | ⚪ |
| Valid & Reachable | `OK` | 🟢 |
| Invalid URL Format | `FORMAT_ERR` | 🔴 |
| Non-Stripe Domain | `DOMAIN_ERR` | 🔴 |
| HTTP Error (4xx/5xx) | `HTTP_ERR` | 🟡 |
| Timeout | `TIMEOUT` | 🟡 |

**Submit URL:**
```
/submit [URL]
/submit_bulk  — Upload file .txt berisi daftar URL
```

---

### 5.4 📱 Tampilan Menu Command (Inline Keyboard)

**Menu Utama (`/menu`):**
```
╔════════════════════════════════╗
║   🤖 STRIPE VERIF BOT v1.0    ║
║   Halo, [Nama] • [Role]       ║
╠════════════════════════════════╣
║  [📋 Task Hari Ini]  [📤 Submit URL]  ║
║  [📊 Progress Saya]  [📖 History]     ║
╠══════════════════ [Admin/Dev] ═╣
║  [⚙️ Config Task]  [👥 Kelola User]  ║
║  [📈 Report]       [🔔 Reminder]     ║
╠════════════════════════════════╣
║  [🌐 Dashboard]    [ℹ️ Info]          ║
╚════════════════════════════════╝
```

**Task Hari Ini (`/task`):**
```
╔══════════════════════════════════╗
║  📋 TASK HARI INI                ║
║  Kamis, 05 Juni 2026             ║
╠══════════════════════════════════╣
║  📌 [TASK-001] Verifikasi Checkout║
║  ├ Target  : 20 URL              ║
║  ├ Progress: ████░░ 12/20 (60%)  ║
║  ├ Deadline: 23:59 WIB           ║
║  └ Status  : 🟡 On Progress      ║
╠══════════════════════════════════╣
║  [✅ Submit URL]  [📊 Detail]    ║
║  [🔙 Menu Utama]                 ║
╚══════════════════════════════════╝
```

**Submit URL:**
```
╔══════════════════════════════════╗
║  📤 SUBMIT VERIFIKASI URL        ║
╠══════════════════════════════════╣
║  Pilih task:                     ║
║  [📌 TASK-001 Checkout]          ║
║  [📌 TASK-002 Payment Link]      ║
╠══════════════════════════════════╣
║  [🔙 Kembali]                    ║
╚══════════════════════════════════╝
```

**Setelah pilih task:**
```
Silakan kirim URL yang ingin diverifikasi.
Format: https://checkout.stripe.com/...

Atau kirim file .txt untuk bulk submit.
```

---

### 5.5 🔔 Sistem Notifikasi & Reminder

| Trigger | Penerima | Pesan |
|---|---|---|
| Task baru dibuat | Semua staff | "📋 Task baru tersedia!" |
| Progress 50% | Admin | "⚠️ Progress 50% di task [X]" |
| 2 jam sebelum deadline | Staff yang belum selesai | "⏰ Deadline 2 jam lagi!" |
| Task selesai | Admin + Dev | "✅ Task [X] selesai 100%" |
| URL submit gagal | Staff submitter | "❌ URL invalid: [alasan]" |
| End of day summary | Admin | Laporan harian otomatis |

---

### 5.6 📈 Dashboard Web Monitoring

**URL Akses:** `http://[host]:8080/dashboard`  
**Auth:** Token dari bot (`/dashboard` command → kirim link one-time)

**Halaman Dashboard:**

#### 🏠 Overview
```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  Total   │ │Completed │ │  Active  │ │  Failed  │
│ Task: 5  │ │   3/5    │ │   1/5    │ │   1/5    │
└──────────┘ └──────────┘ └──────────┘ └──────────┘

📊 Progress Chart (Bar / Donut)
📅 Timeline Task Hari Ini
👥 Leaderboard Staff (teratas berdasarkan completion rate)
```

#### 📋 Task Manager
- Tabel semua task (filter: status, tanggal, assignee)
- Action: Edit, Pause, Delete, Duplicate
- Progress bar per task
- Export CSV/Excel

#### 👥 Staff Monitor
- Daftar staff + status online/offline
- Progress masing-masing staff hari ini
- History submission per staff

#### 🔗 URL Log
- Tabel semua URL yang disubmit
- Filter: status, task, staff, tanggal
- Re-check URL secara manual
- Export log

#### 📊 Analytics
- Grafik tren harian/mingguan
- Completion rate per staff
- Jam produktif (heatmap)
- Error rate per kategori

---

## 6. Data Model

### 6.1 Tabel `users`
```sql
CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY,  -- Telegram user ID
    username      TEXT,
    full_name     TEXT,
    role          TEXT DEFAULT 'pending', -- dev | admin | staff | pending
    is_active     BOOLEAN DEFAULT TRUE,
    joined_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_by   INTEGER                -- FK user_id approver
);
```

### 6.2 Tabel `tasks`
```sql
CREATE TABLE tasks (
    task_id       TEXT PRIMARY KEY,     -- TASK-YYYYMMDD-XXX
    title         TEXT NOT NULL,
    description   TEXT,
    url_target    TEXT,
    quota_total   INTEGER DEFAULT 0,
    quota_per_staff INTEGER DEFAULT 0,
    deadline      DATETIME,
    repeat_type   TEXT DEFAULT 'daily', -- daily | weekly | custom | once
    repeat_days   TEXT,                 -- JSON: ["Mon","Wed"]
    assigned_to   TEXT DEFAULT 'all',   -- JSON: ["all"] or [user_id, ...]
    status        TEXT DEFAULT 'active',-- active | paused | completed | archived
    created_by    INTEGER,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 6.3 Tabel `task_progress`
```sql
CREATE TABLE task_progress (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT,
    user_id       INTEGER,
    date          DATE,                 -- Tanggal progress (untuk daily reset)
    submitted     INTEGER DEFAULT 0,
    verified_ok   INTEGER DEFAULT 0,
    verified_fail INTEGER DEFAULT 0,
    completed_at  DATETIME,
    UNIQUE(task_id, user_id, date)
);
```

### 6.4 Tabel `url_submissions`
```sql
CREATE TABLE url_submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT,
    user_id       INTEGER,
    url           TEXT NOT NULL,
    status        TEXT,               -- OK | FORMAT_ERR | DOMAIN_ERR | HTTP_ERR | TIMEOUT
    http_code     INTEGER,
    error_msg     TEXT,
    submitted_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    verified_at   DATETIME
);
```

### 6.5 Tabel `audit_logs`
```sql
CREATE TABLE audit_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id      INTEGER,
    action        TEXT,               -- task.create | task.edit | user.approve | url.submit ...
    target_type   TEXT,
    target_id     TEXT,
    detail        TEXT,               -- JSON metadata
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. Command Reference Lengkap

### 👤 Universal (semua role)
```
/start          — Daftarkan akun / masuk
/menu           — Tampilkan menu utama interaktif
/task           — Lihat task aktif hari ini
/submit [url]   — Submit URL untuk verifikasi
/submit_bulk    — Bulk submit via file .txt
/progress       — Lihat progress saya hari ini
/history [n]    — Riwayat n hari terakhir (default: 7)
/me             — Profil & statistik saya
/help           — Bantuan & panduan
```

### 🛡️ Admin & Dev
```
/config_task    — Buka wizard konfigurasi task
/assign [task_id] [@user|all] — Assign task
/report [daily|weekly|monthly] — Laporan tim
/report_export  — Export laporan ke CSV
/set_reminder [time] [pesan]  — Atur pengingat otomatis
/dashboard      — Dapatkan link akses dashboard
/broadcast [pesan]  — Kirim pesan ke semua
```

### 🔧 Dev Only
```
/users          — Daftar & kelola semua user
/setrole @user [dev|admin|staff] — Ubah role
/approve @user  — Approve pendaftaran manual
/revoke @user   — Nonaktifkan user
/logs [n]       — Lihat n baris audit log terakhir
/flush_cache    — Bersihkan cache bot
/status         — Status sistem bot
```

---

## 8. Tech Stack

| Komponen | Teknologi | Alasan |
|---|---|---|
| Bot Framework | `python-telegram-bot v20` atau `aiogram v3` | Async, modern, inline keyboard support |
| Language | Python 3.11+ | Ekosistem kaya, familiar |
| Database | SQLite (dev) / PostgreSQL (prod) | Portabel → Scalable |
| Scheduler | `APScheduler` | Task harian & reminder |
| URL Checker | `httpx` (async HTTP) | Fast, non-blocking |
| Dashboard Backend | `FastAPI` | Lightweight REST API |
| Dashboard Frontend | HTML + Vanilla JS + Chart.js | Ringan, tidak perlu build step |
| Auth Dashboard | JWT one-time token | Secure, stateless |
| Deployment | Docker + docker-compose | Konsisten dengan stack sebelumnya |
| Logging | `loguru` | Structured logging |

---

## 9. Deployment & Infrastruktur

### 9.1 Docker Compose
```yaml
# docker-compose.yml (TEMPLATE — isi .env terpisah)
version: '3.8'
services:
  bot:
    build: ./bot
    env_file: .env          # BOT_TOKEN, ADMIN_IDS, dll — JANGAN hardcode
    depends_on: [db]
    restart: unless-stopped

  dashboard:
    build: ./dashboard
    ports:
      - "8080:8080"
    env_file: .env
    depends_on: [db]
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### 9.2 Environment Variables (`.env` — JANGAN commit ke Git)
```
# Contoh .env — Isi dengan nilai asli Anda, simpan aman!
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
ADMIN_IDS=YOUR_TELEGRAM_USER_ID_HERE
DASHBOARD_SECRET=YOUR_RANDOM_JWT_SECRET_HERE
DB_NAME=stripebot
DB_USER=botuser
DB_PASSWORD=YOUR_DB_PASSWORD_HERE
WEBHOOK_URL=https://yourdomain.com/webhook
```

> [!CAUTION]
> File `.env` wajib masuk ke `.gitignore`. **Jangan pernah** menyimpan token/password langsung di source code.

---

## 10. Roadmap

### v1.0 (MVP — Target: 2 minggu)
- [x] PRD selesai
- [ ] Setup project & DB schema
- [ ] Auth & role system
- [ ] Task CRUD + scheduler harian
- [ ] URL verifier (format + HTTP check)
- [ ] Inline menu bot
- [ ] Dashboard monitoring basic
- [ ] Docker deployment

### v1.1 (Bulan 2)
- [ ] Screenshot URL via Playwright
- [ ] Bulk submit .txt
- [ ] Export report CSV
- [ ] Grafik analytics dashboard
- [ ] Notifikasi webhook ke Slack/Discord

### v2.0 (Bulan 3+)
- [ ] Multi-project support
- [ ] AI-powered URL anomaly detection
- [ ] Stripe API integration (live status check)
- [ ] Mobile-first dashboard PWA

---

## 11. Acceptance Criteria

| ID | Kriteria | Prioritas |
|---|---|---|
| AC-01 | Staff dapat melihat task hari ini via `/task` | Must Have |
| AC-02 | Staff dapat submit URL dan mendapat feedback instan | Must Have |
| AC-03 | Admin dapat buat & edit task via inline menu | Must Have |
| AC-04 | Task reset otomatis setiap hari jam 00:00 WIB | Must Have |
| AC-05 | Dev dapat ubah role user | Must Have |
| AC-06 | Dashboard menampilkan progress real-time | Must Have |
| AC-07 | Reminder otomatis terkirim sebelum deadline | Should Have |
| AC-08 | Export laporan ke CSV | Should Have |
| AC-09 | Bulk submit URL via file .txt | Should Have |
| AC-10 | Screenshot URL otomatis | Nice to Have |

---

*PRD ini adalah dokumen hidup. Perubahan akan dicatat di changelog.*
