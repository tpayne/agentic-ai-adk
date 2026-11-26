"""Tests for SSO and regulatory compliance REST endpoints in ProcessArchitect web service."""

import json
import pytest

import cli


@pytest.fixture
def client():
    app = cli.build_web_app("process_architect", https=False)
    app.config["TESTING"] = True
    return app.test_client()


def test_get_auth_providers(client):
    resp = client.get("/auth/providers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    provider_ids = [p["id"] for p in data["providers"]]
    assert "google" in provider_ids
    assert "github" in provider_ids
    assert "microsoft" in provider_ids
    assert "outlook" in provider_ids


def test_auth_login_unconfigured_provider_returns_error(client):
    # Unconfigured provider must reject login with clear configuration requirement
    resp = client.get("/auth/login/google?json=true")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "not configured" in data["error"]


def test_auth_login_configured_provider_redirect_and_cookies(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-client-secret")

    # Requesting JSON response
    resp = client.get("/auth/login/google?json=true")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["provider"] == "google"
    assert "accounts.google.com" in data["auth_url"]
    assert "client_id=test-google-client-id" in data["auth_url"]

    # Verify anti-CSRF state cookie and PKCE verifier cookie are set
    set_cookies = resp.headers.getlist("Set-Cookie")
    cookie_str = " ".join(set_cookies)
    assert "sso_state=" in cookie_str
    assert "sso_pkce_verifier=" in cookie_str
    assert data["state"] in cookie_str


def test_auth_callback_state_verification(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Missing or invalid state should fail
    resp = client.get("/auth/callback/google?code=somecode&state=invalid_state&mode=json")
    assert resp.status_code == 400
    assert "Anti-CSRF" in resp.get_json()["error"]


def test_auth_callback_and_session_lifecycle(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    from process_toolkit.sso.providers import GoogleProvider
    monkeypatch.setattr(
        GoogleProvider,
        "exchange_code_for_token",
        lambda self, code, redirect_uri, code_verifier=None: {"access_token": "real_mock_access_token_123"},
    )
    monkeypatch.setattr(
        GoogleProvider,
        "fetch_user_profile",
        lambda self, access_token: {
            "sub": "google-user-9988",
            "name": "Tim Payne",
            "email": "tim.tpayne@gmail.com",
            "picture": "https://lh3.googleusercontent.com/test",
            "email_verified": True,
        },
    )

    login_resp = client.get("/auth/login/google?json=true")
    state = login_resp.get_json()["state"]

    # Execute callback with matching state
    client.set_cookie("sso_state", state)
    client.set_cookie("sso_pkce_verifier", "verifier123")
    resp = client.get(f"/auth/callback/google?mode=json&code=real_auth_code_xyz&state={state}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["authenticated"] is True
    token = data["token"]
    assert token.startswith("sso_")
    assert data["user"]["email"] == "tim.tpayne@gmail.com"
    assert data["user"]["name"] == "Tim Payne"

    # Query /auth/session with Bearer token
    resp_session = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert resp_session.status_code == 200
    sess_data = resp_session.get_json()
    assert sess_data["authenticated"] is True
    assert sess_data["user"]["name"] == "Tim Payne"

    # Export user data (GDPR Art. 15)
    resp_export = client.get("/auth/user/export", headers={"Authorization": f"Bearer {token}"})
    assert resp_export.status_code == 200
    export_data = resp_export.get_json()
    assert export_data["status"] == "ok"
    assert "user_profile" in export_data

    # Log out
    resp_logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp_logout.status_code == 200
    assert resp_logout.get_json()["authenticated"] is False

    # After logout, session is revoked
    resp_revoked = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert resp_revoked.get_json()["authenticated"] is False


def test_auth_login_token_direct(client, monkeypatch):
    from process_toolkit.sso.providers import GitHubProvider
    monkeypatch.setattr(
        GitHubProvider,
        "fetch_user_profile",
        lambda self, token: {
            "id": 519524,
            "login": "tpayne",
            "name": "Tim Payne",
            "email": "tim.tpayne@gmail.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/519524?v=4",
        } if token == "valid_gho_token" else {"error": "Bad credentials 401"},
    )

    # Invalid token rejected
    bad_resp = client.post("/auth/login/token", json={"provider": "github", "token": "any_crap_fake_token"})
    assert bad_resp.status_code == 401
    assert "failed" in bad_resp.get_json()["error"].lower()

    # Valid token authenticated via real API model
    good_resp = client.post("/auth/login/token", json={"provider": "github", "token": "valid_gho_token"})
    assert good_resp.status_code == 200
    good_data = good_resp.get_json()
    assert good_data["status"] == "ok"
    assert good_data["user"]["username"] == "tpayne"
    assert good_data["user"]["name"] == "Tim Payne"

    # CONFIRMED AS A REAL BUG: this used to set the SSO token cookie under
    # WEB_SESSION_COOKIE's own name ("process_architect_session") --
    # clobbering the unrelated chat-session cookie -- instead of
    # "sso_token" (what _resolve_sso_token/every other login path reads).
    set_cookies = good_resp.headers.getlist("Set-Cookie")
    cookie_str = " ".join(set_cookies)
    assert f"sso_token={good_data['token']}" in cookie_str
    assert "process_architect_session=" not in cookie_str

    # And the cookie it sets must actually be usable for /auth/session.
    session_resp = client.get("/auth/session")
    assert session_resp.get_json()["authenticated"] is True


def test_gdpr_data_erasure(client, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-gh-secret")

    from process_toolkit.sso.providers import GitHubProvider
    monkeypatch.setattr(
        GitHubProvider,
        "exchange_code_for_token",
        lambda self, code, redirect_uri, code_verifier=None: {"access_token": "real_gh_access_token"},
    )
    monkeypatch.setattr(
        GitHubProvider,
        "fetch_user_profile",
        lambda self, token: {
            "id": 519524,
            "login": "tpayne",
            "name": "Tim Payne",
            "email": "tim.tpayne@gmail.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/519524?v=4",
        },
    )

    login_resp = client.get("/auth/login/github?json=true")
    state = login_resp.get_json()["state"]

    client.set_cookie("sso_state", state)
    client.set_cookie("sso_pkce_verifier", "verifier123")
    resp = client.get(f"/auth/callback/github?mode=json&code=gh_code_123&state={state}")
    token = resp.get_json()["token"]

    # Delete data (GDPR Art. 17)
    resp_delete = client.delete("/auth/user/data", headers={"Authorization": f"Bearer {token}"})
    assert resp_delete.status_code == 200
    data = resp_delete.get_json()
    assert data["status"] == "ok"
    assert "Right to Erasure" in data["action"]

    # Confirm session is gone
    resp_session = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert resp_session.get_json()["authenticated"] is False


def test_compliance_notices(client):
    # Notice at Collection
    resp_notice = client.get("/auth/compliance/notice")
    assert resp_notice.status_code == 200
    assert "Notice at Collection" in resp_notice.get_json()["notice"]["title"]

    # Privacy Policy
    resp_privacy = client.get("/auth/compliance/privacy-policy")
    assert resp_privacy.status_code == 200
    assert "Privacy Policy" in resp_privacy.get_json()["markdown"]

    # Terms of Service
    resp_terms = client.get("/auth/compliance/terms")
    assert resp_terms.status_code == 200
    assert "Terms of Service" in resp_terms.get_json()["markdown"]


def test_serve_index_and_static_assets_exempt_from_web_api_key(monkeypatch):
    monkeypatch.setenv("WEBAPIKEY", "secret-test-key")
    app = cli.build_web_app("process_architect", https=False)
    app.config["TESTING"] = True
    c = app.test_client()

    # / and static files must succeed with 200 without Authorization header
    resp_index = c.get("/")
    assert resp_index.status_code == 200
    assert b"Process Architect" in resp_index.data

    resp_style = c.get("/style.css")
    assert resp_style.status_code == 200

    resp_app = c.get("/app.js")
    assert resp_app.status_code == 200

    # Whereas protected API endpoints like /chat require auth and return 401
    resp_chat = c.post("/chat", json={"message": "hello"})
    assert resp_chat.status_code == 401


def test_auth_callback_error_bridge_html_and_client_return(client):
    # When provider returns error and caller wants HTML (browser navigation),
    # server returns friendly bridge HTML with SSO_AUTH_ERROR and client_return redirect.
    # Uses a relative path, not an absolute cross-origin URL -- see
    # test_auth_callback_rejects_an_unrecognized_cross_origin_client_return
    # below for why an arbitrary absolute URL here must NOT be honored.
    client.set_cookie("sso_client_return", "/index.html")
    resp = client.get("/auth/callback/github?error=access_denied")
    assert resp.status_code == 400
    text = resp.get_data(as_text=True)
    assert "SSO_AUTH_ERROR" in text
    assert "access_denied" in text
    assert "/index.html" in text


def test_auth_callback_rejects_an_unrecognized_cross_origin_client_return(client):
    # CONFIRMED AS A REAL BUG: the post-login/error redirect destination
    # used to be accepted completely unvalidated -- an attacker-crafted
    # link (`/auth/login/google?redirect_uri=https://evil.example/steal`)
    # would send a victim through a completely legitimate OAuth login and
    # then hand their real, usable session token straight to evil.example
    # via the final JS redirect, since the raw cookie value was used
    # verbatim as the navigation target. An absolute URL whose origin
    # isn't in SSO_ALLOWED_REDIRECT_ORIGINS (unset here) and doesn't match
    # this request's own origin must fall back to "/".
    client.set_cookie("sso_client_return", "https://evil.example/steal")
    resp = client.get("/auth/callback/github?error=access_denied")
    text = resp.get_data(as_text=True)
    assert "evil.example" not in text


def test_auth_callback_honors_an_allowlisted_cross_origin_client_return(client, monkeypatch):
    # The legitimate case: a web client on its own, different origin can
    # still be redirected back to once its origin is explicitly trusted.
    monkeypatch.setenv("SSO_ALLOWED_REDIRECT_ORIGINS", "https://my-webclient.example")
    client.set_cookie("sso_client_return", "https://my-webclient.example/app")
    resp = client.get("/auth/callback/github?error=access_denied")
    text = resp.get_data(as_text=True)
    assert "https://my-webclient.example/app" in text


def test_auth_callback_honors_a_client_return_matching_this_servers_own_origin(client):
    # Also safe without any allowlist config: an absolute URL that just
    # spells out this same server's own origin (e.g. a deployment where
    # this backend also serves the web client via its own /index.html
    # route) -- functionally identical to a relative path.
    client.set_cookie("sso_client_return", "http://localhost/index.html")
    resp = client.get("/auth/callback/github?error=access_denied")
    text = resp.get_data(as_text=True)
    assert "http://localhost/index.html" in text


def test_auth_login_records_client_return_cookie(client, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-gh-secret")

    resp = client.get("/auth/login/github?json=true&redirect_uri=http://127.0.0.1:8081/index.html")
    assert resp.status_code == 200
    set_cookies = resp.headers.getlist("Set-Cookie")
    cookie_str = " ".join(set_cookies)
    assert "sso_client_return=" in cookie_str


def test_auth_login_unconfigured_mode_returns_configuration_error_bridge(client):
    # When provider is not configured, server returns clear error bridge requiring credentials,
    # rather than presenting a fake interactive mock login.
    resp = client.get("/auth/login/github")
    assert resp.status_code == 400
    html = resp.get_data(as_text=True)
    assert "not configured" in html
    assert "GITHUB_CLIENT_ID" in html


def test_auth_login_authorization_url_forces_reauthentication_with_prompt_login(client):
    # Google and Microsoft OAuth URLs MUST include prompt=login to force
    # the 3rd-party identity provider to require password/passkey re-authentication,
    # preventing silent auto-login bypass after user logs out.
    from process_toolkit.sso.providers import GoogleProvider, MicrosoftProvider

    google = GoogleProvider("test-client-id", "test-client-secret")
    g_url = google.get_authorization_url("http://127.0.0.1:8081/auth/callback/google", "state123")
    assert "prompt=login" in g_url

    ms = MicrosoftProvider("test-client-id", "test-client-secret")
    ms_url = ms.get_authorization_url("http://127.0.0.1:8081/auth/callback/microsoft", "state123")
    assert "prompt=login" in ms_url


def test_get_auth_providers_includes_logout_urls(client):
    resp = client.get("/auth/providers")
    assert resp.status_code == 200
    data = resp.get_json()
    for p in data["providers"]:
        assert "logout_url" in p
        assert p["logout_url"].startswith("https://")


def test_auth_configured_login_and_logout_cycle(client, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-gh-secret")

    from process_toolkit.sso.providers import GitHubProvider
    monkeypatch.setattr(
        GitHubProvider,
        "exchange_code_for_token",
        lambda self, code, redirect_uri, code_verifier=None: {"access_token": "real_gh_access_token"},
    )
    monkeypatch.setattr(
        GitHubProvider,
        "fetch_user_profile",
        lambda self, token: {
            "id": 519524,
            "login": "tpayne",
            "name": "Tim Payne",
            "email": "tim.tpayne@gmail.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/519524?v=4",
        },
    )

    login_resp = client.get("/auth/login/github?json=true")
    state = login_resp.get_json()["state"]

    client.set_cookie("sso_state", state)
    client.set_cookie("sso_pkce_verifier", "verifier123")
    resp = client.get(f"/auth/callback/github?mode=json&code=gh_code_123&state={state}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["authenticated"] is True
    assert data["user"]["name"] == "Tim Payne"
    assert data["user"]["email"] == "tim.tpayne@gmail.com"
    token = data["token"]

    # Session verification succeeds
    resp_sess = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert resp_sess.status_code == 200
    assert resp_sess.get_json()["authenticated"] is True

    # Log out
    resp_logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp_logout.status_code == 200
    assert resp_logout.get_json()["authenticated"] is False

    # Subsequent verification fails
    resp_revoked = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert resp_revoked.get_json()["authenticated"] is False


def test_auth_callback_resolves_logged_in_username_properly(client, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-gh-secret")

    from process_toolkit.sso.providers import GitHubProvider
    monkeypatch.setattr(
        GitHubProvider,
        "exchange_code_for_token",
        lambda self, code, redirect_uri, code_verifier=None: {"access_token": "real_gh_token"},
    )
    monkeypatch.setattr(
        GitHubProvider,
        "fetch_user_profile",
        lambda self, token: {
            "id": 519524,
            "login": "tpayne",
            "name": "Tim Payne",
            "email": "tpayne@users.noreply.github.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/519524?v=4",
        },
    )

    login_resp = client.get("/auth/login/github?json=true")
    state = login_resp.get_json()["state"]

    client.set_cookie("sso_state", state)
    client.set_cookie("sso_pkce_verifier", "verifier123")
    resp = client.get(f"/auth/callback/github?mode=json&code=gh_code_123&state={state}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["authenticated"] is True
    assert data["user"]["name"] == "Tim Payne"
    assert data["user"]["username"] == "tpayne"



