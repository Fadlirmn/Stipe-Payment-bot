# 📋 Panduan Admin — Bot Verifikasi Stripe

> Panduan ini khusus untuk **Admin** — orang yang bertugas mengatur dan memantau pekerjaan tim. Tidak perlu jago IT, ikuti langkah-langkahnya saja!

---

## 🔑 Apa yang Bisa Dilakukan Admin?

Sebagai Admin, kamu bisa:
- ✅ Membuat & mengatur **jadwal kerja harian** (task)
- ✅ **Menerima atau menolak** anggota tim baru yang mau bergabung
- ✅ **Melihat laporan** hasil kerja tim setiap hari
- ✅ **Membuka dashboard** untuk pantau progres secara visual
- ✅ **Mengatur pengingat** otomatis untuk tim

Yang **tidak bisa** dilakukan Admin (hanya Dev/pemilik sistem yang bisa):
- ❌ Mengganti jabatan/role orang lain (misal: naikkan staff jadi admin)
- ❌ Melihat semua daftar pengguna sistem
- ❌ Kirim pesan broadcast ke semua orang

---

## 👋 Cara Mulai Pakai Bot

1. Buka Telegram, cari bot ini (nama bot sesuai yang dikasih developer)
2. Ketik `/start` dan kirim
3. Bot akan langsung mengenali kamu sebagai Admin
4. Ketik `/menu` untuk melihat semua tombol pilihan

Tampilannya akan seperti ini:
```
🤖 STRIPE VERIF BOT
Halo, [Nama Kamu] • Admin

[⚙️ Config Task]    [📋 Task Hari Ini]
[📈 Laporan Tim]    [🔔 Pengingat]
[🌐 Dashboard]      [ℹ️ Info]
```

---

## 🧩 Bagian 0 — Distribusi & Update Extension ke Staff

Staff membutuhkan **Extension Chrome "Stripe Card Autofill"** untuk bisa mengisi data kartu secara otomatis. Kamu sebagai Admin bertugas menyebarkan dan mengupdate extension ini ke seluruh tim.

### Yang Perlu Kamu Siapkan:
- 📁 Folder `stripe-autofill-extension` (minta dari Developer sekali saja)
- 📄 File `vcc.txt` berisi data kartu VCC yang akan dipakai staff

---

### Cara Kirim Extension ke Staff Baru:

**Langkah 1 — Kirim folder extension**

Kirim folder `stripe-autofill-extension` ke staff lewat:
- Google Drive / Dropbox (upload lalu share link)
- Telegram (compress jadi `.zip` dulu, lalu kirim file)
- WhatsApp / email (dalam format `.zip`)

> [!IMPORTANT]
> Pastikan kamu mengirim **seluruh folder** `stripe-autofill-extension`, bukan hanya satu file di dalamnya. Kalau isinya tidak lengkap, extension tidak bisa dipasang.

**Langkah 2 — Kirim file `vcc.txt`**

Buat file `vcc.txt` dengan data kartu VCC yang ingin dipakai tim. Format setiap baris:
```
nomorKartu|bulanTahunExp|cvc|namaPemegang|negaraKode|alamat|alamat2|kota|provinsi|kodePos
```

Contoh isi file:
```
# Data VCC Tim
4519912173897820|02/27|304|John Doe|US|123 Maple St||New York|NY|10001
4000056655665556|03/28|737|Jane Smith|US|456 Oak Ave||Los Angeles|CA|90001
```

Kirim file ini secara terpisah ke masing-masing staff, atau bagikan lewat grup.

> [!NOTE]
> Baris diawali `#` dianggap komentar — berguna untuk memberi label/keterangan di file.

**Langkah 3 — Minta staff ikuti panduan pemasangan**

Arahkan staff ke `user_guide.md` — di sana sudah ada instruksi lengkap cara pasang extension dan import `vcc.txt`.

---

### Cara Update Extension (kalau ada versi baru dari Developer):

Kalau Developer mengirim versi baru extension:

1. Terima folder `stripe-autofill-extension` baru dari Developer
2. Compress jadi `.zip` dan kirim ke semua staff
3. Minta staff:
   - Buka `chrome://extensions`
   - Klik tombol 🔄 **reload** (ikon putar) di kartu extension **Stripe Card Autofill**
   - Kalau tidak ada tombol reload, minta staff **hapus extension lama** lalu pasang ulang dengan folder baru

> [!TIP]
> Kalau update hanya pada file `vcc.txt` (data kartu baru/ganti), cukup kirim file `vcc.txt` baru ke staff. Tidak perlu update extension-nya.

---

### Cara Update Data VCC Saja (tanpa update extension):

Kalau kamu hanya ingin **mengganti atau menambah data kartu** untuk dipakai tim:

1. Edit file `vcc.txt` — tambah/ganti/hapus baris data kartu sesuai kebutuhan
2. Kirim file `vcc.txt` yang sudah diupdate ke staff
3. Minta staff buka extension → klik **Import File** → pilih file baru
4. Data lama otomatis tergantikan

---

## 👥 Bagian 1 — Menerima Anggota Tim Baru

Setiap kali ada staff baru yang mau bergabung, mereka harus **minta persetujuan Admin** dulu.

### Cara kerjanya:

**Langkah 1 — Staff kirim `/start` ke bot**

Bot akan otomatis kirim pesan notifikasi ke kamu seperti ini — **langsung ada tombolnya**:
```
🔔 Pendaftaran Baru!
━━━━━━━━━━━━━━━━━━━━
👤 Nama     : Budi Santoso
🔗 Username : @budisantoso

Klik tombol di bawah untuk menyetujui atau menolak.

[ ✅ Setujui ]  [ ❌ Tolak ]
```

**Langkah 2 — Klik salah satu tombol:**
- Klik **✅ Setujui** → staff langsung aktif dan bisa mulai bekerja
- Klik **❌ Tolak** → staff mendapat notifikasi bahwa pendaftarannya ditolak

**Langkah 3 — Selesai!**
Pesan notifikasi akan berubah jadi konfirmasi siapa yang menyetujui/menolak, dan staff langsung menerima kabar hasilnya secara otomatis.

> [!NOTE]
> Tidak perlu tahu atau mengetik ID apapun. Cukup klik tombol yang muncul di pesan notifikasi.

---

## 📋 Bagian 2 — Membuat Task Harian

Task harian = **daftar pekerjaan yang harus diselesaikan staff setiap hari**. Kamu yang menentukan berapa banyak URL yang harus dicek, jam batasnya kapan, dan seterusnya.

### Cara Membuat Task Baru:

**Langkah 1** — Ketik `/config_task` lalu kirim (atau klik tombol **⚙️ Config Task** di menu)

Bot akan mulai **tanya kamu satu per satu**, jawab saja sesuai instruksinya:

---

**❓ Pertanyaan 1 — Nama/Judul Task**

Contoh jawaban:
```
Verifikasi URL Hari Ini
```

---

**❓ Pertanyaan 2 — Keterangan Tambahan**

Isi dengan instruksi untuk staff, misal:
```
Pastikan semua URL bisa dibuka dengan normal
```
Kalau tidak perlu, ketik saja tanda minus:
```
-
```

---

**❓ Pertanyaan 3 — Nama Tab di Google Sheet**

Ini adalah nama tab (lembar) di spreadsheet Google yang berisi daftar URL-nya.
Biasanya cukup jawab:
```
Sheet1
```
*(Kalau kamu punya nama tab khusus, sesuaikan)*

---

**❓ Pertanyaan 4 — Berapa Total URL yang Dikerjakan?**

Jumlah total URL untuk seluruh tim hari ini. Contoh:
```
100
```
Kalau tidak mau dibatasi, ketik:
```
0
```

---

**❓ Pertanyaan 5 — Berapa URL per Orang?**

Batas URL yang boleh dikerjakan setiap satu orang staff. Contoh:
```
20
```
Kalau tidak mau dibatasi per orang, ketik:
```
0
```

---

**❓ Pertanyaan 6 — Jam Batas (Deadline)**

Batas jam kerja task hari ini dalam format jam:menit. Contoh:
```
23:59
```
Kalau tidak ada batas waktu, ketik:
```
-
```

---

**❓ Pertanyaan 7 — Jenis Pengulangan**

Pilih salah satu dan ketik:
- `daily` → Task ini **muncul otomatis setiap hari** (cocok untuk pekerjaan rutin harian)
- `weekly` → Task **muncul setiap hari Senin** saja
- `once` → Task **hanya sekali**, tidak muncul lagi keesokan harinya

---

Setelah kamu jawab semua pertanyaan, bot akan konfirmasi:
```
✅ Task berhasil dibuat!
ID    : TASK-20260606-...
Judul : Verifikasi URL Hari Ini
Repeat: daily
```

**Selesai! Staff sudah bisa mulai bekerja.**

---

> [!TIP]
> Kalau kamu salah ketik di tengah-tengah, cukup ketik `/cancel` dan mulai ulang dari awal.

---

## 📊 Bagian 3 — Melihat Laporan Tim

### Cara Cepat Lihat Laporan (via Telegram):

Ketik `/report` dan kirim. Bot langsung tampilkan ringkasan seperti ini:

```
📈 LAPORAN HARIAN — 2026-06-06
━━━━━━━━━━━━━━━━━━━━
Total URL   : 80
✅ Berhasil : 65
❌ Gagal    : 10
⚪ Belum    : 5
Progress    : ████████░░ 75/80

👥 Per Staff:
  1. Budi    : 25✅ 2❌ (27 total)
  2. Sari    : 22✅ 4❌ (26 total)
  3. Rudi    : 18✅ 4❌ (22 total)
```

Kamu bisa langsung tahu:
- Siapa yang paling banyak menyelesaikan pekerjaan
- Berapa URL yang berhasil vs gagal
- Berapa yang belum dikerjakan

---

### Lihat Laporan Lebih Detail (via Dashboard Web):

Untuk tampilan grafik dan data yang lebih lengkap, gunakan **Web Dashboard**.

**Cara membukanya:**
1. Ketik `/dashboard` di bot, lalu kirim
2. Bot akan kirimkan **tautan link**
3. Klik linknya — kamu akan dibawa ke halaman web
4. Klik tombol **Login dengan Telegram**, lalu setujui di aplikasi Telegram kamu
5. Dashboard akan terbuka!

**Di dalam Dashboard, kamu bisa lihat:**

| Menu | Isinya |
| :--- | :--- |
| 🏠 **Ringkasan** | Total URL hari ini, grafik persentase berhasil/gagal |
| 📋 **Daftar Task** | Semua task yang aktif beserta progresnya |
| 👥 **Monitor Staff** | Urutan performa staff hari ini (siapa paling banyak selesai) |
| 🔗 **Log URL** | Riwayat URL satu per satu — siapa yang cek, hasilnya apa, jam berapa |
| 📈 **Grafik** | Tren kerja tim selama 7 hari terakhir |

---

## 🔔 Bagian 4 — Pengingat Otomatis

Sistem sudah otomatis kirim pengingat tanpa kamu atur manual:

- Setiap malam pukul **22:00 WIB** → kamu dapat ringkasan laporan harian otomatis di Telegram
- Kalau ada staff yang **belum selesai menjelang deadline** → mereka dapat pesan pengingat otomatis
- Kalau URL **gagal diverifikasi** → staff langsung dapat notifikasi di Telegram

---

## ❓ Bagian 5 — Kalau Ada Masalah

| Masalah yang Kamu Temui | Yang Perlu Dilakukan |
| :--- | :--- |
| **Bot tidak membalas sama sekali** | Hubungi Developer — kemungkinan sistem sedang mati atau ada gangguan |
| **Staff bilang tidak ada task hari ini** | Cek apakah kamu sudah buat task dengan `/config_task`. Kalau sudah, coba minta staff ketik `/verif` lagi |
| **URL di spreadsheet tidak muncul di bot** | Pastikan kolom tanggal di spreadsheet terisi dengan tanggal **hari ini**, dan kolom statusnya masih **kosong** |
| **Tidak bisa buka Dashboard (tombol login tidak muncul)** | Hubungi Developer untuk didaftarkan domain-nya ke pengaturan bot |
| **Dashboard muncul tapi langsung ditolak** | Hubungi Developer dan minta akun kamu diaktifkan ulang |
| **Staff bilang extension tidak bisa autofill** | Pastikan staff membuka URL `checkout.stripe.com` — extension tidak bekerja di URL lain. Coba minta reload extension di `chrome://extensions` |
| **Staff bilang data kartu tidak muncul di extension** | Pastikan staff sudah import file `vcc.txt` yang benar. Kirim ulang file-nya dan minta import lagi |

---

## 📝 Ringkasan Perintah Penting untuk Admin

| Perintah / Tombol | Fungsi |
| :--- | :--- |
| `/menu` | Buka menu utama dengan tombol-tombol |
| `/task` | Lihat task yang aktif hari ini |
| `/config_task` | Buat task baru |
| **Tombol ✅ Setujui** di notifikasi | Terima anggota tim baru — langsung klik, tanpa ketik apapun |
| **Tombol ❌ Tolak** di notifikasi | Tolak pendaftaran anggota baru |
| `/report` | Lihat laporan harian tim |
| `/dashboard` | Dapatkan link Web Dashboard |
| `/backup` | Mencadangkan seluruh data Firestore ke SQLite lokal (`data/backup.db`) |
| `/cancel` | Batalkan apapun yang sedang diisi |

---

> Kalau ada pertanyaan atau ada yang tidak berjalan sesuai panduan ini, hubungi Developer / pemilik sistem. 😊
