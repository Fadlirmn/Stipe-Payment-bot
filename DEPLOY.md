# 🚀 Deployment Guide — Stripe Verif Bot

> **Stack:** Bot (Docker/VPS) · Database (Firebase Firestore) · Dashboard (Vercel + Telegram Auth)
>
> Estimasi waktu setup: **45–60 menit**

---

## 📋 Checklist Persiapan

- [ ] VPS Linux (Ubuntu 22.04 disarankan) dengan akses SSH
- [ ] Docker & Docker Compose terinstall di VPS
- [ ] Akun Firebase (gratis tier cukup)
- [ ] Akun Vercel (gratis)
- [ ] Bot Telegram sudah dibuat via [@BotFather](https://t.me/BotFather)
- [ ] Google Spreadsheet sudah disiapkan dengan format kolom yang benar
- [ ] Apps Script sudah di-deploy sebagai Web App di spreadsheet tersebut

---

## BAGIAN 1 — Firebase Firestore

### 1.1 Buat Project Firebase

1. Buka [console.firebase.google.com](https://console.firebase.google.com)
2. Klik **Add project** → beri nama (contoh: `stripe-verif-bot`)
3. Matikan Google Analytics (opsional) → **Create project**

### 1.2 Aktifkan Firestore

1. Di sidebar kiri → **Build** → **Firestore Database**
2. Klik **Create database**
3. Pilih mode **Production** → pilih region (contoh: `asia-southeast1`)
4. Klik **Enable**

### 1.3 Set Security Rules

Klik tab **Rules** → replace dengan:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      // Dashboard baca langsung dari browser via Telegram Auth
      allow read: if true;
      // Hanya Service Account bot yang bisa write (via Admin SDK)
      allow write: if false;
    }
  }
}
```

> [!NOTE]
> `allow read: if true` aman karena akses dashboard sudah diproteksi oleh **Telegram Login Widget**
> + verifikasi hash server-side. Data yang tersimpan hanya nama, username Telegram, dan URL Stripe.

Klik **Publish**.

### 1.4 Download Service Account (untuk Bot)

1. ⚙️ Project Settings (gear icon) → tab **Service accounts**
2. Klik **Generate new private key** → **Generate key**
3. Simpan file JSON yang didownload sebagai **`firebase-credentials.json`**

> [!CAUTION]
> File ini SANGAT SENSITIF. Jangan pernah commit ke Git atau upload ke repo publik.

### 1.5 Catat Firebase Web Config (untuk Dashboard)

1. Project Settings → tab **General** → scroll ke **Your apps**
2. Klik icon **Web** (`</>`) → beri nama app (contoh: `dashboard`)
3. Salin objek `firebaseConfig` — akan dipakai sebagai **Vercel Environment Variables** di Bagian 3

```js
// Contoh — nilai Anda akan berbeda
const firebaseConfig = {
  apiKey:            "AIzaSy...",
  authDomain:        "stripe-verif-bot.firebaseapp.com",
  projectId:         "stripe-verif-bot",
  storageBucket:     "stripe-verif-bot.appspot.com",
  messagingSenderId: "123456789",
  appId:             "1:123456789:web:abc123",
};
```

---

## BAGIAN 2 — Google Apps Script

> [!NOTE]
> Pendekatan ini **tidak memerlukan** Service Account, credentials.json, atau Google Cloud Console.
> Cukup gunakan akun Google biasa yang memiliki spreadsheet.

### 2.1 Struktur Spreadsheet

Pastikan **Sheet1** memiliki kolom berikut (urutan penting):

| **A: Email** | **B: Password** | **C: API Key** | **D: Stripe URL** | **E: Timestamp** | **F: Status** |
|---|---|---|---|---|---|
| acc@email.com | ••••• | sk_live_xxx | https://buy.stripe.com/xxx | 2026-06-05 10:00 | _(kosong)_ |

> [!TIP]
> Kolom E (Timestamp) diisi otomatis saat extension/script append baris baru.
> Bot hanya mengambil URL yang Kolom F-nya **masih kosong** dan tanggalnya sesuai hari ini.

### 2.2 Pasang Apps Script ke Spreadsheet

1. Buka spreadsheet → **Extensions** → **Apps Script**
2. Hapus semua kode default, paste seluruh isi file **`appscript/Code.gs`** dari project ini
3. Script ini sudah berisi `doGet` (untuk bot) dan `doPost` (untuk service lain) sekaligus

> [!IMPORTANT]
> Script **tidak menggunakan secret/auth parameter** karena sudah di-deploy dan dipakai service lain.
> Jika ingin menambahkan proteksi, tambahkan kembali `SCRIPT_SECRET` di `doGet`.

### 2.3 Deploy sebagai Web App

Jika Apps Script belum pernah di-deploy:

1. Klik **Deploy** → **New deployment**
2. Klik ikon ⚙️ → pilih **Web app**
3. Atur:
   - **Execute as**: `Me`
   - **Who has access**: `Anyone`
4. Klik **Deploy** → **Authorize access** → izinkan
5. Salin **Web App URL** (format: `https://script.google.com/macros/s/AKfy.../exec`)

Jika Apps Script **sudah di-deploy** dan dipakai service lain:

1. Klik **Deploy** → **Manage deployments**
2. Klik ✏️ (edit) pada deployment yang ada
3. Pilih **New version** → **Deploy**

> [!TIP]
> URL Web App tidak berubah saat update versi — tidak perlu update `.env`.

### 2.4 Test Web App

Buka browser, akses:

```
https://script.google.com/macros/s/[ID_SCRIPT]/exec?date=2026-06-05
```

Response yang diharapkan:
```json
{
  "date": "2026-06-05",
  "count": 3,
  "data": [
    { "account": "acc@email.com", "payment_url": "https://buy.stripe.com/xxx", "notes": "" }
  ]
}
```

---

## BAGIAN 3 — Deploy Dashboard ke Vercel

> [!NOTE]
> Dashboard dilindungi oleh **Telegram Login Widget**. Hanya user yang terdaftar
> di Firestore dengan role `dev` atau `staff` yang bisa masuk.
> Firebase config & BOT_TOKEN tidak pernah hardcoded — semua via Vercel Environment Variables.

### 3.1 Set Environment Variables di Vercel

Buka [vercel.com](https://vercel.com) → Project → **Settings → Environment Variables**, tambahkan semua variabel berikut. Set ke **Production + Preview + Development**.

**Firebase (dari Bagian 1.5):**

| Variable | Sumber |
|---|---|
| `FIREBASE_API_KEY` | Firebase Console → Project Settings → Web app config |
| `FIREBASE_AUTH_DOMAIN` | Firebase Console → Project Settings → Web app config |
| `FIREBASE_PROJECT_ID` | Firebase Console → Project Settings → Web app config |
| `FIREBASE_STORAGE_BUCKET` | Firebase Console → Project Settings → Web app config |
| `FIREBASE_MESSAGING_SENDER_ID` | Firebase Console → Project Settings → Web app config |
| `FIREBASE_APP_ID` | Firebase Console → Project Settings → Web app config |

**Telegram Auth (untuk Login Widget + verifikasi hash):**

| Variable | Keterangan |
|---|---|
| `TELEGRAM_BOT_USERNAME` | Username bot **tanpa `@`** (contoh: `StripeVerifBot`) — dipakai widget di browser |
| `BOT_TOKEN` | Token bot dari BotFather — dipakai `api/verify.js` di server untuk verifikasi hash |

> [!CAUTION]
> `BOT_TOKEN` di Vercel **hanya dipakai server-side** oleh `api/verify.js`.
> Tidak pernah dikirim ke browser. Pastikan tidak di-log atau di-expose.

### 3.2 Aktifkan Telegram Login di BotFather

Agar Telegram Login Widget berfungsi, domain dashboard harus didaftarkan ke bot:

1. Buka [@BotFather](https://t.me/BotFather) → `/mybots` → pilih bot
2. **Bot Settings** → **Domain** → **Add domain**
3. Masukkan domain Vercel: `stipe-payment-bot.vercel.app`

> [!IMPORTANT]
> Langkah ini wajib dilakukan. Widget tidak akan berfungsi jika domain belum didaftarkan.

### 3.3 Deploy ke Vercel

**Opsi A — via Vercel CLI (direkomendasikan):**

```bash
# Install Vercel CLI (skip jika sudah)
npm install -g vercel

# Masuk ke folder dashboard
cd dashboard-vercel

# Deploy production
vercel --prod
```

Ikuti prompt:
- Set up and deploy? → **Y**
- Which scope? → pilih akun Anda
- Link to existing project? → **N** (buat baru)
- Project name → `stipe-payment-bot`
- Directory → `./` (enter)

Setelah selesai, Vercel akan memberi URL:
```
https://stipe-payment-bot.vercel.app/
```

**Opsi B — via GitHub:**

1. Push folder `dashboard-vercel/` ke repo GitHub
2. Buka [vercel.com](https://vercel.com) → **New Project** → Import dari GitHub
3. Set **Root Directory** ke `dashboard-vercel`
4. **Framework Preset**: Other
5. Deploy

> [!TIP]
> Dengan opsi GitHub, setiap push ke branch `main` akan auto-deploy ulang dashboard.

### 3.4 Verifikasi Dashboard

1. Buka URL dashboard → muncul halaman login dengan tombol **Telegram**
2. Klik login → authorize di Telegram → kembali ke dashboard
3. Jika role `dev`: semua menu tampil termasuk **User Management**
4. Jika role `staff`: menu User Management tersembunyi

---

## BAGIAN 4 — Deploy Bot ke VPS (Docker)

### 4.1 Persiapan VPS

SSH ke VPS dan install Docker:

```bash
# Update sistem
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verifikasi
docker --version
docker compose version
```

### 4.2 Upload Project ke VPS

```bash
# Buat folder di VPS
ssh user@VPS_IP "mkdir -p ~/stripe-verif-bot"

# Upload project (kecuali file sensitif)
rsync -avz --exclude='.git' \
  --exclude='.env' \
  --exclude='firebase-credentials.json' \
  --exclude='dashboard-vercel/' \
  --exclude='__pycache__/' \
  /home/sumbul/Dokumen/BOTS_STRIPE_VERIF/ \
  user@VPS_IP:~/stripe-verif-bot/

# Upload firebase credentials secara terpisah (aman via SCP)
scp firebase-credentials.json user@VPS_IP:~/stripe-verif-bot/
```

### 4.3 Buat File `.env` di VPS

```bash
ssh user@VPS_IP
cd ~/stripe-verif-bot
cp .env.example .env
nano .env
```

Isi dengan nilai asli:

```env
# Telegram Bot
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
DEV_IDS=987654321

# Google Apps Script (untuk ambil URL dari spreadsheet)
APPS_SCRIPT_URL=https://script.google.com/macros/s/.../exec

# Firebase (Bot — Service Account)
FIREBASE_CREDENTIALS_JSON=./firebase-credentials.json
FIREBASE_PROJECT_ID=stripe-verif-bot

# Timezone
TIMEZONE=Asia/Jakarta
```

> [!TIP]
> Untuk mendapat Telegram user ID Anda, kirim pesan ke [@userinfobot](https://t.me/userinfobot).

> [!NOTE]
> `APPS_SCRIPT_SECRET` **tidak diperlukan** — Apps Script sudah di-deploy tanpa auth parameter
> agar kompatibel dengan service lain yang memakai endpoint yang sama.

### 4.4 Jalankan Bot

```bash
# Build image
docker compose build

# Jalankan di background
docker compose up -d

# Cek status
docker compose ps

# Lihat log real-time
docker compose logs -f bot
```

Output log yang diharapkan:
```
INFO  | 🚀 Starting Stripe Verif Bot (Firebase)...
INFO  | [Firebase] Initialized project=stripe-verif-bot
INFO  | [Firebase] Firestore connection OK
INFO  | ✅ Firebase Firestore connected
INFO  | ✅ Scheduler started
INFO  | ✅ Bot polling started
```

---

## BAGIAN 5 — Setup Awal Bot

### 5.1 Daftarkan Diri sebagai Dev

1. Buka Telegram → cari bot Anda → kirim `/start`
2. Karena `user_id` Anda ada di `DEV_IDS`, bot langsung assign role **Dev**
3. Kirim `/menu` → pastikan muncul menu dengan tombol **Dev Tools**

### 5.2 Buat Task Pertama

```
/config_task
```

Ikuti wizard 7 langkah:
1. **Judul** → contoh: `Verifikasi URL Checkout`
2. **Deskripsi** → contoh: `Cek URL payment Stripe hari ini` (atau `-` untuk skip)
3. **Tab Google Sheet** → nama tab sheet (default: `Sheet1`)
4. **Kuota total** → contoh: `50` (atau `0` untuk unlimited)
5. **Kuota per staff** → contoh: `10`
6. **Deadline** → contoh: `23:59` (atau `-` untuk tidak ada)
7. **Repeat** → `daily`

### 5.3 Tambahkan Staff

Staff kirim `/start` ke bot → bot notif ke Dev → Dev approve:

```
/approve 123456789
```

Atau ubah role langsung:

```
/setrole 123456789 staff
```

### 5.4 Test Verifikasi

Isi spreadsheet dengan beberapa baris URL hari ini → kirim `/verif` di bot → pilih task → bot tampilkan URL satu per satu untuk diverifikasi.

---

## BAGIAN 6 — Fitur Dashboard

Dashboard Vercel memiliki 7 section:

| Section | Akses | Keterangan |
|---|---|---|
| 🏠 Overview | Dev & Staff | Statistik harian: total URL, OK, failed, pending, completion rate |
| 📋 Task Manager | Dev & Staff | Daftar task + progress bar per task |
| 👥 Staff Monitor | Dev & Staff | Leaderboard staff berdasarkan URL berhasil diverifikasi |
| 📊 Task per User | Dev & Staff | Pilih staff → lihat progress semua task yang dikerjakan |
| 🔗 URL Log | Dev & Staff | Log semua URL + status + siapa yang verifikasi + kapan |
| 📈 Analytics | Dev & Staff | Grafik tren 7 hari terakhir (OK vs Failed) |
| ⚙️ User Management | **Dev only** | Daftar semua user, filter by role, statistik jumlah per role |

### Auth Flow Dashboard

```
Klik Login → Telegram Widget → POST /api/verify (server) → cek hash BOT_TOKEN
     → client query Firestore → cek role user → masuk dashboard
```

- Session disimpan di `sessionStorage` (hilang saat browser ditutup)
- Role `pending` / tidak terdaftar → ditolak masuk

---

## BAGIAN 7 — Maintenance

### Update Bot

```bash
ssh user@VPS_IP
cd ~/stripe-verif-bot

# Upload file terbaru (ulangi rsync dari lokal)

# Rebuild & restart
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Update Dashboard

```bash
cd dashboard-vercel
vercel --prod
```

Atau jika pakai GitHub: cukup `git push` → Vercel auto-deploy.

### Monitoring Log

```bash
# Log real-time
docker compose logs -f bot

# 100 baris terakhir
docker compose logs --tail=100 bot
```

### Update Apps Script

1. Edit `appscript/Code.gs` di lokal
2. Paste ke Apps Script Editor di browser
3. **Deploy** → **Manage deployments** → edit → **New version** → **Deploy**

### Backup

Sistem dilengkapi dengan fitur pencadangan otomatis (backup) dari Firestore Cloud ke database SQLite lokal di VPS:
- **Lokasi Backup:** file database disimpan di host VPS pada direktori `./data/backup.db` (melalui volume mount `./data:/app/data` di Docker Compose).
- **Backup Otomatis:** Berjalan otomatis setiap 3 jam via scheduler.
- **Backup Manual:** Dev atau Admin dapat memicu pencadangan instan kapan saja dengan mengirimkan perintah `/backup` ke bot Telegram.
- **Backup Cloud (Opsional):** Firestore → ⋮ → **Export data** → simpan ke Google Cloud Storage.

---

## BAGIAN 8 — Troubleshooting

| Masalah | Kemungkinan Penyebab | Solusi |
|---|---|---|
| Bot tidak merespons | `BOT_TOKEN` salah / container crash | `docker compose logs bot` |
| Firebase connection failed | `firebase-credentials.json` tidak ada / salah path | Cek `.env` → `FIREBASE_CREDENTIALS_JSON` |
| URL hari ini tidak muncul | Kolom E (Timestamp) kosong / format salah | Pastikan kolom E terisi saat append |
| URL tidak muncul padahal ada | Kolom F sudah berisi status | Normal — bot skip URL yang sudah punya status |
| Dashboard: tombol login tidak muncul | Domain belum didaftarkan ke BotFather | BotFather → Bot Settings → Domain → Add |
| Dashboard: "Invalid authentication data" | `BOT_TOKEN` di Vercel env salah | Cek env var `BOT_TOKEN` di Vercel Dashboard |
| Dashboard: "Akun belum terdaftar" | User belum kirim `/start` ke bot | Minta user kirim `/start` ke bot terlebih dahulu |
| Dashboard: "Akses ditolak" | Role masih `pending` | Dev jalankan `/approve {user_id}` di bot |
| Dashboard kosong setelah login | Firebase config salah di Vercel env | Cek console browser (F12) → re-check env vars |
| `PENDING` semua URL | `/verif` belum dijalankan staff | Staff jalankan `/verif` |
| Firestore write denied | Security Rules memblokir | Cek rules — bot pakai Admin SDK (bypass rules) |

---

## BAGIAN 9 — Arsitektur Akhir

```
┌─────────────────┐      ┌──────────────────────────────────────┐
│  Staff / Admin  │      │         Google Spreadsheet            │
│  (Telegram App) │      │  Email | Pass | Key | URL | TS | Stat │
└────────┬────────┘      └─────────────────┬────────────────────┘
         │ Telegram API                     │ Apps Script (doGet)
         ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│               BOT SERVER — Docker @ VPS                         │
│  python-telegram-bot + firebase-admin SDK                       │
│  + httpx (Apps Script client + URL checker) + APScheduler       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Firestore Admin SDK (write)
                               ▼
                   ┌───────────────────────┐
                   │   FIREBASE FIRESTORE  │
                   │  users / tasks /      │
                   │  sheet_urls /         │
                   │  task_progress /      │
                   │  audit_logs           │
                   └──────────┬────────────┘
                              │ Firebase JS SDK (read, public)
                              ▼
                   ┌──────────────────────────────┐
                   │      DASHBOARD — Vercel       │
                   │  Static HTML + JS + Chart.js  │
                   │                               │
                   │  Auth: Telegram Login Widget  │
                   │    → /api/verify (serverless) │
                   │    → Firestore role check     │
                   │                               │
                   │  Fitur:                       │
                   │  · Overview & Analytics       │
                   │  · Task Manager               │
                   │  · Staff Monitor              │
                   │  · Task per User              │
                   │  · URL Log                    │
                   │  · User Management (dev only) │
                   └──────────────────────────────┘
```

---

*Dokumen ini dibuat untuk Stripe Verif Bot v1.1 · Update: 2026-06-05*
