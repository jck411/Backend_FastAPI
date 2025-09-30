#!/usr/bin/env python3
"""
Setup and start ngrok tunnel for FastAPI backend.
This script will help you configure ngrok and start the tunnel.
"""

import sys
from pathlib import Path

from pyngrok import conf, ngrok


def setup_ngrok_authtoken():
    """Prompt user for ngrok authtoken and configure it."""
    print("📋 To get your ngrok authtoken:")
    print("1. Go to https://ngrok.com/")
    print("2. Sign up or log in (free tier is fine)")
    print("3. Go to https://dashboard.ngrok.com/get-started/your-authtoken")
    print("4. Copy your authtoken")
    print()

    authtoken = input("🔑 Enter your ngrok authtoken: ").strip()
    if not authtoken:
        print("❌ No authtoken provided!")
        return False

    try:
        # Set the authtoken
        conf.get_default().auth_token = authtoken
        print("✅ Authtoken configured successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to configure authtoken: {e}")
        return False


def start_tunnel(port=8000):
    """Start ngrok tunnel and return the public HTTPS URL."""
    try:
        print(f"🚀 Starting ngrok tunnel for localhost:{port}...")

        # Start the tunnel
        tunnel = ngrok.connect(str(port), "http")
        public_url = tunnel.public_url

        # Convert to HTTPS if it's HTTP
        if public_url and public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://")

        print("✅ Tunnel started successfully!")
        print(f"📡 Public URL: {public_url}")
        print(f"🔗 Local URL: http://localhost:{port}")
        print()

        return public_url

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
    """Main function to set up ngrok tunnel."""
    print("🔧 NgRok Setup for FastAPI Backend")
    print("=" * 40)

    # Check if authtoken is already configured
    try:
        # Try to start a quick tunnel to test auth
        test_tunnel = ngrok.connect("8001", "http")
        if test_tunnel.public_url:
            ngrok.disconnect(test_tunnel.public_url)
        print("✅ NgRok authtoken is already configured!")
    except Exception:
        print("🔑 NgRok authtoken not configured.")
        if not setup_ngrok_authtoken():
            sys.exit(1)

    # Start the tunnel
    public_url = start_tunnel(8000)
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
            ngrok.disconnect(public_url)
            print("✅ Tunnel stopped.")


if __name__ == "__main__":
    main()
