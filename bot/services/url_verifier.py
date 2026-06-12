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


# Global optimized HTTP client with connection pooling
_client = httpx.AsyncClient(
    follow_redirects=True,
    timeout=HTTP_TIMEOUT,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    },
)


async def verify_url(url: str) -> VerifResult:
    """
    Verifikasi URL Stripe secara async.
    Urutan pengecekan:
      1. Format URL valid
      2. Domain termasuk whitelist Stripe
      3. HTTP GET (follows redirect, max 3) — cek status code & isi HTML untuk status pembayaran
    """
    url = url.strip()

    # 1. Format
    if not _URL_RE.match(url):
        return VerifResult(VerifStatus.FORMAT_ERR, None, "Format URL tidak valid", url)

    # 2. Domain
    if not _check_domain(url):
        return VerifResult(VerifStatus.DOMAIN_ERR, None, "Bukan domain Stripe", url)

    # 3. HTTP check
    try:
        resp = await _client.get(url)
        code = resp.status_code
        html = resp.text.lower()
        final_url = str(resp.url).lower()

        if 200 <= code < 400:
            # 1. Check if the page contains keywords indicating completed payment
            paid_keywords = [
                "already been completed",
                "already been paid",
                "invoice has already",
                "payment has already",
                "link has already been used",
                "already paid",
                "already completed",
                "payment is complete",
                "payment successful",
                "successful payment",
                "thank you for your payment",
                "pembayaran ini sudah diselesaikan",
                "pembayaran ini telah diselesaikan",
                "faktur ini sudah dibayar",
                "invoice sudah dibayar"
            ]
            is_paid = any(kw in html for kw in paid_keywords)

            # 2. Check if the final URL is redirected away from Stripe domains (indicating success redirect)
            is_redirected_away = not any(domain in final_url for domain in STRIPE_ALLOWED_DOMAINS)

            if is_paid or is_redirected_away:
                return VerifResult(VerifStatus.OK, code, "Pembayaran sukses / sudah selesai", url)
            else:
                return VerifResult(VerifStatus.HTTP_ERR, code, "Stripe belum dibayar / masih aktif", url)
        else:
            return VerifResult(VerifStatus.HTTP_ERR, code, f"HTTP {code}", url)

    except httpx.TimeoutException:
        logger.warning(f"[Verifier] Timeout: {url}")
        return VerifResult(VerifStatus.TIMEOUT, None, "Request timeout", url)
    except Exception as exc:
        logger.error(f"[Verifier] Error: {exc} | URL={url}")
        return VerifResult(VerifStatus.HTTP_ERR, None, str(exc), url)


async def check_leonardo_api_key(api_key: str) -> str:
    """
    Verifikasi keaktifan API Key Leonardo.ai secara async.
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
            return "ACTIVE"
        elif r.status_code == 401:
            return "EXPIRED"
        else:
            return f"FAILED (HTTP {r.status_code})"
    except Exception as e:
        logger.error(f"[Verifier] API Key Check Error: {e}")
        return f"FAILED (Error: {str(e)})"
