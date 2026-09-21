#!/usr/bin/env python3
"""Pancake API client — resolve Facebook ad attribution + sale tags for conversations.

Usage:
  python pancake_client.py test-connection
  python pancake_client.py list-conversations --page N [--output conversations.json]
  python pancake_client.py count-conversations --since 2026-08-01 --until 2026-08-15 [--order-by inserted_at]
  python pancake_client.py tag-report --since 2026-08-01 --until 2026-08-15 [--page N]
  python pancake_client.py lag-report --since 2026-08-01 --until 2026-08-15 [--tags "Hẹn lịch,Đã pt"]
  python pancake_client.py resolve-batch --input leads.csv --output leads_resolved.csv [--page N]
  python pancake_client.py rechat-report --since 2026-01-01 --output rechat.csv [--stale-days 30]

Requires: pip install requests
Env vars (scripts/.env): PANCAKE_PAGE_ID_1.. and page_access_token_1.. (paired by index).
See references/api-reference.md for the confirmed endpoint/schema.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REQUEST_DELAY_SECONDS = 1.5  # conservative — rate limit hit in testing with rapid consecutive calls
MAX_RETRIES = 3  # total attempts per call — covers transient "try again later" / timeout errors
RETRY_BACKOFF_SECONDS = 2  # doubles each retry: 2s, 4s, 8s...

try:
    import requests
except ImportError:
    print("ERROR: Install requests: pip install requests")
    sys.exit(1)

# Windows consoles/redirected-file streams often default to cp1252, which can't encode the
# Vietnamese text this script prints (tag labels, page names) — confirmed 2026-08-24 this
# crashed a real rechat-report --add-tag batch run mid-scan on a near-cap WARNING. Force UTF-8
# regardless of the caller's locale/PYTHONIOENCODING so output never depends on the console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

_scripts_dir = Path(__file__).parent
BASE_URL = "https://pages.fm/api/public_api/v2"


def _load_env():
    env_file = _scripts_dir / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


_load_env()


def _known_pages():
    """Return {index: (page_id, page_access_token)} for every configured page."""
    pages = {}
    i = 1
    while True:
        page_id = os.getenv(f"PANCAKE_PAGE_ID_{i}", "").strip()
        token = os.getenv(f"page_access_token_{i}", "").strip()
        if not page_id and not token:
            break
        pages[i] = (page_id, token)
        i += 1
    return pages


def _known_funnel_stages():
    """Return ordered [(name, {tag_labels})] from FUNNEL_STAGE_N_NAME / FUNNEL_STAGE_N_TAGS in .env."""
    stages = []
    i = 1
    while True:
        name = os.getenv(f"FUNNEL_STAGE_{i}_NAME", "").strip()
        tags = os.getenv(f"FUNNEL_STAGE_{i}_TAGS", "").strip()
        if not name and not tags:
            break
        stages.append((name or f"Stage {i}", set(t.strip() for t in tags.split(",") if t.strip())))
        i += 1
    return stages


def _page_by_id(page_id):
    for pid, token in _known_pages().values():
        if pid == page_id:
            return pid, token
    return None, None


NOTES_BASE_URL = "https://pages.fm/api/public_api/v1"  # confirmed 2026-08-24 — note: v1, not v2 like /conversations


def add_note(page_id, page_customer_id, message):
    """Add a note to a customer's Pancake profile. Confirmed 2026-08-24 (user-supplied cURL):
    POST https://pages.fm/api/public_api/v1/pages/{page_id}/page_customers/{page_customer_id}/notes
    ?page_access_token=<per-page token> — same public-API auth as /conversations (page_access_token,
    NOT the internal dashboard's session token/cookie used by pancake_dashboard_client.py).
    page_customer_id is the same page-scoped customer UUID as toggle_spam's customer_id
    (customers[].id / page_customer.id on a conversation object).
    Returns the parsed JSON response on success; raises RuntimeError on failure.
    """
    _, token = _page_by_id(page_id)
    if not token:
        raise RuntimeError(f"no page_access_token configured for page_id {page_id}")

    url = f"{NOTES_BASE_URL}/pages/{page_id}/page_customers/{page_customer_id}/notes"
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        resp = requests.post(
            url,
            params={"page_access_token": token},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"message": message},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"network error calling notes endpoint: {e}")

    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} from notes endpoint: {resp.text[:300]!r} (page_access_token redacted)")

    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"non-JSON response (status {resp.status_code}) from notes endpoint")


def get_tags(page_id):
    """List all tags defined for a page. Confirmed 2026-08-24 (user-supplied endpoint, verified
    live: HTTP 200, 34 tags returned on page 1):
    GET https://pages.fm/api/public_api/v1/pages/{page_id}/tags?page_access_token=<token>
    Same auth surface as add_note (page_access_token, NOT the internal dashboard session).
    Returns [{"id": int, "text": str, "color": str, "is_deactive": bool, "description": str,
    "lighten_color": str}, ...] — schema confirmed live 2026-08-24.
    """
    _, token = _page_by_id(page_id)
    if not token:
        raise RuntimeError(f"no page_access_token configured for page_id {page_id}")

    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        resp = requests.get(f"{NOTES_BASE_URL}/pages/{page_id}/tags", params={"page_access_token": token}, timeout=20)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"network error calling tags endpoint: {e}")

    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} from tags endpoint: {resp.text[:300]!r} (page_access_token redacted)")

    try:
        return resp.json().get("tags", [])
    except ValueError:
        raise RuntimeError(f"non-JSON response (status {resp.status_code}) from tags endpoint")


def find_tag_id(page_id, tag_text):
    """Exact, case-sensitive lookup of a tag's numeric id by its label text (via get_tags).
    Returns None if no tag on this page has that exact text."""
    for t in get_tags(page_id):
        if t.get("text") == tag_text:
            return t.get("id")
    return None


def set_conversation_tag(page_id, conversation_id, tag_id, action="add"):
    """Add or remove a tag (by numeric id, from get_tags/find_tag_id) on a conversation.
    User-supplied endpoint + body shape 2026-08-24 (matches Pancake's own public API doc example),
    **confirmed live 2026-08-24** for action="add": POST returns
    {"data": [<tag_id>, ...], "success": true} — `data` is the conversation's resulting tag-id
    list (confirmed idempotent: re-adding an already-present tag_id returns the same list, no
    duplicate, still success:true — safe to re-run this on the same conversation/tag repeatedly,
    unlike add_note).
    POST https://pages.fm/api/public_api/v1/pages/{page_id}/conversations/{conversation_id}/tags
    ?page_access_token=<token>
    Body: {"action": "add"|"remove", "tag_id": "<id>"} — tag_id sent as a string per the doc
    example. action="remove" is inferred symmetric to "add" (not live-tested) — if it errors,
    only "add" is confirmed working.
    Returns the parsed JSON response on success; raises RuntimeError on failure.
    """
    if action not in ("add", "remove"):
        raise ValueError(f"action must be 'add' or 'remove', got {action!r}")
    _, token = _page_by_id(page_id)
    if not token:
        raise RuntimeError(f"no page_access_token configured for page_id {page_id}")

    url = f"{NOTES_BASE_URL}/pages/{page_id}/conversations/{conversation_id}/tags"
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        resp = requests.post(
            url,
            params={"page_access_token": token},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"action": action, "tag_id": str(tag_id)},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"network error calling tags endpoint: {e}")

    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} from tags endpoint (action={action}): {resp.text[:300]!r} (page_access_token redacted)")

    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"non-JSON response (status {resp.status_code}) from tags endpoint")


def add_tag_to_conversation(page_id, conversation_id, tag_id):
    """Attach an existing tag to a conversation. Thin wrapper over set_conversation_tag(action='add')."""
    return set_conversation_tag(page_id, conversation_id, tag_id, action="add")


def rechat_tag_name(d=None):
    """Deterministic daily rechat tag label: R-{DD}{MM}{Y} where Y is the last digit of the
    year — e.g. 2026-08-24 -> "R-24086". User-specified format 2026-08-24."""
    d = d or datetime.now(LOCAL_TZ).date()
    return f"R-{d.day:02d}{d.month:02d}{d.year % 10}"


def cmd_test_connection(args):
    pages = _known_pages()
    if not pages:
        print("ERROR: no PANCAKE_PAGE_ID_N / page_access_token_N pairs set in scripts/.env")
        sys.exit(1)

    any_ok = False
    for i, (page_id, token) in pages.items():
        if not page_id or not token:
            print(f"page {i}: SKIP (missing page_id or token)")
            continue
        resp = requests.get(
            f"{BASE_URL}/pages/{page_id}/conversations",
            params={"access_token": token},
            timeout=20,
        )
        ok = False
        try:
            data = resp.json()
            ok = resp.status_code == 200 and data.get("success") is True
        except ValueError:
            data = None
        count = len(data.get("conversations", [])) if ok else None
        print(f"page {i} ({page_id}): status={resp.status_code} ok={ok} conversations_returned={count}")
        any_ok = any_ok or ok

    if not any_ok:
        print("\nNo page succeeded. Check page_access_token_N values in scripts/.env — this endpoint")
        print("needs a per-page 'Public API access token', not the account-level session key.")


LOCAL_TZ = timezone(timedelta(hours=7))  # Asia/Bangkok (Vietnam) — no DST, fixed offset is safe


def _resolve_window(args):
    """Resolve the (since_date, until_date_exclusive, until_ts_cap) triple for a command that
    accepts either --month YYYY-MM or an explicit --since/--until pair.

    --month sets since to the 1st of that month. For a past month, until is the 1st of the
    following month — the whole month, same exclusive-end convention as every --until in this
    script. For the CURRENT month, until_date_exclusive stops at tomorrow (so the day-chunk
    loop never walks into days that have not happened yet) and until_ts_cap carries the exact
    "now" unix timestamp — the caller must clamp today's chunk to it, so a report run at 15:00
    does not claim to cover the rest of today.

    until_ts_cap is None whenever no clamping is needed (explicit --since/--until, or a past
    --month) — callers should apply min(day_until_ts, until_ts_cap) only when it is not None.
    """
    month = getattr(args, "month", None)
    if month:
        if args.since or args.until:
            print("ERROR: --month cannot be combined with --since/--until")
            sys.exit(1)
        try:
            year_s, mon_s = month.split("-")
            since_date = date(int(year_s), int(mon_s), 1)
        except (ValueError, AttributeError):
            print(f"ERROR: --month must be YYYY-MM (got {month!r})")
            sys.exit(1)
        next_month = date(since_date.year + (since_date.month == 12),
                          since_date.month % 12 + 1, 1)
        now = datetime.now(LOCAL_TZ)
        today = now.date()
        if since_date <= today < next_month:
            return since_date, today + timedelta(days=1), int(now.timestamp())
        return since_date, next_month, None

    if not args.since or not args.until:
        print("ERROR: provide --month YYYY-MM, or both --since and --until")
        sys.exit(1)
    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date()
    if until_date <= since_date:
        print("ERROR: --until must be after --since")
        sys.exit(1)
    return since_date, until_date, None


def _to_unix(date_str):
    """Accept YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, interpreted in Asia/Bangkok (UTC+7),
    return unix seconds. A bare YYYY-MM-DD means local midnight of that day, matching
    what a human means by "today" in this business's timezone — NOT UTC midnight."""
    if date_str is None:
        return None
    fmt = "%Y-%m-%dT%H:%M:%S" if "T" in date_str else "%Y-%m-%d"
    dt = datetime.strptime(date_str, fmt).replace(tzinfo=LOCAL_TZ)
    return int(dt.timestamp())


def _fetch_conversations(page_id, token, since=None, until=None, order_by=None, tags=None, types=None, extra_params=None):
    params = {"access_token": token}
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if order_by:
        params["order_by"] = order_by
    if tags:
        params["tags"] = tags
    if types:
        # Confirmed 2026-08-14: the API only accepts ONE type value per call. Passing
        # multiple (type=COMMENT&type=COMMENT_LIVESTREAM) silently returns 0 results
        # instead of the union — no error, so this must be caught client-side.
        if len(types) > 1:
            raise ValueError(
                f"Pancake API only supports one --type value per call (got {types}); "
                "call once per type and sum client-side instead."
            )
        params["type"] = types[0]
    if extra_params:
        params.update(extra_params)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY_SECONDS)
        try:
            resp = requests.get(f"{BASE_URL}/pages/{page_id}/conversations", params=params, timeout=20)
        except requests.exceptions.RequestException as e:
            last_error = f"network error: {e}"
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code} on GET /pages/{page_id}/conversations (params redacted)"
            elif not resp.ok:
                # Non-retryable client error (bad token, bad params, etc.) — retrying won't help.
                raise RuntimeError(f"HTTP {resp.status_code} on GET /pages/{page_id}/conversations (params redacted)")
            else:
                data = resp.json()
                if data.get("success"):
                    return data.get("conversations", [])
                # Pancake returns this generic shape for its own transient backend errors
                # (confirmed 2026-08-17: same call succeeded on immediate retry, no param change).
                last_error = f"Pancake API error: {data}"

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"WARNING: {last_error} — retry {attempt}/{MAX_RETRIES - 1} in {wait}s", file=sys.stderr)
            time.sleep(wait)

    raise RuntimeError(f"{last_error} (failed after {MAX_RETRIES} attempts)")


CAP_SPLIT_THRESHOLD = 55   # the API's hard cap is 60/call; treat anything at/above this as possibly truncated
MIN_WINDOW_SECONDS = 60    # stop subdividing at 1-minute windows — below that, truncation is not recoverable


def fetch_conversations_complete(page_id, token, since, until, order_by="inserted_at", types=None, _depth=0):
    """Fetch every conversation in [since, until) despite the API's confirmed 60-per-call cap.

    The cap has no pagination cursor, so a busy window silently returns only the 60 most recent
    and drops the rest with no error. Confirmed 2026-08-24 this bites in practice: an hourly
    re-scan of 24 capped days on one page surfaced 79 conversations the plain day-chunked scan
    had missed entirely.

    Strategy: fetch the window; if the result is at/above CAP_SPLIT_THRESHOLD it may be
    truncated, so split the window in half and recurse on each half, then union by conversation
    id. Halving (rather than fixed hourly slicing) adapts to whatever the real density is and
    costs no extra calls on quiet windows. Gives up subdividing below MIN_WINDOW_SECONDS and
    warns, since at that point a still-capped window means >60 conversations in one minute.

    Returns a list of conversation dicts, deduped by id.
    """
    convs = _fetch_conversations(page_id, token, since=since, until=until, order_by=order_by, types=types)

    if len(convs) < CAP_SPLIT_THRESHOLD or (until - since) <= MIN_WINDOW_SECONDS:
        if len(convs) >= CAP_SPLIT_THRESHOLD:
            print(f"WARNING: {page_name(page_id)} returned {len(convs)} for a "
                  f"{until - since}s window — at the cap but too narrow to split further; "
                  "some conversations may be missing.", file=sys.stderr)
        return convs

    mid = since + (until - since) // 2
    merged = {}
    for lo, hi in ((since, mid), (mid, until)):
        for c in fetch_conversations_complete(page_id, token, lo, hi, order_by=order_by,
                                               types=types, _depth=_depth + 1):
            merged[c.get("id")] = c
    return list(merged.values())


def _lag_stats(vals):
    """n/avg/median/p90/min/max over a list of day-lags. Shared by lag-report and
    phone-lag-report so the two use identical statistics semantics."""
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return {"n": 0}
    avg = sum(vals) / n
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    p90 = vals[min(n - 1, int(round(n * 0.9)))] if n > 1 else vals[0]
    return {
        "n": n,
        "avg_days": round(avg, 2),
        "median_days": round(median, 2),
        "p90_days": round(p90, 2),
        "min_days": round(vals[0], 2),
        "max_days": round(vals[-1], 2),
        "low_sample": n < 10,
    }


def cmd_list_conversations(args):
    pages = _known_pages()
    page_id, token = pages.get(args.page, (None, None))
    if not page_id or not token:
        print(f"ERROR: no configured page at index {args.page} (PANCAKE_PAGE_ID_{args.page} / page_access_token_{args.page})")
        sys.exit(1)

    conversations = _fetch_conversations(
        page_id, token,
        since=_to_unix(args.since), until=_to_unix(args.until),
        order_by=args.order_by, tags=args.tags, types=args.type,
    )
    result = {"page_id": page_id, "count": len(conversations), "conversations": conversations}
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"status": "written", "output": args.output, "count": len(conversations)}))
    else:
        # Console-safe summary only — full conversation objects contain customer PII.
        summary = [
            {
                "id": c.get("id"),
                "ad_ids": c.get("ad_ids"),
                "tags": [t.get("text") for t in (c.get("tags") or []) if t],
                "has_phone": c.get("has_phone"),
            }
            for c in conversations
        ]
        print(json.dumps(summary, indent=2, ensure_ascii=True))


def cmd_count_conversations(args):
    """Count conversations over a date range, chunked by day to stay under the
    confirmed 60-per-call cap (see references/api-reference.md)."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date, until_date, until_ts_cap = _resolve_window(args)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    per_page_total = {i: 0 for i in target_pages}
    per_page_with_phone = {i: 0 for i in target_pages}
    per_day = {}
    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        if until_ts_cap is not None:
            until_ts = min(until_ts, until_ts_cap)
        day_total = 0
        day_with_phone = 0
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by=args.order_by, types=args.type)
            n = len(convs)
            with_phone = sum(1 for c in convs if c.get("has_phone"))
            if n >= 55:
                print(f"WARNING: {day} page {i} returned {n} — near the 60 cap, "
                      f"may still be truncated; narrow further (e.g. by hour) if this matters.")
            per_page_total[i] += n
            per_page_with_phone[i] += with_phone
            day_total += n
            day_with_phone += with_phone
        per_day[day.isoformat()] = {"total": day_total, "with_phone": day_with_phone}
        day = next_day

    grand_total = sum(per_page_total.values())
    grand_with_phone = sum(per_page_with_phone.values())
    print(json.dumps({
        "since": args.since,
        "until": args.until,
        "order_by": args.order_by,
        "per_day": per_day,
        "per_page": {f"page_{i}": t for i, t in per_page_total.items()},
        "per_page_with_phone": {f"page_{i}": t for i, t in per_page_with_phone.items()},
        "total": grand_total,
        "total_with_phone": grand_with_phone,
    }, indent=2))


def _matches_tag_filter(labels, all_of=None, any_of=None, exclude=None):
    """Client-side tag filter: AND (all_of), OR (any_of), NOT (exclude) — combinable,
    matching the dashboard's "Có chứa thẻ" (AND/OR) + "Loại trừ thẻ" UI."""
    if all_of and not (all_of <= labels):
        return False
    if any_of and not (labels & any_of):
        return False
    if exclude and (labels & exclude):
        return False
    return True


def cmd_tag_report(args):
    """Like count-conversations, but grouped by tag label instead of a single total.
    A conversation with multiple tags counts toward each of its tags."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date, until_date, until_ts_cap = _resolve_window(args)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    tag_counts = {}       # tag text -> count
    total_conversations = 0
    total_untagged = 0
    all_of = set(args.all_of) if args.all_of else None
    any_of = set(args.any_of) if args.any_of else None
    exclude = set(args.exclude) if args.exclude else None
    all_of_count = 0
    filter_count = 0
    filter_with_phone = 0

    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        if until_ts_cap is not None:
            until_ts = min(until_ts, until_ts_cap)
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by=args.order_by, types=args.type)
            if len(convs) >= 55:
                print(f"WARNING: {day} page {i} returned {len(convs)} — near the 60 cap, may still be truncated.")
            total_conversations += len(convs)
            for c in convs:
                tags = [t for t in (c.get("tags") or []) if t]
                if not tags:
                    total_untagged += 1
                labels = set()
                for t in tags:
                    label = t.get("text") or f"(id {t.get('id')})"
                    tag_counts[label] = tag_counts.get(label, 0) + 1
                    labels.add(label)
                if (all_of or any_of or exclude) and _matches_tag_filter(labels, all_of, any_of, exclude):
                    filter_count += 1
                    if c.get("has_phone"):
                        filter_with_phone += 1
        day = next_day

    ranked = sorted(tag_counts.items(), key=lambda kv: -kv[1])
    result = {
        "since": args.since,
        "until": args.until,
        "order_by": args.order_by,
        "type_filter": args.type,
        "total_conversations": total_conversations,
        "total_untagged": total_untagged,
        "tags": [{"tag": label, "count": n} for label, n in ranked],
    }
    if all_of or any_of or exclude:
        result["filter"] = {
            "all_of": sorted(all_of) if all_of else None,
            "any_of": sorted(any_of) if any_of else None,
            "exclude": sorted(exclude) if exclude else None,
        }
        result["filter_count"] = filter_count
        result["filter_with_phone"] = filter_with_phone
    print(json.dumps(result, indent=2, ensure_ascii=True))


PAGE_SLUGS = {
    "108067022357425": "bacsidacquang",
    "107684028988499": "drDacQuang",
    "180350405152355": "bsDacQuangthammy",
    "767583606434885": "drdacquangthammyantoanchuanykhoa",
}

# Human-readable page names, as they appear in Pancake/Facebook. Reports and console output
# use these instead of "page 1/2/3" — a bare index means nothing to whoever reads the report.
# Source: GET https://pancake.vn/api/v1/pages/{page_id} -> data.name (confirmed 2026-08-24).
PAGE_NAMES = {
    "108067022357425": "Bác sĩ Đắc Quang - Bác sĩ Sửa",
    "107684028988499": "Bác sĩ Đắc Quang",
    "180350405152355": "Bác Sĩ Đắc Quang - Phẫu thuật Thẩm mỹ",
    "767583606434885": "Dr. Đắc Quang - Thẩm Mỹ An Toàn Chuẩn Y Khoa",
}


def page_name(page_id):
    """Display name for a page_id, falling back to the raw id if it isn't in PAGE_NAMES."""
    return PAGE_NAMES.get(page_id, f"(page_id {page_id})")


def _conversation_link(page_id, c_id):
    slug = PAGE_SLUGS.get(page_id)
    if not slug:
        return f"(unknown slug for page {page_id}) c_id={c_id}"
    return f"https://pancake.vn/{slug}?c_id={c_id}"


def cmd_list_by_tag(args):
    """List conversations matching a tag (by label), with the fields needed for a
    customer-facing report: inbox date, name, phone-capture date, phone, conversation link."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date, until_date, until_ts_cap = _resolve_window(args)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    rows = []
    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        if until_ts_cap is not None:
            until_ts = min(until_ts, until_ts_cap)
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by="inserted_at", types=args.type)
            for c in convs:
                tags = [t.get("text") for t in (c.get("tags") or []) if t]
                if args.tag not in tags:
                    continue
                name = ((c.get("customers") or [{}])[0].get("name")
                        or (c.get("from") or {}).get("name") or "")
                phones = c.get("recent_phone_numbers") or []
                link = _conversation_link(page_id, c.get("id"))
                ad_ids = ",".join(c.get("ad_ids") or [])
                # NOTE: recent_phone_numbers[].captured is NOT a date — confirmed 2026-08-14
                # it duplicates phone_number itself. The API exposes no per-phone capture
                # timestamp; inserted_at (conversation start) is the closest available date.
                if phones:
                    for p in phones:
                        rows.append({
                            "inbox_date": c.get("inserted_at", ""),
                            "name": name,
                            "phone_number": p.get("phone_number", ""),
                            "link": link,
                            "ad_ids": ad_ids,
                        })
                else:
                    rows.append({
                        "inbox_date": c.get("inserted_at", ""),
                        "name": name,
                        "phone_number": "",
                        "link": link,
                        "ad_ids": ad_ids,
                    })
        day = next_day

    if args.output:
        fieldnames = ["inbox_date", "name", "phone_number", "link", "ad_ids"]
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({"status": "written", "output": args.output, "count": len(rows)}))
    else:
        print(json.dumps({"count": len(rows), "note": "contains customer PII — avoid printing to console; use --output"}, indent=2))
        for r in rows:
            print(json.dumps(r, ensure_ascii=True))


def cmd_watch_tag(args):
    """Poll for conversations tagged --tag (default QM) that have not been reported by a
    previous run — the building block for an n8n Schedule Trigger that notifies on new tags
    every few minutes without re-notifying the same conversation.

    Scans every conversation INSERTED in the last --lookback-days, not just today's — a tag
    is commonly added days after the conversation itself was created (sale rep triages later),
    so restricting the fetch window to "today" misses exactly the case a sale team cares about
    most: an old lead that was just qualified. Confirmed 2026-08-27 against real data: one
    conversation inserted 2026-08-17 had a tag added 2026-08-25, an 8-day gap. There is no
    cheaper API-side filter for this — the `tags` query param does NOT restrict results
    server-side (tested empirically: passing tags=["QM"] over an 8-month window returned 60
    untagged-for-QM conversations, the same silent 60-per-call truncation as an unfiltered
    call) and `updated_at` does not reliably move when a tag is added (tested: a tag_histories
    'add' event timestamped AFTER the conversation's own `updated_at` field), so ordering by
    updated_at to shrink the window is not safe either. The only correct signal is each
    conversation's *current* `tags` array, which means fetching the conversation itself.

    Every conversation in the window is fetched via `fetch_conversations_complete` (not the
    plain day-chunked call other commands use) so a busy day cannot silently truncate and hide
    a tagged conversation — this command's entire job is not missing one.

    State (which conversation ids were already reported, and when) lives in a small JSON file
    next to this script by default. Entries older than --lookback-days are pruned each run,
    since the fetch window itself would never see that conversation again either — pruning
    can't cause a re-notification. There is no server-side "notify me" primitive on this API
    (see SKILL.md), so this file IS the queue.
    """
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    now = datetime.now(LOCAL_TZ)
    since_date = (now - timedelta(days=args.lookback_days)).date()
    until_date = now.date() + timedelta(days=1)  # exclusive end: covers all of today

    state_path = Path(args.state_file) if args.state_file else _scripts_dir / "watch_tag_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        # A corrupt state file must not crash the poll loop — worst case is one run of
        # duplicate notifications, which is far cheaper than silently going blind.
        state = {}
    seen_ids = set(state.keys())

    new_items = []
    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        for i, (page_id, token) in pages.items():
            convs = fetch_conversations_complete(page_id, token, since_ts, until_ts,
                                                  order_by="inserted_at", types=["INBOX"])
            for c in convs:
                conv_id = c.get("id")
                if not conv_id or conv_id in seen_ids:
                    continue
                tags = [t.get("text") for t in (c.get("tags") or []) if t]
                if args.tag not in tags:
                    continue
                name = ((c.get("customers") or [{}])[0].get("name")
                        or (c.get("from") or {}).get("name") or "")
                phones = c.get("recent_phone_numbers") or []
                new_items.append({
                    "conversation_id": conv_id,
                    "page": page_name(page_id),
                    "name": name,
                    "phone_number": phones[0].get("phone_number", "") if phones else "",
                    "tags": tags,
                    "link": _conversation_link(page_id, conv_id),
                    "inbox_date": c.get("inserted_at", ""),
                })
                seen_ids.add(conv_id)
        day = next_day

    cutoff_iso = (now - timedelta(days=args.lookback_days)).isoformat()
    pruned = {cid: ts for cid, ts in state.items() if ts >= cutoff_iso}
    now_iso = now.isoformat()
    for item in new_items:
        pruned[item["conversation_id"]] = now_iso
    state_path.write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"tag": args.tag, "lookback_days": args.lookback_days,
                      "checked_at": now_iso, "new_count": len(new_items),
                      "new_items": new_items}, ensure_ascii=False, indent=2))


def cmd_funnel_report(args):
    """Conversion funnel report: for each configured FUNNEL_STAGE_N in .env, sum how many
    times each of that stage's criteria (each tag, plus HAS_PHONE if listed) matches —
    ADDITIVE per criterion, not deduplicated OR. A conversation matching 2 criteria in the
    same stage contributes 2 to that stage's count. Stages are reported in the order
    defined (N=1 first) — expected top-of-funnel to bottom-of-funnel, but this command
    does not assume cumulative tagging."""
    stages = _known_funnel_stages()
    if not stages:
        print("ERROR: no FUNNEL_STAGE_N_NAME/FUNNEL_STAGE_N_TAGS pairs found in scripts/.env")
        print("Add e.g. FUNNEL_STAGE_1_NAME=Lead moi / FUNNEL_STAGE_1_TAGS=KTT,Thanh, then FUNNEL_STAGE_2_...")
        sys.exit(1)

    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date, until_date, until_ts_cap = _resolve_window(args)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    stage_counts = [0] * len(stages)
    total_conversations = 0
    unmatched = 0

    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        if until_ts_cap is not None:
            until_ts = min(until_ts, until_ts_cap)
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by=args.order_by, types=args.type)
            if len(convs) >= 55:
                print(f"WARNING: {day} page {i} returned {len(convs)} — near the 60 cap, may still be truncated.")
            total_conversations += len(convs)
            for c in convs:
                labels = set(t.get("text") for t in (c.get("tags") or []) if t)
                has_phone = bool(c.get("has_phone"))
                has_ad_id = bool(c.get("ad_ids"))
                matched_any = False
                for idx, (name, stage_tags) in enumerate(stages):
                    special = {"HAS_PHONE", "HAS_AD_ID", "ALL"}
                    real_tags = stage_tags - special
                    wants_phone = "HAS_PHONE" in stage_tags
                    wants_ad_id = "HAS_AD_ID" in stage_tags
                    wants_all = "ALL" in stage_tags
                    # Additive: each criterion in the stage (each tag, plus HAS_PHONE/HAS_AD_ID)
                    # is counted independently and summed — a conversation matching 2 criteria
                    # in the same stage adds 2, not 1 (confirmed 2026-08-14: "tổng số tag LLK
                    # cộng với số lượng inbox HAS_PHONE" — sum, not deduplicated OR).
                    if wants_all:
                        stage_counts[idx] += 1
                        matched_any = True
                    for tag in real_tags:
                        if tag in labels:
                            stage_counts[idx] += 1
                            matched_any = True
                    if wants_phone and has_phone:
                        stage_counts[idx] += 1
                        matched_any = True
                    if wants_ad_id and has_ad_id:
                        stage_counts[idx] += 1
                        matched_any = True
                if not matched_any:
                    unmatched += 1
        day = next_day

    top = stage_counts[0] if stage_counts and stage_counts[0] else None
    funnel = []
    prev = None
    for (name, stage_tags), count in zip(stages, stage_counts):
        entry = {
            "stage": name,
            "tags": sorted(stage_tags),
            "count": count,
            "pct_of_top": round(count / top * 100, 1) if top else None,
            "pct_of_prev": round(count / prev * 100, 1) if prev else None,
        }
        funnel.append(entry)
        prev = count if count else prev

    print(json.dumps({
        "since": args.since,
        "until": args.until,
        "order_by": args.order_by,
        "type_filter": args.type,
        "total_conversations": total_conversations,
        "unmatched_any_stage": unmatched,
        "funnel": funnel,
    }, indent=2, ensure_ascii=True))


def cmd_lag_report(args):
    """Measure the lag, in days, between a conversation's inserted_at and the first time
    each target tag was added (tag_histories[].inserted_at). This does NOT re-anchor funnel/
    tag counts — inserted_at cohort anchoring stays authoritative for "how many conversations
    this month converted." It answers a different question: how long a cohort needs to mature
    before its downstream tags (Hẹn lịch, Đã lên tv, Đã pt, ...) can be judged fairly, so a
    cohort isn't marked "low conversion" just because it hasn't had time to progress yet.
    Confirmed 2026-08-17: has_phone / recent_phone_numbers carries no timestamp anywhere in the
    API, so lag can only be measured for tag-based criteria, never for raw phone capture."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date()  # exclusive end
    if until_date <= since_date:
        print("ERROR: --until must be after --since")
        sys.exit(1)

    if args.tags:
        target_tags = set(args.tags)
    else:
        # Default: every real tag label referenced by FUNNEL_STAGE_N_TAGS in .env (excludes
        # the special keywords ALL/HAS_PHONE/HAS_AD_ID, which have no tag_histories entries).
        target_tags = set()
        for _, stage_tags in _known_funnel_stages():
            target_tags |= stage_tags - {"ALL", "HAS_PHONE", "HAS_AD_ID"}
        if not target_tags:
            print("ERROR: no --tags given and no FUNNEL_STAGE_N_TAGS configured in scripts/.env")
            sys.exit(1)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    lags = {tag: [] for tag in target_tags}
    total_conversations = 0

    day = since_date
    total_days = (until_date - since_date).days
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by="inserted_at", types=args.type)
            total_conversations += len(convs)
            for c in convs:
                try:
                    conv_inserted = datetime.fromisoformat(c["inserted_at"])
                except (KeyError, ValueError, TypeError):
                    continue
                first_add = {}  # tag text -> earliest 'add' event datetime for this conversation
                for entry in (c.get("tag_histories") or []):
                    payload = entry.get("payload") or {}
                    if payload.get("action") != "add":
                        continue
                    tag_text = (payload.get("tag") or {}).get("text")
                    if tag_text not in target_tags:
                        continue
                    try:
                        tag_time = datetime.fromisoformat(entry["inserted_at"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    if tag_text not in first_add or tag_time < first_add[tag_text]:
                        first_add[tag_text] = tag_time
                for tag_text, tag_time in first_add.items():
                    lag_days = (tag_time - conv_inserted).total_seconds() / 86400
                    if lag_days < 0:
                        continue  # defensive: tag timestamp predates the conversation record
                    lags[tag_text].append(lag_days)
        day = next_day
        if total_days >= 30 and (day - since_date).days % 30 == 0:
            print(f"... scanned through {day.isoformat()} ({(day - since_date).days}/{total_days} days)", file=sys.stderr)

    print(json.dumps({
        "since": args.since,
        "until": args.until,
        "type_filter": args.type,
        "total_conversations_scanned": total_conversations,
        "note": "Lag = (first tag_histories 'add' event for that tag) - (conversation inserted_at). "
                "Use to decide how long to wait before judging a cohort's downstream conversion — "
                "NOT to re-anchor funnel/tag counts, which should stay on inserted_at. low_sample=true "
                "means n<10; treat that tag's numbers as a rough estimate, not a stable maturation window.",
        "lag_by_tag": {tag: _lag_stats(vals) for tag, vals in sorted(lags.items())},
    }, indent=2, ensure_ascii=True))


def cmd_ad_report(args):
    """Like tag-report, but grouped by Meta ad_id instead of tag label. A conversation
    with multiple ad_ids (multiple ad touches before messaging) counts toward each."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date()
    if until_date <= since_date:
        print("ERROR: --until must be after --since")
        sys.exit(1)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    ad_counts = {}
    total_conversations = 0
    total_without_ad = 0

    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by=args.order_by, types=args.type)
            if len(convs) >= 55:
                print(f"WARNING: {day} page {i} returned {len(convs)} — near the 60 cap, may still be truncated.")
            total_conversations += len(convs)
            for c in convs:
                ad_ids = c.get("ad_ids") or []
                if not ad_ids:
                    total_without_ad += 1
                for aid in ad_ids:
                    ad_counts[aid] = ad_counts.get(aid, 0) + 1
        day = next_day

    ranked = sorted(ad_counts.items(), key=lambda kv: -kv[1])
    print(json.dumps({
        "since": args.since,
        "until": args.until,
        "order_by": args.order_by,
        "type_filter": args.type,
        "total_conversations": total_conversations,
        "total_without_ad_id": total_without_ad,
        "ads": [{"ad_id": aid, "count": n} for aid, n in ranked],
    }, indent=2))


def cmd_list_by_ad(args):
    """List conversations whose ad_ids include a given Meta ad_id — the reverse lookup
    of ads-management's campaign/adset IDs back to real Pancake conversations."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date()
    if until_date <= since_date:
        print("ERROR: --until must be after --since")
        sys.exit(1)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    rows = []
    day = since_date
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            convs = _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by="inserted_at", types=args.type)
            for c in convs:
                ad_ids = c.get("ad_ids") or []
                if args.ad_id not in ad_ids:
                    continue
                name = ((c.get("customers") or [{}])[0].get("name")
                        or (c.get("from") or {}).get("name") or "")
                phones = c.get("recent_phone_numbers") or []
                tags = ",".join(t.get("text", "") for t in (c.get("tags") or []) if t)
                link = _conversation_link(page_id, c.get("id"))
                row_base = {
                    "inbox_date": c.get("inserted_at", ""),
                    "name": name,
                    "tags": tags,
                    "ad_ids": ",".join(ad_ids),
                    "link": link,
                }
                if phones:
                    for p in phones:
                        rows.append({**row_base, "phone_number": p.get("phone_number", "")})
                else:
                    rows.append({**row_base, "phone_number": ""})
        day = next_day

    if args.output:
        fieldnames = ["inbox_date", "name", "phone_number", "tags", "ad_ids", "link"]
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({"status": "written", "output": args.output, "count": len(rows)}))
    else:
        print(json.dumps({"count": len(rows), "note": "contains customer PII — avoid printing to console; use --output"}, indent=2))
        for r in rows:
            print(json.dumps(r, ensure_ascii=True))


def cmd_resolve_batch(args):
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("ERROR: input CSV has no rows")
        sys.exit(1)

    link_col = next((c for c in rows[0].keys() if "link" in c.lower()), None)
    if not link_col:
        print("ERROR: no column containing 'link' found in input CSV header.")
        sys.exit(1)

    # Fetch conversations for the requested page (or every configured page) once,
    # build a lookup by conversation id — cheaper than one API call per row.
    target_pages = {args.page: pages[args.page]} if args.page else pages
    convo_index = {}
    since, until = _to_unix(args.since), _to_unix(args.until)
    for i, (page_id, token) in target_pages.items():
        if not page_id or not token:
            continue
        try:
            for c in _fetch_conversations(page_id, token, since=since, until=until, order_by="inserted_at"):
                convo_index[c.get("id")] = c
        except Exception as e:
            print(f"WARNING: failed to fetch page {i} ({page_id}): {e}")

    print(f"Indexed {len(convo_index)} conversations across {len(target_pages)} page(s).")

    resolved = []
    for row in rows:
        link = row.get(link_col, "")
        m = re.search(r"c_id=(\d+_\d+)", link)
        c_id = m.group(1) if m else None
        row["c_id"] = c_id or ""
        row["ad_ids"] = ""
        row["tags"] = ""
        row["sale_rep"] = ""
        row["resolve_status"] = "no_link" if not c_id else ("not_in_recent_list" if c_id not in convo_index else "resolved")
        if c_id and c_id in convo_index:
            c = convo_index[c_id]
            row["ad_ids"] = ",".join(c.get("ad_ids") or [])
            row["tags"] = ",".join(t.get("text", "") for t in (c.get("tags") or []) if t)
            row["sale_rep"] = (c.get("last_sent_by") or {}).get("name", "")
        resolved.append(row)

    fieldnames = list(resolved[0].keys())
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(resolved)

    resolved_count = sum(1 for r in resolved if r["resolve_status"] == "resolved")
    not_in_list_count = sum(1 for r in resolved if r["resolve_status"] == "not_in_recent_list")
    print(json.dumps({
        "status": "done",
        "total_rows": len(resolved),
        "resolved": resolved_count,
        "not_in_recent_list": not_in_list_count,
        "note": "not_in_recent_list means the conversation wasn't in the fetched batch (endpoint returns a limited recent set; date-range pagination not yet confirmed — see references/api-reference.md)",
        "output": args.output,
    }))


def cmd_phone_lag_report(args):
    """Measure lag (whole days) between a conversation's inserted_at and a manually-logged
    phone-capture date from an external CSV (a Google Sheets export) — fills the gap Pancake's
    own API leaves open: has_phone/recent_phone_numbers carries no capture timestamp anywhere
    (confirmed 2026-08-17, see references/api-reference.md). Joins by the pancake.vn conversation
    link in the CSV — same c_id extraction as resolve-batch. Date-only precision: the sheet logs a
    calendar date, not a timestamp, so lag is (phone-log date) - (conversation's inserted_at date),
    not fractional like tag-based lag-report."""
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    with open(args.input, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("ERROR: input CSV has no rows")
        sys.exit(1)

    link_col = next((c for c in rows[0].keys() if "link" in c.lower()), None)
    if not link_col:
        print("ERROR: no column containing 'link' found in input CSV header.")
        sys.exit(1)
    date_col = next((c for c in rows[0].keys() if "ngày" in c.lower() or "ngay" in c.lower() or "date" in c.lower()), None)
    if not date_col:
        print("ERROR: no column containing 'ngày'/'ngay'/'date' found in input CSV header.")
        sys.exit(1)

    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date()
    if until_date <= since_date:
        print("ERROR: --until must be after --since")
        sys.exit(1)

    target_pages = {args.page: pages[args.page]} if args.page else pages
    convo_index = {}
    day = since_date
    total_days = (until_date - since_date).days
    while day < until_date:
        next_day = day + timedelta(days=1)
        since_ts, until_ts = _to_unix(day.isoformat()), _to_unix(next_day.isoformat())
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            for c in _fetch_conversations(page_id, token, since=since_ts, until=until_ts, order_by="inserted_at"):
                convo_index[c.get("id")] = c
        day = next_day
        if total_days >= 30 and (day - since_date).days % 30 == 0:
            print(f"... indexed through {day.isoformat()} ({(day - since_date).days}/{total_days} days)", file=sys.stderr)

    print(f"Indexed {len(convo_index)} conversations across {len(target_pages)} page(s).", file=sys.stderr)

    lags = []
    suspicious = []
    status_counts = {"resolved": 0, "no_link": 0, "not_in_recent_list": 0, "bad_date": 0}
    output_rows = []

    for row in rows:
        link = row.get(link_col, "") or ""
        m = re.search(r"c_id=(\d+_\d+)", link)
        c_id = m.group(1) if m else None

        phone_date_str = (row.get(date_col) or "").strip()
        phone_date = None
        if phone_date_str:
            # Sheet's date column format is user-controlled and has changed at least once —
            # confirmed 2026-08-17 the sheet was reformatted from majority D/M/Y to majority
            # M/D/Y. Try M/D/Y first (current convention), then D/M/Y, then ISO — whichever
            # parses. A row where day/month are both <=12 will parse under either order without
            # erroring, so this can't detect a stray leftover-format row on its own; the
            # suspicious_excluded check below (lag outside -1..60 days) is what catches those.
            for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    phone_date = datetime.strptime(phone_date_str, fmt).date()
                    break
                except ValueError:
                    continue

        if not c_id:
            status = "no_link"
        elif c_id not in convo_index:
            status = "not_in_recent_list"
        elif phone_date is None:
            status = "bad_date"
        else:
            status = "resolved"
        status_counts[status] += 1

        lag_days = None
        if status == "resolved":
            try:
                conv_date = datetime.fromisoformat(convo_index[c_id]["inserted_at"]).date()
                lag_days = (phone_date - conv_date).days
            except (KeyError, ValueError, TypeError):
                lag_days = None
            if lag_days is not None:
                if lag_days < -1 or lag_days > 60:
                    suspicious.append(lag_days)
                else:
                    lags.append(lag_days)

        output_rows.append({"c_id": c_id or "", "resolve_status": status, "lag_days": lag_days if lag_days is not None else ""})

    if args.output:
        fieldnames = list(rows[0].keys()) + ["c_id", "resolve_status", "lag_days"]
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row, extra in zip(rows, output_rows):
                writer.writerow({**row, **extra})

    print(json.dumps({
        "since": args.since,
        "until": args.until,
        "total_rows": len(rows),
        "status_counts": status_counts,
        "suspicious_excluded": len(suspicious),
        "phone_lag": _lag_stats(lags),
        "note": "Lag = (ngày ghi nhận SĐT trong sheet) - (ngày inserted_at của conversation), tính "
                "theo NGÀY nguyên (không có giờ vì nguồn chỉ ghi ngày) — khác lag-report (theo tag, "
                "có giờ). suspicious_excluded = số dòng bị loại khỏi phone_lag vì lag <-1 hoặc >60 "
                "ngày, thường do sheet lẫn định dạng ngày D/M/Y và M/D/Y chứ không phải hành vi thật "
                "— xem cột resolve_status/lag_days trong --output để rà lại từng dòng nghi vấn.",
        "output": args.output,
    }, indent=2, ensure_ascii=True))


RECHAT_NOTE_TEMPLATE = ("⚠️ Rechat: đã {days} ngày chưa liên hệ lại (cập nhật lần cuối {last_update}). "
                         "Vui lòng chăm sóc/tư vấn lại khách hàng.")


def cmd_rechat_report(args):
    """Find "sale bỏ quên" conversations — no reply/consultation in more than --stale-days
    (default 30) — so they can be re-nurtured ("rechat"). Queries with order_by=updated_at,
    so since/until filter directly against updated_at (confirmed behavior, see
    references/api-reference.md) instead of scanning inserted_at across all history and
    filtering client-side — this targets exactly the stale set: since=--since, until=today
    minus --stale-days. Still day-chunks to respect the 60/call cap.

    Excludes any conversation carrying a tag in --exclude-tags (default: RÁC, Đã pt — already
    spam-marked or already-converted leads don't need re-nurturing). Conversations that both
    have a captured phone number AND carry --priority-tag (default: LIÊN LẠC KHÁC) are flagged
    priority=true and sorted first, per user instruction to scan those first — they're contactable
    leads that got tagged for other follow-up but then went cold.

    --add-note (opt-in, off by default) additionally writes a Pancake note to each matched
    conversation's customer profile via the confirmed notes endpoint (add_note) — so the sale
    rep sees the reminder directly inside the conversation they already work in, not just in a
    separate CSV. NOT idempotent: there is no notes-listing endpoint to detect an existing rechat
    note, so re-running --add-note over an overlapping --since range adds a duplicate note each
    time — run it periodically (e.g. weekly) with non-overlapping windows, not on every report run.

    --add-tag (opt-in, off by default) instead/additionally attaches a dated tag (default
    "R-DDMMY", e.g. "R-24086" for 2026-08-24 — user-specified format) to each matched
    conversation via the confirmed tags endpoint (set_conversation_tag). Unlike --add-note this
    IS idempotent (confirmed 2026-08-24: re-adding an already-present tag is a no-op, same
    success response) — safe to re-run. The tag must already exist on each target page (created
    manually in the Pancake UI — no tag-creation endpoint is available); a page missing the tag
    is skipped for tagging (with a warning) but its conversations still appear in the report/CSV.
    Presence of this tag in a later scan's `tags` column is how you tell "already flagged for
    rechat on this date" from "never flagged".
    """
    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)

    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
    now_bkk = datetime.now(LOCAL_TZ)
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)  # updated_at/inserted_at are naive UTC strings — confirmed 2026-08-24
    cutoff_date = (now_bkk - timedelta(days=args.stale_days)).date()
    if cutoff_date <= since_date:
        print(f"ERROR: --since ({since_date}) must be before the stale cutoff ({cutoff_date} = today - {args.stale_days} days)")
        sys.exit(1)

    exclude_tags = set(t.strip() for t in args.exclude_tags.split(",") if t.strip())
    priority_tag = args.priority_tag

    target_pages = {args.page: pages[args.page]} if args.page else pages

    # Resolve the rechat tag's id on each target page up front (tag must already exist —
    # created manually, no create-tag endpoint available). A page missing the tag is tagged
    # nowhere (still reported/CSV'd) — warn once here rather than per-conversation.
    tag_ids_by_page = {}
    if args.add_tag:
        tag_name = args.tag_name or rechat_tag_name()
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            try:
                tid = find_tag_id(page_id, tag_name)
            except RuntimeError as e:
                print(f"WARNING: could not fetch tags for {page_name(page_id)}: {e}", file=sys.stderr)
                continue
            if tid is None:
                print(f"WARNING: tag {tag_name!r} not found on {page_name(page_id)} — create it manually "
                      "in the Pancake UI first; conversations on this page will be reported but not tagged.", file=sys.stderr)
                continue
            tag_ids_by_page[page_id] = tid

    rows = []
    # Kept separate from `rows` (rather than adding extra columns) so the CSV schema doesn't
    # change based on whether --add-note/--add-tag was passed.
    note_targets = []
    tag_targets = []
    total_scanned = 0
    total_excluded = 0
    notes_skipped_no_customer = 0

    day = since_date
    total_days = (cutoff_date - since_date).days
    while day < cutoff_date:
        next_day = day + timedelta(days=1)
        since_ts = _to_unix(day.isoformat())
        until_ts = _to_unix(next_day.isoformat())
        for i, (page_id, token) in target_pages.items():
            if not page_id or not token:
                continue
            # fetch_conversations_complete auto-subdivides the day window when it hits the 60/call
            # cap (confirmed 2026-08-24 this matters: a real 8-month rechat-report scan had 8 days
            # at/near the cap with the plain _fetch_conversations, risking silently dropped leads —
            # the exact failure mode already documented for the auto-spam job, see api-reference.md).
            convs = fetch_conversations_complete(page_id, token, since_ts, until_ts, order_by="updated_at", types=args.type)
            total_scanned += len(convs)
            for c in convs:
                labels = set(t.get("text") for t in (c.get("tags") or []) if t)
                if labels & exclude_tags:
                    total_excluded += 1
                    continue
                has_phone = bool(c.get("has_phone"))
                is_priority = has_phone and priority_tag in labels
                try:
                    days_stale = round((now_utc_naive - datetime.fromisoformat(c["updated_at"])).total_seconds() / 86400, 1)
                except (KeyError, ValueError, TypeError):
                    days_stale = ""
                name = ((c.get("customers") or [{}])[0].get("name")
                        or (c.get("from") or {}).get("name") or "")
                phones = c.get("recent_phone_numbers") or []
                phone_str = ",".join(p.get("phone_number", "") for p in phones)
                sale_rep = (c.get("last_sent_by") or {}).get("name", "")
                link = _conversation_link(page_id, c.get("id"))
                rows.append({
                    "priority": is_priority,
                    "days_stale": days_stale,
                    "inserted_at": c.get("inserted_at", ""),
                    "updated_at": c.get("updated_at", ""),
                    "name": name,
                    "phone_number": phone_str,
                    "has_phone": has_phone,
                    "tags": ",".join(sorted(labels)),
                    "sale_rep": sale_rep,
                    "link": link,
                })

                if args.add_note:
                    customers = c.get("customers") or []
                    customer_id = customers[0].get("id") if customers else None
                    if not customer_id:
                        notes_skipped_no_customer += 1
                        print(f"WARNING: c_id {c.get('id')} matched but has no page-scoped customer id — note skipped", file=sys.stderr)
                        continue
                    message = RECHAT_NOTE_TEMPLATE.format(
                        days=days_stale if days_stale != "" else "?",
                        last_update=c.get("updated_at", "")[:10],
                    )
                    note_targets.append({"page_id": page_id, "customer_id": customer_id, "c_id": c.get("id"), "message": message})

                if args.add_tag and page_id in tag_ids_by_page:
                    tag_targets.append({"page_id": page_id, "c_id": c.get("id"), "tag_id": tag_ids_by_page[page_id]})
        day = next_day
        if total_days >= 30 and (day - since_date).days % 30 == 0:
            print(f"... scanned through {day.isoformat()} ({(day - since_date).days}/{total_days} days)", file=sys.stderr)

    rows.sort(key=lambda r: (not r["priority"], -(r["days_stale"] if isinstance(r["days_stale"], (int, float)) else 0)))
    priority_count = sum(1 for r in rows if r["priority"])

    notes_added = 0
    notes_failed = 0
    if args.add_note:
        for t in note_targets:
            try:
                add_note(t["page_id"], t["customer_id"], t["message"])
                notes_added += 1
            except RuntimeError as e:
                notes_failed += 1
                print(f"WARNING: note failed for c_id {t['c_id']}: {e}", file=sys.stderr)

    tags_added = 0
    tags_failed = 0
    if args.add_tag:
        for t in tag_targets:
            try:
                add_tag_to_conversation(t["page_id"], t["c_id"], t["tag_id"])
                tags_added += 1
            except RuntimeError as e:
                tags_failed += 1
                print(f"WARNING: tag failed for c_id {t['c_id']}: {e}", file=sys.stderr)

    summary = {
        "since": args.since,
        "stale_cutoff": cutoff_date.isoformat(),
        "stale_days": args.stale_days,
        "type_filter": args.type,
        "total_scanned": total_scanned,
        "total_excluded": total_excluded,
        "exclude_tags": sorted(exclude_tags),
        "priority_tag": priority_tag,
        "matched": len(rows),
        "priority_matched": priority_count,
    }
    if args.add_note:
        summary["add_note"] = True
        summary["notes_added"] = notes_added
        summary["notes_failed"] = notes_failed
        summary["notes_skipped_no_customer_id"] = notes_skipped_no_customer
    if args.add_tag:
        summary["add_tag"] = True
        summary["tag_name"] = args.tag_name or rechat_tag_name()
        summary["tagged_pages"] = sorted(page_name(pid) for pid in tag_ids_by_page)
        summary["tags_added"] = tags_added
        summary["tags_failed"] = tags_failed

    if args.output:
        fieldnames = ["priority", "days_stale", "inserted_at", "updated_at", "name",
                      "phone_number", "has_phone", "tags", "sale_rep", "link"]
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({"status": "written", "output": args.output, **summary}, indent=2, ensure_ascii=True))
    else:
        print(json.dumps({**summary, "note": "contains customer PII — avoid printing to console; use --output"}, indent=2, ensure_ascii=True))
        for r in rows:
            print(json.dumps(r, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description="Pancake API client")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("test-connection", help="Verify page_access_token_N values work")

    lc = sub.add_parser("list-conversations", help="List conversations for one configured page")
    lc.add_argument("--page", type=int, default=1, help="Index matching PANCAKE_PAGE_ID_N in .env (default 1)")
    lc.add_argument("--output", default=None, help="Write full JSON to file (contains PII — do not print to console)")
    lc.add_argument("--since", default=None, help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (UTC)")
    lc.add_argument("--until", default=None, help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (UTC)")
    lc.add_argument("--order-by", default="inserted_at", choices=["inserted_at", "updated_at"],
                     help="Which timestamp since/until filters against. Default inserted_at ('new conversations') "
                          "— omitting this param entirely (not just picking updated_at) changes since/until semantics, "
                          "confirmed 2026-08-14: same day-window query returned 11 (unspecified) vs 4 (inserted_at).")
    lc.add_argument("--type", default=None, type=lambda s: s.split(","),
                     help="Comma-separated conversation types (INBOX, COMMENT, COMMENT_LIVESTREAM, POST). Default: all types.")
    lc.add_argument("--tags", default=None, help="Comma-separated tag IDs to filter by")

    cc = sub.add_parser("count-conversations", help="Count conversations over a date range (auto-chunks by day to avoid the 60/call cap)")
    cc.add_argument("--month", default=None,
                    help="YYYY-MM instead of --since/--until — the whole month, or up to "
                         "right now if it's the current month")
    cc.add_argument("--since", default=None, help="YYYY-MM-DD, inclusive (with --until; omit if using --month)")
    cc.add_argument("--until", default=None, help="YYYY-MM-DD, exclusive (e.g. 2026-08-15 to include all of 2026-08-14)")
    cc.add_argument("--order-by", default="inserted_at", choices=["inserted_at", "updated_at"])
    cc.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default sums all")
    cc.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","),
                     help="Comma-separated conversation types (INBOX, COMMENT, COMMENT_LIVESTREAM, POST). "
                          "Default INBOX only — real customer conversations, excludes public comments/posts. "
                          "Confirmed 2026-08-14: unfiltered counts include COMMENT entries mixed in.")

    tr = sub.add_parser("tag-report", help="Count conversations grouped by tag over a date range (auto-chunks by day)")
    tr.add_argument("--month", default=None,
                    help="YYYY-MM instead of --since/--until — the whole month, or up to "
                         "right now if it's the current month")
    tr.add_argument("--since", default=None, help="YYYY-MM-DD, inclusive (with --until; omit if using --month)")
    tr.add_argument("--until", default=None, help="YYYY-MM-DD, exclusive")
    tr.add_argument("--order-by", default="inserted_at", choices=["inserted_at", "updated_at"])
    tr.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default sums all")
    tr.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","),
                     help="Single conversation type to filter (INBOX, COMMENT, COMMENT_LIVESTREAM, POST). Default INBOX.")
    tr.add_argument("--all-of", default=None, type=lambda s: s.split(","),
                     help="Comma-separated tag labels — also report the count of conversations having ALL of them (AND / intersection).")
    tr.add_argument("--any-of", default=None, type=lambda s: s.split(","),
                     help="Comma-separated tag labels — count of conversations having AT LEAST ONE (OR). Combinable with --all-of/--exclude.")
    tr.add_argument("--exclude", default=None, type=lambda s: s.split(","),
                     help="Comma-separated tag labels — count of conversations having NONE of these. Combinable with --all-of/--any-of.")

    lbt = sub.add_parser("list-by-tag", help="List conversations matching a tag label with inbox date/name/phone/link (contains PII)")
    lbt.add_argument("--tag", required=True, help="Exact tag label to match, e.g. \"Đã pt\"")
    lbt.add_argument("--month", default=None,
                     help="YYYY-MM instead of --since/--until — the whole month, or up to "
                          "right now if it's the current month")
    lbt.add_argument("--since", default=None, help="YYYY-MM-DD, inclusive (with --until; omit if using --month)")
    lbt.add_argument("--until", default=None, help="YYYY-MM-DD, exclusive")
    lbt.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default checks all")
    lbt.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","))
    lbt.add_argument("--output", default=None, help="Write CSV to file (recommended — contains PII, avoid printing to console)")

    wt = sub.add_parser("watch-tag", help="Report conversations tagged --tag (scanned across "
                        "the last --lookback-days, not just today) that a previous run hasn't "
                        "seen yet - for polling from a scheduler")
    wt.add_argument("--tag", default="QM", help="Exact tag label to watch for (default QM)")
    wt.add_argument("--lookback-days", type=int, default=14,
                    help="How many days back to re-scan for a newly-added tag on an older "
                         "conversation (default 14). Larger = catches later retroactive "
                         "tagging but costs more API calls per poll.")
    wt.add_argument("--state-file", default=None,
                    help="Path to the seen-conversations state file (default: watch_tag_state.json next to this script)")

    fr = sub.add_parser("funnel-report", help="Conversion funnel counts per FUNNEL_STAGE_N defined in .env")
    fr.add_argument("--month", default=None,
                    help="YYYY-MM instead of --since/--until — the whole month, or up to "
                         "right now if it's the current month")
    fr.add_argument("--since", default=None, help="YYYY-MM-DD, inclusive (with --until; omit if using --month)")
    fr.add_argument("--until", default=None, help="YYYY-MM-DD, exclusive")
    fr.add_argument("--order-by", default="inserted_at", choices=["inserted_at", "updated_at"])
    fr.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default sums all")
    fr.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","))

    lr = sub.add_parser("lag-report", help="Days from conversation inserted_at to first tag-add event, per tag (auto-chunks by day) — tells you how long a cohort needs to mature before judging downstream conversion")
    lr.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive")
    lr.add_argument("--until", required=True, help="YYYY-MM-DD, exclusive")
    lr.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default sums all")
    lr.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","))
    lr.add_argument("--tags", default=None, type=lambda s: s.split(","),
                     help="Comma-separated tag labels to measure. Default: every real tag label referenced by "
                          "FUNNEL_STAGE_N_TAGS in .env (excludes ALL/HAS_PHONE/HAS_AD_ID, which have no tag_histories).")

    ar = sub.add_parser("ad-report", help="Count conversations grouped by Meta ad_id over a date range (auto-chunks by day)")
    ar.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive")
    ar.add_argument("--until", required=True, help="YYYY-MM-DD, exclusive")
    ar.add_argument("--order-by", default="inserted_at", choices=["inserted_at", "updated_at"])
    ar.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default sums all")
    ar.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","))

    lba = sub.add_parser("list-by-ad", help="List conversations whose ad_ids include a given Meta ad_id (contains PII)")
    lba.add_argument("--ad-id", required=True, help="Meta ad_id, e.g. 120249531888710690")
    lba.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive")
    lba.add_argument("--until", required=True, help="YYYY-MM-DD, exclusive")
    lba.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default checks all")
    lba.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","))
    lba.add_argument("--output", default=None, help="Write CSV to file (recommended — contains PII, avoid printing to console)")

    rb = sub.add_parser("resolve-batch", help="Resolve ad_ids/tags/sale_rep for every row in a lead CSV")
    rb.add_argument("--input", required=True, help="CSV with a LINK column containing pancake.vn URLs")
    rb.add_argument("--output", required=True, help="Output CSV path")
    rb.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default checks all")
    rb.add_argument("--since", default=None, help="YYYY-MM-DD — narrow the fetch window to match your lead sheet's date range")
    rb.add_argument("--until", default=None, help="YYYY-MM-DD")

    pl = sub.add_parser("phone-lag-report", help="Lag (days) from conversation inserted_at to a manually-logged phone-capture date in an external CSV — fills the gap Pancake's API leaves for phone timestamps")
    pl.add_argument("--input", required=True, help="CSV with a LINK column (pancake.vn URLs) and a Ngày/date column")
    pl.add_argument("--output", default=None, help="Write per-row c_id/resolve_status/lag_days CSV (contains PII — do not print to console)")
    pl.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default checks all")
    pl.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive — must cover the sheet's date range")
    pl.add_argument("--until", required=True, help="YYYY-MM-DD, exclusive")

    rr = sub.add_parser("rechat-report", help="Find conversations not updated in over --stale-days (sale bỏ quên / forgotten leads to re-nurture) — excludes RÁC/Đã pt, flags has_phone+LIÊN LẠC KHÁC as priority (contains PII)")
    rr.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive — how far back to look for stale conversations (by updated_at)")
    rr.add_argument("--stale-days", type=int, default=30, help="Conversations not updated in this many days count as forgotten (default 30)")
    rr.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default checks all")
    rr.add_argument("--type", default=["INBOX"], type=lambda s: s.split(","))
    rr.add_argument("--exclude-tags", default="RÁC,Đã pt", help="Comma-separated tag labels to exclude (exact match, default: RÁC,Đã pt)")
    rr.add_argument("--priority-tag", default="LIÊN LẠC KHÁC", help="Tag label that, combined with has_phone, marks a row priority=true and sorts it first")
    rr.add_argument("--output", default=None, help="Write CSV to file (recommended — contains PII, avoid printing to console)")
    rr.add_argument("--add-note", action="store_true",
                     help="MUTATES data: also write a Pancake note (⚠️ Rechat: ...) to each matched conversation's "
                          "customer profile via the confirmed notes endpoint, so sale sees the reminder inside the "
                          "conversation itself. Default: off (report/CSV only). Not idempotent — re-running with an "
                          "overlapping --since adds a duplicate note each time; run periodically, not on every call.")
    rr.add_argument("--add-tag", action="store_true",
                     help="MUTATES data: attach a dated tag (default: today's R-DDMMY, e.g. R-24086) to each matched "
                          "conversation via the confirmed tags endpoint. Default: off. Idempotent (safe to re-run). "
                          "The tag must already exist on each target page — create it manually in Pancake first; "
                          "pages missing it are skipped for tagging (still reported) with a warning.")
    rr.add_argument("--tag-name", default=None, help="Override the tag label to attach with --add-tag (default: today's R-DDMMY)")

    args = parser.parse_args()
    if args.command == "test-connection":
        cmd_test_connection(args)
    elif args.command == "list-conversations":
        cmd_list_conversations(args)
    elif args.command == "count-conversations":
        cmd_count_conversations(args)
    elif args.command == "tag-report":
        cmd_tag_report(args)
    elif args.command == "watch-tag":
        cmd_watch_tag(args)
    elif args.command == "list-by-tag":
        cmd_list_by_tag(args)
    elif args.command == "funnel-report":
        cmd_funnel_report(args)
    elif args.command == "lag-report":
        cmd_lag_report(args)
    elif args.command == "ad-report":
        cmd_ad_report(args)
    elif args.command == "list-by-ad":
        cmd_list_by_ad(args)
    elif args.command == "resolve-batch":
        cmd_resolve_batch(args)
    elif args.command == "phone-lag-report":
        cmd_phone_lag_report(args)
    elif args.command == "rechat-report":
        cmd_rechat_report(args)


if __name__ == "__main__":
    main()
