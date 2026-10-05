#!/usr/bin/env python3
"""
CBN Backend — Main HTTP Server
==============================
A pure-Python secure web server (no frameworks) for the CBN website.
Uses http.server (stdlib) with threading for concurrency.

Run with:  python3 server.py
"""

import json
import os
import mimetypes
import posixpath
import urllib.parse
import logging
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import HTTPStatus

import database as db
import security as sec
import admin_ui as ui
import mailer
import monime

# ------------------------------------------------------------------
# STRUCTURED LOGGING
# ------------------------------------------------------------------
def setup_logging():
    """Configure structured logging to file and console."""
    log_file = os.environ.get("CBN_LOG_FILE", os.path.join(
        os.path.dirname(__file__), "cbn.log"))
    log_level = os.environ.get("CBN_LOG_LEVEL", "INFO").upper()
    
    logger = logging.getLogger("cbn")
    logger.setLevel(getattr(logging, log_level))
    
    # File handler (with rotation support)
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(fh)
    except Exception as e:
        print(f"Warning: could not set up file logging: {e}", file=sys.stderr)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        '[%(levelname)s] %(message)s'))
    logger.addHandler(ch)
    
    return logger

logger = setup_logging()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
# Render and other cloud hosts usually pass PORT in the environment and bind
# to 0.0.0.0. Keep local behavior by falling back to localhost only when
# those env vars are not set.
HOST = os.environ.get("CBN_HOST") or os.environ.get("HOST") or "0.0.0.0"
PORT = int(os.environ.get("CBN_PORT") or os.environ.get("PORT") or "8000")

# ── Project layout ────────────────────────────────────────────────
#   project/
#   ├── backend/   ← this file, the other .py modules, cbn.db, *.env
#   └── frontend/  ← *.html, styles.css, script.js, partials/
# Public files are served ONLY from the frontend folder, so nothing in
# backend/ (code, database, secrets) can ever be downloaded.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)
STATIC_DIR  = os.path.abspath(
    os.environ.get("CBN_FRONTEND_DIR") or os.path.join(PROJECT_DIR, "frontend"))
if not os.path.isdir(STATIC_DIR):
    # Fallback for a flat checkout (everything in one folder, pre-restructure)
    STATIC_DIR = BACKEND_DIR
ALLOWED_STATIC_EXT = {
    ".html", ".css", ".js", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2",
}

SECURITY_HEADERS = [
    ("X-Content-Type-Options",  "nosniff"),
    ("X-Frame-Options",         "DENY"),
    ("Referrer-Policy",         "strict-origin-when-cross-origin"),
    ("Permissions-Policy",      "geolocation=(), microphone=(), camera=()"),
    # CSP: allow our own scripts/styles, plus Pexels for images
    ("Content-Security-Policy",
     "default-src 'self'; "
     "img-src 'self' https://images.pexels.com data:; "
     "style-src 'self' 'unsafe-inline'; "
     "script-src 'self' 'unsafe-inline'; "
     "connect-src 'self'; "
     "frame-ancestors 'none'; "
     "base-uri 'self'"),
]


# ==================================================================
# REQUEST HANDLER
# ==================================================================
class CBNHandler(BaseHTTPRequestHandler):
    server_version = "CBN"
    sys_version    = ""            # don't advertise the Python version in Server:
    protocol_version = "HTTP/1.1"

    # ------------------ RESPONSE HELPERS ------------------
    def _send(self, status, body=b"", content_type="text/plain; charset=utf-8",
              extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS:
                self.send_header(k, v)
            # HSTS only makes sense (and is only honoured) over HTTPS
            if sec._https_deployment():
                self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            if extra_headers:
                for k, v in extra_headers:
                    self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            # Client closed the connection (or other socket-level error) while
            # we were writing headers/body. Ignore to avoid crashing the server
            # thread; log for visibility and move on.
            try:
                self.log_message("client disconnected while sending response: %s", str(e))
            except Exception:
                pass

    def send_html(self, html, status=200, cookies=None, use_partials=False, page_key=""):
        """
        Send an HTML response. With use_partials=True the inline
        <header class="site-header"> / <footer class="site-footer"> blocks in the
        generated page are swapped for partials/header.html + partials/footer.html,
        so the server-rendered article pages share the exact same chrome as the
        static pages (and inherit any edit made to the partials).
        """
        if use_partials:
            raw = html.encode("utf-8") if isinstance(html, str) else html
            html = _inject_partials(raw, page_key or "")
        headers = [("Set-Cookie", c) for c in (cookies or [])]
        self._send(status, html, "text/html; charset=utf-8", headers)

    def send_json(self, data, status=200, cookies=None):
        headers = [("Set-Cookie", c) for c in (cookies or [])]
        # API responses are live database reads — never let the browser cache them,
        # otherwise a freshly published post could be hidden behind a stale copy.
        headers.append(("Cache-Control", "no-store"))
        self._send(status, json.dumps(data), "application/json; charset=utf-8", headers)

    def send_redirect(self, location, cookies=None):
        headers = [("Location", location)]
        for c in (cookies or []):
            headers.append(("Set-Cookie", c))
        self._send(302, b"", "text/plain", headers)

    def send_error_page(self, status, message):
        self.send_html(
            f"<h1>{status}</h1><p>{sec.esc(message)}</p>"
            f'<p><a href="/">← Home</a></p>',
            status=status,
        )

    # ------------------ REQUEST PARSERS ------------------
    def get_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        # Enforce a 1 MB limit. If the declared body is larger, drain the
        # incoming bytes from the socket so the client can finish sending
        # without the server closing the connection abruptly (which causes
        # BrokenPipeError on the client side). We do NOT retain oversized
        # bodies in memory.
        if length <= 0:
            return b""
        MAX_LEN = 1_000_000
        if length > MAX_LEN:
            to_read = length
            try:
                # Read and discard in chunks
                while to_read > 0:
                    chunk = self.rfile.read(min(64 * 1024, to_read))
                    if not chunk:
                        break
                    to_read -= len(chunk)
            except Exception:
                pass
            return b""
        return self.rfile.read(length)

    def parse_form(self):
        ct = self.headers.get("Content-Type", "")
        body = self.get_body()
        if "application/x-www-form-urlencoded" in ct:
            return {k: v[0] for k, v in
                    urllib.parse.parse_qs(body.decode("utf-8", "replace"),
                                          keep_blank_values=True).items()}
        if "application/json" in ct:
            try:
                return json.loads(body.decode("utf-8"))
            except Exception:
                return {}
        return {}

    def get_cookies(self):
        return sec.parse_cookies(self.headers.get("Cookie", ""))

    def client_ip(self):
        return self.client_address[0]

    def user_agent(self):
        return self.headers.get("User-Agent", "")

    # Quieter logs (to structured logger)
    def log_message(self, fmt, *args):
        msg = fmt % args if args else fmt
        logger.debug(f"{self.client_ip()} {msg}")

    # ==============================================================
    # ROUTING
    # ==============================================================
    def do_GET(self):
        sec.maybe_cleanup()
        path = urllib.parse.urlparse(self.path).path

        # Health check (monitoring/load balancers)
        if path == "/health":
            return self.send_json({"status": "ok", "timestamp": datetime.utcnow().isoformat()})
        
        # Public API — JSON
        if path == "/api/csrf":                 return self.api_csrf()
        if path == "/api/projects":             return self.api_list_projects()
        if path == "/api/blog":                 return self.api_list_blog()
        if path == "/api/events":               return self.api_list_events()

        # Dynamic article pages (server-rendered from the database)
        if path.startswith("/projects/"):       return self.project_article(path)
        if path in ("/blog", "/blog/"):         return self.send_redirect("/news.html#blog")
        if path.startswith("/blog/"):           return self.blog_article(path)

        # Payments (Monime)
        if path == "/donate/return":            return self.donate_return()
        if path == "/api/donate/status":
            if self._rate_limited("status"):
                return
            return self.api_donation_status()
        if path.startswith("/pay/simulate/"):   return self.simulate_checkout_page(path)

        # Admin routes
        if path == "/admin/login":              return self.admin_login_page()
        if path == "/admin/logout":             return self.send_redirect("/admin/login")
        if path.startswith("/admin"):           return self.admin_dispatch_get(path)

        # Static files (HTML pages, CSS, JS, images)
        return self.serve_static(path)

    def do_POST(self):
        sec.maybe_cleanup()
        path = urllib.parse.urlparse(self.path).path

        # Public form endpoints (AJAX or traditional POST) — per-IP rate limited
        if path in ("/api/volunteer", "/api/contact", "/api/partner", "/api/newsletter"):
            if self._rate_limited("form"):
                return
        if path == "/api/donate" and self._rate_limited("donate"):
            return
        if path == "/api/volunteer":   return self.api_volunteer()
        if path == "/api/contact":     return self.api_contact()
        if path == "/api/partner":     return self.api_partner()
        if path == "/api/newsletter":  return self.api_newsletter()
        if path == "/api/donate":      return self.api_donate()
        if path == "/api/monime/webhook":       return self.api_monime_webhook()
        if path.startswith("/pay/simulate/"):   return self.simulate_checkout_action(path)

        # Admin auth
        if path == "/admin/login":     return self.admin_login_submit()
        if path == "/admin/logout":    return self.admin_logout()

        # Admin CRUD
        if path.startswith("/admin"):  return self.admin_dispatch_post(path)

        return self.send_error_page(404, "Not found")

    def do_HEAD(self):
        self.do_GET()

    # ==============================================================
    # STATIC FILES
    # ==============================================================
    def serve_static(self, path):
        # Default to index.html
        if path in ("", "/"):
            path = "/index.html"

        # Sanitize path (prevent directory traversal)
        safe = posixpath.normpath(urllib.parse.unquote(path)).lstrip("/")
        if safe.startswith("..") or "/../" in safe or safe.startswith("/"):
            return self.send_error_page(400, "Bad request")

        full_path = os.path.join(STATIC_DIR, safe)
        # Must stay inside STATIC_DIR
        if not os.path.abspath(full_path).startswith(STATIC_DIR):
            return self.send_error_page(403, "Forbidden")

        ext = os.path.splitext(full_path)[1].lower()
        if ext not in ALLOWED_STATIC_EXT:
            return self.send_error_page(404, "Not found")

        if not os.path.isfile(full_path):
            return self.send_error_page(404, "Page not found")

        try:
            with open(full_path, "rb") as f:
                content = f.read()
        except OSError:
            return self.send_error_page(500, "Failed to read file")

        mime, _ = mimetypes.guess_type(full_path)
        mime = mime or "application/octet-stream"

        cookies = []
        # For HTML pages, ensure a CSRF cookie is present (double-submit pattern)
        if ext == ".html":
            existing = self.get_cookies().get(sec.COOKIE_CSRF)
            if not existing:
                import secrets as _s
                cookies.append(sec.build_cookie(
                    sec.COOKIE_CSRF, _s.token_urlsafe(32),
                    http_only=False, max_age=60*60*24, same_site="Strict"))
            # Server-side include of the shared header/footer partials, so the chrome
            # is present in the HTML itself (no flash, works for crawlers). The
            # client-side loader in script.js is then a no-op for these pages.
            content = _inject_partials(content, safe)

        self._send(200, content, mime,
                   [("Set-Cookie", c) for c in cookies])

    # ==============================================================
    # PUBLIC API HANDLERS
    # ==============================================================
    def _check_public_csrf(self):
        cookie_val = self.get_cookies().get(sec.COOKIE_CSRF)
        header_val = self.headers.get("X-CSRF-Token")
        return sec.check_csrf_public(cookie_val, header_val)

    def _rate_limited(self, bucket):
        """Apply a per-IP limit; on breach, answer 429 and return True."""
        if _rate_ok(bucket, self.client_ip()):
            return False
        self.send_json({"success": False,
                        "message": "Too many requests from your connection. Please wait a few minutes and try again."},
                       429, cookies=None)
        return True

    def _wants_json(self):
        return "application/json" in (self.headers.get("Accept", "") + " " +
                                       self.headers.get("Content-Type", ""))

    def _form_response(self, ok, message, redirect="/thank-you.html"):
        """Reply to a public form: JSON if AJAX, HTML redirect otherwise."""
        if self._wants_json():
            return self.send_json({"success": ok, "message": message},
                                  status=200 if ok else 400)
        # Fallback for non-JS clients: simple HTML confirmation
        title = "Thank You" if ok else "Submission Error"
        self.send_html(
            f"<!DOCTYPE html><html><head><title>{title}</title>"
            f"<link rel='stylesheet' href='/styles.css'></head>"
            f"<body><section class='page-hero'><div class='container'>"
            f"<h1>{title}</h1><p>{sec.esc(message)}</p>"
            f"<p><a href='/' class='btn btn-primary' "
            f"style='color:#fff;margin-top:20px;'>Return Home</a></p>"
            f"</div></section></body></html>",
            status=200 if ok else 400)

    def api_csrf(self):
        """Return the current CSRF token from cookie (for JS to read)."""
        val = self.get_cookies().get(sec.COOKIE_CSRF)
        cookies = []
        if not val:
            import secrets as _s
            val = _s.token_urlsafe(32)
            cookies.append(sec.build_cookie(
                sec.COOKIE_CSRF, val, http_only=False,
                max_age=60*60*24, same_site="Strict"))
        self.send_json({"csrf_token": val}, cookies=cookies)

    def api_volunteer(self):
        if not self._check_public_csrf():
            return self._form_response(False, "Security check failed. Please refresh and try again.")
        data = self.parse_form()

        # Honeypot: if the invisible 'website' field is filled, it's a bot
        if sec.clean_str(data.get("website")):
            return self._form_response(True, "Thank you!")  # silently ignore

        first = sec.clean_str(data.get("first"), 50) or sec.clean_str(data.get("first_name"), 50)
        last  = sec.clean_str(data.get("last"),  50) or sec.clean_str(data.get("last_name"),  50)
        email = sec.clean_str(data.get("email"), 254).lower()
        phone = sec.clean_str(data.get("phone"), 30)
        role  = sec.clean_str(data.get("role"),  100)
        avail = sec.clean_str(data.get("availability"), 100)
        msg   = sec.clean_str(data.get("message"), 2000)

        if not first or not last or not sec.is_valid_email(email):
            return self._form_response(False, "Please provide a valid name and email.")
        if not role or not avail:
            return self._form_response(False, "Please select a role and availability.")

        new_id = db.execute(
            "INSERT INTO volunteers (first_name,last_name,email,phone,role,availability,message,ip_address)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (first, last, email, phone, role, avail, msg, self.client_ip()),
        )

        # ── Emails on submission (both in the background; the form never waits) ──
        vol = {"id": new_id, "first_name": first, "last_name": last, "email": email,
               "phone": phone, "role": role, "availability": avail, "message": msg}

        # 1) Acknowledgement TO the applicant, FROM cbnetwork.sierraleone@gmail.com
        subj, txt, html = mailer.build_application_received_email(vol)
        self._queue_email(email, subj, txt, html, kind="application_received",
                          related=("volunteers", new_id), to_name=f"{first} {last}",
                          label="application receipt")

        # 2) Alert TO the office inbox so the team knows a decision is waiting
        host_hdr  = self.headers.get("Host", f"{HOST}:{PORT}")
        admin_url = f"http://{host_hdr}/admin/volunteers"
        self._send_office_copy(
            *mailer.build_new_application_alert(vol, admin_url),
            related=("volunteers", new_id), kind="new_application_alert",
        )

        return self._form_response(True,
            "Thank you! Your application has been received — a confirmation email is on its way "
            "to you. Our team will be in touch within 3 working days.")

    def api_contact(self):
        if not self._check_public_csrf():
            return self._form_response(False, "Security check failed. Please refresh and try again.")
        data = self.parse_form()
        if sec.clean_str(data.get("website")):
            return self._form_response(True, "Thank you!")

        name    = sec.clean_str(data.get("name"), 100)
        email   = sec.clean_str(data.get("email"), 254).lower()
        subject = sec.clean_str(data.get("subject"), 200)
        message = sec.clean_str(data.get("message"), 3000)

        if not name or not sec.is_valid_email(email) or not message:
            return self._form_response(False, "Please fill in your name, a valid email, and a message.")

        db.execute(
            "INSERT INTO contacts (name,email,subject,message,ip_address)"
            " VALUES (?,?,?,?,?)",
            (name, email, subject, message, self.client_ip()),
        )
        return self._form_response(True,
            "Thank you! Your message has been received. We'll get back to you soon.")

    def api_partner(self):
        if not self._check_public_csrf():
            return self._form_response(False, "Security check failed. Please refresh and try again.")
        data = self.parse_form()
        if sec.clean_str(data.get("website")):
            return self._form_response(True, "Thank you!")

        org   = sec.clean_str(data.get("organisation"), 200)
        name  = sec.clean_str(data.get("contact_name"), 100)
        email = sec.clean_str(data.get("email"), 254).lower()
        ptype = sec.clean_str(data.get("partnership_type"), 100)
        msg   = sec.clean_str(data.get("message"), 3000)

        if not org or not name or not sec.is_valid_email(email):
            return self._form_response(False, "Please provide organisation, contact name and a valid email.")

        db.execute(
            "INSERT INTO partners (organisation,contact_name,email,partnership_type,message)"
            " VALUES (?,?,?,?,?)",
            (org, name, email, ptype, msg),
        )
        return self._form_response(True,
            "Thank you! Our partnerships team will contact you within 5 working days.")

    def api_newsletter(self):
        if not self._check_public_csrf():
            return self._form_response(False, "Security check failed.")
        data = self.parse_form()
        if sec.clean_str(data.get("website")):
            return self._form_response(True, "Thanks for subscribing!")

        email = sec.clean_str(data.get("email"), 254).lower()
        if not sec.is_valid_email(email):
            return self._form_response(False, "Please provide a valid email address.")

        try:
            db.execute("INSERT INTO subscribers (email) VALUES (?)", (email,))
        except Exception:
            pass  # already subscribed — pretend success
        return self._form_response(True,
            "You're subscribed! Watch your inbox for CBN updates.")

    def api_donate(self):
        """Process a donation — Orange Money push-payment initiation."""
        if not self._check_public_csrf():
            return self.send_json({"success": False,
                                   "message": "Security check failed. Please refresh."}, 400)
        data = self.parse_form()

        # Honeypot
        if sec.clean_str(data.get("website")):
            return self.send_json({"success": True,
                                   "message": "Thank you!", "ref": "CBN-OK"})

        # ── Validate inputs ──────────────────────────────────────────
        first  = sec.clean_str(data.get("first_name"), 50)
        last   = sec.clean_str(data.get("last_name"),  50)
        email  = sec.clean_str(data.get("email"), 254).lower()
        phone  = sec.clean_str(data.get("phone"), 20).replace(" ", "")
        method = (sec.clean_str(data.get("method"), 30)
                  or sec.clean_str(data.get("payment_method"), 30) or "orange_money")
        if method not in ("orange_money", "africell_money", "card", "bank_transfer"):
            method = "orange_money"
        freq   = sec.clean_str(data.get("frequency"), 20) or "once"
        proj   = sec.clean_str(data.get("project"), 100)
        ref    = sec.clean_str(data.get("ref"), 30)
        anon   = 1 if data.get("anonymous") else 0

        try:
            amount = int(str(data.get("amount", "0")).strip())
        except (ValueError, TypeError):
            amount = 0

        if not first or not last:
            return self.send_json({"success": False,
                                   "message": "Please enter your full name."}, 400)
        if not sec.is_valid_email(email):
            return self.send_json({"success": False,
                                   "message": "Please enter a valid email address."}, 400)
        if amount < 5000:
            return self.send_json({"success": False,
                                   "message": "Minimum donation is Le 5,000."}, 400)

        # ── Per-method validation (mirrors the per-method functions on donate.html) ──
        card_holder   = ""
        momo_operator = None
        if method == "orange_money":
            ok_no, e164, why = monime.validate_momo_number(phone, "orange")
            if not ok_no:
                return self.send_json({"success": False, "field": "om-phone", "message": why}, 400)
            phone, momo_operator = e164, "orange"
        elif method == "africell_money":
            ok_no, e164, why = monime.validate_momo_number(phone, "africell")
            if not ok_no:
                return self.send_json({"success": False, "field": "am-phone", "message": why}, 400)
            phone, momo_operator = e164, "africell"
        elif method == "card":
            import re as _re
            card_holder = _re.sub(r"\s+", " ", sec.clean_str(data.get("card_holder"), 60)).strip().upper()
            if (len(card_holder) < 3 or len(card_holder.split(" ")) < 2
                    or not _re.match(r"^[A-Z][A-Z .'\-]{1,58}$", card_holder)):
                return self.send_json({"success": False, "field": "card-holder",
                                       "message": "Please enter the full name printed on the card (letters only)."}, 400)
            phone = ""     # not needed for card payments
        else:              # bank_transfer — nothing extra; handled offline
            phone = ""

        # Auto-generate ref if frontend didn't supply one
        import secrets as _s
        if not ref or len(ref) < 6:
            ref = "CBN-" + _s.token_urlsafe(6).upper()[:8]

        # ── Persist the pending donation ────────────────────────────
        insert_sql = (
            "INSERT INTO donations "
            "(reference, first_name, last_name, email, phone, card_holder, momo_operator, "
            " amount_sll, payment_method, frequency, project_designation, "
            " anonymous, status, ip_address) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        row_vals = lambda r: (r, first, last, email, phone, card_holder or None, momo_operator,
                              amount, method, freq, proj, anon, "pending", self.client_ip())
        try:
            db.execute(insert_sql, row_vals(ref))
        except Exception:
            # Duplicate ref — generate a new one
            ref = "CBN-" + _s.token_urlsafe(8).upper()[:10]
            db.execute(insert_sql, row_vals(ref))

        # ── Create the Monime checkout session ─────────────────────────
        # Monime hosts the payment page (Orange Money, Africell Money, bank, card).
        # We store the session id and send the donor to `redirectUrl`.
        # The donation is only marked 'completed' after the server verifies the
        # session with Monime (see donate_return / _verify_donation), never on
        # the strength of the browser redirect alone.
        donation = dict(db.query_one("SELECT * FROM donations WHERE reference=?", (ref,)))
        base_url = self._public_base_url()
        proj_title = None
        if proj:
            prow = db.query_one("SELECT title FROM projects WHERE slug=?", (proj,))
            proj_title = prow["title"] if prow else None

        gw_mode = monime.mode()
        if gw_mode == "disabled":
            db.execute("UPDATE donations SET status='pending', gateway='offline', gateway_mode='disabled' "
                       "WHERE reference=?", (ref,))
            return self.send_json({
                "success": True, "ref": ref, "amount": amount, "checkout": None,
                "message": ("Online payments are currently unavailable. Please use the bank-transfer "
                            f"details on this page and quote reference {ref}."),
            })

        if gw_mode == "simulation":
            ok, session = True, monime.simulate_create(donation, base_url)
        else:
            ok, session = monime.create_checkout(donation, base_url, proj_title)

        if not ok:
            err = str(session)
            db.execute("UPDATE donations SET status='failed', failure_reason=?, gateway_mode=? WHERE reference=?",
                       (err[:500], gw_mode, ref))
            db.payment_event(ref, None, "create", "checkout_session.create_failed", "failed", 1,
                             {"error": err}, self.client_ip())
            friendly = ("We couldn't reach the payment provider right now. Please try again in a moment "
                        "or use the bank-transfer option.")
            if err.startswith("NETWORK:"):
                friendly = "The server is offline and cannot contact the payment provider. Please try again shortly."
            print(f"[monime] ❌ create checkout for {ref} failed: {err}")
            return self.send_json({"success": False, "message": friendly, "ref": ref}, 502)

        db.execute(
            "UPDATE donations SET gateway='monime', gateway_mode=?, checkout_session_id=?, checkout_url=?, "
            "order_number=?, amount_minor=?, gateway_status=?, status='pending' WHERE reference=?",
            (gw_mode, session.get("id"), session.get("redirectUrl"), session.get("orderNumber"),
             monime.sll_to_minor(amount), session.get("status", "pending"), ref),
        )
        db.payment_event(ref, session.get("id"), "create", "checkout_session.created",
                         session.get("status", "pending"), 1,
                         {k: session.get(k) for k in ("id", "orderNumber", "status", "expireTime", "simulated")},
                         self.client_ip())
        db.log_audit(None, "donation_checkout_created",
                     f"ref={ref} amount_sll={amount} mode={gw_mode} session={session.get('id')}",
                     self.client_ip())
        print(f"[monime] 🧾 {gw_mode.upper()} checkout {session.get('id')} for {ref} "
              f"({monime.fmt_sle(monime.sll_to_minor(amount))}) → {session.get('redirectUrl')}")

        return self.send_json({
            "success":  True,
            "ref":      ref,
            "amount":   amount,
            "mode":     gw_mode,
            "checkout": {
                "session_id":   session.get("id"),
                "redirect_url": session.get("redirectUrl"),
                "order_number": session.get("orderNumber"),
                "expires_at":   session.get("expireTime"),
                "amount_sle":   monime.fmt_sle(monime.sll_to_minor(amount)),
            },
            "message": ("Redirecting you to the secure payment page…"
                        if gw_mode != "simulation" else
                        "SIMULATION — opening a test payment page (no real money moves)."),
        })

    # ------------------------------------------------------------------
    # Donation helpers — verification is the ONLY thing that marks 'completed'
    # ------------------------------------------------------------------
    def _public_base_url(self):
        """Absolute origin for redirect/webhook URLs (config first, then request Host)."""
        configured = monime.get("CBN_PUBLIC_BASE_URL").strip().rstrip("/")
        if configured:
            return configured
        host = self.headers.get("Host", f"{HOST}:{PORT}")
        scheme = "https" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
        return f"{scheme}://{host}"

    def _apply_gateway_status(self, donation, session, source, verified, event_type=None, ip=None):
        """
        Reconcile a donation row with a checkout-session object from Monime.
        Idempotent: re-applying the same completed session changes nothing.
        Returns the (possibly new) donation status.
        """
        ref = donation["reference"]
        gw_status = (session or {}).get("status") or "pending"
        db.payment_event(ref, (session or {}).get("id"), source, event_type or f"checkout_session.{gw_status}",
                         gw_status, verified, session, ip)

        if not verified:
            return donation["status"]          # never change state on unverified data

        # Amount tamper check: Monime's total must match what we asked for
        expected_minor = donation.get("amount_minor") or monime.sll_to_minor(donation["amount_sll"])
        items = ((session or {}).get("lineItems") or {}).get("data") or []
        total_minor = sum(int((i.get("price") or {}).get("value") or 0) * int(i.get("quantity") or 1) for i in items)
        if items and total_minor != int(expected_minor):
            db.execute("UPDATE donations SET failure_reason=?, gateway_status=?, last_verified_at=CURRENT_TIMESTAMP "
                       "WHERE reference=?",
                       (f"amount mismatch: expected {expected_minor} minor, Monime reports {total_minor}", gw_status, ref))
            print(f"[monime] ⚠ amount mismatch for {ref}: expected {expected_minor}, got {total_minor}")
            return donation["status"]

        if gw_status == "completed":
            if donation["status"] != "completed":
                db.execute(
                    "UPDATE donations SET status='completed', gateway_status='completed', "
                    "confirmed_at=COALESCE(confirmed_at, CURRENT_TIMESTAMP), paid_at=CURRENT_TIMESTAMP, "
                    "last_verified_at=CURRENT_TIMESTAMP, om_transaction_id=COALESCE(om_transaction_id, ?), "
                    "failure_reason=NULL WHERE reference=?",
                    ((session or {}).get("orderNumber") or (session or {}).get("id"), ref),
                )
                db.log_audit(None, "donation_completed",
                             f"ref={ref} via={source} session={(session or {}).get('id')} mode={donation.get('gateway_mode')}", ip)
                print(f"[monime] ✅ donation {ref} COMPLETED ({source})")
                self._send_donation_receipt(ref)
            return "completed"

        if gw_status in ("cancelled", "expired"):
            new_status = "failed"
            if donation["status"] not in ("completed",):
                db.execute("UPDATE donations SET status=?, gateway_status=?, failure_reason=?, "
                           "last_verified_at=CURRENT_TIMESTAMP WHERE reference=?",
                           (new_status, gw_status, f"checkout {gw_status}", ref))
                print(f"[monime] ✖ donation {ref} {gw_status}")
            return new_status

        db.execute("UPDATE donations SET gateway_status=?, last_verified_at=CURRENT_TIMESTAMP WHERE reference=?",
                   (gw_status, ref))
        return donation["status"]

    def _verify_donation(self, ref, source="verify", ip=None):
        """
        Ask Monime (or the simulator) for the session's real status and apply it.
        Returns (donation_dict, status, detail).
        """
        row = db.query_one("SELECT * FROM donations WHERE reference=?", (ref,))
        if not row:
            return None, None, "unknown reference"
        donation = dict(row)
        if donation["status"] == "completed":
            return donation, "completed", "already completed"
        sid = donation.get("checkout_session_id")
        if not sid:
            return donation, donation["status"], "no checkout session"

        if donation.get("gateway_mode") == "simulation" and str(sid).startswith("sim_"):
            # Simulated rows can only be trusted while the gateway is still in simulation
            # mode. Once real credentials are configured, a stale simulated donation can
            # never be flipped to 'completed' — it is left pending for an admin to review.
            if monime.mode() != "simulation":
                return donation, donation["status"], "simulated donation ignored (gateway is live)"
            status_ = donation.get("gateway_status") or "pending"
            session = {"id": sid, "status": status_, "orderNumber": donation.get("order_number"),
                       "lineItems": {"data": [{"price": {"value": donation.get("amount_minor")}, "quantity": 1}]},
                       "simulated": True}
            return donation, self._apply_gateway_status(donation, session, source, True, ip=ip), "simulated"

        ok, session = monime.get_checkout(sid)
        if not ok:
            db.payment_event(ref, sid, source, "verify_failed", None, 0, {"error": str(session)}, ip)
            return donation, donation["status"], f"verification failed: {session}"
        return donation, self._apply_gateway_status(donation, session, source, True, ip=ip), "verified with Monime"

    def _send_donation_receipt(self, ref):
        """Thank-you / receipt email to the donor + copy to the office inbox."""
        row = db.query_one("SELECT * FROM donations WHERE reference=?", (ref,))
        if not row:
            return
        d = dict(row)
        if not sec.is_valid_email(d.get("email") or ""):
            return
        if db.query_one("SELECT 1 FROM email_log WHERE kind='donation_receipt' AND related_table='donations' "
                        "AND related_id=?", (d["id"],)):
            return                                   # already sent (idempotent)
        subj, txt, html = mailer.build_donation_receipt_email(d)
        self._queue_email(d["email"], subj, txt, html, kind="donation_receipt",
                          related=("donations", d["id"]),
                          to_name=f"{d.get('first_name','')} {d.get('last_name','')}".strip(),
                          label=f"donation receipt {ref}")
        self._send_office_copy(*mailer.build_donation_alert_email(d),
                               related=("donations", d["id"]), kind="donation_alert")

    # ------------------------------------------------------------------
    # /donate/return  — donor comes back from Monime (success or cancel)
    # ------------------------------------------------------------------
    def donate_return(self):
        qs  = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ref = sec.clean_str(qs.get("ref", [""])[0], 40)
        outcome = sec.clean_str(qs.get("outcome", [""])[0], 20)
        import re as _re
        if not ref or not _re.match(r"^CBN-[A-Za-z0-9_-]{4,24}$", ref):
            return self.send_redirect("/donate.html?status=unknown")
        donation, status_, detail = self._verify_donation(ref, source="return", ip=self.client_ip())
        if not donation:
            return self.send_redirect("/donate.html?status=unknown")
        if status_ == "completed":
            return self.send_redirect(f"/donate.html?status=success&ref={ref}")
        if outcome == "cancel" or status_ == "failed":
            return self.send_redirect(f"/donate.html?status=cancelled&ref={ref}")
        # Still pending (e.g. MoMo confirmation in flight) — page will poll /api/donate/status
        return self.send_redirect(f"/donate.html?status=pending&ref={ref}")

    def api_donation_status(self):
        """Public, reference-scoped status poll used by donate.html."""
        qs  = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ref = sec.clean_str(qs.get("ref", [""])[0], 40)
        import re as _re
        if not ref or not _re.match(r"^CBN-[A-Za-z0-9_-]{4,24}$", ref):
            return self.send_json({"success": False, "message": "bad reference"}, 400)
        donation, status_, detail = self._verify_donation(ref, source="poll", ip=self.client_ip())
        if not donation:
            return self.send_json({"success": False, "message": "unknown reference"}, 404)
        return self.send_json({
            "success": True, "ref": ref, "status": status_,
            "gateway_status": donation.get("gateway_status"),
            "amount_sll": donation["amount_sll"],
            "amount_sle": monime.fmt_sle(donation.get("amount_minor") or monime.sll_to_minor(donation["amount_sll"])),
            "mode": donation.get("gateway_mode"),
            "checkout_url": donation.get("checkout_url") if status_ == "pending" else None,
            "detail": detail,
        })

    # ------------------------------------------------------------------
    # /api/monime/webhook — Monime → us (fast path; verified, then re-fetched)
    # ------------------------------------------------------------------
    def api_monime_webhook(self):
        raw = self.get_body()
        sig = monime.find_signature(self.headers)
        verified, why = monime.verify_webhook(raw, sig) if monime.get("CBN_MONIME_WEBHOOK_SECRET") else (False, "no secret configured")
        try:
            event = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            db.payment_event(None, None, "webhook", "malformed", None, 0, raw[:2000].decode("utf-8", "replace"), self.client_ip())
            return self.send_json({"received": False, "message": "malformed JSON"}, 400)

        # Monime event envelopes vary slightly between releases — dig out the session object.
        obj = event.get("data") or event.get("object") or event.get("result") or event
        if isinstance(obj, dict) and isinstance(obj.get("object"), dict):
            obj = obj["object"]
        event_type = event.get("event") or event.get("type") or event.get("name") or "unknown"
        session_id = (obj or {}).get("id")
        ref = ((obj or {}).get("reference") or (obj or {}).get("callbackState")
               or ((obj or {}).get("metadata") or {}).get("donation_reference"))

        db.payment_event(ref, session_id, "webhook", event_type, (obj or {}).get("status"),
                         verified, event, self.client_ip())
        print(f"[monime] 🔔 webhook {event_type} session={session_id} ref={ref} signature={'OK' if verified else why}")

        # ── Decide whether this delivery may trigger work ──────────────────
        # A webhook can never complete a donation by itself (we always re-fetch the
        # session from api.monime.io), but each re-fetch is an outbound API call. To
        # stop an unauthenticated caller using this endpoint to make us hammer Monime
        # (or to burn rate limits), we only act on deliveries we can trust:
        #   • secret configured  → signature MUST verify
        #   • no secret yet      → accept, but throttle per-IP (best effort while the
        #                           operator hasn't registered the webhook yet)
        if monime.get("CBN_MONIME_WEBHOOK_SECRET") and not verified:
            print(f"[monime] ⛔ unsigned/invalid webhook ignored ({why}) from {self.client_ip()}")
            return self.send_json({"received": True, "verified": False, "action": "ignored"}, 401)
        if not monime.get("CBN_MONIME_WEBHOOK_SECRET") and not _webhook_throttle_ok(self.client_ip()):
            return self.send_json({"received": True, "verified": False, "action": "throttled"}, 429)

        # Only ever verify references that (a) look like ours and (b) exist — never
        # let the payload steer us toward arbitrary work.
        import re as _re
        if ref and not _re.match(r"^CBN-[A-Za-z0-9_-]{4,24}$", str(ref)):
            ref = None
        if not ref and session_id:
            row = db.query_one("SELECT reference FROM donations WHERE checkout_session_id=?", (str(session_id)[:100],))
            ref = row["reference"] if row else None
        if ref:
            # Even a verified webhook is only a hint: the truth is re-fetched from Monime.
            self._verify_donation(ref, source="webhook", ip=self.client_ip())
        # 200 so Monime doesn't retry forever on our side; problems are logged.
        return self.send_json({"received": True, "verified": verified})

    # ------------------------------------------------------------------
    # /pay/simulate/<id> — local stand-in for Monime's hosted page (no credentials)
    # ------------------------------------------------------------------
    def simulate_checkout_page(self, path):
        # Hard gate: the simulator only exists when no real gateway is configured.
        if monime.mode() != "simulation":
            return self.send_error_page(404, "Not found")
        sid = path.replace("/pay/simulate/", "").strip("/")
        row = db.query_one("SELECT * FROM donations WHERE checkout_session_id=?", (sid,))
        if not row or not str(sid).startswith("sim_") or row["gateway_mode"] != "simulation":
            return self.send_error_page(404, "Simulated checkout not found")
        d = dict(row)
        if d["status"] == "completed":
            return self.send_redirect(f"/donate/return?ref={d['reference']}&outcome=success")
        html = ui.render_simulated_checkout(d, monime.fmt_sle(d.get("amount_minor") or monime.sll_to_minor(d["amount_sll"])))
        self.send_html(html)

    def simulate_checkout_action(self, path):
        """POST from the fake page: outcome=success|fail|cancel"""
        if monime.mode() != "simulation":
            return self.send_error_page(404, "Not found")
        sid = path.replace("/pay/simulate/", "").strip("/")
        data = self.parse_form()
        outcome = sec.clean_str(data.get("outcome"), 10)
        if outcome not in ("success", "fail", "cancel"):
            return self.send_error_page(400, "Bad outcome")
        row = db.query_one("SELECT * FROM donations WHERE checkout_session_id=?", (sid,))
        if not row or not str(sid).startswith("sim_") or row["gateway_mode"] != "simulation":
            return self.send_error_page(404, "Simulated checkout not found")
        ref = row["reference"]
        new_gw = {"success": "completed", "cancel": "cancelled", "fail": "expired"}.get(outcome, "pending")
        db.execute("UPDATE donations SET gateway_status=? WHERE reference=?", (new_gw, ref))
        db.payment_event(ref, sid, "simulate", f"simulated.{outcome}", new_gw, 1,
                         {"provider": data.get("provider"), "phone": data.get("phone")}, self.client_ip())
        # Simulated "webhook": apply immediately, then bounce like Monime would
        self._verify_donation(ref, source="simulate", ip=self.client_ip())
        return self.send_redirect(f"/donate/return?ref={ref}&outcome={'success' if outcome == 'success' else 'cancel'}")

    def api_list_projects(self):
        rows = db.query_all(
            "SELECT id, title, slug, category, district, description, "
            "image_url, status, funded_percent, start_year, end_year, author "
            "FROM projects ORDER BY status, id DESC"
        )
        self.send_json([dict(r) for r in rows])

    # ------------------------------------------------------------------
    # DYNAMIC PROJECT ARTICLE PAGE
    # ------------------------------------------------------------------
    def project_article(self, path):
        """Serve a full-article page for /projects/<slug>"""
        slug = path.replace("/projects/", "").strip("/")

        # Sanitize: only allow safe slug characters
        import re as _re
        if not slug or not _re.match(r'^[a-z0-9-]+$', slug):
            return self.send_error_page(404, "Project not found")

        row = db.query_one("SELECT * FROM projects WHERE slug = ?", (slug,))
        if not row:
            return self.send_error_page(404, "Project not found")

        p = dict(row)

        # Related projects (same category, different slug, limit 3)
        related = db.query_all(
            "SELECT title, slug, image_url, district, category FROM projects "
            "WHERE category = ? AND slug != ? LIMIT 3",
            (p["category"], slug),
        )

        html = self._render_project_article(p, related)
        self.send_html(html, use_partials=True, page_key="projects")

    def _render_project_article(self, p, related):
        """Build the full HTML article page for a project."""

        # Status badge colours
        status_colour = "#16a34a" if p["status"] == "current" else "#6b7280"
        status_label  = "Active" if p["status"] == "current" else "Completed"

        # Progress bar (only for current projects)
        progress_html = ""
        if p["status"] == "current" and p.get("funded_percent") is not None:
            pct = int(p["funded_percent"])
            progress_html = f"""
            <div class="art-funding">
              <div class="art-funding-label">
                <span>Project Funding</span>
                <strong>{pct}% secured</strong>
              </div>
              <div class="art-bar"><div class="art-bar-fill" style="width:{pct}%"></div></div>
            </div>"""

        # Years range
        years = ""
        if p.get("start_year") and p.get("end_year"):
            years = f"{p['start_year']}–{p['end_year']}"
        elif p.get("start_year"):
            years = str(p["start_year"])

        # Article content — NOTE: this comes from the database (admin-entered).
        # We trust it here because only authenticated admins can write it.
        # For a real production app you'd sanitize with a whitelist HTML library.
        # Admin-authored HTML is passed through a whitelist sanitiser: formatting
        # survives, scripts / event handlers / javascript: URLs do not.
        article_body = sec.sanitize_html(p.get("article_content") or "") or "<p>Article content coming soon.</p>"

        # Related cards
        related_cards = ""
        for r in related:
            cat_color = {
                "health":"#0ea5e9","education":"#8b5cf6",
                "livelihoods":"#16a34a","youth":"#f59e0b"
            }.get(r["category"] or "", "#f36f21")
            related_cards += f"""
            <a href="/projects/{sec.esc(r['slug'])}" class="rel-card">
              <div class="rel-img"
                   style="background-image:url('{sec.esc(r['image_url'] or '')}')">
                <span class="rel-cat"
                      style="background:{cat_color}">{sec.esc(r['category'] or '').title()}</span>
              </div>
              <div class="rel-body">
                <h4>{sec.esc(r['title'])}</h4>
                <span>📍 {sec.esc(r['district'] or '')}</span>
              </div>
            </a>"""

        related_section = ""
        if related_cards:
            related_section = f"""
            <section class="related-section">
              <h3>Related Projects</h3>
              <div class="related-grid">{related_cards}</div>
            </section>"""

        banner = p.get("banner_url") or p.get("image_url") or ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{sec.esc(p['title'])} | CBN Sierra Leone</title>
  <meta name="description" content="{sec.esc(p.get('description',''))}"/>
  <link rel="stylesheet" href="/styles.css"/>
  <style>
    /* ── Article page extra styles ── */
    .art-hero {{
      min-height: 420px;
      background: linear-gradient(rgba(10,42,74,.72),rgba(10,42,74,.72)),
                  url('{sec.esc(banner)}') center/cover no-repeat;
      display:flex; align-items:flex-end; padding-bottom:0;
    }}
    .art-hero-inner {{
      width:100%; max-width:1200px; margin:0 auto; padding:0 20px 0;
    }}
    .art-badge {{
      display:inline-flex; align-items:center; gap:8px;
      background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.25);
      color:#fff; padding:6px 14px; border-radius:40px;
      font-size:.78rem; font-weight:700; letter-spacing:1.2px;
      text-transform:uppercase; margin-bottom:16px;
    }}
    .art-badge .dot {{
      width:8px; height:8px; border-radius:50%;
      background:{status_colour}; display:inline-block;
    }}
    .art-hero h1 {{
      color:#fff; font-size:clamp(1.8rem,4vw,3rem);
      line-height:1.2; margin-bottom:20px; max-width:820px;
    }}
    .art-meta-bar {{
      background:#fff; border-top:4px solid #f36f21;
      padding:18px 0; margin-bottom:0;
    }}
    .art-meta-inner {{
      max-width:1200px; margin:0 auto; padding:0 20px;
      display:flex; flex-wrap:wrap; gap:28px; align-items:center;
    }}
    .art-meta-item {{
      display:flex; flex-direction:column;
    }}
    .art-meta-item .label {{
      font-size:.68rem; font-weight:700; text-transform:uppercase;
      letter-spacing:1.5px; color:#6b7280;
    }}
    .art-meta-item .value {{
      font-size:.95rem; font-weight:700; color:#0a2a4a; margin-top:2px;
    }}
    .art-layout {{
      max-width:1200px; margin:0 auto; padding:48px 20px;
      display:grid; grid-template-columns:1fr 320px; gap:56px;
      align-items:flex-start;
    }}
    /* Article body typography */
    .art-body h2 {{
      color:#0a2a4a; font-size:1.5rem; margin:36px 0 14px;
      padding-bottom:8px; border-bottom:2px solid #eef1f5;
    }}
    .art-body h2:first-child {{ margin-top:0; }}
    .art-body h3 {{ color:#0a2a4a; font-size:1.15rem; margin:24px 0 10px; }}
    .art-body p  {{ color:#374151; line-height:1.8; margin-bottom:16px; }}
    .art-body ul {{ margin:0 0 18px 22px; }}
    .art-body ul li {{ color:#374151; line-height:1.7; margin-bottom:8px; }}
    .art-body blockquote {{
      margin:28px 0; padding:20px 28px;
      background:#f7f8fa; border-left:4px solid #f36f21;
      border-radius:0 6px 6px 0;
    }}
    .art-body blockquote p {{
      font-style:italic; font-size:1.08rem; color:#374151;
      margin-bottom:8px;
    }}
    .art-body blockquote footer {{
      font-size:.85rem; color:#6b7280; font-style:normal;
    }}
    /* Sidebar */
    .art-sidebar {{ position:sticky; top:130px; }}
    .art-sidebar .sidebar-card {{
      background:#fff; border:1px solid #dfe4ec; border-radius:6px;
      overflow:hidden; margin-bottom:22px;
    }}
    .art-sidebar .sc-head {{
      background:#0a2a4a; color:#fff; padding:12px 18px;
      font-size:.8rem; font-weight:700; text-transform:uppercase;
      letter-spacing:1.2px;
    }}
    .art-sidebar .sc-body {{ padding:18px; }}
    .art-sidebar .sc-body p {{
      color:#374151; font-size:.92rem; line-height:1.6; margin-bottom:14px;
    }}
    .art-sidebar .sc-body .btn {{
      width:100%; text-align:center; display:block;
    }}
    .art-funding {{
      padding:16px 18px; background:#f7f8fa;
      border-top:1px solid #eef1f5;
    }}
    .art-funding-label {{
      display:flex; justify-content:space-between;
      font-size:.82rem; color:#374151; margin-bottom:8px;
    }}
    .art-bar {{
      height:8px; background:#dfe4ec; border-radius:4px; overflow:hidden;
    }}
    .art-bar-fill {{
      height:100%; background:linear-gradient(90deg,#f36f21,#f7b500);
      border-radius:4px;
    }}
    .art-stat-grid {{
      display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px;
    }}
    .art-stat {{
      background:#f7f8fa; border-radius:5px; padding:12px;
      text-align:center;
    }}
    .art-stat .n {{
      font-size:1.4rem; font-weight:800; color:#f36f21; line-height:1;
    }}
    .art-stat .l {{
      font-size:.68rem; color:#6b7280; text-transform:uppercase;
      letter-spacing:1px; margin-top:4px;
    }}
    /* Related projects */
    .related-section {{
      border-top:2px solid #eef1f5; padding-top:36px; margin-top:8px;
    }}
    .related-section h3 {{
      color:#0a2a4a; font-size:1.25rem; margin-bottom:20px;
    }}
    .related-grid {{
      display:grid; grid-template-columns:repeat(3,1fr); gap:20px;
    }}
    .rel-card {{
      border-radius:6px; overflow:hidden; border:1px solid #dfe4ec;
      background:#fff; text-decoration:none;
      transition:transform .2s, box-shadow .2s;
      display:flex; flex-direction:column;
    }}
    .rel-card:hover {{ transform:translateY(-4px); box-shadow:0 8px 24px rgba(0,0,0,.1); }}
    .rel-img {{
      height:130px; background-size:cover; background-position:center;
      position:relative;
    }}
    .rel-cat {{
      position:absolute; top:10px; left:10px; color:#fff;
      font-size:.65rem; font-weight:700; letter-spacing:1px;
      text-transform:uppercase; padding:3px 8px; border-radius:3px;
    }}
    .rel-body {{ padding:12px 14px; }}
    .rel-body h4 {{ color:#0a2a4a; font-size:.95rem; margin-bottom:4px; }}
    .rel-body span {{ color:#6b7280; font-size:.8rem; }}
    /* Back link */
    .art-breadcrumb {{
      background:#f7f8fa; border-bottom:1px solid #eef1f5;
      padding:12px 0;
    }}
    .art-breadcrumb .container {{
      max-width:1200px; margin:0 auto; padding:0 20px;
      font-size:.85rem; color:#6b7280;
    }}
    .art-breadcrumb a {{ color:#f36f21; text-decoration:none; }}
    .art-breadcrumb a:hover {{ text-decoration:underline; }}
    @media (max-width:900px) {{
      .art-layout {{ grid-template-columns:1fr; gap:30px; }}
      .art-sidebar {{ position:static; }}
      .related-grid {{ grid-template-columns:1fr 1fr; }}
    }}
    @media (max-width:560px) {{
      .art-hero {{ min-height:300px; }}
      .related-grid {{ grid-template-columns:1fr; }}
      .art-meta-inner {{ gap:16px; }}
    }}
  </style>
</head>
<body>

  <!-- ── HEADER (same nav structure as all pages) ── -->
  <header class="site-header">
    <div class="utility-bar">
      <div class="container">
        <a href="/contact.html" class="util-contact">Contact Us</a>
        <div class="lang-switcher" aria-label="Language selector">
          <span class="lang-label">🌐</span>
          <button class="lang-btn active" data-lang="EN" aria-pressed="true" title="English">EN</button>
          <button class="lang-btn" data-lang="KR" aria-pressed="false" title="Krio">KR</button>
          <button class="lang-btn" data-lang="FR" aria-pressed="false" title="Français">FR</button>
        </div>
        <button class="util-search-btn" id="searchToggle" aria-label="Open search (Ctrl+K)">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
          <span>Search</span>
        </button>
      </div>
    </div>
    <nav class="main-nav" aria-label="Primary">
      <div class="container">
        <a href="/" class="brand">
          <span class="brand-mark">CBN</span>
          <span class="brand-text">
            <span class="brand-name">Community Builders Network</span>
            <span class="brand-tag">Sierra Leone</span>
          </span>
        </a>
        <button class="menu-toggle" aria-label="Toggle menu" aria-expanded="false">
          <span></span><span></span><span></span>
        </button>
        <ul class="nav-list">
          <li><a href="/">Home</a></li>
          <li><a href="/about.html">About Us</a></li>
          <li><a href="/projects.html" class="active">Projects</a></li>
          <li><a href="/get-involved.html">Get Involved</a></li>
          <li><a href="/news.html">News &amp; Updates</a></li>
          <li><a href="/contact.html">Contact</a></li>
          <li><a href="#" class="nav-cta">Donate</a></li>
        </ul>
      </div>
    </nav>
  </header>

  <!-- ── BREADCRUMB ── -->
  <div class="art-breadcrumb">
    <div class="container">
      <a href="/">Home</a> /
      <a href="/projects.html">Projects</a> /
      {sec.esc(p['title'])}
    </div>
  </div>

  <!-- ── HERO BANNER ── -->
  <div class="art-hero">
    <div class="art-hero-inner">
      <div class="art-badge">
        <span class="dot"></span>
        {sec.esc(status_label)}
        &nbsp;·&nbsp;
        {sec.esc((p.get('category') or '').replace('-',' ').title())}
      </div>
      <h1>{sec.esc(p['title'])}</h1>
    </div>
  </div>

  <!-- ── META BAR ── -->
  <div class="art-meta-bar">
    <div class="art-meta-inner">
      <div class="art-meta-item">
        <span class="label">District</span>
        <span class="value">📍 {sec.esc(p.get('district') or 'Sierra Leone')}</span>
      </div>
      <div class="art-meta-item">
        <span class="label">Period</span>
        <span class="value">🗓 {sec.esc(years or '—')}</span>
      </div>
      <div class="art-meta-item">
        <span class="label">Category</span>
        <span class="value">{sec.esc((p.get('category') or '').title())}</span>
      </div>
      <div class="art-meta-item">
        <span class="label">Author</span>
        <span class="value">✍ {sec.esc(p.get('author') or 'CBN Team')}</span>
      </div>
      <div class="art-meta-item">
        <span class="label">Status</span>
        <span class="value"
              style="color:{status_colour}">● {sec.esc(status_label)}</span>
      </div>
    </div>
  </div>

  <!-- ── MAIN CONTENT ── -->
  <div class="art-layout">

    <!-- Article body (DB content) -->
    <article class="art-body">
      <p style="font-size:1.12rem;color:#374151;line-height:1.8;
                border-bottom:1px solid #eef1f5;padding-bottom:24px;
                margin-bottom:28px;">
        <strong>{sec.esc(p.get('description',''))}</strong>
      </p>
      {article_body}
      {related_section}
    </article>

    <!-- Sidebar -->
    <aside class="art-sidebar">

      <!-- Quick stats -->
      <div class="sidebar-card">
        <div class="sc-head">Project at a Glance</div>
        <div class="art-stat-grid" style="padding:16px 18px 0;">
          <div class="art-stat">
            <div class="n">{sec.esc(str(p.get('start_year') or '—'))}</div>
            <div class="l">Started</div>
          </div>
          <div class="art-stat">
            <div class="n">{sec.esc(str(p.get('end_year') or '—'))}</div>
            <div class="l">{'Target End' if p['status']=='current' else 'Completed'}</div>
          </div>
        </div>
        {progress_html}
        <div class="sc-body" style="border-top:1px solid #eef1f5;">
          <p>{sec.esc(p.get('description',''))}</p>
        </div>
      </div>

      <!-- Donate CTA -->
      <div class="sidebar-card">
        <div class="sc-head">Support This Project</div>
        <div class="sc-body">
          <p>Your donation goes directly to communities in Sierra Leone. Every contribution matters.</p>
          <a href="/get-involved.html" class="btn btn-primary">Donate Now</a>
          <a href="/get-involved.html#volunteer"
             class="btn btn-ghost" style="margin-top:10px;">Volunteer</a>
        </div>
      </div>

      <!-- Share -->
      <div class="sidebar-card">
        <div class="sc-head">Share This Article</div>
        <div class="sc-body">
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <a href="https://twitter.com/intent/tweet?text={sec.esc(p['title'])}&url="
               class="btn btn-ghost btn-sm" target="_blank" rel="noopener">𝕏 Twitter</a>
            <a href="https://facebook.com/sharer/sharer.php?u="
               class="btn btn-ghost btn-sm" target="_blank" rel="noopener">f Facebook</a>
            <a href="https://www.linkedin.com/shareArticle?title={sec.esc(p['title'])}"
               class="btn btn-ghost btn-sm" target="_blank" rel="noopener">in LinkedIn</a>
          </div>
        </div>
      </div>

      <!-- Back link -->
      <a href="/projects.html"
         style="display:flex;align-items:center;gap:8px;
                color:#0a2a4a;font-weight:700;font-size:.88rem;
                text-decoration:none;">
        ← Back to All Projects
      </a>
    </aside>
  </div>

  <!-- ── FOOTER ── -->
  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-about">
          <a href="/" class="brand" style="margin-bottom:16px;">
            <span class="brand-mark">CBN</span>
            <span class="brand-text">
              <span class="brand-name" style="color:#fff;">Community Builders Network</span>
              <span class="brand-tag" style="color:#94a3b8;">Sierra Leone</span>
            </span>
          </a>
          <p>Empowering Sierra Leonean communities through education, health, livelihoods and inclusive leadership since 2010.</p>
        </div>
        <div>
          <h5>Explore</h5>
          <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/about.html">About Us</a></li>
            <li><a href="/projects.html">Projects</a></li>
            <li><a href="/news.html">News</a></li>
            <li><a href="/contact.html">Contact</a></li>
          </ul>
        </div>
        <div>
          <h5>Get Involved</h5>
          <ul>
            <li><a href="/get-involved.html#volunteer">Volunteer</a></li>
            <li><a href="/get-involved.html#partner">Partner</a></li>
            <li><a href="/get-involved.html">Donate</a></li>
          </ul>
        </div>
        <div>
          <h5>Contact</h5>
          <ul>
            <li>15 Wilkinson Road, Freetown</li>
            <li>+232 76 000 000</li>
            <li><a href="mailto:info@cbn-sl.org">info@cbn-sl.org</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        © <span id="year"></span> Community Builders Network — Sierra Leone
      </div>
    </div>
  </footer>

  <script src="/script.js"></script>
</body>
</html>"""

    def api_list_blog(self):
        """Published posts, newest publication first. Index 0 is the featured post."""
        rows = db.query_all(
            "SELECT id,title,slug,category,excerpt,content,author,image_url,"
            "       created_at,updated_at,published_at "
            "FROM blog_posts WHERE published=1 "
            "ORDER BY COALESCE(published_at, created_at) DESC, id DESC")
        out = []
        for r in rows:
            d = dict(r)
            plain = _plain_text(d.pop("content"))
            words = len(plain.split())
            d["read_time"]    = max(1, round(words / 200)) if words else 1
            d["published_at"] = d["published_at"] or d["created_at"]
            d["url"]          = "/blog/" + d["slug"]
            if not (d.get("excerpt") or "").strip():
                d["excerpt"] = (plain[:180].rstrip() + "…") if len(plain) > 180 else plain
            out.append(d)
        self.send_json(out)

    # ------------------------------------------------------------------
    # DYNAMIC BLOG ARTICLE PAGE  —  /blog/<slug>
    # ------------------------------------------------------------------
    def blog_article(self, path):
        slug = path.replace("/blog/", "").strip("/")
        import re as _re
        if not slug or not _re.match(r"^[a-z0-9-]+$", slug):
            return self.send_error_page(404, "Article not found")

        row = db.query_one("SELECT * FROM blog_posts WHERE slug = ?", (slug,))
        if not row:
            return self.send_error_page(404, "Article not found")
        p = dict(row)

        # Drafts are visible only to a logged-in admin (handy for previewing)
        is_admin_preview = False
        if not p.get("published"):
            token = self.get_cookies().get(sec.COOKIE_SESSION)
            if not sec.get_session(token, self.client_ip(), self.user_agent()):
                return self.send_error_page(404, "Article not found")
            is_admin_preview = True

        related = db.query_all(
            "SELECT title, slug, image_url, category, published_at, created_at "
            "FROM blog_posts WHERE published = 1 AND slug != ? "
            "ORDER BY (category = ?) DESC, COALESCE(published_at, created_at) DESC "
            "LIMIT 3",
            (slug, p.get("category")),
        )
        self.send_html(self._render_blog_article(p, related, is_admin_preview),
                       use_partials=True, page_key="news")

    def _render_blog_article(self, p, related, is_admin_preview=False):
        CAT = {"field": "Field Notes", "policy": "Policy",
               "voices": "Voices", "research": "Research"}
        cat_label = CAT.get(p.get("category") or "", (p.get("category") or "Update").title())
        date_str  = _fmt_date(p.get("published_at") or p.get("created_at"))
        plain     = _plain_text(p.get("content"))
        read_min  = max(1, round(len(plain.split()) / 200)) if plain else 1
        body_html = _format_blog_content(p.get("content"))
        banner    = p.get("image_url") or \
            "https://images.pexels.com/photos/20407106/pexels-photo-20407106.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400"
        page_url  = f"/blog/{p['slug']}"

        related_cards = "".join(
            f"""<a href="/blog/{sec.esc(r['slug'])}" class="rel-card">
                  <div class="rel-img" style="background-image:url('{sec.esc(r['image_url'] or banner)}')">
                    <span class="rel-cat">{sec.esc(CAT.get(r['category'] or '', (r['category'] or 'Update').title()))}</span>
                  </div>
                  <div class="rel-body">
                    <h4>{sec.esc(r['title'])}</h4>
                    <span>📅 {sec.esc(_fmt_date(r['published_at'] or r['created_at']))}</span>
                  </div>
                </a>"""
            for r in related
        )
        related_section = (
            f'<section class="related-section"><h3>More from the Blog</h3>'
            f'<div class="related-grid">{related_cards}</div></section>'
            if related_cards else ""
        )
        draft_banner = (
            '<div style="background:#fef3c7;color:#92400e;text-align:center;padding:10px;'
            'font-weight:700;font-size:.85rem;letter-spacing:1px;text-transform:uppercase;">'
            'Draft preview — only visible to logged-in admins</div>'
            if is_admin_preview else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{sec.esc(p['title'])} | CBN Blog</title>
  <meta name="description" content="{sec.esc(p.get('excerpt') or plain[:160])}"/>
  <link rel="stylesheet" href="/styles.css"/>
  <style>
    .art-breadcrumb {{ background:#f7f8fa; border-bottom:1px solid #eef1f5; padding:12px 0; }}
    .art-breadcrumb .container {{ font-size:.85rem; color:#6b7280; }}
    .art-breadcrumb a {{ color:#f36f21; text-decoration:none; }}
    .art-hero {{
      min-height:440px; display:flex; align-items:flex-end;
      background:linear-gradient(rgba(10,42,74,.25),rgba(10,42,74,.85)),
                 url('{sec.esc(banner)}') center/cover no-repeat;
    }}
    .art-hero-inner {{ width:100%; max-width:1200px; margin:0 auto; padding:0 20px 44px; }}
    .art-cat {{
      display:inline-block; background:#f36f21; color:#fff; font-size:.72rem; font-weight:700;
      letter-spacing:1.5px; text-transform:uppercase; padding:6px 12px; border-radius:3px; margin-bottom:16px;
    }}
    .art-hero h1 {{ color:#fff; font-size:clamp(1.8rem,4vw,3rem); line-height:1.2; max-width:860px; margin-bottom:16px; }}
    .art-meta {{ display:flex; flex-wrap:wrap; gap:22px; color:#e2e8f0; font-size:.85rem; letter-spacing:.5px; }}
    .art-meta strong {{ color:#fff; }}
    .art-layout {{
      max-width:1200px; margin:0 auto; padding:52px 20px;
      display:grid; grid-template-columns:1fr 320px; gap:56px; align-items:flex-start;
    }}
    .art-lead {{ font-size:1.15rem; color:#374151; line-height:1.75; border-left:4px solid #f36f21;
                 padding-left:20px; margin-bottom:32px; }}
    .art-body h2 {{ color:#0a2a4a; font-size:1.5rem; margin:36px 0 14px; padding-bottom:8px; border-bottom:2px solid #eef1f5; }}
    .art-body h3 {{ color:#0a2a4a; font-size:1.15rem; margin:24px 0 10px; }}
    .art-body p  {{ color:#374151; line-height:1.85; margin-bottom:18px; font-size:1.02rem; }}
    .art-body ul, .art-body ol {{ margin:0 0 18px 22px; }}
    .art-body li {{ color:#374151; line-height:1.7; margin-bottom:8px; }}
    .art-body img {{ max-width:100%; border-radius:6px; margin:10px 0 20px; }}
    .art-body blockquote {{ margin:28px 0; padding:20px 28px; background:#f7f8fa;
                            border-left:4px solid #f36f21; border-radius:0 6px 6px 0; font-style:italic; }}
    .art-author {{ display:flex; align-items:center; gap:14px; margin-top:40px; padding-top:24px; border-top:2px solid #eef1f5; }}
    .art-author .av {{ width:52px; height:52px; border-radius:50%; flex-shrink:0; display:grid; place-items:center;
                       background:linear-gradient(135deg,#f36f21,#f7b500); color:#fff; font-weight:800; }}
    .art-author small {{ display:block; color:#6b7280; font-size:.78rem; text-transform:uppercase; letter-spacing:1.2px; }}
    .art-author strong {{ color:#0a2a4a; }}
    .art-sidebar {{ position:sticky; top:130px; }}
    .sidebar-card {{ background:#fff; border:1px solid #dfe4ec; border-radius:6px; overflow:hidden; margin-bottom:22px; }}
    .sidebar-card .sc-head {{ background:#0a2a4a; color:#fff; padding:12px 18px; font-size:.8rem; font-weight:700;
                              text-transform:uppercase; letter-spacing:1.2px; }}
    .sidebar-card .sc-body {{ padding:18px; }}
    .sidebar-card .sc-body p {{ color:#374151; font-size:.92rem; line-height:1.6; margin-bottom:14px; }}
    .sidebar-card .btn {{ display:block; text-align:center; width:100%; }}
    .share-row {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .related-section {{ border-top:2px solid #eef1f5; padding-top:36px; margin-top:40px; }}
    .related-section h3 {{ color:#0a2a4a; font-size:1.25rem; margin-bottom:20px; }}
    .related-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:20px; }}
    .rel-card {{ border-radius:6px; overflow:hidden; border:1px solid #dfe4ec; background:#fff; text-decoration:none;
                 display:flex; flex-direction:column; transition:transform .2s, box-shadow .2s; }}
    .rel-card:hover {{ transform:translateY(-4px); box-shadow:0 8px 24px rgba(0,0,0,.1); text-decoration:none; }}
    .rel-img {{ height:130px; background-size:cover; background-position:center; position:relative; }}
    .rel-cat {{ position:absolute; top:10px; left:10px; background:#f36f21; color:#fff; font-size:.65rem; font-weight:700;
                letter-spacing:1px; text-transform:uppercase; padding:3px 8px; border-radius:3px; }}
    .rel-body {{ padding:12px 14px; }}
    .rel-body h4 {{ color:#0a2a4a; font-size:.95rem; margin-bottom:4px; }}
    .rel-body span {{ color:#6b7280; font-size:.8rem; }}
    @media (max-width:900px) {{
      .art-layout {{ grid-template-columns:1fr; gap:30px; }}
      .art-sidebar {{ position:static; }}
      .related-grid {{ grid-template-columns:1fr 1fr; }}
    }}
    @media (max-width:560px) {{
      .art-hero {{ min-height:320px; }}
      .related-grid {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  {draft_banner}
  <header class="site-header">
    <div class="utility-bar">
      <div class="container">
        <a href="/contact.html" class="util-contact">Contact Us</a>
        <div class="lang-switcher" aria-label="Language selector">
          <span class="lang-label">🌐</span>
          <button class="lang-btn active" data-lang="EN" aria-pressed="true" title="English">EN</button>
          <button class="lang-btn" data-lang="KR" aria-pressed="false" title="Krio">KR</button>
          <button class="lang-btn" data-lang="FR" aria-pressed="false" title="Français">FR</button>
        </div>
        <button class="util-search-btn" id="searchToggle" aria-label="Open search (Ctrl+K)">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
          <span>Search</span>
        </button>
      </div>
    </div>
    <nav class="main-nav" aria-label="Primary">
      <div class="container">
        <a href="/" class="brand">
          <span class="brand-mark">CBN</span>
          <span class="brand-text">
            <span class="brand-name">Community Builders Network</span>
            <span class="brand-tag">Sierra Leone</span>
          </span>
        </a>
        <button class="menu-toggle" aria-label="Toggle menu" aria-expanded="false">
          <span></span><span></span><span></span>
        </button>
        <ul class="nav-list">
          <li><a href="/">Home</a></li>
          <li><a href="/about.html">About Us</a></li>
          <li><a href="/projects.html">Projects</a></li>
          <li><a href="/get-involved.html">Get Involved</a></li>
          <li><a href="/news.html" class="active">News &amp; Updates</a></li>
          <li><a href="/contact.html">Contact</a></li>
          <li><a href="/donate.html" class="nav-cta">Donate</a></li>
        </ul>
      </div>
    </nav>
  </header>

  <div class="art-breadcrumb">
    <div class="container">
      <a href="/">Home</a> / <a href="/news.html">News &amp; Updates</a> /
      <a href="/news.html#blog">Blog</a> / {sec.esc(p['title'])}
    </div>
  </div>

  <div class="art-hero">
    <div class="art-hero-inner">
      <span class="art-cat">{sec.esc(cat_label)}</span>
      <h1>{sec.esc(p['title'])}</h1>
      <div class="art-meta">
        <span>📅 <strong>{sec.esc(date_str)}</strong></span>
        <span>✍ By <strong>{sec.esc(p.get('author') or 'CBN Team')}</strong></span>
        <span>⏱ {read_min} min read</span>
      </div>
    </div>
  </div>

  <div class="art-layout">
    <article class="art-body">
      {f'<p class="art-lead">{sec.esc(p["excerpt"])}</p>' if (p.get("excerpt") or "").strip() else ""}
      {body_html}
      <div class="art-author">
        <div class="av">{sec.esc((p.get('author') or 'C')[:1].upper())}</div>
        <div>
          <small>Written by</small>
          <strong>{sec.esc(p.get('author') or 'CBN Team')}</strong>
          <div style="color:#6b7280;font-size:.85rem;">Community Builders Network — Sierra Leone</div>
        </div>
      </div>
      {related_section}
    </article>

    <aside class="art-sidebar">
      <div class="sidebar-card">
        <div class="sc-head">Share This Article</div>
        <div class="sc-body">
          <div class="share-row">
            <a class="btn btn-ghost btn-sm" target="_blank" rel="noopener"
               href="https://twitter.com/intent/tweet?text={urllib.parse.quote(p['title'])}&url={urllib.parse.quote(page_url)}">𝕏 Twitter</a>
            <a class="btn btn-ghost btn-sm" target="_blank" rel="noopener"
               href="https://www.facebook.com/sharer/sharer.php?u={urllib.parse.quote(page_url)}">f Facebook</a>
            <a class="btn btn-ghost btn-sm" target="_blank" rel="noopener"
               href="https://www.linkedin.com/shareArticle?mini=true&title={urllib.parse.quote(p['title'])}&url={urllib.parse.quote(page_url)}">in LinkedIn</a>
          </div>
        </div>
      </div>
      <div class="sidebar-card">
        <div class="sc-head">Support Our Work</div>
        <div class="sc-body">
          <p>Stories like this one are only possible because of people like you.</p>
          <a href="/donate.html" class="btn btn-primary">Donate Now</a>
          <a href="/get-involved.html#volunteer" class="btn btn-ghost" style="margin-top:10px;">Volunteer</a>
        </div>
      </div>
      <div class="sidebar-card">
        <div class="sc-head">Stay Updated</div>
        <div class="sc-body">
          <p>Get new field stories and event invitations in your inbox once a month.</p>
          <a href="/news.html#newsletter" class="btn btn-navy">Subscribe to Newsletter</a>
        </div>
      </div>
      <a href="/news.html#blog" style="display:flex;align-items:center;gap:8px;color:#0a2a4a;
         font-weight:700;font-size:.88rem;text-decoration:none;">← Back to all posts</a>
    </aside>
  </div>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-about">
          <a href="/" class="brand" style="margin-bottom:16px;">
            <span class="brand-mark">CBN</span>
            <span class="brand-text">
              <span class="brand-name" style="color:#fff;">Community Builders Network</span>
              <span class="brand-tag" style="color:#94a3b8;">Sierra Leone</span>
            </span>
          </a>
          <p>Empowering Sierra Leonean communities through education, health, livelihoods and inclusive leadership since 2010.</p>
        </div>
        <div>
          <h5>Explore</h5>
          <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/about.html">About Us</a></li>
            <li><a href="/projects.html">Projects</a></li>
            <li><a href="/news.html">News &amp; Updates</a></li>
            <li><a href="/contact.html">Contact</a></li>
          </ul>
        </div>
        <div>
          <h5>Get Involved</h5>
          <ul>
            <li><a href="/get-involved.html#volunteer">Volunteer</a></li>
            <li><a href="/get-involved.html#partner">Partner with Us</a></li>
            <li><a href="/donate.html">Donate</a></li>
          </ul>
        </div>
        <div>
          <h5>Contact</h5>
          <ul>
            <li>15 Wilkinson Road, Freetown</li>
            <li><a href="tel:+23276000000">+232 76 000 000</a></li>
            <li><a href="mailto:info@cbn-sl.org">info@cbn-sl.org</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        © <span id="year"></span> Community Builders Network — Sierra Leone
      </div>
    </div>
  </footer>
  <script src="/script.js"></script>
</body>
</html>"""

    def api_list_events(self):
        rows = db.query_all(
            "SELECT * FROM events WHERE event_date >= date('now') ORDER BY event_date")
        self.send_json([dict(r) for r in rows])

    # ==============================================================
    # ADMIN — AUTHENTICATION
    # ==============================================================
    def _require_admin(self):
        """Return (session_row, admin) or send redirect to login and return None."""
        token = self.get_cookies().get(sec.COOKIE_SESSION)
        session = sec.get_session(token, self.client_ip(), self.user_agent())
        if not session:
            self.send_redirect("/admin/login")
            return None
        
        # Check if admin must change password (forced on first login with default creds)
        admin = db.query_one(
            "SELECT must_change_password FROM admins WHERE id=?",
            (session["admin_id"],))
        if admin and admin["must_change_password"]:
            # Redirect to password change page (unless already there)
            if not self.path.startswith("/admin/password"):
                self.send_redirect("/admin/password?next=" + urllib.parse.quote(self.path))
                return None
        
        return session

    def admin_login_page(self, error=None, username=""):
        # Give every login page a fresh CSRF via a temp cookie-less token.
        # We use a "pre-session" CSRF stored in a short-lived cookie.
        cookies = self.get_cookies()
        pre_csrf = cookies.get("cbn_pre_csrf")
        set_cookies = []
        if not pre_csrf:
            import secrets as _s
            pre_csrf = _s.token_urlsafe(32)
            set_cookies.append(sec.build_cookie(
                "cbn_pre_csrf", pre_csrf, http_only=True,
                max_age=600, same_site="Strict"))
        rate_limited = sec.is_login_rate_limited(self.client_ip())
        html = ui.render_login(pre_csrf, error=error,
                               rate_limited=rate_limited, username=username)
        self.send_html(html, cookies=set_cookies)

    def admin_login_submit(self):
        data = self.parse_form()
        submitted_csrf = sec.clean_str(data.get("csrf_token"), 100)
        cookie_csrf    = self.get_cookies().get("cbn_pre_csrf", "")
        if not sec.constant_eq(submitted_csrf, cookie_csrf):
            return self.admin_login_page(error="Security check failed. Please try again.")

        if sec.is_login_rate_limited(self.client_ip()):
            return self.admin_login_page()

        username = sec.clean_str(data.get("username"), 50)
        password = sec.clean_str(data.get("password"), 200)

        if not username or not password:
            sec.record_login_attempt(self.client_ip(), username, False)
            return self.admin_login_page(error="Enter your username and password.",
                                         username=username)

        row = db.query_one(
            "SELECT id,username,password_hash,password_salt FROM admins WHERE username=?",
            (username,))

        if not row or not sec.verify_password(password, row["password_salt"], row["password_hash"]):
            sec.record_login_attempt(self.client_ip(), username, False)
            return self.admin_login_page(
                error="Invalid username or password.", username=username)

        # Login OK
        sec.record_login_attempt(self.client_ip(), username, True)
        db.execute("UPDATE admins SET last_login=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
        session_token, csrf = sec.create_session(row["id"], self.client_ip(), self.user_agent())
        db.log_audit(row["id"], "login", f"user={username}", self.client_ip())
        logger.info(f"Admin login successful: {username} from {self.client_ip()}")

        cookies = [
            sec.build_cookie(sec.COOKIE_SESSION, session_token,
                             http_only=True, max_age=sec.SESSION_DURATION_HR*3600),
            sec.build_cookie("cbn_pre_csrf", "", http_only=True, max_age=0),  # clear
        ]
        
        # If user logged in with default creds, force password change
        user_row = db.query_one("SELECT must_change_password FROM admins WHERE id=?", (row["id"],))
        if user_row and user_row["must_change_password"]:
            self.send_redirect("/admin/password", cookies=cookies)
        else:
            self.send_redirect("/admin", cookies=cookies)

    def admin_logout(self):
        token = self.get_cookies().get(sec.COOKIE_SESSION)
        session = sec.get_session(token, self.client_ip(), self.user_agent())
        # CSRF check (form submission)
        data = self.parse_form()
        if session and sec.check_csrf_admin(session, sec.clean_str(data.get("csrf_token"),100)):
            db.log_audit(session["admin_id"], "logout", "", self.client_ip())
            logger.info(f"Admin logout: {session['username']} from {self.client_ip()}")
            sec.destroy_session(token)
        cookies = [sec.build_cookie(sec.COOKIE_SESSION, "", http_only=True, max_age=0)]
        self.send_redirect("/admin/login", cookies=cookies)

    # ==============================================================
    # ADMIN — GET DISPATCH
    # ==============================================================
    def admin_dispatch_get(self, path):
        session = self._require_admin()
        if not session:
            return
        admin = {"id": session["admin_id"], "username": session["username"],
                 "email": session["email"]}
        csrf  = session["csrf_token"]
        flash = self._read_flash()

        # Parse ?edit=ID for edit forms
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        edit_id = qs.get("edit", [None])[0]

        if path == "/admin" or path == "/admin/":
            return self._page_dashboard(admin, csrf, flash)
        if path == "/admin/volunteers":
            rows = db.query_all("SELECT * FROM volunteers ORDER BY submitted_at DESC")
            ids = [r["id"] for r in rows]
            emails = db.latest_email_for("volunteers", ids,
                                         kinds=("volunteer_approved", "volunteer_rejected"))
            replies = db.inbound_unread_counts(ids)
            mode, message = mailer.status()
            return self.send_html(ui.render_volunteers(
                admin, csrf, rows, flash,
                emails=emails, mail_mode=message, mail_live=(mode == "live"),
                sender=mailer.sender_address(), replies=replies))
        if path == "/admin/inbox":
            return self._admin_inbox_page(admin, csrf, flash)
        if path == "/admin/payments":
            gw_mode, gw_msg = monime.status()
            events = db.query_all("SELECT * FROM payment_events ORDER BY id DESC LIMIT 40")
            recent = db.query_all("SELECT * FROM donations ORDER BY submitted_at DESC LIMIT 20")
            base = self._public_base_url()
            webhook = None
            if gw_mode in ("test", "live"):
                ok, hook = monime.find_our_webhook(f"{base}/api/monime/webhook")
                webhook = hook if ok else {"error": hook}
            return self.send_html(ui.render_payments(admin, csrf, monime.config_view(), gw_mode, gw_msg,
                                                     recent, events, public_base=base, webhook=webhook,
                                                     flash=flash))
        if path == "/admin/email":
            mode, message = mailer.status()
            log_rows = db.query_all("SELECT * FROM email_log ORDER BY id DESC LIMIT 25")
            outbox_rows = db.query_all(
                "SELECT * FROM outbox WHERE status IN ('pending','sending','failed') "
                "ORDER BY id DESC LIMIT 50")
            net_ok, net_why = (mailer.check_connectivity() if mode == "live" else (False, ""))
            return self.send_html(ui.render_email_settings(
                admin, csrf, mailer.current_config_view(), mode, message, log_rows,
                default_test_to=(admin.get("email") or mailer.sender_address()),
                flash=flash, outbox_rows=outbox_rows, outbox=db.outbox_summary(),
                net_ok=net_ok, net_why=net_why))
        if path == "/admin/contacts":
            rows = db.query_all("SELECT * FROM contacts ORDER BY submitted_at DESC")
            return self.send_html(ui.render_contacts(admin, csrf, rows, flash))
        if path == "/admin/donations":
            rows = db.query_all("SELECT * FROM donations ORDER BY submitted_at DESC")
            return self.send_html(ui.render_donations(admin, csrf, rows, flash))
        if path == "/admin/partners":
            rows = db.query_all("SELECT * FROM partners ORDER BY submitted_at DESC")
            return self.send_html(ui.render_partners(admin, csrf, rows, flash))
        if path == "/admin/subscribers":
            rows = db.query_all("SELECT * FROM subscribers ORDER BY subscribed_at DESC")
            return self.send_html(ui.render_subscribers(admin, csrf, rows, flash))
        if path == "/admin/blog":
            # Same ordering as the public /api/blog so the top row here is
            # always the featured post on news.html (drafts sort by creation).
            rows = db.query_all(
                "SELECT * FROM blog_posts "
                "ORDER BY COALESCE(published_at, created_at) DESC, id DESC")
            editing = None
            if edit_id and edit_id.isdigit():
                editing = db.query_one("SELECT * FROM blog_posts WHERE id=?", (int(edit_id),))
            return self.send_html(ui.render_blog(admin, csrf, rows,
                                                  editing=dict(editing) if editing else None,
                                                  flash=flash))
        if path == "/admin/events":
            rows = db.query_all("SELECT * FROM events ORDER BY event_date DESC")
            editing = None
            if edit_id and edit_id.isdigit():
                editing = db.query_one("SELECT * FROM events WHERE id=?", (int(edit_id),))
            return self.send_html(ui.render_events(admin, csrf, rows,
                                                    editing=dict(editing) if editing else None,
                                                    flash=flash))
        if path == "/admin/projects":
            rows = db.query_all("SELECT * FROM projects ORDER BY status, id DESC")
            editing = None
            if edit_id and edit_id.isdigit():
                editing = db.query_one("SELECT * FROM projects WHERE id=?", (int(edit_id),))
            return self.send_html(ui.render_projects(admin, csrf, rows,
                                                      editing=dict(editing) if editing else None,
                                                      flash=flash))
        if path == "/admin/password":
            return self.send_html(ui.render_password(admin, csrf, flash))

        return self.send_error_page(404, "Admin page not found")

    def _page_dashboard(self, admin, csrf, flash):
        # Pre-compute counts (avoids escaped quotes inside f-string expressions)
        vol_total   = db.query_one("SELECT COUNT(*) c FROM volunteers")["c"]
        vol_pending = db.query_one("SELECT COUNT(*) c FROM volunteers WHERE status='pending'")["c"]
        con_total   = db.query_one("SELECT COUNT(*) c FROM contacts")["c"]
        con_new     = db.query_one("SELECT COUNT(*) c FROM contacts WHERE status='new'")["c"]
        sub_total   = db.query_one("SELECT COUNT(*) c FROM subscribers WHERE active=1")["c"]
        blog_total  = db.query_one("SELECT COUNT(*) c FROM blog_posts")["c"]
        blog_pub    = db.query_one("SELECT COUNT(*) c FROM blog_posts WHERE published=1")["c"]

        stats = [
            ("Total Volunteers", vol_total, f"{vol_pending} pending"),
            ("Contact Messages", con_total, f"{con_new} new"),
            ("Newsletter Subs",  sub_total, ""),
            ("Blog Posts",       blog_total, f"{blog_pub} live"),
        ]
        recent = db.query_all("SELECT * FROM volunteers ORDER BY submitted_at DESC LIMIT 5")
        self.send_html(ui.render_dashboard(admin, csrf, stats, recent, flash))

    # ==============================================================
    # ADMIN — POST DISPATCH
    # ==============================================================
    def admin_dispatch_post(self, path):
        session = self._require_admin()
        if not session:
            return
        data = self.parse_form()
        # Every admin POST must present a valid CSRF token
        if not sec.check_csrf_admin(session, sec.clean_str(data.get("csrf_token"), 100)):
            return self.send_error_page(403, "Security check failed (CSRF)")

        admin_id = session["admin_id"]
        parts = [p for p in path.split("/") if p]  # e.g. ['admin','volunteer','5','status']

        # Order matters: specific patterns first, general last.

        # /admin/password  (special case, no ID)
        if path == "/admin/password":
            return self._admin_change_password(session, data, admin_id)

        # /admin/email  (save settings)   |   /admin/email/test  (send a test message)
        if path == "/admin/email":
            return self._admin_email_save(session, data, admin_id)
        if path == "/admin/email/test":
            return self._admin_email_test(session, data, admin_id)

        # /admin/payments (save) | /admin/payments/test | /admin/donation/{id}/verify
        if path == "/admin/payments":
            return self._admin_payments_save(data, admin_id)
        if path == "/admin/payments/test":
            ok, detail = monime.ping()
            db.log_audit(admin_id, "monime_test", detail, self.client_ip())
            return self._flash_back("ok" if ok else "err",
                                    ("Monime connection OK — " if ok else "Monime connection failed — ") + detail,
                                    "/admin/payments")
        if path == "/admin/payments/webhook/register":
            # Generate (or reuse) a strong HS256 secret, register the URL with Monime, persist the secret.
            base = self._public_base_url()
            url  = f"{base}/api/monime/webhook"
            secret = monime.get("CBN_MONIME_WEBHOOK_SECRET") or ("cbnwh_" + monime._secrets.token_urlsafe(48))
            ok, result = monime.register_webhook(url, secret)
            if not ok:
                db.log_audit(admin_id, "monime_webhook_register_failed", str(result)[:300], self.client_ip())
                return self._flash_back("err", f"Could not register the webhook: {result}", "/admin/payments")
            monime.save_config({"CBN_MONIME_WEBHOOK_SECRET": secret})
            db.log_audit(admin_id, "monime_webhook_registered",
                         f"url={url} id={result.get('id') if isinstance(result, dict) else '?'}", self.client_ip())
            return self._flash_back("ok", f"Webhook registered with Monime at {url} (HS256, secret saved). "
                                          f"Monime will now notify this server the instant a donation completes.",
                                    "/admin/payments")
        if path == "/admin/payments/webhook/delete":
            base = self._public_base_url()
            ok, hook = monime.find_our_webhook(f"{base}/api/monime/webhook")
            if ok and hook and hook.get("id"):
                ok2, detail = monime.delete_webhook(hook["id"])
                db.log_audit(admin_id, "monime_webhook_deleted", f"id={hook['id']} {detail}", self.client_ip())
                return self._flash_back("ok" if ok2 else "err", f"Webhook removed: {detail}", "/admin/payments")
            return self._flash_back("warn", "No webhook registered for this site's URL.", "/admin/payments")
        if len(parts) == 4 and parts[1] == "donation" and parts[2].isdigit() and parts[3] == "verify":
            row = db.query_one("SELECT reference FROM donations WHERE id=?", (int(parts[2]),))
            if not row:
                return self._flash_back("err", "Donation not found.", "/admin/donations")
            d, status_, detail = self._verify_donation(row["reference"], source="admin", ip=self.client_ip())
            db.log_audit(admin_id, "donation_verify", f"ref={row['reference']} → {status_} ({detail})", self.client_ip())
            return self._flash_back("ok" if status_ == "completed" else "info",
                                    f"{row['reference']}: {status_} — {detail}", "/admin/donations")

        # /admin/outbox/send-now | /admin/outbox/{id}/retry | /admin/outbox/{id}/cancel
        if path == "/admin/outbox/send-now":
            db.outbox_retry_now()
            net_ok, why = mailer.check_connectivity()
            if not net_ok:
                return self._flash_back("err", f"Still offline — {why}", "/admin/email")
            sent, requeued, failed = mailer.process_outbox(limit=100)
            db.log_audit(admin_id, "outbox_send_now", f"sent={sent} requeued={requeued} failed={failed}", self.client_ip())
            return self._flash_back("ok" if not failed else "warn",
                                    f"Outbox processed — {sent} sent, {requeued} still waiting, {failed} failed.",
                                    "/admin/email")
        if len(parts) == 4 and parts[1] == "outbox" and parts[2].isdigit():
            if parts[3] == "retry":
                db.outbox_retry_now(int(parts[2]))
                mailer.process_outbox(limit=5)
                return self._flash_back("ok", "Retrying that email now.", "/admin/email")
            if parts[3] == "cancel":
                db.outbox_cancel(int(parts[2]))
                row = db.query_one("SELECT email_log_id FROM outbox WHERE id=?", (int(parts[2]),))
                if row and row["email_log_id"]:
                    db.email_log_finish(row["email_log_id"], False, "cancelled by admin")
                return self._flash_back("ok", "Email cancelled.", "/admin/email")

        # /admin/inbox/sync | /admin/inbox/{id}/read | /admin/inbox/{id}/reply
        if path == "/admin/inbox/sync":
            return self._admin_inbox_sync(admin_id)
        if len(parts) == 4 and parts[1] == "inbox" and parts[2].isdigit():
            if parts[3] == "read":
                return self._admin_inbox_mark(int(parts[2]), data, admin_id)
            if parts[3] == "reply":
                return self._admin_inbox_reply(int(parts[2]), data, admin_id, session)

        # /admin/{kind}/{id}/edit  → update existing record
        if len(parts) == 4 and parts[0] == "admin" and parts[3] == "edit":
            return self._admin_update(parts[1], parts[2], data, admin_id)

        # /admin/{kind}/{id}/status  |  /admin/{kind}/{id}/delete  |  /admin/volunteer/{id}/notify
        if len(parts) == 4 and parts[0] == "admin" and parts[3] in ("status", "delete", "notify"):
            return self._admin_record_action(parts[1], parts[2], parts[3], data, admin_id)

        # /admin/{kind}/create  → new record
        if len(parts) == 3 and parts[0] == "admin" and parts[2] == "create":
            return self._admin_create(parts[1], data, admin_id)

        return self.send_error_page(404, "Admin action not found")

    def _admin_record_action(self, kind, rec_id, action, data, admin_id):
        table_map = {
            "volunteer": ("volunteers", ["pending","approved","rejected"]),
            "contact":   ("contacts",   ["new","read","replied","archived"]),
            "partner":   ("partners",   None),
            "subscriber":("subscribers",None),
            "donation":  ("donations",  ["pending","completed","failed","refunded"]),
            "blog":      ("blog_posts", None),
            "event":     ("events",     None),
            "project":   ("projects",   None),
        }
        if kind not in table_map or not rec_id.isdigit():
            return self.send_error_page(404, "Unknown record")
        table, valid_statuses = table_map[kind]
        rec_id = int(rec_id)

        if action == "delete":
            db.execute(f"DELETE FROM {table} WHERE id=?", (rec_id,))
            db.log_audit(admin_id, f"delete_{kind}", f"id={rec_id}", self.client_ip())
            self._set_flash("ok", f"{kind.title()} deleted.")
        elif action == "status" and valid_statuses:
            new_status = sec.clean_str(data.get("status"), 20)
            if new_status not in valid_statuses:
                return self.send_error_page(400, "Invalid status")

            # Read the previous status so we only email on a real change
            prev_row = db.query_one(f"SELECT status FROM {table} WHERE id=?", (rec_id,))
            prev_status = prev_row["status"] if prev_row else None

            db.execute(f"UPDATE {table} SET status=? WHERE id=?", (new_status, rec_id))
            db.log_audit(admin_id, f"update_{kind}_status",
                         f"id={rec_id} status={new_status}", self.client_ip())

            flash_msg = f"Status updated to {new_status}."

            # ── Volunteer decision → notify applicant by email ──────────
            if kind == "volunteer" and new_status in ("approved", "rejected") \
                    and new_status != prev_status:
                note = self._notify_volunteer_decision(rec_id, new_status, admin_id)
                if note:
                    flash_msg += " " + note

            self._set_flash("ok", flash_msg)

        elif action == "notify" and kind == "volunteer":
            # Manual (re)send of the decision email from the admin table
            row = db.query_one("SELECT status FROM volunteers WHERE id=?", (rec_id,))
            if not row or row["status"] not in ("approved", "rejected"):
                return self._flash_back("err",
                    "Set the application to Approved or Rejected before sending a decision email.",
                    "/admin/volunteers")
            note = self._notify_volunteer_decision(rec_id, row["status"], admin_id)
            self._set_flash("ok", note or "Email queued.")
        else:
            return self.send_error_page(404, "Unknown action")

        # Redirect back to the appropriate listing (carry the flash message)
        listing = {"volunteer":"volunteers","contact":"contacts","partner":"partners",
                   "subscriber":"subscribers","donation":"donations","blog":"blog",
                   "event":"events","project":"projects"}[kind]
        kind_flash = getattr(self, "_pending_flash", None)
        if kind_flash:
            return self._flash_back(kind_flash[0], kind_flash[1], f"/admin/{listing}")
        self.send_redirect(f"/admin/{listing}")

    # ------------------------------------------------------------------
    # Volunteer decision email
    # ------------------------------------------------------------------
    def _notify_volunteer_decision(self, volunteer_id, decision, admin_id):
        """
        Build + send the approved/rejected email to the applicant.
        The send happens on a background thread; the result is written to
        email_log when it completes. Returns a short note for the flash message.
        """
        vol = db.query_one("SELECT * FROM volunteers WHERE id=?", (volunteer_id,))
        if not vol:
            return "Volunteer record not found — no email sent."
        vol = dict(vol)

        to_addr = (vol.get("email") or "").strip().lower()
        if not sec.is_valid_email(to_addr):
            db.log_audit(admin_id, "volunteer_email_skipped",
                         f"id={volunteer_id} invalid address '{to_addr}'", self.client_ip())
            return f"No email sent — the applicant's address '{to_addr}' is not valid."

        subject, text_body, html_body = mailer.build_volunteer_decision_email(vol, decision)
        to_name = f"{vol.get('first_name','')} {vol.get('last_name','')}".strip()

        self._queue_email(to_addr, subject, text_body, html_body,
                          kind=f"volunteer_{decision}", related=("volunteers", volunteer_id),
                          to_name=to_name, triggered_by=admin_id,
                          label=f"volunteer #{volunteer_id} ({decision})",
                          audit_prefix="volunteer_email")

        # ── Copy to the organisation's own inbox (cbnetwork.sierraleone@gmail.com) ──
        admin_row  = db.query_one("SELECT username FROM admins WHERE id=?", (admin_id,))
        admin_name = admin_row["username"] if admin_row else "admin"
        self._send_office_copy(
            *mailer.build_decision_copy_email(vol, decision, admin_name),
            related=("volunteers", volunteer_id), kind=f"office_copy_{decision}",
            triggered_by=admin_id,
        )

        if not mailer.is_configured():
            return (f"Decision email for {to_addr} was printed to the server terminal — add the Gmail "
                    f"App Password for {mailer.sender_address()} under Email Settings to send it for real.")
        net_ok, why = mailer.check_connectivity()
        if net_ok:
            return f"Decision email is being sent from {mailer.sender_address()} to {to_addr}."
        return (f"Decision email to {to_addr} has been QUEUED — {why} It will be sent automatically "
                f"as soon as the connection is back (see Email Settings → Outbox).")

    # ------------------------------------------------------------------
    # Inbox — replies from applicants
    # ------------------------------------------------------------------
    def _admin_inbox_page(self, admin, csrf, flash):
        qs  = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        vid = qs.get("volunteer", [None])[0]
        if vid and vid.isdigit():
            rows = db.query_all(
                "SELECT i.*, v.first_name, v.last_name, v.status AS vol_status "
                "FROM inbound_emails i LEFT JOIN volunteers v ON v.id=i.volunteer_id "
                "WHERE i.volunteer_id=? ORDER BY i.received_at DESC", (int(vid),))
        else:
            rows = db.query_all(
                "SELECT i.*, v.first_name, v.last_name, v.status AS vol_status "
                "FROM inbound_emails i LEFT JOIN volunteers v ON v.id=i.volunteer_id "
                "ORDER BY i.received_at DESC LIMIT 200")
        last_sync = db.state_get("inbox_last_sync", "never")
        last_err  = db.state_get("inbox_last_error", "")
        mode, message = mailer.status()
        self.send_html(ui.render_inbox(admin, csrf, rows, flash,
                                       last_sync=last_sync, last_error=last_err,
                                       mail_live=(mode == "live"), account=mailer.sender_address(),
                                       filter_volunteer=int(vid) if vid and vid.isdigit() else None))

    def _admin_inbox_sync(self, admin_id):
        new, detail, ok = sync_inbox()
        db.log_audit(admin_id, "inbox_sync", detail, self.client_ip())
        if ok:
            return self._flash_back("ok", f"Inbox checked — {new} new repl{'y' if new == 1 else 'ies'}. ({detail})", "/admin/inbox")
        return self._flash_back("err", f"Could not check the inbox: {detail}", "/admin/inbox")

    def _admin_inbox_mark(self, rec_id, data, admin_id):
        read = 0 if data.get("unread") else 1
        db.execute("UPDATE inbound_emails SET is_read=? WHERE id=?", (read, rec_id))
        return self._flash_back("ok", "Marked as " + ("read." if read else "unread."), "/admin/inbox")

    def _admin_inbox_reply(self, rec_id, data, admin_id, session):
        """Reply to an applicant from the admin panel — sent from the CBN Gmail account."""
        row = db.query_one("SELECT * FROM inbound_emails WHERE id=?", (rec_id,))
        if not row:
            return self._flash_back("err", "Message not found.", "/admin/inbox")
        body = sec.clean_str(data.get("body"), 5000)
        if not body:
            return self._flash_back("err", "Write a reply first.", "/admin/inbox")
        to_addr = (row["from_addr"] or "").lower()
        if not sec.is_valid_email(to_addr):
            return self._flash_back("err", f"'{to_addr}' is not a valid address.", "/admin/inbox")

        subject = row["subject"] or "Your message to CBN"
        if not subject.lower().startswith("re:"):
            subject = "Re: " + subject
        signature = (f"\n\n— {session['username']}, Volunteer Coordination Team\n"
                     f"{mailer.ORG_NAME}\n{mailer.get('CBN_OFFICE_ADDRESS')} · {mailer.get('CBN_OFFICE_PHONE')}")
        text = body + signature
        html = ("<div style='font-family:Helvetica,Arial,sans-serif;color:#374151;line-height:1.65;font-size:15px;'>"
                + sec.esc(body).replace("\n", "<br>")
                + f"<p style='margin-top:22px;color:#6b7280;font-size:13px;'>— {sec.esc(session['username'])}, "
                  f"Volunteer Coordination Team<br>{sec.esc(mailer.ORG_NAME)}<br>"
                  f"{sec.esc(mailer.get('CBN_OFFICE_ADDRESS'))} · {sec.esc(mailer.get('CBN_OFFICE_PHONE'))}</p></div>")

        self._queue_email(to_addr, subject, text, html, kind="admin_reply",
                          related=("inbound_emails", rec_id), to_name=row["from_name"] or "",
                          triggered_by=admin_id, label="admin reply")
        db.execute("UPDATE inbound_emails SET is_read=1 WHERE id=?", (rec_id,))
        db.log_audit(admin_id, "inbox_reply", f"to={to_addr} inbound_id={rec_id}", self.client_ip())
        net_ok, why = mailer.check_connectivity()
        if net_ok:
            return self._flash_back("ok", f"Reply is being sent from {mailer.sender_address()} to {to_addr}.", "/admin/inbox")
        return self._flash_back("warn", f"Reply to {to_addr} is queued — {why} It will be sent when the connection returns.", "/admin/inbox")

    def _queue_email(self, to_addr, subject, text_body, html_body, *, kind, related=("", None),
                     to_name="", triggered_by=None, label="email", audit_prefix=None):
        """
        Single entry point for every outgoing email.
          • creates the email_log row (status 'queued')
          • hands the message to the mailer/outbox with the log id attached, so a
            delayed success (after the network comes back) still closes the log row
          • prints a clear ✅ / ⏳ / ❌ line and writes the audit trail
        Returns the email_log id.
        """
        log_id = db.email_log_create(related[0], related[1], to_addr, subject, kind, triggered_by)

        def _done(ok, detail):
            queued = (not ok) and str(detail).startswith("QUEUED:")
            if queued:
                # Leave email_log as 'queued'; the outbox worker will finalise it.
                print(f"[mailer] ⏳ {label} → {to_addr}: {detail}")
                if audit_prefix:
                    db.log_audit(triggered_by, f"{audit_prefix}_queued", f"to={to_addr} {detail}", None)
                return
            db.email_log_finish(log_id, ok, detail)
            print(f"[mailer] {'✅' if ok else '❌'} {label} → {to_addr}: {detail}")
            if audit_prefix:
                db.log_audit(triggered_by, f"{audit_prefix}_{'sent' if ok else 'failed'}",
                             f"to={to_addr} {detail}", None)

        _done.email_log_id = log_id            # lets the outbox finalise the log row later
        mailer.send_async(to_addr, subject, text_body, html_body, to_name=to_name, on_done=_done)
        return log_id

    def _send_office_copy(self, subject, text_body, html_body, related=("", None),
                          kind="office_copy", triggered_by=None):
        """Internal message to the organisation's own inbox (cbnetwork.sierraleone@gmail.com)."""
        office = (mailer.get("CBN_OFFICE_EMAIL") or mailer.sender_address()).strip().lower()
        if not sec.is_valid_email(office):
            return
        self._queue_email(office, subject, text_body, html_body, kind=kind, related=related,
                          to_name="CBN Volunteer Coordination", triggered_by=triggered_by,
                          label=f"office copy ({kind})")

    # ------------------------------------------------------------------
    # Payments settings (admin)
    # ------------------------------------------------------------------
    def _admin_payments_save(self, data, admin_id):
        space  = sec.clean_str(data.get("space_id"), 64)
        token  = (data.get("access_token") or "").strip()
        whsec  = (data.get("webhook_secret") or "").strip()
        fa_id  = sec.clean_str(data.get("financial_account_id"), 100)
        mode_  = sec.clean_str(data.get("mode"), 10).lower()
        colour = sec.clean_str(data.get("primary_color"), 9) or "#f36f21"
        base   = sec.clean_str(data.get("public_base_url"), 255).rstrip("/")
        enabled_ = "1" if data.get("enabled") else "0"
        clear = []
        if data.get("clear_token"):  clear.append("CBN_MONIME_ACCESS_TOKEN")
        if data.get("clear_secret"): clear.append("CBN_MONIME_WEBHOOK_SECRET")

        if space and not space.startswith("spc-"):
            return self._flash_back("err", "The Monime Space ID must start with 'spc-'.", "/admin/payments")
        if mode_ not in ("test", "live"):
            mode_ = "test"
        if base and not base.startswith(("http://", "https://")):
            return self._flash_back("err", "Public site URL must start with http:// or https://", "/admin/payments")
        if mode_ == "live" and base.startswith("http://") and "localhost" not in base and "127.0.0.1" not in base:
            return self._flash_back("err", "Live mode requires an https:// public URL for the return and webhook links.", "/admin/payments")
        import re as _re
        if not _re.match(r"^#[0-9A-Fa-f]{6}$", colour):
            colour = "#f36f21"

        monime.save_config({
            "CBN_MONIME_ENABLED": enabled_, "CBN_MONIME_SPACE_ID": space,
            "CBN_MONIME_ACCESS_TOKEN": token, "CBN_MONIME_WEBHOOK_SECRET": whsec,
            "CBN_MONIME_FINANCIAL_ACCOUNT_ID": fa_id, "CBN_MONIME_MODE": mode_,
            "CBN_MONIME_PRIMARY_COLOR": colour, "CBN_PUBLIC_BASE_URL": base,
        }, clear_secrets=clear)
        db.log_audit(admin_id, "monime_settings_saved",
                     f"space={space} mode={mode_} enabled={enabled_} token={'changed' if token else 'unchanged'}",
                     self.client_ip())
        gw_mode, gw_msg = monime.status()
        return self._flash_back("ok" if gw_mode in ("test", "live") else "warn", f"Saved. {gw_msg}", "/admin/payments")

    # ------------------------------------------------------------------
    # Email settings (admin)
    # ------------------------------------------------------------------
    def _admin_email_save(self, session, data, admin_id):
        host         = sec.clean_str(data.get("smtp_host"), 200)
        port         = _to_int(data.get("smtp_port"), 587, 1, 65535)
        user         = sec.clean_str(data.get("smtp_user"), 254).lower()
        password     = (data.get("smtp_pass") or "").strip()
        from_name    = sec.clean_str(data.get("from_name"), 100) or "CBN Sierra Leone"
        reply_to     = sec.clean_str(data.get("reply_to"), 254).lower()
        office_addr  = sec.clean_str(data.get("office_address"), 200)
        office_phone = sec.clean_str(data.get("office_phone"), 40)
        office_email = sec.clean_str(data.get("office_email"), 254).lower()
        enabled      = "1" if data.get("enabled") else "0"
        clear_pw     = bool(data.get("clear_password"))

        if not host:
            return self._flash_back("err", "SMTP host is required.", "/admin/email")
        if not sec.is_valid_email(user):
            return self._flash_back("err", "The sending account must be a valid email address.", "/admin/email")
        if reply_to and not sec.is_valid_email(reply_to):
            return self._flash_back("err", "Reply-To must be a valid email address (or blank).", "/admin/email")
        if office_email and not sec.is_valid_email(office_email):
            return self._flash_back("err", "Office email must be a valid email address (or blank).", "/admin/email")
        if password and "gmail" in host.lower() and len(password.replace(" ", "")) != 16:
            return self._flash_back("err",
                "A Gmail App Password is exactly 16 characters (Google shows it as four groups of four). "
                "Please copy it again — do not use the normal account password.", "/admin/email")

        mailer.save_config({
            "CBN_EMAIL_ENABLED":  enabled,
            "CBN_SMTP_HOST":      host,
            "CBN_SMTP_PORT":      str(port),
            "CBN_SMTP_USER":      user,
            "CBN_SMTP_PASS":      password,          # blank = keep the saved one
            "CBN_SMTP_FROM_NAME": from_name,
            "CBN_SMTP_REPLY_TO":  reply_to,
            "CBN_OFFICE_ADDRESS": office_addr,
            "CBN_OFFICE_PHONE":   office_phone,
            "CBN_OFFICE_EMAIL":   office_email,
        }, clear_secrets=("CBN_SMTP_PASS",) if clear_pw else ())

        # Never log the password itself
        db.log_audit(admin_id, "email_settings_saved",
                     f"account={user} host={host}:{port} enabled={enabled} "
                     f"password={'changed' if password else ('cleared' if clear_pw else 'unchanged')}",
                     self.client_ip())

        mode, message = mailer.status()
        return self._flash_back("ok" if mode == "live" else "warn",
                                f"Settings saved. {message}", "/admin/email")

    def _admin_email_test(self, session, data, admin_id):
        to_addr = sec.clean_str(data.get("to"), 254).lower()
        if not sec.is_valid_email(to_addr):
            return self._flash_back("err", "Enter a valid email address to send the test to.", "/admin/email")

        subject, text_body, html_body = mailer.build_test_email(to_addr, session["username"])
        self._queue_email(to_addr, subject, text_body, html_body, kind="test_email",
                          related=("test", None), triggered_by=admin_id,
                          label="test email", audit_prefix="test_email")

        if not mailer.is_configured():
            return self._flash_back("ok", "Test email was printed to the server terminal "
                                          "(console mode — no App Password saved yet).", "/admin/email")
        net_ok, why = mailer.check_connectivity()
        if not net_ok:
            return self._flash_back("err", f"Cannot send right now — {why} The test email is queued "
                                           f"and will go out automatically once the connection is back.", "/admin/email")
        return self._flash_back("ok", f"Test email is being sent from {mailer.sender_address()} to {to_addr}. "
                                      f"Refresh this page in a few seconds — the result appears in the delivery log below.",
                                "/admin/email")

    def _admin_create(self, kind, data, admin_id):
        if kind == "blog":
            title    = sec.clean_str(data.get("title"), 200)
            if not title: return self._flash_back("err","Title required.","/admin/blog")
            slug     = sec.slugify(title)
            # Ensure unique
            if db.query_one("SELECT id FROM blog_posts WHERE slug=?", (slug,)):
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            is_pub = 1 if data.get("published") else 0
            db.execute(
                "INSERT INTO blog_posts "
                "(title,slug,category,excerpt,content,author,image_url,published,published_at)"
                " VALUES (?,?,?,?,?,?,?,?, CASE WHEN ?=1 THEN CURRENT_TIMESTAMP ELSE NULL END)",
                (title, slug,
                 sec.clean_str(data.get("category"),50),
                 sec.clean_str(data.get("excerpt"),500),
                 sec.clean_str(data.get("content"),50000),
                 sec.clean_str(data.get("author"),100),
                 sec.clean_str(data.get("image_url"),500),
                 is_pub, is_pub),
            )
            db.log_audit(admin_id, "create_blog", f"title={title}", self.client_ip())
            return self._flash_back("ok","Blog post created.","/admin/blog")

        if kind == "events":
            title = sec.clean_str(data.get("title"), 200)
            date  = sec.clean_str(data.get("event_date"), 20)
            if not title or not date:
                return self._flash_back("err","Title and date required.","/admin/events")
            db.execute(
                "INSERT INTO events (title,event_date,event_time,location,description)"
                " VALUES (?,?,?,?,?)",
                (title, date,
                 sec.clean_str(data.get("event_time"),20),
                 sec.clean_str(data.get("location"),200),
                 sec.clean_str(data.get("description"),3000)),
            )
            db.log_audit(admin_id, "create_event", f"title={title}", self.client_ip())
            return self._flash_back("ok","Event created.","/admin/events")

        if kind == "projects":
            title = sec.clean_str(data.get("title"), 200)
            if not title:
                return self._flash_back("err","Title required.","/admin/projects")
            # Auto-generate unique slug
            slug = sec.slugify(title)
            if db.query_one("SELECT id FROM projects WHERE slug=?", (slug,)):
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            db.execute(
                "INSERT INTO projects "
                "(title,slug,category,district,description,article_content,"
                " image_url,banner_url,status,funded_percent,start_year,end_year,author)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (title,
                 slug,
                 sec.clean_str(data.get("category"),50),
                 sec.clean_str(data.get("district"),100),
                 sec.clean_str(data.get("description"),5000),
                 sec.clean_str(data.get("article_content"),50000),
                 sec.clean_str(data.get("image_url"),500),
                 sec.clean_str(data.get("banner_url"),500),
                 sec.clean_str(data.get("status"),20) or "current",
                 _to_int(data.get("funded_percent"), 0, 0, 100),
                 _to_int(data.get("start_year"), None, 2000, 2100),
                 _to_int(data.get("end_year"),   None, 2000, 2100),
                 sec.clean_str(data.get("author"),100)),
            )
            db.log_audit(admin_id, "create_project", f"title={title}", self.client_ip())
            return self._flash_back("ok","Project created.","/admin/projects")

        self.send_error_page(404, "Unknown create target")

    def _admin_update(self, kind, rec_id, data, admin_id):
        if not rec_id.isdigit():
            return self.send_error_page(404, "Bad ID")
        rec_id = int(rec_id)

        if kind == "blog":
            title = sec.clean_str(data.get("title"), 200)
            if not title: return self._flash_back("err","Title required.","/admin/blog")
            is_pub = 1 if data.get("published") else 0
            # published_at: keep the original go-live date on edits; stamp it the
            # first time a draft is published; clear it if the post is unpublished.
            db.execute(
                "UPDATE blog_posts SET title=?,category=?,excerpt=?,content=?,author=?,"
                "image_url=?,published=?,"
                "published_at = CASE WHEN ?=1 THEN COALESCE(published_at, CURRENT_TIMESTAMP) ELSE NULL END,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title,
                 sec.clean_str(data.get("category"),50),
                 sec.clean_str(data.get("excerpt"),500),
                 sec.clean_str(data.get("content"),50000),
                 sec.clean_str(data.get("author"),100),
                 sec.clean_str(data.get("image_url"),500),
                 is_pub, is_pub,
                 rec_id),
            )
            db.log_audit(admin_id, "update_blog", f"id={rec_id}", self.client_ip())
            return self._flash_back("ok","Blog post updated.","/admin/blog")

        if kind == "events":
            title = sec.clean_str(data.get("title"), 200)
            date  = sec.clean_str(data.get("event_date"), 20)
            if not title or not date:
                return self._flash_back("err","Title and date required.","/admin/events")
            db.execute(
                "UPDATE events SET title=?,event_date=?,event_time=?,location=?,description=? WHERE id=?",
                (title, date,
                 sec.clean_str(data.get("event_time"),20),
                 sec.clean_str(data.get("location"),200),
                 sec.clean_str(data.get("description"),3000),
                 rec_id),
            )
            db.log_audit(admin_id, "update_event", f"id={rec_id}", self.client_ip())
            return self._flash_back("ok","Event updated.","/admin/events")

        if kind == "projects":
            title = sec.clean_str(data.get("title"), 200)
            if not title:
                return self._flash_back("err","Title required.","/admin/projects")
            db.execute(
                "UPDATE projects SET title=?,category=?,district=?,description=?,"
                "article_content=?,image_url=?,banner_url=?,status=?,"
                "funded_percent=?,start_year=?,end_year=?,author=?,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title,
                 sec.clean_str(data.get("category"),50),
                 sec.clean_str(data.get("district"),100),
                 sec.clean_str(data.get("description"),5000),
                 sec.clean_str(data.get("article_content"),50000),
                 sec.clean_str(data.get("image_url"),500),
                 sec.clean_str(data.get("banner_url"),500),
                 sec.clean_str(data.get("status"),20) or "current",
                 _to_int(data.get("funded_percent"), 0, 0, 100),
                 _to_int(data.get("start_year"), None, 2000, 2100),
                 _to_int(data.get("end_year"),   None, 2000, 2100),
                 sec.clean_str(data.get("author"),100),
                 rec_id),
            )
            db.log_audit(admin_id, "update_project", f"id={rec_id}", self.client_ip())
            return self._flash_back("ok","Project updated.","/admin/projects")

        self.send_error_page(404, "Unknown update target")

    def _admin_change_password(self, session, data, admin_id):
        current = sec.clean_str(data.get("current"), 200)
        new1    = sec.clean_str(data.get("new1"), 200)
        new2    = sec.clean_str(data.get("new2"), 200)

        row = db.query_one("SELECT password_hash,password_salt FROM admins WHERE id=?", (admin_id,))
        if not row or not sec.verify_password(current, row["password_salt"], row["password_hash"]):
            return self._flash_back("err","Current password is incorrect.","/admin/password")
        if new1 != new2:
            return self._flash_back("err","New passwords do not match.","/admin/password")
        err = sec.password_strength_error(new1)
        if err:
            return self._flash_back("err", err, "/admin/password")

        salt, pwd_hash = sec.hash_password(new1)
        db.execute("UPDATE admins SET password_hash=?, password_salt=?, must_change_password=0 WHERE id=?",
                   (pwd_hash, salt, admin_id))
        # Kill all other sessions for this admin
        db.execute("DELETE FROM sessions WHERE admin_id=? AND token != ?",
                   (admin_id, session["token"]))
        db.log_audit(admin_id, "change_password", "", self.client_ip())
        logger.info(f"Admin password changed: {session['username']}")
        
        # Redirect to admin dashboard or specified next URL
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        next_url = qs.get("next", ["/admin"])[0] or "/admin"
        # Validate the redirect target (prevent open redirect)
        if not next_url.startswith("/") or next_url.startswith("//"):
            next_url = "/admin"
        
        self._flash_back("ok","Password updated. Other sessions have been logged out.", next_url)

    # ------------------ FLASH MESSAGES (cookie-based) ------------------
    def _set_flash(self, kind, msg):
        # We store flash in a short-lived cookie; simplest for stateless PRG
        self._pending_flash = (kind, msg)

    def _read_flash(self):
        cookies = self.get_cookies()
        raw = cookies.get("cbn_flash")
        if not raw:
            return None
        try:
            payload = urllib.parse.unquote(raw)
            kind, msg = payload.split("|", 1)
            # The cookie is client-controlled: constrain 'kind' to known CSS classes
            # and cap the message so a tampered cookie can't inject markup or bloat.
            if kind not in ("ok", "err", "info", "warn"):
                kind = "info"
            return (kind, msg[:500])
        except Exception:
            return None

    def _flash_back(self, kind, msg, url):
        val = urllib.parse.quote(f"{kind}|{msg}")
        cookies = [sec.build_cookie("cbn_flash", val, http_only=True,
                                    max_age=10, same_site="Strict")]
        self.send_redirect(url, cookies=cookies)


def _to_int(value, default, lo=None, hi=None):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if lo is not None and n < lo: n = lo
    if hi is not None and n > hi: n = hi
    return n


# ------------------------------------------------------------------
# Per-IP rate limiting for public endpoints (in-memory sliding window)
# ------------------------------------------------------------------
import threading as _rl_threading
import time as _rl_time
from collections import deque as _deque, defaultdict as _defaultdict

_RL_LOCK = _rl_threading.Lock()
_RL_BUCKETS = _defaultdict(_deque)          # key → deque[timestamps]

# (max requests, window seconds) per bucket name
RATE_LIMITS = {
    "form":     (12,  600),   # public forms: 12 submissions / 10 min / IP
    "donate":   (6,   600),   # checkout creation: 6 / 10 min / IP
    "status":   (120, 600),   # donation status polling: 120 / 10 min / IP
    "webhook":  (60,   60),   # unsigned webhook deliveries: 60 / min / IP
}


def _rate_ok(bucket, ip):
    """True if this request is within the limit for (bucket, ip)."""
    limit, window = RATE_LIMITS[bucket]
    now = _rl_time.monotonic()
    key = f"{bucket}:{ip}"
    with _RL_LOCK:
        dq = _RL_BUCKETS[key]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        # keep the map from growing without bound
        if len(_RL_BUCKETS) > 20000:
            for k in [k for k, v in _RL_BUCKETS.items() if not v or now - v[-1] > 3600][:5000]:
                _RL_BUCKETS.pop(k, None)
        return True


def _webhook_throttle_ok(ip):
    return _rate_ok("webhook", ip)


# ------------------------------------------------------------------
# Shared header / footer — server-side include
# ------------------------------------------------------------------
import re as _re_partials

_PARTIALS_DIR = os.path.join(STATIC_DIR, "partials")
_INLINE_HEADER_RE = _re_partials.compile(rb'[ \t]*<header class="site-header">.*?</header>[ \t]*\n?', _re_partials.S)
_INLINE_FOOTER_RE = _re_partials.compile(rb'[ \t]*<footer class="site-footer">.*?</footer>[ \t]*\n?', _re_partials.S)


def _read_partial(name):
    try:
        with open(os.path.join(_PARTIALS_DIR, f"{name}.html"), "rb") as f:
            return f.read()
    except OSError:
        return b""


def _inject_partials(html_bytes, page_path):
    """
    Make every static page use partials/header.html + partials/footer.html:
      • <div data-include="header"></div>  → replaced with the partial
      • any legacy inline <header class="site-header">…</header> → replaced too
    The current page's nav link is given class="active".
    """
    header = _read_partial("header")
    footer = _read_partial("footer")
    if not header and not footer:
        return html_bytes

    page_key = os.path.basename(page_path).replace(".html", "") or "index"

    # Nested routes (/blog/<slug>, /projects/<slug>) must not resolve "about.html"
    # as "/blog/about.html" — make the partials' relative links root-relative there.
    nested = "/" in page_path.strip("/")
    if nested:
        def _rootify(blob):
            return _re_partials.sub(
                rb'(href|src)="(?!https?:|/|#|mailto:|tel:|data:)([^"]+)"',
                rb'\1="/\2"', blob)
        header = _rootify(header)
        footer = _rootify(footer)

    if header:
        header = _re_partials.sub(
            rb'data-nav="' + page_key.encode() + rb'"',
            rb'class="active" data-nav="' + page_key.encode() + rb'"',
            header, count=1)
        # If the link already had a class attribute, merge instead of duplicating
        header = header.replace(b'class="nav-cta" class="active"', b'class="nav-cta active"')

    out = html_bytes
    if b'data-include="header"' in out:
        out = _re_partials.sub(rb'<div data-include="header"></div>', lambda m: header, out, count=1)
    elif header:
        out = _INLINE_HEADER_RE.sub(lambda m: header, out, count=1)
    if b'data-include="footer"' in out:
        out = _re_partials.sub(rb'<div data-include="footer"></div>', lambda m: footer, out, count=1)
    elif footer:
        out = _INLINE_FOOTER_RE.sub(lambda m: footer, out, count=1)
    return out


# ------------------------------------------------------------------
# Inbox sync (IMAP) — shared by the manual button and the background poller
# ------------------------------------------------------------------
import threading as _threading

_inbox_lock = _threading.Lock()
INBOX_POLL_SECONDS = int(os.environ.get("CBN_INBOX_POLL_SECONDS", "120") or 120)


def sync_inbox():
    """
    Pull new messages from the CBN Gmail inbox into inbound_emails.
    Returns (new_count, detail, ok). Safe to call from any thread.
    """
    if not _inbox_lock.acquire(blocking=False):
        return 0, "a sync is already running", True
    try:
        if not mailer.is_configured():
            return 0, mailer.status()[1], False
        # Fast offline check so the poller doesn't log an IMAP error every cycle
        net_ok, why = mailer.check_connectivity()
        if not net_ok:
            db.state_set("inbox_last_error", f"offline — {why}")
            return 0, f"offline — {why}", False
        last_uid = int(db.state_get("inbox_last_uid", "0") or 0)
        ok, detail, messages = mailer.fetch_inbox(since_uid=last_uid, limit=100)
        if not ok:
            db.state_set("inbox_last_error", detail)
            return 0, detail, False
        # Ignore our own outgoing copies if they land in the inbox
        own = mailer.sender_address().lower()
        messages = [m for m in messages if m["from_addr"] != own]
        new = db.inbound_store(messages)
        if messages:
            db.state_set("inbox_last_uid", max(m["uid"] for m in messages))
        elif ok:
            # Nothing new — still advance nothing; keep last_uid
            pass
        db.state_set("inbox_last_sync", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        db.state_set("inbox_last_error", "")
        if new:
            print(f"[inbox] 📥 {new} new repl{'y' if new == 1 else 'ies'} from applicants stored")
        return new, detail, True
    finally:
        _inbox_lock.release()


def start_inbox_poller():
    """Check the inbox every INBOX_POLL_SECONDS in the background."""
    if INBOX_POLL_SECONDS <= 0:
        return
    def _loop():
        import time as _t
        _t.sleep(15)                                     # let start-up finish
        while True:
            try:
                sync_inbox()
            except Exception as e:                       # never let the poller die
                print(f"[inbox] poller error: {e}")
            _t.sleep(INBOX_POLL_SECONDS)
    _threading.Thread(target=_loop, name="cbn-inbox-poller", daemon=True).start()


# ------------------------------------------------------------------
# Blog helpers
# ------------------------------------------------------------------
import re as _re_mod

_HTML_BLOCK_RE = _re_mod.compile(r"<(p|h[1-6]|ul|ol|li|blockquote|br|div|img|a|strong|em)\b", _re_mod.I)


def _plain_text(html_or_text):
    """Strip tags and collapse whitespace — used for excerpts and read-time."""
    s = _re_mod.sub(r"<[^>]+>", " ", html_or_text or "")
    return _re_mod.sub(r"\s+", " ", s).strip()


def _fmt_date(value):
    """'2026-09-03 18:00:04' → '3 September 2026' (portable; no %-d)."""
    try:
        dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        return f"{dt.day} {dt.strftime('%B %Y')}"
    except Exception:
        return str(value or "")[:10]


def _format_blog_content(content):
    """
    Admins may paste either HTML or plain text into the post body.
      • Looks like HTML  → render as-is (only authenticated admins can write it).
      • Plain text       → escape it, blank lines become paragraphs, single
                           newlines become <br>, so it never collapses into one blob.
    """
    content = (content or "").strip()
    if not content:
        return "<p>Full article coming soon.</p>"
    if _HTML_BLOCK_RE.search(content):
        return sec.sanitize_html(content)     # whitelist tags/attrs; strip scripts & js: URLs
    paragraphs = []
    for block in _re_mod.split(r"\n\s*\n", content):
        block = sec.esc(block.strip()).replace("\n", "<br>")
        if block:
            paragraphs.append(f"<p>{block}</p>")
    return "".join(paragraphs)


# ==================================================================
# ENTRY POINT
# ==================================================================
def main():
    print("=" * 60)
    print("Community Builders Network - Sierra Leone")
    print("Pure-Python secure backend")
    print("=" * 60)

    # One-time: switch pages to the shared header/footer partials (idempotent)
    try:
        import use_partials
        use_partials.run()
    except Exception as e:
        print(f"  ⚠ partials migration skipped: {e}")

    print("Initializing database…")
    created = db.initialize()
    if created:
        print()
        print("⚠  DEFAULT ADMIN CREATED:")
        print("     Username: admin")
        print("     Password: ChangeMe123!")
        print("   >>> PLEASE LOG IN AND CHANGE IT IMMEDIATELY <<<")
        print()

    print(f"Public site   : http://{HOST}:{PORT}/")
    print(f"Admin panel   : http://{HOST}:{PORT}/admin/login")
    print(f"Database file : {db.DB_PATH}")
    mailer.load_config()
    print(f"Email sender  : {mailer.sender_header()}")
    print(f"Email status  : {mailer.config_summary()}")
    monime.load_config()
    gw_mode, gw_msg = monime.status()
    icon = {"live": "💳", "Live": "🧪", "simulation": "🎭", "disabled": "⏸"}.get(gw_mode, "•")
    print(f"Payments      : {icon} {gw_msg}")
    print("=" * 60)
    if gw_mode in ("test", "live"):
        import threading as _th
        def _ping():
            ok, detail = monime.ping()
            print(f"{'✅' if ok else '❌'} Monime: {detail}")
        _th.Thread(target=_ping, daemon=True).start()

    # Confirm the Gmail App Password actually works (background, non-blocking)
    if mailer.is_configured():
        pending = db.outbox_summary()
        if pending["pending"] or pending["failed"]:
            print(f"📤 Outbox: {pending['pending']} email(s) waiting to be sent, "
                  f"{pending['failed']} failed (Admin → Email Settings → Outbox)")
        print("Checking network + Gmail login for the sending account…")
        def _report(ok, detail):
            if ok:
                print(f"✅ Email ready — {detail}")
                print(f"📥 Inbox poller: checking {mailer.sender_address()} for replies every "
                      f"{INBOX_POLL_SECONDS}s (Admin → Inbox)")
            elif str(detail).startswith("NETWORK:"):
                print(f"📴 OFFLINE — {detail[9:]}")
                print("   Emails will be queued in the outbox and sent automatically when the "
                      "connection returns.")
            else:
                print(f"❌ EMAIL LOGIN FAILED — {detail}")
                print("   Emails will fail until this is fixed: Admin → Email Settings.")
        mailer.verify_connection_async(_report)
        mailer.start_outbox_worker(interval_seconds=30)   # retries queued mail until it goes out
        start_inbox_poller()
    print("Press Ctrl+C to stop.\n")

    server = ThreadingHTTPServer((HOST, PORT), CBNHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        server.server_close()


if __name__ == "__main__":
    main()
