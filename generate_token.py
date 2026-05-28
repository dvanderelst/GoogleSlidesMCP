"""
One-time local helper to obtain a Google OAuth refresh token.

Prereqs:
  1. In Google Cloud Console, enable the Slides API and Drive API.
  2. Create OAuth 2.0 credentials of type "Desktop app".
  3. Download the credentials JSON and save it next to this script as
     client_secret.json (gitignored).

Then run:
    python generate_token.py

A browser window opens for consent. On success, this prints the values
you need to paste into Railway as environment variables:
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    GOOGLE_REFRESH_TOKEN
"""

import json
import secrets
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

CLIENT_SECRET_FILE = Path(__file__).parent / "client_secret.json"


def main() -> None:
    if not CLIENT_SECRET_FILE.exists():
        raise SystemExit(
            f"Missing {CLIENT_SECRET_FILE}. Download it from Google Cloud Console "
            "(OAuth 2.0 Client IDs, type 'Desktop app')."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        raise SystemExit(
            "No refresh token returned. Revoke the app at "
            "https://myaccount.google.com/permissions and re-run."
        )

    with open(CLIENT_SECRET_FILE) as f:
        secret = json.load(f)
    installed = secret.get("installed") or secret.get("web") or {}

    mcp_auth_token = secrets.token_hex(32)

    print()
    print("Paste these into Railway as environment variables:")
    print()
    print(f"GOOGLE_CLIENT_ID={installed.get('client_id', '')}")
    print(f"GOOGLE_CLIENT_SECRET={installed.get('client_secret', '')}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"MCP_AUTH_TOKEN={mcp_auth_token}")
    print()
    print("Save MCP_AUTH_TOKEN somewhere safe — you'll append it to your")
    print("Claude MCP URL as `?token=<MCP_AUTH_TOKEN>`. Re-running this")
    print("script mints a fresh one; update Railway and your Claude config")
    print("together if you do.")
    print()


if __name__ == "__main__":
    main()
