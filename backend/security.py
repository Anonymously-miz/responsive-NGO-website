"""
CBN Backend — Security helpers
==============================
Password hashing (PBKDF2-SHA256), sessions, CSRF, rate limiting,
input validation, and safe HTML escaping. Pure standard library.
"""

import hashlib
import hmac
import secrets
import re
import html
import time
from datetime import datetime, timedelta
from database import get_db, query_one, execute, query_all


# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
PBKDF2_ITERATIONS   = 260_000            # OWASP-recommended (2025)
PBKDF2_ALGORITHM    = "sha256"
PBKDF2_HASH_LEN     = 32
SESSION_DURATION_HR = 8                  # admin session length
LOGIN_MAX_ATTEMPTS  = 5                  # per IP per window
LOGIN_WINDOW_MIN    = 15                 # rate-limit window minutes
COOKIE_SESSION      = "cbn_session"
COOKIE_CSRF         = "cbn_csrf"         # readable by JS (double-submit)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# ------------------------------------------------------------------
# PASSWORD HASHING
# ------------------------------------------------------------------
def hash_password(password: str):
    """Return (salt_hex, hash_hex) using PBKDF2-SHA256."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM, password.encode("utf-8"),
        salt, PBKDF2_ITERATIONS, PBKDF2_HASH_LEN
    )
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    """Constant-time comparison of a candidate password."""
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM, password.encode("utf-8"),
        salt, PBKDF2_ITERATIONS, PBKDF2_HASH_LEN
    )
    return hmac.compare_digest(dk.hex(), expected_hash_hex)


def password_strength_error(pwd: str):
    """Return an error string if password is weak, else None."""
    if len(pwd) < 12:
        return "Password must be at least 12 characters."
    if not re.search(r"[A-Z]", pwd):
        return "Password must contain an uppercase letter."
    if not re.search(r"[a-z]", pwd):
        return "Password must contain a lowercase letter."
    if not re.search(r"\d", pwd):
        return "Password must contain a digit."
    if not re.search(r"[^A-Za-z0-9]", pwd):
        return "Password must contain a special character."
    return None


# ------------------------------------------------------------------
# SESSIONS
# ------------------------------------------------------------------
def create_session(admin_id: int, ip: str, user_agent: str):
    """Create a new session; return (session_token, csrf_token)."""
    token = secrets.token_urlsafe(32)
    csrf  = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(hours=SESSION_DURATION_HR)).isoformat()
    execute(
        "INSERT INTO sessions (token, admin_id, csrf_token, ip_address, user_agent, expires_at) "
        "VALUES (?,?,?,?,?,?)",
        (token, admin_id, csrf, ip, user_agent[:200], expires),
    )
    return token, csrf


def get_session(token: str, ip: str, user_agent: str):
    """Return session row if valid, else None. Enforces IP+UA fingerprint."""
    if not token:
        return None
    row = query_one(
        "SELECT s.*, a.username, a.email FROM sessions s "
        "JOIN admins a ON a.id = s.admin_id "
        "WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP",
        (token,),
    )
    if not row:
        return None
    # Session hijack protection: bind to IP + first 200 chars of UA
    if row["ip_address"] != ip or row["user_agent"] != user_agent[:200]:
        destroy_session(token)
        return None
    return row


def destroy_session(token: str):
    if token:
        execute("DELETE FROM sessions WHERE token = ?", (token,))


def rotate_csrf(token: str):
    """Generate a fresh CSRF token for the given session."""
    new_csrf = secrets.token_urlsafe(32)
    execute("UPDATE sessions SET csrf_token = ? WHERE token = ?", (new_csrf, token))
    return new_csrf


# ------------------------------------------------------------------
# LOGIN RATE LIMITING
# ------------------------------------------------------------------
def record_login_attempt(ip: str, username: str, success: bool):
    execute(
        "INSERT INTO login_attempts (ip_address, username, success) VALUES (?,?,?)",
        (ip, username, 1 if success else 0),
    )


def is_login_rate_limited(ip: str) -> bool:
    """Return True if too many failed attempts from this IP recently."""
    # SQLite CURRENT_TIMESTAMP uses 'YYYY-MM-DD HH:MM:SS' — match that format
    cutoff = (datetime.utcnow() - timedelta(minutes=LOGIN_WINDOW_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    row = query_one(
        "SELECT COUNT(*) AS c FROM login_attempts "
        "WHERE ip_address = ? AND success = 0 AND attempted_at > ?",
        (ip, cutoff),
    )
    return row["c"] >= LOGIN_MAX_ATTEMPTS


# ------------------------------------------------------------------
# CSRF
# ------------------------------------------------------------------
def constant_eq(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return hmac.compare_digest(a.encode(), b.encode())


def check_csrf_admin(session_row, submitted_token: str) -> bool:
    """Admin forms: submitted CSRF must equal the session's CSRF token."""
    if not session_row or not submitted_token:
        return False
    return constant_eq(session_row["csrf_token"], submitted_token)


def check_csrf_public(cookie_val: str, header_val: str) -> bool:
    """Public AJAX: X-CSRF-Token header must equal cbn_csrf cookie."""
    if not cookie_val or not header_val:
        return False
    return constant_eq(cookie_val, header_val)


# ------------------------------------------------------------------
# INPUT VALIDATION & SANITIZATION
# ------------------------------------------------------------------
def clean_str(value, max_len=500):
    """Trim, cap length. Never returns None."""
    if value is None:
        return ""
    s = str(value).strip()
    return s[:max_len]


def is_valid_email(email: str) -> bool:
    if not email or len(email) > 254:
        return False
    # Reject suspicious inputs that look like HTML/script attempts
    if "<" in email or ">" in email or "script" in email.lower():
        return False
    return bool(EMAIL_RE.match(email))


def slugify(text: str) -> str:
    """Convert 'Hello World!' to 'hello-world'."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", text) or "post"


def esc(value) -> str:
    """HTML-escape a value for safe inclusion in HTML output."""
    return html.escape("" if value is None else str(value), quote=True)


# ------------------------------------------------------------------
# RICH-TEXT SANITISER (whitelist) — for admin-authored article HTML
# ------------------------------------------------------------------
# Admins may paste HTML for blog posts / project articles. They are trusted
# users, but a phished admin account must not become stored XSS on public
# pages. Only these tags/attributes survive; everything else is stripped
# (tag removed, inner text kept). Standard library only.
from html.parser import HTMLParser as _HTMLParser

_ALLOWED_TAGS = {
    "p", "br", "hr", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "small", "sub", "sup", "mark",
    "ul", "ol", "li", "blockquote", "footer", "cite", "q",
    "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td",
    "pre", "code", "span", "div",
}
_ALLOWED_ATTRS = {
    "a":   {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "td":  {"colspan", "rowspan"},
    "th":  {"colspan", "rowspan"},
    "*":   {"class"},
}
_VOID_TAGS = {"br", "hr", "img"}
_SAFE_URL_RE = re.compile(r"^(https?://|mailto:|tel:|/|#)", re.I)


class _Sanitiser(_HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._skip_depth = 0          # inside <script>/<style>: drop content too

    def _attr_ok(self, tag, name, value):
            allowed = _ALLOWED_ATTRS.get(tag, set()) | _ALLOWED_ATTRS["*"]
            if name not in allowed:
                return False
            if name in ("href", "src"):
                v = (value or "").strip().replace("\n", "").replace("\r", "").replace("\t", "")
                v_l = v.lower()
                # Block dangerous schemes explicitly; allow relative URLs and plain paths.
                if v_l.startswith("javascript:") or v_l.startswith("data:") or v_l.startswith("vbscript:"):
                    return False
                return True
            return True

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style", "iframe", "object", "embed", "form", "input", "button", "svg", "math"):
            if tag in ("script", "style"):
                self._skip_depth += 1
            return
        if self._skip_depth or tag not in _ALLOWED_TAGS:
            return
        parts = []
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on"):
                continue                                     # onclick= etc.
            if self._attr_ok(tag, name, value):
                parts.append(f' {name}="{html.escape(value or "", quote=True)}"')
        if tag == "a":
            # External links: never leak opener, always open safely
            href = dict(attrs).get("href", "") or ""
            if href.lower().startswith("http"):
                if 'target="' not in "".join(parts):
                    parts.append(' target="_blank"')
                parts.append(' rel="noopener noreferrer"')
        if tag == "img" and ' loading="' not in "".join(parts):
            parts.append(' loading="lazy"')
        self.out.append(f"<{tag}{''.join(parts)}{' /' if tag in _VOID_TAGS else ''}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth or tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._skip_depth:
            self.out.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        pass                                                  # drop comments (incl. conditional)


def sanitize_html(fragment: str) -> str:
    """Return `fragment` with only whitelisted tags/attributes and safe URLs."""
    if not fragment:
        return ""
    p = _Sanitiser()
    try:
        p.feed(fragment)
        p.close()
    except Exception:
        return html.escape(fragment)                          # never fail open
    return "".join(p.out)


# ------------------------------------------------------------------
# COOKIE HELPERS
# ------------------------------------------------------------------
import os as _os
# Cookies get the Secure flag automatically when the site is served over HTTPS.
# Detected from CBN_PUBLIC_BASE_URL (monime.env / environment) or forced with
# CBN_SECURE_COOKIES=1. Never set on plain http://127.0.0.1 so local dev works.
def _https_deployment() -> bool:
    flag = (_os.environ.get("CBN_SECURE_COOKIES") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    try:
        import monime as _monime
        return _monime.get("CBN_PUBLIC_BASE_URL").strip().lower().startswith("https://")
    except Exception:
        return False


def build_cookie(name, value, *, http_only=True, max_age=None, same_site="Strict"):
    """Build a Set-Cookie header value string."""
    parts = [f"{name}={value}", "Path=/", f"SameSite={same_site}"]
    if http_only:
        parts.append("HttpOnly")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if _https_deployment():
        parts.append("Secure")
    return "; ".join(parts)


def parse_cookies(header: str) -> dict:
    """Parse a Cookie: header into a dict."""
    result = {}
    if not header:
        return result
    for pair in header.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
    return result


# ------------------------------------------------------------------
# STARTUP HOUSEKEEPING
# ------------------------------------------------------------------
_last_cleanup = 0
def maybe_cleanup():
    """Delete expired sessions and old login attempts once every 5 minutes."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < 300:
        return
    _last_cleanup = now
    # SQLite CURRENT_TIMESTAMP format is 'YYYY-MM-DD HH:MM:SS' (no T, no fractional seconds)
    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP")
        db.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,))
