/* =====================================================
   Community Builders Network - Sierra Leone
   Global JavaScript
   ===================================================== */

/* =====================================================================
   SHARED HEADER / FOOTER LOADER
   ---------------------------------------------------------------------
   Every page contains two placeholders:
       <div data-include="header"></div>   …page content…   <div data-include="footer"></div>
   This loader fetches partials/header.html and partials/footer.html,
   swaps them in, marks the current page's nav link as active, and THEN
   runs the rest of this script (which wires the menu, search, language
   buttons, forms …). Edit the partials once → every page updates.

   If the page is opened straight from disk (file://) the browser blocks
   fetch(); a minimal inline fallback header/footer is shown instead so
   the site still works — run `python3 server.py` for the full version.
   ===================================================================== */
(function loadPartials() {
  'use strict';

  const slots = document.querySelectorAll('[data-include]');
  if (!slots.length) { runSite(); return; }          // page has its own markup

  // Pages live at the site root; server-rendered pages (/blog/x, /projects/x)
  // are nested, so resolve partials against the root.
  const ROOT = document.querySelector('base') ? '' :
               (location.pathname.split('/').length > 2 && !location.pathname.endsWith('.html') ? '/' : '');
  const currentPage = (location.pathname.split('/').pop() || 'index.html').replace(/\.html$/, '') || 'index';

  function absolutise(html) {
    // Inside nested routes, make relative hrefs/srcs root-relative
    if (!ROOT) return html;
    return html.replace(/(href|src)="(?!https?:|\/|#|mailto:|tel:)([^"]+)"/g, '$1="/$2"');
  }

  function fallback(name) {
    if (name === 'header') {
            return '<header class="site-header"><nav class="main-nav"><div class="container">' +
              '<a href="/index.html" class="brand"><span class="brand-mark">CBN</span><span class="brand-text">' +
              '<span class="brand-name">Community Builders Network</span><span class="brand-tag">Sierra Leone</span></span></a>' +
              '<ul class="nav-list" style="margin-left:auto;">' +
              '<li><a href="/index.html">Home</a></li><li><a href="/about.html">About Us</a></li>' +
              '<li><a href="/projects.html">Projects</a></li><li><a href="/get-involved.html">Get Involved</a></li>' +
              '<li><a href="/news.html">News</a></li><li><a href="/contact.html">Contact</a></li>' +
              '<li><a href="/donate.html" class="nav-cta">Donate</a></li></ul></div></nav></header>';
    }
    return '<footer class="site-footer"><div class="container"><div class="footer-bottom">© ' +
           new Date().getFullYear() + ' Community Builders Network - Sierra Leone</div></div></footer>';
  }

  const jobs = Array.prototype.map.call(slots, function (slot) {
    const name = slot.getAttribute('data-include');
    const url  = ROOT + 'partials/' + name + '.html';
    return fetch(url, { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .catch(function () { return fallback(name); })
      .then(function (html) {
        const tpl = document.createElement('template');
        tpl.innerHTML = absolutise(html).trim();
        slot.replaceWith(tpl.content);
      });
  });

  Promise.all(jobs).then(function () {
    // Highlight the current page in the nav
    document.querySelectorAll('.nav-list a[data-nav]').forEach(function (a) {
      if (a.getAttribute('data-nav') === currentPage) a.classList.add('active');
    });
    runSite();
  });
})();


function runSite() {
  'use strict';
  if (window.__cbnSiteStarted) return;   // guard against double-init
  window.__cbnSiteStarted = true;

  /* ---------- Mobile menu toggle ---------- */
  const toggle  = document.querySelector('.menu-toggle');
  const navList = document.querySelector('.nav-list');

  if (toggle && navList) {
    toggle.addEventListener('click', function () {
      toggle.classList.toggle('is-active');
      navList.classList.toggle('is-open');
      const expanded = toggle.classList.contains('is-active');
      toggle.setAttribute('aria-expanded', expanded);
    });
  }

  /* ---------- Dropdown behaviour (click on mobile, hover on desktop) ---------- */
  const dropdownItems = document.querySelectorAll('.nav-list > li.has-mega > a');

  dropdownItems.forEach(function (link) {
    link.addEventListener('click', function (e) {
      // On mobile widths, hijack the click to expand the mega menu
      if (window.innerWidth <= 860) {
        e.preventDefault();
        const parent = link.parentElement;

        // Close siblings
        parent.parentElement.querySelectorAll('li.has-mega').forEach(function (li) {
          if (li !== parent) li.classList.remove('is-open');
        });
        parent.classList.toggle('is-open');
      }
    });
  });

  /* ---------- Close mobile menu when clicking a real link ---------- */
  document.querySelectorAll('.nav-list a').forEach(function (a) {
    if (a.classList.contains('has-mega')) return;
    a.addEventListener('click', function () {
      if (window.innerWidth <= 860 && !a.parentElement.classList.contains('has-mega')) {
        if (toggle) toggle.classList.remove('is-active');
        if (navList) navList.classList.remove('is-open');
      }
    });
  });

  /* ---------- Reset mobile state on resize ---------- */
  let resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (window.innerWidth > 860) {
        if (toggle)  toggle.classList.remove('is-active');
        if (navList) navList.classList.remove('is-open');
        document.querySelectorAll('.nav-list > li.is-open').forEach(function (li) {
          li.classList.remove('is-open');
        });
      }
    }, 150);
  });

  /* ============================================================
     SEARCH OVERLAY — full working site search
     ============================================================ */

  // Site-wide searchable index (page title · url · section)
  var SEARCH_INDEX = [
    // Home
    { title: 'Home', section: 'Page', url: '/index.html',
      keywords: 'home community builders network sierra leone' },
    { title: 'Donate Now', section: 'Home · Hero',  url: '/donate.html',
      keywords: 'donate donation give money support fund' },
    { title: 'Volunteer with CBN', section: 'Home · CTA', url: '/get-involved.html#volunteer',
      keywords: 'volunteer time skills help join' },
    // About
    { title: 'About Us', section: 'Page', url: '/about.html',
      keywords: 'about us who we are cbn' },
    { title: 'Mission & Vision', section: 'About Us', url: '/about.html#mission',
      keywords: 'mission vision purpose goal' },
    { title: 'Our Team', section: 'About Us', url: '/about.html#team',
      keywords: 'team staff people leadership aminata ibrahim fatmata' },
    { title: 'History & Achievements', section: 'About Us', url: '/about.html#history',
      keywords: 'history founded achievements milestones ebola' },
    { title: 'Core Values', section: 'About Us', url: '/about.html#values',
      keywords: 'values integrity compassion empowerment inclusion' },
    { title: 'Our Partners', section: 'About Us', url: '/about.html#partners',
      keywords: 'partners unicef usaid undp wateraid plan international' },
    // Projects
    { title: 'All Projects', section: 'Page', url: '/projects.html',
      keywords: 'projects work initiatives programmes' },
    { title: 'Safe Water for Kono District', section: 'Current Projects', url: '/projects/safe-water-kono-district',
      keywords: 'water borehole kono solar wash sanitation clean drinking' },
    { title: "Girls' Education Initiative", section: 'Current Projects', url: '/projects/girls-education-initiative',
      keywords: 'girls education scholarship school bombali bo secondary' },
    { title: "Women's Farming Cooperatives", section: 'Current Projects', url: '/projects/womens-farming-cooperatives',
      keywords: 'women farming cooperatives livelihoods agriculture northern province' },
    { title: 'Rebuilding Rural Primary Schools', section: 'Current Projects', url: '/projects/rebuilding-rural-primary-schools',
      keywords: 'school rebuild primary kailahun solar pupils' },
    { title: 'Maternal & Child Health Outreach', section: 'Current Projects', url: '/projects/maternal-child-health-outreach',
      keywords: 'maternal child health outreach pujehun clinic nurse midwife' },
    { title: 'Youth Vocational Skills Programme', section: 'Current Projects', url: '/projects/youth-vocational-skills-programme',
      keywords: 'youth vocational skills carpentry tailoring ict bo kenema training' },
    { title: 'Ebola Community Response', section: 'Past Projects', url: '/projects/ebola-community-response',
      keywords: 'ebola response health mobilisers outbreak nationwide 2014' },
    { title: 'Current Projects', section: 'Projects', url: '/projects.html#current',
      keywords: 'current active running projects' },
    { title: 'Past Projects', section: 'Projects', url: '/projects.html#past',
      keywords: 'past completed delivered projects' },
    // Get Involved
    { title: 'Get Involved', section: 'Page', url: '/get-involved.html',
      keywords: 'get involved volunteer donate partner join' },
    { title: 'Volunteer Opportunities', section: 'Get Involved', url: '/get-involved.html#volunteer',
      keywords: 'volunteer roles health tutor wash communications field remote' },
    { title: 'Partner with CBN', section: 'Get Involved', url: '/get-involved.html#partner',
      keywords: 'partner corporate organisation sponsorship programme' },
    { title: 'Volunteer Application Form', section: 'Get Involved', url: '/get-involved.html#signup',
      keywords: 'apply volunteer application form' },
    // News
    { title: 'News & Updates', section: 'Page', url: '/news.html',
      keywords: 'news updates blog events stories articles' },
    { title: 'Blog', section: 'News & Updates', url: '/news.html#blog',
      keywords: 'blog articles field notes policy voices research posts' },
    { title: 'Upcoming Events', section: 'News & Updates', url: '/news.html#events',
      keywords: 'events gala fundraiser open day conference ceremony 2026' },
    { title: 'Success Stories', section: 'News & Updates', url: '/news.html#stories',
      keywords: 'success stories mariama isata mohamed community impact' },
    { title: 'Newsletter Sign-up', section: 'News & Updates', url: '/news.html#newsletter',
      keywords: 'newsletter subscribe email updates' },
    // Donate
    { title: 'Donate', section: 'Page', url: '/donate.html',
      keywords: 'donate donation orange money give fund payment' },
    { title: 'Donate via Orange Money', section: 'Donate', url: '/donate.html',
      keywords: 'orange money mobile payment ussd sierra leone +232' },
    { title: 'Bank Transfer', section: 'Donate', url: '/donate.html',
      keywords: 'bank transfer slcb account sierra leone commercial bank' },
    // Contact
    { title: 'Contact Us', section: 'Page', url: '/contact.html',
      keywords: 'contact freetown wilkinson road phone email' },
    { title: 'Contact Form', section: 'Contact', url: '/contact.html',
      keywords: 'contact form message send enquiry' },
  ];

  function searchSite(query) {
    if (!query || !query.trim()) return [];
    var terms = query.toLowerCase().trim().split(/\s+/);
    var scored = SEARCH_INDEX.map(function (item) {
      var haystack = (item.title + ' ' + item.section + ' ' + item.keywords).toLowerCase();
      var score = 0;
      terms.forEach(function (t) {
        if (item.title.toLowerCase().includes(t)) score += 10;
        if (item.section.toLowerCase().includes(t)) score += 5;
        if (haystack.includes(t)) score += 2;
      });
      return { item: item, score: score };
    });
    return scored
      .filter(function (s) { return s.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, 7)
      .map(function (s) { return s.item; });
  }

  // Inject search overlay HTML once into the page
  function buildSearchOverlay() {
    if (document.getElementById('searchOverlay')) return; // already exists
    var overlay = document.createElement('div');
    overlay.id = 'searchOverlay';
    overlay.className = 'search-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', 'Site search');
    overlay.innerHTML =
      '<button class="so-close" id="soClose" aria-label="Close search">✕</button>' +
      '<div class="so-inner">' +
        '<p class="so-label">Search Community Builders Network</p>' +
        '<div class="so-field">' +
          '<input type="search" id="soInput" placeholder="e.g. water project, volunteer, donate…"' +
                 ' autocomplete="off" spellcheck="false" aria-label="Search query">' +
          '<button class="so-submit" id="soSubmit" aria-label="Search">' +
            '<svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:#fff;fill:none;stroke-width:2.5;stroke-linecap:round;">' +
              '<circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/>' +
            '</svg>' +
          '</button>' +
        '</div>' +
        '<div class="so-results" id="soResults">' +
          '<p class="so-no-results">No results found. Try a different search term.</p>' +
        '</div>' +
        '<div class="so-quick">' +
          '<span>Quick links:</span>' +
          '<a href="/projects.html">Projects</a>' +
          '<a href="/donate.html">Donate</a>' +
          '<a href="/get-involved.html#volunteer">Volunteer</a>' +
          '<a href="/news.html#events">Events</a>' +
          '<a href="/contact.html">Contact</a>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    var input    = document.getElementById('soInput');
    var results  = document.getElementById('soResults');
    var closeBtn = document.getElementById('soClose');

    function renderResults(query) {
      var hits = searchSite(query);
      // Remove old result items (keep the no-results p)
      results.querySelectorAll('.so-result-item').forEach(function (el) { el.remove(); });
      results.classList.remove('has-results', 'no-match');

      if (!query.trim()) {
        return;
      }
      if (hits.length === 0) {
        results.classList.add('has-results', 'no-match');
        return;
      }
      results.classList.add('has-results');
      var frag = document.createDocumentFragment();
      hits.forEach(function (hit) {
        var a = document.createElement('a');
        a.href = hit.url;
        a.className = 'so-result-item';
        a.innerHTML =
          '<div class="r-title">' + hit.title + '</div>' +
          '<div class="r-section">' + hit.section + '</div>';
        a.addEventListener('click', function () { closeSearch(); });
        frag.appendChild(a);
      });
      results.insertBefore(frag, results.firstChild);
    }

    // Debounced live search
    var searchTimer;
    input.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        renderResults(input.value);
      }, 180);
    });

    // Submit on Enter or button click
    function runSearch() { renderResults(input.value); }
    document.getElementById('soSubmit').addEventListener('click', runSearch);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); runSearch(); }
      if (e.key === 'Escape') { closeSearch(); }
    });

    closeBtn.addEventListener('click', closeSearch);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeSearch();
    });
  }

  function openSearch() {
    buildSearchOverlay();
    var overlay = document.getElementById('searchOverlay');
    var input   = document.getElementById('soInput');
    if (overlay) {
      overlay.classList.add('is-open');
      document.body.style.overflow = 'hidden';
      setTimeout(function () { if (input) input.focus(); }, 80);
    }
  }

  function closeSearch() {
    var overlay = document.getElementById('searchOverlay');
    if (overlay) overlay.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  // Wire search button (matches both the class and the id)
  var searchBtn = document.querySelector('.util-search-btn, #searchToggle');
  if (searchBtn) {
    searchBtn.addEventListener('click', openSearch);
  }

  // Global keyboard shortcut: Ctrl+K / Cmd+K
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      openSearch();
    }
    if (e.key === 'Escape') closeSearch();
  });

  /* ============================================================
     LANGUAGE SWITCHER — EN / KR / FR
     ============================================================
     Stores preference in localStorage. Applies a simple
     word-swap translation for Krio (KR) and French (FR).
     Full Google Translate integration hook is included.
     ============================================================ */

  // Translation dictionaries: key = English phrase, value = translated
  var TRANSLATIONS = {

    KR: { // Krio (Sierra Leone creole)
      'Building Stronger Communities, One Village at a Time.':
        'Wi de Bil Kominiti Bɛtɛ, Wan Vɪlej fɔ Wan Tɛm.',
      'Donate Now':      'Gɪv Mɔni Na',
      'Become a Volunteer': 'Kɔmɔt Na Vɔlɔntia',
      'Volunteer with CBN': 'Wok Wit CBN',
      'View All Projects':  'Luk Ɔl Di Projɛkt',
      'Read full article →': 'Rid Di Ful Atikul →',
      'Your Time Can Transform a Village.':
        'Yu Tɛm Kin Chenjam Di Vɪlej.',
      'Contact': 'Ple Kontakt',
      'Donate':  'Gɪv',
      'Home':    'Ɔm',
      'About Us': 'Ɔbawt Wi',
      'Projects': 'Projɛkt',
      'Get Involved': 'Jɔyn Wi',
      'News & Updates': 'Nius & Nyuz',
      'Safe Water for Kono District': 'Klin Wata fɔ Kono',
      "Girls' Education Initiative": 'Pikin Gyal Skul Projɛkt',
      "Women's Farming Cooperatives": 'Umon Fam Grup',
    },

    FR: { // French
      'Building Stronger Communities, One Village at a Time.':
        'Construire des Communautés plus Fortes, un Village à la Fois.',
      'Donate Now':      'Faire un Don',
      'Become a Volunteer': 'Devenir Bénévole',
      'Volunteer with CBN': 'Bénévolat avec CBN',
      'View All Projects':  'Voir tous les Projets',
      'Read full article →': 'Lire l\'article complet →',
      'Your Time Can Transform a Village.':
        'Votre Temps Peut Transformer un Village.',
      'Contact': 'Contact',
      'Donate':  'Donner',
      'Home':    'Accueil',
      'About Us': 'À Propos',
      'Projects': 'Projets',
      'Get Involved': 'S\'impliquer',
      'News & Updates': 'Actualités',
      'Safe Water for Kono District': 'Eau Potable pour le District de Kono',
      "Girls' Education Initiative": "Initiative pour l'Éducation des Filles",
      "Women's Farming Cooperatives": 'Coopératives Agricoles des Femmes',
    }
  };

  // Store original text nodes so we can restore them
  var originalTexts = new Map();
  var currentLang   = localStorage.getItem('cbn_lang') || 'EN';

  function getTextNodes(root) {
    var walker = document.createTreeWalker(
      root, NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          var p = node.parentElement;
          if (!p) return NodeFilter.FILTER_REJECT;
          var tag = p.tagName;
          // Skip script, style, input, textarea, meta
          if (/^(SCRIPT|STYLE|INPUT|TEXTAREA|META|NOSCRIPT)$/.test(tag))
            return NodeFilter.FILTER_REJECT;
          // Skip empty / whitespace-only nodes
          if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      }, false
    );
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) nodes.push(n);
    return nodes;
  }

  function applyTranslation(lang) {
    var dict = TRANSLATIONS[lang];

    // Restore originals first
    originalTexts.forEach(function (orig, node) {
      if (node.parentNode) node.nodeValue = orig;
    });

    if (lang === 'EN' || !dict) {
      // English — nothing else to do
      return;
    }

    // Build a list of text nodes to search through
    var nodes = getTextNodes(document.body);
    nodes.forEach(function (node) {
      var text = node.nodeValue;
      // Save original if first time
      if (!originalTexts.has(node)) {
        originalTexts.set(node, text);
      }
      // Try each phrase in the dictionary
      Object.keys(dict).forEach(function (phrase) {
        if (text.includes(phrase)) {
          text = text.replace(phrase, dict[phrase]);
        }
      });
      node.nodeValue = text;
    });
  }

  function setLang(lang) {
    currentLang = lang;
    localStorage.setItem('cbn_lang', lang);

    // Update button active states on ALL language buttons in page
    document.querySelectorAll('.lang-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.lang === lang);
      btn.setAttribute('aria-pressed', btn.dataset.lang === lang);
    });

    // Update the html[lang] attribute
    var names = { EN: 'en', KR: 'kri', FR: 'fr' };
    document.documentElement.lang = names[lang] || 'en';

    // Apply translations
    applyTranslation(lang);

    // Show/hide the translation info banner
    showTranslateBanner(lang);
  }

  function showTranslateBanner(lang) {
    var existing = document.getElementById('translateBanner');
    if (lang === 'EN') {
      if (existing) existing.classList.remove('show');
      return;
    }
    if (!existing) {
      existing = document.createElement('div');
      existing.id = 'translateBanner';
      existing.className = 'translate-banner';
      var langNames = { KR: 'Krio', FR: 'Français' };
      existing.innerHTML =
        '<p>🌐 Viewing in <strong>' + (langNames[lang] || lang) + '</strong>. ' +
        'Some content may not be fully translated. ' +
        '<a href="#" onclick="document.getElementById(\'translateBanner\').classList.remove(\'show\'); return false;" ' +
        'style="color:var(--cbn-gold);">Switch to English</a></p>' +
        '<button class="tb-close" id="tbClose" aria-label="Close">✕</button>';
      document.body.appendChild(existing);
      document.getElementById('tbClose').addEventListener('click', function () {
        existing.classList.remove('show');
        setLang('EN');
      });
    } else {
      // Update banner text language name
      var langNames = { KR: 'Krio', FR: 'Français' };
      var p = existing.querySelector('p');
      if (p) {
        p.innerHTML = '🌐 Viewing in <strong>' + (langNames[lang] || lang) + '</strong>. ' +
          'Some content may not be fully translated. ' +
          '<a href="#" onclick="document.getElementById(\'translateBanner\').classList.remove(\'show\'); return false;" ' +
          'style="color:var(--cbn-gold);">Switch to English</a>';
      }
    }
    // Animate in
    setTimeout(function () { existing.classList.add('show'); }, 100);
  }

  // Wire all lang buttons present in page
  function wireLangButtons() {
    document.querySelectorAll('.lang-btn').forEach(function (btn) {
      // Avoid double-wiring
      if (btn.dataset.wired) return;
      btn.dataset.wired = '1';
      btn.addEventListener('click', function () {
        setLang(btn.dataset.lang);
      });
    });
  }

  wireLangButtons();

  // Apply saved language preference on page load
  if (currentLang !== 'EN') {
    // Slight delay so page content has rendered
    setTimeout(function () { setLang(currentLang); }, 120);
  } else {
    // Still mark EN button active
    document.querySelectorAll('.lang-btn[data-lang="EN"]').forEach(function (b) {
      b.classList.add('active');
      b.setAttribute('aria-pressed', 'true');
    });
  }

  /* ---------- Animated impact counters ---------- */
  const counters = document.querySelectorAll('.impact-num[data-count]');
  if (counters.length && 'IntersectionObserver' in window) {
    const runCounter = function (el) {
      const target   = parseInt(el.dataset.count, 10);
      const suffix   = el.dataset.suffix || '';
      const duration = 1600;
      const start    = performance.now();

      const step = function (now) {
        const p = Math.min((now - start) / duration, 1);
        // ease-out cubic
        const val = Math.floor(target * (1 - Math.pow(1 - p, 3)));
        el.textContent = val.toLocaleString() + suffix;
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = target.toLocaleString() + suffix;
      };
      requestAnimationFrame(step);
    };

    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          runCounter(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.4 });

    counters.forEach(function (c) { io.observe(c); });
  }

  /* ---------- Fade-in on scroll (progressive enhancement) ---------- */
  const revealables = document.querySelectorAll('.project-card, .value-card, .team-card, .mv-card, .tl-item');
  if (revealables.length && 'IntersectionObserver' in window) {
    revealables.forEach(function (el) {
      el.style.opacity = '0';
      el.style.transform = 'translateY(18px)';
      el.style.transition = 'opacity .55s ease, transform .55s ease';
    });
    const io2 = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'none';
          io2.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    revealables.forEach(function (el) { io2.observe(el); });
  }

  /* ---------- Set current year in footer ---------- */
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---------- Category filter tabs (Projects + Blog pages) ----------
     Cards on these pages are loaded from the API *after* page load, so the
     grid is resolved lazily on every click rather than once at start-up.
     Pages can point a tab bar at its grid with data-target="<grid-id>";
     otherwise the next .projects-grid / .blog-grid sibling is used
     (skipping skeleton loaders marked aria-busy).                          */
  document.querySelectorAll('.filter-tabs').forEach(function (tabBar) {
    const buttons = tabBar.querySelectorAll('button[data-filter]');

    function resolveGrid() {
      if (tabBar.dataset.target) {
        const byId = document.getElementById(tabBar.dataset.target);
        if (byId) return byId;
      }
      let el = tabBar.nextElementSibling;
      while (el) {
        if (el.matches('.projects-grid, .blog-grid') && !el.hasAttribute('aria-busy')) return el;
        el = el.nextElementSibling;
      }
      return null;
    }

    function applyFilter(filter) {
      const grid = resolveGrid();
      if (!grid) return;
      grid.querySelectorAll('[data-category]').forEach(function (card) {
        const cats = (card.dataset.category || '').split(/\s+/);
        card.classList.toggle('is-hidden', !(filter === 'all' || cats.indexOf(filter) !== -1));
      });
    }

    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        buttons.forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        applyFilter(btn.dataset.filter);
      });
    });

    // Let dynamic loaders re-apply the current tab after injecting cards
    tabBar.applyActiveFilter = function () {
      const active = tabBar.querySelector('button.is-active');
      applyFilter(active ? active.dataset.filter : 'all');
    };
  });

  /* ---------- Keep the "Latest" card in the News mega-menu in sync ----------
     The nav on every page shows a "Latest" story card. Instead of a
     hard-coded post, pull the most recently published one from the API.
     Fails silently (keeps the static text) if the backend isn't running.  */
  (function syncLatestPostCard() {
    const cards = Array.prototype.filter.call(
      document.querySelectorAll('.mega-feature'),
      function (c) { const t = c.querySelector('.mf-tag'); return t && /latest/i.test(t.textContent); }
    );
    if (!cards.length || typeof fetch !== 'function') return;

    fetch('/api/blog', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (posts) {
        if (!posts || !posts.length) return;
        const p   = posts[0];
        const url = p.url || ('/blog/' + p.slug);
        cards.forEach(function (card) {
          const img = card.querySelector('img');
          const h5  = card.querySelector('h5');
          const par = card.querySelector('p');
          if (img) { if (p.image_url) img.src = p.image_url; img.alt = p.title; }
          if (h5) {
            h5.textContent = '';
            const a = document.createElement('a');
            a.href = url; a.textContent = p.title;
            a.style.cssText = 'color:inherit;text-decoration:none;';
            h5.appendChild(a);
          }
          if (par) par.textContent = p.excerpt || '';
          card.style.cursor = 'pointer';
          card.addEventListener('click', function (e) {
            if (e.target.closest('a')) return;   // the title link handles itself
            window.location.href = url;
          });
        });
      })
      .catch(function () { /* offline / static preview — keep placeholder text */ });
  })();

  /* ============================================================
     Backend form submission (AJAX with CSRF)
     ============================================================
     Every form uses its explicit method + action attributes as the
     transport target; here we intercept for a nicer AJAX UX with an
     inline success/error message. If JS is disabled, the browser
     falls back to a plain HTML POST to the same URL.
     ============================================================ */

  // Read the CSRF token from the cbn_csrf cookie (set by server on every HTML load)
  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)cbn_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }
  window.getCsrfToken = getCsrfToken;   // used by page-level scripts (donate, projects, news)

  // Submit any <form method="POST" action="/api/…"> via fetch
  async function submitForm(form, messageEl) {
    if (!form.checkValidity()) { form.reportValidity(); return; }

    const submitBtn = form.querySelector('button[type="submit"]');
    const originalBtnText = submitBtn ? submitBtn.textContent : '';
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Sending…'; }

    try {
      const response = await fetch(form.action, {
        method: form.method || 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRF-Token': getCsrfToken()
        },
        credentials: 'same-origin',
        body: new URLSearchParams(new FormData(form)).toString()
      });

      const data = await response.json().catch(() => ({}));

      if (response.ok && data.success) {
        // Success! Show message and reset the form
        form.reset();
        if (messageEl) {
          messageEl.textContent = '✓ ' + (data.message || 'Thank you!');
          messageEl.classList.add('show');
          messageEl.style.background = '#dcfce7';
          messageEl.style.color = '#166534';
          messageEl.style.borderLeft = '4px solid #22c55e';
          messageEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      } else {
        // Show error inline
        if (messageEl) {
          messageEl.textContent = '✗ ' + (data.message || 'Something went wrong.');
          messageEl.classList.add('show');
          messageEl.style.background = '#fee2e2';
          messageEl.style.color = '#7f1d1d';
          messageEl.style.borderLeft = '4px solid #dc2626';
        } else {
          alert(data.message || 'Something went wrong.');
        }
      }
    } catch (err) {
      // Network error
      if (messageEl) {
        messageEl.textContent = '✗ Network error. Please try again.';
        messageEl.classList.add('show');
        messageEl.style.background = '#fee2e2';
        messageEl.style.color = '#7f1d1d';
      }
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = originalBtnText; }
    }
  }

  // Wire each known form to the AJAX helper
  const volForm = document.getElementById('volunteerForm');
  if (volForm) {
    volForm.addEventListener('submit', function (e) {
      e.preventDefault();
      submitForm(volForm, document.getElementById('formMsg'));
    });
  }

  const contactForm = document.getElementById('contactForm');
  if (contactForm) {
    contactForm.addEventListener('submit', function (e) {
      e.preventDefault();
      submitForm(contactForm, document.getElementById('contactMsg'));
    });
  }

  const newsForm = document.getElementById('newsletterForm');
  if (newsForm) {
    newsForm.addEventListener('submit', function (e) {
      e.preventDefault();
      submitForm(newsForm, document.getElementById('newsMsg'));
    });
  }

  // Any additional form with class "cbn-ajax" will also be wired automatically
  document.querySelectorAll('form.cbn-ajax').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const msgEl = form.querySelector('.form-msg');
      submitForm(form, msgEl);
    });
  });

  /* ---------- Projects page: animate progress bars on scroll ---------- */
  const progressBars = document.querySelectorAll('.progress > span');
  if (progressBars.length && 'IntersectionObserver' in window) {
    // Store target and reset to 0 so it can animate in
    progressBars.forEach(function (bar) {
      bar.dataset.target = bar.style.width || '0%';
      bar.style.width = '0%';
    });
    const pio = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          const bar = entry.target;
          // slight delay for nicer effect
          setTimeout(function () {
            bar.style.width = bar.dataset.target;
          }, 120);
          pio.unobserve(bar);
        }
      });
    }, { threshold: 0.4 });
    progressBars.forEach(function (bar) { pio.observe(bar); });
  }

  // Let per-page scripts know the shared chrome is ready (they may run before us)
  document.dispatchEvent(new CustomEvent('cbn:ready'));
}
