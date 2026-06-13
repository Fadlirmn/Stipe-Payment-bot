# Verifikasi Setelah Deadline & Status Gagal

**Tanggal:** 2026-06-13  
**Status:** selesai  
**Versi:** v4

## Konteks
Staff kesulitan melakukan verifikasi ulang pada tautan Stripe Checkout yang gagal setelah deadline tugas terlewati atau kuota harian habis. Selain itu, progress di menu pilihan task sebelumnya menghitung seluruh URL yang diproses (termasuk yang gagal) dan memiliki teks yang redundan. Selain itu, staff mendapatkan tampilan kosong ("Tidak ada URL") pada menu daftar link saat tugas selesai/deadline terlewati jika mereka tidak memiliki URL yang di-assign secara personal.

## Keputusan & Hasil
- **Akses Verifikasi Tetap Aktif**: Tombol verifikasi (`⚡ Verif` dan `Verifikasi Sekarang`) tetap ditampilkan dan dapat digunakan walaupun batas waktu terlewati atau kuota penuh.
- **Tampilan Status Gagal**: Status kegagalan (seperti `HTTP_ERR`, `TIMEOUT`) ditampilkan secara eksplisit di daftar tautan (contoh: `| HTTP_ERR`) untuk mempermudah identifikasi.
- **Peringatan Deadline**: Notifikasi peringatan deadline ditambahkan pada daftar tautan, detail, dan antrean berikutnya tanpa memblokir alur verifikasi.
- **Perbaikan Sinkronisasi**: Menyimpan kolom `assigned_to` dari Sheets ke database saat sync status dilakukan, serta memperbolehkan pembaruan status final antar status final lainnya.
- **Progress Valid (OK) Berbanding Total**: Mengubah tampilan progress pada menu pilihan task agar membandingkan jumlah URL berstatus `OK` dengan total URL (`OK / Total`), serta merapikan duplikasi kurung.
- **Aksesibilitas Daftar Link untuk Staff**: Jika deadline telah lewat atau semua URL pending telah terproses (tidak ada yang tersisa di pool), staff dapat melihat keseluruhan daftar URL tugas (tidak lagi dibatasi hanya ke milik sendiri) untuk mempermudah verifikasi ulang / retry URL yang gagal.

## Tindak Lanjut
- [ ] Monitor efektivitas verifikasi ulang oleh staff setelah deadline.

---
*Dibuat otomatis oleh agent · maks. 200 kata*
