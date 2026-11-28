"""Session-scoped server logging with automatic credential redaction.

Captures log records emitted during active web chat/artifact sessions,
redacts sensitive credentials (API keys, authorization headers, tokens, passwords),
and provides filtered access (level: ALL/INFO/WARNING/ERROR, search substring)
for the Web Client's Server Logs viewer.
"""

import collections
import datetime
import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional

from process_toolkit import paths

_SESSION_REGEX = re.compile(r"(?:session[=_]|session\s+)([a-zA-Z0-9_-]{8,})", re.IGNORECASE)

_KNOWN_SECRET_ENV_VARS = (
    "WEBAPIKEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "FLASK_SECRET_KEY",
    "SECRET_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GITHUB_CLIENT_SECRET",
    "GOOGLE_CLIENT_SECRET",
    "MICROSOFT_CLIENT_SECRET",
    "OUTLOOK_CLIENT_SECRET",
    "CLIENT_SECRET",
)

_COMMON_NON_SECRETS = frozenset({
    "true", "false", "none", "null", "undefined", "change-me",
    "test-key-unused", "fake-key", "default", "debug", "info", "warning", "error",
})

_REDACTION_PATTERNS = [
    # Google Gemini / Cloud API keys
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_API_KEY]"),
    # OpenAI / Anthropic / Generic sk- keys
    (re.compile(r"\b(?:sk|pk)[-_][a-zA-Z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    # Bearer tokens in headers or logs
    (re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{8,}\b"), "Bearer [REDACTED_TOKEN]"),
    # Basic auth
    (re.compile(r"(?i)\bBasic\s+[a-zA-Z0-9+/=]{10,}\b"), "Basic [REDACTED_AUTH]"),
    # Private keys (PEM format)
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # Key-value pairs in URLs or config text: password=..., secret=..., token=...
    (
        re.compile(r"(?i)\b(api[_-]?key|password|passwd|secret|token|auth_token|access_token|client_secret)\s*[:=]\s*['\"]?([^\s,'\"&;]{4,})['\"]?"),
        r"\1=[REDACTED]",
    ),
    # URL query parameter keys
    (
        re.compile(r"(?i)([?&](?:api[_-]?key|token|secret|password|access_token)=)[^&\s]+"),
        r"\1[REDACTED]",
    ),
]


def redact_sensitive_data(text: str) -> str:
    """Redacts any sensitive tokens, API keys, passwords, or Authorization headers
    from the given text string."""
    if not text:
        return ""

    result = str(text)

    # Redact literal values of environment secrets
    for env_var in _KNOWN_SECRET_ENV_VARS:
        val = os.environ.get(env_var)
        if val:
            val_clean = val.strip()
            if len(val_clean) >= 5 and val_clean.lower() not in _COMMON_NON_SECRETS:
                result = result.replace(val_clean, "[REDACTED_API_KEY]")

    # Apply regex patterns
    for pattern, replacement in _REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)

    return result


_EXC_FORMATTER = logging.Formatter()


class SessionLogHandler(logging.Handler):
    """Logging handler that captures records into an in-memory ring buffer
    partitioned by active session ID, and appends to output/<session_id>/session.log."""

    def __init__(self, max_entries_per_session: int = 2000):
        super().__init__()
        self.max_entries_per_session = max_entries_per_session
        self._lock = threading.Lock()
        self._session_buffers: Dict[str, collections.deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=self.max_entries_per_session)
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sid = paths.current_session_id()
            msg = record.getMessage()

            if not sid:
                # Try detecting session id from formatted message
                match = _SESSION_REGEX.search(msg)
                if match:
                    candidate = match.group(1)
                    try:
                        paths.sanitize_session_id(candidate)
                        sid = candidate
                    except ValueError:
                        pass

            if not sid:
                return

            dt_str = datetime.datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            clean_msg = redact_sensitive_data(msg)

            if record.exc_info and not record.exc_text:
                # formatException, not self.format(record) -- the latter
                # bakes record.getMessage() into its own output (Python's
                # default Formatter always does), which would duplicate
                # the message (clean_msg already carries it separately)
                # on top of the traceback.
                record.exc_text = _EXC_FORMATTER.formatException(record.exc_info)
            if record.exc_text:
                clean_exc = redact_sensitive_data(record.exc_text)
                clean_msg = f"{clean_msg}\n{clean_exc}"

            entry = {
                "timestamp": dt_str,
                "level": record.levelname.upper(),
                "logger": record.name,
                "message": clean_msg,
            }

            with self._lock:
                self._session_buffers[sid].append(entry)

            # Also persist to session directory
            try:
                with paths.use_session(sid):
                    log_file = paths.output_path("session.log")
                    out_dir = os.path.dirname(log_file)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"[{dt_str}] [{entry['level']}] [{entry['logger']}] {clean_msg}\n")
            except Exception:
                pass
        except Exception:
            self.handleError(record)

    def record_entry(
        self,
        session_id: str,
        level: str,
        message: str,
        logger_name: str = "ProcessArchitect",
    ) -> None:
        """Explicitly records a log entry for a specific session."""
        try:
            paths.sanitize_session_id(session_id)
        except ValueError:
            return

        dt_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_msg = redact_sensitive_data(message)
        entry = {
            "timestamp": dt_str,
            "level": level.upper(),
            "logger": logger_name,
            "message": clean_msg,
        }
        with self._lock:
            self._session_buffers[session_id].append(entry)

        try:
            with paths.use_session(session_id):
                log_file = paths.output_path("session.log")
                out_dir = os.path.dirname(log_file)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"[{dt_str}] [{entry['level']}] [{entry['logger']}] {clean_msg}\n")
        except Exception:
            pass

    def get_entries(
        self,
        session_id: str,
        level: str = "all",
        search: str = "",
        limit: int = 500,
    ) -> Dict[str, Any]:
        """Retrieves and filters log entries for `session_id`."""
        try:
            paths.sanitize_session_id(session_id)
        except ValueError:
            return {"total_count": 0, "logs": []}

        with self._lock:
            raw_entries = list(self._session_buffers.get(session_id, []))

        # If in-memory is empty, try reading from disk
        if not raw_entries:
            try:
                with paths.use_session(session_id):
                    log_file = paths.output_path("session.log")
                    if os.path.isfile(log_file):
                        with open(log_file, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                # Parse line format: [timestamp] [level] [logger] message
                                m = re.match(r"^\[(.*?)\]\s+\[(.*?)\]\s+\[(.*?)\]\s+(.*)$", line)
                                if m:
                                    raw_entries.append({
                                        "timestamp": m.group(1),
                                        "level": m.group(2).upper(),
                                        "logger": m.group(3),
                                        "message": m.group(4),
                                    })
                                else:
                                    raw_entries.append({
                                        "timestamp": "",
                                        "level": "INFO",
                                        "logger": "server",
                                        "message": line,
                                    })
            except Exception:
                pass

        total_count = len(raw_entries)
        lvl = (level or "all").lower().strip()
        srch = (search or "").lower().strip()

        filtered = []
        for e in raw_entries:
            entry_lvl = e.get("level", "INFO").upper()

            # Level filtering
            if lvl == "error":
                if entry_lvl not in ("ERROR", "CRITICAL"):
                    continue
            elif lvl == "warning":
                if entry_lvl not in ("WARNING", "WARN"):
                    continue
            elif lvl == "info":
                if entry_lvl != "INFO":
                    continue

            # Substring search
            if srch:
                msg = e.get("message", "").lower()
                logger_name = e.get("logger", "").lower()
                lvl_str = entry_lvl.lower()
                if srch not in msg and srch not in logger_name and srch not in lvl_str:
                    continue

            filtered.append(e)

        if limit is not None:
            # A plain `filtered[-limit:]` is wrong for limit == 0 -- Python
            # slicing treats -0 the same as 0, so `filtered[-0:]` is the
            # WHOLE list, not an empty one. Handle zero/negative explicitly
            # rather than relying on the slice to do the right thing.
            filtered = filtered[-limit:] if limit > 0 else []

        return {
            "total_count": total_count,
            "logs": filtered,
        }

    def clear_session(self, session_id: str) -> None:
        """Clears in-memory log buffer for `session_id`."""
        with self._lock:
            if session_id in self._session_buffers:
                del self._session_buffers[session_id]


_GLOBAL_SESSION_HANDLER: Optional[SessionLogHandler] = None
_HANDLER_LOCK = threading.Lock()


def get_session_log_handler() -> SessionLogHandler:
    """Returns the singleton SessionLogHandler."""
    global _GLOBAL_SESSION_HANDLER
    with _HANDLER_LOCK:
        if _GLOBAL_SESSION_HANDLER is None:
            _GLOBAL_SESSION_HANDLER = SessionLogHandler()
        return _GLOBAL_SESSION_HANDLER


def install_session_log_handler(logger_name: str = "ProcessArchitect") -> SessionLogHandler:
    """Installs the SessionLogHandler on the specified logger hierarchy,
    ensuring it is attached only once."""
    handler = get_session_log_handler()
    target_logger = logging.getLogger(logger_name)
    if handler not in target_logger.handlers:
        target_logger.addHandler(handler)

    # Also attach to root logger so any library errors (Werkzeug, Flask, etc.)
    # during active turns are captured
    root_logger = logging.getLogger()
    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)

    return handler


def record_session_log(
    session_id: str,
    level: str,
    message: str,
    logger_name: str = "ProcessArchitect",
) -> None:
    """Convenience helper to record a log message directly for a session."""
    get_session_log_handler().record_entry(session_id, level, message, logger_name)


def get_session_log_entries(
    session_id: str,
    level: str = "all",
    search: str = "",
    limit: int = 500,
) -> Dict[str, Any]:
    """Convenience helper to query log entries for a session."""
    return get_session_log_handler().get_entries(session_id, level=level, search=search, limit=limit)


def clear_session_logs(session_id: str) -> None:
    """Convenience helper to clear in-memory logs for a session."""
    get_session_log_handler().clear_session(session_id)
