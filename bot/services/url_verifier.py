"""
services/url_verifier.py
Memverifikasi URL Stripe: format, domain, dan reachability (HTTP check).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import httpx
from loguru import logger

from bot.config import STRIPE_ALLOWED_DOMAINS, HTTP_TIMEOUT


class VerifStatus(str, Enum):
    OK         = "OK"
    FORMAT_ERR = "FORMAT_ERR"
    DOMAIN_ERR = "DOMAIN_ERR"
    HTTP_ERR   = "HTTP_ERR"
    TIMEOUT    = "TIMEOUT"


@dataclass
class VerifResult:
    status:    VerifStatus
    http_code: int | None
    message:   str
    url:       str

    @property
    def is_ok(self) -> bool:
        return self.status == VerifStatus.OK

    @property
    def emoji(self) -> str:
        return {
            VerifStatus.OK:         "🟢",
            VerifStatus.FORMAT_ERR: "🔴",
            VerifStatus.DOMAIN_ERR: "🔴",
            VerifStatus.HTTP_ERR:   "🟡",
            VerifStatus.TIMEOUT:    "🟡",
        }[self.status]

    def short_text(self) -> str:
        return f"{self.emoji} {self.status.value}" + (
            f" ({self.http_code})" if self.http_code else ""
        )


_URL_RE = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|\d{1,3}(?:\.\d{1,3}){3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def _check_domain(url: str) -> bool:
    """Pastikan URL berasal dari domain Stripe yang diizinkan."""
    for domain in STRIPE_ALLOWED_DOMAINS:
        if domain in url.lower():
            return True
    return False


# Global optimized HTTP client — timeout 8 detik agar UX lebih responsif
_client = httpx.AsyncClient(
    follow_redirects=True,
    timeout=8.0,   # link expired biasanya langsung error, tidak perlu tunggu lama
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    },
)


async def verify_url(url: str) -> VerifResult:
    """
    Verifikasi URL Stripe secara async.

    Logika (dibalik dari konvensional):
      ✅ OK   = URL TIDAK bisa dibuka (timeout / error / 4xx / 5xx)
               → link sudah expired / sudah digunakan / sudah dibayar
      ✅ OK   = URL terbuka tapi ada konfirmasi pembayaran / redirect ke luar Stripe
               → pembayaran sudah selesai
      ❌ FAIL = URL berhasil dibuka, halaman Stripe masih aktif
               → link masih hidup = belum dibayar
    """
    url = url.strip()

    # 1. Format
    if not _URL_RE.match(url):
        return VerifResult(VerifStatus.FORMAT_ERR, None, "Format URL tidak valid", url)

    # 2. Domain whitelist
    if not _check_domain(url):
        return VerifResult(VerifStatus.DOMAIN_ERR, None, "Bukan domain Stripe", url)

    # 3. HTTP check — jalankan dengan try/except menyeluruh
    try:
        resp = await _client.get(url)
        code = resp.status_code
        html = resp.text.lower()
        final_url = str(resp.url).lower()

        # Redirect ke luar Stripe = sukses setelah bayar
        is_redirected_away = not any(
            domain in final_url for domain in STRIPE_ALLOWED_DOMAINS
        )

        # Kata kunci konfirmasi pembayaran di halaman
        paid_keywords = [
            "already been completed", "already been paid",
            "invoice has already", "payment has already",
            "link has already been used", "already paid",
            "already completed", "payment is complete",
            "payment successful", "successful payment",
            "thank you for your payment",
            "pembayaran ini sudah diselesaikan",
            "pembayaran ini telah diselesaikan",
            "faktur ini sudah dibayar", "invoice sudah dibayar",
        ]
        is_paid = any(kw in html for kw in paid_keywords)

        if 200 <= code < 300:
            if is_paid or is_redirected_away:
                return VerifResult(
                    VerifStatus.OK, code,
                    "Pembayaran sudah selesai / dikonfirmasi ✅", url
                )
            # HTTP 200 + halaman Stripe masih aktif → belum dibayar
            return VerifResult(
                VerifStatus.HTTP_ERR, code,
                "Link Stripe masih aktif — belum dibayar", url
            )
        else:
            # 4xx / 5xx → link tidak bisa dibuka → expired/digunakan → OK
            return VerifResult(
                VerifStatus.OK, code,
                f"Link tidak aktif (HTTP {code}) → sudah expired/digunakan ✅", url
            )

    except httpx.TimeoutException:
        # Timeout → link tidak merespons → anggap sudah tidak aktif → OK
        logger.info(f"[Verifier] Timeout → OK: {url}")
        return VerifResult(
            VerifStatus.OK, None,
            "Link timeout → tidak aktif lagi ✅", url
        )
    except Exception as exc:
        # Error koneksi apapun → link tidak bisa diakses → OK
        logger.info(f"[Verifier] Error → OK: {type(exc).__name__} | {url}")
        return VerifResult(
            VerifStatus.OK, None,
            "Link tidak dapat diakses → sudah tidak aktif ✅", url
        )


async def check_leonardo_api_key(api_key: str) -> str:
    """
    Verifikasi keaktifan API Key Leonardo.ai secara async.
    Mengecek keaktifan key dan memastikan sisa kredit/token > 0.
    """
    if not api_key:
        return ""
    url = "https://cloud.leonardo.ai/api/rest/v1/me"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    try:
        r = await _client.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            try:
                payload = r.json()
                user_details = payload.get("user_details", [])
                if user_details and isinstance(user_details, list):
                    user_info = user_details[0]
                    credits = user_info.get("apiCreditBalance", 0) or 0
                    tokens = user_info.get("subscriptionTokens", 0) or 0
                    
                    if credits <= 0 and tokens <= 0:
                        logger.warning(f"[Verifier] API Key has no credits/tokens (credits={credits}, tokens={tokens})")
                        return "EXPIRED"
                return "ACTIVE"
            except Exception as e:
                logger.error(f"[Verifier] Failed to parse Leonardo API response JSON: {e}")
                return "ACTIVE"  # Fallback to active if response parsing fails but status is 200
        elif r.status_code == 401:
            return "EXPIRED"
        else:
            return "EXPIRED"
    except Exception as e:
        logger.error(f"[Verifier] API Key Check Error: {e}")
        return f"FAILED (Error: {str(e)})"





