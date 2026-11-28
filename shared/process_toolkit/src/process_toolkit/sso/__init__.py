"""Single Sign-On (SSO) authentication and US/EU regulatory compliance package.

Supports:
- Google (OpenID Connect)
- GitHub (OAuth 2.0)
- Microsoft (Microsoft Identity Platform / Entra ID v2.0)
- Outlook (Personal and Office 365 Microsoft accounts)
- GDPR (Articles 5, 6, 7, 12, 13, 14, 15, 17, 20, 25) & ePrivacy Directive
- CCPA / CPRA Notice at Collection and 'Do Not Sell' provisions
- PKCE (RFC 7636) & cryptographic anti-CSRF protection
"""

from process_toolkit.sso.compliance import (
    COOKIE_CATEGORIES,
    MINIMAL_SCOPES,
    get_notice_at_collection,
    get_privacy_policy_text,
    get_terms_of_service_text,
)
from process_toolkit.sso.providers import (
    BaseSSOProvider,
    GitHubProvider,
    GoogleProvider,
    MicrosoftProvider,
    OutlookProvider,
    generate_oauth_state,
    generate_pkce_pair,
    get_configured_providers,
    get_providers_metadata,
)
from process_toolkit.sso.session_manager import (
    SSOSessionManager,
    get_sso_session_manager,
)
from process_toolkit.sso.cli_auth import (
    clear_cli_credentials,
    load_cli_credentials,
    perform_cli_sso_login,
    save_cli_credentials,
)

__all__ = [
    "COOKIE_CATEGORIES",
    "MINIMAL_SCOPES",
    "get_notice_at_collection",
    "get_privacy_policy_text",
    "get_terms_of_service_text",
    "BaseSSOProvider",
    "GitHubProvider",
    "GoogleProvider",
    "MicrosoftProvider",
    "OutlookProvider",
    "generate_oauth_state",
    "generate_pkce_pair",
    "get_configured_providers",
    "get_providers_metadata",
    "SSOSessionManager",
    "get_sso_session_manager",
    "clear_cli_credentials",
    "load_cli_credentials",
    "perform_cli_sso_login",
    "save_cli_credentials",
]
