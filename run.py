#!/usr/bin/env python3
"""
run.py — start the CBN website from the project root.

    python3 run.py                 # same as:  cd backend && python3 server.py
    python3 run.py --test          # run the security test-suite instead
    python3 run.py --restructure   # move a flat checkout into frontend/ + backend/

Layout:
    project/
    ├── backend/    server.py, database.py, security.py, admin_ui.py, mailer.py,
    │               monime.py, use_partials.py, security_test.py,
    │               cbn.db, email.env, monime.env, *.env.example
    ├── frontend/   *.html, styles.css, script.js, partials/header.html, partials/footer.html
    ├── run.py      ← you are here
    └── README.md
"""
import os
import runpy
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")


def main():
    args = sys.argv[1:]

    if "--restructure" in args or not os.path.isdir(BACKEND):
        if not os.path.exists(os.path.join(ROOT, "restructure.py")):
            sys.exit("backend/ folder not found and restructure.py is missing.")
        print("Project is not yet split into frontend/ and backend/ — running restructure.py …\n")
        subprocess.check_call([sys.executable, os.path.join(ROOT, "restructure.py")])
        if "--restructure" in args:
            return

    if not os.path.isdir(FRONTEND):
        sys.exit("frontend/ folder not found — run:  python3 restructure.py")

    os.chdir(BACKEND)                    # server.py resolves cbn.db / *.env next to itself
    sys.path.insert(0, BACKEND)
    os.environ.setdefault("CBN_FRONTEND_DIR", FRONTEND)

    target = "security_test.py" if "--test" in args else "server.py"
    sys.argv = [os.path.join(BACKEND, target)] + [a for a in args if a not in ("--test",)]
    runpy.run_path(os.path.join(BACKEND, target), run_name="__main__")


if __name__ == "__main__":
    main()
