"""OAuth 2.0 / OpenID Connect provider definitions and client handlers for SSO.

Supported providers:
- Google (OpenID Connect / Google Identity)
- GitHub (OAuth 2.0)
- Microsoft (Microsoft Identity Platform / Entra ID v2.0)
- Outlook (Microsoft Identity for Personal / Office 365 accounts)

Complies with:
- RFC 7636 (Proof Key for Code Exchange by OAuth Public Clients - PKCE)
- RFC 6749 (The OAuth 2.0 Authorization Framework)
- OpenID Connect Core 1.0
- Data Minimization (GDPR Art. 5(1)(c)) requesting only minimal identity scopes
"""

import base64
import hashlib
import json
import os
import secrets
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from process_toolkit.sso.compliance import MINIMAL_SCOPES


def generate_pkce_pair() -> Tuple[str, str]:
    """Generates a high-entropy PKCE code_verifier and code_challenge using SHA-256.

    Returns:
        (code_verifier, code_challenge)
    """
    # 32 random bytes -> 43 base64url characters (RFC 7636 Section 4.1 specifies 43-128 chars)
    verifier_bytes = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).decode("ascii").rstrip("=")

    # code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    return code_verifier, code_challenge


def generate_oauth_state() -> str:
    """Generates a cryptographically secure random state parameter for anti-CSRF protection."""
    return secrets.token_urlsafe(32)


class BaseSSOProvider:
    """Abstract base class for SSO identity providers."""

    provider_id: str
    display_name: str
    brand_color: str
    icon_type: str
    auth_url: str
    token_url: str
    userinfo_url: str

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""

    @property
    def is_configured(self) -> bool:
        """Returns True if live production OAuth credentials are configured."""
        return bool(self.client_id and self.client_secret)

    @property
    def scopes(self) -> List[str]:
        return MINIMAL_SCOPES.get(self.provider_id, ["openid", "email", "profile"])

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: Optional[str] = None,
        scope: Optional[List[str]] = None,
    ) -> str:
        """Constructs the real upstream OAuth 2.0 / OIDC authorization URL for this provider."""
        scopes = scope or self.scopes
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes) if self.provider_id != "github" else ",".join(scopes),
            "state": state,
        }
        if self.provider_id in ("google", "microsoft", "outlook"):
            params["prompt"] = "login"
        elif self.provider_id == "github":
            params["prompt"] = "consent"
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def verify_token(self, access_token: str) -> Dict[str, Any]:
        """Directly verifies an access token against the provider's real userinfo API and returns normalized profile."""
        raw = self.fetch_user_profile(access_token)
        if "error" in raw:
            return {"error": raw["error"]}
        return self.normalize_user_profile(raw)

    def exchange_code_for_token(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchanges authorization code for access token via token endpoint."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            self.token_url,
            data=encoded_data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "ProcessArchitect-SSO/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            return {"error": f"Token exchange failed: {str(e)}"}

    def fetch_user_profile(self, access_token: str) -> Dict[str, Any]:
        """Fetches the user's standardized profile from the provider's userinfo API."""
        req = urllib.request.Request(
            self.userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "ProcessArchitect-SSO/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            return {"error": f"Failed to fetch profile: {str(e)}"}

    def normalize_user_profile(self, raw_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Maps provider-specific response to standardized user model."""
        raise NotImplementedError


class GoogleProvider(BaseSSOProvider):
    provider_id = "google"
    display_name = "Google"
    brand_color = "#ffffff"
    icon_type = "google"
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
    logout_url = "https://accounts.google.com/Logout"

    def normalize_user_profile(self, raw_profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "id": str(raw_profile.get("sub", "")),
            "email": raw_profile.get("email", ""),
            "name": raw_profile.get("name", raw_profile.get("email", "Google User")),
            "first_name": raw_profile.get("given_name", ""),
            "last_name": raw_profile.get("family_name", ""),
            "avatar_url": raw_profile.get("picture", ""),
            "email_verified": bool(raw_profile.get("email_verified", False)),
        }


class GitHubProvider(BaseSSOProvider):
    provider_id = "github"
    display_name = "GitHub"
    brand_color = "#24292e"
    icon_type = "github"
    auth_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    userinfo_url = "https://api.github.com/user"
    logout_url = "https://github.com/logout"

    def fetch_user_profile(self, access_token: str) -> Dict[str, Any]:
        base_profile = super().fetch_user_profile(access_token)
        if "error" in base_profile:
            return base_profile

        # If primary email is hidden, query /user/emails
        if not base_profile.get("email"):
            emails_req = urllib.request.Request(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "User-Agent": "ProcessArchitect-SSO/1.0",
                },
            )
            try:
                with urllib.request.urlopen(emails_req, timeout=10) as resp:
                    emails = json.loads(resp.read().decode("utf-8"))
                    for em in emails:
                        if em.get("primary") and em.get("verified"):
                            base_profile["email"] = em.get("email")
                            break
                        if not base_profile.get("email") and em.get("email"):
                            base_profile["email"] = em.get("email")
            except Exception:
                pass
        return base_profile

    def normalize_user_profile(self, raw_profile: Dict[str, Any]) -> Dict[str, Any]:
        login = raw_profile.get("login", "")
        name = raw_profile.get("name") or login or "GitHub User"
        return {
            "provider": self.provider_id,
            "id": str(raw_profile.get("id", "")),
            "email": raw_profile.get("email") or f"{login}@users.noreply.github.com",
            "name": name,
            "username": login,
            "avatar_url": raw_profile.get("avatar_url", ""),
            "email_verified": True,
        }


class MicrosoftProvider(BaseSSOProvider):
    provider_id = "microsoft"
    display_name = "Microsoft"
    brand_color = "#2f2f2f"
    icon_type = "microsoft"
    auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    userinfo_url = "https://graph.microsoftonline.com/v1.0/me"
    logout_url = "https://login.microsoftonline.com/common/oauth2/v2.0/logout"

    def normalize_user_profile(self, raw_profile: Dict[str, Any]) -> Dict[str, Any]:
        email = raw_profile.get("mail") or raw_profile.get("userPrincipalName", "")
        name = raw_profile.get("displayName", email or "Microsoft User")
        return {
            "provider": self.provider_id,
            "id": str(raw_profile.get("id", "")),
            "email": email,
            "name": name,
            "first_name": raw_profile.get("givenName", ""),
            "last_name": raw_profile.get("surname", ""),
            "avatar_url": f"https://api.dicebear.com/7.x/initials/svg?seed={urllib.parse.quote(name)}&backgroundColor=00a4ef",
            "email_verified": bool(email),
        }


class OutlookProvider(BaseSSOProvider):
    provider_id = "outlook"
    display_name = "Outlook"
    brand_color = "#0078d4"
    icon_type = "outlook"
    auth_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    userinfo_url = "https://graph.microsoftonline.com/v1.0/me"
    logout_url = "https://login.microsoftonline.com/common/oauth2/v2.0/logout"

    def normalize_user_profile(self, raw_profile: Dict[str, Any]) -> Dict[str, Any]:
        email = raw_profile.get("mail") or raw_profile.get("userPrincipalName", "")
        name = raw_profile.get("displayName", email or "Outlook User")
        return {
            "provider": self.provider_id,
            "id": str(raw_profile.get("id", "")),
            "email": email,
            "name": name,
            "first_name": raw_profile.get("givenName", ""),
            "last_name": raw_profile.get("surname", ""),
            "avatar_url": f"https://api.dicebear.com/7.x/initials/svg?seed={urllib.parse.quote(name)}&backgroundColor=0078d4",
            "email_verified": bool(email),
        }


def _load_env_files() -> None:
    """Attempts to load environment variables from local .env files if present."""
    try:
        from dotenv import load_dotenv
        for candidate in [
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../samples/Neurosan/ProcessEngineering/.env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../samples/GCP/ProcessEngineering/.env"),
        ]:
            if os.path.isfile(candidate):
                load_dotenv(candidate)
    except Exception:
        pass


def get_configured_providers() -> Dict[str, BaseSSOProvider]:
    """Returns a dictionary of all supported providers initialized from environment variables."""
    _load_env_files()

    # Google
    g_id = os.environ.get("GOOGLE_CLIENT_ID")
    g_sec = os.environ.get("GOOGLE_CLIENT_SECRET")
    google = GoogleProvider(g_id, g_sec)

    # GitHub
    gh_id = os.environ.get("GITHUB_CLIENT_ID")
    gh_sec = os.environ.get("GITHUB_CLIENT_SECRET")
    github = GitHubProvider(gh_id, gh_sec)

    # Microsoft / Azure
    ms_id = os.environ.get("MICROSOFT_CLIENT_ID") or os.environ.get("AZURE_CLIENT_ID")
    ms_sec = os.environ.get("MICROSOFT_CLIENT_SECRET") or os.environ.get("AZURE_CLIENT_SECRET")
    microsoft = MicrosoftProvider(ms_id, ms_sec)

    # Outlook (can use OUTLOOK_* or fallback to Microsoft)
    out_id = os.environ.get("OUTLOOK_CLIENT_ID") or ms_id
    out_sec = os.environ.get("OUTLOOK_CLIENT_SECRET") or ms_sec
    outlook = OutlookProvider(out_id, out_sec)

    return {
        "google": google,
        "github": github,
        "microsoft": microsoft,
        "outlook": outlook,
    }


def get_providers_metadata() -> List[Dict[str, Any]]:
    """Returns public UI metadata for all providers, indicating whether live
    OAuth credentials are configured."""
    providers = get_configured_providers()
    meta = []
    for pid, prov in providers.items():
        meta.append({
            "id": pid,
            "display_name": prov.display_name,
            "brand_color": prov.brand_color,
            "icon_type": prov.icon_type,
            "configured": prov.is_configured,
            "scopes": prov.scopes,
            "logout_url": getattr(prov, "logout_url", None),
        })
    return meta
