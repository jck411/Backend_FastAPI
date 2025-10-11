#!/usr/bin/env python3
"""Quick script to authorize and test Google Calendar MCP integration."""

import sys
import webbrowser

import requests

BASE_URL = "http://localhost:8000"
USER_EMAIL = "jck411@gmail.com"


def check_auth_status():
    """Check if user is authorized."""
    response = requests.get(f"{BASE_URL}/api/google-auth/status/{USER_EMAIL}")
    return response.json().get("authorized", False)


def get_auth_url():
    """Get Google authorization URL."""
    response = requests.post(
        f"{BASE_URL}/api/google-auth/authorize", json={"user_email": USER_EMAIL}
    )
    return response.json()["auth_url"]


def test_calendar():
    """Test calendar_get_events tool."""
    response = requests.get(f"{BASE_URL}/api/mcp/servers/")
    servers = response.json()["servers"]

    # Find custom-calendar server
    cal_server = next((s for s in servers if s["id"] == "custom-calendar"), None)
    if not cal_server:
        print("❌ Custom calendar server not found!")
        return False

    print(f"✅ Custom calendar server found with {cal_server['tool_count']} tools")
    print(f"   Connected: {cal_server['connected']}")
    return True


def main():
    print("🔍 Checking Google Calendar authorization...")

    if check_auth_status():
        print("✅ Already authorized!")
    else:
        print("❌ Not authorized. Opening browser for authorization...")
        auth_url = get_auth_url()
        print(f"\n📋 Authorization URL:\n{auth_url}\n")

        # Open browser
        webbrowser.open(auth_url)

        print("⏳ Waiting for you to authorize in the browser...")
        print("   After authorizing, you'll be redirected back to localhost.")
        print("   Press Enter after completing authorization...")
        input()

        # Check again
        if check_auth_status():
            print("✅ Authorization successful!")
        else:
            print("❌ Authorization failed. Please try again.")
            sys.exit(1)

    print("\n🧪 Testing calendar MCP server...")
    if test_calendar():
        print("\n🎉 Calendar MCP server is ready!")
        print("\nYou can now:")
        print("  - Ask about your calendar events")
        print("  - Create new events")
        print("  - Update or delete events")
    else:
        print("\n❌ Calendar MCP server test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
