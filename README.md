# 🤖 Stripe Verif Bot

**Stack:**
- 🤖 **Bot** — Python + Docker di VPS
- 🗄️ **Database** — Firebase Firestore
- 🌐 **Dashboard** — Static HTML di Vercel (baca Firestore langsung)

## 📁 Struktur Project

```
BOTS_STRIPE_VERIF/
├── main.py                     ← Entry point bot
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── .env.example
│
├── bot/
│   ├── config.py               ← Config dari .env
│   ├── firebase_db.py          ← Firestore helpers (ganti SQLAlchemy)
│   ├── scheduler.py            ← EOD summary job
│   ├── handlers/               ← start, task, verif, admin
│   ├── middlewares/auth.py     ← Role guard
│   ├── services/
│   │   ├── sheet_parser.py     ← Ambil URL dari Google Sheets by date
│   │   └── url_verifier.py     ← Async HTTP check
│   └── utils/
│       ├── keyboards.py
│       └── formatters.py
│
└── dashboard-vercel/           ← Deploy ke Vercel (terpisah)
    ├── index.html              ← Dashboard UI
    ├── vercel.json             ← Vercel config
    ├── css/dashboard.css
    └── js/dashboard.js         ← Baca Firestore via Firebase JS SDK
```

---

## 🚀 Setup Langkah-Langkah

### 1. Firebase Firestore

1. Buka [Firebase Console](https://console.firebase.google.com) → Buat project baru
2. Pilih **Firestore Database** → Create (mode: **Production**)
3. Atur **Security Rules** Firestore (tab Rules):

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Dashboard (baca publik dari Vercel — batasi sesuai kebutuhan)
    match /{document=**} {
      allow read: if true;  // Ganti dengan auth jika perlu
      allow write: if false; // Hanya bot (Service Account) yang bisa tulis
    }
  }
}
```

4. **Service Account untuk Bot:**
   - Project Settings → Service Accounts → Generate new private key
   - Simpan sebagai `firebase-credentials.json` (jangan di-commit!)

5. **Config untuk Dashboard (public):**
   - Project Settings → General → Your apps → Add app (Web)
   - Salin `firebaseConfig` → paste ke `dashboard-vercel/index.html`

---

### 2. Google Sheets Service Account

1. [Google Cloud Console](https://console.cloud.google.com) → Enable Sheets API & Drive API
2. Buat Service Account → Download JSON → simpan sebagai `credentials.json`
3. Share spreadsheet ke email service account (Viewer)

**Format Sheet:**

| Date | Account | Payment URL | Notes |
|---|---|---|---|
| 2026-06-05 | acc1@gmail.com | https://buy.stripe.com/xxx | ... |

---

### 3. Setup Bot di VPS

```bash
# Clone project ke VPS
git clone <repo> && cd BOTS_STRIPE_VERIF

# Salin credentials (JANGAN commit file ini)
cp .env.example .env
nano .env    # isi BOT_TOKEN, DEV_IDS, GOOGLE_SHEET_ID, FIREBASE_PROJECT_ID
# Upload firebase-credentials.json dan credentials.json ke folder ini

# Jalankan
docker-compose up -d
docker-compose logs -f bot   # monitor log
```

---

### 4. Deploy Dashboard ke Vercel

```bash
cd dashboard-vercel

# Install Vercel CLI (jika belum)
npm i -g vercel

# Edit index.html dulu — isi firebaseConfig dengan nilai dari Firebase Console

# Deploy
vercel --prod
```

Dashboard akan live di `https://stipe-payment-bot.vercel.app/` (atau domain custom Anda).

---

## 📋 Commands Bot

| Command | Role | Fungsi |
|---|---|---|
| `/start` | Semua | Registrasi & masuk |
| `/menu` | Semua | Menu utama |
| `/task` | Semua | Task aktif hari ini |
| `/verif` | Semua | Mulai verifikasi URL dari sheet |
| `/progress` | Semua | Progress saya hari ini |
| `/history` | Semua | Riwayat 7 hari |
| `/config_task` | Admin/Dev | Buat task baru (wizard) |
| `/approve <id>` | Admin/Dev | Approve user baru |
| `/setrole <id> <role>` | Dev | Ubah role user |
| `/users` | Dev | Daftar semua user |
| `/report` | Admin/Dev | Laporan tim hari ini |
| `/broadcast <msg>` | Dev | Pesan ke semua user |

## 🔐 Security

> ⚠️ File `.env`, `credentials.json`, `firebase-credentials.json` wajib di `.gitignore`.
> Jangan pernah hardcode credentials di source code.

Bot Telegram untuk verifikasi URL Payment Stripe dari Google Spreadsheet, dengan role-based access dan dashboard monitoring.

## 📁 Struktur Project

```
BOTS_STRIPE_VERIF/
├── main.py                          # Entry point bot
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example                     # Template env (salin ke .env)
├── .gitignore
│
├── bot/
│   ├── config.py                    # Config dari env vars
│   ├── database.py                  # SQLAlchemy models
│   ├── scheduler.py                 # APScheduler jobs
│   ├── handlers/
│   │   ├── start.py                 # /start /menu /me /help
│   │   ├── task.py                  # /task /progress /history
│   │   ├── verif.py                 # /verif + alur verifikasi sheet
│   │   └── admin.py                 # /config_task /approve /report ...
│   ├── middlewares/
│   │   └── auth.py                  # Role guard decorators
│   ├── services/
│   │   ├── sheet_parser.py          # Parse URL dari Google Sheets
│   │   └── url_verifier.py          # HTTP check URL Stripe
│   └── utils/
│       ├── keyboards.py             # Inline keyboard builders
│       └── formatters.py            # Text/progress bar helpers
│
├── dashboard/
│   ├── app.py                       # FastAPI dashboard API
│   └── static/
│       ├── index.html               # Dashboard UI
│       ├── css/dashboard.css
│       └── js/dashboard.js
│
└── data/                            # SQLite DB (auto-created)
```

## 🚀 Cara Setup

### 1. Persiapkan Google Spreadsheet

Format kolom yang wajib ada di sheet:

| Date | Account | Payment URL | Notes |
|---|---|---|---|
| 2026-06-05 | acc1@email.com | https://buy.stripe.com/xxx | ... |

- Nama kolom harus persis sama (case-sensitive)
- Kolom `Date` mendukung format: `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`

### 2. Buat Google Service Account

1. Buka [Google Cloud Console](https://console.cloud.google.com)
2. Buat project baru → Enable **Google Sheets API** & **Google Drive API**
3. Buat **Service Account** → Download JSON credentials
4. Share spreadsheet Anda ke email service account (role: Viewer)
5. Simpan file JSON sebagai `credentials.json` di root project

### 3. Konfigurasi `.env`

```bash
cp .env.example .env
nano .env   # isi semua variabel
```

> ⚠️ **JANGAN** commit file `.env` atau `credentials.json` ke Git!

### 4. Jalankan

**Dengan Docker:**
```bash
docker-compose up -d
```

**Tanpa Docker (dev):**
```bash
pip install -r requirements.txt
python main.py          # Bot
uvicorn dashboard.app:app --reload --port 8080  # Dashboard (terminal lain)
```

## 🗺️ Alur Kerja

```
Admin: /config_task → Buat task → Pilih Sheet Tab → Set deadline
                ↓
Bot: setiap hari sync URL dari Sheet berdasarkan tanggal hari ini
                ↓
Staff: /verif → Pilih task → Bot tampilkan URL per URL
             → Klik [Verifikasi] → Bot HTTP-check → Simpan hasil
             → Lanjut URL berikutnya → Sampai selesai
                ↓
Dashboard: monitor progress real-time di http://host:8080/dashboard
```

## 📋 Commands

| Command | Role | Fungsi |
|---|---|---|
| `/start` | Semua | Registrasi & masuk |
| `/menu` | Semua | Menu utama |
| `/task` | Semua | Task aktif hari ini |
| `/verif` | Semua | Mulai verifikasi URL dari sheet |
| `/progress` | Semua | Progress saya hari ini |
| `/history` | Semua | Riwayat 7 hari |
| `/me` | Semua | Info profil |
| `/config_task` | Admin/Dev | Buat task baru |
| `/approve <id>` | Admin/Dev | Approve user baru |
| `/setrole <id> <role>` | Dev | Ubah role user |
| `/users` | Dev | Daftar semua user |
| `/report` | Admin/Dev | Laporan tim hari ini |
| `/broadcast <msg>` | Dev | Pesan ke semua user |
| `/dashboard` | Admin/Dev | Link dashboard monitoring |

## 🔐 Security Notes

- Token bot hanya dari environment variable (`BOT_TOKEN`)
- `credentials.json` tidak di-commit (ada di `.gitignore`)
- Dashboard menggunakan one-time token per akses
- Audit log tersimpan untuk semua aksi penting
