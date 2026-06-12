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

from bot.config import STRIPE_ALLOWED_DOMAINS, HTTP_TIMEOUT, LEONARDO_PROXY_URL


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

# Residential Proxy Session Rotator & API Croxy client
async def get_rotated_proxy_url(proxy_url: str | None) -> str | None:
    """
    Mendapatkan URL proxy dengan rotasi IP per request.
    Jika proxy_url adalah API Croxy, bot melakukan GET request ke API tersebut.
    Jika merupakan URL proxy biasa, dirotasi session ID-nya jika memiliki username:password.
    """
    if not proxy_url:
        return None
    proxy_url = proxy_url.strip()
    
    # 1. API Croxy (get-ip-v3 / api.croxy.com)
    if "api.croxy.com" in proxy_url or "get-ip-v3" in proxy_url or "/ip/" in proxy_url:
        try:
            logger.info("Fetching dynamic proxy from Croxy API...")
            # Menggunakan _client (koneksi langsung) ke API Croxy
            resp = await _client.get(proxy_url, timeout=10)
            if resp.status_code == 200:
                ip_port = resp.text.strip()
                if ip_port and ":" in ip_port:
                    actual_proxy = f"http://{ip_port}"
                    logger.info(f"Successfully fetched dynamic proxy from Croxy API: {actual_proxy}")
                    return actual_proxy
                else:
                    logger.warning(f"Unexpected response from Croxy API: {resp.text}")
            else:
                logger.warning(f"Failed to fetch proxy from Croxy API, status: {resp.status_code}")
        except Exception as e:
            logger.error(f"Error fetching dynamic proxy from Croxy API: {e}")
        return None
        
    # 2. Proxy biasa dengan rotasi session
    import urllib.parse
    import random
    import string
    try:
        parsed = urllib.parse.urlparse(proxy_url)
        if parsed.username and parsed.password:
            session_id = "".join(random.choices(string.ascii_letters + string.digits, k=10))
            username = parsed.username
            if "-session-" in username:
                base_username = username.split("-session-")[0]
                new_username = f"{base_username}-session-{session_id}"
            elif "_session_" in username:
                base_username = username.split("_session_")[0]
                new_username = f"{base_username}_session_{session_id}"
            else:
                new_username = f"{username}-session-{session_id}"
            
            netloc = f"{new_username}:{parsed.password}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urllib.parse.urlunparse((
                parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment
            ))
    except Exception as e:
        logger.error(f"Error parsing static proxy URL session: {e}")
        
    return proxy_url




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


async def check_leonardo_api_key_credits(api_key: str) -> tuple[str, int | None]:
    """
    Memeriksa status dan sisa kredit/token API Key Leonardo.ai secara async.
    Returns:
        tuple[status_str, total_tokens_or_none]
    """
    if not api_key:
        return "EXPIRED", 0
    url = "https://cloud.leonardo.ai/api/rest/v1/me"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    try:
        active_proxy = await get_rotated_proxy_url(LEONARDO_PROXY_URL)
        proxy_config = active_proxy if active_proxy else None
        
        async with httpx.AsyncClient(
            proxy=proxy_config,
            timeout=10.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
        ) as client:
            r = await client.get(url, headers=headers)
            
        if r.status_code == 200:
            try:
                payload = r.json()
                user_details = payload.get("user_details", [])
                if user_details and isinstance(user_details, list) and len(user_details) > 0:
                    details = user_details[0]
                    subscription_tokens = details.get("subscriptionTokens") or 0
                    paid_tokens = details.get("paidTokens") or 0
                    api_paid_tokens = details.get("apiPaidTokens") or 0
                    total_tokens = subscription_tokens + paid_tokens + api_paid_tokens
                    
                    status_str = f"ACTIVE ({total_tokens} credits)" if total_tokens > 0 else f"EXPIRED ({total_tokens} credits)"
                    return status_str, total_tokens
                else:
                    return "EXPIRED (no user details)", 0
            except Exception as e:
                logger.error(f"[Verifier] Failed to parse Leonardo API response JSON: {e}")
                # Fallback ke ACTIVE jika status 200 tapi gagal parsing (dianggap memiliki token agar tidak false negative)
                return "ACTIVE (unknown credits)", 1
        elif r.status_code == 401:
            return "EXPIRED (Unauthorized)", 0
        else:
            return f"EXPIRED (Status {r.status_code})", 0
    except Exception as e:
        logger.error(f"[Verifier] API Key Check Error: {e}")
        return f"FAILED (Error: {type(e).__name__})", None


async def check_leonardo_api_key(api_key: str) -> str:
    """
    Verifikasi keaktifan API Key Leonardo.ai secara async (legacy wrapper).
    """
    if not api_key:
        return ""
    status_str, _ = await check_leonardo_api_key_credits(api_key)
    return status_str


async def verify_stripe_and_credits(payment_url: str, api_key: str | None = None) -> tuple[VerifResult, str | None]:
    """
    Memverifikasi URL Stripe dan sisa kredit API Key Leonardo (jika ada).
    Logika:
      - Cek keaktifan link Stripe via verify_url.
      - Cek sisa kredit API Key via check_leonardo_api_key_credits.
      - Jika Stripe tidak aktif (is_ok = True) ATAU sisa kredit > 0, maka OK.
      - Selain itu, GAGAL.
    
    Returns:
        tuple[VerifResult, api_key_status]
    """
    stripe_result = await verify_url(payment_url)
    
    if not api_key:
        return stripe_result, None

    api_key_status, credits = await check_leonardo_api_key_credits(api_key)
    
    # Stripe error (is_ok) ATAU kredit > 0
    if stripe_result.is_ok:
        return stripe_result, api_key_status
        
    if credits is not None and credits > 0:
        result = VerifResult(
            status=VerifStatus.OK,
            http_code=stripe_result.http_code or 200,
            message=f"Leonardo API Key Aktif ({credits} kredit) -> Pembayaran Terkonfirmasi ✅",
            url=payment_url
        )
        return result, api_key_status
        
    credits_str = str(credits) if credits is not None else "tidak diketahui"
    result = VerifResult(
        status=VerifStatus.HTTP_ERR,
        http_code=stripe_result.http_code or 401,
        message=f"Stripe masih aktif (belum dibayar) & Leonardo API Key tidak valid/habis ({credits_str} kredit) ❌",
        url=payment_url
    )
    return result, api_key_status






