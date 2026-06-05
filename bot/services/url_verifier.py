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


async def verify_url(url: str) -> VerifResult:
    """
    Verifikasi URL Stripe secara async.
    Urutan pengecekan:
      1. Format URL valid
      2. Domain termasuk whitelist Stripe
      3. HTTP GET (follows redirect, max 3) — cek status code
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
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (StripeVerifBot/1.0)"},
        ) as client:
            resp = await client.get(url)
            code = resp.status_code

        if 200 <= code < 400:
            return VerifResult(VerifStatus.OK, code, "URL aktif & dapat diakses", url)
        else:
            return VerifResult(VerifStatus.HTTP_ERR, code, f"HTTP {code}", url)

    except httpx.TimeoutException:
        logger.warning(f"[Verifier] Timeout: {url}")
        return VerifResult(VerifStatus.TIMEOUT, None, "Request timeout", url)
    except Exception as exc:
        logger.error(f"[Verifier] Error: {exc} | URL={url}")
        return VerifResult(VerifStatus.HTTP_ERR, None, str(exc), url)
