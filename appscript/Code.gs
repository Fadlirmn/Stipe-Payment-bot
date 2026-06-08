/**
 * Code.gs — Stripe Verif Bot · Google Apps Script Web App
 *
 * Deploy sebagai Web App:
 *   Extensions → Apps Script → Deploy → New deployment
 *   Type: Web App | Execute as: Me | Who has access: Anyone
 *
 * ── Struktur Sheet1 (kolom): ──────────────────────────────────────────────
 *   A: Email  B: Password  C: API Key  D: Stripe URL  E: Timestamp  F: Status
 *
 * ── doGet  — dipakai oleh bot Telegram untuk ambil URL hari ini ──────────
 *   GET  {WEB_APP_URL}?secret=...&date=YYYY-MM-DD
 *   → { date, count, data: [{account, payment_url, notes}] }
 *
 * ── doPost — dipakai oleh extension / script lain ────────────────────────
 *   action: updateStatus | copyActiveKey | getUnusedKey | getAllKeys
 *   (atau tanpa action → append baris baru)
 */

// ── Konfigurasi ─────────────────────────────────────────────────────────────
// Kolom Sheet1 (0-indexed)
var COL_EMAIL     = 0; // A
var COL_PASSWORD  = 1; // B
var COL_API_KEY   = 2; // C
var COL_URL       = 3; // D — Stripe URL
var COL_TIMESTAMP = 4; // E — waktu append
var COL_STATUS    = 5; // F — SUCCESS / FAILED / ERROR

// Domain Stripe yang valid
var STRIPE_DOMAINS = /^https?:\/\/(checkout|buy|billing|invoice|pay)?\.?stripe\.com\//i;

// ═══════════════════════════════════════════════════════════════════════════
//  doGet — Bot Telegram ambil URL hari ini
// ═══════════════════════════════════════════════════════════════════════════

function doGet(e) {
  var params = (e && e.parameter) ? e.parameter : {};
  var dateStr = params.date || getTodayStr();

  try {
    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("Sheet1") || ss.getSheets()[0];
    var data  = sheet.getDataRange().getValues();

    var results = [];
    for (var i = 1; i < data.length; i++) {
      var row       = data[i];
      var rawUrl    = String(row[COL_URL]       || "").trim();
      var rawTs     = row[COL_TIMESTAMP];
      var email     = String(row[COL_EMAIL]     || "").trim();
      var currentStatus = String(row[COL_STATUS] || "").trim();

      if (!rawUrl || !STRIPE_DOMAINS.test(rawUrl)) continue;

      // Skip baris yang sudah punya status (sudah diverifikasi)
      if (currentStatus) continue;

      var rowDate = parseDateValue(rawTs);
      if (!rowDate) continue;
      if (formatDate(rowDate) !== dateStr) continue;

      results.push({
        account:     email,
        api_key:     String(row[COL_API_KEY]     || "").trim(),
        payment_url: rawUrl,
        notes:       "",
        row_index:   i + 1  // 1-based, berguna jika bot perlu update status nanti
      });
    }

    return jsonOut({ date: dateStr, count: results.length, data: results });

  } catch (err) {
    return jsonOut({ error: err.message });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  doPost — Extension / script lain
// ═══════════════════════════════════════════════════════════════════════════

function doPost(e) {
  var data = JSON.parse(e.postData.contents);
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  if (data.action === "updateStatus") {
    var tabName = data.tab || "Sheet1";
    var sheet = ss.getSheetByName(tabName) || ss.getSheets()[0];
    var range = sheet.getDataRange();
    var values = range.getValues();

    for (var i = 0; i < values.length; i++) {
      if (values[i][COL_URL] === data.stripe_url) {
        // Tulis status ke Kolom F (Kolom ke-6)
        sheet.getRange(i + 1, COL_STATUS + 1).setValue(data.status);

        // Tulis info staff ke Kolom G (Kolom ke-7, sebelahnya) jika disediakan
        if (data.staff_info !== undefined) {
          sheet.getRange(i + 1, COL_STATUS + 2).setValue(data.staff_info);
        }

        // Warna baris secara dinamis
        var statusUpper = String(data.status).toUpperCase();
        var color = "#ffffff";
        if (statusUpper === "SUCCESS" || statusUpper === "OK") {
          color = "#b7e1cd"; // Hijau muda jika sukses
        } else if (statusUpper.indexOf("ASSIGNED") === 0) {
          color = "#c9daf8"; // Biru muda jika sedang di-assign/proses
        } else if (statusUpper === "FAILED" || statusUpper === "SKIPPED" || statusUpper === "ERROR") {
          color = "#f8cecc"; // Merah muda jika gagal/error atau dilewati
        }
        sheet.getRange(i + 1, 1, 1, sheet.getLastColumn()).setBackground(color);

        return jsonOut({ status: "updated", row: i + 1 });
      }
    }
    return jsonOut({ status: "not_found" });
  }

  else if (data.action === "copyActiveKey") {
    var sheets = ss.getSheets();
    var targetSheet = null;
    var targetGid = data.target_gid.toString();
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId().toString() === targetGid) {
        targetSheet = sheets[i];
        break;
      }
    }
    if (!targetSheet) {
      targetSheet = sheets.length > 1 ? sheets[1] : ss.insertSheet("Active Keys");
    }

    if (targetSheet.getLastRow() === 0) {
      targetSheet.appendRow(["API Key", "Email", "Username", "Tokens", "Renewal Date", "Check Date", "Used Status", "Active Status", "Check Keys Timestamp"]);
    }

    var range = targetSheet.getDataRange();
    var values = range.getValues();
    var exists = false;
    for (var j = 0; j < values.length; j++) {
      if (values[j][0] === data.api_key) {
        exists = true;
        if (data.tokens        !== undefined) targetSheet.getRange(j + 1, 4).setValue(data.tokens);
        if (data.renewal_date  !== undefined) targetSheet.getRange(j + 1, 5).setValue(data.renewal_date);
        targetSheet.getRange(j + 1, 6).setValue(new Date());
        if (data.used_status   !== undefined) targetSheet.getRange(j + 1, 7).setValue(data.used_status);
        if (data.active_status !== undefined) {
          var ar = targetSheet.getRange(j + 1, 8);
          ar.setValue(data.active_status);
          ar.setBackground(data.active_status === "Aktif" ? "#b7e1cd" : "#f8cecc");
        }
        if (data.check_keys_timestamp !== undefined) targetSheet.getRange(j + 1, 9).setValue(data.check_keys_timestamp);
        break;
      }
    }

    if (!exists) {
      targetSheet.appendRow([data.api_key, data.email, data.username, data.tokens, data.renewal_date, new Date(), data.used_status || "", data.active_status || "", data.check_keys_timestamp || ""]);
      if (data.active_status) {
        var lastRow = targetSheet.getLastRow();
        var ar = targetSheet.getRange(lastRow, 8);
        ar.setBackground(data.active_status === "Aktif" ? "#b7e1cd" : "#f8cecc");
      }
    }

    return jsonOut({ status: "copied" });
  }

  else if (data.action === "getUnusedKey") {
    var sheets = ss.getSheets();
    var targetSheet = null;
    var targetGid = data.target_gid.toString();
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId().toString() === targetGid) { targetSheet = sheets[i]; break; }
    }
    if (!targetSheet) {
      if (sheets.length > 1) targetSheet = sheets[1];
      else return jsonOut({ status: "error", message: "Target sheet not found" });
    }

    var values = targetSheet.getDataRange().getValues();
    for (var i = 1; i < values.length; i++) {
      var key = values[i][0];
      var status = (values[i][6] || "").toString().trim().toLowerCase();
      if (!key) continue;
      if (status === "used" || status === "invalid" || status === "inactive") continue;

      targetSheet.getRange(i + 1, 7).setValue("used");
      return jsonOut({ status: "success", api_key: key, email: values[i][1] || "", username: values[i][2] || "" });
    }
    return jsonOut({ status: "no_keys_available" });
  }

  else if (data.action === "getAllKeys") {
    var sheets = ss.getSheets();
    var targetSheet = null;
    var targetGid = data.target_gid.toString();
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId().toString() === targetGid) { targetSheet = sheets[i]; break; }
    }
    if (!targetSheet) {
      if (sheets.length > 1) targetSheet = sheets[1];
      else return jsonOut({ status: "error", message: "Target sheet not found" });
    }

    var values = targetSheet.getDataRange().getValues();
    var keysList = [];
    for (var i = 1; i < values.length; i++) {
      var key = values[i][0];
      if (key && key.toString().trim() !== "") {
        keysList.push({ api_key: key, tokens: values[i][3], used_status: values[i][6] });
      }
    }
    return jsonOut({ status: "success", keys: keysList });
  }

  else {
    // Default: append baris baru
    var sheet = ss.getSheetByName("Sheet1") || ss.getSheets()[0];
    sheet.appendRow([data.email, data.password, data.api_key, data.stripe_url, new Date()]);
    return jsonOut({ status: "success" });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════════════════

function parseDateValue(val) {
  if (!val) return null;
  if (val instanceof Date) return val;
  var s = String(val).trim();
  var m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
  m = s.match(/^(\d{2})-(\d{2})-(\d{4})/);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
  return null;
}

function formatDate(d) {
  var y  = d.getFullYear();
  var m  = String(d.getMonth() + 1).padStart(2, "0");
  var dd = String(d.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + dd;
}

function getTodayStr() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
}

function jsonOut(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
