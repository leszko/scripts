#!/usr/bin/env python3
"""Check Librus for new messages and forward them to Gmail.

Uses the new messaging API at wiadomosci.librus.pl instead of the legacy
synergia.librus.pl scraping, which returns stale/mismatched messages.
"""

import argparse
import json
import re
import smtplib
import sys
from base64 import b64decode
from email.mime.text import MIMEText
from pathlib import Path

from urllib.parse import urljoin

import requests
from dotenv import load_dotenv
import os

SCRIPT_DIR = Path(__file__).parent
SENT_FILE = SCRIPT_DIR / "forwarded_messages.json"

load_dotenv(SCRIPT_DIR / ".env")

LIBRUS_USERNAME = os.environ["LIBRUS_USERNAME"]
LIBRUS_PASSWORD = os.environ["LIBRUS_PASSWORD"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]

API_BASE = "https://wiadomosci.librus.pl/api"


def load_forwarded() -> set[str]:
    if SENT_FILE.exists():
        return set(str(x) for x in json.loads(SENT_FILE.read_text()))
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


OAUTH_URL = "https://api.librus.pl/OAuth/Authorization?client_id=46"
OAUTH_URL_WITH_SCOPE = f"{OAUTH_URL}&response_type=code&scope=mydata"
SYNERGIA_PORTAL_LOGIN_URL = "https://synergia.librus.pl/loguj/portalRodzina"
SYNERGIA_MESSAGES_BOOTSTRAP_URL = "https://synergia.librus.pl/wiadomosci3"
MAX_OAUTH_REDIRECTS = 10


def create_session() -> requests.Session:
    """Authenticate with Librus and return a session with access to the new messaging API.

    As of 2026-03-28, Librus requires the OAuth flow to start from the Synergia
    portalRodzina entry point (not directly at api.librus.pl). The goTo redirect
    now goes through /OAuth/Authorization/2FA, and the redirect chain must be
    followed manually (with allow_redirects=False) so that the oauth_token cookie
    gets set on the synergia.librus.pl domain. Only then can wiadomosci3 bootstrap
    the MultiDomainLogon cookies for wiadomosci.librus.pl.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
    )

    # 1. Start OAuth via the Synergia entry point (portalRodzina).
    #    This sets up the server-side state (oauth_state) that the new flow requires.
    response = session.get(SYNERGIA_PORTAL_LOGIN_URL, allow_redirects=False)
    response.raise_for_status()
    oauth_authorization_url = response.headers.get("Location")
    if not oauth_authorization_url:
        raise RuntimeError(
            "Failed to initialize OAuth login flow: no redirect from portalRodzina."
        )

    # 2. Follow the redirect to the API OAuth endpoint (sets API-side session cookies).
    response = session.get(oauth_authorization_url, allow_redirects=False)
    response.raise_for_status()

    # 3. Submit login credentials.
    response = session.post(
        OAUTH_URL,
        data={"action": "login", "login": LIBRUS_USERNAME, "pass": LIBRUS_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    response.raise_for_status()
    login_data = response.json()
    if login_data.get("status") == "error":
        raise RuntimeError(f"Login failed: {login_data}")

    go_to = login_data.get("goTo")
    if not go_to:
        raise RuntimeError("OAuth login response does not contain 'goTo' redirect.")

    # 4. Follow the redirect chain manually (2FA -> PerformLogin -> Grant -> synergia).
    #    This preserves intermediate cookies, including the critical oauth_token.
    current_url = urljoin(OAUTH_URL_WITH_SCOPE, go_to)
    for _ in range(MAX_OAUTH_REDIRECTS):
        response = session.get(current_url, allow_redirects=False)
        response.raise_for_status()
        location = response.headers.get("Location")
        if not location:
            break
        current_url = urljoin(response.url, location)
    else:
        raise RuntimeError("OAuth redirect chain exceeded limit.")

    # 5. Verify that the oauth_token cookie was set on synergia.librus.pl.
    if not any(
        cookie.name == "oauth_token" and cookie.domain.endswith("synergia.librus.pl")
        for cookie in session.cookies
    ):
        raise RuntimeError(
            "Synergia oauth_token cookie was not set during login. "
            "The authentication flow may have changed again."
        )

    # 6. Bootstrap wiadomosci.librus.pl session via the wiadomosci3 page
    #    (MultiDomainLogon sets cookies on the wiadomosci subdomain).
    response = session.get(SYNERGIA_MESSAGES_BOOTSTRAP_URL)
    response.raise_for_status()
    if "Brak dostępu" in response.text:
        raise RuntimeError(
            "Access denied on wiadomosci3 page after login. Session may be incomplete."
        )

    if not any(
        cookie.domain.endswith("wiadomosci.librus.pl") for cookie in session.cookies
    ):
        raise RuntimeError(
            "Wiadomosci session bootstrap failed: no wiadomosci.librus.pl cookies set."
        )

    return session


def decode_b64(text: str) -> str:
    """Decode base64-encoded message content."""
    try:
        return b64decode(text).decode("utf-8", errors="replace")
    except Exception:
        return text


def format_content(raw: str) -> str:
    """Clean up message content: strip XML wrappers, resolve links, fix spacing."""
    text = raw
    # Strip XML wrapper tags
    text = re.sub(r"</?Message>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?Content>", "", text, flags=re.IGNORECASE)
    text = text.replace("<![CDATA[", "").replace("]]>", "")
    # Convert <a href="...">text</a> to just the href URL
    text = re.sub(r'<a\b[^>]*href="([^"]*)"[^>]*>[^<]*</a>', r"\1", text, flags=re.IGNORECASE)
    # Remove any remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse runs of 3+ newlines into 2 (keep paragraph breaks, remove extra spacing)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward Librus messages to email")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Record messages as forwarded without sending emails",
    )
    args = parser.parse_args()

    session = create_session()
    forwarded = load_forwarded()
    new_count = 0

    # Fetch all pages of messages from the new API.
    all_messages: list[dict] = []
    page = 1
    page_size = 50
    while True:
        print(f"Fetching page {page}...", file=sys.stderr)
        sys.stderr.flush()
        resp = session.get(f"{API_BASE}/inbox/messages?page={page}&limit={page_size}")
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("data", [])
        if not messages:
            break
        all_messages.extend(messages)
        total = data.get("total", 0)
        if len(all_messages) >= total:
            break
        page += 1
        if page > 100:
            break  # safety

    print(f"Loaded {len(all_messages)} messages from {page} page(s).", file=sys.stderr)

    for i, msg in enumerate(all_messages):
        msg_id = str(msg.get("messageId", ""))
        if not msg_id or msg_id in forwarded:
            continue

        topic = msg.get("topic", "(no subject)")
        sender = msg.get("senderName", "Unknown")
        send_date = msg.get("sendDate", "")

        print(
            f"Processing message {i + 1}/{len(all_messages)} (id={msg_id})...",
            file=sys.stderr,
        )
        sys.stderr.flush()

        # Fetch full message content
        resp = session.get(f"{API_BASE}/inbox/messages/{msg_id}")
        resp.raise_for_status()
        full_msg = resp.json()["data"]

        content = format_content(decode_b64(full_msg.get("Message", "")))
        title = full_msg.get("topic", topic)
        author = full_msg.get("senderName", sender)
        date = full_msg.get("sendDate", send_date)

        if args.dry_run:
            print(f"[DRY RUN] Would forward: {title} (from {author}, {date})")
        else:
            body = f"From: {author}\nDate: {date}\n---\n\n{content}"
            send_email(title, body)
            print(f"Forwarded: {title} (from {author})")

        forwarded.add(msg_id)
        new_count += 1

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
