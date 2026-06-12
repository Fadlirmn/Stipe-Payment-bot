import sys
import os
import asyncio

# Add project root to sys.path to resolve imports correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.services.url_verifier import verify_url

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/verify_link.py <stripe_checkout_url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Verifying Stripe URL: {url}\n")
    
    try:
        result = await verify_url(url)
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Status    : {result.emoji} {result.status.value}")
        print(f"HTTP Code : {result.http_code or '-'}")
        print(f"Message   : {result.message}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if result.is_ok:
            print("✅ VERIFICATION SUCCESSFUL (Payment Completed / Success Redirect)")
        else:
            print("❌ VERIFICATION FAILED (Unpaid / Active / Error)")
    except Exception as e:
        print(f"Error executing verification: {e}")

if __name__ == "__main__":
    asyncio.run(main())
