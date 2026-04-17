#!/usr/bin/env python3
"""
send_notify.py — Send today's Morning Edition via GOV.UK Notify.

GOV.UK Notify is the official UK government email service, free for
government users. Sign up with your government email address at:
  https://www.notifications.service.gov.uk/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ONE-TIME SETUP (do this once in the Notify dashboard)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Sign in at https://www.notifications.service.gov.uk/
2. Create a new service (e.g. "Morning Edition")
3. Go to Templates → Add new template → Email
4. Paste the template text printed by --print-template below
5. Note the template ID from the URL
   e.g. /services/.../templates/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
6. Go to Settings → API keys → Create API key
7. Add these four secrets to your GitHub repo
   (Settings → Secrets and variables → Actions → New repository secret):

     NOTIFY_API_KEY        your Notify API key
     NOTIFY_TEMPLATE_ID    the template ID from step 5
     EMAIL_TO              comma-separated recipient addresses

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run  python scripts/send_notify.py --print-template  to print the
template text ready to paste into the Notify dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE  = ROOT / "data" / "sample_events.json"
ISSUES_DIR = ROOT / "issues"

# ──────────────────────────────────────────────────────────────────────────────
# Notify email template
# Copy this text exactly into the Notify template editor.
# ──────────────────────────────────────────────────────────────────────────────

TEMPLATE = """\
# Morning Edition — ((date))

((count)) conference((plural)) worth your attention this morning.

---

((conference_list))

---

Read the full digest — ((digest_url))

Read the full magazine — ((magazine_url))

---

Morning Edition · AI harm · safety · security · policy\
"""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def build_conference_list(events: list[dict]) -> str:
    lines = []
    for i, c in enumerate(events[:10], start=1):
        verdict = c.get("applies", "")
        tag     = c.get("tag", "")
        lines.append(
            f"{i:02d}. {c['title']}\n"
            f"{verdict} · {tag}\n"
            f"{c['date']} · {c['location']} · {c['host']}\n"
            f"\n"
            f"{c['why']}\n"
            f"\n"
            f"Watch: {c['watch']}\n"
            f"\n"
            f"{c['source']}"
        )
    return "\n\n---\n\n".join(lines)


def page_url(issue_date: str, suffix: str = "") -> str:
    base = os.environ.get("MORNING_EDITION_PAGES_URL", "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo:
            owner, name = repo.split("/", 1)
            base = f"https://{owner}.github.io/{name}"
    filename = f"{issue_date}{suffix}.html"
    return f"{base}/issues/{filename}" if base else f"./issues/{filename}"


# ──────────────────────────────────────────────────────────────────────────────
# Send
# ──────────────────────────────────────────────────────────────────────────────

def send(events: list[dict], issue_date: str) -> None:
    try:
        from notifications_python_client.notifications import NotificationsAPIClient
    except ImportError:
        print("ERROR: notifications-python-client is not installed.")
        print("       Run: pip install notifications-python-client")
        sys.exit(1)

    missing = [v for v in ("NOTIFY_API_KEY", "NOTIFY_TEMPLATE_ID", "EMAIL_TO")
               if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "See the script docstring for setup instructions."
        )

    api_key     = os.environ["NOTIFY_API_KEY"]
    template_id = os.environ["NOTIFY_TEMPLATE_ID"]
    recipients  = [a.strip() for a in os.environ["EMAIL_TO"].split(",") if a.strip()]

    if not recipients:
        raise ValueError("EMAIL_TO contains no valid addresses")

    n = len(events[:10])
    personalisation = {
        "date":             datetime.strptime(issue_date, "%Y-%m-%d").strftime("%-d %B %Y"),
        "count":            str(n),
        "plural":           "" if n == 1 else "s",
        "conference_list":  build_conference_list(events),
        "digest_url":       page_url(issue_date, "-digest"),
        "magazine_url":     page_url(issue_date),
    }

    client = NotificationsAPIClient(api_key)
    sent = 0
    for address in recipients:
        client.send_email_notification(
            email_address=address,
            template_id=template_id,
            personalisation=personalisation,
        )
        sent += 1
        print(f"  → {address}")

    print(f"Sent '{issue_date}' edition to {sent} recipient(s) via GOV.UK Notify")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--print-template",
        action="store_true",
        help="Print the Notify template text and exit (paste this into the dashboard)",
    )
    args = parser.parse_args()

    if args.print_template:
        print("─" * 60)
        print("Paste this text into your GOV.UK Notify email template:")
        print("─" * 60)
        print(TEMPLATE)
        print("─" * 60)
        return

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing data file: {DATA_FILE}")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)

    if not events:
        print("No events in data file — skipping send.")
        return

    issue_date = datetime.now().strftime("%Y-%m-%d")
    send(events, issue_date)


if __name__ == "__main__":
    main()
