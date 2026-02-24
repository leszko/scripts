#!/usr/bin/env python3
"""Check Librus Synergia for new messages and forward them to Gmail."""

import argparse
import json
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
import os

from librus_apix.client import new_client
from librus_apix.messages import get_received, message_content

SCRIPT_DIR = Path(__file__).parent
SENT_FILE = SCRIPT_DIR / "forwarded_messages.json"

load_dotenv(SCRIPT_DIR / ".env")

LIBRUS_USERNAME = os.environ["LIBRUS_USERNAME"]
LIBRUS_PASSWORD = os.environ["LIBRUS_PASSWORD"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]


def load_forwarded() -> set[str]:
    if SENT_FILE.exists():
        return set(json.loads(SENT_FILE.read_text()))
    return set()


def save_forwarded(forwarded: set[str]) -> None:
    SENT_FILE.write_text(json.dumps(sorted(forwarded), indent=2))


def send_email(subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[Librus] {subject}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward Librus messages to email")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Record messages as forwarded without sending emails",
    )
    args = parser.parse_args()

    client = new_client()
    client.get_token(LIBRUS_USERNAME, LIBRUS_PASSWORD)

    forwarded = load_forwarded()
    new_count = 0

    page = 1
    while True:
        messages = get_received(client, page=page)
        if not messages:
            break

        all_known = True
        for msg in messages:
            if msg.href in forwarded:
                continue

            all_known = False
            content = message_content(client, msg.href)

            if args.dry_run:
                print(f"[DRY RUN] Would forward: {content.title} (from {content.author}, {content.date})")
            else:
                body = (
                    f"From: {content.author}\n"
                    f"Date: {content.date}\n"
                    f"---\n\n"
                    f"{content.content}"
                )
                send_email(content.title, body)
                print(f"Forwarded: {content.title} (from {content.author})")

            forwarded.add(msg.href)
            new_count += 1

        if all_known:
            break
        page += 1

    save_forwarded(forwarded)

    if new_count == 0:
        print("No new messages.")
    else:
        label = "recorded" if args.dry_run else "forwarded"
        print(f"{new_count} message(s) {label}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
