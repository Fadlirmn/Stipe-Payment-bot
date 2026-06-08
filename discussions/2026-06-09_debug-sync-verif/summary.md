# Debug Sync & Verif

**Tanggal:** 2026-06-09  
**Status:** selesai  
**Versi:** v1

## Konteks
Mengatasi kendala kegagalan sinkronisasi data Google Sheets ke PostgreSQL, mengidentifikasi penyebab baris dilewati (skip), serta mempercepat dan mengamankan verifikasi URL Stripe.

## Keputusan & Hasil
- **Apps Script Tab & Debug**: Mengaktifkan input `params.tab` fleksibel dan mode `debug=1` untuk mendeteksi baris terisi `ASSIGNED` di spreadsheet.
- **User-Agent Realistis**: Mengganti User-Agent `StripeVerifBot/1.0` ke Chrome Windows asli untuk menghindari pemblokiran/timeout oleh Cloudflare/Stripe.
- **Resiliensi Bot**: Menambahkan *global error handler* untuk menangkap callback query yang kedaluwarsa secara bersih.
- **Perintah Dev Baru**: Implementasi perintah `/reset_today`, `/retry_failed`, dan `/verify_failed` untuk re-verifikasi massal otomatis di background.

## Tindak Lanjut
- [ ] Lakukan `git pull` dan restart bot kontainer di VPS.

---
*Dibuat otomatis oleh agent · maks. 200 kata*
