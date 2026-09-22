"""
CBN Backend — Monime payment gateway (Sierra Leone)
===================================================
Pure standard-library client for the Monime Checkout Sessions API.
Docs: https://docs.monime.io  ·  API: https://api.monime.io/v1

HOW A DONATION FLOWS
--------------------
  1. Donor fills the form on donate.html and clicks "Donate".
  2. Our server creates a Monime *Checkout Session*  (POST /v1/checkout-sessions)
     and stores the returned session id + status 'pending' on the donation row.
  3. Donor is redirected to Monime's hosted page (result.redirectUrl) where
     they pay with Orange Money (m17), Africell Money (m18), a bank or a card.
  4. Monime sends them back to our successUrl / cancelUrl.
  5. We NEVER trust the redirect. The server calls
        GET /v1/checkout-sessions/{id}
     and marks the donation 'completed' only when Monime says status=completed.
     (Monime can also POST a webhook to /api/monime/webhook — verified with
      HMAC-SHA256 when a secret is configured — as a faster notification.)

MONEY
-----
  Monime amounts are integers in the currency's MINOR unit:
      SLE 1.00  →  value = 100
  Sierra Leone redenominated in 2022: the new Leone (SLE) = old Leone (SLL) / 1000.
  The website historically quoted "Le 250,000" in OLD leones; that is SLE 250,
  which Monime expects as value = 25000.  See `sll_to_minor()`.

TEST MODE
---------
  Monime gives every account a live Space and a test Space (id starts with
  'spc-'). Point CBN_MONIME_SPACE_ID at the TEST space id and use a token
  created in that space: real checkout pages appear, but no money moves and
  Monime's test wallets let you simulate success / failure.
  Until credentials are configured this module runs in SIMULATION mode: a
  local fake checkout page (/pay/simulate/<id>) mimics the redirect flow so
  the whole journey can be exercised offline.
"""

import hashlib
import hmac
import json
import os
import secrets as _secrets
import socket
import ssl
import stat
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, "monime.env")

API_BASE    = "https://api.monime.io"
API_VERSION = "caph.2025-08-23"
TIMEOUT     = 25

# Provider ids from the Monime API spec
PROVIDERS = {
    "m17":   "Orange Money",
    "m18":   "Africell Money",
    "slb001": "Sierra Leone Commercial Bank",
    "slb004": "Bank (slb004)",
    "slb007": "Bank (slb007)",
    "dw001": "SafulPay wallet",
}

DEFAULTS = {
    "CBN_MONIME_ENABLED":        "1",
    "CBN_MONIME_SPACE_ID":       "",      # spc-…  (use your TEST space first)
    "CBN_MONIME_ACCESS_TOKEN":   "",      # created in the Monime dashboard
    "CBN_MONIME_WEBHOOK_SECRET": "",      # HS256 secret from the webhook you create (optional)
    "CBN_MONIME_FINANCIAL_ACCOUNT_ID": "",  # optional: settle into a specific account
    "CBN_MONIME_MODE":           "live",  # 'test' | 'live'  (label only; the Space decides)
    "CBN_MONIME_PRIMARY_COLOR":  "#f36f21",
    "CBN_PUBLIC_BASE_URL":       "",      # e.g. https://cbn-sl.org — for success/cancel/webhook URLs
}
SECRET_KEYS = {"CBN_MONIME_ACCESS_TOKEN", "CBN_MONIME_WEBHOOK_SECRET"}

_cfg = {}


def _parse_env_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                values[k] = v
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"[monime] could not read {path}: {e}")
    return values


def load_config():
    merged = dict(DEFAULTS)
    for k in DEFAULTS:
        v = os.environ.get(k)
        if v is not None and v.strip():
            merged[k] = v.strip()
    for k, v in _parse_env_file(ENV_FILE).items():
        if k in DEFAULTS and v.strip():
            merged[k] = v.strip()
    _cfg.clear()
    _cfg.update(merged)
    return dict(_cfg)


def save_config(values, clear_secrets=()):
    current = _parse_env_file(ENV_FILE)
    for k, v in values.items():
        if k not in DEFAULTS:
            continue
        v = "" if v is None else str(v).strip()
        if k in SECRET_KEYS and not v and k not in clear_secrets:
            continue
        current[k] = v
    for k in clear_secrets:
        current[k] = ""
    lines = ["# CBN — Monime payment gateway settings (managed by Admin → Payments)",
             "# Contains API secrets: never commit or share this file.", ""]
    for k in DEFAULTS:
        if k in current:
            lines.append(f"{k}='{current[k].replace(chr(10), ' ').replace(chr(39), '')}'")
    tmp = ENV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(tmp, ENV_FILE)
    load_config()
    return ENV_FILE


def get(key):
    return _cfg.get(key, DEFAULTS.get(key, ""))


def enabled():
    return get("CBN_MONIME_ENABLED").strip().lower() not in ("0", "false", "no", "off")


def is_configured():
    """Real Monime calls are possible."""
    return (enabled()
            and get("CBN_MONIME_SPACE_ID").startswith("spc-")
            and bool(get("CBN_MONIME_ACCESS_TOKEN")))


def mode():
    """'live' | 'test' | 'simulation' | 'disabled'"""
    if not enabled():
        return "disabled"
    if not is_configured():
        return "simulation"
    return "live" if get("CBN_MONIME_MODE").lower() == "live" else "test"


def status():
    m = mode()
    if m == "disabled":
        return m, "Online payments are switched OFF — the donate page shows bank-transfer details only."
    if m == "simulation":
        return m, ("SIMULATION — no Monime credentials saved. Donations go through a local fake "
                   "checkout page so the flow can be tested; no real money moves. Add your Monime "
                   "TEST space id + access token under Admin → Payments to talk to the real API.")
    if m == "test":
        return m, (f"TEST MODE — connected to Monime space {get('CBN_MONIME_SPACE_ID')}. Real "
                   f"checkout pages, no real money. Switch the mode to 'live' and use your live "
                   f"space when you're ready to accept donations.")
    return m, f"LIVE — accepting real donations via Monime space {get('CBN_MONIME_SPACE_ID')}."


def config_view():
    tok = get("CBN_MONIME_ACCESS_TOKEN")
    sec_ = get("CBN_MONIME_WEBHOOK_SECRET")
    return {
        "enabled": enabled(),
        "space_id": get("CBN_MONIME_SPACE_ID"),
        "has_token": bool(tok),
        "token_mask": (tok[:6] + "…" + tok[-4:]) if len(tok) > 12 else ("•" * len(tok) if tok else ""),
        "has_webhook_secret": bool(sec_),
        "financial_account_id": get("CBN_MONIME_FINANCIAL_ACCOUNT_ID"),
        "mode": get("CBN_MONIME_MODE"),
        "primary_color": get("CBN_MONIME_PRIMARY_COLOR"),
        "public_base_url": get("CBN_PUBLIC_BASE_URL"),
        "env_file": ENV_FILE,
        "env_file_exists": os.path.exists(ENV_FILE),
        "effective_mode": mode(),
    }


# ------------------------------------------------------------------
# SIERRA LEONE MOBILE NUMBERS — operator detection
# ------------------------------------------------------------------
# 8-digit local numbers (after the +232 country code). First two digits identify
# the operator. Keep these lists in sync with the JavaScript on donate.html.
ORANGE_PREFIXES   = ("72", "73", "74", "75", "76", "77", "78", "79")
AFRICELL_PREFIXES = ("30", "31", "32", "33", "34", "77", "88", "99")

import re as _re


def normalise_sl_number(raw):
    """'+232 76 123 456' / '076123456' / '76123456' → '76123456' (or '' if not 8 digits)."""
    d = _re.sub(r"\D", "", raw or "")
    if d.startswith("232"):
        d = d[3:]
    if len(d) == 9 and d.startswith("0"):
        d = d[1:]
    return d if len(d) == 8 else ""


def sl_operator(local8):
    """'orange' | 'africell' | None for an 8-digit local number."""
    if not local8:
        return None
    p = local8[:2]
    if p in ORANGE_PREFIXES:
        return "orange"
    if p in AFRICELL_PREFIXES:
        return "africell"
    return None


def to_e164(local8):
    return "+232" + local8 if local8 else ""


def validate_momo_number(raw, operator):
    """
    Check that `raw` is a valid Sierra Leone number for the given operator
    ('orange' | 'africell'). → (ok, e164_or_None, message)
    """
    local = normalise_sl_number(raw)
    if not local:
        return False, None, "Please enter a valid Sierra Leone mobile number (8 digits after +232)."
    found = sl_operator(local)
    if operator == "orange" and found != "orange":
        if found == "africell":
            return False, None, ("That is an Africell number. Choose Africell Money, or enter an Orange "
                                 "number (starts with 072–079).")
        return False, None, "That is not an Orange Sierra Leone number (Orange numbers start with 072–079)."
    if operator == "africell" and found != "africell":
        if found == "orange":
            return False, None, ("That is an Orange number. Choose Orange Money, or enter an Africell "
                                 "number (starts with 030–034, 077, 088 or 099).")
        return False, None, ("That is not an Africell Sierra Leone number (Africell numbers start with "
                             "030–034, 077, 088 or 099).")
    return True, to_e164(local), "ok"


# ------------------------------------------------------------------
# MONEY
# ------------------------------------------------------------------
def sll_to_minor(amount_sll):
    """
    Old-Leone amount (as displayed on the site, e.g. 250000) → Monime minor units
    of the NEW Leone.   Le 250,000 (SLL) = SLE 250.00 = 25000 minor units.
    """
    return int(round(int(amount_sll) / 1000 * 100))


def minor_to_sle(value):
    """Monime minor units → new-Leone float (25000 → 250.00)."""
    return int(value) / 100.0


def fmt_sle(value_minor):
    return f"SLE {minor_to_sle(value_minor):,.2f}"


# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------
def _ssl_context():
    cafile = None
    try:
        import certifi
        cafile = certifi.where()
    except Exception:
        cafile = os.environ.get("SSL_CERT_FILE") or None
    ctx = ssl.create_default_context(cafile=cafile)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _request(method, path, body=None, idempotency_key=None):
    """
    Call the Monime API. Returns (ok, status_code, json_or_text).
    Never raises — network problems come back as ok=False.
    """
    url = API_BASE + path
    headers = {
        "Authorization":   f"Bearer {get('CBN_MONIME_ACCESS_TOKEN')}",
        "Monime-Space-Id": get("CBN_MONIME_SPACE_ID"),
        "Monime-Version":  API_VERSION,
        "Accept":          "application/json",
        "User-Agent":      "CBN-SierraLeone-Website/1.0 (+python-urllib)",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:64]

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return True, resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return True, resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = raw
        return False, e.code, payload
    except socket.gaierror:
        return False, 0, "NETWORK: cannot resolve api.monime.io — no internet connection"
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as e:
        return False, 0, f"NETWORK: {type(e).__name__}: {e}"


def _error_text(payload, code):
    """Human-readable message from a Monime error payload."""
    if isinstance(payload, dict):
        msgs = payload.get("messages")
        if isinstance(msgs, list) and msgs:
            first = msgs[0]
            if isinstance(first, dict):
                return first.get("message") or first.get("detail") or json.dumps(first)
            return str(first)
        for k in ("message", "error", "detail"):
            if payload.get(k):
                return str(payload[k])
        return json.dumps(payload)[:300]
    if isinstance(payload, str) and payload.startswith("NETWORK:"):
        return payload
    if code == 401:
        return "Monime rejected the access token (401). Check the token and that it belongs to the configured Space."
    if code == 403:
        return "Monime refused the request (403) — the token may lack permission for checkout sessions."
    if code == 404:
        return "Monime resource not found (404)."
    return f"Monime error HTTP {code}: {str(payload)[:200]}"


# ------------------------------------------------------------------
# CHECKOUT SESSIONS
# ------------------------------------------------------------------
def create_checkout(donation, base_url, project_title=None):
    """
    Create a Monime checkout session for a donation row (dict).
    Returns (ok, result) where result is the session dict on success or an
    error string on failure.
    """
    ref        = donation["reference"]
    amount_min = sll_to_minor(donation["amount_sll"])
    donor      = f"{donation.get('first_name','')} {donation.get('last_name','')}".strip() or "Anonymous donor"
    name       = "Donation to Community Builders Network"
    if project_title:
        name = f"Donation — {project_title}"[:150]

    body = {
        "name":        name,
        "description": (f"Thank you {donor}! Reference {ref}. 100% of your gift reaches communities "
                        f"in Sierra Leone.")[:1000],
        "reference":   ref,
        "callbackState": ref,
        "successUrl":  f"{base_url}/donate/return?ref={ref}&outcome=success",
        "cancelUrl":   f"{base_url}/donate/return?ref={ref}&outcome=cancel",
        "lineItems": [{
            "type":      "custom",
            "name":      name[:100],
            "price":     {"currency": "SLE", "value": amount_min},
            "quantity":  1,
            "reference": ref,
            "description": (project_title or "General fund")[:100],
        }],
        "brandingOptions": {"primaryColor": get("CBN_MONIME_PRIMARY_COLOR") or "#f36f21"},
        "metadata": {
            "donation_reference": ref,
            "donor_email":  (donation.get("email") or "")[:100],
            "frequency":    (donation.get("frequency") or "once")[:20],
            "project":      (donation.get("project_designation") or "general")[:100],
            "source":       "cbn-website",
        },
    }
    # Prefer mobile money for the SL audience; leave card/bank available.
    method = (donation.get("payment_method") or "").lower()
    if method == "orange_money":
        body["paymentOptions"] = {"momo": {"enabledProviders": ["m17"]}}
    elif method == "africell_money":
        body["paymentOptions"] = {"momo": {"enabledProviders": ["m18"]}}
    elif method == "bank_transfer":
        body["paymentOptions"] = {"momo": {"disable": True}, "card": {"disable": True}}
    elif method == "card":
        body["paymentOptions"] = {"momo": {"disable": True}, "bank": {"disable": True}}

    fa = get("CBN_MONIME_FINANCIAL_ACCOUNT_ID").strip()
    if fa:
        body["financialAccountId"] = fa

    # Idempotency: same donation → same key → Monime won't create a duplicate
    idem = f"cbn-{ref}-{hashlib.sha1(str(amount_min).encode()).hexdigest()[:10]}"

    ok, code, payload = _request("POST", "/v1/checkout-sessions", body, idempotency_key=idem)
    if not ok:
        return False, _error_text(payload, code)
    result = payload.get("result") if isinstance(payload, dict) else None
    if not result or not result.get("redirectUrl"):
        return False, f"Monime returned no checkout URL: {json.dumps(payload)[:300]}"
    return True, result


def get_checkout(session_id):
    """Fetch a checkout session → (ok, session_dict_or_error)."""
    if not session_id:
        return False, "no session id"
    ok, code, payload = _request("GET", f"/v1/checkout-sessions/{urllib.parse.quote(session_id)}")
    if not ok:
        return False, _error_text(payload, code)
    result = payload.get("result") if isinstance(payload, dict) else None
    return (True, result) if result else (False, "empty response from Monime")


def ping():
    """Cheap credential + connectivity check → (ok, detail)."""
    if not is_configured():
        return False, status()[1]
    ok, code, payload = _request("GET", "/v1/checkout-sessions?limit=1")
    if ok:
        return True, f"connected to Monime space {get('CBN_MONIME_SPACE_ID')} ({get('CBN_MONIME_MODE')} mode)"
    return False, _error_text(payload, code)


# ------------------------------------------------------------------
# WEBHOOKS — register our endpoint with Monime via the API
# ------------------------------------------------------------------
WEBHOOK_EVENTS = [
    "checkout_session.completed",
    "checkout_session.cancelled",
    "checkout_session.expired",
]
WEBHOOK_NAME = "CBN Website — donations"


def list_webhooks():
    """→ (ok, [webhook dicts] | error)"""
    ok, code, payload = _request("GET", "/v1/webhooks?limit=50")
    if not ok:
        return False, _error_text(payload, code)
    result = payload.get("result") if isinstance(payload, dict) else None
    return True, (result or [])


def find_our_webhook(webhook_url):
    ok, hooks = list_webhooks()
    if not ok:
        return False, hooks
    for h in hooks:
        if (h.get("url") or "").rstrip("/") == webhook_url.rstrip("/"):
            return True, h
    return True, None


def register_webhook(webhook_url, secret):
    """
    Create (or update) the Monime webhook that points at our /api/monime/webhook.
    Uses HS256 with the supplied shared secret so we can verify every delivery.
    → (ok, webhook_dict | error)
    """
    if not webhook_url.startswith("https://"):
        return False, ("Monime only delivers webhooks to public https:// URLs. Set 'Public site URL' to your "
                       "https address (or an ngrok/Cloudflare tunnel while testing) and try again.")
    if len(secret) < 32:
        return False, "webhook secret must be at least 32 characters"

    body = {
        "name":   WEBHOOK_NAME,
        "url":    webhook_url,
        "enabled": True,
        "events": WEBHOOK_EVENTS,
        "apiRelease": "caph",
        "verificationMethod": {"type": "HS256", "secret": secret},
        "metadata": {"source": "cbn-website"},
    }
    ok, existing = find_our_webhook(webhook_url)
    if not ok:
        return False, existing

    if existing and existing.get("id"):
        ok, code, payload = _request("PATCH", f"/v1/webhooks/{urllib.parse.quote(existing['id'])}", body,
                                     idempotency_key=f"cbn-wh-upd-{hashlib.sha1(webhook_url.encode()).hexdigest()[:16]}")
        if not ok and code in (404, 405):
            ok, code, payload = _request("PUT", f"/v1/webhooks/{urllib.parse.quote(existing['id'])}", body)
    else:
        ok, code, payload = _request("POST", "/v1/webhooks", body,
                                     idempotency_key=f"cbn-wh-{hashlib.sha1((webhook_url + secret[:8]).encode()).hexdigest()[:20]}")
    if not ok:
        return False, _error_text(payload, code)
    result = payload.get("result") if isinstance(payload, dict) else None
    return True, (result or {"url": webhook_url})


def delete_webhook(webhook_id):
    ok, code, payload = _request("DELETE", f"/v1/webhooks/{urllib.parse.quote(webhook_id)}")
    return (True, "deleted") if ok else (False, _error_text(payload, code))


# ------------------------------------------------------------------
# WEBHOOK VERIFICATION (HS256)
# ------------------------------------------------------------------
_SIGNATURE_HEADERS = ("Monime-Signature", "X-Monime-Signature", "Signature", "X-Signature", "X-Webhook-Signature")


def find_signature(headers):
    """Return the raw signature header value, whichever name Monime used."""
    for name in _SIGNATURE_HEADERS:
        v = headers.get(name)
        if v:
            return v.strip()
    return ""


def verify_webhook(raw_body: bytes, signature: str) -> (bool, str):
    """
    Verify an HS256 webhook. Accepts the common encodings:
      • hex digest                         'ab12…'
      • prefixed                           'sha256=ab12…'  /  'v1=ab12…'
      • base64 digest
      • Stripe-style 't=<ts>,v1=<hex>'     (signs '<ts>.<body>')
    Returns (ok, reason).
    """
    secret = get("CBN_MONIME_WEBHOOK_SECRET").encode("utf-8")
    if not secret:
        return False, "no webhook secret configured"
    if not signature:
        return False, "missing signature header"

    import base64
    candidates = []
    parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p) if "," in signature or "=" in signature else {}
    ts = parts.get("t")
    for key in ("v1", "sha256", "s", "signature"):
        if key in parts:
            candidates.append(parts[key])
    if not candidates:
        candidates.append(signature.split("=", 1)[1] if signature.startswith(("sha256=", "v1=")) else signature)

    payloads = [raw_body]
    if ts:
        payloads.insert(0, f"{ts}.".encode() + raw_body)

    for payload in payloads:
        digest = hmac.new(secret, payload, hashlib.sha256)
        hexd, b64d = digest.hexdigest(), base64.b64encode(digest.digest()).decode()
        for cand in candidates:
            cand = cand.strip()
            if hmac.compare_digest(hexd, cand.lower()) or hmac.compare_digest(b64d, cand):
                return True, "signature valid"
    return False, "signature mismatch"


# ------------------------------------------------------------------
# SIMULATION (no credentials) — a fake session that mimics Monime's shape
# ------------------------------------------------------------------
def simulate_create(donation, base_url):
    sid = "sim_" + uuid.uuid4().hex[:20]
    return {
        "id": sid,
        "status": "pending",
        "name": "Donation to Community Builders Network (SIMULATION)",
        "orderNumber": "SIM-" + donation["reference"],
        "reference": donation["reference"],
        "redirectUrl": f"{base_url}/pay/simulate/{sid}?ref={donation['reference']}",
        "successUrl": f"{base_url}/donate/return?ref={donation['reference']}&outcome=success",
        "cancelUrl":  f"{base_url}/donate/return?ref={donation['reference']}&outcome=cancel",
        "lineItems": {"data": [{"name": "Donation", "price": {"currency": "SLE",
                      "value": sll_to_minor(donation["amount_sll"])}, "quantity": 1}]},
        "expireTime": (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z",
        "createTime": datetime.utcnow().isoformat() + "Z",
        "simulated": True,
    }


load_config()
