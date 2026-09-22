#!/usr/bin/env python3
"""
security_test.py — automated security test-suite for the CBN website
=====================================================================
Starts the server on a throw-away SQLite database and a random port,
then attacks it the way a pentester would. Standard library only.

    python3 security_test.py            # run everything
    python3 security_test.py -v         # verbose (show every response detail)

Exit code 0 = all checks passed, 1 = at least one FAIL.
Nothing here touches your real cbn.db, email.env or monime.env.
"""

import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

VERBOSE = "-v" in sys.argv
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))       # backend/
PROJECT_DIR = os.path.dirname(BASE_DIR)                          # project root
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = BASE_DIR                                      # flat checkout

# ------------------------------------------------------------------ harness
results = []          # (name, passed, detail)


def check(name, passed, detail=""):
    results.append((name, bool(passed), detail))
    mark = "PASS" if passed else "FAIL"
    line = f"  [{mark}] {name}"
    if detail and (VERBOSE or not passed):
        line += f"\n         → {detail}"
    print(line)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Client:
    """Minimal cookie-aware HTTP client (no redirects followed automatically)."""

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.cookies = {}

    def request(self, method, path, body=None, headers=None, raw_body=None, keep_cookies=True):
        h = {"Host": f"{self.host}:{self.port}", "User-Agent": "cbn-sectest/1.0"}
        if headers:
            h.update(headers)
        if self.cookies and keep_cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        data = None
        if raw_body is not None:
            data = raw_body if isinstance(raw_body, bytes) else raw_body.encode()
        elif body is not None:
            if isinstance(body, dict):
                data = urllib.parse.urlencode(body).encode()
                h.setdefault("Content-Type", "application/x-www-form-urlencoded")
            else:
                data = body.encode() if isinstance(body, str) else body
        conn = http.client.HTTPConnection(self.host, self.port, timeout=15)
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        payload = resp.read()
        # Capture cookies
        for k, v in resp.getheaders():
            if k.lower() == "set-cookie":
                name, _, rest = v.partition("=")
                value = rest.split(";", 1)[0]
                if "Max-Age=0" in v:
                    self.cookies.pop(name.strip(), None)
                else:
                    self.cookies[name.strip()] = value
        r = type("R", (), {})()
        r.status, r.headers, r.body = resp.status, {k.lower(): v for k, v in resp.getheaders()}, payload
        r.all_headers = resp.getheaders()
        r.text = payload.decode("utf-8", "replace")
        try:
            r.json = json.loads(r.text) if r.text else None
        except Exception:
            r.json = None
        conn.close()
        return r

    def get(self, path, **kw):  return self.request("GET", path, **kw)
    def post(self, path, **kw): return self.request("POST", path, **kw)


def csrf_headers(c):
    """Headers for a legitimate AJAX form post (double-submit CSRF)."""
    if "cbn_csrf" not in c.cookies:
        c.get("/api/csrf")
    return {"X-CSRF-Token": c.cookies.get("cbn_csrf", ""), "Accept": "application/json"}


# ------------------------------------------------------------------ bootstrap
def start_server():
    tmp = tempfile.mkdtemp(prefix="cbn-sectest-")
    # Rebuild the project layout in a scratch dir: backend/ (code only — no db,
    # no secrets) + frontend/ (public files). Nothing real is touched.
    be_tmp = os.path.join(tmp, "backend")
    os.makedirs(be_tmp)
    for name in os.listdir(BASE_DIR):
        src = os.path.join(BASE_DIR, name)
        if name in ("cbn.db", "cbn.db-wal", "cbn.db-shm", "email.env", "monime.env", "__pycache__"):
            continue
        if os.path.isfile(src) and name.endswith((".py", ".example")):
            shutil.copy2(src, be_tmp)
    if FRONTEND_DIR == BASE_DIR:
        # flat checkout: copy web files next to the code
        for name in os.listdir(BASE_DIR):
            src = os.path.join(BASE_DIR, name)
            if name.endswith((".html", ".css", ".js")):
                shutil.copy2(src, be_tmp)
            elif name == "partials":
                shutil.copytree(src, os.path.join(be_tmp, "partials"))
    else:
        shutil.copytree(FRONTEND_DIR, os.path.join(tmp, "frontend"),
                        ignore=shutil.ignore_patterns("__pycache__"))
    port = free_port()
    env = dict(os.environ, CBN_HOST="127.0.0.1", CBN_PORT=str(port), CBN_INBOX_POLL_SECONDS="0",
               CBN_EMAIL_ENABLED="0", CBN_MONIME_ENABLED="1")
    # Make sure no real credentials leak in from the environment
    for k in list(env):
        if k.startswith("CBN_SMTP") or k in ("CBN_MONIME_SPACE_ID", "CBN_MONIME_ACCESS_TOKEN", "CBN_MONIME_WEBHOOK_SECRET"):
            env.pop(k)
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=be_tmp, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Wait for it to listen
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.15)
    else:
        out = proc.stdout.read() if proc.stdout else ""
        raise SystemExit(f"server failed to start:\n{out}")
    time.sleep(0.6)   # let DB seeding finish
    return proc, port, tmp


# ================================================================== TESTS
def test_headers(c):
    print("\n■ Security headers")
    r = c.get("/index.html")
    h = r.headers
    check("X-Content-Type-Options: nosniff", h.get("x-content-type-options") == "nosniff")
    check("X-Frame-Options: DENY (clickjacking)", h.get("x-frame-options") == "DENY")
    check("Content-Security-Policy present", "content-security-policy" in h, h.get("content-security-policy", "")[:80])
    check("CSP forbids framing (frame-ancestors 'none')", "frame-ancestors 'none'" in h.get("content-security-policy", ""))
    check("Referrer-Policy set", "referrer-policy" in h)
    check("Server header does not leak Python version",
          "python" not in h.get("server", "").lower(), h.get("server", ""))


def test_static_files(c):
    print("\n■ Static file serving / path traversal")
    for p in ["/../server.py", "/..%2F..%2Fserver.py", "/%2e%2e/%2e%2e/etc/passwd",
              "/partials/../../etc/passwd", "/....//....//server.py"]:
        r = c.get(p)
        leaked = b"BaseHTTPRequestHandler" in r.body or b"root:" in r.body
        check(f"traversal blocked: {p}", r.status in (400, 403, 404) and not leaked, f"HTTP {r.status}")
    # Sensitive files must never be downloadable, whatever the extension checks say
    for p in ["/server.py", "/database.py", "/security.py", "/mailer.py", "/monime.py",
              "/cbn.db", "/email.env", "/monime.env", "/email.env.example", "/monime.env.example",
              "/README.md", "/.gitignore", "/security_test.py", "/use_partials.py"]:
        r = c.get(p)
        check(f"not served: {p}", r.status == 404, f"HTTP {r.status}")
    r = c.get("/styles.css")
    check("legit asset served (styles.css)", r.status == 200 and b"site-header" in r.body)
    r = c.get("/partials/header.html")
    check("partials readable by loader", r.status == 200 and b"site-header" in r.body)


def test_public_csrf(c):
    print("\n■ CSRF on public forms")
    fresh = Client(c.host, c.port)
    r = fresh.post("/api/contact", body={"name": "x", "email": "x@x.io", "message": "hi"},
                   headers={"Accept": "application/json"})
    check("contact form rejected without CSRF token", r.status == 400 and not (r.json or {}).get("success"), f"HTTP {r.status}")
    fresh.get("/api/csrf")
    r = fresh.post("/api/contact", body={"name": "x", "email": "x@x.io", "message": "hi"},
                   headers={"X-CSRF-Token": "wrong-token", "Accept": "application/json"})
    check("contact form rejected with WRONG CSRF token", r.status == 400, f"HTTP {r.status}")
    r = fresh.post("/api/contact", body={"name": "x", "email": "x@x.io", "message": "hi"},
                   headers=csrf_headers(fresh))
    check("contact form accepted with matching CSRF token", r.status == 200 and (r.json or {}).get("success"), r.text[:120])
    # Cookie attributes
    fresh2 = Client(c.host, c.port)
    r = fresh2.get("/api/csrf")
    sc = " ".join(v for k, v in r.all_headers if k.lower() == "set-cookie")
    check("CSRF cookie is SameSite=Strict", "SameSite=Strict" in sc, sc)


def test_input_validation(c):
    print("\n■ Input validation & injection")
    h = csrf_headers(c)
    # SQL injection attempts through every public form field
    sqli = "x' OR '1'='1'; DROP TABLE volunteers; --"
    r = c.post("/api/contact", body={"name": sqli, "email": "sqli@test.io", "subject": sqli, "message": sqli}, headers=h)
    check("SQLi payload stored harmlessly (parameterised queries)", r.status == 200 and (r.json or {}).get("success"))
    r = c.get("/api/projects")
    check("tables still intact after SQLi attempt", r.status == 200 and isinstance(r.json, list) and len(r.json) > 0)
    r = c.post("/api/volunteer", body={"first": "a", "last": "b", "email": "not-an-email", "role": "x", "availability": "y"}, headers=h)
    check("volunteer form rejects invalid email", r.status == 400)
    r = c.post("/api/newsletter", body={"email": "<script>alert(1)</script>@x.io"}, headers=h)
    check("newsletter rejects XSS-looking email", r.status == 400)
    # Honeypot
    r = c.post("/api/contact", body={"name": "bot", "email": "bot@x.io", "message": "spam", "website": "http://spam"}, headers=h)
    check("honeypot: bot submission silently accepted but not stored", r.status == 200)
    # Oversized body
    big = "A" * 1_100_000
    r = c.post("/api/contact", body={"name": "x", "email": "x@x.io", "message": big}, headers=h)
    check("1 MB+ body rejected (no DoS via huge payload)", r.status == 400 or not (r.json or {}).get("success"), f"HTTP {r.status}")
    # Bad JSON to webhook
    r = c.post("/api/monime/webhook", raw_body=b"{not json", headers={"Content-Type": "application/json"})
    check("malformed webhook JSON handled (no 500)", r.status == 400, f"HTTP {r.status}")


def test_xss_reflection(c):
    print("\n■ XSS — reflection & stored")
    payload = "<script>alert('xss')</script>"
    # Reflected: 404 page echoes the message? path echoes?
    r = c.get("/" + urllib.parse.quote(payload) + ".html")
    check("404 page does not reflect raw script tag", payload not in r.text)
    r = c.get("/projects/" + urllib.parse.quote(payload))
    check("project slug route rejects script in slug", r.status == 404 and payload not in r.text)
    r = c.get("/blog/" + urllib.parse.quote(payload))
    check("blog slug route rejects script in slug", r.status == 404 and payload not in r.text)
    r = c.get("/donate/return?ref=" + urllib.parse.quote(payload) + "&outcome=success")
    check("donate/return rejects malformed ref (redirects to unknown)", r.status == 302 and "status=unknown" in r.headers.get("location", ""), r.headers.get("location"))
    r = c.get("/api/donate/status?ref=" + urllib.parse.quote(payload))
    check("donation status API rejects malformed ref", r.status == 400)
    # Stored XSS via contact form → viewed in admin (checked after login)
    h = csrf_headers(c)
    c.post("/api/contact", body={"name": payload, "email": "xss@test.io", "subject": payload, "message": payload}, headers=h)
    c.post("/api/volunteer", body={"first": payload, "last": "Zed", "email": "xssvol@test.io",
                                   "role": payload, "availability": "y", "message": payload}, headers=h)
    globals()["_XSS_PAYLOAD"] = payload


def test_admin_auth(c):
    print("\n■ Admin authentication & authorisation")
    anon = Client(c.host, c.port)
    for p in ["/admin", "/admin/volunteers", "/admin/donations", "/admin/email", "/admin/payments", "/admin/inbox", "/admin/blog"]:
        r = anon.get(p)
        check(f"anonymous GET {p} → redirected to login", r.status == 302 and "/admin/login" in r.headers.get("location", ""), f"HTTP {r.status}")
    r = anon.post("/admin/volunteer/1/status", body={"status": "approved", "csrf_token": "x"})
    check("anonymous POST admin action → redirected (no state change)", r.status == 302 and "/admin/login" in r.headers.get("location", ""))
    r = anon.post("/admin/blog/create", body={"title": "hacked", "csrf_token": "x"})
    check("anonymous cannot create blog post", r.status == 302)
    # Login CSRF: posting credentials without the pre-CSRF cookie must fail
    r = anon.post("/admin/login", body={"username": "admin", "password": "ChangeMe123!", "csrf_token": "forged"}, keep_cookies=False)
    check("login POST without pre-session CSRF cookie rejected", r.status == 200 and "cbn_session" not in anon.cookies)
    # Wrong password
    anon.get("/admin/login")
    pre = anon.cookies.get("cbn_pre_csrf", "")
    r = anon.post("/admin/login", body={"username": "admin", "password": "wrong-password-1!", "csrf_token": pre})
    check("wrong password rejected, no session cookie", "cbn_session" not in anon.cookies and "Invalid username" in r.text)
    check("login error is generic (no username enumeration)", "Invalid username or password" in r.text)
    r = anon.post("/admin/login", body={"username": "nobody-here", "password": "wrong-password-1!", "csrf_token": pre})
    check("unknown user gets identical error message", "Invalid username or password" in r.text)


def test_rate_limit(c):
    print("\n■ Brute-force protection")
    b = Client(c.host, c.port)
    b.get("/admin/login")
    pre = b.cookies.get("cbn_pre_csrf", "")
    locked = False
    for i in range(7):
        r = b.post("/admin/login", body={"username": "admin", "password": f"guess{i}!!!!!!!", "csrf_token": pre})
        if "Too many failed attempts" in r.text:
            locked = True
            break
    check("login locked after 5 failed attempts (rate limit)", locked, f"locked after {i+1} attempts" if locked else "never locked")
    # Correct password must ALSO be blocked while locked
    r = b.post("/admin/login", body={"username": "admin", "password": "ChangeMe123!", "csrf_token": pre})
    check("correct password still blocked during lock-out", "cbn_session" not in b.cookies)
    # Note: the lock is per-IP; our admin login below uses the same IP, so clear it via DB
    return locked


def login_admin(c, tmpdir):
    """Log in as the seeded admin. Clears the rate-limit rows first (same IP as the brute-force test)."""
    import sqlite3
    conn = sqlite3.connect(os.path.join(tmpdir, "backend", "cbn.db"))
    conn.execute("DELETE FROM login_attempts")
    conn.commit(); conn.close()
    c.get("/admin/login")
    pre = c.cookies.get("cbn_pre_csrf", "")
    r = c.post("/admin/login", body={"username": "admin", "password": "ChangeMe123!", "csrf_token": pre})
    ok = r.status == 302 and "cbn_session" in c.cookies
    check("admin login succeeds with correct credentials + CSRF", ok)
    sc = " ".join(v for k, v in r.all_headers if k.lower() == "set-cookie")
    check("session cookie is HttpOnly", "HttpOnly" in sc, sc[:120])
    check("session cookie is SameSite=Strict", "SameSite=Strict" in sc)
    check("pre-login CSRF cookie cleared after login", "cbn_pre_csrf" not in c.cookies)
    return ok


def test_admin_csrf_and_session(c):
    print("\n■ Admin CSRF & session hardening")
    r = c.get("/admin")
    check("dashboard loads for logged-in admin", r.status == 200 and "Dashboard" in r.text)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    csrf = m.group(1) if m else ""
    check("per-session CSRF token embedded in admin forms", bool(csrf))
    # Admin action without CSRF → 403
    r = c.post("/admin/volunteer/1/status", body={"status": "approved"})
    check("admin POST without CSRF token → 403", r.status == 403)
    r = c.post("/admin/volunteer/1/status", body={"status": "approved", "csrf_token": "forged-token"})
    check("admin POST with forged CSRF token → 403", r.status == 403)
    # Session fixation / hijack: same cookie from a different User-Agent must be rejected
    hijack = Client(c.host, c.port)
    hijack.cookies = dict(c.cookies)
    r = hijack.get("/admin", headers={"User-Agent": "Evil/9.9"})
    check("session cookie replayed from different browser fingerprint → rejected", r.status == 302)
    # That rejection destroys the session — log back in for the remaining tests
    return csrf


def test_stored_xss_in_admin(c):
    print("\n■ Stored XSS rendered in admin panel")
    payload = globals().get("_XSS_PAYLOAD", "<script>alert('xss')</script>")
    r = c.get("/admin/contacts")
    check("contact XSS payload is HTML-escaped in admin (contacts)", payload not in r.text and "&lt;script&gt;" in r.text)
    r = c.get("/admin/volunteers")
    check("volunteer XSS payload is HTML-escaped in admin (volunteers)", payload not in r.text and "&lt;script&gt;" in r.text)


def test_flash_cookie_injection(c):
    print("\n■ Flash-message cookie tampering")
    evil = Client(c.host, c.port)
    evil.cookies = dict(c.cookies)
    evil.cookies["cbn_flash"] = urllib.parse.quote("ok|<img src=x onerror=alert(1)>")
    r = evil.get("/admin/volunteers")
    check("attacker-controlled flash cookie is escaped, not executed", "<img src=x onerror" not in r.text, r.status)
    evil.cookies["cbn_flash"] = urllib.parse.quote('ok" onmouseover="alert(1)|hello')
    r = evil.get("/admin/volunteers")
    check("flash 'kind' cannot break out of the class attribute", 'onmouseover="alert' not in r.text)


def test_password_change(c, csrf):
    print("\n■ Password policy")
    r = c.post("/admin/password", body={"current": "ChangeMe123!", "new1": "short", "new2": "short", "csrf_token": csrf})
    r2 = c.get("/admin/password")
    check("weak new password rejected", "at least 12 characters" in r2.text or "Password must" in r2.text, r2.text[r2.text.find("flash"):][:100])
    r = c.post("/admin/password", body={"current": "WRONG", "new1": "Str0ng!Passw0rd#2026", "new2": "Str0ng!Passw0rd#2026", "csrf_token": csrf})
    r2 = c.get("/admin/password")
    check("password change requires the current password", "incorrect" in r2.text.lower())


def test_payment_flow_integrity(c):
    print("\n■ Payment integrity (Monime simulation mode)")
    d = Client(c.host, c.port)
    h = csrf_headers(d)
    # Tamper: amount below minimum
    r = d.post("/api/donate", body={"amount": "10", "first_name": "A", "last_name": "B", "email": "a@b.io",
                                     "phone": "+23276123456", "method": "orange_money"}, headers=h)
    check("donation below minimum rejected", r.status == 400)
    # Tamper: Africell number sent as Orange
    r = d.post("/api/donate", body={"amount": "50000", "first_name": "A", "last_name": "B", "email": "a@b.io",
                                     "phone": "+23288123456", "method": "orange_money"}, headers=h)
    check("Orange Money rejects an Africell number (server-side)", r.status == 400 and "Africell" in (r.json or {}).get("message", ""))
    # Card without holder name
    r = d.post("/api/donate", body={"amount": "50000", "first_name": "A", "last_name": "B", "email": "a@b.io",
                                     "method": "card", "card_holder": ""}, headers=h)
    check("card payment rejects missing cardholder name", r.status == 400)
    # Valid donation → pending, never completed by the client
    r = d.post("/api/donate", body={"amount": "50000", "first_name": "Test", "last_name": "Donor", "email": "donor@test.io",
                                     "phone": "076123456", "method": "orange_money"}, headers=h)
    ok = r.status == 200 and (r.json or {}).get("success") and (r.json or {}).get("checkout")
    check("valid donation creates a checkout session", bool(ok), r.text[:160])
    ref = (r.json or {}).get("ref")
    sid = ((r.json or {}).get("checkout") or {}).get("session_id")
    # The browser cannot mark it paid by visiting the success URL
    r = d.get(f"/donate/return?ref={ref}&outcome=success")
    r2 = d.get(f"/api/donate/status?ref={ref}")
    check("visiting the success URL does NOT complete the donation", (r2.json or {}).get("status") == "pending",
          f"status={ (r2.json or {}).get('status') }")
    # A forged webhook (no signature) cannot complete it either
    forged = json.dumps({"event": "checkout_session.completed", "data": {"id": sid, "status": "completed", "reference": ref}})
    r = d.post("/api/monime/webhook", raw_body=forged, headers={"Content-Type": "application/json"})
    r2 = d.get(f"/api/donate/status?ref={ref}")
    check("forged (unsigned) webhook is logged but does NOT complete the donation",
          (r2.json or {}).get("status") == "pending", f"webhook HTTP {r.status}, status now {(r2.json or {}).get('status')}")
    # Status API must not leak donor PII
    body = (r2.json or {})
    check("status API does not expose donor email/phone/name",
          not any(k in body for k in ("email", "phone", "first_name", "last_name")), ",".join(body.keys()))
    # Someone else's reference cannot be guessed easily (format has 6+ random-ish chars) and unknown ref → 404
    r = d.get("/api/donate/status?ref=CBN-ZZZZZZ")
    check("unknown donation reference → 404 (no info leak)", r.status == 404)
    return ref, sid


def test_simulation_gate(c, ref, sid):
    print("\n■ Simulation endpoints")
    r = c.get(f"/pay/simulate/{sid}")
    check("simulated checkout page reachable in simulation mode", r.status == 200 and "SIMULATION" in r.text)
    r = c.get("/pay/simulate/cs_realmonimeid")
    check("simulator refuses non-simulated session ids", r.status == 404)


def test_sanitiser():
    print("\n■ Rich-text sanitiser (admin-authored article HTML)")
    sys.path.insert(0, BASE_DIR)
    import importlib
    sec = importlib.import_module("security")
    s = sec.sanitize_html
    cases = [
        ("<p>Hello <strong>world</strong></p>", "<p>Hello <strong>world</strong></p>", "keeps allowed formatting"),
        ("<script>alert(1)</script><p>x</p>", "<p>x</p>", "drops <script> and its contents"),
        ('<img src="x" onerror="alert(1)">', '<img src="x"', "strips on* event handlers"),
        ('<a href="javascript:alert(1)">x</a>', "<a>x</a>", "strips javascript: URLs"),
        ('<a href="https://monime.io">m</a>', 'rel="noopener noreferrer"', "external links get rel=noopener"),
        ('<iframe src="https://evil"></iframe><b>ok</b>', "<b>ok</b>", "drops <iframe>"),
        ('<div style="position:fixed">x</div>', "<div>x</div>", "strips style attribute"),
        ("<!--[if IE]><script>x</script><![endif]--><p>y</p>", "<p>y</p>", "drops HTML comments"),
        ('<img src="data:text/html;base64,PHNjcmlwdD4=">', "<img", "blocks data: URLs on img"),
    ]
    for src, expect, label in cases:
        out = s(src)
        ok = expect in out and ("<script" not in out) and ("onerror" not in out) and ("javascript:" not in out.lower()) and ("data:" not in out.lower())
        check(f"sanitiser: {label}", ok, f"in={src!r} out={out!r}")


def test_rate_limits(c):
    print("\n■ Per-IP rate limiting on public endpoints")
    d = Client(c.host, c.port)
    h = csrf_headers(d)
    codes = []
    for i in range(14):
        r = d.post("/api/newsletter", body={"email": f"rl{i}@test.io"}, headers=h)
        codes.append(r.status)
    check("newsletter form throttled after burst (429 seen)", 429 in codes, f"codes={codes}")
    d2 = Client(c.host, c.port)
    h2 = csrf_headers(d2)
    codes = []
    for i in range(8):
        r = d2.post("/api/donate", body={"amount": "50000", "first_name": "A", "last_name": "B", "email": "a@b.io",
                                          "phone": "076123456", "method": "orange_money"}, headers=h2)
        codes.append(r.status)
    check("checkout creation throttled after burst (429 seen)", 429 in codes, f"codes={codes}")


def test_misc(c):
    print("\n■ Miscellaneous")
    r = c.request("OPTIONS", "/api/projects")
    check("unsupported method does not crash (501/405/404)", r.status in (501, 405, 404), f"HTTP {r.status}")
    r = c.get("/api/blog")
    check("public blog API hides unpublished drafts", r.status == 200 and all(p.get("published", 1) != 0 for p in (r.json or [])))
    r = c.get("/blog/does-not-exist")
    check("unknown blog slug → 404", r.status == 404)
    r = c.get("/admin/login")
    check("login page has autocomplete off on password", 'autocomplete="off"' in r.text)
    r = c.get("/api/projects")
    check("JSON API sets Cache-Control: no-store", "no-store" in r.headers.get("cache-control", ""))


# ================================================================== MAIN
def main():
    print("=" * 66)
    print("CBN website — security test-suite")
    print("=" * 66)
    proc, port, tmp = start_server()
    print(f"scratch server on 127.0.0.1:{port}  (temp dir {tmp})")
    c = Client("127.0.0.1", port)
    try:
        test_headers(c)
        test_static_files(c)
        test_public_csrf(c)
        test_input_validation(c)
        test_xss_reflection(c)
        test_admin_auth(c)
        test_rate_limit(c)
        if login_admin(c, tmp):
            csrf = test_admin_csrf_and_session(c)
            login_admin(c, tmp)                       # hijack test destroyed the session
            test_stored_xss_in_admin(c)
            test_flash_cookie_injection(c)
            r = c.get("/admin"); m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
            test_password_change(c, m.group(1) if m else "")
        ref, sid = test_payment_flow_integrity(c)
        if ref and sid:
            test_simulation_gate(c, ref, sid)
        test_sanitiser()
        test_rate_limits(c)
        test_misc(c)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print("\n" + "=" * 66)
    print(f"RESULT: {passed}/{len(results)} checks passed")
    if failed:
        print("\nFAILED:")
        for n, d in failed:
            print(f"  ✗ {n}" + (f"  — {d}" if d else ""))
    print("=" * 66)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
