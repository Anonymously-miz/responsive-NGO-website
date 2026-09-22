#!/usr/bin/env python3
"""
use_partials.py — one-time migration to the shared header/footer.

Replaces the inline <header class="site-header">…</header> and
<footer class="site-footer">…</footer> blocks in every public page with

    <div data-include="header"></div>      and      <div data-include="footer"></div>

which script.js fills from partials/header.html and partials/footer.html.
After this, editing the two partial files updates every page.

Run:   python3 use_partials.py
(also runs automatically from server.py on start-up; it is idempotent —
 pages that already use the placeholders are left untouched)
"""
import os
import re
import sys

# Pages live in ../frontend (project layout: backend/ + frontend/). Falls back to
# this folder for a flat checkout, and honours CBN_FRONTEND_DIR like server.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.environ.get("CBN_FRONTEND_DIR")
                       or os.path.join(os.path.dirname(_HERE), "frontend"))
if not os.path.isdir(BASE):
    BASE = _HERE
PAGES = ["index.html", "about.html", "projects.html", "get-involved.html",
         "news.html", "contact.html", "donate.html"]

HEADER_RE = re.compile(r'[ \t]*<header class="site-header">.*?</header>[ \t]*\n?', re.S)
FOOTER_RE = re.compile(r'[ \t]*<footer class="site-footer">.*?</footer>[ \t]*\n?', re.S)


def migrate(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    orig = html
    if 'data-include="header"' not in html:
        html, n = HEADER_RE.subn('  <div data-include="header"></div>\n', html, count=1)
    if 'data-include="footer"' not in html:
        html, n = FOOTER_RE.subn('  <div data-include="footer"></div>\n', html, count=1)
    if html != orig:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return True
    return False


def run(verbose=True):
    changed = []
    for name in PAGES:
        p = os.path.join(BASE, name)
        if not os.path.exists(p):
            continue
        try:
            if migrate(p):
                changed.append(name)
        except Exception as e:  # never break server start-up
            if verbose:
                print(f"  ⚠ could not migrate {name}: {e}")
    if verbose and changed:
        print(f"  Shared header/footer: migrated {', '.join(changed)}")
    return changed


if __name__ == "__main__":
    ch = run()
    print("Done." if ch else "All pages already use the shared header/footer.")
    sys.exit(0)
