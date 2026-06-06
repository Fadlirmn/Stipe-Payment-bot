# 📋 Panduan Staff — Bot Verifikasi Stripe

> Panduan ini khusus untuk **Staff** — orang yang bertugas mengerjakan verifikasi URL setiap harinya. Tidak perlu jago IT, ikuti langkah-langkahnya saja!

---

## 🔑 Apa yang Bisa Dilakukan Staff?

Sebagai Staff, kamu bisa:
- ✅ **Melihat task** yang harus dikerjakan hari ini
- ✅ **Mengambil & mengerjakan URL** untuk diverifikasi
- ✅ **Melaporkan hasil** verifikasi (berhasil / gagal)
- ✅ **Melihat progres** kerjaan kamu sendiri hari ini

Yang **tidak bisa** dilakukan Staff (hanya Admin/Dev yang bisa):
- ❌ Membuat atau mengubah task
- ❌ Menyetujui pendaftaran anggota lain
- ❌ Melihat laporan seluruh tim
- ❌ Mengakses Web Dashboard

---

## 🚀 Cara Pertama Kali Gabung

1. Buka Telegram, cari bot ini (nama bot sesuai yang dikasih Admin/Developer)
2. Ketik `/start` dan kirim
3. Bot akan mendeteksi kamu sebagai anggota baru dan mengirim permintaan ke Admin
4. **Tunggu persetujuan Admin** — kamu akan dapat notifikasi otomatis kalau sudah diterima

```
✅ Pendaftaranmu telah disetujui!
Selamat datang, [Nama Kamu].
Ketik /menu untuk mulai bekerja.
```

> [!NOTE]
> Kalau belum ada balasan dari bot setelah beberapa saat, minta Admin untuk mengecek permintaan pendaftaranmu.

---

## 🧩 Bagian 0 — Cara Pasang Extension Stripe Autofill

Extension ini digunakan untuk **mengisi data kartu VCC secara otomatis** di halaman Stripe Checkout — kamu tidak perlu mengetik manual satu per satu.

> [!IMPORTANT]
> Extension ini **tidak tersedia di Chrome Web Store**. Kamu perlu memasangnya secara manual menggunakan file yang dikirim Admin.

### Yang Kamu Butuhkan:
- File folder extension (namanya `stripe-autofill-extension`) — minta dari Admin
- Browser **Google Chrome** (atau browser berbasis Chromium seperti Edge, Brave, dll)

---

### Langkah-langkah Pemasangan:

**Langkah 1 — Buka halaman Extensions di Chrome**

Di address bar Chrome, ketik:
```
chrome://extensions
```
lalu tekan Enter.

---

**Langkah 2 — Aktifkan Developer Mode**

Di pojok kanan atas halaman, nyalakan toggle **"Developer mode"**.

```
┌─────────────────────────────────────┐
│ Extensions            Developer mode ● │
└─────────────────────────────────────┘
```

---

**Langkah 3 — Load folder extension**

1. Klik tombol **"Load unpacked"** yang muncul di kiri atas
2. Cari dan pilih **folder `stripe-autofill-extension`** yang sudah kamu terima dari Admin
3. Klik **Select Folder**

Extension akan langsung muncul di daftar dengan nama **"Stripe Card Autofill"**.

---

**Langkah 4 — Pin extension ke toolbar (opsional tapi disarankan)**

1. Klik ikon puzzle 🧩 di toolbar Chrome (pojok kanan atas)
2. Cari **Stripe Card Autofill**
3. Klik ikon 📌 pin agar ikonnya selalu muncul di toolbar

---

### Cara Memasukkan Data VCC ke Extension:

Setelah extension terpasang, kamu perlu mengisi data kartu VCC yang diberikan Admin. Cara termudah adalah dengan **import file `vcc.txt`**.

**Format isi file `vcc.txt`:**
```
nomorKartu|bulanTahunExp|cvc|namaPemegang|negaraKode|alamat|alamat2|kota|provinsi|kodePos
```

Contoh:
```
4519912173897820|02/27|304|John Doe|US|123 Maple St||New York|NY|10001
```

> [!NOTE]
> - Gunakan `|` (pipe) sebagai pemisah antar kolom
> - Kalau `alamat2` kosong, cukup biarkan kosong (tetap ada dua `||` berturutan)
> - Baris yang diawali `#` dianggap komentar dan diabaikan

**Cara import file:**
1. Klik ikon extension **Stripe Card Autofill** di toolbar
2. Di popup yang muncul, cari tombol **Import File / Import TXT**
3. Pilih file `vcc.txt` yang sudah kamu siapkan
4. Data kartu akan langsung masuk ke extension

---

### Cara Pakai Extension saat Verifikasi:

1. Buka URL Stripe Checkout yang diberikan bot
2. Klik ikon **Stripe Card Autofill** di toolbar
3. Pilih data kartu yang mau dipakai (kalau ada lebih dari satu)
4. Klik tombol **Autofill** / **Isi Otomatis**
5. Kolom-kolom di halaman Stripe akan terisi otomatis
6. **Kamu yang menekan tombol Save/Submit** — extension tidak melakukan itu sendiri

> [!TIP]
> Extension hanya bekerja di halaman `checkout.stripe.com`. Kalau URL bukan halaman checkout Stripe, tombol autofill tidak akan berfungsi.

---

## 👋 Cara Mulai Bekerja Setiap Hari

Setelah akun kamu aktif, setiap hari cukup:

1. Buka Telegram dan buka chat dengan bot
2. Ketik `/menu` atau `/verif` lalu kirim
3. Bot akan tampilkan task hari ini

Tampilan menu seperti ini:
```
🤖 STRIPE VERIF BOT
Halo, [Nama Kamu] • Staff

[📋 Task Hari Ini]    [📊 Progres Saya]
[ℹ️ Info]
```

---

## 📋 Bagian 1 — Melihat Task Hari Ini

### Cara Melihat Task:

Ketik `/task` atau klik tombol **📋 Task Hari Ini** di menu.

Bot akan tampilkan task aktif seperti ini:
```
📋 TASK HARI INI — 2026-06-06
━━━━━━━━━━━━━━━━━━━━
📌 Judul   : Verifikasi URL Hari Ini
📝 Catatan : Pastikan semua URL bisa dibuka dengan normal
⏰ Deadline: 23:59 WIB
🔗 Jatah   : 20 URL per orang

[ 🚀 Mulai Ambil URL ]
```

> [!IMPORTANT]
> Perhatikan **deadline** dan **jatah URL per orang**. Kamu hanya bisa mengambil URL sesuai batas yang ditentukan Admin.

---

## 🔗 Bagian 2 — Mengambil & Mengerjakan URL

### Cara Mengambil URL:

**Langkah 1** — Klik tombol **🚀 Mulai Ambil URL** atau ketik `/verif`

Bot akan memberikan 1 URL untuk kamu cek:
```
🔗 URL untuk Kamu:
https://contoh-url-stripe.com/page/12345

Silakan cek URL di atas, lalu laporkan hasilnya:

[ ✅ Berhasil ]  [ ❌ Gagal ]
```

**Langkah 2** — Buka URL tersebut di browser kamu dan cek kondisinya

**Langkah 3** — Kembali ke bot dan klik salah satu tombol:
- **✅ Berhasil** → URL bisa dibuka / berjalan normal
- **❌ Gagal** → URL tidak bisa dibuka, error, atau ada masalah

**Langkah 4** — Bot otomatis catat hasilnya dan siapkan URL berikutnya

> [!TIP]
> Setelah klik ✅ atau ❌, bot langsung memberikan URL berikutnya secara otomatis. Ulangi prosesnya sampai jatahmu habis atau task selesai.

---

## 📊 Bagian 3 — Melihat Progres Kamu Hari Ini

Ketik `/progress` atau klik tombol **📊 Progres Saya** di menu.

Bot akan tampilkan ringkasan kerjaan kamu hari ini:
```
📊 PROGRES KAMU — 2026-06-06
━━━━━━━━━━━━━━━━━━━━
✅ Berhasil : 14
❌ Gagal    : 3
⚪ Sisa     : 3
Progress    : ███████░░░ 17/20
```

---

## 🔔 Bagian 4 — Notifikasi Otomatis

Kamu akan otomatis menerima pesan dari bot dalam kondisi berikut:

| Situasi | Notifikasi yang Kamu Terima |
| :--- | :--- |
| **Pendaftaran disetujui** | Selamat datang! Kamu bisa mulai bekerja |
| **Pendaftaran ditolak** | Informasi bahwa pendaftaranmu tidak diterima |
| **Ada task baru** | Bot memberitahu ada pekerjaan baru hari ini |
| **Mendekati deadline** | Pengingat otomatis kalau kamu belum selesai |
| **URL yang dicek gagal** | Konfirmasi bahwa laporan kegagalan telah tercatat |

> [!NOTE]
> Semua notifikasi dikirim langsung ke chat bot kamu. Pastikan notifikasi Telegram tidak dimatikan agar tidak ketinggalan informasi penting.

---

## ❓ Bagian 5 — Kalau Ada Masalah

| Masalah yang Kamu Temui | Yang Perlu Dilakukan |
| :--- | :--- |
| **Pendaftaran tidak juga disetujui** | Hubungi Admin dan minta dicek pendaftaranmu |
| **Bot tidak membalas sama sekali** | Hubungi Admin atau Developer — kemungkinan sistem sedang mati |
| **Tidak ada task hari ini di bot** | Minta Admin mengecek apakah task sudah dibuat. Coba ketik `/verif` lagi nanti |
| **Sudah klik Berhasil/Gagal tapi tidak ada URL berikutnya** | Kemungkinan jatah URL-mu sudah habis. Cek dengan `/progress` |
| **URL yang diberikan tidak bisa dibuka sama sekali (error 404, dll)** | Tetap klik ❌ Gagal dan laporkan ke Admin lewat chat |
| **Tidak sengaja salah klik (mau Berhasil tapi klik Gagal)** | Hubungi Admin untuk koreksi data — kamu tidak bisa mengubah sendiri |

---

## 📝 Ringkasan Perintah Penting untuk Staff

| Perintah / Tombol | Fungsi |
| :--- | :--- |
| `/start` | Daftar pertama kali ke bot |
| `/menu` | Buka menu utama |
| `/task` | Lihat task yang aktif hari ini |
| `/verif` | Mulai ambil URL untuk dikerjakan |
| `/progress` | Lihat progres kerjaan kamu hari ini |
| `/cancel` | Batalkan apapun yang sedang dilakukan |
| **Tombol ✅ Berhasil** | Laporkan URL berhasil diverifikasi |
| **Tombol ❌ Gagal** | Laporkan URL gagal / bermasalah |

---

> Kalau ada pertanyaan atau ada yang tidak berjalan sesuai panduan ini, hubungi Admin atau Developer. 😊
