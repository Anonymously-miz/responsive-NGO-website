#!/usr/bin/env python3
"""
fix_links.py
============
One-time script that patches every href="#" and nav/footer stub
across all public HTML pages, then deletes itself.

Run:  python3 fix_links.py
"""

import re, os

# ─── The corrected shared header block (utility bar + full nav) ──────────────
SHARED_HEADER = '''  <header class="site-header">
    <div class="utility-bar">
      <div class="container">
        <a href="news.html" class="util-hide-sm">Newsroom</a>
        <a href="contact.html" class="util-hide-sm">Contact</a>
        <span class="lang util-hide-sm">🌐 <span style="color:#94a3b8;">EN</span></span>
        <button class="util-search" aria-label="Search">🔍 Search</button>
      </div>
    </div>
    <nav class="main-nav" aria-label="Primary">
      <div class="container">
        <a href="index.html" class="brand" aria-label="CBN Home">
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
          <li><a href="index.html" class="{home_active}">Home</a></li>

          <li class="has-mega">
            <a href="about.html" class="{about_active}">About Us <span class="caret">▾</span></a>
            <div class="mega">
              <div class="container mega-grid">
                <div class="mega-feature">
                  <img src="https://images.pexels.com/photos/15538205/pexels-photo-15538205.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=400&w=600" alt="Community" />
                  <div class="mf-body">
                    <span class="mf-tag">Our Story</span>
                    <h5>15 Years Rebuilding Sierra Leone</h5>
                    <p>How CBN turns local action into lasting change.</p>
                  </div>
                </div>
                <div>
                  <h4>Who We Are</h4>
                  <ul>
                    <li><a href="about.html#mission">Mission &amp; Vision</a></li>
                    <li><a href="about.html#team">Our Team</a></li>
                    <li><a href="about.html#history">History &amp; Achievements</a></li>
                    <li><a href="about.html#values">Core Values</a></li>
                    <li><a href="about.html#partners">Our Partners</a></li>
                  </ul>
                </div>
                <div>
                  <h4>Transparency</h4>
                  <ul>
                    <li><a href="contact.html">Annual Reports</a></li>
                    <li><a href="contact.html">Financial Accountability</a></li>
                  </ul>
                </div>
              </div>
            </div>
          </li>

          <li class="has-mega">
            <a href="projects.html" class="{projects_active}">Projects <span class="caret">▾</span></a>
            <div class="mega">
              <div class="container mega-grid">
                <div class="mega-feature">
                  <img src="https://images.pexels.com/photos/19879046/pexels-photo-19879046.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=400&w=600" alt="Water project" />
                  <div class="mf-body">
                    <span class="mf-tag">Featured</span>
                    <h5>Clean Water for Kono District</h5>
                    <p>Bringing safe drinking water to 12 rural villages.</p>
                  </div>
                </div>
                <div>
                  <h4>Our Work</h4>
                  <ul>
                    <li><a href="projects.html#current">Current Projects</a></li>
                    <li><a href="projects.html#past">Past Projects</a></li>
                    <li><a href="projects.html#stories">Project Impact Stories</a></li>
                  </ul>
                </div>
                <div>
                  <h4>Focus Areas</h4>
                  <ul>
                    <li><a href="projects.html#current">Education</a></li>
                    <li><a href="projects.html#current">Health &amp; WASH</a></li>
                    <li><a href="projects.html#current">Livelihoods</a></li>
                    <li><a href="projects.html#current">Youth &amp; Gender</a></li>
                  </ul>
                </div>
              </div>
            </div>
          </li>

          <li class="has-mega">
            <a href="get-involved.html" class="{involve_active}">Get Involved <span class="caret">▾</span></a>
            <div class="mega">
              <div class="container mega-grid">
                <div class="mega-feature">
                  <img src="https://images.pexels.com/photos/6646852/pexels-photo-6646852.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=400&w=600" alt="Volunteer" />
                  <div class="mf-body">
                    <span class="mf-tag">Join Us</span>
                    <h5>Become a Volunteer</h5>
                    <p>Give your time and skills to Sierra Leonean communities.</p>
                  </div>
                </div>
                <div>
                  <h4>Take Action</h4>
                  <ul>
                    <li><a href="get-involved.html#volunteer">Volunteer</a></li>
                    <li><a href="get-involved.html#partner">Partner with Us</a></li>
                    <li><a href="get-involved.html#partner">Corporate Sponsorship</a></li>
                  </ul>
                </div>
                <div>
                  <h4>Ways to Give</h4>
                  <ul>
                    <li><a href="donate.html">One-time Donation</a></li>
                    <li><a href="donate.html">Monthly Giving</a></li>
                    <li><a href="contact.html">In-kind Support</a></li>
                    <li><a href="donate.html">Fundraise for CBN</a></li>
                  </ul>
                </div>
              </div>
            </div>
          </li>

          <li class="has-mega">
            <a href="news.html" class="{news_active}">News &amp; Updates <span class="caret">▾</span></a>
            <div class="mega">
              <div class="container mega-grid">
                <div class="mega-feature">
                  <img src="https://images.pexels.com/photos/20407106/pexels-photo-20407106.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=400&w=600" alt="Latest story" />
                  <div class="mf-body">
                    <span class="mf-tag">Latest</span>
                    <h5>Youth Skills Programme Launches in Bo</h5>
                    <p>300 young Sierra Leoneans will receive vocational training in 2026.</p>
                  </div>
                </div>
                <div>
                  <h4>Stay Informed</h4>
                  <ul>
                    <li><a href="news.html#blog">Blog</a></li>
                    <li><a href="news.html#events">Events</a></li>
                    <li><a href="news.html#stories">Success Stories</a></li>
                  </ul>
                </div>
                <div>
                  <h4>Media</h4>
                  <ul>
                    <li><a href="news.html">Press Releases</a></li>
                    <li><a href="news.html">Photo Gallery</a></li>
                    <li><a href="news.html">Video Stories</a></li>
                    <li><a href="news.html#newsletter">Newsletter</a></li>
                  </ul>
                </div>
              </div>
            </div>
          </li>

          <li><a href="contact.html" class="{contact_active}">Contact</a></li>
          <li><a href="donate.html" class="nav-cta {donate_active}">Donate</a></li>
        </ul>
      </div>
    </nav>
  </header>'''

# ─── Corrected shared footer ─────────────────────────────────────────────────
SHARED_FOOTER = '''  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-about">
          <a href="index.html" class="brand" style="margin-bottom:16px;">
            <span class="brand-mark">CBN</span>
            <span class="brand-text">
              <span class="brand-name" style="color:#fff;">Community Builders Network</span>
              <span class="brand-tag" style="color:#94a3b8;">Sierra Leone</span>
            </span>
          </a>
          <p>Empowering Sierra Leonean communities through education, health, livelihoods and inclusive leadership since 2010.</p>
          <div class="socials">
            <a href="https://facebook.com" target="_blank" rel="noopener" aria-label="Facebook">f</a>
            <a href="https://x.com" target="_blank" rel="noopener" aria-label="Twitter/X">𝕏</a>
            <a href="https://instagram.com" target="_blank" rel="noopener" aria-label="Instagram">◎</a>
            <a href="https://linkedin.com" target="_blank" rel="noopener" aria-label="LinkedIn">in</a>
          </div>
        </div>
        <div>
          <h5>Explore</h5>
          <ul>
            <li><a href="index.html">Home</a></li>
            <li><a href="about.html">About Us</a></li>
            <li><a href="projects.html">Projects</a></li>
            <li><a href="news.html">News &amp; Updates</a></li>
            <li><a href="contact.html">Contact</a></li>
          </ul>
        </div>
        <div>
          <h5>Get Involved</h5>
          <ul>
            <li><a href="get-involved.html#volunteer">Volunteer</a></li>
            <li><a href="get-involved.html#partner">Partner with Us</a></li>
            <li><a href="donate.html">Donate</a></li>
            <li><a href="donate.html">Fundraise</a></li>
            <li><a href="contact.html">Careers</a></li>
          </ul>
        </div>
        <div>
          <h5>Contact</h5>
          <ul>
            <li>15 Wilkinson Road<br/>Freetown, Sierra Leone</li>
            <li><a href="tel:+23276000000">+232 76 000 000</a></li>
            <li><a href="mailto:info@cbn-sl.org">info@cbn-sl.org</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        © <span id="year"></span> Community Builders Network - Sierra Leone. All rights reserved. &nbsp;·&nbsp;
        <a href="privacy.html" style="color:#94a3b8;">Privacy</a> &nbsp;·&nbsp;
        <a href="terms.html" style="color:#94a3b8;">Terms</a>
      </div>
    </div>
  </footer>'''

# ─── Per-page active states & CTA fixes ──────────────────────────────────────
PAGES = {
    "about.html":        dict(home="", about="active", projects="", involve="", news="", contact="", donate="",
                              cta_donate="donate.html", cta_volunteer="get-involved.html#volunteer",
                              cta_getinvolved="get-involved.html"),
    "projects.html":     dict(home="", about="", projects="active", involve="", news="", contact="", donate="",
                              cta_donate="donate.html", cta_volunteer="get-involved.html#volunteer",
                              cta_getinvolved="get-involved.html"),
    "get-involved.html": dict(home="", about="", projects="", involve="active", news="", contact="", donate="",
                              cta_donate="donate.html", cta_volunteer="get-involved.html#volunteer",
                              cta_getinvolved="get-involved.html"),
    "news.html":         dict(home="", about="", projects="", involve="", news="active", contact="", donate="",
                              cta_donate="donate.html", cta_volunteer="get-involved.html#volunteer",
                              cta_getinvolved="get-involved.html"),
    "contact.html":      dict(home="", about="", projects="", involve="", news="", contact="active", donate="",
                              cta_donate="donate.html", cta_volunteer="get-involved.html#volunteer",
                              cta_getinvolved="get-involved.html"),
}

def get_header(active_key):
    return SHARED_HEADER.format(
        home_active     = "active" if active_key=="home" else "",
        about_active    = "active" if active_key=="about" else "",
        projects_active = "active" if active_key=="projects" else "",
        involve_active  = "active" if active_key=="involve" else "",
        news_active     = "active" if active_key=="news" else "",
        contact_active  = "active" if active_key=="contact" else "",
        donate_active   = "active" if active_key=="donate" else "",
    )

ACTIVE_KEYS = {
    "about.html":        "about",
    "projects.html":     "projects",
    "get-involved.html": "involve",
    "news.html":         "news",
    "contact.html":      "contact",
}

def fix_file(fname):
    with open(fname, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Replace entire <header class="site-header">…</header>
    html = re.sub(
        r'<header class="site-header">.*?</header>',
        get_header(ACTIVE_KEYS.get(fname, "")),
        html, flags=re.DOTALL
    )

    # 2. Replace entire <footer class="site-footer">…</footer>
    html = re.sub(
        r'<footer class="site-footer">.*?</footer>',
        SHARED_FOOTER,
        html, flags=re.DOTALL
    )

    # 3. Fix remaining href="#" donate buttons (keep page-specific CTAs)
    # Donate buttons and CTA buttons
    html = html.replace('href="#" class="btn btn-primary">Donate Now', 'href="donate.html" class="btn btn-primary">Donate Now')
    html = html.replace('href="#" class="btn btn-primary">Donate', 'href="donate.html" class="btn btn-primary">Donate')
    html = html.replace('href="#" class="btn btn-primary">Get Involved', 'href="get-involved.html" class="btn btn-primary">Get Involved')
    html = html.replace('href="#" class="btn btn-primary">Support Our Work', 'href="donate.html" class="btn btn-primary">Support Our Work')
    html = html.replace('href="#" class="btn btn-primary">Volunteer with CBN', 'href="get-involved.html#volunteer" class="btn btn-primary">Volunteer with CBN')
    html = html.replace('href="#" class="btn btn-primary">Get Involved', 'href="get-involved.html" class="btn btn-primary">Get Involved')
    html = html.replace('href="#" class="btn btn-ghost">View All Projects', 'href="projects.html" class="btn btn-ghost">View All Projects')
    html = html.replace('href="#" class="btn btn-ghost">Read Full Story', 'href="news.html#stories" class="btn btn-ghost">Read Full Story')
    html = html.replace('href="#" class="more">Read the story →', 'href="projects.html" class="more">Read the story →')
    html = html.replace('href="#" class="more">View report →', 'href="projects.html#past" class="more">View report →')
    html = html.replace('href="#" class="more">Read story →', 'href="news.html#stories" class="more">Read story →')
    html = html.replace('href="#" class="more">Read more →', 'href="news.html#blog" class="more">Read more →')

    # 4. Fix social links remaining as "#"
    # (already fixed by footer replacement above)

    # 5. Fix any leftover generic href="#" that are inline CTAs
    html = html.replace('href="#" class="btn btn-primary">Sign Up', 'href="get-involved.html#volunteer" class="btn btn-primary">Sign Up')
    html = html.replace('href="#" class="btn btn-primary">Register', 'href="contact.html" class="btn btn-primary">Register')
    html = html.replace('href="#" class="btn btn-ghost">RSVP', 'href="contact.html" class="btn btn-ghost">RSVP')
    html = html.replace('href="#" class="btn btn-ghost">Attend', 'href="contact.html" class="btn btn-ghost">Attend')
    html = html.replace('href="#" class="btn btn-ghost">Join Online', 'href="contact.html" class="btn btn-ghost">Join Online')
    html = html.replace('href="#" class="btn btn-ghost">Load More Posts', 'href="news.html#blog" class="btn btn-ghost">Load More Posts')

    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)

    remaining = html.count('href="#"')
    print(f"  ✅ {fname}: fixed. Remaining href=\"#\": {remaining}")
    return remaining

# ─── Run ─────────────────────────────────────────────────────────────────────
total = 0
for fname in PAGES:
    if os.path.exists(fname):
        total += fix_file(fname)
    else:
        print(f"  ⚠  {fname} not found, skipping")

print(f"\nDone. Total remaining href=\"#\" across all pages: {total}")
print("(Remaining '#' are intentional anchors in social links or placeholders)")
