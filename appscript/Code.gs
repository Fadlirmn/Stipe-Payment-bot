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
var COL_ASSIGN_BY = 5; // F — Assigned By (nama staff yang di-assign)
var COL_STATUS    = 6; // G — OK / HTTP_ERR / ASSIGNED-xxx / SKIPPED
var COL_VERIF_BY  = 7; // H — Verified By (nama staff yang verifikasi)

// Domain Stripe yang valid
var STRIPE_DOMAINS = /^https?:\/\/(checkout|buy|billing|invoice|pay)?\.?stripe\.com\//i;

// ═══════════════════════════════════════════════════════════════════════════
//  doGet — Bot Telegram ambil URL hari ini
// ═══════════════════════════════════════════════════════════════════════════

function doGet(e) {
  var params = (e && e.parameter) ? e.parameter : {};
  var dateStr = params.date || getTodayStr();
  var isDebug = params.debug === "1";

  try {
    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    var tabName = params.tab || "Sheet1";
    var sheet = ss.getSheetByName(tabName) || ss.getSheets()[0];
    var data  = sheet.getDataRange().getValues();

    var results = [];
    var debugInfo = [];

    for (var i = 1; i < data.length; i++) {
      var row       = data[i];
      var rawUrl    = String(row[COL_URL]       || "").trim();
      var rawTs     = row[COL_TIMESTAMP];
      var email     = String(row[COL_EMAIL]     || "").trim();
      var currentStatus = String(row[COL_STATUS] || "").trim();

      if (!rawUrl) {
        if (isDebug) debugInfo.push({ row: i + 1, reason: "empty url" });
        continue;
      }
      if (!STRIPE_DOMAINS.test(rawUrl)) {
        if (isDebug) debugInfo.push({ row: i + 1, reason: "invalid stripe domain: " + rawUrl });
        continue;
      }

      // Skip baris yang sudah punya status verifikasi final (OK/HTTP_ERR/SKIPPED/dll.)
      // Jangan skip baris yang berstatus ASSIGNED karena masih harus diverifikasi oleh staff
      if (currentStatus && !/^ASSIGNED/i.test(currentStatus)) {
        if (isDebug) debugInfo.push({ row: i + 1, reason: "status is final: " + currentStatus });
        continue;
      }

      var rowDate = parseDateValue(rawTs);
      if (!rowDate) {
        if (isDebug) debugInfo.push({ row: i + 1, reason: "cannot parse date: " + String(rawTs) });
        continue;
      }

      var formatted = formatDate(rowDate);
      if (formatted !== dateStr) {
        if (isDebug) debugInfo.push({ row: i + 1, reason: "date mismatch: " + formatted + " vs target " + dateStr });
        continue;
      }

      results.push({
        account:     email,
        api_key:     String(row[COL_API_KEY]     || "").trim(),
        payment_url: rawUrl,
        notes:       "",
        status:      currentStatus,
        date:        formatted,
        timestamp:   String(rawTs),
        row_index:   i + 1  // 1-based, berguna jika bot perlu update status nanti
      });
    }

    if (isDebug) {
      return jsonOut({ date: dateStr, count: results.length, debug: debugInfo, data: results });
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
        var statusUpper = String(data.status).toUpperCase();
        var isAssign = statusUpper.indexOf("ASSIGNED") === 0;

        // Kolom F — Status utama
        sheet.getRange(i + 1, COL_STATUS + 1).setValue(data.status);

        if (data.staff_info !== undefined) {
          if (isAssign) {
            // Kolom G — Assigned By (hanya diisi saat assign, tidak ditimpa verif)
            sheet.getRange(i + 1, COL_ASSIGN_BY + 1).setValue(data.staff_info);
          } else {
            // Kolom H — Verified By (hasil verifikasi, tidak menimpa assign)
            sheet.getRange(i + 1, COL_VERIF_BY + 1).setValue(data.staff_info);
          }
        }

        // Warna baris secara dinamis
        var color = "#ffffff";
        if (statusUpper === "SUCCESS" || statusUpper === "OK") {
          color = "#b7e1cd"; // Hijau muda — sukses/expired
        } else if (isAssign) {
          color = "#c9daf8"; // Biru muda — sedang diproses
        } else if (statusUpper === "FAILED" || statusUpper === "HTTP_ERR" ||
                   statusUpper === "TIMEOUT" || statusUpper === "SKIPPED" ||
                   statusUpper === "ERROR") {
          color = "#f8cecc"; // Merah muda — gagal/error
        }
        sheet.getRange(i + 1, 1, 1, sheet.getLastColumn()).setBackground(color);

        return jsonOut({ status: "updated", row: i + 1,
                         column: isAssign ? "assign_by (G)" : "verif_by (H)" });
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
    var range = sheet.getDataRange();
    var values = range.getValues();
    var foundIndex = -1;

    for (var i = 0; i < values.length; i++) {
      var sheetUrl = String(values[i][COL_URL] || "").trim();
      var sheetEmail = String(values[i][COL_EMAIL] || "").trim();
      if ((data.stripe_url && sheetUrl === String(data.stripe_url).trim()) || 
          (data.email && sheetEmail === String(data.email).trim())) {
        foundIndex = i;
        break;
      }
    }

    if (foundIndex !== -1) {
      // Update data yang sudah ada (misal API key baru)
      if (data.api_key) {
        sheet.getRange(foundIndex + 1, COL_API_KEY + 1).setValue(data.api_key);
      }
      sheet.getRange(foundIndex + 1, COL_TIMESTAMP + 1).setValue(new Date());
      return jsonOut({ status: "updated", row: foundIndex + 1 });
    } else {
      // Append baris baru jika benar-benar baru
      sheet.appendRow([data.email, data.password, data.api_key, data.stripe_url, new Date()]);
      return jsonOut({ status: "success" });
    }
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
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tz = ss.getSpreadsheetTimeZone();
  return Utilities.formatDate(d, tz, "yyyy-MM-dd");
}

function getTodayStr() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tz = ss.getSpreadsheetTimeZone();
  return Utilities.formatDate(new Date(), tz, "yyyy-MM-dd");
}

function jsonOut(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Fungsi sekali pakai (One-time run) untuk membersihkan semua baris duplikat di Google Sheet.
 * Jalankan fungsi ini langsung dari editor Apps Script.
 */
function cleanDuplicates() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("Sheet1") || ss.getSheets()[0];
  var range = sheet.getDataRange();
  var values = range.getValues();
  
  if (values.length <= 1) {
    Logger.log("Sheet kosong atau hanya berisi header.");
    return;
  }
  
  var header = values[0];
  var uniqueRows = [];
  var seenUrls = {};
  var seenEmails = {};
  
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    var email = String(row[COL_EMAIL] || "").trim();
    var url = String(row[COL_URL] || "").trim();
    
    // Jika url atau email sudah terdaftar sebelumnya, anggap sebagai duplikat
    if ((url && seenUrls[url]) || (email && seenEmails[email])) {
      continue;
    }
    
    if (url) seenUrls[url] = true;
    if (email) seenEmails[email] = true;
    uniqueRows.push(row);
  }
  
  // Bersihkan data lama, lalu tulis ulang data unik
  sheet.clearContents();
  
  // Tulis kembali header
  sheet.getRange(1, 1, 1, header.length).setValues([header]);
  
  // Tulis kembali data unik jika ada
  if (uniqueRows.length > 0) {
    sheet.getRange(2, 1, uniqueRows.length, header.length).setValues(uniqueRows);
  }
  
  Logger.log("✅ Pembersihan selesai! Data unik tersisa: " + uniqueRows.length + " baris.");
}
