"""Regulatory and compliance utilities for SSO authentication under US and EU regulations.

Covers:
- EU GDPR (Regulation (EU) 2016/679) & ePrivacy Directive (Directive 2002/58/EC):
  * Article 5: Data minimization (requesting only minimal scopes: openid, profile, email)
  * Article 6 & 7: Lawful basis and unambiguous consent
  * Article 12-14: Transparent Privacy Policy and Notice at Collection
  * Article 15 & 20: Right of access and data portability (structured export)
  * Article 17: Right to erasure ('Right to be Forgotten')
  * Article 25: Privacy by Design & Default (CSRF tokens, PKCE, secure session handling)
- US State Privacy Laws (CCPA / CPRA - Cal. Civ. Code § 1798.100 et seq.):
  * Notice at Collection before/at login
  * 'Do Not Sell or Share My Personal Information' guarantee
  * Non-discrimination notice
- Security standards (NIST SP 800-63B, OWASP ASVS):
  * PKCE (RFC 7636)
  * Cryptographic CSRF state validation (RFC 6749)
  * Cookie security flags: HttpOnly, Secure, SameSite=Lax
"""

import datetime
from typing import Any, Dict, List

APP_NAME = "Process Architect"
CONTROLLER_NAME = "Process Architect Team"
CONTROLLER_CONTACT = "privacy@process-architect.local"
DPO_CONTACT = "dpo@process-architect.local"

# Minimal OAuth scopes per provider (GDPR Art. 5(1)(c) Data Minimization)
MINIMAL_SCOPES = {
    "google": ["openid", "email", "profile"],
    "github": ["read:user", "user:email"],
    "microsoft": ["openid", "profile", "email", "User.Read"],
    "outlook": ["openid", "profile", "email", "User.Read"],
}

# Cookie classifications for ePrivacy / GDPR consent
COOKIE_CATEGORIES = {
    "strictly_necessary": {
        "id": "strictly_necessary",
        "name": "Strictly Necessary Cookies",
        "required": True,
        "description": "Essential for login, anti-CSRF protection, and keeping you authenticated during active sessions. Cannot be disabled.",
        "cookies": [
            {
                "name": "process_architect_session",
                "purpose": "Stores active authenticated session identifier",
                "duration": "Session or 30 days",
                "security": "HttpOnly, SameSite=Lax",
            },
            {
                "name": "sso_state",
                "purpose": "Cryptographic anti-CSRF token used to protect OAuth 2.0 / OIDC redirects",
                "duration": "10 minutes (transient)",
                "security": "HttpOnly, SameSite=Lax",
            },
            {
                "name": "sso_pkce_verifier",
                "purpose": "PKCE (Proof Key for Code Exchange) secret to prevent authorization code interception",
                "duration": "10 minutes (transient)",
                "security": "HttpOnly, SameSite=Lax",
            },
        ],
    },
    "preferences": {
        "id": "preferences",
        "name": "Preference & Settings Cookies",
        "required": False,
        "description": "Remember your UI theme (dark/light mode), voice synthesis preferences, and default views.",
        "cookies": [
            {
                "name": "pa_theme",
                "purpose": "Stores user theme choice (light, dark, system)",
                "duration": "1 year",
                "security": "SameSite=Lax",
            },
            {
                "name": "pa_cookie_consent",
                "purpose": "Records your cookie consent choices and timestamp",
                "duration": "6 months",
                "security": "SameSite=Lax",
            },
        ],
    },
}


def get_notice_at_collection() -> Dict[str, Any]:
    """Returns the California Consumer Privacy Act (CCPA/CPRA § 1798.100)
    and EU GDPR Article 13/14 Notice at Collection."""
    return {
        "title": f"{APP_NAME} — Notice at Collection & Privacy Summary",
        "effective_date": "2026-01-01",
        "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "controller": {
            "name": CONTROLLER_NAME,
            "contact": CONTROLLER_CONTACT,
            "dpo": DPO_CONTACT,
        },
        "data_collected": [
            {
                "category": "Identifiers",
                "details": "Name, email address, unique SSO account identifier, and profile picture avatar URL.",
                "purpose": "Authentication, session verification, user personalization, and secure access control.",
                "legal_basis_gdpr": "Article 6(1)(b) — Performance of a contract / requested authentication service.",
                "retention": "Duration of active account or until data erasure is requested.",
            },
            {
                "category": "Session & Technical Metadata",
                "details": "IP address, browser user-agent, session identifiers, and authentication timestamps.",
                "purpose": "Rate limiting, anti-abuse protection, security audit logs, and session management.",
                "legal_basis_gdpr": "Article 6(1)(f) — Legitimate interest in securing infrastructure against unauthorized access.",
                "retention": "Automatically purged after session expiry or 30 days.",
            },
        ],
        "do_not_sell": {
            "statement": f"{APP_NAME} DOES NOT sell, rent, or share personal data with third parties for cross-context behavioral advertising or monetary consideration under CCPA/CPRA.",
            "status": "We do not sell personal information",
        },
        "user_rights": [
            {
                "name": "Right of Access & Data Portability",
                "description": "You can view and export a full JSON package of your stored personal profile and sessions at any time.",
                "gdpr": "Articles 15 & 20",
                "ccpa": "Cal. Civ. Code § 1798.110",
                "action": "GET /auth/user/export",
            },
            {
                "name": "Right to Erasure / Deletion",
                "description": "You can request the immediate and complete deletion of your account and all associated session data.",
                "gdpr": "Article 17 ('Right to be Forgotten')",
                "ccpa": "Cal. Civ. Code § 1798.105",
                "action": "DELETE /auth/user/data",
            },
            {
                "name": "Right to Revoke Consent / Logout",
                "description": "You can end your active session and revoke authentication tokens immediately.",
                "action": "POST /auth/logout",
            },
        ],
        "subprocessors": [
            {"name": "Google Identity", "purpose": "Single Sign-On authentication for Google accounts"},
            {"name": "GitHub OAuth", "purpose": "Single Sign-On authentication for GitHub accounts"},
            {"name": "Microsoft Identity / Entra ID", "purpose": "Single Sign-On authentication for Microsoft and Outlook accounts"},
        ],
    }


def get_privacy_policy_text() -> str:
    """Returns the comprehensive Privacy Policy in Markdown format."""
    notice = get_notice_at_collection()
    return f"""# {APP_NAME} — Privacy Policy

**Effective Date:** {notice['effective_date']}  
**Last Updated:** {notice['last_updated']}

This Privacy Policy explains how {APP_NAME} ("we", "us", or "our") collects, uses, protects, and discloses your personal data when you use our Single Sign-On (SSO) login application and related engineering services, in compliance with the **European Union General Data Protection Regulation (EU GDPR 2016/679)**, the **UK GDPR**, the **California Consumer Privacy Act (CCPA/CPRA)**, and applicable privacy laws.

---

## 1. Data Controller
- **Organization:** {CONTROLLER_NAME}
- **Contact:** {CONTROLLER_CONTACT}
- **Data Protection Officer (DPO):** {DPO_CONTACT}

---

## 2. Information We Collect
We adhere strictly to the principle of **Data Minimization (GDPR Art. 5(1)(c))**. We only collect what is strictly necessary to authenticate you:
- **Profile Identifiers:** Name, email address, unique provider user ID, and avatar picture URL retrieved via OAuth 2.0 / OpenID Connect scopes (`openid`, `profile`, `email`).
- **Security & Session Data:** Session cookies, cryptographic PKCE verifiers, CSRF state tokens, login timestamps, and client IP address.

We **do not** collect passwords, payment data, location tracking, or biometric information.

---

## 3. Lawful Basis for Processing (GDPR Article 6)
- **Contractual Necessity (Art. 6(1)(b)):** Processing your identity data is required to grant you access to your requested workspace and session artifacts.
- **Legitimate Interests (Art. 6(1)(f)):** Processing technical session data, rate limiting, and cryptographic anti-CSRF tokens is necessary to protect the service against unauthorized access and cyber threats.
- **Consent (Art. 6(1)(a)):** Non-essential preference cookies are placed solely with your explicit consent.

---

## 4. Third-Party Identity Providers (Sub-Processors)
When you choose to sign in with an external identity provider, authentication is handled securely under their respective privacy policies:
- **Google LLC:** [Google Privacy Policy](https://policies.google.com/privacy)
- **GitHub, Inc. (Microsoft):** [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement)
- **Microsoft Corporation:** [Microsoft Privacy Statement](https://privacy.microsoft.com/privacystatement)

We never share your prompt engineering queries or generated workflow artifacts with these identity providers.

---

## 5. California Privacy Rights (CCPA / CPRA)
- **We DO NOT sell or share your personal information.**
- You have the right to request disclosure of personal information collected.
- You have the right to request deletion of personal information.
- You have the right to non-discrimination for exercising your privacy rights.

---

## 6. Your Rights Under GDPR (Articles 15–22)
1. **Right of Access (Art. 15):** Request a copy of all personal data held about you.
2. **Right to Rectification (Art. 16):** Update or correct inaccurate information.
3. **Right to Erasure (Art. 17):** Request deletion of your account and associated session files ("Right to be Forgotten").
4. **Right to Data Portability (Art. 20):** Download your profile data in machine-readable JSON format via `GET /auth/user/export`.
5. **Right to Object / Withdraw Consent (Art. 7(3)):** Sign out and revoke stored tokens via `POST /auth/logout`.

To exercise these rights, use the in-app user account controls or email `{CONTROLLER_CONTACT}`.

---

## 7. Security Standards
We implement rigorous technical safeguards pursuant to **GDPR Article 32** and **NIST SP 800-63B**:
- PKCE (Proof Key for Code Exchange, RFC 7636) on all authorization requests.
- Single-use, cryptographically secure 256-bit CSRF state tokens.
- Secure cookie attributes: `HttpOnly`, `SameSite=Lax`, and `Secure` over HTTPS.
- Automatic session invalidation and idle eviction.

---

## 8. Retention Period
Personal identity records are retained only for the duration of your active account or until you invoke deletion. Inactive transient sessions are automatically purged after 30 days.
"""


def get_terms_of_service_text() -> str:
    """Returns standard Terms of Service in Markdown format."""
    return f"""# {APP_NAME} — Terms of Service

**Last Updated:** {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")}

By accessing or using {APP_NAME} ("Service") and signing in through our Single Sign-On (SSO) interfaces (Google, GitHub, Microsoft, or Outlook), you agree to be bound by these Terms of Service.

---

## 1. Acceptance of Terms
By creating an account or signing in, you confirm that you are at least 18 years old (or the legal age of majority in your jurisdiction) and agree to comply with all applicable local, national, and international laws and regulations.

## 2. Authentication & Account Responsibility
- You are responsible for maintaining the confidentiality of your credentials and linked third-party identity accounts (Google, GitHub, Microsoft).
- You agree to notify us immediately of any unauthorized use or security compromise of your session.

## 3. Acceptable Use Policy
You agree not to use the Service:
- To violate any applicable laws or intellectual property rights.
- To upload malicious code, reverse-engineer, or attempt to bypass security controls, rate limits, or access permissions.
- To transmit harassing, abusive, fraudulent, or defamatory material.

## 4. Privacy & Data Handling
Your use of the Service is governed by our [Privacy Policy](#privacy-policy). By signing in, you acknowledge and agree to the collection and processing of personal data as described therein.

## 5. Disclaimer of Warranties
THE SERVICE IS PROVIDED ON AN "AS IS" AND "AS AVAILABLE" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED.

## 6. Termination & Right of Deletion
You may terminate your account at any time by selecting "Delete My Account & Data" in your user settings or calling `DELETE /auth/user/data`.
"""
