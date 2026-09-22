"""
CBN Backend — Admin Panel HTML rendering
========================================
Server-side templates for the admin panel. Everything user-supplied
is escaped through `esc()` in security.py to prevent XSS.
"""

from security import esc


# ------------------------------------------------------------------
# BASE LAYOUT
# ------------------------------------------------------------------
BASE_CSS = """
:root {
  --navy:#0a2a4a; --navy-d:#061a30; --orange:#f36f21; --orange-d:#d95e15;
  --gray-50:#f7f8fa; --gray-100:#eef1f5; --gray-200:#dfe4ec; --gray-500:#6b7280;
  --gray-700:#374151; --gray-900:#111827; --green:#16a34a; --red:#dc2626;
  --yellow:#f59e0b;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Helvetica Neue",Arial,sans-serif; background:var(--gray-50);
  color:var(--gray-900); font-size:14px; line-height:1.5; }
a { color:var(--orange); text-decoration:none; }
a:hover { text-decoration:underline; }

/* Layout */
.admin-wrap { display:flex; min-height:100vh; }
.sidebar { width:240px; background:var(--navy-d); color:#cbd5e1;
  display:flex; flex-direction:column; padding:24px 0; }
.sidebar .brand { padding:0 22px 24px; border-bottom:1px solid #ffffff1a; }
.sidebar .brand strong { color:#fff; display:block; font-size:15px; }
.sidebar .brand span { font-size:11px; color:#94a3b8; letter-spacing:1.5px;
  text-transform:uppercase; }
.sidebar nav { flex:1; padding:16px 0; }
.sidebar nav a { display:block; padding:11px 22px; color:#cbd5e1;
  border-left:3px solid transparent; font-size:13px; }
.sidebar nav a:hover { background:#ffffff0d; color:#fff; text-decoration:none; }
.sidebar nav a.active { background:#ffffff14; color:#fff;
  border-left-color:var(--orange); }
.sidebar .foot { padding:16px 22px; border-top:1px solid #ffffff1a;
  font-size:12px; color:#94a3b8; }
.sidebar .foot form { display:inline; }
.sidebar .foot button { background:none; border:0; color:var(--orange);
  cursor:pointer; padding:0; font:inherit; }

.main { flex:1; padding:32px 40px; overflow:auto; }
.page-head { display:flex; justify-content:space-between; align-items:center;
  margin-bottom:24px; }
.page-head h1 { font-size:22px; color:var(--navy); }

/* Flash messages */
.flash { padding:12px 18px; border-radius:6px; margin-bottom:20px; font-size:13px; }
.flash.ok    { background:#dcfce7; color:#065f46; border-left:4px solid var(--green); }
.flash.err   { background:#fee2e2; color:#7f1d1d; border-left:4px solid var(--red); }
.flash.info  { background:#dbeafe; color:#1e40af; border-left:4px solid #3b82f6; }
.flash.warn  { background:#fef3c7; color:#92400e; border-left:4px solid var(--yellow); }

/* Cards & tables */
.card { background:#fff; border:1px solid var(--gray-200); border-radius:6px;
  overflow:hidden; margin-bottom:24px; }
.card-head { padding:14px 18px; border-bottom:1px solid var(--gray-100);
  font-weight:700; color:var(--navy); font-size:13px; text-transform:uppercase;
  letter-spacing:1px; }
.card-body { padding:20px; }

table { width:100%; border-collapse:collapse; background:#fff; }
th { text-align:left; padding:12px 14px; font-size:11px; text-transform:uppercase;
  letter-spacing:1.2px; color:var(--gray-500); background:var(--gray-50);
  border-bottom:1px solid var(--gray-200); }
td { padding:14px; border-bottom:1px solid var(--gray-100); vertical-align:top; }
tr:hover td { background:var(--gray-50); }
td small { color:var(--gray-500); }

/* Stats grid */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:18px;
  margin-bottom:28px; }
.stat { background:#fff; border:1px solid var(--gray-200); border-radius:6px;
  padding:22px; }
.stat .k { font-size:11px; color:var(--gray-500); text-transform:uppercase;
  letter-spacing:1.2px; }
.stat .v { font-size:28px; font-weight:800; color:var(--navy); margin-top:6px; }
.stat .sub { font-size:11px; color:var(--orange); margin-top:4px; }

/* Buttons */
.btn { display:inline-block; padding:8px 16px; border-radius:5px; border:0;
  font:inherit; font-weight:700; font-size:12px; letter-spacing:.5px;
  text-transform:uppercase; cursor:pointer; text-decoration:none; }
.btn:hover { text-decoration:none; }
.btn-primary { background:var(--orange); color:#fff; }
.btn-primary:hover { background:var(--orange-d); }
.btn-navy { background:var(--navy); color:#fff; }
.btn-navy:hover { background:var(--navy-d); }
.btn-ghost { background:#fff; border:1.5px solid var(--gray-200);
  color:var(--gray-700); }
.btn-ghost:hover { border-color:var(--orange); color:var(--orange); }
.btn-danger { background:var(--red); color:#fff; }
.btn-danger:hover { background:#991b1b; }
.btn-sm { padding:5px 10px; font-size:11px; }

/* Status pills */
.pill { display:inline-block; padding:3px 9px; font-size:10px; font-weight:700;
  letter-spacing:1px; text-transform:uppercase; border-radius:20px; }
.pill.pending  { background:#fef3c7; color:#92400e; }
.pill.approved { background:#dcfce7; color:#065f46; }
.pill.rejected { background:#fee2e2; color:#7f1d1d; }
.pill.new      { background:#dbeafe; color:#1e40af; }
.pill.read     { background:var(--gray-100); color:var(--gray-700); }
.pill.replied  { background:#dcfce7; color:#065f46; }
.pill.archived { background:var(--gray-100); color:var(--gray-500); }

/* Forms */
.form-row { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:14px; }
.form-group { margin-bottom:14px; }
.form-group.full { grid-column:1 / -1; }
label { display:block; font-weight:700; font-size:11px; color:var(--navy);
  text-transform:uppercase; letter-spacing:.8px; margin-bottom:6px; }
input[type=text], input[type=email], input[type=password], input[type=date],
input[type=number], select, textarea {
  width:100%; padding:10px 12px; border:1.5px solid var(--gray-200);
  border-radius:5px; font:inherit; font-size:13px; background:#fff; }
input:focus, select:focus, textarea:focus {
  outline:none; border-color:var(--orange);
  box-shadow:0 0 0 3px rgba(243,111,33,.15); }
textarea { min-height:110px; resize:vertical; }

.actions { display:flex; gap:6px; align-items:center; }
.actions form { display:inline; }

/* Login page */
.login-wrap { min-height:100vh; display:grid; place-items:center;
  background:linear-gradient(135deg,var(--navy),var(--navy-d)); padding:20px; }
.login-card { background:#fff; padding:40px; border-radius:8px; width:100%;
  max-width:400px; box-shadow:0 20px 50px rgba(0,0,0,.3); }
.login-card h1 { color:var(--navy); font-size:22px; margin-bottom:6px; }
.login-card p.sub { color:var(--gray-500); font-size:13px; margin-bottom:24px; }

@media (max-width:800px) {
  .admin-wrap { flex-direction:column; }
  .sidebar { width:100%; }
  .sidebar nav { display:flex; flex-wrap:wrap; padding:8px; }
  .sidebar nav a { padding:8px 12px; border-left:0; border-bottom:2px solid transparent; }
  .sidebar nav a.active { border-left:0; border-bottom-color:var(--orange); }
  .main { padding:20px; }
  .stats { grid-template-columns:1fr 1fr; }
  .form-row { grid-template-columns:1fr; }
  table { font-size:12px; }
  th, td { padding:8px; }
}
"""

# Sidebar navigation items: (path, label, key)
NAV = [
    ("/admin",             "Dashboard",      "dashboard"),
    ("/admin/volunteers",  "Volunteers",     "volunteers"),
    ("/admin/contacts",    "Contacts",       "contacts"),
    ("/admin/partners",    "Partners",       "partners"),
    ("/admin/donations",   "Donations",      "donations"),
    ("/admin/subscribers", "Subscribers",    "subscribers"),
    ("/admin/blog",        "Blog Posts",     "blog"),
    ("/admin/events",      "Events",         "events"),
    ("/admin/projects",    "Projects",       "projects"),
    ("/admin/inbox",       "Inbox (replies)","inbox"),
    ("/admin/payments",    "Payments (Monime)", "payments"),
    ("/admin/email",       "Email Settings", "email"),
    ("/admin/password",    "Change Password","password"),
]


def render_layout(title, active, content, admin, csrf, flash=None):
    """Wrap page content with the admin layout."""
    nav_html = "".join(
        f'<a href="{esc(path)}" class="{"active" if key==active else ""}">{esc(label)}</a>'
        for path, label, key in NAV
    )
    flash_html = ""
    if flash:
        kind, msg = flash
        flash_html = f'<div class="flash {esc(kind)}">{esc(msg)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — CBN Admin</title>
<style>{BASE_CSS}</style>
</head><body>
<div class="admin-wrap">
  <aside class="sidebar">
    <div class="brand"><strong>CBN-SL Admin</strong><span>Sierra Leone</span></div>
    <nav>{nav_html}</nav>
    <div class="foot">
      Logged in as <strong style="color:#fff;">{esc(admin['username'])}</strong><br>
      <form method="POST" action="/admin/logout">
        <input type="hidden" name="csrf_token" value="{esc(csrf)}">
        <button type="submit">Log out →</button>
      </form>
    </div>
  </aside>
  <main class="main">
    <div class="page-head"><h1>{esc(title)}</h1></div>
    {flash_html}
    {content}
  </main>
</div>
</body></html>"""


# ------------------------------------------------------------------
# LOGIN PAGE
# ------------------------------------------------------------------
def render_login(csrf_token, error=None, rate_limited=False, username=""):
    err_html = ""
    if rate_limited:
        err_html = '<div class="flash err">Too many failed attempts. Please wait 15 minutes.</div>'
    elif error:
        err_html = f'<div class="flash err">{esc(error)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Login — CBN</title><style>{BASE_CSS}</style>
</head><body><div class="login-wrap"><div class="login-card">
<h1>CBN-SL Admin</h1><p class="sub">Sign in to manage the website.</p>
{err_html}
<form method="POST" action="/admin/login" autocomplete="off">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <div class="form-group">
    <label for="u">Username</label>
    <input type="text" id="u" name="username" required autofocus
           value="{esc(username)}" maxlength="50">
  </div>
  <div class="form-group">
    <label for="p">Password</label>
    <input type="password" id="p" name="password" required maxlength="200">
  </div>
  <button type="submit" class="btn btn-primary" style="width:100%;padding:12px;">
    Sign In
  </button>
</form>
<p style="text-align:center;margin-top:20px;font-size:11px;color:var(--gray-500);">
  ← <a href="/" style="color:var(--gray-500);">Back to public site</a>
</p>
</div></div></body></html>"""


# ------------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------------
def render_dashboard(admin, csrf, stats, recent_volunteers, flash=None):
    stat_parts = []
    for k, v, sub in stats:
        sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
        stat_parts.append(
            f'<div class="stat"><div class="k">{esc(k)}</div>'
            f'<div class="v">{esc(v)}</div>{sub_html}</div>'
        )
    stat_cards = "".join(stat_parts)

    rows = ""
    for v in recent_volunteers:
        rows += f"""<tr>
          <td><strong>{esc(v['first_name'])} {esc(v['last_name'])}</strong><br>
              <small>{esc(v['email'])}</small></td>
          <td>{esc(v['role'] or '—')}</td>
          <td><span class="pill {esc(v['status'])}">{esc(v['status'])}</span></td>
          <td><small>{esc(v['submitted_at'][:16])}</small></td>
        </tr>"""

    body = f"""
    <div class="stats">{stat_cards}</div>
    <div class="card">
      <div class="card-head">Recent Volunteer Applications</div>
      <table>
        <thead><tr><th>Applicant</th><th>Role</th><th>Status</th><th>When</th></tr></thead>
        <tbody>{rows or '<tr><td colspan="4" style="text-align:center;color:var(--gray-500);padding:24px;">No applications yet.</td></tr>'}</tbody>
      </table>
    </div>
    <p><a href="/admin/volunteers" class="btn btn-ghost">View all volunteers →</a></p>
    """
    return render_layout("Dashboard", "dashboard", body, admin, csrf, flash)


# ------------------------------------------------------------------
# VOLUNTEERS
# ------------------------------------------------------------------
def render_volunteers(admin, csrf, rows, flash=None, emails=None, mail_mode="", mail_live=False,
                      sender="", replies=None):
    emails  = emails or {}
    replies = replies or {}

    def _reply_badge(v):
        n = replies.get(v["id"], 0)
        if not n:
            return ""
        return (f'<a href="/admin/inbox?volunteer={v["id"]}" class="pill new" '
                f'style="text-decoration:none;margin-left:6px;" title="Unread replies from this applicant">'
                f'✉ {n} repl{"y" if n == 1 else "ies"}</a>')

    def _email_cell(v):
        """Delivery state of the most recent decision email for this applicant."""
        e = emails.get(v["id"])
        if not e:
            if v["status"] in ("approved", "rejected"):
                return '<small style="color:var(--gray-500);">No email sent yet</small>'
            return '<small style="color:var(--gray-500);">—</small>'
        pill = {"sent": "approved", "console": "read", "queued": "pending", "failed": "rejected"}.get(e["status"], "read")
        label = {"sent": "Sent", "console": "Printed to console", "queued": "Sending…", "failed": "Failed"}.get(e["status"], e["status"])
        when = (e["sent_at"] or e["created_at"] or "")[:16]
        detail = f'<br><small style="color:var(--red);">{esc(e["detail"])}</small>' if e["status"] == "failed" and e["detail"] else ""
        kind = (e["kind"] or "").replace("volunteer_", "")
        return (f'<span class="pill {pill}">{esc(label)}</span><br>'
                f'<small>{esc(kind)} · {esc(when)}</small>{detail}')

    def _notify_form(v):
        if v["status"] not in ("approved", "rejected"):
            return ""
        has_prev = v["id"] in emails
        return (f'<form method="POST" action="/admin/volunteer/{v["id"]}/notify" '
                f'style="margin-top:6px;">'
                f'<input type="hidden" name="csrf_token" value="{esc(csrf)}">'
                f'<button type="submit" class="btn btn-navy btn-sm" '
                f'title="Email the {v["status"]} decision and office visit details to {esc(v["email"])}">'
                f'✉ {"Resend" if has_prev else "Send"} email</button></form>')

    mode_banner = (
        f'<div class="flash {"ok" if mail_live else "warn"}" style="display:flex;gap:10px;align-items:flex-start;">'
        f'<span style="font-size:16px;">✉</span>'
        f'<div><strong>Decision emails</strong> are sent from <strong>{esc(sender)}</strong> to the address '
        f'each applicant entered on the volunteer form. {esc(mail_mode)}<br>'
        f'<small>New applications: the applicant gets a receipt and {esc(sender)} gets an alert. '
        f'Approving or rejecting: the applicant is emailed the decision plus an invitation to attend the office '
        f'within one week at 13:00 for final verification, and a copy goes to {esc(sender)}. '
        f'<a href="/admin/email">Email Settings →</a></small></div></div>'
    )

    body = mode_banner + _render_submissions_table(
        rows, csrf,
        columns=["Applicant", "Role", "Availability", "Status", "Decision Email", "Submitted", "Actions"],
        row_fn=lambda v: f"""
          <td><strong>{esc(v['first_name'])} {esc(v['last_name'])}</strong>{_reply_badge(v)}<br>
              <small><a href="mailto:{esc(v['email'])}">{esc(v['email'])}</a>{" · "+esc(v['phone']) if v['phone'] else ""}</small><br>
              {f"<small><em>{esc(v['message'])}</em></small>" if v['message'] else ""}</td>
          <td>{esc(v['role'] or '—')}</td>
          <td>{esc(v['availability'] or '—')}</td>
          <td><span class="pill {esc(v['status'])}">{esc(v['status'])}</span></td>
          <td>{_email_cell(v)}</td>
          <td><small>{esc(v['submitted_at'][:16])}<br>{esc(v['ip_address'] or '')}</small></td>
          <td>{_status_actions('volunteer', v['id'], csrf, ['approved','rejected','pending'])}{_notify_form(v)}</td>
        """
    )
    return render_layout("Volunteer Applications", "volunteers", body, admin, csrf, flash)


def render_contacts(admin, csrf, rows, flash=None):
    body = _render_submissions_table(
        rows, csrf,
        columns=["From", "Subject", "Message", "Status", "Submitted", "Actions"],
        row_fn=lambda c: f"""
          <td><strong>{esc(c['name'])}</strong><br><small>{esc(c['email'])}</small></td>
          <td>{esc(c['subject'] or '—')}</td>
          <td><small>{esc(c['message'][:180])}{"…" if len(c['message'])>180 else ""}</small></td>
          <td><span class="pill {esc(c['status'])}">{esc(c['status'])}</span></td>
          <td><small>{esc(c['submitted_at'][:16])}</small></td>
          <td>{_status_actions('contact', c['id'], csrf, ['read','replied','archived','new'])}</td>
        """
    )
    return render_layout("Contact Messages", "contacts", body, admin, csrf, flash)


def render_partners(admin, csrf, rows, flash=None):
    body = _render_submissions_table(
        rows, csrf,
        columns=["Organisation", "Contact", "Type", "Message", "Submitted", "Actions"],
        row_fn=lambda p: f"""
          <td><strong>{esc(p['organisation'])}</strong></td>
          <td>{esc(p['contact_name'])}<br><small>{esc(p['email'])}</small></td>
          <td>{esc(p['partnership_type'] or '—')}</td>
          <td><small>{esc((p['message'] or '')[:180])}</small></td>
          <td><small>{esc(p['submitted_at'][:16])}</small></td>
          <td>{_delete_form('partner', p['id'], csrf)}</td>
        """
    )
    return render_layout("Partnership Enquiries", "partners", body, admin, csrf, flash)


def render_donations(admin, csrf, rows, flash=None):
    """Admin donations listing with totals."""
    total_completed = sum(r["amount_sll"] for r in rows if r["status"] == "completed")
    total_pending   = sum(r["amount_sll"] for r in rows if r["status"] == "pending")
    count_complete  = sum(1 for r in rows if r["status"] == "completed")

    summary = f"""
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px;">
      <div class="stat">
        <div class="k">Total Raised (SLL)</div>
        <div class="v">Le {total_completed:,}</div>
        <div class="sub">{count_complete} completed</div>
      </div>
      <div class="stat">
        <div class="k">Pending</div>
        <div class="v">Le {total_pending:,}</div>
      </div>
      <div class="stat">
        <div class="k">All Donations</div>
        <div class="v">{len(rows)}</div>
      </div>
    </div>"""

    def _gw(d):
        keys = d.keys()
        gmode = d["gateway_mode"] if "gateway_mode" in keys else None
        gstat = d["gateway_status"] if "gateway_status" in keys else None
        sid   = d["checkout_session_id"] if "checkout_session_id" in keys else None
        badge = {"live": "approved", "test": "new", "simulation": "read"}.get(gmode or "", "read")
        parts = [f'<span class="pill {badge}">{esc(gmode or "—")}</span>']
        if gstat:
            parts.append(f'<br><small>Monime: {esc(gstat)}</small>')
        if sid:
            parts.append(f'<br><small style="font-family:monospace;color:var(--gray-500);">{esc(str(sid)[:22])}</small>')
        return "".join(parts)

    def _verify_btn(d):
        if d["status"] == "completed":
            return ""
        return (f'<form method="POST" action="/admin/donation/{d["id"]}/verify">'
                f'<input type="hidden" name="csrf_token" value="{esc(csrf)}">'
                f'<button type="submit" class="btn btn-navy btn-sm" title="Ask Monime for the current status">⟳ Verify</button></form>')

    body = summary + _render_submissions_table(
        rows, csrf,
        columns=["Donor", "Amount", "Gateway", "Project", "Status", "Date", "Actions"],
        row_fn=lambda d: f"""
          <td><strong>{'Anonymous' if d['anonymous'] else esc(str(d['first_name'] or ''))+' '+esc(str(d['last_name'] or ''))}</strong><br>
              <small>{esc(d['email'] or '')}</small><br>
              <small>{esc(d['phone'] or '')}</small></td>
          <td><strong>Le {d['amount_sll']:,}</strong><br>
              <small>SLE {d['amount_sll']/1000:,.2f} · {esc(d['frequency'] or 'once')}</small><br>
              <small>{esc((d['payment_method'] or '—').replace('_',' '))}
                {(' · ' + esc(d['momo_operator'])) if ('momo_operator' in d.keys() and d['momo_operator']) else ''}
                {(' · card: ' + esc(d['card_holder'])) if ('card_holder' in d.keys() and d['card_holder']) else ''}</small></td>
          <td>{_gw(d)}</td>
          <td><small>{esc(d['project_designation'] or 'General')}</small></td>
          <td><span class="pill {'approved' if d['status']=='completed' else ('pending' if d['status']=='pending' else 'rejected')}">
              {esc(d['status'])}</span>
              {f'<br><small style="color:var(--red);">{esc(d["failure_reason"])}</small>' if ('failure_reason' in d.keys() and d['failure_reason']) else ''}</td>
          <td><small>{esc(d['submitted_at'][:16])}</small><br>
              <small style="font-family:monospace;color:var(--gray-500);">{esc(d['reference'])}</small></td>
          <td><div class="actions" style="flex-wrap:wrap;">{_verify_btn(d)}{_delete_form('donation', d['id'], csrf)}</div></td>
        """
    )
    return render_layout("Donations", "donations", body, admin, csrf, flash)


def render_subscribers(admin, csrf, rows, flash=None):
    body = _render_submissions_table(
        rows, csrf,
        columns=["Email", "Subscribed", "Status", "Actions"],
        row_fn=lambda s: f"""
          <td><strong>{esc(s['email'])}</strong></td>
          <td><small>{esc(s['subscribed_at'][:16])}</small></td>
          <td><span class="pill {'approved' if s['active'] else 'archived'}">
              {'active' if s['active'] else 'unsubscribed'}</span></td>
          <td>{_delete_form('subscriber', s['id'], csrf)}</td>
        """
    )
    return render_layout("Newsletter Subscribers", "subscribers", body, admin, csrf, flash)


def _render_submissions_table(rows, csrf, columns, row_fn):
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body_rows = "".join(f"<tr>{row_fn(r)}</tr>" for r in rows)
    empty = f'<tr><td colspan="{len(columns)}" style="text-align:center;color:var(--gray-500);padding:32px;">No records yet.</td></tr>'
    return f"""<div class="card"><table>
      <thead><tr>{head}</tr></thead>
      <tbody>{body_rows or empty}</tbody>
    </table></div>"""


_STATUS_LABELS = {
    "approved": ("✓ Approve", "btn-primary", "Approve and email the applicant"),
    "rejected": ("✗ Reject",  "btn-ghost",   "Reject and email the applicant"),
    "pending":  ("↺ Pending", "btn-ghost",   "Move back to pending (no email)"),
}


def _status_actions(kind, rec_id, csrf, statuses):
    """Render status-update buttons + a delete button."""
    parts = []
    for s in statuses:
        label, cls, title = _STATUS_LABELS.get(s, (s, "btn-ghost", ""))
        parts.append(
            f'<form method="POST" action="/admin/{kind}/{rec_id}/status">'
            f'<input type="hidden" name="csrf_token" value="{esc(csrf)}">'
            f'<input type="hidden" name="status" value="{esc(s)}">'
            f'<button type="submit" class="btn {cls} btn-sm" title="{esc(title)}">{esc(label)}</button>'
            f'</form>'
        )
    parts.append(_delete_form(kind, rec_id, csrf))
    return f'<div class="actions" style="flex-wrap:wrap;">{"".join(parts)}</div>'


def _delete_form(kind, rec_id, csrf):
    return (
        f'<form method="POST" action="/admin/{kind}/{rec_id}/delete" '
        f'onsubmit="return confirm(\'Delete this record?\');">'
        f'<input type="hidden" name="csrf_token" value="{esc(csrf)}">'
        f'<button type="submit" class="btn btn-danger btn-sm">Delete</button>'
        f'</form>'
    )


# ------------------------------------------------------------------
# BLOG / EVENTS / PROJECTS — CRUD
# ------------------------------------------------------------------
def render_blog(admin, csrf, rows, editing=None, flash=None):
    e = editing or {}
    is_edit = bool(editing)
    action  = f"/admin/blog/{e['id']}/edit" if is_edit else "/admin/blog/create"

    def _blog_row(r, is_first):
        pub_at = r["published_at"] if "published_at" in r.keys() else None
        when = (f"Published {esc(pub_at[:16])}" if (r["published"] and pub_at)
                else "Not published")
        featured = ('<span class="pill" style="background:#fff2e7;color:#c2410c;margin-left:6px;">'
                    'Featured on site</span>' if (is_first and r["published"]) else "")
        view = (f'<a href="/blog/{esc(r["slug"])}" target="_blank" rel="noopener" '
                f'class="btn btn-ghost btn-sm">{"View" if r["published"] else "Preview"}</a>')
        return f"""<tr>
          <td><strong>{esc(r['title'])}</strong>{featured}<br>
              <small>/blog/{esc(r['slug'])} · {esc(r['category'] or 'uncategorised')}</small></td>
          <td><span class="pill {'approved' if r['published'] else 'archived'}">
              {'published' if r['published'] else 'draft'}</span></td>
          <td><small>{when}<br>Updated {esc(r['updated_at'][:16])}</small></td>
          <td><div class="actions">
            {view}
            <a href="/admin/blog?edit={r['id']}" class="btn btn-ghost btn-sm">Edit</a>
            {_delete_form('blog', r['id'], csrf)}
          </div></td>
        </tr>"""

    first_pub_id = next((r["id"] for r in rows if r["published"]), None)
    list_rows = "".join(_blog_row(r, r["id"] == first_pub_id) for r in rows)

    body = f"""
    <div class="card">
      <div class="card-head">{'Edit Post' if is_edit else 'Create New Post'}</div>
      <div class="card-body">
        <form method="POST" action="{esc(action)}">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <div class="form-row">
            <div class="form-group">
              <label>Title</label>
              <input type="text" name="title" required maxlength="200"
                     value="{esc(e.get('title',''))}">
            </div>
            <div class="form-group">
              <label>Category</label>
              <select name="category">
                {_options(['field','policy','voices','research'], e.get('category'))}
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Author</label>
              <input type="text" name="author" maxlength="100"
                     value="{esc(e.get('author',''))}">
            </div>
            <div class="form-group">
              <label>Image URL</label>
              <input type="text" name="image_url" maxlength="500"
                     value="{esc(e.get('image_url',''))}">
            </div>
          </div>
          <div class="form-group">
            <label>Excerpt (short summary)</label>
            <textarea name="excerpt" maxlength="500" style="min-height:70px;">{esc(e.get('excerpt',''))}</textarea>
          </div>
          <div class="form-group">
            <label>Content
              <span style="text-transform:none;font-weight:400;font-size:11px;
                           color:var(--gray-500);letter-spacing:0;">
                — plain text is fine (blank line = new paragraph); HTML such as
                &lt;h2&gt;, &lt;p&gt;, &lt;ul&gt;, &lt;blockquote&gt; is also allowed
              </span>
            </label>
            <textarea name="content" style="min-height:220px;">{esc(e.get('content',''))}</textarea>
          </div>
          <div class="form-group">
            <label style="display:inline-flex;align-items:center;gap:8px;text-transform:none;font-weight:400;font-size:13px;color:var(--gray-700);">
              <input type="checkbox" name="published" value="1" style="width:auto;"
                     {'checked' if e.get('published') else ''}>
              Publish immediately
            </label>
          </div>
          <button type="submit" class="btn btn-primary">
            {'Save Changes' if is_edit else 'Create Post'}
          </button>
          {f'<a href="/admin/blog" class="btn btn-ghost">Cancel</a>' if is_edit else ''}
        </form>
      </div>
    </div>

    <div class="card">
      <div class="card-head">All Blog Posts ({len(rows)})</div>
      <table>
        <thead><tr><th>Title</th><th>Status</th><th>Published / Updated</th><th>Actions</th></tr></thead>
        <tbody>{list_rows or '<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--gray-500);">No posts yet.</td></tr>'}</tbody>
      </table>
    </div>
    """
    return render_layout("Blog Posts", "blog", body, admin, csrf, flash)


def render_events(admin, csrf, rows, editing=None, flash=None):
    e = editing or {}
    is_edit = bool(editing)
    action  = f"/admin/events/{e['id']}/edit" if is_edit else "/admin/events/create"

    list_rows = "".join(
        f"""<tr>
          <td><strong>{esc(r['title'])}</strong></td>
          <td>{esc(r['event_date'])} {esc(r['event_time'] or '')}</td>
          <td>{esc(r['location'] or '—')}</td>
          <td><div class="actions">
            <a href="/admin/events?edit={r['id']}" class="btn btn-ghost btn-sm">Edit</a>
            {_delete_form('event', r['id'], csrf)}
          </div></td>
        </tr>""" for r in rows
    )

    body = f"""
    <div class="card">
      <div class="card-head">{'Edit Event' if is_edit else 'Add New Event'}</div>
      <div class="card-body">
        <form method="POST" action="{esc(action)}">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <div class="form-group">
            <label>Title</label>
            <input type="text" name="title" required maxlength="200"
                   value="{esc(e.get('title',''))}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Date</label>
              <input type="date" name="event_date" required
                     value="{esc(e.get('event_date',''))}">
            </div>
            <div class="form-group">
              <label>Time</label>
              <input type="text" name="event_time" placeholder="e.g. 18:00"
                     maxlength="20" value="{esc(e.get('event_time',''))}">
            </div>
          </div>
          <div class="form-group">
            <label>Location</label>
            <input type="text" name="location" maxlength="200"
                   value="{esc(e.get('location',''))}">
          </div>
          <div class="form-group">
            <label>Description</label>
            <textarea name="description">{esc(e.get('description',''))}</textarea>
          </div>
          <button type="submit" class="btn btn-primary">
            {'Save Changes' if is_edit else 'Create Event'}
          </button>
          {f'<a href="/admin/events" class="btn btn-ghost">Cancel</a>' if is_edit else ''}
        </form>
      </div>
    </div>

    <div class="card">
      <div class="card-head">All Events ({len(rows)})</div>
      <table>
        <thead><tr><th>Title</th><th>When</th><th>Location</th><th>Actions</th></tr></thead>
        <tbody>{list_rows or '<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--gray-500);">No events yet.</td></tr>'}</tbody>
      </table>
    </div>
    """
    return render_layout("Events", "events", body, admin, csrf, flash)


def render_projects(admin, csrf, rows, editing=None, flash=None):
    e = editing or {}
    is_edit = bool(editing)
    action  = f"/admin/projects/{e['id']}/edit" if is_edit else "/admin/projects/create"

    list_rows = "".join(
        f"""<tr>
          <td><strong>{esc(r['title'])}</strong><br>
              <small>{esc(r['district'] or '')} · {esc(r['category'] or '')}</small></td>
          <td><span class="pill {'approved' if r['status']=='current' else 'archived'}">
              {esc(r['status'])}</span></td>
          <td>{esc(r['funded_percent'])}%</td>
          <td>{esc(r['start_year'] or '')}–{esc(r['end_year'] or '')}</td>
          <td><div class="actions">
            <a href="/admin/projects?edit={r['id']}" class="btn btn-ghost btn-sm">Edit</a>
            {_delete_form('project', r['id'], csrf)}
          </div></td>
        </tr>""" for r in rows
    )

    body = f"""
    <div class="card">
      <div class="card-head">{'Edit Project' if is_edit else 'Add New Project'}</div>
      <div class="card-body">
        <form method="POST" action="{esc(action)}">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <div class="form-group">
            <label>Title</label>
            <input type="text" name="title" required maxlength="200"
                   value="{esc(e.get('title',''))}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Category</label>
              <select name="category">
                {_options(['education','health','livelihoods','youth'], e.get('category'))}
              </select>
            </div>
            <div class="form-group">
              <label>District</label>
              <input type="text" name="district" maxlength="100"
                     value="{esc(e.get('district',''))}">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Status</label>
              <select name="status">
                {_options(['current','past'], e.get('status'))}
              </select>
            </div>
            <div class="form-group">
              <label>Funded %</label>
              <input type="number" name="funded_percent" min="0" max="100"
                     value="{esc(e.get('funded_percent',0))}">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Start Year</label>
              <input type="number" name="start_year" min="2000" max="2100"
                     value="{esc(e.get('start_year',''))}">
            </div>
            <div class="form-group">
              <label>End Year</label>
              <input type="number" name="end_year" min="2000" max="2100"
                     value="{esc(e.get('end_year',''))}">
            </div>
          </div>
          <div class="form-group">
            <label>Image URL</label>
            <input type="text" name="image_url" maxlength="500"
                   value="{esc(e.get('image_url',''))}">
          </div>
          <div class="form-group">
            <label>Description (short)</label>
            <textarea name="description" style="min-height:70px;">{esc(e.get('description',''))}</textarea>
          </div>
          <div class="form-group">
            <label>Banner Image URL (wide hero image)</label>
            <input type="text" name="banner_url" maxlength="500"
                   value="{esc(e.get('banner_url',''))}">
          </div>
          <div class="form-group">
            <label>Author / Written by</label>
            <input type="text" name="author" maxlength="100"
                   value="{esc(e.get('author',''))}">
          </div>
          <div class="form-group">
            <label>Full Article Content
              <span style="text-transform:none;font-weight:400;font-size:11px;
                           color:var(--gray-500);letter-spacing:0;">
                — HTML is allowed (h2, h3, p, ul, li, blockquote)
              </span>
            </label>
            <textarea name="article_content" style="min-height:280px;font-family:monospace;font-size:12px;">{esc(e.get('article_content',''))}</textarea>
          </div>
          <button type="submit" class="btn btn-primary">
            {'Save Changes' if is_edit else 'Create Project'}
          </button>
          {f'<a href="/admin/projects" class="btn btn-ghost">Cancel</a>' if is_edit else ''}
        </form>
      </div>
    </div>

    <div class="card">
      <div class="card-head">All Projects ({len(rows)})</div>
      <table>
        <thead><tr><th>Title</th><th>Status</th><th>Funded</th><th>Years</th><th>Actions</th></tr></thead>
        <tbody>{list_rows or '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--gray-500);">No projects yet.</td></tr>'}</tbody>
      </table>
    </div>
    """
    return render_layout("Projects", "projects", body, admin, csrf, flash)


def _options(values, selected):
    """Build <option> tags with the given value selected."""
    return "".join(
        f'<option value="{esc(v)}" {"selected" if str(v)==str(selected) else ""}>{esc(v.title())}</option>'
        for v in values
    )


# ------------------------------------------------------------------
# PAYMENTS (Monime) — settings + gateway log
# ------------------------------------------------------------------
def render_payments(admin, csrf, cfg, gw_mode, gw_msg, recent, events, public_base="", webhook=None, flash=None):
    kind = {"live": "ok", "test": "info", "simulation": "warn", "disabled": "warn"}.get(gw_mode, "info")
    icon = {"live": "💳", "test": "🧪", "simulation": "🎭", "disabled": "⏸"}.get(gw_mode, "•")
    webhook_url = f"{public_base}/api/monime/webhook"
    is_https = public_base.startswith("https://")

    # ── Webhook status card ──
    if gw_mode not in ("test", "live"):
        wh_state = ('<div class="flash warn">Connect Monime first (space id + token), then the webhook can be registered.</div>')
    elif isinstance(webhook, dict) and webhook.get("error"):
        wh_state = f'<div class="flash err">Could not read webhooks from Monime: {esc(webhook["error"])}</div>'
    elif webhook:
        wh_state = (f'<div class="flash ok"><strong>✅ Registered with Monime</strong> · id <code>{esc(webhook.get("id",""))}</code> · '
                    f'{"enabled" if webhook.get("enabled", True) else "<span style=color:var(--red)>DISABLED</span>"} · '
                    f'events: {esc(", ".join(webhook.get("events") or []))}<br>'
                    f'<small>URL: <code>{esc(webhook.get("url",""))}</code> · verification: '
                    f'{esc(((webhook.get("verificationMethod") or {}).get("type")) or "?")}'
                    f'{" · secret saved locally ✓" if cfg["has_webhook_secret"] else " · <strong style=color:var(--red)>no secret saved locally — click Register again to re-sync</strong>"}</small></div>')
    else:
        wh_state = ('<div class="flash warn"><strong>Not registered yet.</strong> Payments still work — the server confirms each donation '
                    'by asking Monime when the donor returns — but a webhook makes confirmation instant and catches donors who '
                    'close the browser before returning.</div>')

    https_note = "" if is_https else (
        f'<p style="color:var(--red);font-size:13px;margin:8px 0 0;">Monime only delivers webhooks to <strong>https://</strong> URLs. '
        f'Your current public URL is <code>{esc(public_base)}</code>. While testing locally, run '
        f'<code>ngrok http 8000</code> (or a Cloudflare tunnel), paste the https address into <em>Public site URL</em> below, save, '
        f'then click Register.</p>')

    webhook_card = f"""
    <div class="card">
      <div class="card-head">Webhook — instant payment confirmation</div>
      <div class="card-body">
        {wh_state}
        <p style="font-size:13px;color:var(--gray-700);margin:0 0 6px;">Endpoint this server listens on: <code>{esc(webhook_url)}</code></p>
        {https_note}
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;">
          <form method="POST" action="/admin/payments/webhook/register">
            <input type="hidden" name="csrf_token" value="{esc(csrf)}">
            <button type="submit" class="btn btn-primary" {'disabled' if (gw_mode not in ('test','live') or not is_https) else ''}>
              {'⟳ Re-register / re-sync webhook' if webhook and not webhook.get('error') else '＋ Register webhook with Monime'}</button>
          </form>
          {f'''<form method="POST" action="/admin/payments/webhook/delete" onsubmit="return confirm('Remove the webhook from Monime?');">
            <input type="hidden" name="csrf_token" value="{esc(csrf)}">
            <button type="submit" class="btn btn-danger">Remove webhook</button></form>''' if webhook and not webhook.get('error') else ''}
        </div>
        <small style="display:block;margin-top:10px;color:var(--gray-500);">Registering generates a strong HS256 secret, creates the webhook in your Monime space for
        <code>checkout_session.completed / cancelled / expired</code>, and stores the secret in <code>monime.env</code> so every delivery is signature-checked.
        Even a verified webhook is treated only as a hint: the server re-fetches the session from Monime before marking a donation completed.</small>
      </div>
    </div>"""

    setup = f"""
    <div class="card" style="border-left:4px solid var(--orange);">
      <div class="card-head">How to connect Monime (test first, then live)</div>
      <div class="card-body" style="font-size:13px;color:var(--gray-700);line-height:1.7;">
        <ol style="margin:0 0 0 18px;">
          <li>Create a business account at <a href="https://monime.io" target="_blank" rel="noopener">monime.io</a>
              and open the dashboard. Every account has a <strong>Test</strong> space and a <strong>Live</strong> space.</li>
          <li>In the <strong>Test</strong> space copy the <strong>Space ID</strong> (starts with <code>spc-</code>) and create an
              <strong>Access Token</strong>. Paste both below, keep Mode = <em>test</em>, click <strong>Save</strong>, then
              <strong>Test connection</strong>.</li>
          <li>Make a donation on <a href="/donate.html" target="_blank">the donate page</a>: you'll land on Monime's real
              hosted checkout. Use Monime's test wallets to simulate a successful Orange Money payment — no money moves.</li>
          <li>(Recommended) In the dashboard add a <strong>Webhook</strong> pointing at
              <code>{esc(webhook_url)}</code> for the <code>checkout_session.completed</code> event, choose
              <strong>HS256</strong>, and paste its secret below. Without it the site still confirms payments by
              asking Monime directly when the donor returns — the webhook just makes it instant.</li>
          <li>Go live: switch to the <strong>Live</strong> space id + token, set Mode = <em>live</em>, and make sure the
              Public site URL is <code>https://…</code>.</li>
        </ol>
        <p style="margin:12px 0 0;color:var(--gray-500);">
          Amounts on the site are shown in old Leones (Le 250,000). Monime is charged in the new Leone:
          <strong>Le 250,000 = SLE 250.00</strong>, sent to the API as <code>25000</code> minor units.
        </p>
      </div>
    </div>"""

    form = f"""
    <div class="card">
      <div class="card-head">Gateway settings</div>
      <div class="card-body">
        <form method="POST" action="/admin/payments" autocomplete="off">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <div class="form-group">
            <label style="display:inline-flex;align-items:center;gap:8px;text-transform:none;font-size:13px;">
              <input type="checkbox" name="enabled" value="1" style="width:auto;" {'checked' if cfg['enabled'] else ''}>
              Enable online payments on the donate page
            </label>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Monime Space ID</label>
              <input type="text" name="space_id" maxlength="64" placeholder="spc-…" value="{esc(cfg['space_id'])}">
            </div>
            <div class="form-group">
              <label>Mode</label>
              <select name="mode">
                <option value="test" {'selected' if cfg['mode']!='live' else ''}>test — no real money</option>
                <option value="live" {'selected' if cfg['mode']=='live' else ''}>live — real donations</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>Access token</label>
            <input type="password" name="access_token" maxlength="512" autocomplete="new-password"
                   placeholder="{'saved: ' + esc(cfg['token_mask']) + ' — leave blank to keep' if cfg['has_token'] else 'paste the token from the Monime dashboard'}">
            {f'<label style="display:inline-flex;align-items:center;gap:8px;text-transform:none;font-size:12px;margin-top:6px;color:var(--red);"><input type="checkbox" name="clear_token" value="1" style="width:auto;"> Remove saved token</label>' if cfg['has_token'] else ''}
          </div>
          <div class="form-group">
            <label>Webhook secret (HS256) — optional</label>
            <input type="password" name="webhook_secret" maxlength="256" autocomplete="new-password"
                   placeholder="{'saved — leave blank to keep' if cfg['has_webhook_secret'] else 'from the webhook you create in Monime'}">
            <small style="color:var(--gray-500);">Webhook URL to register: <code>{esc(webhook_url)}</code></small>
            {f'<br><label style="display:inline-flex;align-items:center;gap:8px;text-transform:none;font-size:12px;margin-top:6px;color:var(--red);"><input type="checkbox" name="clear_secret" value="1" style="width:auto;"> Remove saved secret</label>' if cfg['has_webhook_secret'] else ''}
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Public site URL</label>
              <input type="text" name="public_base_url" maxlength="255" placeholder="https://cbn-sl.org" value="{esc(cfg['public_base_url'])}">
              <small style="color:var(--gray-500);">Used for Monime's return + webhook links. Currently detected: <code>{esc(public_base)}</code>. Monime cannot reach 127.0.0.1 — for webhooks during local testing use a tunnel such as ngrok.</small>
            </div>
            <div class="form-group">
              <label>Financial account ID (optional)</label>
              <input type="text" name="financial_account_id" maxlength="100" value="{esc(cfg['financial_account_id'])}">
              <small style="color:var(--gray-500);">Leave blank to settle into your main Monime account.</small>
            </div>
          </div>
          <div class="form-group" style="max-width:220px;">
            <label>Checkout brand colour</label>
            <input type="text" name="primary_color" maxlength="9" value="{esc(cfg['primary_color'])}">
          </div>
          <button type="submit" class="btn btn-primary">Save settings</button>
          <small style="margin-left:12px;color:var(--gray-500);">Saved to <code>{esc(cfg['env_file'])}</code> (owner-only) and applied immediately.</small>
        </form>
        <form method="POST" action="/admin/payments/test" style="margin-top:14px;">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <button type="submit" class="btn btn-navy" {'disabled' if cfg['effective_mode'] in ('simulation','disabled') else ''}>Test connection to Monime</button>
        </form>
      </div>
    </div>"""

    recent_rows = "".join(
        f"""<tr>
          <td><strong>{esc(r['reference'])}</strong><br><small>{esc(r['email'] or '')}</small></td>
          <td>Le {r['amount_sll']:,}<br><small>SLE {r['amount_sll']/1000:,.2f}</small></td>
          <td><span class="pill {'approved' if r['status']=='completed' else ('pending' if r['status']=='pending' else 'rejected')}">{esc(r['status'])}</span>
              <br><small>{esc((r['gateway_mode'] if 'gateway_mode' in r.keys() else '') or '')} · {esc((r['gateway_status'] if 'gateway_status' in r.keys() else '') or '')}</small></td>
          <td><small>{esc(r['submitted_at'][:16])}</small></td>
        </tr>""" for r in recent
    ) or '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--gray-500);">No donations yet.</td></tr>'

    event_rows = "".join(
        f"""<tr>
          <td><small>{esc(r['created_at'][:19])}</small></td>
          <td><strong>{esc(r['donation_ref'] or '—')}</strong><br><small style="font-family:monospace;">{esc((r['session_id'] or '')[:24])}</small></td>
          <td>{esc(r['source'])}<br><small>{esc(r['event_type'] or '')}</small></td>
          <td>{esc(r['status'] or '—')}</td>
          <td>{'<span class="pill approved">verified</span>' if r['verified'] else '<span class="pill pending">unverified</span>'}</td>
        </tr>""" for r in events
    ) or '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--gray-500);">No gateway events yet.</td></tr>'

    body = f"""
    <div class="flash {kind}" style="display:flex;gap:10px;align-items:flex-start;">
      <span style="font-size:16px;">{icon}</span>
      <div><strong>Status:</strong> {esc(gw_msg)}<br>
        <small>Donations are only marked <em>completed</em> after the server confirms the checkout session with Monime —
        never from the browser redirect alone.</small></div>
    </div>
    {setup}
    {form}
    {webhook_card}
    <div class="card">
      <div class="card-head">Recent donations</div>
      <table><thead><tr><th>Reference</th><th>Amount</th><th>Status</th><th>When</th></tr></thead>
      <tbody>{recent_rows}</tbody></table>
      <div style="padding:10px 18px;"><a href="/admin/donations">All donations →</a></div>
    </div>
    <div class="card">
      <div class="card-head">Gateway event log (last {len(events)})</div>
      <table><thead><tr><th>When</th><th>Reference / Session</th><th>Source / Event</th><th>Status</th><th>Trust</th></tr></thead>
      <tbody>{event_rows}</tbody></table>
    </div>"""
    return render_layout("Payments (Monime)", "payments", body, admin, csrf, flash)


# ------------------------------------------------------------------
# SIMULATED CHECKOUT PAGE (used only when no Monime credentials exist)
# ------------------------------------------------------------------
def render_simulated_checkout(d, amount_sle):
    ref = d["reference"]
    sid = d["checkout_session_id"]
    donor = f"{d.get('first_name','')} {d.get('last_name','')}".strip() or "Donor"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simulated checkout — CBN</title>
<style>
  body{{margin:0;font-family:Helvetica,Arial,sans-serif;background:#f4f6f9;color:#111827;}}
  .wrap{{max-width:520px;margin:40px auto;padding:0 16px;}}
  .card{{background:#fff;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.08);overflow:hidden;}}
  .head{{background:#0a2a4a;color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;}}
  .head strong{{font-size:15px;}} .tag{{background:#f59e0b;color:#111;font-size:11px;font-weight:800;letter-spacing:1px;padding:4px 10px;border-radius:20px;}}
  .body{{padding:24px;}}
  .amt{{font-size:34px;font-weight:800;color:#0a2a4a;margin:4px 0 2px;}}
  .sub{{color:#6b7280;font-size:13px;margin-bottom:18px;}}
  .opt{{display:flex;align-items:center;gap:12px;border:2px solid #e5e7eb;border-radius:10px;padding:12px 14px;margin-bottom:10px;cursor:pointer;}}
  .opt input{{accent-color:#f36f21;}}
  .opt .logo{{width:38px;height:38px;border-radius:8px;display:grid;place-items:center;font-weight:900;color:#fff;font-size:12px;}}
  label.f{{display:block;font-size:12px;font-weight:700;color:#0a2a4a;text-transform:uppercase;letter-spacing:.8px;margin:14px 0 6px;}}
  input.t{{width:100%;padding:12px;border:1.5px solid #e5e7eb;border-radius:8px;font-size:15px;box-sizing:border-box;}}
  .btn{{display:block;width:100%;border:0;border-radius:8px;padding:14px;font-weight:800;font-size:15px;cursor:pointer;margin-top:10px;}}
  .ok{{background:#16a34a;color:#fff;}} .bad{{background:#fee2e2;color:#991b1b;}} .cancel{{background:#f3f4f6;color:#374151;}}
  .note{{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:8px;padding:12px;font-size:13px;line-height:1.5;margin-bottom:16px;}}
  .foot{{text-align:center;color:#9ca3af;font-size:12px;padding:14px;}}
</style></head><body><div class="wrap"><div class="card">
  <div class="head"><strong>Secure checkout</strong><span class="tag">SIMULATION</span></div>
  <div class="body">
    <div class="note">This is a <strong>local stand-in</strong> for Monime's hosted payment page, shown because no Monime
      credentials are configured yet. Nothing is charged. Pick an outcome to test how the website reacts.</div>
    <div class="sub">Donation to Community Builders Network · Ref <strong>{esc(ref)}</strong></div>
    <div class="amt">{esc(amount_sle)}</div>
    <div class="sub">≈ Le {int(d['amount_sll']):,} (old leones) · {esc(donor)}</div>
    <form method="POST" action="/pay/simulate/{esc(sid)}">
      <label class="opt"><input type="radio" name="provider" value="m17" checked><span class="logo" style="background:#ff6b00;">OM</span><span><strong>Orange Money</strong><br><small style="color:#6b7280;">m17 · USSD PIN prompt</small></span></label>
      <label class="opt"><input type="radio" name="provider" value="m18"><span class="logo" style="background:#7c3aed;">AM</span><span><strong>Africell Money</strong><br><small style="color:#6b7280;">m18</small></span></label>
      <label class="opt"><input type="radio" name="provider" value="card"><span class="logo" style="background:#0a2a4a;">💳</span><span><strong>Card</strong><br><small style="color:#6b7280;">Visa / Mastercard</small></span></label>
      <label class="f">Mobile number</label>
      <input class="t" type="tel" name="phone" value="{esc(d.get('phone') or '')}" placeholder="+232 76 000 000">
      <button class="btn ok" name="outcome" value="success">✓ Simulate successful payment</button>
      <button class="btn bad" name="outcome" value="fail">✗ Simulate failed / expired payment</button>
      <button class="btn cancel" name="outcome" value="cancel">Cancel and return to CBN</button>
    </form>
  </div>
  <div class="foot">Session {esc(sid)} · add Monime credentials in Admin → Payments to use the real hosted checkout</div>
</div></div></body></html>"""


# ------------------------------------------------------------------
# INBOX — replies from applicants
# ------------------------------------------------------------------
def render_inbox(admin, csrf, rows, flash=None, last_sync="never", last_error="",
                 mail_live=False, account="", filter_volunteer=None):
    unread = sum(1 for r in rows if not r["is_read"])

    if not mail_live:
        banner = ('<div class="flash warn">Email is not configured, so the inbox cannot be read. '
                  'Add the Gmail App Password under <a href="/admin/email">Email Settings</a>.</div>')
    elif last_error:
        banner = (f'<div class="flash err"><strong>Last inbox check failed:</strong> {esc(last_error)}<br>'
                  f'<small>Replies are still arriving in the Gmail inbox for {esc(account)} — this only affects '
                  f'showing them here.</small></div>')
    else:
        banner = (f'<div class="flash info">Replies sent to <strong>{esc(account)}</strong> appear here automatically '
                  f'(checked every 2 minutes; last check: {esc(last_sync)}). Messages are matched to applicants by '
                  f'their reference number or email address.</div>')

    head = f"""
    {banner}
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:18px;flex-wrap:wrap;">
      <form method="POST" action="/admin/inbox/sync">
        <input type="hidden" name="csrf_token" value="{esc(csrf)}">
        <button type="submit" class="btn btn-primary" {'disabled' if not mail_live else ''}>⟳ Check inbox now</button>
      </form>
      {'<a href="/admin/inbox" class="btn btn-ghost">Show all messages</a>' if filter_volunteer else ''}
      <span style="color:var(--gray-500);font-size:13px;">{len(rows)} message(s) · {unread} unread</span>
    </div>"""

    cards = []
    for r in rows:
        who = f"{esc(r['from_name'])} &lt;{esc(r['from_addr'])}&gt;" if r["from_name"] else esc(r["from_addr"])
        link = ""
        if r["volunteer_id"]:
            link = (f'<a href="/admin/volunteers" style="font-size:12px;">'
                    f'Applicant: {esc(r["first_name"] or "")} {esc(r["last_name"] or "")} '
                    f'(CBN-VOL-{int(r["volunteer_id"]):05d}) · <span class="pill {esc(r["vol_status"] or "pending")}">'
                    f'{esc(r["vol_status"] or "")}</span></a>')
        else:
            link = '<small style="color:var(--gray-500);">Not matched to an application</small>'
        body = esc(r["body"] or "").replace("\n", "<br>")
        cards.append(f"""
        <div class="card" style="border-left:4px solid {'var(--orange)' if not r['is_read'] else 'var(--gray-200)'};">
          <div class="card-head" style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;text-transform:none;letter-spacing:0;">
            <div>
              {'<span class="pill new" style="margin-right:8px;">unread</span>' if not r['is_read'] else ''}
              <span style="font-size:14px;">{esc(r['subject'] or '(no subject)')}</span><br>
              <small style="font-weight:400;color:var(--gray-500);">From {who} · {esc((r['received_at'] or '')[:16].replace('T',' '))}</small>
            </div>
            <form method="POST" action="/admin/inbox/{r['id']}/read">
              <input type="hidden" name="csrf_token" value="{esc(csrf)}">
              {'<input type="hidden" name="unread" value="1">' if r['is_read'] else ''}
              <button type="submit" class="btn btn-ghost btn-sm">{'Mark unread' if r['is_read'] else 'Mark read'}</button>
            </form>
          </div>
          <div class="card-body">
            <div style="margin-bottom:12px;">{link}</div>
            <div style="background:var(--gray-50);border:1px solid var(--gray-100);border-radius:6px;padding:14px 16px;
                        font-size:14px;line-height:1.65;color:var(--gray-700);white-space:normal;">{body or '<em style="color:var(--gray-500);">(empty message)</em>'}</div>
            <details style="margin-top:14px;">
              <summary style="cursor:pointer;font-weight:700;font-size:13px;color:var(--navy);">↩ Reply from {esc(account)}</summary>
              <form method="POST" action="/admin/inbox/{r['id']}/reply" style="margin-top:10px;">
                <input type="hidden" name="csrf_token" value="{esc(csrf)}">
                <textarea name="body" required placeholder="Type your reply to {esc(r['from_addr'])}…" style="min-height:120px;"></textarea>
                <button type="submit" class="btn btn-navy" style="margin-top:8px;">Send reply</button>
                <small style="margin-left:10px;color:var(--gray-500);">Signed with your admin name and the office details.</small>
              </form>
            </details>
          </div>
        </div>""")

    empty = ('<div class="card"><div class="card-body" style="text-align:center;color:var(--gray-500);padding:40px;">'
             'No replies yet. When an applicant answers one of our emails, it will appear here.</div></div>')

    title = "Inbox — replies from applicants" + (f" (CBN-VOL-{filter_volunteer:05d})" if filter_volunteer else "")
    return render_layout(title, "inbox", head + ("".join(cards) or empty), admin, csrf, flash)


# ------------------------------------------------------------------
# EMAIL SETTINGS
# ------------------------------------------------------------------
def render_email_settings(admin, csrf, cfg, mode, message, log_rows, default_test_to, flash=None,
                          outbox_rows=None, outbox=None, net_ok=True, net_why=""):
    outbox_rows = outbox_rows or []
    outbox = outbox or {"pending": 0, "sending": 0, "failed": 0, "sent": 0}
    banner_kind = {"live": "ok", "console": "warn", "disabled": "warn"}.get(mode, "info")
    banner_icon = {"live": "✅", "console": "⚠", "disabled": "⏸"}.get(mode, "ℹ")
    if mode == "live" and not net_ok:
        banner_kind, banner_icon = "err", "📴"
        message = f"OFFLINE — {net_why}"

    # ── Outbox panel ──
    waiting = outbox["pending"] + outbox["sending"]
    outbox_banner = ""
    if waiting or outbox["failed"]:
        outbox_banner = (
            f'<div class="flash {"warn" if waiting else "err"}" style="display:flex;gap:10px;align-items:flex-start;">'
            f'<span style="font-size:16px;">📤</span><div>'
            f'<strong>{waiting} email(s) waiting to be sent</strong>'
            + (f' · <strong style="color:var(--red);">{outbox["failed"]} failed permanently</strong>' if outbox["failed"] else "")
            + '<br><small>Queued emails are retried automatically every 30 seconds with increasing delays '
              'for up to 30 attempts. They are sent the moment the network is back — nothing is lost.</small>'
              '</div></div>'
        )
    outbox_row_html = "".join(
        f"""<tr>
          <td><strong>{esc(r['to_address'])}</strong><br><small>{esc(r['subject'])}</small></td>
          <td><span class="pill {'pending' if r['status'] in ('pending','sending') else 'rejected'}">{esc(r['status'])}</span>
              <br><small>attempt {r['attempts']} / {r['max_attempts']}</small></td>
          <td><small>{esc((r['last_error'] or '').replace('NETWORK: ', '')[:160])}</small></td>
          <td><small>next: {esc((r['next_try_at'] or '')[:16])}</small></td>
          <td><div class="actions">
            <form method="POST" action="/admin/outbox/{r['id']}/retry">
              <input type="hidden" name="csrf_token" value="{esc(csrf)}">
              <button type="submit" class="btn btn-ghost btn-sm">Retry now</button></form>
            <form method="POST" action="/admin/outbox/{r['id']}/cancel" onsubmit="return confirm('Cancel this email?');">
              <input type="hidden" name="csrf_token" value="{esc(csrf)}">
              <button type="submit" class="btn btn-danger btn-sm">Cancel</button></form>
          </div></td>
        </tr>""" for r in outbox_rows
    )
    outbox_panel = f"""
    <div class="card">
      <div class="card-head" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Outbox — {waiting} waiting · {outbox['failed']} failed · {outbox['sent']} sent in total</span>
        <form method="POST" action="/admin/outbox/send-now">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <button type="submit" class="btn btn-primary btn-sm" {'disabled' if not outbox_rows else ''}>⟳ Send all waiting now</button>
        </form>
      </div>
      <table>
        <thead><tr><th>To / Subject</th><th>Status</th><th>Last problem</th><th>Next try</th><th></th></tr></thead>
        <tbody>{outbox_row_html or '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--gray-500);">Nothing waiting — all emails have been delivered.</td></tr>'}</tbody>
      </table>
    </div>"""

    gmail_steps = ""
    if cfg["is_gmail"]:
        gmail_steps = f"""
        <div class="card" style="border-left:4px solid var(--orange);">
          <div class="card-head">How to get the Gmail App Password for {esc(cfg['sender_address'])}</div>
          <div class="card-body" style="font-size:13px;color:var(--gray-700);line-height:1.7;">
            <ol style="margin:0 0 0 18px;">
              <li>Sign in to Google with <strong>{esc(cfg['sender_address'])}</strong>.</li>
              <li>Open <a href="https://myaccount.google.com/security" target="_blank" rel="noopener">Google Account → Security</a>
                  and make sure <strong>2-Step Verification</strong> is turned <strong>on</strong> (App Passwords are only offered when it is).</li>
              <li>Open <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener">App passwords</a>,
                  type a name such as <em>CBN website</em> and click <strong>Create</strong>.</li>
              <li>Copy the 16-character password Google shows (e.g. <code>abcd efgh ijkl mnop</code>) and paste it below —
                  spaces are fine. Do <strong>not</strong> use the normal Gmail password.</li>
              <li>Click <strong>Save settings</strong>, then <strong>Send test email</strong> to confirm delivery.</li>
              <li>To see applicants' <em>replies</em> in <a href="/admin/inbox">Inbox</a>, make sure IMAP is on:
                  Gmail → ⚙ Settings → <em>See all settings</em> → <em>Forwarding and POP/IMAP</em> → <strong>Enable IMAP</strong>
                  (on by default for new accounts; the same App Password is used).</li>
            </ol>
            <p style="margin:12px 0 0;color:var(--gray-500);">Free Gmail accounts can send about 500 emails per day — plenty for volunteer notifications.
            The server tries port 587 (STARTTLS) and falls back to 465 (SSL) automatically; if you ever see an
            <code>SSL</code> error in the log, install the <code>certifi</code> package (<code>pip3 install certifi</code>) or try another network.</p>
          </div>
        </div>"""

    pw_hint = (f'<span style="color:var(--green);font-weight:700;">Saved</span> {esc(cfg["password_mask"])} — '
               f'leave blank to keep it, or paste a new one to replace it.'
               if cfg["has_password"] else
               '<span style="color:var(--red);font-weight:700;">Not saved yet</span> — emails are printed to the terminal until you add it.')

    log_html = "".join(
        f"""<tr>
          <td><strong>{esc(r['to_address'])}</strong><br><small>{esc(r['subject'])}</small></td>
          <td><small>{esc(_email_kind_label(r['kind']))}</small></td>
          <td><span class="pill {_email_pill(r['status'])}">{esc(_email_label(r['status']))}</span>
              {f'<br><small style="color:var(--red);">{esc(r["detail"])}</small>' if r['status']=='failed' and r['detail'] else ''}</td>
          <td><small>{esc((r['sent_at'] or r['created_at'] or '')[:16])}</small></td>
        </tr>""" for r in log_rows
    ) or '<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--gray-500);">No emails sent yet.</td></tr>'

    body = f"""
    <div class="flash {banner_kind}" style="display:flex;gap:10px;align-items:flex-start;">
      <span style="font-size:16px;">{banner_icon}</span>
      <div><strong>Status:</strong> {esc(message)}<br>
        <small>All notifications are sent <strong>from {esc(cfg['sender_header'])}</strong> to the address
        the applicant entered on the website form.</small></div>
    </div>

    {outbox_banner}
    {outbox_panel}

    {gmail_steps}

    <div class="card">
      <div class="card-head">Sending account (SMTP)</div>
      <div class="card-body">
        <form method="POST" action="/admin/email" autocomplete="off">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">

          <div class="form-group">
            <label style="display:inline-flex;align-items:center;gap:8px;text-transform:none;font-size:13px;">
              <input type="checkbox" name="enabled" value="1" style="width:auto;" {'checked' if cfg['enabled'] else ''}>
              Enable sending real emails (untick to print emails to the terminal instead)
            </label>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Sending account (Gmail address) *</label>
              <input type="email" name="smtp_user" required maxlength="254" value="{esc(cfg['user'])}">
              <small style="color:var(--gray-500);">Emails are sent <em>from</em> this address. Gmail requires it to be the account that logs in.</small>
            </div>
            <div class="form-group">
              <label>Display name</label>
              <input type="text" name="from_name" maxlength="100" value="{esc(cfg['from_name'])}">
              <small style="color:var(--gray-500);">Shown as: <strong>{esc(cfg['sender_header'])}</strong></small>
            </div>
          </div>

          <div class="form-group">
            <label>Gmail App Password *</label>
            <input type="password" name="smtp_pass" maxlength="100" placeholder="abcd efgh ijkl mnop"
                   autocomplete="new-password">
            <small style="color:var(--gray-500);">{pw_hint}</small>
            {f'''<label style="display:inline-flex;align-items:center;gap:8px;text-transform:none;font-size:12px;margin-top:8px;color:var(--red);">
              <input type="checkbox" name="clear_password" value="1" style="width:auto;"> Remove the saved password
            </label>''' if cfg['has_password'] else ''}
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>SMTP host *</label>
              <input type="text" name="smtp_host" required maxlength="200" value="{esc(cfg['host'])}">
            </div>
            <div class="form-group">
              <label>SMTP port</label>
              <input type="number" name="smtp_port" min="1" max="65535" value="{esc(cfg['port'])}">
              <small style="color:var(--gray-500);">587 = STARTTLS (recommended) · 465 = SSL</small>
            </div>
          </div>

          <div class="form-group">
            <label>Reply-To address</label>
            <input type="email" name="reply_to" maxlength="254" value="{esc(cfg['reply_to'])}">
            <small style="color:var(--gray-500);">Where applicants' replies land. Leave as the sending account unless you have a shared inbox.</small>
          </div>

          <div class="card-head" style="margin:10px -20px 16px;">Office details printed in every email</div>
          <div class="form-group">
            <label>Office address</label>
            <input type="text" name="office_address" maxlength="200" value="{esc(cfg['office_address'])}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Office phone</label>
              <input type="text" name="office_phone" maxlength="40" value="{esc(cfg['office_phone'])}">
            </div>
            <div class="form-group">
              <label>Office email</label>
              <input type="email" name="office_email" maxlength="254" value="{esc(cfg['office_email'])}">
            </div>
          </div>

          <button type="submit" class="btn btn-primary">Save settings</button>
          <small style="margin-left:12px;color:var(--gray-500);">
            Saved to <code>{esc(cfg['env_file'])}</code> (owner-only permissions) and applied immediately — no restart needed.
          </small>
        </form>
      </div>
    </div>

    <div class="card">
      <div class="card-head">Send a test email</div>
      <div class="card-body">
        <form method="POST" action="/admin/email/test" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <div class="form-group" style="flex:1;min-width:260px;margin:0;">
            <label>Send to</label>
            <input type="email" name="to" required maxlength="254" value="{esc(default_test_to)}">
          </div>
          <button type="submit" class="btn btn-navy">Send test email</button>
        </form>
        <small style="display:block;margin-top:10px;color:var(--gray-500);">
          Sends a short message from {esc(cfg['sender_address'])}. The result appears in the delivery log below (refresh after a few seconds).
        </small>
      </div>
    </div>

    <div class="card">
      <div class="card-head">Delivery log — last {len(log_rows)} emails</div>
      <table>
        <thead><tr><th>To / Subject</th><th>Type</th><th>Result</th><th>When</th></tr></thead>
        <tbody>{log_html}</tbody>
      </table>
    </div>
    """
    return render_layout("Email Settings", "email", body, admin, csrf, flash)


def _email_pill(status):
    return {"sent": "approved", "console": "read", "queued": "pending", "failed": "rejected"}.get(status, "read")


def _email_label(status):
    return {"sent": "Sent", "console": "Printed to console", "queued": "Sending…", "failed": "Failed"}.get(status, status or "")


_EMAIL_KIND_LABELS = {
    "volunteer_approved":    "→ applicant · approved",
    "volunteer_rejected":    "→ applicant · rejected",
    "application_received":  "→ applicant · receipt",
    "new_application_alert": "→ office · new application",
    "office_copy_approved":  "→ office · approved copy",
    "office_copy_rejected":  "→ office · rejected copy",
    "test_email":            "test",
}


def _email_kind_label(kind):
    return _EMAIL_KIND_LABELS.get(kind or "", (kind or "").replace("_", " "))


# ------------------------------------------------------------------
# CHANGE PASSWORD
# ------------------------------------------------------------------
def render_password(admin, csrf, flash=None):
    body = f"""
    <div class="card" style="max-width:600px;">
      <div class="card-head">Change Your Password</div>
      <div class="card-body">
        <p style="color:var(--gray-500);font-size:13px;margin-bottom:20px;">
          Passwords must be at least 12 characters and include upper, lower,
          digit and special characters.
        </p>
        <form method="POST" action="/admin/password" autocomplete="off">
          <input type="hidden" name="csrf_token" value="{esc(csrf)}">
          <div class="form-group">
            <label>Current Password</label>
            <input type="password" name="current" required maxlength="200">
          </div>
          <div class="form-group">
            <label>New Password</label>
            <input type="password" name="new1" required maxlength="200" minlength="12">
          </div>
          <div class="form-group">
            <label>Confirm New Password</label>
            <input type="password" name="new2" required maxlength="200" minlength="12">
          </div>
          <button type="submit" class="btn btn-primary">Update Password</button>
        </form>
      </div>
    </div>
    """
    return render_layout("Change Password", "password", body, admin, csrf, flash)
