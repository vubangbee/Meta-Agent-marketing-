#!/usr/bin/env python3
"""Daily job: find conversations tagged a given label (default "RÁC") created on a target
date (default: yesterday) across all configured Pancake pages, and move each to spam via
the internal dashboard API.

Usage:
  python pancake_auto_spam_tagged.py
  python pancake_auto_spam_tagged.py --tag RÁC --page 1
  python pancake_auto_spam_tagged.py --date 2026-08-21 --dry-run

Requires: pip install requests
Env vars (scripts/.env): PANCAKE_PAGE_ID_N / page_access_token_N (read, from pancake_client.py)
and PANCAKE_INTERNAL_SESSION_TOKEN (write, from pancake_dashboard_client.py).

Composes the two existing clients: reads tagged conversations via the confirmed public API
(pancake_client._fetch_conversations), then calls the confirmed internal move-to-spam action
(pancake_dashboard_client.toggle_spam) on each match's page-scoped customer_id
(customers[].id — NOT the conversation's c_id). On a successful spam, also adds a Pancake
note "Đã chuyển đến thư mục Spam." via the confirmed public API notes endpoint
(pancake_client.add_note — a THIRD auth surface: page_access_token again, like
/conversations, but base URL .../v1/, not the internal dashboard's session cookie).

Intended for a daily 08:30 run via an external scheduler (Windows Task Scheduler / cron) —
this script itself has no scheduling logic, it just does one pass and exits. Tag matching is
an exact, case-sensitive label match (same caveat as pancake_client.py's list-by-tag) —
confirmed real tag text is "RÁC" (uppercase with accent), not "Rác"; override with --tag if
your account's label differs. "Created" is inserted_at (matches this skill's established
"created" semantics, not updated_at). toggle_move_to_spam is confirmed idempotent-set, not a
true toggle (2026-08-24) — safe to re-run this job on the same day/tag without double-effects.

⚠️ PANCAKE_INTERNAL_SESSION_TOKEN is an account login session JWT with its own expiry
(~2026-11-15 as captured) — this job will start failing with a 401/403 per-item error once it
expires or the underlying Pancake login session ends, and needs a manually re-captured token
(see .env.example) to keep working. There is no automatic renewal.
"""

import argparse
import json
import sys
from datetime import date, timedelta

from pancake_client import (_known_pages, _load_env, _to_unix, add_note,
                             fetch_conversations_complete, page_name)
from pancake_dashboard_client import toggle_spam

_load_env()

SPAM_NOTE_MESSAGE = "Đã chuyển đến thư mục Spam."


def find_and_spam_tagged(tag, since, until, target_pages, dry_run=False):
    """Find conversations with `tag` (exact, case-sensitive) whose inserted_at falls in
    [since, until) unix seconds, across target_pages ({index: (page_id, page_access_token)}),
    and call toggle_spam on each match's page-scoped customer_id (unless dry_run).

    Returns (matched, results): `matched` is the raw list of match dicts (page_index, page_id,
    c_id, customer_id, name, inserted_at); `results` is the same dicts plus a `status`
    ("ok"/"error"/"dry_run") and either `response` or `error`. Shared by the 08:30 full-day job
    (pancake_auto_spam_tagged.py's own CLI) and pancake_spam_report.py's same-day 17:00 pass —
    only the since/until window and what's done with the result (JSON to stdout vs a Markdown
    report file) differ between the two.

    NOTE: `name` is customer PII — carried here so pancake_spam_report.py can label its report
    with names instead of bare c_id (an explicit user decision 2026-08-24, despite this skill's
    usual "no PII in output" default elsewhere — see that script's report for the actual output).
    """
    matched = []
    for i, (page_id, token) in target_pages.items():
        if not page_id or not token:
            continue
        # Auto-subdivides the window if it hits the API's 60/call cap, so a busy day can't
        # silently drop conversations (confirmed 2026-08-24: that bug cost 79 missed
        # conversations across 24 capped days before this was added).
        convs = fetch_conversations_complete(page_id, token, since, until, order_by="inserted_at")
        for c in convs:
            tags = [t.get("text") for t in (c.get("tags") or []) if t]
            if tag not in tags:
                continue
            customers = c.get("customers") or []
            if not customers or not customers[0].get("id"):
                print(f"WARNING: c_id {c.get('id')} matched tag but has no page-scoped customer id — skipped", file=sys.stderr)
                continue
            matched.append({
                "page_index": i, "page_id": page_id,
                "c_id": c.get("id"), "customer_id": customers[0]["id"],
                "name": customers[0].get("name") or "",
                "inserted_at": c.get("inserted_at"),
            })

    results = []
    for m in matched:
        if dry_run:
            results.append({**m, "status": "dry_run"})
            continue
        try:
            resp = toggle_spam(m["page_id"], m["customer_id"])
        except RuntimeError as e:
            results.append({**m, "status": "error", "error": str(e)})
            continue

        entry = {**m, "status": "ok", "response": resp}
        try:
            add_note(m["page_id"], m["customer_id"], SPAM_NOTE_MESSAGE)
            entry["note_status"] = "ok"
        except RuntimeError as e:
            # Spam action itself succeeded — a note failure doesn't undo that, just gets
            # logged and flagged separately so it can be retried without re-spamming.
            entry["note_status"] = "error"
            entry["note_error"] = str(e)
            print(f"WARNING: spam ok but note failed for c_id {m['c_id']}: {e}", file=sys.stderr)
        results.append(entry)

    return matched, results


def main():
    parser = argparse.ArgumentParser(description="Move tagged conversations from a target date to spam")
    parser.add_argument("--tag", default="RÁC", help="Exact tag label to match (case-sensitive, default: RÁC)")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD to process instead of yesterday (for backfill/testing)")
    parser.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default all configured pages")
    parser.add_argument("--dry-run", action="store_true", help="List matches without calling toggle_move_to_spam")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    since = _to_unix(target_date.isoformat())
    until = _to_unix((target_date + timedelta(days=1)).isoformat())

    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)
    target_pages = {args.page: pages[args.page]} if args.page else pages

    matched, results = find_and_spam_tagged(args.tag, since, until, target_pages, dry_run=args.dry_run)

    print(f"Date: {target_date.isoformat()} | Tag: {args.tag!r} | Matched: {len(matched)}", file=sys.stderr)

    ok = sum(1 for r in results if r["status"] == "ok")
    errors = [r for r in results if r["status"] == "error"]

    # Write the FULL-day section, replacing whatever the previous evening's 17:00 job wrote for
    # this date (that run could only see 00:00-16:59:59). Without this the report would silently
    # omit every conversation created 17:00-23:59, even though this job does spam them.
    # Imported lazily to avoid a circular import: pancake_spam_report imports find_and_spam_tagged
    # from this module at load time.
    report_path = None
    if not args.dry_run:
        from pancake_spam_report import FULL_DAY_WINDOW, _write_report
        report_path = str(_write_report(target_date, args.tag, matched, results,
                                         window_label=FULL_DAY_WINDOW))

    print(json.dumps({
        "date": target_date.isoformat(),
        "tag": args.tag,
        "matched": len(matched),
        "moved_to_spam": ok,
        "dry_run": args.dry_run,
        "report": report_path,
        "errors": [{"c_id": e["c_id"], "error": e["error"]} for e in errors],
    }, indent=2, ensure_ascii=False))

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
