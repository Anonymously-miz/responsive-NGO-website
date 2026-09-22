"""
CBN Backend — Database layer (SQLite)
======================================
Schema, connection helper, initialization, and seed data.
Uses only the standard library (sqlite3).
"""

import sqlite3
import os
from contextlib import contextmanager

# Path to the SQLite database file (sits next to server.py)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cbn.db")


# ------------------------------------------------------------------
# SCHEMA — all tables in one place
# ------------------------------------------------------------------
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- Admin users who can log into the panel
CREATE TABLE IF NOT EXISTS admins (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    email          TEXT,
    password_hash  TEXT NOT NULL,
    password_salt  TEXT NOT NULL,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login     TEXT
);

-- Active login sessions (server-side)
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    admin_id    INTEGER NOT NULL,
    csrf_token  TEXT NOT NULL,
    ip_address  TEXT,
    user_agent  TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at  TEXT NOT NULL,
    FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
);

-- Volunteer applications
CREATE TABLE IF NOT EXISTS volunteers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    email          TEXT NOT NULL,
    phone          TEXT,
    role           TEXT,
    availability   TEXT,
    message        TEXT,
    status         TEXT DEFAULT 'pending'
                   CHECK(status IN ('pending','approved','rejected')),
    submitted_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    ip_address     TEXT
);

-- Contact form messages
CREATE TABLE IF NOT EXISTS contacts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    email          TEXT NOT NULL,
    subject        TEXT,
    message        TEXT NOT NULL,
    status         TEXT DEFAULT 'new'
                   CHECK(status IN ('new','read','replied','archived')),
    submitted_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    ip_address     TEXT
);

-- Partnership enquiries
CREATE TABLE IF NOT EXISTS partners (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    organisation      TEXT NOT NULL,
    contact_name      TEXT NOT NULL,
    email             TEXT NOT NULL,
    partnership_type  TEXT,
    message           TEXT,
    status            TEXT DEFAULT 'new',
    submitted_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Newsletter subscribers
CREATE TABLE IF NOT EXISTS subscribers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    subscribed_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    active          INTEGER DEFAULT 1
);

-- Blog posts (managed by admin)
CREATE TABLE IF NOT EXISTS blog_posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    slug         TEXT NOT NULL UNIQUE,
    category     TEXT,
    excerpt      TEXT,
    content      TEXT,
    author       TEXT,
    image_url    TEXT,
    published    INTEGER DEFAULT 0,
    published_at TEXT,                          -- set when a post first goes live
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Events (upcoming and past)
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    event_date   TEXT NOT NULL,
    event_time   TEXT,
    location     TEXT,
    description  TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Projects (current and past)
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    category        TEXT,
    district        TEXT,
    description     TEXT,
    article_content TEXT,
    image_url       TEXT,
    banner_url      TEXT,
    status          TEXT DEFAULT 'current'
                    CHECK(status IN ('current','past')),
    funded_percent  INTEGER DEFAULT 0,
    start_year      INTEGER,
    end_year        INTEGER,
    author          TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug);

-- Login attempts (for rate limiting)
CREATE TABLE IF NOT EXISTS login_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address    TEXT NOT NULL,
    username      TEXT,
    success       INTEGER DEFAULT 0,
    attempted_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Donations (Orange Money / bank / card)
CREATE TABLE IF NOT EXISTS donations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    reference           TEXT NOT NULL UNIQUE,
    first_name          TEXT,
    last_name           TEXT,
    email               TEXT,
    phone               TEXT,
    amount_sll          INTEGER NOT NULL,
    currency            TEXT DEFAULT 'SLL',
    payment_method      TEXT DEFAULT 'orange_money',
    frequency           TEXT DEFAULT 'once',
    project_designation TEXT,
    anonymous           INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'pending'
                        CHECK(status IN ('pending','completed','failed','refunded')),
    om_transaction_id   TEXT,
    submitted_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    confirmed_at        TEXT,
    ip_address          TEXT
);

CREATE INDEX IF NOT EXISTS idx_donations_ref    ON donations(reference);
CREATE INDEX IF NOT EXISTS idx_donations_status ON donations(status);
CREATE INDEX IF NOT EXISTS idx_donations_email  ON donations(email);

-- Raw record of every payment-gateway event we receive or fetch
-- (webhooks, verification calls, simulation clicks). Nothing is ever deleted.
CREATE TABLE IF NOT EXISTS payment_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    donation_ref   TEXT,
    session_id     TEXT,
    source         TEXT,                 -- 'webhook' | 'verify' | 'return' | 'simulate' | 'admin'
    event_type     TEXT,                 -- e.g. checkout_session.completed
    status         TEXT,                 -- session status reported
    verified       INTEGER DEFAULT 0,    -- 1 if signature checked OK / server-fetched
    payload        TEXT,                 -- JSON (truncated)
    ip_address     TEXT,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payment_events_ref ON payment_events(donation_ref);

-- Outbound email log (every notification the system sends)
CREATE TABLE IF NOT EXISTS email_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    related_table TEXT,                 -- e.g. 'volunteers'
    related_id    INTEGER,              -- id in that table
    to_address    TEXT NOT NULL,
    subject       TEXT NOT NULL,
    kind          TEXT,                 -- e.g. 'volunteer_approved'
    status        TEXT DEFAULT 'queued'
                  CHECK(status IN ('queued','sent','failed','console')),
    detail        TEXT,                 -- server response / error text
    triggered_by  INTEGER,              -- admin id
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    sent_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_email_log_related ON email_log(related_table, related_id);

-- Inbound email (replies from applicants, read from the CBN Gmail inbox via IMAP)
CREATE TABLE IF NOT EXISTS inbound_emails (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    imap_uid      INTEGER NOT NULL UNIQUE,
    message_id    TEXT,
    in_reply_to   TEXT,
    from_name     TEXT,
    from_addr     TEXT NOT NULL,
    to_addr       TEXT,
    subject       TEXT,
    body          TEXT,
    volunteer_id  INTEGER,                 -- matched by reference or sender address
    is_read       INTEGER DEFAULT 0,
    received_at   TEXT,
    fetched_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (volunteer_id) REFERENCES volunteers(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_inbound_volunteer ON inbound_emails(volunteer_id);
CREATE INDEX IF NOT EXISTS idx_inbound_from      ON inbound_emails(from_addr);

-- Outbox: every email is queued here first and delivered by the background
-- worker, so nothing is lost if the network is down when it is created.
CREATE TABLE IF NOT EXISTS outbox (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    to_address    TEXT NOT NULL,
    to_name       TEXT,
    subject       TEXT NOT NULL,
    text_body     TEXT NOT NULL,
    html_body     TEXT,
    kind          TEXT,
    email_log_id  INTEGER,                 -- row in email_log to update on completion
    attempts      INTEGER DEFAULT 0,
    max_attempts  INTEGER DEFAULT 30,
    next_try_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    last_error    TEXT,
    status        TEXT DEFAULT 'pending'
                  CHECK(status IN ('pending','sending','sent','failed','cancelled')),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    sent_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox(status, next_try_at);

-- Small key/value store for runtime state (e.g. last IMAP UID seen)
CREATE TABLE IF NOT EXISTS app_state (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Audit log of admin actions
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER,
    action      TEXT NOT NULL,
    details     TEXT,
    ip_address  TEXT,
    timestamp   TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires    ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_volunteers_status   ON volunteers(status);
CREATE INDEX IF NOT EXISTS idx_contacts_status     ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip   ON login_attempts(ip_address, attempted_at);
CREATE INDEX IF NOT EXISTS idx_blog_slug           ON blog_posts(slug);
"""


# ------------------------------------------------------------------
# CONNECTION HELPER
# ------------------------------------------------------------------
@contextmanager
def get_db():
    """Yield a SQLite connection with Row factory and foreign keys ON."""
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # safer concurrent access
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def query_one(sql, params=()):
    """Return the first row or None."""
    with get_db() as db:
        return db.execute(sql, params).fetchone()


def query_all(sql, params=()):
    """Return all matching rows."""
    with get_db() as db:
        return db.execute(sql, params).fetchall()


def execute(sql, params=()):
    """Run an INSERT/UPDATE/DELETE; return lastrowid."""
    with get_db() as db:
        cur = db.execute(sql, params)
        return cur.lastrowid


# ------------------------------------------------------------------
# INITIALIZATION & SEEDING
# ------------------------------------------------------------------
def initialize():
    """Create tables, run migrations, seed default data."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.executescript(SCHEMA_SQL)
    finally:
        conn.close()

    _migrate_projects_table()   # safely add new columns to existing DBs
    _migrate_blog_table()       # adds published_at + back-fills existing posts
    _migrate_donations_table()  # adds Monime gateway columns
    _migrate_admins_table()     # adds must_change_password flag

    created_default = _seed_admin()
    _seed_projects()
    _seed_blog()
    _seed_events()
    return created_default


def _migrate_donations_table():
    """Add Monime payment-gateway columns to donations (safe, idempotent)."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.execute("BEGIN")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(donations)")}
        migrations = [
            ("gateway",             "ALTER TABLE donations ADD COLUMN gateway TEXT DEFAULT 'monime'"),
            ("gateway_mode",        "ALTER TABLE donations ADD COLUMN gateway_mode TEXT"),           # test/live/simulation
            ("checkout_session_id", "ALTER TABLE donations ADD COLUMN checkout_session_id TEXT"),
            ("checkout_url",        "ALTER TABLE donations ADD COLUMN checkout_url TEXT"),
            ("order_number",        "ALTER TABLE donations ADD COLUMN order_number TEXT"),
            ("amount_minor",        "ALTER TABLE donations ADD COLUMN amount_minor INTEGER"),        # SLE minor units sent to Monime
            ("gateway_status",      "ALTER TABLE donations ADD COLUMN gateway_status TEXT"),         # raw Monime status
            ("paid_at",             "ALTER TABLE donations ADD COLUMN paid_at TEXT"),
            ("last_verified_at",    "ALTER TABLE donations ADD COLUMN last_verified_at TEXT"),
            ("failure_reason",      "ALTER TABLE donations ADD COLUMN failure_reason TEXT"),
            ("card_holder",         "ALTER TABLE donations ADD COLUMN card_holder TEXT"),        # card payments only
            ("momo_operator",       "ALTER TABLE donations ADD COLUMN momo_operator TEXT"),      # 'orange' | 'africell'
        ]
        for col, sql in migrations:
            if col not in existing:
                conn.execute(sql)
                print(f"  Migration applied: added column '{col}' to donations")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_session ON donations(checkout_session_id)")
        conn.execute("COMMIT")
    except Exception as e:
        print(f"  Migration warning (donations): {e}")
        try: conn.execute("ROLLBACK")
        except Exception: pass
    finally:
        conn.close()


def payment_event(donation_ref, session_id, source, event_type, status, verified, payload, ip=None):
    """Append-only gateway audit trail."""
    try:
        import json as _json
        text = payload if isinstance(payload, str) else _json.dumps(payload, default=str)
    except Exception:
        text = str(payload)
    execute(
        "INSERT INTO payment_events (donation_ref,session_id,source,event_type,status,verified,payload,ip_address) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (donation_ref, session_id, source, event_type, status, 1 if verified else 0, (text or "")[:4000], ip),
    )


def _migrate_blog_table():
    """Add published_at to blog_posts (safe migration) and back-fill it.

    Ordering the public blog by published_at means "most recent post" is the
    one that most recently went live — not merely the one last edited.
    """
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.execute("BEGIN")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(blog_posts)")}
        if "published_at" not in existing:
            conn.execute("ALTER TABLE blog_posts ADD COLUMN published_at TEXT")
            print("  Migration applied: added column 'published_at' to blog_posts")
        # Any live post without a publish date: assume it went live when created
        cur = conn.execute(
            "UPDATE blog_posts SET published_at = created_at "
            "WHERE published = 1 AND (published_at IS NULL OR published_at = '')"
        )
        if cur.rowcount:
            print(f"  Migration: back-filled published_at for {cur.rowcount} blog post(s)")
        conn.execute("COMMIT")
    except Exception as e:
        print(f"  Migration warning (blog): {e}")
        try: conn.execute("ROLLBACK")
        except Exception: pass
    finally:
        conn.close()


def _migrate_admins_table():
    """Add must_change_password flag to admins table (for forced password change on first login)."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.execute("BEGIN")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(admins)")}
        if "must_change_password" not in existing:
            conn.execute("ALTER TABLE admins ADD COLUMN must_change_password INTEGER DEFAULT 0")
            print("  Migration applied: added column 'must_change_password' to admins")
        conn.execute("COMMIT")
    except Exception as e:
        print(f"  Migration warning (admins): {e}")
        try: conn.execute("ROLLBACK")
        except Exception: pass
    finally:
        conn.close()


def _migrate_projects_table():
    """Add new columns to projects table if they don't already exist (safe migration)."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.execute("BEGIN")   # explicit transaction so the COMMIT below is valid
        existing = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
        migrations = [
            ("slug",            "ALTER TABLE projects ADD COLUMN slug TEXT"),
            ("article_content", "ALTER TABLE projects ADD COLUMN article_content TEXT"),
            ("banner_url",      "ALTER TABLE projects ADD COLUMN banner_url TEXT"),
            ("author",          "ALTER TABLE projects ADD COLUMN author TEXT"),
            ("updated_at",      "ALTER TABLE projects ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP"),
        ]
        for col, sql in migrations:
            if col not in existing:
                conn.execute(sql)
                print(f"  Migration applied: added column '{col}' to projects")

        # Create index if missing (safe to run again — IF NOT EXISTS)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug)")

        # Back-fill slugs for any rows that have none
        rows = conn.execute("SELECT id, title FROM projects WHERE slug IS NULL OR slug = ''").fetchall()
        if rows:
            import re as _re
            for row_id, title in rows:
                base = _re.sub(r'[^\w\s-]', '', title.lower()).strip()
                base = _re.sub(r'[-\s]+', '-', base) or 'project'
                slug = base
                # Ensure uniqueness
                n = 1
                while conn.execute("SELECT id FROM projects WHERE slug=? AND id!=?",
                                   (slug, row_id)).fetchone():
                    slug = f"{base}-{n}"; n += 1
                conn.execute("UPDATE projects SET slug=? WHERE id=?", (slug, row_id))
            print(f"  Migration: back-filled slugs for {len(rows)} project(s)")
        conn.execute("COMMIT")
    except Exception as e:
        print(f"  Migration warning: {e}")
        try: conn.execute("ROLLBACK")
        except: pass
    finally:
        conn.close()


def _seed_admin():
    """Create a default admin account if none exist."""
    from security import hash_password  # local import avoids circular dep
    if query_one("SELECT id FROM admins LIMIT 1"):
        return False
    salt, pwd_hash = hash_password("ChangeMe123!")
    execute(
        "INSERT INTO admins (username, email, password_hash, password_salt, must_change_password) VALUES (?,?,?,?,?)",
        ("admin", "admin@cbn-sl.org", pwd_hash, salt, 1),
    )
    return True


def _seed_projects():
    if query_one("SELECT id FROM projects LIMIT 1"):
        return

    projects = [

        # ── 1. Safe Water for Kono District ────────────────────────────
        dict(
            title="Safe Water for Kono District",
            slug="safe-water-kono-district",
            category="health",
            district="Kono District",
            description="Constructing 24 solar-powered boreholes to provide reliable clean water to 12,000 people in remote villages.",
            image_url="https://images.pexels.com/photos/19879046/pexels-photo-19879046.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/19879046/pexels-photo-19879046.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="current",
            funded_percent=72,
            start_year=2024,
            end_year=2026,
            author="Fatmata Bangura",
            article_content="""<h2>The Challenge</h2>
<p>In Kono District, over 60% of rural households historically walked more than four kilometres daily to collect water from unprotected streams and seasonal ponds. Women and girls bore the heaviest burden — losing four to six hours every day that could have been spent in school, building a business, or caring for family. Water-borne diseases including cholera, typhoid and diarrhoeal illness accounted for nearly a third of under-five child deaths in the district.</p>

<h2>What We Are Doing</h2>
<p>The <strong>Safe Water for Kono District</strong> project is installing 24 solar-powered boreholes across 12 rural villages, serving an estimated 12,000 people. Each borehole is fitted with a submersible solar pump, a 5,000-litre overhead storage tank and multiple tap-stands positioned to minimise walking distance to under 300 metres for every household.</p>
<p>Every community receives a 12-week training programme covering:</p>
<ul>
  <li>Borehole maintenance and minor repairs</li>
  <li>Hygiene promotion and handwashing behaviour change</li>
  <li>Financial management for a community water fund</li>
  <li>Record-keeping and monthly usage reporting</li>
</ul>
<p>Each village elects a five-person <em>Water Management Committee</em> (at least three members must be women) that collects a small monthly fee from households — typically the equivalent of $0.30 — to cover spare parts and future repairs. This community-ownership model is the single biggest driver of long-term sustainability.</p>

<h2>Progress So Far</h2>
<p>By March 2026, <strong>17 of the 24 boreholes</strong> have been drilled and are operational. More than 8,500 people now have reliable access to safe water within a 5-minute walk. The remaining seven boreholes are under construction and are expected to be completed by October 2026.</p>
<p>Key results to date:</p>
<ul>
  <li>📉 Reported cases of diarrhoeal illness in participating villages are down <strong>61%</strong> year-on-year</li>
  <li>🏫 School attendance among girls aged 10–17 is up <strong>23%</strong> because they no longer spend mornings fetching water</li>
  <li>💧 17 Water Management Committees fully trained and operational</li>
  <li>♻️ 100% of committees collecting the community water fund on schedule</li>
</ul>

<h2>A Voice from the Ground</h2>
<blockquote>
  "Before the borehole, I woke up at 5 am every morning and walked with my daughters to the river. Sometimes the water was green. Now the tap is five minutes from our door. My daughters go to school every single day."
  <footer>— <strong>Mama Kadi</strong>, Njala Village, Kono District</footer>
</blockquote>

<h2>Partners & Funding</h2>
<p>This project is implemented by CBN in partnership with <strong>WaterAid Sierra Leone</strong> and the <strong>Kono District Council</strong>, with funding from <strong>USAID</strong> under the Water, Sanitation and Hygiene (WASH) for Rural Communities programme. Total project budget: <strong>$480,000</strong>. Funding secured to date: <strong>$345,600 (72%)</strong>.</p>

<h2>How You Can Help</h2>
<p>Each borehole costs approximately $20,000 to drill, equip and commission. A contribution of <strong>$5,000</strong> covers the solar pump and tank for one village. Every donation, large or small, brings safe water closer to the remaining 3,500 people still waiting.</p>""",
        ),

        # ── 2. Girls' Education Initiative ──────────────────────────────
        dict(
            title="Girls' Education Initiative",
            slug="girls-education-initiative",
            category="education",
            district="Bombali & Bo",
            description="Scholarships, mentorship and safe learning spaces for 1,500 girls at risk of dropping out of secondary school.",
            image_url="https://images.pexels.com/photos/15538205/pexels-photo-15538205.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/15538205/pexels-photo-15538205.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="current",
            funded_percent=58,
            start_year=2023,
            end_year=2027,
            author="Aminata Kamara",
            article_content="""<h2>Why Girls' Education in Sierra Leone?</h2>
<p>Sierra Leone has one of the highest adolescent pregnancy rates in the world, and pregnancy remains the leading cause of girls dropping out of secondary school. In Bombali and Bo districts, just <strong>38%</strong> of girls who start secondary school complete it. The barriers are well-documented: school fees, the cost of uniforms and materials, distance to school, domestic workload, and early marriage.</p>
<p>Research consistently shows that every additional year a girl stays in school increases her lifetime earnings by 10–12%, reduces the probability that her own children will be malnourished, and increases the age at which she first gives birth. Educating girls is the single highest-return investment Sierra Leone can make.</p>

<h2>What the Initiative Provides</h2>
<p>The <strong>Girls' Education Initiative</strong> supports 1,500 secondary-school girls across Bombali and Bo Districts with a comprehensive package:</p>
<ul>
  <li><strong>Scholarship grant:</strong> Full annual school fees paid directly to the school on the girl's behalf — no cash in hand that can be redirected</li>
  <li><strong>Material support:</strong> School uniform, textbooks, exercise books and sanitary supplies at the start of each term</li>
  <li><strong>Mentorship:</strong> Each girl is paired with a trained female mentor — a teacher, health worker or community leader — who meets with her monthly</li>
  <li><strong>Safe Spaces:</strong> After-school clubs in 18 partner schools providing a safe, gender-responsive environment for study, discussion and peer support</li>
  <li><strong>Family engagement:</strong> Quarterly meetings with parents and guardians to address attitudes about girls' education and early marriage</li>
  <li><strong>Emergency fund:</strong> A small fund for girls facing sudden household crises (illness, bereavement) that would otherwise force them to drop out</li>
</ul>

<h2>Results Since 2023</h2>
<p>The initiative began its first cohort in September 2023 with 500 girls. The second cohort of 500 joined in 2024, and the third cohort of 500 in 2025, bringing total enrolment to 1,500.</p>
<ul>
  <li>🎓 <strong>96.4%</strong> retention rate across all three cohorts — compared to a district average of 62%</li>
  <li>📈 Average exam scores for scholarship recipients are <strong>18%</strong> higher than the district average</li>
  <li>💬 <strong>1,200 parent-guardian meetings</strong> held since launch</li>
  <li>🏆 12 scholarship girls have won district or national academic awards</li>
  <li>👩‍⚕️ Of the 2023 cohort now in their final year, <strong>67%</strong> intend to pursue nursing, teaching or public health</li>
</ul>

<h2>Mariama's Story</h2>
<blockquote>
  "When my father died, my mother could not afford the school fees. She told me I would have to stay home and help with my younger brothers. The CBN scholarship changed everything. I completed secondary school and I am now studying nursing at Njala University — the first in my family to go to university."
  <footer>— <strong>Mariama Koroma, 19</strong>, CBN Scholar, Class of 2025, Bombali District</footer>
</blockquote>

<h2>Partners & Funding</h2>
<p>Implemented by CBN in partnership with the <strong>Ministry of Basic and Senior Secondary Education (MBSSE)</strong> and <strong>Plan International Sierra Leone</strong>. Funded by <strong>FCDO</strong> under the Girls' Education Challenge programme. Total budget: <strong>$1,200,000</strong>. Secured: <strong>$696,000 (58%)</strong>.</p>""",
        ),

        # ── 3. Women's Farming Cooperatives ─────────────────────────────
        dict(
            title="Women's Farming Cooperatives",
            slug="womens-farming-cooperatives",
            category="livelihoods",
            district="Northern Province",
            description="Training and micro-grants supporting 40 women-led agricultural cooperatives across the Northern Province.",
            image_url="https://images.pexels.com/photos/31537320/pexels-photo-31537320.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/31537320/pexels-photo-31537320.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="current",
            funded_percent=41,
            start_year=2025,
            end_year=2028,
            author="Ibrahim Sesay",
            article_content="""<h2>The Context: Women & Agriculture in Northern Sierra Leone</h2>
<p>Women produce approximately <strong>70%</strong> of Sierra Leone's food, yet they own less than 10% of agricultural land and receive under 5% of available agricultural credit. In the Northern Province — covering Bombali, Tonkolili, Koinadugu and Falaba districts — most female farmers work on smallholder plots of less than one hectare, growing rice, cassava, groundnuts and vegetables primarily for household consumption.</p>
<p>Without access to better seeds, storage facilities, market linkages or finance, these women are trapped in subsistence farming regardless of how hard they work. The result is household food insecurity, child malnutrition and persistent poverty — even in fertile land with good rainfall.</p>

<h2>Our Approach: The Cooperative Model</h2>
<p>CBN's <strong>Women's Farming Cooperatives</strong> project supports 40 women-led cooperatives across the Northern Province, each with 15–30 members, totalling approximately <strong>1,000 women</strong>.</p>
<p>Each cooperative receives a phased programme over three years:</p>

<h3>Year 1 — Foundation</h3>
<ul>
  <li>Legal registration of the cooperative and opening of a group bank account</li>
  <li>Training in cooperative governance, record-keeping and conflict resolution</li>
  <li>Agronomy training: improved seed varieties, soil health, intercropping and composting</li>
  <li>A <strong>starter micro-grant of $500</strong> for seed and basic tools</li>
</ul>

<h3>Year 2 — Growth</h3>
<ul>
  <li>Post-harvest handling and storage: reducing loss from the current 35% average to below 10%</li>
  <li>Market linkages: connecting cooperatives to local traders, school feeding programmes and urban markets in Makeni and Freetown</li>
  <li>Access to a <strong>matching grant of up to $2,000</strong> for equipment (drying racks, storage bins, small-scale processing)</li>
  <li>Financial literacy and introduction to mobile money savings</li>
</ul>

<h3>Year 3 — Sustainability</h3>
<ul>
  <li>Business planning for expansion and diversification</li>
  <li>Peer mentoring: established cooperatives mentor newer ones</li>
  <li>Introduction to formal microfinance institutions for future credit access</li>
</ul>

<h2>Early Results (Year 1, 2025)</h2>
<p>With 14 cooperatives now completing their first year:</p>
<ul>
  <li>🌾 Average crop yield among participating farmers is up <strong>42%</strong> compared to their own baseline</li>
  <li>💰 Average monthly household income increased from Le 320,000 to Le 580,000 (+81%)</li>
  <li>🏦 12 cooperatives now have active savings accounts with a combined balance of Le 48 million</li>
  <li>🥗 Reported child meal frequency (meals per day) increased from 1.8 to 2.6 in participating households</li>
</ul>

<h2>Isata's Story</h2>
<blockquote>
  "Before CBN, I farmed alone and sold a little at the roadside. Now our cooperative supplies vegetables to the school feeding programme in three chiefdoms. I have employed two women from my own village. My children eat properly and my eldest daughter is in secondary school."
  <footer>— <strong>Isata Conteh</strong>, Cooperative Chair, Tonkolili District</footer>
</blockquote>

<h2>Partners & Funding</h2>
<p>Implemented by CBN in partnership with the <strong>Ministry of Agriculture</strong> and <strong>Mercy Corps Sierra Leone</strong>. Funded by <strong>UNDP</strong> and the <strong>EU Delegation to Sierra Leone</strong>. Total budget: <strong>$860,000</strong>. Secured: <strong>$352,600 (41%)</strong>. This project urgently needs additional funding to reach the remaining 26 cooperatives.</p>""",
        ),

        # ── 4. Ebola Community Response ─────────────────────────────────
        dict(
            title="Ebola Community Response",
            slug="ebola-community-response",
            category="health",
            district="Nationwide",
            description="Trained 200 community health mobilisers reaching 40,000+ households during the outbreak.",
            image_url="https://images.pexels.com/photos/6129192/pexels-photo-6129192.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/6129192/pexels-photo-6129192.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="past",
            funded_percent=100,
            start_year=2014,
            end_year=2016,
            author="Aminata Kamara",
            article_content="""<h2>Background: Sierra Leone and the 2014–2016 Ebola Epidemic</h2>
<p>The West African Ebola epidemic of 2014–2016 was the largest in history. Sierra Leone was among the three worst-affected countries, recording <strong>14,124 confirmed cases</strong> and <strong>3,956 deaths</strong>. Beyond the direct mortality, the epidemic devastated healthcare systems, shut schools for nine months, collapsed agricultural supply chains and triggered an economic contraction of 21%.</p>
<p>In the early months of the outbreak, a critical obstacle was community resistance. Rumours, fear, distrust of health workers and deeply held cultural practices around burial meant that many families hid sick relatives, continued traditional washing of the dead and fled affected villages — all of which accelerated transmission.</p>

<h2>CBN's Response</h2>
<p>In August 2014, CBN rapidly retrained and deployed <strong>200 community health mobilisers</strong> drawn from within the affected communities — people who were already trusted by their neighbours. The decision to use insiders rather than external health workers proved transformative.</p>
<p>Each mobiliser was trained in a three-day intensive programme covering:</p>
<ul>
  <li>Ebola transmission routes and clinical signs</li>
  <li>Safe burial guidance and how to sensitively discuss it with families</li>
  <li>Rumour identification and evidence-based counter-messaging</li>
  <li>Referral pathways to Ebola Treatment Units (ETUs)</li>
  <li>Basic personal protective measures</li>
  <li>Psychosocial first aid for affected families</li>
</ul>
<p>Mobilisers conducted household visits — averaging <strong>10–15 houses per day</strong> — as well as community meetings, mosque and church outreach and market sensitisation. They operated across all 16 districts at peak deployment.</p>

<h2>Scale & Reach</h2>
<ul>
  <li>🏠 <strong>40,000+ households</strong> visited with life-saving information</li>
  <li>📢 <strong>1,200 community meetings</strong> held across all 16 districts</li>
  <li>🕌 Outreach delivered in <strong>380 mosques and churches</strong></li>
  <li>📞 <strong>6,800 hotline referrals</strong> logged and followed up</li>
  <li>⚰️ CBN mobilisers facilitated <strong>214 safe burials</strong> in communities that had initially refused them</li>
</ul>

<h2>Outcomes</h2>
<p>An independent evaluation commissioned by WHO and conducted by the London School of Hygiene & Tropical Medicine attributed a <strong>35% reduction in community transmission</strong> in districts where CBN mobilisers were active, compared to comparable districts without community-based mobilisation. In post-response surveys, 84% of respondents in CBN-covered areas said they would "definitely" use the ETU if they showed symptoms — up from 31% at the start of the response.</p>

<h2>A Mobiliser's Account</h2>
<blockquote>
  "People were so afraid. They thought the government had brought Ebola. When I went to a household, they sometimes chased me away. But I kept going back, with patience. By the third visit, they were asking me questions. I watched people in my own community survive because they came to the ETU in time. That is what I will always remember."
  <footer>— <strong>Alhaji Sesay</strong>, CBN Community Health Mobiliser, Kenema District</footer>
</blockquote>

<h2>Legacy</h2>
<p>The 200 community health mobilisers trained during the Ebola response formed the foundation of CBN's permanent Community Health Worker network, which today operates in 30 chiefdoms across Sierra Leone. The systems, training materials and community trust built during the crisis have since been used for COVID-19 response, malaria bed-net distribution and maternal health outreach. The Ebola response demonstrated, conclusively, that community-led approaches are not just more ethical — they are more effective.</p>

<h2>Partners</h2>
<p><strong>WHO Sierra Leone</strong>, <strong>UNICEF</strong>, <strong>MSF (Médecins Sans Frontières)</strong>, <strong>Ministry of Health and Sanitation</strong> and the <strong>Sierra Leone Red Cross</strong>. Fully funded by the <strong>Ebola Response Multi-Partner Trust Fund</strong>. Total expenditure: <strong>$620,000</strong>.</p>""",
        ),

        # ── 5. Rebuilding Rural Primary Schools ─────────────────────────
        dict(
            title="Rebuilding Rural Primary Schools",
            slug="rebuilding-rural-primary-schools",
            category="education",
            district="Kailahun District",
            description="Reconstructing 18 damaged primary schools with solar lighting, latrines and safe learning environments for 4,200 pupils.",
            image_url="https://images.pexels.com/photos/34162713/pexels-photo-34162713.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/34162713/pexels-photo-34162713.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="current",
            funded_percent=85,
            start_year=2024,
            end_year=2026,
            author="Ibrahim Sesay",
            article_content="""<h2>The Problem: Schools in Name Only</h2>
<p>In Kailahun District in eastern Sierra Leone — one of the poorest districts in the country — a survey conducted by CBN and the Ministry of Basic and Senior Secondary Education in 2023 found that <strong>18 primary schools</strong> were operating in conditions that posed a direct risk to the safety and learning of their pupils. Roofs had collapsed, walls were crumbling, latrines were overflowing or absent, and none had any form of electricity.</p>
<p>In total, <strong>4,200 children</strong> — of whom 52% were girls — were attending these schools. Teachers reported conducting lessons under mango trees when rain made the classrooms unusable. In some schools, children shared a single textbook between five pupils. In the absence of separate female latrines, many older girls stopped attending school during menstruation.</p>

<h2>What We Are Building</h2>
<p>The <strong>Rebuilding Rural Primary Schools</strong> project is reconstructing all 18 schools to a standard design approved by MBSSE, with each school receiving:</p>
<ul>
  <li><strong>Three permanent classrooms</strong> with cement floors, corrugated iron roofs and proper ventilation</li>
  <li><strong>A solar lighting system</strong> — four panels, a battery bank and LED lighting in all classrooms, enabling evening adult literacy classes</li>
  <li><strong>Separate sex latrines:</strong> 3 stalls for girls (including a menstrual hygiene management space), 2 for boys and 1 for teachers</li>
  <li><strong>A rainwater harvesting tank</strong> (5,000 litres) for handwashing and cleaning</li>
  <li><strong>A dedicated headteacher's office</strong> and a small library room stocked with 200 books</li>
  <li><strong>A lockable storeroom</strong> for teaching materials</li>
</ul>
<p>All construction uses local contractors and locally sourced materials where possible, creating employment in the communities.</p>

<h2>Progress</h2>
<p>As of March 2026, <strong>15 of the 18 schools</strong> have been fully completed and handed over to their communities. The three remaining schools are expected to be complete by June 2026.</p>
<ul>
  <li>🏫 15 schools completed and operational</li>
  <li>👧 Girls' enrolment across completed schools is up <strong>34%</strong> compared to the previous academic year</li>
  <li>📚 Pupil-to-textbook ratio improved from 5:1 to 1:1 in all completed schools</li>
  <li>🔆 All 15 completed schools have functional solar lighting</li>
  <li>🤝 Local contractors employed on the project earned a combined Le 2.4 billion in wages</li>
</ul>

<h2>Teacher's Perspective</h2>
<blockquote>
  "I have been teaching at this school for eleven years. For the first five, I taught in a room where the roof had holes and the children could not hear me when it rained. Now I have a classroom, a light, and books. My pupils come to school excited. That is everything."
  <footer>— <strong>Mr. James Lahai</strong>, Class 5 Teacher, Njaluahun Primary School, Kailahun</footer>
</blockquote>

<h2>Partners & Funding</h2>
<p>Implemented in partnership with <strong>MBSSE</strong> and the <strong>Kailahun District Education Office</strong>. Funded by <strong>UNICEF Sierra Leone</strong> and the <strong>Rotary Foundation</strong>. Total budget: <strong>$720,000</strong>. Secured: <strong>$612,000 (85%)</strong>.</p>""",
        ),

        # ── 6. Maternal & Child Health Outreach ─────────────────────────
        dict(
            title="Maternal & Child Health Outreach",
            slug="maternal-child-health-outreach",
            category="health",
            district="Pujehun District",
            description="Mobile clinics and 60 trained community health workers reducing maternal mortality in 30 rural chiefdoms.",
            image_url="https://images.pexels.com/photos/36633133/pexels-photo-36633133.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/36633133/pexels-photo-36633133.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="current",
            funded_percent=63,
            start_year=2025,
            end_year=2027,
            author="Fatmata Bangura",
            article_content="""<h2>The Crisis: Maternal Mortality in Pujehun</h2>
<p>Sierra Leone has one of the highest maternal mortality ratios in the world — approximately <strong>443 deaths per 100,000 live births</strong> (UNFPA, 2023). Pujehun District in the south of the country consistently records figures above the national average. The leading causes are post-partum haemorrhage, eclampsia, sepsis and obstructed labour — all of which are preventable or treatable with skilled attendance at birth and timely referral.</p>
<p>The fundamental problem is distance. Pujehun's 30 chiefdoms are spread across difficult terrain, with many villages more than 30 kilometres from the nearest government health facility. Women in labour may travel for hours by foot or motorbike before reaching care. Many do not make it in time.</p>

<h2>Our Approach</h2>
<p>The <strong>Maternal & Child Health Outreach</strong> project tackles the distance problem with a two-pronged strategy: bringing care to the community, and ensuring the community is equipped to get women to higher-level care when needed.</p>

<h3>60 Trained Community Health Workers</h3>
<p>CBN has recruited and trained 60 women — two per chiefdom — as Community Health Workers (CHWs). Each CHW completed a 12-week intensive training programme covering:</p>
<ul>
  <li>Antenatal care: registering pregnant women, monitoring weight, blood pressure and foetal position</li>
  <li>Recognising danger signs in pregnancy and labour</li>
  <li>Clean and safe delivery assistance for uncomplicated births</li>
  <li>Newborn care: immediate breastfeeding, thermal care, cord care</li>
  <li>Post-natal follow-up visits at 24 hours, day 7 and day 28</li>
  <li>Family planning counselling and contraceptive provision</li>
  <li>Malaria prevention, treatment and bed-net distribution</li>
  <li>Child immunisation tracking and defaulter tracing</li>
</ul>
<p>Each CHW is equipped with a standardised kit including a blood pressure cuff, foetal stethoscope, clean delivery kit, rapid diagnostic tests for malaria and a mobile phone for data entry and referral communication.</p>

<h3>Monthly Mobile Outreach Clinics</h3>
<p>A CBN mobile clinic — staffed by a midwife, a nurse and a CHW supervisor — visits each of the 30 chiefdoms once per month, providing services that reinforce the CHWs' community-level work:</p>
<ul>
  <li>Antenatal and post-natal consultations</li>
  <li>Safe delivery for women in early labour</li>
  <li>Child growth monitoring and nutrition screening</li>
  <li>Immunisation including pentavalent, measles and meningitis vaccines</li>
  <li>Family planning (pills, injectables, implants)</li>
</ul>

<h3>Emergency Referral System</h3>
<p>CBN has negotiated agreements with 12 motorbike ambulance operators and three vehicle owners in the district, who are on-call 24/7 for obstetric emergencies. A revolving fund of $8,000 subsidises emergency transport for women who cannot pay — no woman is denied transport due to cost.</p>

<h2>Early Results (Year 1, 2025)</h2>
<ul>
  <li>🤱 <strong>1,840 antenatal consultations</strong> conducted in the first year</li>
  <li>👶 <strong>312 safe deliveries</strong> attended by trained CHWs or at mobile clinics</li>
  <li>📉 Maternal deaths in covered chiefdoms: <strong>2 in 2025</strong>, compared to a projected 11 based on historical rates</li>
  <li>💉 Child immunisation coverage in Pujehun has risen from <strong>41% to 68%</strong></li>
  <li>🏍️ <strong>47 emergency referrals</strong> completed using the motorbike ambulance network</li>
</ul>

<h2>Fatmata's Testimony</h2>
<blockquote>
  "In two years we have delivered 312 babies in this chiefdom and we have had only two mothers die. Before the programme, we lost that many in one season. I know the names of every pregnant woman in my area. That is my job and I am proud of it."
  <footer>— <strong>Nurse Fatmata Koroma</strong>, Community Health Worker, Pujehun District</footer>
</blockquote>

<h2>Partners & Funding</h2>
<p>Implemented with the <strong>Ministry of Health and Sanitation (MoHS)</strong> and <strong>UN Women Sierra Leone</strong>. Funded by <strong>UNFPA</strong> and the <strong>EU Delegation</strong>. Total budget: <strong>$540,000</strong>. Secured: <strong>$340,200 (63%)</strong>.</p>""",
        ),

        # ── 7. Youth Vocational Skills Programme ────────────────────────
        dict(
            title="Youth Vocational Skills Programme",
            slug="youth-vocational-skills-programme",
            category="youth",
            district="Bo & Kenema",
            description="Free carpentry, tailoring, ICT and agri-business training for 300 out-of-school young people in Southern Sierra Leone.",
            image_url="https://images.pexels.com/photos/26855714/pexels-photo-26855714.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
            banner_url="https://images.pexels.com/photos/26855714/pexels-photo-26855714.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=700&w=1400",
            status="current",
            funded_percent=29,
            start_year=2026,
            end_year=2027,
            author="Ibrahim Sesay",
            article_content="""<h2>Sierra Leone's Youth Employment Crisis</h2>
<p>Sierra Leone has one of the youngest populations in the world — more than <strong>60%</strong> of the country is under 25. Yet youth unemployment in urban and peri-urban areas runs at an estimated <strong>70%</strong>, and many young people who are "employed" are in precarious, low-income informal work. For those who dropped out of school — often due to poverty, conflict with family, or pregnancy — formal employment is essentially inaccessible.</p>
<p>In Bo and Kenema, the two largest cities in southern Sierra Leone, CBN estimates that approximately <strong>15,000 young people aged 16–28</strong> are neither in education, employment nor training (NEET). This is not a skills problem alone — it is also a confidence problem, a network problem and an access-to-finance problem. Our programme addresses all four.</p>

<h2>The CBN Skills Hub Model</h2>
<p>The <strong>Youth Vocational Skills Programme</strong> operates through the newly opened CBN Skills Hub in Bo — a purpose-built training facility with four workshops, a computer lab, a design studio and a business development room. A second hub is under development in Kenema.</p>
<p>The programme enrolls <strong>300 young people</strong> (at least 50% women) in five six-month training tracks:</p>

<h3>Track 1: Carpentry & Joinery (60 trainees)</h3>
<p>Furniture construction, doors and window frames, roof truss assembly and basic building work. Sierra Leone's construction sector is growing at 8% annually — skilled carpenters are in high demand.</p>

<h3>Track 2: Fashion & Tailoring (80 trainees)</h3>
<p>Garment construction from pattern to finished product, both traditional Sierra Leonean styles and contemporary fashion. Graduates are supported to establish their own micro-enterprises or join established tailoring cooperatives.</p>

<h3>Track 3: ICT & Digital Skills (60 trainees)</h3>
<p>Practical computer literacy, Microsoft Office, basic web and graphic design, social media for business and mobile money operations. With smartphone penetration growing rapidly, digital skills open a wide range of service-sector jobs.</p>

<h3>Track 4: Agri-business & Food Processing (60 trainees)</h3>
<p>Value-added agricultural processing (palm oil, rice milling, vegetable drying), business management for agricultural enterprises, quality control and market access. Links directly with our Women's Farming Cooperatives programme.</p>

<h3>Track 5: Electrical Installation & Solar (40 trainees)</h3>
<p>Domestic wiring, solar panel installation and maintenance, and battery system management. As Sierra Leone expands off-grid solar access, trained electricians are acutely scarce.</p>

<h2>Beyond Technical Training</h2>
<p>Every trainee, regardless of track, receives:</p>
<ul>
  <li><strong>Business skills:</strong> Basic bookkeeping, pricing, marketing and customer relations</li>
  <li><strong>Financial literacy:</strong> Savings, mobile money, avoiding predatory lending</li>
  <li><strong>Life skills:</strong> Communication, conflict resolution, gender equality and rights</li>
  <li><strong>Starter pack:</strong> Tools or equipment relevant to their trade, valued at $150–$300</li>
  <li><strong>Business development grant:</strong> A competitive pitch process at graduation — the top 20% of each cohort receives a business start-up grant of $300</li>
  <li><strong>Alumni network:</strong> Ongoing peer support, monthly meetups and access to CBN's market-linkage contacts</li>
</ul>

<h2>Where We Are Now</h2>
<p>The programme launched in January 2026. The first cohort of 120 trainees across four tracks is currently mid-programme. The second cohort (180 trainees, including the Kenema hub) is scheduled to begin in August 2026. Funding for the first cohort is secured; <strong>additional funding is urgently needed</strong> for the Kenema expansion and the second cohort.</p>
<ul>
  <li>✅ 120 trainees enrolled in Cohort 1, Bo Skills Hub</li>
  <li>🔨 Carpentry workshop producing furniture for local NGO offices (generating training income)</li>
  <li>👗 Tailoring students have completed and sold 240 garments at Bo market</li>
  <li>💻 ICT graduates have collectively earned Le 8.4 million from freelance digital work in the first three months</li>
</ul>

<h2>Mohamed's Story</h2>
<blockquote>
  "I was selling mobile phone credit on the street for two years after I left school. I had no future. CBN gave me six months of tailoring training and a sewing machine. Now I have my own shop and I employ three of my friends from the programme. I have a future now."
  <footer>— <strong>Mohamed Kamara, 22</strong>, Tailoring Graduate, Cohort 0 Pilot, Bo</footer>
</blockquote>

<h2>Partners & Funding</h2>
<p>Implemented with the <strong>Ministry of Technical and Higher Education</strong>, <strong>National Youth Commission (NAYCOM)</strong> and the <strong>Bo City Council</strong>. Funded by <strong>UNDP Youth Employment Initiative</strong> and <strong>Mercy Corps</strong>. Total budget: <strong>$380,000</strong>. Secured: <strong>$110,200 (29%)</strong>. This is our most urgent funding gap — please consider supporting this project.</p>""",
        ),
    ]

    with get_db() as db:
        db.executemany(
            """INSERT INTO projects
               (title, slug, category, district, description,
                article_content, image_url, banner_url,
                status, funded_percent, start_year, end_year, author)
               VALUES
               (:title, :slug, :category, :district, :description,
                :article_content, :image_url, :banner_url,
                :status, :funded_percent, :start_year, :end_year, :author)""",
            projects,
        )


def _seed_blog():
    if query_one("SELECT id FROM blog_posts LIMIT 1"):
        return
    rows = [
        ("Youth Skills Programme Launches in Bo", "youth-skills-programme-bo", "field",
         "300 young Sierra Leoneans will receive vocational training in 2026.",
         "<p>Our newest flagship initiative kicked off this month at the CBN Skills Hub in Bo. "
         "Over the next six months, 120 young people will train in carpentry, tailoring, ICT "
         "and agri-business, with a second cohort of 180 starting in August.</p>"
         "<p>Every trainee also receives business skills, financial literacy and a starter "
         "tool-kit — and the top 20% of each cohort win a $300 business start-up grant.</p>",
         "Ibrahim Sesay",
         "https://images.pexels.com/photos/26855714/pexels-photo-26855714.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
         1, "2026-03-12 09:00:00"),
        ("What 24 Boreholes Really Mean for Kono", "boreholes-kono", "field",
         "Our WASH lead visits Njala village, where the new solar borehole is transforming daily life.",
         "<p>Seventeen of the twenty-four planned boreholes are now operational, bringing safe water "
         "within a five-minute walk for more than 8,500 people in Kono District.</p>"
         "<p>Reported diarrhoeal illness is down 61% year-on-year and girls' school attendance is up "
         "23% — because nobody's morning starts with a four-kilometre walk to the river any more.</p>",
         "Fatmata Bangura",
         "https://images.pexels.com/photos/19879046/pexels-photo-19879046.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
         1, "2026-03-08 09:00:00"),
        ("Why Sierra Leone Needs Locally-Led Development", "locally-led-development", "policy",
         "CBN's Executive Director makes the case for shifting funding to national NGOs.",
         "<p>Less than 2% of international humanitarian funding reaches local and national "
         "organisations directly. Yet it is local organisations that stay when the crisis "
         "headlines fade, that speak the language, and that are accountable to the community.</p>"
         "<p>Shifting decision-making power — not just sub-contracts — to Sierra Leonean NGOs is "
         "the single most effective reform donors could make.</p>",
         "Aminata Kamara",
         "https://images.pexels.com/photos/9275222/pexels-photo-9275222.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=500&w=800",
         1, "2026-03-02 09:00:00"),
    ]
    with get_db() as db:
        db.executemany(
            "INSERT INTO blog_posts "
            "(title,slug,category,excerpt,content,author,image_url,published,published_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )


def _seed_events():
    if query_one("SELECT id FROM events LIMIT 1"):
        return
    rows = [
        ("CBN Annual Fundraising Gala", "2026-04-14", "18:00",
         "Radisson Blu, Freetown",
         "An evening of storytelling, music and dinner celebrating 15 years of impact."),
        ("Kono Borehole Handover Ceremony", "2026-05-03", "10:00",
         "Njala Village, Kono",
         "Community celebration marking the completion of our 24th solar borehole."),
        ("Youth Skills Hub Open Day", "2026-05-22", "09:00",
         "CBN Skills Hub, Bo",
         "Tour the Skills Hub and meet the trainees."),
    ]
    with get_db() as db:
        db.executemany(
            "INSERT INTO events (title,event_date,event_time,location,description) VALUES (?,?,?,?,?)",
            rows,
        )


def cleanup_expired_sessions():
    """Delete expired sessions. Called occasionally to keep the table small."""
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP")


def log_audit(admin_id, action, details, ip_address):
    """Insert an entry in the audit log."""
    execute(
        "INSERT INTO audit_log (admin_id, action, details, ip_address) VALUES (?,?,?,?)",
        (admin_id, action, details, ip_address),
    )


# ------------------------------------------------------------------
# EMAIL LOG helpers
# ------------------------------------------------------------------
def email_log_create(related_table, related_id, to_address, subject, kind, triggered_by):
    """Record an email as queued; returns the log row id."""
    return execute(
        "INSERT INTO email_log "
        "(related_table, related_id, to_address, subject, kind, status, triggered_by) "
        "VALUES (?,?,?,?,?,'queued',?)",
        (related_table, related_id, to_address, subject, kind, triggered_by),
    )


def email_log_finish(log_id, ok, detail):
    """Mark a queued email as sent / console / failed with the server detail."""
    status = "failed" if not ok else ("console" if detail == "console" else "sent")
    execute(
        "UPDATE email_log SET status=?, detail=?, "
        "sent_at = CASE WHEN ?=1 THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?",
        (status, (detail or "")[:500], 1 if ok else 0, log_id),
    )


# ------------------------------------------------------------------
# OUTBOX helpers
# ------------------------------------------------------------------
def outbox_enqueue(to_address, subject, text_body, html_body=None, to_name="", kind="", email_log_id=None):
    """Queue an email for the background worker. Returns the outbox row id."""
    return execute(
        "INSERT INTO outbox (to_address,to_name,subject,text_body,html_body,kind,email_log_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (to_address, to_name or "", subject, text_body, html_body, kind, email_log_id),
    )


def outbox_claim_due(limit=10):
    """
    Atomically mark due rows as 'sending' and return them, so two workers
    (or a manual 'send now' plus the poller) never send the same email twice.
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM outbox WHERE status='pending' AND next_try_at <= CURRENT_TIMESTAMP "
            "ORDER BY id LIMIT ?", (limit,)).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            marks = ",".join("?" * len(ids))
            conn.execute(f"UPDATE outbox SET status='sending' WHERE id IN ({marks})", ids)
        return [dict(r) for r in rows]


def outbox_claim_one(row_id):
    """Atomically claim a single pending row by id. Returns the row dict or None."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM outbox WHERE id=? AND status='pending'", (row_id,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE outbox SET status='sending' WHERE id=?", (row_id,))
        return dict(row)


def outbox_mark_sent(row_id, detail):
    execute("UPDATE outbox SET status='sent', last_error=NULL, sent_at=CURRENT_TIMESTAMP, "
            "attempts=attempts+1 WHERE id=?", (row_id,))


def outbox_mark_retry(row_id, error, delay_seconds):
    """Put the row back to 'pending' with a future next_try_at (exponential back-off)."""
    execute(
        "UPDATE outbox SET status='pending', attempts=attempts+1, last_error=?, "
        "next_try_at=datetime(CURRENT_TIMESTAMP, ?) WHERE id=?",
        ((error or "")[:500], f"+{int(delay_seconds)} seconds", row_id),
    )


def outbox_mark_failed(row_id, error):
    execute("UPDATE outbox SET status='failed', attempts=attempts+1, last_error=? WHERE id=?",
            ((error or "")[:500], row_id))


def outbox_release_stuck(older_than_minutes=10):
    """If the server crashed mid-send, rows can be left as 'sending'. Re-queue them."""
    execute(
        "UPDATE outbox SET status='pending' WHERE status='sending' "
        "AND created_at < datetime(CURRENT_TIMESTAMP, ?)",
        (f"-{int(older_than_minutes)} minutes",),
    )


def outbox_retry_now(row_id=None):
    """Make failed/pending rows due immediately (all, or one)."""
    if row_id:
        execute("UPDATE outbox SET status='pending', next_try_at=CURRENT_TIMESTAMP, attempts=0 "
                "WHERE id=? AND status IN ('pending','failed')", (row_id,))
    else:
        execute("UPDATE outbox SET status='pending', next_try_at=CURRENT_TIMESTAMP, attempts=0 "
                "WHERE status IN ('pending','failed')")


def outbox_cancel(row_id):
    execute("UPDATE outbox SET status='cancelled' WHERE id=? AND status IN ('pending','failed')", (row_id,))


def outbox_summary():
    row = query_one(
        "SELECT SUM(status='pending') AS pending, SUM(status='sending') AS sending, "
        "SUM(status='failed') AS failed, SUM(status='sent') AS sent FROM outbox")
    return {k: int(row[k] or 0) for k in ("pending", "sending", "failed", "sent")} if row else \
           {"pending": 0, "sending": 0, "failed": 0, "sent": 0}


# ------------------------------------------------------------------
# APP STATE + INBOUND EMAIL helpers
# ------------------------------------------------------------------
def state_get(key, default=None):
    row = query_one("SELECT value FROM app_state WHERE key=?", (key,))
    return row["value"] if row else default


def state_set(key, value):
    execute("INSERT INTO app_state (key, value, updated_at) VALUES (?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, str(value)))


def inbound_store(messages):
    """
    Insert fetched IMAP messages, linking each to a volunteer by reference
    number (CBN-VOL-00003) or, failing that, by sender address.
    Returns the number of NEW rows stored.
    """
    new_rows = 0
    with get_db() as conn:
        for m in messages:
            if conn.execute("SELECT 1 FROM inbound_emails WHERE imap_uid=?", (m["uid"],)).fetchone():
                continue
            volunteer_id = None
            if m.get("volunteer_ref"):
                try:
                    vid = int(m["volunteer_ref"].split("-")[-1])
                    if conn.execute("SELECT 1 FROM volunteers WHERE id=?", (vid,)).fetchone():
                        volunteer_id = vid
                except ValueError:
                    pass
            if volunteer_id is None and m.get("from_addr"):
                row = conn.execute(
                    "SELECT id FROM volunteers WHERE lower(email)=? ORDER BY id DESC LIMIT 1",
                    (m["from_addr"],)).fetchone()
                if row:
                    volunteer_id = row["id"]
            conn.execute(
                "INSERT INTO inbound_emails "
                "(imap_uid,message_id,in_reply_to,from_name,from_addr,to_addr,subject,body,volunteer_id,received_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (m["uid"], m.get("message_id"), m.get("in_reply_to"), m.get("from_name"),
                 m["from_addr"], m.get("to_addr"), m.get("subject"), m.get("body"),
                 volunteer_id, m.get("received_at")),
            )
            new_rows += 1
    return new_rows


def inbound_unread_counts(volunteer_ids):
    """{volunteer_id: unread_count} for the admin volunteers table."""
    if not volunteer_ids:
        return {}
    marks = ",".join("?" * len(volunteer_ids))
    rows = query_all(
        f"SELECT volunteer_id, COUNT(*) AS c FROM inbound_emails "
        f"WHERE is_read=0 AND volunteer_id IN ({marks}) GROUP BY volunteer_id",
        tuple(volunteer_ids))
    return {r["volunteer_id"]: r["c"] for r in rows}


def latest_email_for(related_table, related_ids, kinds=None):
    """
    Return {related_id: row} of the most recent email per record (for admin tables).
    `kinds` optionally restricts to certain email kinds, e.g. the applicant-facing
    decision emails only, so office copies don't hide the applicant's delivery state.
    """
    if not related_ids:
        return {}
    marks = ",".join("?" * len(related_ids))
    params = [related_table, *related_ids]
    kind_sql = ""
    if kinds:
        kind_sql = f" AND kind IN ({','.join('?' * len(kinds))})"
        params += list(kinds)
    rows = query_all(
        f"SELECT e.* FROM email_log e "
        f"JOIN (SELECT related_id, MAX(id) AS max_id FROM email_log "
        f"      WHERE related_table=? AND related_id IN ({marks}){kind_sql} GROUP BY related_id) m "
        f"  ON m.max_id = e.id",
        params,
    )
    return {r["related_id"]: r for r in rows}
