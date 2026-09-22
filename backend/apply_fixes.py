#!/usr/bin/env python3
"""
apply_fixes.py — run with: python3 apply_fixes.py
Fixes ALL remaining href="#" across projects.html, get-involved.html,
news.html, contact.html by doing bulk string replacements.
"""
import os

# Each entry: (file, list of (old_str, new_str))
FIXES = {

"projects.html": [
  ('<a href="#" class="util-hide-sm">Newsroom</a>', '<a href="news.html" class="util-hide-sm">Newsroom</a>'),
  ('<a href="#" class="util-hide-sm">Careers</a>',  '<a href="contact.html" class="util-hide-sm">Careers</a>'),
  ('<span class="lang util-hide-sm">🌐 <a href="#">EN</a> / <a href="#">FR</a></span>',
   '<span class="lang util-hide-sm">🌐 <span style="color:#94a3b8;">EN</span></span>'),
  ('"#">Annual Reports',    '"contact.html">Annual Reports'),
  ('"#">Financial Accountability', '"contact.html">Financial Accountability'),
  ('<a href="#">Current Projects</a>', '<a href="projects.html#current">Current Projects</a>'),
  ('<a href="#">Past Projects</a>',    '<a href="projects.html#past">Past Projects</a>'),
  ('<a href="#">Project Impact Stories</a>', '<a href="projects.html#stories">Project Impact Stories</a>'),
  ('<a href="#">Education</a>',    '<a href="projects.html#current">Education</a>'),
  ('<a href="#">Health &amp; WASH</a>', '<a href="projects.html#current">Health &amp; WASH</a>'),
  ('<a href="#">Livelihoods</a>',  '<a href="projects.html#current">Livelihoods</a>'),
  ('<a href="#">Youth &amp; Gender</a>', '<a href="projects.html#current">Youth &amp; Gender</a>'),
  ('"#">Volunteer</a>\n                    <li><a href="#">Partner with Us</a>',
   '"get-involved.html#volunteer">Volunteer</a>\n                    <li><a href="get-involved.html#partner">Partner with Us</a>'),
  ('<a href="#">Corporate Sponsorship</a>', '<a href="get-involved.html#partner">Corporate Sponsorship</a>'),
  ('<a href="#">One-time Donation</a>',   '<a href="donate.html">One-time Donation</a>'),
  ('<a href="#">Monthly Giving</a>',      '<a href="donate.html">Monthly Giving</a>'),
  ('<a href="#">In-kind Support</a>',     '<a href="contact.html">In-kind Support</a>'),
  ('<a href="#">Fundraise for CBN</a>',   '<a href="donate.html">Fundraise for CBN</a>'),
  ('<a href="#">Blog</a>',                '<a href="news.html#blog">Blog</a>'),
  ('<a href="#">Events</a>',              '<a href="news.html#events">Events</a>'),
  ('<a href="#">Success Stories</a>',     '<a href="news.html#stories">Success Stories</a>'),
  ('<a href="#">Press Releases</a>',      '<a href="news.html">Press Releases</a>'),
  ('<a href="#">Photo Gallery</a>',       '<a href="news.html">Photo Gallery</a>'),
  ('<a href="#">Video Stories</a>',       '<a href="news.html">Video Stories</a>'),
  ('<a href="#">Newsletter</a>',          '<a href="news.html#newsletter">Newsletter</a>'),
  ('<li><a href="#" class="nav-cta">Donate</a></li>', '<li><a href="donate.html" class="nav-cta">Donate</a></li>'),
  ('"#" class="btn btn-primary">Support Our Work', '"donate.html" class="btn btn-primary">Support Our Work'),
  ('<a href="#" aria-label="Facebook">f</a>',  '<a href="https://facebook.com" target="_blank" rel="noopener" aria-label="Facebook">f</a>'),
  ('<a href="#" aria-label="Twitter/X">𝕏</a>', '<a href="https://x.com" target="_blank" rel="noopener" aria-label="Twitter/X">𝕏</a>'),
  ('<a href="#" aria-label="Instagram">◎</a>', '<a href="https://instagram.com" target="_blank" rel="noopener" aria-label="Instagram">◎</a>'),
  ('<a href="#" aria-label="LinkedIn">in</a>',  '<a href="https://linkedin.com" target="_blank" rel="noopener" aria-label="LinkedIn">in</a>'),
  ('<li><a href="#">Projects</a></li>',          '<li><a href="projects.html">Projects</a></li>'),
  ('<li><a href="#">News &amp; Updates</a></li>','<li><a href="news.html">News &amp; Updates</a></li>'),
  ('<li><a href="#">Volunteer</a></li>',         '<li><a href="get-involved.html#volunteer">Volunteer</a></li>'),
  ('<li><a href="#">Partner with Us</a></li>',   '<li><a href="get-involved.html#partner">Partner with Us</a></li>'),
  ('<li><a href="#">Donate</a></li>',            '<li><a href="donate.html">Donate</a></li>'),
  ('<li><a href="#">Fundraise</a></li>',         '<li><a href="donate.html">Fundraise</a></li>'),
  ('<li><a href="#">Careers</a></li>',           '<li><a href="contact.html">Careers</a></li>'),
  ('"#" style="color:#94a3b8;">Privacy',  '"privacy.html" style="color:#94a3b8;">Privacy'),
  ('"#" style="color:#94a3b8;">Terms',    '"terms.html" style="color:#94a3b8;">Terms'),
  ('+232 76 000 000</li>', '<a href="tel:+23276000000">+232 76 000 000</a></li>'),
  # Projects page Get Involved mega nav link
  ('<a href="#">Get Involved <span class="caret">▾</span></a>', '<a href="get-involved.html">Get Involved <span class="caret">▾</span></a>'),
  ('<a href="#">News &amp; Updates <span class="caret">▾</span></a>', '<a href="news.html">News &amp; Updates <span class="caret">▾</span></a>'),
  ('<a href="#">Projects <span class="caret">▾</span></a>', '<a href="projects.html">Projects <span class="caret">▾</span></a>'),
],

"get-involved.html": [
  ('<a href="#" class="util-hide-sm">Newsroom</a>', '<a href="news.html" class="util-hide-sm">Newsroom</a>'),
  ('<a href="#" class="util-hide-sm">Careers</a>',  '<a href="contact.html" class="util-hide-sm">Careers</a>'),
  ('<span class="lang util-hide-sm">🌐 <a href="#">EN</a> / <a href="#">FR</a></span>',
   '<span class="lang util-hide-sm">🌐 <span style="color:#94a3b8;">EN</span></span>'),
  ('"#">Annual Reports',    '"contact.html">Annual Reports'),
  ('"#">Financial Accountability', '"contact.html">Financial Accountability'),
  ('<a href="#">Current Projects</a>', '<a href="projects.html#current">Current Projects</a>'),
  ('<a href="#">Past Projects</a>',    '<a href="projects.html#past">Past Projects</a>'),
  ('<a href="#">Project Impact Stories</a>', '<a href="projects.html#stories">Project Impact Stories</a>'),
  ('<a href="#">Education</a>',    '<a href="projects.html#current">Education</a>'),
  ('<a href="#">Health &amp; WASH</a>', '<a href="projects.html#current">Health &amp; WASH</a>'),
  ('<a href="#">Livelihoods</a>',  '<a href="projects.html#current">Livelihoods</a>'),
  ('<a href="#">Youth &amp; Gender</a>', '<a href="projects.html#current">Youth &amp; Gender</a>'),
  ('<a href="#">Corporate Sponsorship</a>', '<a href="get-involved.html#partner">Corporate Sponsorship</a>'),
  ('<a href="#">One-time Donation</a>',   '<a href="donate.html">One-time Donation</a>'),
  ('<a href="#">Monthly Giving</a>',      '<a href="donate.html">Monthly Giving</a>'),
  ('<a href="#">In-kind Support</a>',     '<a href="contact.html">In-kind Support</a>'),
  ('<a href="#">Fundraise for CBN</a>',   '<a href="donate.html">Fundraise for CBN</a>'),
  ('<a href="#">Blog</a>',                '<a href="news.html#blog">Blog</a>'),
  ('<a href="#">Events</a>',              '<a href="news.html#events">Events</a>'),
  ('<a href="#">Success Stories</a>',     '<a href="news.html#stories">Success Stories</a>'),
  ('<a href="#">Press Releases</a>',      '<a href="news.html">Press Releases</a>'),
  ('<a href="#">Photo Gallery</a>',       '<a href="news.html">Photo Gallery</a>'),
  ('<a href="#">Video Stories</a>',       '<a href="news.html">Video Stories</a>'),
  ('<a href="#">Newsletter</a>',          '<a href="news.html#newsletter">Newsletter</a>'),
  ('<li><a href="#" class="nav-cta">Donate</a></li>', '<li><a href="donate.html" class="nav-cta">Donate</a></li>'),
  ('"#" class="btn btn-primary">Donate Now',  '"donate.html" class="btn btn-primary">Donate Now'),
  ('<a href="#" aria-label="Facebook">f</a>',  '<a href="https://facebook.com" target="_blank" rel="noopener" aria-label="Facebook">f</a>'),
  ('<a href="#" aria-label="Twitter/X">𝕏</a>', '<a href="https://x.com" target="_blank" rel="noopener" aria-label="Twitter/X">𝕏</a>'),
  ('<a href="#" aria-label="Instagram">◎</a>', '<a href="https://instagram.com" target="_blank" rel="noopener" aria-label="Instagram">◎</a>'),
  ('<a href="#" aria-label="LinkedIn">in</a>',  '<a href="https://linkedin.com" target="_blank" rel="noopener" aria-label="LinkedIn">in</a>'),
  ('<li><a href="#">Donate</a></li>',  '<li><a href="donate.html">Donate</a></li>'),
  ('<li><a href="#">Fundraise</a></li>', '<li><a href="donate.html">Fundraise</a></li>'),
  ('<li><a href="#">Careers</a></li>',  '<li><a href="contact.html">Careers</a></li>'),
  ('"#" style="color:#94a3b8;">Privacy', '"privacy.html" style="color:#94a3b8;">Privacy'),
  ('"#" style="color:#94a3b8;">Terms',   '"terms.html" style="color:#94a3b8;">Terms'),
  ('+232 76 000 000</li>', '<a href="tel:+23276000000">+232 76 000 000</a></li>'),
  ('<a href="#">Projects <span class="caret">▾</span></a>', '<a href="projects.html">Projects <span class="caret">▾</span></a>'),
  ('<a href="#">News &amp; Updates <span class="caret">▾</span></a>', '<a href="news.html">News &amp; Updates <span class="caret">▾</span></a>'),
],

"news.html": [
  ('<a href="#" class="util-hide-sm">Newsroom</a>', '<a href="news.html" class="util-hide-sm">Newsroom</a>'),
  ('<a href="#" class="util-hide-sm">Careers</a>',  '<a href="contact.html" class="util-hide-sm">Careers</a>'),
  ('<span class="lang util-hide-sm">🌐 <a href="#">EN</a> / <a href="#">FR</a></span>',
   '<span class="lang util-hide-sm">🌐 <span style="color:#94a3b8;">EN</span></span>'),
  ('"#">Annual Reports',    '"contact.html">Annual Reports'),
  ('"#">Financial Accountability', '"contact.html">Financial Accountability'),
  ('<a href="#">Current Projects</a>', '<a href="projects.html#current">Current Projects</a>'),
  ('<a href="#">Past Projects</a>',    '<a href="projects.html#past">Past Projects</a>'),
  ('<a href="#">Project Impact Stories</a>', '<a href="projects.html#stories">Project Impact Stories</a>'),
  ('<a href="#">Education</a>',    '<a href="projects.html#current">Education</a>'),
  ('<a href="#">Health &amp; WASH</a>', '<a href="projects.html#current">Health &amp; WASH</a>'),
  ('<a href="#">Livelihoods</a>',  '<a href="projects.html#current">Livelihoods</a>'),
  ('<a href="#">Youth &amp; Gender</a>', '<a href="projects.html#current">Youth &amp; Gender</a>'),
  ('<a href="#">Corporate Sponsorship</a>', '<a href="get-involved.html#partner">Corporate Sponsorship</a>'),
  ('<a href="#">One-time Donation</a>',   '<a href="donate.html">One-time Donation</a>'),
  ('<a href="#">Monthly Giving</a>',      '<a href="donate.html">Monthly Giving</a>'),
  ('<a href="#">In-kind Support</a>',     '<a href="contact.html">In-kind Support</a>'),
  ('<a href="#">Fundraise for CBN</a>',   '<a href="donate.html">Fundraise for CBN</a>'),
  ('<a href="#">Press Releases</a>',      '<a href="news.html">Press Releases</a>'),
  ('<a href="#">Photo Gallery</a>',       '<a href="news.html">Photo Gallery</a>'),
  ('<a href="#">Video Stories</a>',       '<a href="news.html">Video Stories</a>'),
  ('<li><a href="#" class="nav-cta">Donate</a></li>', '<li><a href="donate.html" class="nav-cta">Donate</a></li>'),
  ('<a href="#" aria-label="Facebook">f</a>',  '<a href="https://facebook.com" target="_blank" rel="noopener" aria-label="Facebook">f</a>'),
  ('<a href="#" aria-label="Twitter/X">𝕏</a>', '<a href="https://x.com" target="_blank" rel="noopener" aria-label="Twitter/X">𝕏</a>'),
  ('<a href="#" aria-label="Instagram">◎</a>', '<a href="https://instagram.com" target="_blank" rel="noopener" aria-label="Instagram">◎</a>'),
  ('<a href="#" aria-label="LinkedIn">in</a>',  '<a href="https://linkedin.com" target="_blank" rel="noopener" aria-label="LinkedIn">in</a>'),
  ('<li><a href="#">Donate</a></li>',  '<li><a href="donate.html">Donate</a></li>'),
  ('<li><a href="#">Fundraise</a></li>', '<li><a href="donate.html">Fundraise</a></li>'),
  ('<li><a href="#">Careers</a></li>',  '<li><a href="contact.html">Careers</a></li>'),
  ('"#" style="color:#94a3b8;">Privacy', '"privacy.html" style="color:#94a3b8;">Privacy'),
  ('"#" style="color:#94a3b8;">Terms',   '"terms.html" style="color:#94a3b8;">Terms'),
  ('+232 76 000 000</li>', '<a href="tel:+23276000000">+232 76 000 000</a></li>'),
  ('<a href="#">Projects <span class="caret">▾</span></a>', '<a href="projects.html">Projects <span class="caret">▾</span></a>'),
  ('<a href="#">Get Involved <span class="caret">▾</span></a>', '<a href="get-involved.html">Get Involved <span class="caret">▾</span></a>'),
  # News page story/blog link stubs
  ('"#" class="btn btn-ghost">Read Full Article', '"news.html#blog" class="btn btn-ghost">Read Full Article'),
  ('"#" class="btn btn-ghost">Load More Posts', '"news.html#blog" class="btn btn-ghost">Load More Posts'),
  ('"#" class="btn btn-primary">Register', '"contact.html" class="btn btn-primary">Register'),
  ('"#" class="btn btn-ghost">RSVP',  '"contact.html" class="btn btn-ghost">RSVP'),
  ('"#" class="btn btn-ghost">Join Online', '"contact.html" class="btn btn-ghost">Join Online'),
  ('"#" class="btn btn-primary">Sign Up', '"get-involved.html#volunteer" class="btn btn-primary">Sign Up'),
  ('class="more">Read more →</a>', 'class="more">Read more →</a>'),  # no change needed - already linked
  ('href="#" class="more">Read story →', 'href="news.html#stories" class="more">Read story →'),
],

"contact.html": [
  ('<a href="#" class="util-hide-sm">Newsroom</a>', '<a href="news.html" class="util-hide-sm">Newsroom</a>'),
  ('<a href="#" class="util-hide-sm">Careers</a>',  '<a href="contact.html" class="util-hide-sm">Careers</a>'),
  ('<span class="lang util-hide-sm">🌐 <a href="#">EN</a> / <a href="#">FR</a></span>',
   '<span class="lang util-hide-sm">🌐 <span style="color:#94a3b8;">EN</span></span>'),
  ('<li><a href="#" class="nav-cta">Donate</a></li>', '<li><a href="donate.html" class="nav-cta">Donate</a></li>'),
  ('<a href="#" aria-label="Facebook">f</a>',  '<a href="https://facebook.com" target="_blank" rel="noopener" aria-label="Facebook">f</a>'),
  ('<a href="#" aria-label="Twitter/X">𝕏</a>', '<a href="https://x.com" target="_blank" rel="noopener" aria-label="Twitter/X">𝕏</a>'),
  ('<a href="#" aria-label="Instagram">◎</a>', '<a href="https://instagram.com" target="_blank" rel="noopener" aria-label="Instagram">◎</a>'),
  ('<a href="#" aria-label="LinkedIn">in</a>',  '<a href="https://linkedin.com" target="_blank" rel="noopener" aria-label="LinkedIn">in</a>'),
  ('<li><a href="#">Donate</a></li>',  '<li><a href="donate.html">Donate</a></li>'),
  ('<li><a href="#">Fundraise</a></li>', '<li><a href="donate.html">Fundraise</a></li>'),
  ('"#" style="color:#94a3b8;">Privacy', '"privacy.html" style="color:#94a3b8;">Privacy'),
  ('"#" style="color:#94a3b8;">Terms',   '"terms.html" style="color:#94a3b8;">Terms'),
  ('+232 76 000 000</li>', '<a href="tel:+23276000000">+232 76 000 000</a></li>'),
],

}

for fname, replacements in FIXES.items():
    if not os.path.exists(fname):
        print(f"SKIP: {fname} not found")
        continue
    with open(fname, "r", encoding="utf-8") as f:
        content = f.read()
    count = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            count += 1
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    remaining = content.count('href="#"')
    print(f"OK  {fname}: applied {count} fixes | remaining href=\"#\": {remaining}")

print("\nAll done. Run: python3 server.py")
