"""
CBN Backend — Email notifications
=================================
Pure standard-library mailer (smtplib + email.message). No frameworks.

Every notification is sent

    FROM  cbnetwork.sierraleone@gmail.com   (the organisation's Gmail account)
    TO    the address the applicant typed into the website form.

Gmail only relays mail for the account that authenticates, so the From
address is always the SMTP login account; only the display name
("CBN Sierra Leone") can be changed.

Configuration precedence (highest first):
    1. email.env  — written by Admin → Email Settings (file mode 0600)
    2. environment variables  (CBN_SMTP_PASS, CBN_SMTP_HOST, …)
    3. built-in defaults      (Gmail SMTP + cbnetwork.sierraleone@gmail.com)

The ONLY value that has to be supplied is the Gmail *App Password* for the
account (CBN_SMTP_PASS). Until it is set the mailer runs in CONSOLE MODE:
each email is printed to the terminal instead of being sent, so the whole
approve/reject flow can be tested without touching a real inbox.
"""

import os
import smtplib
import socket
import ssl
import stat
import threading
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

# ------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, "email.env")

ORG_NAME          = "Community Builders Network - Sierra Leone"
ORG_SHORT         = "CBN Sierra Leone"
SENDER_ACCOUNT    = "cbnetwork.sierraleone@gmail.com"   # the organisation's sending account
VERIFICATION_TIME = "13:00 (1:00 PM)"
SMTP_TIMEOUT      = 20  # seconds

# Built-in defaults — Gmail SMTP with the organisation account.
DEFAULTS = {
    "CBN_EMAIL_ENABLED":  "1",
    "CBN_SMTP_HOST":      "smtp.gmail.com",
    "CBN_SMTP_PORT":      "587",
    "CBN_SMTP_USER":      SENDER_ACCOUNT,
    "CBN_SMTP_PASS":      "",                 # ← Gmail App Password (the only required value)
    "CBN_SMTP_FROM_NAME": "CBN Sierra Leone",
    "CBN_SMTP_REPLY_TO":  SENDER_ACCOUNT,
    "CBN_OFFICE_ADDRESS": "15 Wilkinson Road, Freetown, Sierra Leone",
    "CBN_OFFICE_PHONE":   "+232 76 000 000",
    "CBN_OFFICE_EMAIL":   SENDER_ACCOUNT,
}
SECRET_KEYS = {"CBN_SMTP_PASS"}

_cfg = {}   # effective configuration (populated by load_config)


# ------------------------------------------------------------------
# CONFIG LOADING / SAVING
# ------------------------------------------------------------------
def _parse_env_file(path):
    """Parse KEY=VALUE / export KEY='VALUE' lines. Missing file → {}."""
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
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                    val = val[1:-1]
                values[key] = val
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"[mailer] could not read {path}: {e}")
    return values


def load_config():
    """Build the effective config: defaults < environment < email.env."""
    merged = dict(DEFAULTS)

    for key in DEFAULTS:
        val = os.environ.get(key)
        if val is not None and val.strip():
            merged[key] = val.strip()

    file_vals = _parse_env_file(ENV_FILE)
    for key, val in file_vals.items():
        if key in DEFAULTS and val.strip():
            merged[key] = val.strip()

    # Legacy CBN_SMTP_FROM="Name <addr>" → keep only the display name
    legacy = (file_vals.get("CBN_SMTP_FROM") or os.environ.get("CBN_SMTP_FROM") or "").strip()
    if legacy and not (file_vals.get("CBN_SMTP_FROM_NAME") or os.environ.get("CBN_SMTP_FROM_NAME")):
        name, _ = parseaddr(legacy)
        if name:
            merged["CBN_SMTP_FROM_NAME"] = name

    # Gmail shows App Passwords as "abcd efgh ijkl mnop" — the real password has no spaces
    if "gmail" in merged["CBN_SMTP_HOST"].lower():
        merged["CBN_SMTP_PASS"] = merged["CBN_SMTP_PASS"].replace(" ", "")

    _cfg.clear()
    _cfg.update(merged)
    return dict(_cfg)


def save_config(values, clear_secrets=()):
    """
    Persist admin-supplied settings to email.env (owner read/write only) and
    reload. A blank secret keeps the previously saved one unless its key is
    listed in `clear_secrets`.
    """
    current = _parse_env_file(ENV_FILE)
    for key, val in values.items():
        if key not in DEFAULTS:
            continue
        val = "" if val is None else str(val).strip()
        if key in SECRET_KEYS and not val and key not in clear_secrets:
            continue
        current[key] = val
    for key in clear_secrets:
        current[key] = ""

    lines = [
        "# CBN email settings — managed by Admin → Email Settings",
        "# Contains the Gmail App Password: never commit or share this file.",
        "",
    ]
    for key in DEFAULTS:
        if key in current:
            safe = current[key].replace("\n", " ").replace("'", "")
            lines.append(f"{key}='{safe}'")

    tmp = ENV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)   # 0600
    except OSError:
        pass
    os.replace(tmp, ENV_FILE)
    load_config()
    return ENV_FILE


# ------------------------------------------------------------------
# ACCESSORS
# ------------------------------------------------------------------
def get(key):
    return _cfg.get(key, DEFAULTS.get(key, ""))


def enabled():
    return get("CBN_EMAIL_ENABLED").strip().lower() not in ("0", "false", "no", "off")


def sender_address():
    return get("CBN_SMTP_USER").strip() or SENDER_ACCOUNT


def sender_header():
    return formataddr((get("CBN_SMTP_FROM_NAME").strip(), sender_address()))


def is_gmail():
    return "gmail" in get("CBN_SMTP_HOST").lower() or sender_address().lower().endswith("@gmail.com")


def _port():
    try:
        return int(get("CBN_SMTP_PORT") or 587)
    except (TypeError, ValueError):
        return 587


def is_configured():
    """True when real delivery is possible (enabled + host + credentials)."""
    if not enabled() or not get("CBN_SMTP_HOST").strip():
        return False
    user = get("CBN_SMTP_USER").strip()
    return (not user) or bool(get("CBN_SMTP_PASS"))


def status():
    """(mode, message) — mode is 'live' | 'console' | 'disabled'."""
    if not enabled():
        return "disabled", ("Email sending is switched OFF in Email Settings — "
                            "emails are printed to the server terminal instead.")
    if not is_configured():
        if is_gmail():
            return "console", (f"CONSOLE MODE — no Gmail App Password saved for {sender_address()}. "
                               f"Add it under Admin → Email Settings to send real emails; until then "
                               f"each email is printed to the server terminal.")
        return "console", ("CONSOLE MODE — SMTP is not fully configured. "
                           "Emails are printed to the server terminal.")
    return "live", (f"Live — emails are sent from {sender_header()} "
                    f"via {get('CBN_SMTP_HOST')}:{_port()}")


def config_summary():
    return status()[1]


def current_config_view():
    """Config for the admin form — the password is never returned, only masked."""
    pw = get("CBN_SMTP_PASS")
    return {
        "enabled":        enabled(),
        "host":           get("CBN_SMTP_HOST"),
        "port":           get("CBN_SMTP_PORT"),
        "user":           get("CBN_SMTP_USER"),
        "has_password":   bool(pw),
        "password_mask":  ("•" * 12 + f"  ({len(pw)} characters saved)") if pw else "",
        "from_name":      get("CBN_SMTP_FROM_NAME"),
        "reply_to":       get("CBN_SMTP_REPLY_TO"),
        "office_address": get("CBN_OFFICE_ADDRESS"),
        "office_phone":   get("CBN_OFFICE_PHONE"),
        "office_email":   get("CBN_OFFICE_EMAIL"),
        "sender_address": sender_address(),
        "sender_header":  sender_header(),
        "is_gmail":       is_gmail(),
        "env_file":       ENV_FILE,
        "env_file_exists": os.path.exists(ENV_FILE),
    }


# ------------------------------------------------------------------
# DATE HELPERS
# ------------------------------------------------------------------
def verification_window(days=7):
    """(deadline_date, human_range) for the 'come within a week' window."""
    today    = datetime.now().date()
    deadline = today + timedelta(days=days)
    def _fmt(d): return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}"
    return deadline, f"between {_fmt(today + timedelta(days=1))} and {_fmt(deadline)}"


def _h(value):
    """Minimal HTML escape for template values."""
    return (str(value or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ------------------------------------------------------------------
# TEMPLATE — volunteer decision (approved / rejected)
# ------------------------------------------------------------------
def build_volunteer_decision_email(volunteer, decision):
    """Return (subject, text_body, html_body) for an approve/reject decision."""
    first = (volunteer.get("first_name") or "").strip() or "Volunteer"
    last  = (volunteer.get("last_name") or "").strip()
    name  = f"{first} {last}".strip()
    role  = (volunteer.get("role") or "General Volunteer").strip()
    ref   = f"CBN-VOL-{int(volunteer.get('id') or 0):05d}"
    deadline, window = verification_window(7)
    deadline_str = f"{deadline.strftime('%A')} {deadline.day} {deadline.strftime('%B %Y')}"

    office_address = get("CBN_OFFICE_ADDRESS")
    office_phone   = get("CBN_OFFICE_PHONE")
    office_email   = get("CBN_OFFICE_EMAIL") or sender_address()

    approved = decision == "approved"

    subject = ("Your CBN volunteer application has been approved — action required"
               if approved else "Update on your CBN volunteer application")

    if approved:
        headline  = "Congratulations — you have been approved!"
        intro     = (f"We are delighted to let you know that your application to volunteer with "
                     f"{_h(ORG_NAME)} as a <strong>{_h(role)}</strong> has been <strong>approved</strong>.")
        intro_txt = (f"We are delighted to let you know that your application to volunteer with "
                     f"{ORG_NAME} as a {role} has been APPROVED.")
        next_title    = "Next step: final verification at our office"
        next_body     = (f"To complete your onboarding, please come to our office <strong>within one week</strong> "
                         f"— any working day (Monday to Friday) {_h(window)} — at <strong>{VERIFICATION_TIME}</strong> "
                         f"for a short final verification meeting (about 30 minutes).")
        next_body_txt = (f"To complete your onboarding, please come to our office WITHIN ONE WEEK "
                         f"— any working day (Monday to Friday) {window} — at {VERIFICATION_TIME} "
                         f"for a short final verification meeting (about 30 minutes).")
        bring = [
            "A valid photo ID (National ID card, passport or voter's card)",
            "One passport-size photograph",
            "Proof of address (utility bill or letter from your local authority)",
            "Original certificates for any qualifications listed on your application",
            f"This email or your reference number: {ref}",
        ]
        closing = (f"If you cannot attend within this period, please reply to this email or call "
                   f"{office_phone} so we can arrange another date. Places are confirmed only after "
                   f"verification, so please don't miss it!")
    else:
        headline  = "Thank you for applying"
        intro     = (f"Thank you for your interest in volunteering with {_h(ORG_NAME)} as a "
                     f"<strong>{_h(role)}</strong>. After careful review, we regret that we are "
                     f"<strong>not able to offer you a volunteer placement</strong> at this time.")
        intro_txt = (f"Thank you for your interest in volunteering with {ORG_NAME} as a {role}. "
                     f"After careful review, we regret that we are NOT able to offer you a volunteer "
                     f"placement at this time.")
        next_title    = "Would you like to discuss this decision?"
        next_body     = (f"Our volunteer coordinator would be happy to meet you and explain the decision, "
                         f"verify your documents and discuss other ways you could support CBN in future. "
                         f"You are welcome to come to our office <strong>within one week</strong> "
                         f"— any working day (Monday to Friday) {_h(window)} — at <strong>{VERIFICATION_TIME}</strong>.")
        next_body_txt = (f"Our volunteer coordinator would be happy to meet you and explain the decision, "
                         f"verify your documents and discuss other ways you could support CBN in future. "
                         f"You are welcome to come to our office WITHIN ONE WEEK — any working day "
                         f"(Monday to Friday) {window} — at {VERIFICATION_TIME}.")
        bring = [
            "A valid photo ID (National ID card, passport or voter's card)",
            f"This email or your reference number: {ref}",
        ]
        closing = ("This decision relates to current openings only — we encourage you to apply again "
                   "when new roles are advertised, and to follow our news page for upcoming "
                   "community events where extra hands are always welcome.")

    # ---------- plain text ----------
    lines = [
        f"Dear {name},", "", intro_txt, "",
        f"Application reference : {ref}",
        f"Role applied for      : {role}",
        f"Decision              : {decision.upper()}",
        "", next_title.upper(), next_body_txt, "",
        f"Where : {ORG_SHORT}, {office_address}",
        f"When  : Any working day up to {deadline_str}, at {VERIFICATION_TIME}",
        "", "Please bring:",
    ] + [f"  - {b}" for b in bring] + [
        "", closing, "",
        "Warm regards,", "Volunteer Coordination Team", ORG_NAME,
        office_address, f"Tel: {office_phone} · Email: {office_email}", "",
        "— This message was sent to the email address you entered on our volunteer application form.",
    ]
    text_body = "\n".join(lines)

    # ---------- HTML ----------
    colour   = "#16a34a" if approved else "#0a2a4a"
    badge_bg = "#dcfce7" if approved else "#eef1f5"
    badge_fg = "#065f46" if approved else "#374151"
    bring_html = "".join(f"<li style='margin:0 0 6px'>{_h(b)}</li>" for b in bring)

    html_body = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f6f9;font-family:Helvetica,Arial,sans-serif;color:#111827;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f9;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 18px rgba(0,0,0,.06);">
  <tr><td style="background:#0a2a4a;padding:22px 30px;">
    <table role="presentation" cellspacing="0" cellpadding="0"><tr>
      <td style="width:44px;height:44px;border-radius:50%;background:#f36f21;color:#fff;font-weight:800;text-align:center;vertical-align:middle;font-size:14px;">CBN</td>
      <td style="padding-left:12px;color:#fff;font-weight:700;font-size:16px;line-height:1.2;">
        Community Builders Network<br>
        <span style="font-weight:400;font-size:11px;letter-spacing:2px;color:#94a3b8;">SIERRA LEONE</span>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="height:5px;background:{colour};"></td></tr>
  <tr><td style="padding:32px 30px 8px;">
    <span style="display:inline-block;background:{badge_bg};color:{badge_fg};font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:6px 12px;border-radius:20px;">Application {_h(decision)}</span>
    <h1 style="margin:16px 0 8px;font-size:22px;color:#0a2a4a;">{_h(headline)}</h1>
    <p style="margin:0 0 14px;font-size:15px;line-height:1.65;color:#374151;">Dear {_h(name)},</p>
    <p style="margin:0 0 18px;font-size:15px;line-height:1.65;color:#374151;">{intro}</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f7f8fa;border:1px solid #e5e7eb;border-radius:6px;margin:0 0 24px;">
      <tr><td style="padding:14px 18px;font-size:13px;color:#6b7280;">Reference</td><td style="padding:14px 18px;font-size:13px;font-weight:700;color:#0a2a4a;font-family:monospace;">{_h(ref)}</td></tr>
      <tr><td style="padding:0 18px 14px;font-size:13px;color:#6b7280;">Role</td><td style="padding:0 18px 14px;font-size:13px;font-weight:700;color:#0a2a4a;">{_h(role)}</td></tr>
    </table>
    <h2 style="margin:0 0 10px;font-size:17px;color:#0a2a4a;">{_h(next_title)}</h2>
    <p style="margin:0 0 18px;font-size:15px;line-height:1.65;color:#374151;">{next_body}</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-left:4px solid #f36f21;background:#fff7ed;border-radius:0 6px 6px 0;margin:0 0 22px;">
      <tr><td style="padding:16px 18px;">
        <p style="margin:0 0 8px;font-size:14px;color:#7c2d12;"><strong>📍 Where:</strong> {_h(ORG_SHORT)}, {_h(office_address)}</p>
        <p style="margin:0 0 8px;font-size:14px;color:#7c2d12;"><strong>🗓 When:</strong> Any working day (Mon–Fri) up to <strong>{_h(deadline_str)}</strong></p>
        <p style="margin:0;font-size:14px;color:#7c2d12;"><strong>⏰ Time:</strong> {_h(VERIFICATION_TIME)} sharp</p>
      </td></tr>
    </table>
    <p style="margin:0 0 6px;font-size:14px;font-weight:700;color:#0a2a4a;">Please bring:</p>
    <ul style="margin:0 0 22px 20px;padding:0;font-size:14px;line-height:1.6;color:#374151;">{bring_html}</ul>
    <p style="margin:0 0 24px;font-size:14px;line-height:1.65;color:#374151;">{_h(closing)}</p>
    <p style="margin:0;font-size:14px;line-height:1.6;color:#374151;">Warm regards,<br>
      <strong>Volunteer Coordination Team</strong><br>{_h(ORG_NAME)}</p>
  </td></tr>
  <tr><td style="padding:18px 30px;background:#f7f8fa;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:#6b7280;">
    {_h(office_address)} · Tel {_h(office_phone)} · <a href="mailto:{_h(office_email)}" style="color:#f36f21;">{_h(office_email)}</a><br>
    This message was sent to the email address you entered on our volunteer application form.
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    return subject, text_body, html_body


# ------------------------------------------------------------------
# TEMPLATE — copy to the CBN inbox when a decision is made
# ------------------------------------------------------------------
def build_decision_copy_email(volunteer, decision, admin_username=""):
    """Internal record sent to the organisation's own inbox for every decision."""
    name  = f"{volunteer.get('first_name','')} {volunteer.get('last_name','')}".strip() or "Volunteer"
    ref   = f"CBN-VOL-{int(volunteer.get('id') or 0):05d}"
    role  = volunteer.get("role") or "General Volunteer"
    email = volunteer.get("email") or ""
    phone = volunteer.get("phone") or "—"
    deadline, _ = verification_window(7)
    deadline_str = f"{deadline.strftime('%A')} {deadline.day} {deadline.strftime('%B %Y')}"
    when = datetime.now().strftime("%d %B %Y at %H:%M")

    subject = f"[CBN Admin] Volunteer {decision.upper()}: {name} ({ref})"
    text = "\n".join([
        f"Volunteer application {decision.upper()}", "",
        f"Applicant : {name}",
        f"Email     : {email}",
        f"Phone     : {phone}",
        f"Role      : {role}",
        f"Reference : {ref}",
        f"Decided by: {admin_username or 'admin'} on {when}", "",
        f"The applicant has been emailed the decision and invited to the office",
        f"on any working day up to {deadline_str} at {VERIFICATION_TIME} for final verification.", "",
        "— CBN website backend (automatic copy for the office inbox)",
    ])
    colour = "#16a34a" if decision == "approved" else "#6b7280"
    html = f"""<div style="font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:8px;">
  <h2 style="color:#0a2a4a;margin:0 0 6px;">Volunteer application
     <span style="color:{colour};">{_h(decision.upper())}</span></h2>
  <p style="color:#6b7280;margin:0 0 18px;font-size:13px;">Decided by <strong>{_h(admin_username or 'admin')}</strong> on {_h(when)}</p>
  <table style="border-collapse:collapse;font-size:14px;color:#374151;width:100%;">
    <tr><td style="padding:6px 0;color:#6b7280;width:110px;">Applicant</td><td><strong>{_h(name)}</strong></td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Email</td><td><a href="mailto:{_h(email)}">{_h(email)}</a></td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Phone</td><td>{_h(phone)}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Role</td><td>{_h(role)}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Reference</td><td style="font-family:monospace;">{_h(ref)}</td></tr>
  </table>
  <p style="color:#374151;line-height:1.6;margin:18px 0 0;">The applicant has been emailed the decision and invited to the office on any working day up to <strong>{_h(deadline_str)}</strong> at <strong>{_h(VERIFICATION_TIME)}</strong> for final verification.</p>
  <p style="color:#9ca3af;font-size:12px;margin:18px 0 0;">Automatic copy for the office inbox — CBN website backend.</p>
</div>"""
    return subject, text, html


# ------------------------------------------------------------------
# TEMPLATE — application received (to applicant) + new-application alert (to office)
# ------------------------------------------------------------------
def build_application_received_email(volunteer):
    """Immediate acknowledgement sent to the applicant when the form is submitted."""
    first = (volunteer.get("first_name") or "").strip() or "Volunteer"
    ref   = f"CBN-VOL-{int(volunteer.get('id') or 0):05d}"
    role  = volunteer.get("role") or "General Volunteer"
    office_phone = get("CBN_OFFICE_PHONE")
    office_email = get("CBN_OFFICE_EMAIL") or sender_address()

    subject = f"We received your volunteer application ({ref})"
    text = "\n".join([
        f"Dear {first},", "",
        f"Thank you for applying to volunteer with {ORG_NAME} as a {role}.",
        f"Your application reference is {ref}.", "",
        "Our volunteer coordination team will review your application and email you",
        "a decision within 3 working days. If approved, that email will invite you to",
        f"our office for a short final verification meeting at {VERIFICATION_TIME}.", "",
        f"Questions? Reply to this email or call {office_phone}.", "",
        "Warm regards,", "Volunteer Coordination Team", ORG_NAME,
        f"{get('CBN_OFFICE_ADDRESS')} · {office_email}",
    ])
    html = f"""<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
  <div style="background:#0a2a4a;color:#fff;padding:18px 26px;font-weight:700;">Community Builders Network <span style="color:#94a3b8;font-weight:400;font-size:11px;letter-spacing:2px;">SIERRA LEONE</span></div>
  <div style="padding:26px;color:#374151;line-height:1.65;font-size:15px;">
    <p>Dear {_h(first)},</p>
    <p>Thank you for applying to volunteer with <strong>{_h(ORG_NAME)}</strong> as a <strong>{_h(role)}</strong>.</p>
    <p style="background:#f7f8fa;border:1px solid #e5e7eb;border-radius:6px;padding:12px 16px;font-size:14px;">Your application reference: <strong style="font-family:monospace;color:#0a2a4a;">{_h(ref)}</strong></p>
    <p>Our volunteer coordination team will review your application and email you a decision within <strong>3 working days</strong>. If approved, that email will invite you to our office for a short final verification meeting at <strong>{_h(VERIFICATION_TIME)}</strong>.</p>
    <p>Questions? Simply reply to this email or call {_h(office_phone)}.</p>
    <p style="margin-top:22px;">Warm regards,<br><strong>Volunteer Coordination Team</strong><br>{_h(ORG_NAME)}</p>
  </div>
  <div style="padding:14px 26px;background:#f7f8fa;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;">{_h(get('CBN_OFFICE_ADDRESS'))} · <a href="mailto:{_h(office_email)}" style="color:#f36f21;">{_h(office_email)}</a></div>
</div>"""
    return subject, text, html


def build_new_application_alert(volunteer, admin_url="/admin/volunteers"):
    """Alert sent to the organisation's inbox the moment a new application arrives."""
    name  = f"{volunteer.get('first_name','')} {volunteer.get('last_name','')}".strip() or "Volunteer"
    ref   = f"CBN-VOL-{int(volunteer.get('id') or 0):05d}"
    role  = volunteer.get("role") or "General Volunteer"
    avail = volunteer.get("availability") or "—"
    email = volunteer.get("email") or ""
    phone = volunteer.get("phone") or "—"
    msg   = (volunteer.get("message") or "").strip() or "—"
    when  = datetime.now().strftime("%d %B %Y at %H:%M")

    subject = f"[CBN Admin] New volunteer application: {name} ({ref})"
    text = "\n".join([
        "A new volunteer application has been submitted on the website.", "",
        f"Applicant    : {name}",
        f"Email        : {email}",
        f"Phone        : {phone}",
        f"Role         : {role}",
        f"Availability : {avail}",
        f"Reference    : {ref}",
        f"Submitted    : {when}", "",
        "Message from applicant:", msg, "",
        f"Review it in the admin panel: {admin_url}",
        "Approving or rejecting there will automatically email the applicant the decision.",
    ])
    html = f"""<div style="font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:8px;">
  <h2 style="color:#0a2a4a;margin:0 0 6px;">🆕 New volunteer application</h2>
  <p style="color:#6b7280;margin:0 0 18px;font-size:13px;">Submitted {_h(when)}</p>
  <table style="border-collapse:collapse;font-size:14px;color:#374151;width:100%;">
    <tr><td style="padding:6px 0;color:#6b7280;width:110px;">Applicant</td><td><strong>{_h(name)}</strong></td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Email</td><td><a href="mailto:{_h(email)}">{_h(email)}</a></td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Phone</td><td>{_h(phone)}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Role</td><td>{_h(role)}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Availability</td><td>{_h(avail)}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;">Reference</td><td style="font-family:monospace;">{_h(ref)}</td></tr>
  </table>
  <p style="margin:16px 0 4px;color:#6b7280;font-size:13px;">Message from applicant:</p>
  <blockquote style="margin:0;padding:12px 16px;background:#f7f8fa;border-left:4px solid #f36f21;color:#374151;font-size:14px;line-height:1.6;">{_h(msg)}</blockquote>
  <p style="margin:18px 0 0;"><a href="{_h(admin_url)}" style="display:inline-block;background:#f36f21;color:#fff;text-decoration:none;font-weight:700;padding:10px 18px;border-radius:5px;">Review in admin panel →</a></p>
  <p style="color:#9ca3af;font-size:12px;margin:18px 0 0;">Approving or rejecting in the admin panel automatically emails the applicant the decision.</p>
</div>"""
    return subject, text, html


# ------------------------------------------------------------------
# TEMPLATE — donation receipt (to donor) + donation alert (to office)
# ------------------------------------------------------------------
def _sle(amount_sll):
    return f"SLE {int(amount_sll) / 1000:,.2f}"


def build_donation_receipt_email(d):
    first = (d.get("first_name") or "").strip() or "Friend"
    ref   = d.get("reference") or ""
    amt   = int(d.get("amount_sll") or 0)
    proj  = d.get("project_designation") or ""
    proj_line = f" towards <strong>{_h(proj.replace('-', ' ').title())}</strong>" if proj else ""
    proj_txt  = f" towards {proj.replace('-', ' ').title()}" if proj else ""
    when  = datetime.now().strftime("%d %B %Y at %H:%M")
    mode  = (d.get("gateway_mode") or "").lower()
    test_note_txt = ("\n\nNOTE: this was a TEST transaction — no money was charged.\n" if mode in ("test", "simulation") else "")
    test_note_html = ('<p style="background:#fef3c7;color:#92400e;padding:10px 14px;border-radius:6px;font-size:13px;">'
                      '<strong>Test transaction</strong> — no money was charged.</p>' if mode in ("test", "simulation") else "")
    subject = f"Thank you for your donation to CBN — receipt {ref}"
    text = "\n".join([
        f"Dear {first},", "",
        f"Thank you! We have received your donation of {_sle(amt)} (Le {amt:,}){proj_txt}.", "",
        f"Receipt reference : {ref}",
        f"Amount            : {_sle(amt)}",
        f"Payment method    : {(d.get('payment_method') or 'Monime').replace('_', ' ').title()}",
        f"Date              : {when}",
        f"Transaction id    : {d.get('om_transaction_id') or d.get('order_number') or '—'}",
        test_note_txt,
        "100% of your gift reaches communities in Sierra Leone. You will receive our quarterly impact",
        "report so you can see exactly what it made possible.", "",
        "With gratitude,", "Community Builders Network - Sierra Leone",
        f"{get('CBN_OFFICE_ADDRESS')} · {get('CBN_OFFICE_PHONE')} · {get('CBN_OFFICE_EMAIL') or sender_address()}",
    ])
    html = f"""<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
  <div style="background:#0a2a4a;color:#fff;padding:18px 26px;font-weight:700;">Community Builders Network <span style="color:#94a3b8;font-weight:400;font-size:11px;letter-spacing:2px;">SIERRA LEONE</span></div>
  <div style="height:5px;background:#16a34a;"></div>
  <div style="padding:26px;color:#374151;line-height:1.65;font-size:15px;">
    <h2 style="color:#0a2a4a;margin:0 0 10px;">Thank you, {_h(first)}! 🎉</h2>
    <p>We have received your donation of <strong>{_h(_sle(amt))}</strong> <span style="color:#6b7280;">(Le {amt:,})</span>{proj_line}.</p>
    {test_note_html}
    <table style="width:100%;border-collapse:collapse;background:#f7f8fa;border:1px solid #e5e7eb;border-radius:6px;font-size:14px;margin:16px 0;">
      <tr><td style="padding:10px 14px;color:#6b7280;width:45%;">Receipt reference</td><td style="padding:10px 14px;font-family:monospace;font-weight:700;color:#0a2a4a;">{_h(ref)}</td></tr>
      <tr><td style="padding:10px 14px;color:#6b7280;">Payment method</td><td style="padding:10px 14px;">{_h((d.get('payment_method') or 'Monime').replace('_',' ').title())}</td></tr>
      <tr><td style="padding:10px 14px;color:#6b7280;">Transaction id</td><td style="padding:10px 14px;font-family:monospace;">{_h(d.get('om_transaction_id') or d.get('order_number') or '—')}</td></tr>
      <tr><td style="padding:10px 14px;color:#6b7280;">Date</td><td style="padding:10px 14px;">{_h(when)}</td></tr>
    </table>
    <p>100% of your gift reaches communities in Sierra Leone. You'll receive our quarterly impact report so you can see exactly what it made possible.</p>
    <p style="margin-top:22px;">With gratitude,<br><strong>Community Builders Network - Sierra Leone</strong></p>
  </div>
  <div style="padding:14px 26px;background:#f7f8fa;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;">{_h(get('CBN_OFFICE_ADDRESS'))} · {_h(get('CBN_OFFICE_PHONE'))} · {_h(get('CBN_OFFICE_EMAIL') or sender_address())}</div>
</div>"""
    return subject, text, html


def build_donation_alert_email(d):
    ref  = d.get("reference") or ""
    amt  = int(d.get("amount_sll") or 0)
    name = ("Anonymous" if d.get("anonymous") else
            f"{d.get('first_name','')} {d.get('last_name','')}".strip()) or "Donor"
    mode = (d.get("gateway_mode") or "").upper()
    subject = f"[CBN Admin] Donation received: {_sle(amt)} from {name} ({ref}){' — ' + mode if mode and mode != 'LIVE' else ''}"
    text = "\n".join([
        f"A donation has been confirmed by Monime{' in ' + mode + ' mode' if mode else ''}.", "",
        f"Reference : {ref}",
        f"Amount    : {_sle(amt)}  (Le {amt:,})",
        f"Donor     : {name}",
        f"Email     : {d.get('email') or '—'}",
        f"Phone     : {d.get('phone') or '—'}",
        f"Method    : {d.get('payment_method') or '—'}",
        f"Project   : {d.get('project_designation') or 'General fund'}",
        f"Frequency : {d.get('frequency') or 'once'}",
        f"Monime id : {d.get('checkout_session_id') or '—'}  order {d.get('order_number') or '—'}", "",
        "The donor has been emailed a receipt. See Admin → Donations for details.",
    ])
    html = "<pre style='font-family:Helvetica,Arial,sans-serif;white-space:pre-wrap;color:#374151;line-height:1.6;'>" + _h(text) + "</pre>"
    return subject, text, html


# ------------------------------------------------------------------
# TEMPLATE — admin test email
# ------------------------------------------------------------------
def build_test_email(to_addr, admin_username=""):
    when = datetime.now().strftime("%d %B %Y at %H:%M")
    subject = "CBN email test — your settings work"
    text = "\n".join([
        "Hello,", "",
        f"This is a test message from the {ORG_NAME} website.",
        f"It was sent from {sender_address()} to {to_addr} on {when}"
        + (f" by admin '{admin_username}'." if admin_username else "."), "",
        "If you are reading this, volunteer decision emails will be delivered the same way.", "",
        "— CBN website backend",
    ])
    html = f"""<div style="font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:8px;">
  <h2 style="color:#0a2a4a;margin:0 0 12px;">✅ CBN email test</h2>
  <p style="color:#374151;line-height:1.6;">This is a test message from the <strong>{_h(ORG_NAME)}</strong> website.</p>
  <p style="color:#374151;line-height:1.6;">Sent from <strong>{_h(sender_address())}</strong> to <strong>{_h(to_addr)}</strong> on {_h(when)}{f" by admin <strong>{_h(admin_username)}</strong>" if admin_username else ""}.</p>
  <p style="color:#374151;line-height:1.6;">If you are reading this, volunteer decision emails will be delivered the same way.</p>
</div>"""
    return subject, text, html


# ------------------------------------------------------------------
# SENDING
# ------------------------------------------------------------------
def send_email(to_addr, subject, text_body, html_body=None, to_name=""):
    """Send one email. Returns (ok, detail). Never raises."""
    msg = EmailMessage()
    msg["Subject"]    = subject
    msg["From"]       = sender_header()
    msg["To"]         = formataddr((to_name, to_addr)) if to_name else to_addr
    msg["Date"]       = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender_address().split("@")[-1])
    reply_to = get("CBN_SMTP_REPLY_TO").strip()
    if reply_to and reply_to.lower() != sender_address().lower():
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if not is_configured():
        _print_console(msg, text_body)
        return True, "console"

    return _deliver(msg, to_addr)


# ------------------------------------------------------------------
# TRANSPORT — resilient delivery
# ------------------------------------------------------------------
# The "SSLEOFError: UNEXPECTED_EOF_WHILE_READING" seen on macOS happens when
# the TLS handshake is cut off mid-negotiation. In practice it has three
# causes, and this transport layer handles all of them:
#
#   1. Python's own CA store is empty (python.org builds on macOS don't use
#      the system Keychain)          → use the `certifi` bundle when present
#   2. A proxy / firewall / antivirus interferes with STARTTLS on port 587
#                                    → fall back to implicit TLS on port 465
#   3. Momentary network drop        → retry with back-off
#
# Whichever (port, mode) succeeds is remembered and tried first next time.

_ROUTES_GMAIL = [(587, "starttls"), (465, "ssl")]
_MAX_ATTEMPTS = 3                     # per route
_BACKOFF      = (1.0, 3.0)            # seconds between attempts
_preferred_route = None               # last route that worked
_route_lock = threading.Lock()


def _ssl_context():
    """
    TLS context that verifies Gmail's certificate. Prefers the certifi CA
    bundle (always current), then the interpreter's default store.
    """
    cafile = None
    try:
        import certifi                                     # optional dependency
        cafile = certifi.where()
    except Exception:
        cafile = os.environ.get("SSL_CERT_FILE") or None
    ctx = ssl.create_default_context(cafile=cafile)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _routes():
    """Ordered list of (port, mode) to try — preferred/known-good route first."""
    configured = _port()
    mode = "ssl" if configured == 465 else "starttls"
    routes = [(configured, mode)]
    if is_gmail():
        for r in _ROUTES_GMAIL:
            if r not in routes:
                routes.append(r)
    with _route_lock:
        pref = _preferred_route
    if pref in routes:
        routes.remove(pref)
        routes.insert(0, pref)
    return routes


def _open_session(host, port, mode, ctx):
    """Open + authenticate an SMTP session on the given route. Caller closes it."""
    user, pw = get("CBN_SMTP_USER").strip(), get("CBN_SMTP_PASS")
    if mode == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=ctx)
        s.ehlo()
    else:
        s = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
    if user:
        s.login(user, pw)
    return s


def _is_transient(exc):
    """Errors worth retrying / re-routing (network + TLS handshake failures)."""
    if isinstance(exc, (ssl.SSLEOFError, ssl.SSLZeroReturnError, socket.timeout,
                        ConnectionResetError, ConnectionAbortedError, ConnectionRefusedError,
                        smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                        smtplib.SMTPHeloError)):
        return True
    if isinstance(exc, ssl.SSLError):
        return True                       # handshake problems: try other route / retry
    if isinstance(exc, OSError) and not isinstance(exc, smtplib.SMTPException):
        return True                       # generic socket-level failure
    return False


def _is_dns_failure(exc):
    """socket.gaierror (Errno 8 on macOS / -2 on Linux / 11001 on Windows) = name lookup failed."""
    return isinstance(exc, socket.gaierror)


def _friendly_ssl_hint(exc):
    text = str(exc)
    if _is_dns_failure(exc):
        return ("Your computer could not look up the address of the mail server (DNS failed). "
                "This almost always means the machine is offline or on a Wi-Fi network that needs a "
                "sign-in page — check the internet connection, sign in to the hotspot/captive portal, "
                "or disconnect any VPN, then retry. Queued emails are sent automatically when the "
                "connection returns.")
    if "CERTIFICATE_VERIFY_FAILED" in text:
        return ("Python cannot verify Gmail's certificate — install the certifi package "
                "(pip3 install certifi) or run 'Install Certificates.command' in your Python folder.")
    if "UNEXPECTED_EOF" in text or isinstance(exc, ssl.SSLEOFError):
        return ("The TLS connection was cut off before completing. This is usually a firewall, VPN, "
                "antivirus or corporate proxy interfering with outgoing mail; try another network, "
                "or check that ports 587/465 to smtp.gmail.com are allowed.")
    if isinstance(exc, socket.timeout):
        return ("The mail server did not answer in time — the network may be very slow or a firewall "
                "may be silently dropping ports 587/465.")
    return ""


# ------------------------------------------------------------------
# CONNECTIVITY PRE-FLIGHT
# ------------------------------------------------------------------
class NetworkUnavailable(Exception):
    """Raised when the mail host cannot even be resolved — no point trying routes."""


def check_connectivity(host=None, timeout=6):
    """
    Quick diagnosis that takes < a few seconds:
      1. Can we resolve the SMTP host?           (DNS)
      2. Can we resolve anything at all?         (distinguishes 'offline' from 'blocked host')
      3. Can we open a TCP socket to 587 or 465? (firewall / captive portal)
    Returns (ok, detail).
    """
    host = (host or get("CBN_SMTP_HOST") or "").strip()
    if not host:
        return False, "no SMTP host configured"

    def _resolves(h):
        try:
            socket.getaddrinfo(h, None)
            return True
        except socket.gaierror:
            return False

    if not _resolves(host):
        if _resolves("www.google.com") or _resolves("cloudflare.com"):
            return False, (f"DNS works but '{host}' cannot be resolved — check the SMTP host spelling "
                           f"in Email Settings (should be smtp.gmail.com).")
        return False, ("No internet connection — DNS lookups are failing for every host. Connect to "
                       "the internet (and sign in to the Wi-Fi/hotspot page if one appears), then retry.")

    for port in (587, 465):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, f"network OK — {host}:{port} reachable"
        except OSError:
            continue
    return False, (f"'{host}' resolves but ports 587 and 465 are blocked — a firewall, VPN or the "
                   f"network operator is blocking outgoing mail. Try a different network or mobile hotspot.")


def _run_with_routes(action, what):
    """
    Try `action(session)` over every route with retries.
    Returns (ok, detail). Never raises.
    """
    global _preferred_route
    host = get("CBN_SMTP_HOST").strip()
    ctx  = _ssl_context()
    user = get("CBN_SMTP_USER").strip()
    last_err = None
    tried = []

    # Pre-flight: if the host doesn't even resolve, fail fast with a clear reason
    # instead of burning ~6 attempts across two ports.
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        ok_net, why = check_connectivity(host)
        print(f"[mailer] ⛔ cannot resolve {host}: {why}")
        return False, f"NETWORK: {why}"

    for port, mode in _routes():
        label = f"{host}:{port} ({'SSL' if mode == 'ssl' else 'STARTTLS'})"
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            s = None
            try:
                s = _open_session(host, port, mode, ctx)
                result = action(s)
                with _route_lock:
                    _preferred_route = (port, mode)
                return True, f"{what} via {label}" + (f" after {attempt} attempts" if attempt > 1 else "")
            except smtplib.SMTPAuthenticationError as e:
                # Credentials are wrong — no point retrying or re-routing
                if is_gmail():
                    return False, (f"Gmail rejected the App Password for {user} [{e.smtp_code}]. "
                                   f"Make sure 2-Step Verification is ON for that account and re-create "
                                   f"the 16-character App Password (Admin → Email Settings).")
                return False, f"SMTP authentication failed for {user}: {e}"
            except smtplib.SMTPRecipientsRefused as e:
                return False, f"recipient address refused by the mail server: {e.recipients}"
            except smtplib.SMTPSenderRefused as e:
                return False, f"sender {sender_address()} refused by the mail server: {e}"
            except smtplib.SMTPDataError as e:
                return False, f"mail server rejected the message [{e.smtp_code}]: {e.smtp_error}"
            except Exception as e:
                last_err = e
                tried.append(f"{label} attempt {attempt}: {type(e).__name__}: {e}")
                print(f"[mailer] ⚠ {label} attempt {attempt}/{_MAX_ATTEMPTS} failed: {type(e).__name__}: {e}")
                if _is_dns_failure(e):
                    # Network vanished mid-way — every route will fail identically. Stop now.
                    ok_net, why = check_connectivity(host)
                    return False, f"NETWORK: {why}"
                if not _is_transient(e):
                    break                                  # permanent → next route
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_BACKOFF[min(attempt - 1, len(_BACKOFF) - 1)])
            finally:
                if s is not None:
                    try:
                        s.quit()
                    except Exception:
                        try: s.close()
                        except Exception: pass

    hint = _friendly_ssl_hint(last_err) if last_err else ""
    detail = (f"{type(last_err).__name__}: {last_err}" if last_err else "no route available")
    if hint:
        detail += f" — {hint}"
    detail += f" (tried: {'; '.join(tried)})" if tried else ""
    return False, detail


def _deliver(msg, to_addr):
    return _run_with_routes(lambda s: s.send_message(msg),
                            f"sent from {sender_address()}")


def verify_connection():
    """
    Log in to the SMTP server with the saved credentials WITHOUT sending anything.
    Returns (ok, detail). Used at start-up so a wrong App Password or a blocked
    port is reported immediately instead of on the first volunteer approval.
    """
    if not is_configured():
        return False, status()[1]
    ok, detail = _run_with_routes(lambda s: s.noop(),
                                  f"logged in as {get('CBN_SMTP_USER').strip()} — ready to send")
    return ok, detail


def verify_connection_async(on_done=None):
    """Run verify_connection() in the background (start-up must not block on the network)."""
    def _worker():
        ok, detail = verify_connection()
        if on_done:
            try:
                on_done(ok, detail)
            except Exception as e:
                print(f"[mailer] verify callback error: {e}")
    t = threading.Thread(target=_worker, name="cbn-mailer-verify", daemon=True)
    t.start()
    return t


# ------------------------------------------------------------------
# INBOX — read replies from applicants (IMAP, standard library)
# ------------------------------------------------------------------
# The same Gmail App Password works for IMAP. Gmail needs IMAP enabled:
#   Gmail → Settings ⚙ → See all settings → Forwarding and POP/IMAP → Enable IMAP
# (it is ON by default for new accounts).

import imaplib
import email as _email_pkg
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, getaddresses

IMAP_HOST    = "imap.gmail.com"
IMAP_PORT    = 993
IMAP_TIMEOUT = 25


def _decode_hdr(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body_text(msg):
    """Best-effort plain-text body of an email.message.Message."""
    if msg.is_multipart():
        # Prefer text/plain, fall back to stripped text/html
        plain, html = None, None
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = payload.decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                continue
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
        if plain is not None:
            return plain
        if html is not None:
            import re
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
        return ""
    try:
        payload = msg.get_payload(decode=True)
        return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""
    except Exception:
        return ""


def _strip_quoted(text, max_len=4000):
    """Drop quoted history ('On … wrote:', lines starting with '>') and trim."""
    import re
    lines = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*On .+wrote:\s*$", line) or line.strip().startswith("-----Original Message"):
            break
        if line.lstrip().startswith(">"):
            continue
        lines.append(line.rstrip())
    out = "\n".join(lines).strip()
    return out[:max_len]


def fetch_inbox(since_uid=0, limit=50):
    """
    Fetch new messages from the Gmail inbox with UID > since_uid.
    Returns (ok, detail, messages) where each message is a dict:
      uid, message_id, in_reply_to, from_name, from_addr, to_addr,
      subject, body, received_at (ISO), volunteer_ref (e.g. 'CBN-VOL-00003' or '')
    """
    if not is_configured():
        return False, status()[1], []
    user, pw = get("CBN_SMTP_USER").strip(), get("CBN_SMTP_PASS")
    ctx = _ssl_context()
    out = []
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx, timeout=IMAP_TIMEOUT) as M:
            M.login(user, pw)
            M.select("INBOX", readonly=True)
            typ, data = M.uid("SEARCH", None, f"UID {int(since_uid) + 1}:*")
            if typ != "OK":
                return False, f"IMAP search failed: {typ}", []
            uids = [int(u) for u in (data[0] or b"").split() if int(u) > int(since_uid)]
            uids = uids[-limit:]                       # newest N only
            import re
            ref_re = re.compile(r"CBN-VOL-\d{5}")
            for uid in uids:
                typ, parts = M.uid("FETCH", str(uid), "(RFC822)")
                if typ != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                msg = _email_pkg.message_from_bytes(parts[0][1])
                from_pairs = getaddresses([_decode_hdr(msg.get("From", ""))])
                from_name, from_addr = (from_pairs[0] if from_pairs else ("", ""))
                to_pairs = getaddresses([_decode_hdr(msg.get("To", ""))])
                to_addr = to_pairs[0][1] if to_pairs else ""
                subject = _decode_hdr(msg.get("Subject", ""))
                body = _strip_quoted(_body_text(msg))
                try:
                    received = parsedate_to_datetime(msg.get("Date")).astimezone().isoformat(timespec="seconds")
                except Exception:
                    received = datetime.now().isoformat(timespec="seconds")
                m = ref_re.search(subject) or ref_re.search(body) or ref_re.search(_body_text(msg))
                out.append({
                    "uid": uid,
                    "message_id": (msg.get("Message-ID") or "").strip(),
                    "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
                    "from_name": from_name, "from_addr": (from_addr or "").lower(),
                    "to_addr": (to_addr or "").lower(),
                    "subject": subject, "body": body, "received_at": received,
                    "volunteer_ref": m.group(0) if m else "",
                })
        return True, f"fetched {len(out)} new message(s)", out
    except imaplib.IMAP4.error as e:
        text = str(e)
        if "AUTHENTICATIONFAILED" in text.upper() or "Invalid credentials" in text:
            return False, ("Gmail rejected the IMAP login — the App Password works for SMTP but "
                           "IMAP may be disabled: Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP."), []
        return False, f"IMAP error: {e}", []
    except (ssl.SSLError, socket.timeout, socket.gaierror, ConnectionError, OSError) as e:
        hint = _friendly_ssl_hint(e)
        return False, f"could not reach {IMAP_HOST}:{IMAP_PORT} — {type(e).__name__}: {e}" + (f" — {hint}" if hint else ""), []


def send_async(to_addr, subject, text_body, html_body=None, to_name="", on_done=None):
    """
    Deliver an email reliably:
      • try to send right now on a background thread;
      • if it fails for a NETWORK reason (offline, DNS, blocked port, timeout),
        keep it in the outbox and let the worker retry with back-off until it
        goes through — so approving a volunteer while offline still results in
        the email being sent once the connection is back;
      • permanent failures (bad password, refused recipient) are reported at once.
    `on_done(ok, detail)` is called on the FIRST outcome; queued messages call it
    with ok=False and a detail starting with 'QUEUED:'; the outbox worker updates
    email_log itself when the retry eventually succeeds.
    """
    import database as _db   # local import: keeps mailer importable on its own

    # The caller's on_done usually finalises an email_log row. The outbox must be
    # able to finalise that same row later (delayed success), so server.py
    # attaches the id as on_done.email_log_id.
    kwargs_log_id = getattr(on_done, "email_log_id", None)

    if not is_configured():
        # Console mode: print immediately (nothing to queue)
        def _console():
            ok, detail = send_email(to_addr, subject, text_body, html_body, to_name)
            if on_done:
                try: on_done(ok, detail)
                except Exception as e: print(f"[mailer] on_done callback error: {e}")
        threading.Thread(target=_console, name="cbn-mailer", daemon=True).start()
        return None

    outbox_id = _db.outbox_enqueue(to_addr, subject, text_body, html_body, to_name,
                                   kind="", email_log_id=kwargs_log_id)

    def _worker():
        # Claim only this row (never touch other queued mail) and attempt at once
        row = _db.outbox_claim_one(outbox_id)
        if not row:
            return                       # the background worker already took it
        ok, detail = _attempt_outbox_row(row, _db)
        if on_done:
            try:
                on_done(ok, detail)
            except Exception as e:
                print(f"[mailer] on_done callback error: {e}")

    threading.Thread(target=_worker, name="cbn-mailer", daemon=True).start()
    return outbox_id


# ------------------------------------------------------------------
# OUTBOX WORKER — retries until the network is back
# ------------------------------------------------------------------
_RETRY_SCHEDULE = (30, 60, 120, 300, 600, 900)     # seconds; last value repeats
_outbox_lock = threading.Lock()


def _retry_delay(attempts):
    return _RETRY_SCHEDULE[min(attempts, len(_RETRY_SCHEDULE) - 1)]


def _attempt_outbox_row(row, _db):
    """
    Try to send one claimed outbox row. Updates outbox + (if linked) email_log.
    Returns (ok, detail) where a network failure yields detail 'QUEUED: …'.
    """
    msg = EmailMessage()
    msg["Subject"]    = row["subject"]
    msg["From"]       = sender_header()
    msg["To"]         = formataddr((row["to_name"], row["to_address"])) if row["to_name"] else row["to_address"]
    msg["Date"]       = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender_address().split("@")[-1])
    reply_to = get("CBN_SMTP_REPLY_TO").strip()
    if reply_to and reply_to.lower() != sender_address().lower():
        msg["Reply-To"] = reply_to
    msg.set_content(row["text_body"])
    if row["html_body"]:
        msg.add_alternative(row["html_body"], subtype="html")

    ok, detail = _deliver(msg, row["to_address"])
    attempts = int(row.get("attempts") or 0)

    if ok:
        _db.outbox_mark_sent(row["id"], detail)
        if row.get("email_log_id"):
            _db.email_log_finish(row["email_log_id"], True, detail)
        return True, detail

    network_problem = detail.startswith("NETWORK:") or any(
        k in detail for k in ("timed out", "timeout", "Timeout", "UNEXPECTED_EOF",
                              "ConnectionReset", "ConnectionRefused", "Errno 8", "Errno -2",
                              "nodename nor servname", "Name or service not known",
                              "Network is unreachable", "SSLEOFError"))

    if network_problem and attempts + 1 < int(row.get("max_attempts") or 30):
        delay = _retry_delay(attempts)
        _db.outbox_mark_retry(row["id"], detail, delay)
        queued_detail = (f"QUEUED: will retry in {delay}s (attempt {attempts + 1}) — "
                         f"{detail.replace('NETWORK: ', '')}")
        if row.get("email_log_id"):
            # Keep the log row as 'queued' but record why
            _db.execute("UPDATE email_log SET detail=? WHERE id=?",
                        (queued_detail[:500], row["email_log_id"]))
        print(f"[outbox] ⏳ #{row['id']} → {row['to_address']} queued: {detail.split(' (tried')[0]}")
        return False, queued_detail

    _db.outbox_mark_failed(row["id"], detail)
    if row.get("email_log_id"):
        _db.email_log_finish(row["email_log_id"], False, detail)
    return False, detail


def process_outbox(limit=20):
    """
    Send everything that is due. Returns (sent, requeued, failed).
    Safe to call from the poller thread and from the admin 'Send now' button.
    """
    import database as _db
    if not _outbox_lock.acquire(blocking=False):
        return 0, 0, 0
    try:
        if not is_configured():
            return 0, 0, 0
        _db.outbox_release_stuck()
        rows = _db.outbox_claim_due(limit=limit)
        if not rows:
            return 0, 0, 0
        # One quick connectivity check for the whole batch — if we are offline,
        # re-queue everything immediately without hammering the network.
        net_ok, why = check_connectivity()
        sent = requeued = failed = 0
        for r in rows:
            if not net_ok:
                delay = _retry_delay(int(r.get("attempts") or 0))
                _db.outbox_mark_retry(r["id"], f"NETWORK: {why}", delay)
                if r.get("email_log_id"):
                    _db.execute("UPDATE email_log SET detail=? WHERE id=?",
                                (f"QUEUED: waiting for network — {why}"[:500], r["email_log_id"]))
                requeued += 1
                continue
            ok, detail = _attempt_outbox_row(r, _db)
            if ok:
                sent += 1
                print(f"[outbox] ✅ #{r['id']} → {r['to_address']}: {detail}")
            elif detail.startswith("QUEUED:"):
                requeued += 1
            else:
                failed += 1
                print(f"[outbox] ❌ #{r['id']} → {r['to_address']}: {detail}")
        if not net_ok and rows:
            print(f"[outbox] 📴 offline — {len(rows)} email(s) waiting: {why}")
        return sent, requeued, failed
    finally:
        _outbox_lock.release()


def start_outbox_worker(interval_seconds=30):
    """Background thread: deliver due outbox rows every `interval_seconds`."""
    def _loop():
        time.sleep(8)                                   # let start-up finish
        while True:
            try:
                process_outbox()
            except Exception as e:                      # never let the worker die
                print(f"[outbox] worker error: {type(e).__name__}: {e}")
            time.sleep(interval_seconds)
    threading.Thread(target=_loop, name="cbn-outbox", daemon=True).start()


def _print_console(msg, text_body):
    bar = "─" * 70
    print(f"\n┌{bar}┐")
    print("│  📧  EMAIL (console mode — not actually sent)")
    print(f"├{bar}┤")
    print(f"│  From    : {msg['From']}")
    print(f"│  To      : {msg['To']}")
    print(f"│  Subject : {msg['Subject']}")
    print(f"├{bar}┤")
    for line in text_body.splitlines():
        print(f"│  {line}")
    print(f"└{bar}┘\n")


# Load once at import so every handler sees the effective configuration.
load_config()
