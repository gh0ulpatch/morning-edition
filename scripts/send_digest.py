#!/usr/bin/env python3
"""
send_digest.py — Send today's Morning Edition digest email via SMTP.

Uses Python stdlib only (smtplib, ssl, email) — no extra dependencies.

Required GitHub Actions secrets (set in repo Settings → Secrets):
  SMTP_HOST       SMTP server hostname
                  e.g. smtp.sendgrid.net · smtp.gmail.com · smtp.mailgun.org
  SMTP_USER       SMTP username
                  SendGrid: literally the string "apikey"
                  Gmail:    your full Gmail address
                  Mailgun:  "postmaster@mg.yourdomain.com"
  SMTP_PASSWORD   SMTP password / API key / app password
  EMAIL_FROM      Sender address shown to recipients
                  e.g. "Morning Edition <newsletter@yourdomain.com>"
  EMAIL_TO        Comma-separated recipient addresses
                  e.g. "alice@example.com, bob@example.com"

Optional secrets:
  SMTP_PORT       Default: 587 (STARTTLS). Use 465 for implicit SSL.
  EMAIL_SUBJECT   Override the default subject line.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # ── Required ──────────────────────────────────────────────────────────────
    missing = [v for v in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO") if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASSWORD"]
    from_addr = os.environ["EMAIL_FROM"]
    to_addrs  = [a.strip() for a in os.environ["EMAIL_TO"].split(",") if a.strip()]

    if not to_addrs:
        raise ValueError("EMAIL_TO contains no valid addresses")

    # ── Load digest ───────────────────────────────────────────────────────────
    issue_date  = datetime.now().strftime("%Y-%m-%d")
    digest_file = ROOT / "issues" / f"{issue_date}-digest.html"

    if not digest_file.exists():
        raise FileNotFoundError(
            f"Digest not found: {digest_file}\n"
            "Run generate_morning_edition.py first."
        )

    html_body = digest_file.read_text(encoding="utf-8")

    # ── Build message ─────────────────────────────────────────────────────────
    subject = os.environ.get("EMAIL_SUBJECT", f"Morning Edition · {issue_date}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(to_addrs)
    # Plain-text fallback for clients that strip HTML
    msg.set_content(
        f"Morning Edition · {issue_date}\n\n"
        "This email is best viewed in an HTML-capable client.\n\n"
        "AI harm · safety · security · policy"
    )
    msg.add_alternative(html_body, subtype="html")

    # ── Send ──────────────────────────────────────────────────────────────────
    ctx = ssl.create_default_context()

    if smtp_port == 465:
        # Implicit SSL (SMTPS)
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        # STARTTLS — works for port 587 and 25
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

    print(f"Sent: {subject!r}")
    for addr in to_addrs:
        print(f"  → {addr}")


if __name__ == "__main__":
    main()
