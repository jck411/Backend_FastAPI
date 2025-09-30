#!/usr/bin/env python3
"""
Simple ngrok tunnel starter for FastAPI backend.
Run this script and follow the prompts to set up ngrok.
"""

import sys
from pathlib import Path

from pyngrok import ngrok
from pyngrok.conf import PyngrokConfig


def start_tunnel_with_authtoken():
    """Start ngrok tunnel with user-provided authtoken."""
    print("🔧 NgRok Tunnel Setup for FastAPI Backend")
    print("=" * 45)
    print()
    print("📋 To get your ngrok authtoken:")
    print("1. Go to https://ngrok.com/")
    print("2. Sign up or log in (free tier is fine)")
    print("3. Go to https://dashboard.ngrok.com/get-started/your-authtoken")
    print("4. Copy your authtoken")
    print()

    authtoken = input("🔑 Enter your ngrok authtoken: ").strip()
    if not authtoken:
        print("❌ No authtoken provided!")
        return None

    try:
        # Configure pyngrok with the authtoken
        config = PyngrokConfig(auth_token=authtoken)

        print("🚀 Starting ngrok tunnel for localhost:8000...")

        # Start the tunnel
        tunnel = ngrok.connect("8000", pyngrok_config=config)
        public_url = tunnel.public_url
        https_url = (
            public_url.replace("http://", "https://")
            if public_url and public_url.startswith("http://")
            else public_url
        )

        print("✅ Tunnel started successfully!")
        print(f"📡 Public HTTPS URL: {https_url}")
        print("🔗 Local URL: http://localhost:8000")
        print()

        return https_url

    except Exception as e:
        print(f"❌ Failed to start tunnel: {e}")
        return None


def update_env_file(public_url):
    """Update .env file with the ngrok URL."""
    env_file = Path(".env")

    if not env_file.exists():
        print("❌ .env file not found!")
        return False

    try:
        # Read current .env content
        content = env_file.read_text()
        lines = content.splitlines()

        # Check if ATTACHMENTS_PUBLIC_BASE_URL already exists
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("ATTACHMENTS_PUBLIC_BASE_URL="):
                lines[i] = f"ATTACHMENTS_PUBLIC_BASE_URL={public_url}"
                updated = True
                break

        # If not found, add it
        if not updated:
            lines.append(f"ATTACHMENTS_PUBLIC_BASE_URL={public_url}")

        # Write back to file
        env_file.write_text("\n".join(lines) + "\n")

        print(f"✅ Updated .env file with ATTACHMENTS_PUBLIC_BASE_URL={public_url}")
        return True

    except Exception as e:
        print(f"❌ Failed to update .env file: {e}")
        return False


def main():
    """Main function."""
    # Start the tunnel
    public_url = start_tunnel_with_authtoken()
    if not public_url:
        sys.exit(1)

    # Update .env file
    if update_env_file(public_url):
        print()
        print("🎉 Setup complete!")
        print("📝 Next steps:")
        print("1. Restart your FastAPI backend to reload the configuration")
        print(
            "2. Test uploading an image - it should now have a delivery_url with ngrok hostname"
        )
        print("3. Keep this script running to maintain the tunnel")
        print()
        print("⚠️  Important: Keep this terminal open to maintain the tunnel!")
        print("🛑 Press Ctrl+C to stop the tunnel")

        try:
            print("⏳ Tunnel is running... (press Ctrl+C to stop)")
            while True:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping tunnel...")
            ngrok.kill()
            print("✅ Tunnel stopped.")


if __name__ == "__main__":
    main()
