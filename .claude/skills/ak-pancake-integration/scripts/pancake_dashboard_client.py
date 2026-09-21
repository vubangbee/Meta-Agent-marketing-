#!/usr/bin/env python3
"""Pancake INTERNAL dashboard API client — actions the public API doesn't expose.

Usage:
  python pancake_dashboard_client.py toggle-spam --customer-id <uuid> --page N

Requires: pip install requests
Env vars (scripts/.env): PANCAKE_INTERNAL_SESSION_TOKEN, PANCAKE_PAGE_ID_N (reused from
pancake_client.py's .env — same file, same page indexing).

⚠️ This hits pancake.vn/api/v1/... — a completely different, UNDOCUMENTED surface from
pancake_client.py's confirmed public API (pages.fm/api/public_api/v2). Auth is an account
LOGIN SESSION token (JWT), not a per-page API key: it is tied to one Pancake user login and
carries its own expiry (see PANCAKE_INTERNAL_SESSION_TOKEN comment in .env.example for how
to capture a fresh one).

Request shape confirmed 2026-08-24 (live 200 `{"success": true}`) from a real browser "Copy
as cURL" capture: POST, multipart/form-data body with a single field `action=move_to_spam`,
`Origin`/`Referer` headers pointing at the page's own pancake.vn URL, AND — the piece that
actually mattered — a `jwt=<same token>` session COOKIE alongside the `access_token` query
param. A bare POST with just `access_token` (no cookie, no body, no headers) 500'd; adding
Origin/Referer/multipart body alone still 500'd; only adding the `jwt` cookie fixed it. This
endpoint apparently authenticates via session cookie, unlike the public API's query-param
token — the `access_token` query param may be vestigial/ignored here.

customer-id is the PAGE-SCOPED customer UUID: a conversation object's `customers[].id` /
`page_customer.id` field — NOT the conversation's `id` (c_id), and NOT its top-level
`customer_id` field (a different, global UUID). See references/api-reference.md.
"""

import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: Install requests: pip install requests")
    sys.exit(1)

from pancake_client import PAGE_SLUGS, _known_pages, _load_env  # reuses .env loading + page-slug map

_load_env()

DASHBOARD_BASE_URL = "https://pancake.vn/api/v1"
REQUEST_DELAY_SECONDS = 1.5  # rate limit unconfirmed for this surface — reuse pancake_client.py's conservative pacing


def _session_token():
    token = os.getenv("PANCAKE_INTERNAL_SESSION_TOKEN", "").strip()
    if not token:
        print("ERROR: PANCAKE_INTERNAL_SESSION_TOKEN not set in scripts/.env — see .env.example.")
        sys.exit(1)
    return token


def toggle_spam(page_id, customer_id, method="POST"):
    """Mark a customer as spam. Returns the parsed JSON response dict on success (observed
    shape: {"success": true}). Raises RuntimeError with a clear message on any failure —
    callers (CLI or a batch job) decide how to report/aggregate that.

    NOT a symmetric toggle despite the name/URL (confirmed 2026-08-24: 3 repeated calls on
    the same customer never reverted the spam state) — safe to call again on an
    already-spam customer, it's a no-op that still returns success.
    """
    slug = PAGE_SLUGS.get(page_id)
    if not slug:
        raise RuntimeError(f"no PAGE_SLUGS entry for page_id {page_id} in pancake_client.py — "
                            "needed to build the Referer header this endpoint requires. Add it there first.")

    token = _session_token()
    url = f"{DASHBOARD_BASE_URL}/pages/{page_id}/customers/{customer_id}/toggle_move_to_spam"
    # Confirmed 2026-08-24 via real browser "Copy as cURL": this endpoint is Pancake's own
    # dashboard frontend AJAX call, and 500s without Origin/Referer + a multipart body carrying
    # action=move_to_spam. `files={"action": (None, "move_to_spam")}` makes requests emit the
    # same shape a browser FormData with one text field produces. The `jwt` cookie (not just
    # the access_token query param) is what actually authenticates it.
    headers = {
        "Origin": "https://pancake.vn",
        "Referer": f"https://pancake.vn/{slug}",
    }
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        resp = requests.request(
            method, url,
            params={"access_token": token},
            files={"action": (None, "move_to_spam")},
            headers=headers,
            cookies={"jwt": token, "locale": "vi"},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"network error calling toggle_move_to_spam: {e}")

    if resp.status_code in (401, 403):
        raise RuntimeError("rejected by Pancake (401/403) — PANCAKE_INTERNAL_SESSION_TOKEN likely "
                            "expired or invalid. Capture a fresh one (see scripts/.env.example) and retry.")
    if resp.status_code in (404, 405):
        raise RuntimeError(f"HTTP {resp.status_code} — method {method} is probably wrong for this "
                            f"endpoint. Try the other one: {'POST' if method == 'GET' else 'GET'}")
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} from toggle_move_to_spam: {resp.text[:500]!r} (access_token redacted)")

    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"non-JSON response (status {resp.status_code}) from toggle_move_to_spam")


def get_customer(page_id, customer_id):
    """Fetch a page-scoped customer's profile from the internal dashboard API. Returns the
    parsed JSON response dict on success. Raises RuntimeError with a clear message on failure.

    GET https://pancake.vn/api/v1/pages/{page_id}/customers/{customer_id}
    Observed fields (see references/api-reference.md): activities, banned_count, can_inbox,
    comment_count, gender, global_id, id, is_banned, last_commented_at, lives_in, notes,
    profile_updated_at, recent_orders, recent_phone_numbers, reported_count, thread_id.
    `gender` and `lives_in` are the two fields this is used for — Facebook profile data Pancake
    surfaces nowhere else (no age field observed anywhere on this surface).
    """
    slug = PAGE_SLUGS.get(page_id)
    if not slug:
        raise RuntimeError(f"no PAGE_SLUGS entry for page_id {page_id} in pancake_client.py — "
                            "needed to build the Referer header this endpoint requires. Add it there first.")

    token = _session_token()
    url = f"{DASHBOARD_BASE_URL}/pages/{page_id}/customers/{customer_id}"
    headers = {
        "Origin": "https://pancake.vn",
        "Referer": f"https://pancake.vn/{slug}",
    }
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        resp = requests.get(
            url,
            params={"access_token": token},
            headers=headers,
            cookies={"jwt": token, "locale": "vi"},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"network error calling get_customer: {e}")

    if resp.status_code in (401, 403):
        raise RuntimeError("rejected by Pancake (401/403) — PANCAKE_INTERNAL_SESSION_TOKEN likely "
                            "expired or invalid. Capture a fresh one (see scripts/.env.example) and retry.")
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} from get_customer: {resp.text[:500]!r} (access_token redacted)")

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"non-JSON response (status {resp.status_code}) from get_customer")
    return data.get("data", data)


def cmd_get_customer(args):
    pages = _known_pages()
    page_id, _ = pages.get(args.page, (None, None))
    if not page_id:
        print(f"ERROR: no configured page at index {args.page} (PANCAKE_PAGE_ID_{args.page})")
        sys.exit(1)

    try:
        data = get_customer(page_id, args.customer_id)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_toggle_spam(args):
    pages = _known_pages()
    page_id, _ = pages.get(args.page, (None, None))
    if not page_id:
        print(f"ERROR: no configured page at index {args.page} (PANCAKE_PAGE_ID_{args.page})")
        sys.exit(1)

    try:
        data = toggle_spam(page_id, args.customer_id, method=args.method)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(json.dumps({
        "page_id": page_id,
        "customer_id": args.customer_id,
        "method": args.method,
        "response": data,
    }, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Pancake internal dashboard API client")
    sub = parser.add_subparsers(dest="command", required=True)

    ts = sub.add_parser("toggle-spam", help="Mark a customer as spam. NOT a symmetric toggle despite the name/URL: confirmed 2026-08-24 that calling this repeatedly does not undo it (action=move_to_spam is the only value ever captured, appears idempotent-set not flip)")
    ts.add_argument("--customer-id", required=True,
                     help="Page-scoped customer UUID (customers[].id / page_customer.id from a "
                          "conversation object — NOT c_id, NOT the top-level customer_id field)")
    ts.add_argument("--page", type=int, required=True, help="Index matching PANCAKE_PAGE_ID_N in .env")
    ts.add_argument("--method", default="POST", choices=["POST", "GET"],
                     help="HTTP method — unconfirmed which this endpoint expects, default POST "
                          "(typical for a state-mutating RPC-style action). If it 404/405s, retry with GET.")

    gc = sub.add_parser("get-customer", help="Fetch a page-scoped customer's profile (gender, lives_in, etc.) from the internal dashboard API")
    gc.add_argument("--customer-id", required=True,
                     help="Page-scoped customer UUID (customers[].id / page_customer.id from a "
                          "conversation object — NOT c_id, NOT the top-level customer_id field)")
    gc.add_argument("--page", type=int, required=True, help="Index matching PANCAKE_PAGE_ID_N in .env")

    args = parser.parse_args()
    if args.command == "toggle-spam":
        cmd_toggle_spam(args)
    elif args.command == "get-customer":
        cmd_get_customer(args)


if __name__ == "__main__":
    main()
