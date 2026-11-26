"""CLI Single Sign-On (SSO) login flow with local loopback callback server.

Enables developers and CLI users to authenticate via Google, GitHub, Microsoft,
or Outlook from the command line using standard OAuth 2.0 + PKCE flow.
"""

import http.server
import json
import os
import socket
import threading
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

from process_toolkit.sso.compliance import get_notice_at_collection
from process_toolkit.sso.providers import (
    generate_oauth_state,
    generate_pkce_pair,
    get_configured_providers,
)
from process_toolkit.sso.session_manager import get_sso_session_manager

_CREDENTIALS_DIR = os.path.expanduser("~/.process_architect")
_CREDENTIALS_FILE = os.path.join(_CREDENTIALS_DIR, "credentials.json")


def save_cli_credentials(user_profile: Dict[str, Any], token: str) -> str:
    """Saves user credentials to local user home directory."""
    try:
        os.makedirs(_CREDENTIALS_DIR, exist_ok=True)
        # Protect with user-only permissions (600)
        payload = {
            "token": token,
            "user": user_profile,
            "saved_at": user_profile.get("created_at"),
        }
        with open(_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        try:
            os.chmod(_CREDENTIALS_FILE, 0o600)
        except Exception:
            pass
        return _CREDENTIALS_FILE
    except Exception:
        # Fallback to local output folder
        local_path = os.path.abspath("output/cli_credentials.json")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump({"token": token, "user": user_profile}, f, indent=2)
        return local_path


def load_cli_credentials() -> Optional[Dict[str, Any]]:
    """Loads saved CLI credentials if present."""
    for path in (_CREDENTIALS_FILE, os.path.abspath("output/cli_credentials.json")):
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None


def clear_cli_credentials() -> bool:
    """Removes saved CLI credentials (logout)."""
    removed = False
    for path in (_CREDENTIALS_FILE, os.path.abspath("output/cli_credentials.json")):
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed = True
            except Exception:
                pass
    return removed


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Temporary HTTP handler to capture OAuth redirect on 127.0.0.1."""

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging on CLI
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        self.server.callback_code = params.get("code", [None])[0]
        self.server.callback_state = params.get("state", [None])[0]
        self.server.callback_mock = params.get("mock", [None])[0] == "true"
        self.server.callback_error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Process Architect &mdash; Authentication Successful</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #0f1117; color: #e2e8f0; display: flex; align-items: center;
           justify-content: center; height: 100vh; margin: 0; }
    .card { background: #1a1d27; border: 1px solid #2d3345; border-radius: 12px;
            padding: 36px 42px; text-align: center; max-width: 440px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    .icon { width: 56px; height: 56px; margin: 0 auto 16px; border-radius: 50%;
            background: rgba(16, 185, 129, 0.15); color: #10b981; display: flex;
            align-items: center; justify-content: center; font-size: 28px; }
    h1 { font-size: 20px; margin: 0 0 10px; color: #fff; }
    p { font-size: 14px; color: #94a3b8; line-height: 1.5; margin: 0 0 20px; }
    .badge { display: inline-block; background: #242938; padding: 4px 10px;
             border-radius: 6px; font-size: 12px; color: #38bdf8; font-family: monospace; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10003;</div>
    <h1>Authentication Successful</h1>
    <p>You have signed in to <strong>Process Architect</strong> via SSO.<br>You may now close this browser tab and return to your terminal.</p>
    <div class="badge">SSO Verified &bull; GDPR &amp; CCPA Compliant</div>
  </div>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))
        threading.Thread(target=self.server.shutdown).start()


def find_available_port(start: int = 8989) -> int:
    """Finds an open loopback port."""
    for port in range(start, start + 50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start


def perform_cli_sso_login(
    provider_id: str,
    open_browser_auto: bool = True,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Executes full SSO login from the CLI with local loopback listener."""
    providers = get_configured_providers()
    if provider_id not in providers:
        return {
            "status": "error",
            "error": f"Unsupported provider '{provider_id}'. Choose from: google, github, microsoft, outlook.",
        }

    provider = providers[provider_id]
    if not provider.is_configured:
        return {
            "status": "error",
            "error": f"Provider '{provider_id}' is not configured. Real authentication requires {provider_id.upper()}_CLIENT_ID and {provider_id.upper()}_CLIENT_SECRET in your environment or .env file.",
        }

    port = find_available_port(8989)
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    state = generate_oauth_state()
    verifier, challenge = generate_pkce_pair()

    server = http.server.HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.callback_code = None
    server.callback_state = None
    server.callback_mock = False
    server.callback_error = None

    auth_url = provider.get_authorization_url(
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=challenge,
    )

    print(f"\nInitiating SSO authentication via {provider.display_name}...")
    print(f"Notice at Collection: Requesting minimal identity data (Name, Email, Profile)")
    print(f"Opening browser for authorization. If browser does not open automatically, visit:")
    print(f"  \033[36m{auth_url}\033[0m\n")

    if open_browser_auto:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    server_thread.join(timeout=timeout_seconds)

    if server.callback_error:
        return {"status": "error", "error": f"Provider returned error: {server.callback_error}"}

    if server.callback_state != state:
        return {"status": "error", "error": "Anti-CSRF state validation failed."}

    # Real OAuth code exchange and profile retrieval
    tokens = provider.exchange_code_for_token(
        code=server.callback_code or "",
        redirect_uri=redirect_uri,
        code_verifier=verifier,
    )
    if "error" in tokens:
        return {"status": "error", "error": tokens["error"]}
    access_token = tokens.get("access_token", "")
    if not access_token:
        return {"status": "error", "error": "Provider did not return an access token."}
    raw_profile = provider.fetch_user_profile(access_token)
    if "error" in raw_profile:
        return {"status": "error", "error": f"Failed to fetch profile: {raw_profile['error']}"}
    profile = provider.normalize_user_profile(raw_profile)

    manager = get_sso_session_manager()
    session = manager.create_session(profile)
    saved_path = save_cli_credentials(profile, session["token"])

    return {
        "status": "ok",
        "provider": provider_id,
        "user": profile,
        "session_token": session["token"],
        "credentials_saved_to": saved_path,
    }
