#!/usr/bin/env python3
"""Test script to verify Deepgram API key and token generation."""

import asyncio
import httpx
from dotenv import load_dotenv
import os

load_dotenv()

async def test_deepgram_direct():
    """Test Deepgram API directly."""
    api_key = os.getenv("DEEPGRAM_API_KEY")

    if not api_key:
        print("❌ DEEPGRAM_API_KEY not found in .env")
        return False

    print(f"✓ API Key found: {api_key[:10]}...{api_key[-10:]}")

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    json_data = {"ttl_seconds": 30}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("→ Requesting temporary token from Deepgram...")
            resp = await client.post(
                "https://api.deepgram.com/v1/auth/grant",
                headers=headers,
                json=json_data
            )

            print(f"← Response status: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                expires_in = data.get("expires_in")
                print(f"✓ Token received successfully")
                print(f"  Token: {token[:20]}...")
                print(f"  Expires in: {expires_in} seconds")
                return True
            else:
                print(f"❌ Failed with status {resp.status_code}")
                print(f"  Headers: {dict(resp.headers)}")
                try:
                    body = resp.json()
                    print(f"  Body: {body}")
                except Exception:
                    print(f"  Body: {resp.text}")
                return False

    except httpx.TimeoutException as e:
        print(f"❌ Timeout error: {e}")
        return False
    except httpx.RequestError as e:
        print(f"❌ Network error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_local_endpoint():
    """Test the local FastAPI endpoint."""
    print("\n" + "="*60)
    print("Testing local FastAPI endpoint...")
    print("="*60)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("http://localhost:8000/api/stt/deepgram/token")

            print(f"← Response status: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                print(f"✓ Success!")
                print(f"  Token: {data['access_token'][:20]}...")
                if data.get('expires_in'):
                    print(f"  Expires in: {data['expires_in']} seconds")
                return True
            else:
                print(f"❌ Failed with status {resp.status_code}")
                try:
                    body = resp.json()
                    print(f"  Error: {body}")
                except Exception:
                    print(f"  Body: {resp.text}")
                return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def main():
    print("="*60)
    print("Deepgram Integration Test")
    print("="*60)

    direct_ok = await test_deepgram_direct()

    if direct_ok:
        endpoint_ok = await test_local_endpoint()

        if direct_ok and endpoint_ok:
            print("\n" + "="*60)
            print("✓ All tests passed!")
            print("="*60)
        elif direct_ok:
            print("\n" + "="*60)
            print("⚠ Direct API works but endpoint fails")
            print("  Check if FastAPI server is running on :8000")
            print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ Direct API test failed")
        print("  Check your DEEPGRAM_API_KEY in .env")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
