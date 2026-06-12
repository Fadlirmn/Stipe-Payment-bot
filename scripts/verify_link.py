import sys
import os
import asyncio

# Add project root to sys.path to resolve imports correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.services.url_verifier import verify_stripe_and_credits

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/verify_link.py <stripe_checkout_url> [leonardo_api_key]")
        sys.exit(1)

    url = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Verifying Stripe URL: {url}")
    if api_key:
        masked_api = api_key[:6] + "..." + api_key[-6:] if len(api_key) > 12 else api_key
        print(f"Using Leonardo API Key: {masked_api}")
    print()
    
    try:
        result, api_status = await verify_stripe_and_credits(url, api_key)
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Stripe Result : {result.emoji} {result.status.value}")
        print(f"HTTP Code     : {result.http_code or '-'}")
        print(f"Message       : {result.message}")
        if api_key:
            print(f"API Key Status: {api_status}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if result.is_ok:
            print("✅ VERIFICATION SUCCESSFUL (OK)")
        else:
            print("❌ VERIFICATION FAILED (FAIL / HTTP_ERR)")
    except Exception as e:
        print(f"Error executing verification: {e}")

if __name__ == "__main__":
    asyncio.run(main())

