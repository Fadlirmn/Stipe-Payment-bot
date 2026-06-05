/**
 * build.js — Inject Environment Variables ke index.html
 *
 * ── Cara pakai ────────────────────────────────────────────────────────────
 * Lokal (development):
 *   1. Salin .env.example → .env dan isi nilainya
 *   2. Jalankan: node build.js
 *   3. Buka dist/index.html di browser
 *
 * Vercel (production):
 *   - Set semua variabel di Vercel Dashboard → Settings → Environment Variables
 *   - Vercel otomatis menjalankan "node build.js" saat deploy (via vercel.json)
 *   - File .env lokal diabaikan di Vercel (tidak di-upload)
 *
 * ── Env vars yang dibutuhkan ───────────────────────────────────────────────
 *   FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID,
 *   FIREBASE_STORAGE_BUCKET, FIREBASE_MESSAGING_SENDER_ID, FIREBASE_APP_ID,
 *   TELEGRAM_BOT_USERNAME
 *
 * ── Env vars hanya di Vercel (server-side, JANGAN di .env lokal) ──────────
 *   BOT_TOKEN   → dipakai api/verify.js untuk verifikasi hash Telegram
 */

const fs   = require("fs");
const path = require("path");

// ── Load .env lokal jika ada (untuk development) ───────────────────────────
// Di Vercel, env vars sudah tersedia via process.env — dotenv di-skip otomatis.
const envPath = path.join(__dirname, ".env");
if (fs.existsSync(envPath)) {
  const lines = fs.readFileSync(envPath, "utf8").split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
    // Jangan timpa env var yang sudah ada (Vercel env lebih prioritas)
    if (key && !(key in process.env)) {
      process.env[key] = val;
    }
  }
  console.log("📄 Loaded .env (local development mode)");
}

const SRC  = path.join(__dirname, "index.html");
const DIST = path.join(__dirname, "dist", "index.html");

// Pastikan folder dist ada
fs.mkdirSync(path.join(__dirname, "dist"), { recursive: true });

// Baca template
let html = fs.readFileSync(SRC, "utf8");

// ── Mapping placeholder → env var ─────────────────────────────────────────
const replacements = {
  "%%FIREBASE_API_KEY%%":             process.env.FIREBASE_API_KEY             || "",
  "%%FIREBASE_AUTH_DOMAIN%%":         process.env.FIREBASE_AUTH_DOMAIN         || "",
  "%%FIREBASE_PROJECT_ID%%":          process.env.FIREBASE_PROJECT_ID          || "",
  "%%FIREBASE_STORAGE_BUCKET%%":      process.env.FIREBASE_STORAGE_BUCKET      || "",
  "%%FIREBASE_MESSAGING_SENDER_ID%%": process.env.FIREBASE_MESSAGING_SENDER_ID || "",
  "%%FIREBASE_APP_ID%%":              process.env.FIREBASE_APP_ID              || "",
  "%%TELEGRAM_BOT_USERNAME%%":        process.env.TELEGRAM_BOT_USERNAME        || "",
};

// ── Validasi — semua harus terisi ─────────────────────────────────────────
const missing = Object.entries(replacements)
  .filter(([, v]) => !v)
  .map(([k]) => k.replace(/%%/g, ""));

if (missing.length > 0) {
  console.error("❌ BUILD FAILED — Missing environment variables:");
  missing.forEach(k => console.error(`   - ${k}`));
  console.error("\n💡 Lokal: isi nilai di dashboard-vercel/.env");
  console.error("   Vercel: set di Project → Settings → Environment Variables");
  process.exit(1);
}

// ── Ganti semua placeholder ────────────────────────────────────────────────
for (const [placeholder, value] of Object.entries(replacements)) {
  html = html.replaceAll(placeholder, value);
}

// ── Copy asset files (css/, js/) ke dist/ ─────────────────────────────────
function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath  = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

if (fs.existsSync(path.join(__dirname, "css"))) copyDir(path.join(__dirname, "css"), path.join(__dirname, "dist", "css"));
if (fs.existsSync(path.join(__dirname, "js")))  copyDir(path.join(__dirname, "js"),  path.join(__dirname, "dist", "js"));

// ── Tulis hasil ────────────────────────────────────────────────────────────
fs.writeFileSync(DIST, html, "utf8");
console.log("✅ Build selesai → dist/index.html");
console.log(`   Firebase Project  : ${process.env.FIREBASE_PROJECT_ID}`);
console.log(`   Telegram Bot      : @${process.env.TELEGRAM_BOT_USERNAME}`);
