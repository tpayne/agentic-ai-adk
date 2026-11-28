"""Session and identity management for SSO users with GDPR and CCPA compliance actions.

Implements:
- Secure token generation and lifecycle management
- Article 15 (GDPR) / CCPA: Data Export in machine-readable JSON
- Article 17 (GDPR) / CCPA: Right to Erasure (complete account and session purge)
- Thread-safe storage with disk persistence
"""

import datetime
import json
import os
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Set

from process_toolkit import paths
from process_toolkit.session_purge import purge_session

_DEFAULT_SESSION_TTL_SECONDS = 30 * 86400  # 30 days


class SSOSessionManager:
    """Thread-safe manager for SSO user authentication sessions."""

    def __init__(self, persistence_file: Optional[str] = None):
        self._lock = threading.Lock()
        self.persistence_file = persistence_file or os.path.join(paths.output_dir(), "sso_sessions.json")
        # token -> session_dict
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # user_id -> set of tokens
        self._user_tokens: Dict[str, Set[str]] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        try:
            if os.path.isfile(self.persistence_file):
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now = time.time()
                    for token, sess in data.get("sessions", {}).items():
                        if sess.get("expires_at", 0) > now:
                            self._sessions[token] = sess
                            uid = sess.get("user", {}).get("id")
                            if uid:
                                if uid not in self._user_tokens:
                                    self._user_tokens[uid] = set()
                                self._user_tokens[uid].add(token)
        except Exception:
            pass

    def _save_to_disk(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.persistence_file)), exist_ok=True)
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump({"sessions": self._sessions}, f, indent=2)
            # Every live session's own bearer token is a password-equivalent
            # credential -- this file must never be left world-readable.
            # cli_auth.py's own credentials.json already does this; this
            # file, holding every user's tokens at once, needed it too.
            try:
                os.chmod(self.persistence_file, 0o600)
            except Exception:
                pass
        except Exception:
            pass

    def create_session(
        self,
        user_profile: Dict[str, Any],
        ttl_seconds: int = _DEFAULT_SESSION_TTL_SECONDS,
    ) -> Dict[str, Any]:
        """Creates an authenticated session for the given user profile."""
        token = f"sso_{secrets.token_hex(24)}"
        now = time.time()
        expires_at = now + ttl_seconds
        iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        session_record = {
            "token": token,
            "created_at": iso_now,
            "created_timestamp": now,
            "last_accessed": now,
            "expires_at": expires_at,
            "user": user_profile,
            "linked_chat_sessions": [],
        }

        with self._lock:
            self._sessions[token] = session_record
            uid = user_profile.get("id")
            if uid:
                if uid not in self._user_tokens:
                    self._user_tokens[uid] = set()
                self._user_tokens[uid].add(token)
            self._save_to_disk()

        return session_record

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Retrieves and touches an active session by token."""
        if not token:
            return None
        with self._lock:
            sess = self._sessions.get(token)
            if not sess:
                return None
            now = time.time()
            if sess.get("expires_at", 0) <= now:
                # Expired
                self._sessions.pop(token, None)
                uid = sess.get("user", {}).get("id")
                if uid and uid in self._user_tokens:
                    self._user_tokens[uid].discard(token)
                self._save_to_disk()
                return None
            sess["last_accessed"] = now
            return dict(sess)

    def link_chat_session(self, token: str, chat_session_id: str) -> None:
        """Associates a chat session with this user for audit and deletion tracking."""
        if not token or not chat_session_id:
            return
        with self._lock:
            sess = self._sessions.get(token)
            if sess:
                linked = sess.setdefault("linked_chat_sessions", [])
                if chat_session_id not in linked:
                    linked.append(chat_session_id)
                    self._save_to_disk()

    def revoke_session(self, token: str) -> bool:
        """Revokes an active session token (Sign Out)."""
        if not token:
            return False
        with self._lock:
            sess = self._sessions.pop(token, None)
            if sess:
                uid = sess.get("user", {}).get("id")
                if uid and uid in self._user_tokens:
                    self._user_tokens[uid].discard(token)
                self._save_to_disk()
                return True
            return False

    def export_user_data(self, token: str) -> Dict[str, Any]:
        """GDPR Article 15 & 20 Data Portability Export.

        Returns all user profile data, session records, linked session IDs,
        and legal basis details.
        """
        sess = self.get_session(token)
        if not sess:
            return {"error": "Unauthorized or invalid session"}

        user = sess.get("user", {})
        uid = user.get("id")

        with self._lock:
            all_user_sessions = []
            tokens = self._user_tokens.get(uid, [token])
            for t in tokens:
                s = self._sessions.get(t)
                if s:
                    all_user_sessions.append({
                        "created_at": s.get("created_at"),
                        "last_accessed": datetime.datetime.fromtimestamp(
                            s.get("last_accessed", 0), datetime.timezone.utc
                        ).isoformat(),
                        "linked_chat_sessions": s.get("linked_chat_sessions", []),
                    })

        return {
            "statement": "GDPR Article 15 / CCPA Personal Data Portability Export",
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user_profile": user,
            "session_history": all_user_sessions,
            "compliance_metadata": {
                "lawful_basis": "Contractual Necessity (GDPR Art. 6(1)(b)) & Consent (GDPR Art. 6(1)(a))",
                "retention_period": "Until user requests erasure",
                "do_not_sell": "We do not sell personal information under CCPA/CPRA",
            },
        }

    def delete_user_data(self, token: str) -> Dict[str, Any]:
        """GDPR Article 17 Right to Erasure ('Right to be Forgotten') & CCPA Deletion.

        Permanently removes user profile, revokes all tokens, and purges linked
        chat session directories and generated artifacts.
        """
        sess = self.get_session(token)
        if not sess:
            return {"error": "Unauthorized or invalid session"}

        user = sess.get("user", {})
        uid = user.get("id")
        email = user.get("email")

        linked_chat_sessions: List[str] = []
        with self._lock:
            tokens = list(self._user_tokens.get(uid, [token]))
            for t in tokens:
                s = self._sessions.pop(t, None)
                if s:
                    linked_chat_sessions.extend(s.get("linked_chat_sessions", []))
            self._user_tokens.pop(uid, None)
            self._save_to_disk()

        # purge_session does real filesystem I/O (shutil.rmtree) -- done
        # OUTSIDE the lock above. Holding a process-wide lock for however
        # long that takes would block every OTHER user's own session
        # lookups/creation for the duration of one user's own account
        # deletion, an unrelated-user-facing latency hit with no reason
        # to exist (the bookkeeping these directories are removed FROM is
        # already fully updated by the time this runs).
        purged_chat_sessions = []
        for csid in linked_chat_sessions:
            try:
                if purge_session(csid):
                    purged_chat_sessions.append(csid)
            except Exception:
                pass

        return {
            "status": "ok",
            "action": "Right to Erasure (GDPR Article 17 / CCPA § 1798.105)",
            "message": "User account, active sessions, and associated artifacts have been permanently deleted.",
            "deleted_user_id": uid,
            "deleted_email": email,
            "purged_chat_sessions": purged_chat_sessions,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


_GLOBAL_SESSION_MANAGER: Optional[SSOSessionManager] = None
_GLOBAL_MANAGER_LOCK = threading.Lock()


def get_sso_session_manager() -> SSOSessionManager:
    """Returns the singleton SSOSessionManager."""
    global _GLOBAL_SESSION_MANAGER
    with _GLOBAL_MANAGER_LOCK:
        if _GLOBAL_SESSION_MANAGER is None:
            _GLOBAL_SESSION_MANAGER = SSOSessionManager()
        return _GLOBAL_SESSION_MANAGER
