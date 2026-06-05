/**
 * api/verify.js — Vercel Serverless Function
 *
 * Memverifikasi data dari Telegram Login Widget menggunakan BOT_TOKEN
 * yang tersimpan aman di server (tidak pernah dikirim ke browser).
 *
 * POST /api/verify
 * Body: { id, first_name, last_name, username, photo_url, auth_date, hash }
 * Response: { ok: true, user: {...} } | { ok: false, error: "..." }
 */
const crypto = require('crypto');

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  const BOT_TOKEN = process.env.BOT_TOKEN;
  if (!BOT_TOKEN) return res.status(500).json({ ok: false, error: 'Server misconfiguration' });

  try {
    const { hash, ...data } = req.body;

    if (!hash) return res.status(400).json({ ok: false, error: 'Missing hash' });

    // ── 1. Verifikasi hash Telegram ───────────────────────────────────────
    // Sesuai dokumentasi: https://core.telegram.org/widgets/login#checking-authorization
    const secretKey = crypto.createHash('sha256').update(BOT_TOKEN).digest();
    const checkString = Object.keys(data)
      .sort()
      .map(k => `${k}=${data[k]}`)
      .join('\n');
    const expectedHash = crypto.createHmac('sha256', secretKey).update(checkString).digest('hex');

    if (expectedHash !== hash) {
      return res.status(401).json({ ok: false, error: 'Invalid authentication data' });
    }

    // ── 2. Cek auth_date tidak lebih dari 24 jam ───────────────────────────
    const authAge = Math.floor(Date.now() / 1000) - parseInt(data.auth_date, 10);
    if (authAge > 86400) {
      return res.status(401).json({ ok: false, error: 'Auth data expired. Please login again.' });
    }

    // Hash valid — kembalikan data user ke client
    // Role check dilakukan di client via Firestore (public read)
    return res.status(200).json({ ok: true, user: data });

  } catch (err) {
    console.error('verify error:', err);
    return res.status(500).json({ ok: false, error: 'Internal server error' });
  }
};
