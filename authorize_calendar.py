#!/usr/bin/env python3
"""Interactive script to authorize Google Calendar access for a user."""

import sys
import webbrowser
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from backend.config import get_settings
from backend.services.google_auth.auth import (
    authorize_user,
    get_credentials,
)


def main():
    """Run the authorization flow."""
    print("🔐 Google Calendar Authorization\n")

    # Get user email
    user_email = input("Enter your email address (default: jck411@gmail.com): ").strip()
    if not user_email:
        user_email = "jck411@gmail.com"

    # Check if already authorized
    existing_creds = get_credentials(user_email)
    if existing_creds:
        print(f"\n✅ {user_email} is already authorized!")
        reauth = input("Do you want to re-authorize? (y/N): ").strip().lower()
        if reauth != "y":
            print("Authorization cancelled.")
            return

    settings = get_settings()
    redirect_uri = settings.google_oauth_redirect_uri

    print(f"\n📝 Using redirect URI: {redirect_uri}")
    print(f"📝 Frontend URL: {settings.frontend_url}")

    # Generate authorization URL
    try:
        auth_url = authorize_user(user_email, redirect_uri)
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Make sure you have downloaded the OAuth client credentials")
        print("   from Google Cloud Console and placed them in the credentials/")
        print("   directory as 'client_secret_*.json'")
        return
    except Exception as e:
        print(f"\n❌ Error generating authorization URL: {e}")
        return

    print("\n🌐 Opening browser for authorization...")
    print("\nIf the browser doesn't open automatically, visit this URL:")
    print(f"\n{auth_url}\n")

    # Open browser
    try:
        webbrowser.open(auth_url)
        print("✅ Browser opened!")
    except Exception as e:
        print(f"⚠️  Could not open browser automatically: {e}")
        print("Please copy and paste the URL above into your browser.")

    print("\n📌 Next steps:")
    print("   1. Authorize the application in your browser")
    print("   2. You'll be redirected back to the application")
    print("   3. The credentials will be saved automatically")
    print("\n✨ After authorization, your calendar tools will work!")


if __name__ == "__main__":
    main()
