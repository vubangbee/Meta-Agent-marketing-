#!/usr/bin/env python3
"""17:00 same-day job: find TODAY's conversations tagged a given label (default "RÁC")
created from 00:00:00 up to (not including) 17:00:00 local time, move each to spam, and
append a dated section to ONE Markdown report file per calendar month, in plans/reports/
(report-YYYY-MM-pancake-spam-daily.md) — a month's worth of daily runs stays in one file
instead of accumulating one file per day.

This exists alongside pancake_auto_spam_tagged.py (the 08:30 job, which processes the FULL
previous day) — this is a same-day pass so a conversation tagged in the morning/afternoon
doesn't sit un-spammed until the next day's run. A conversation already moved to spam here
is a harmless no-op if tomorrow's 08:30 job re-matches it on the same date's tag
(toggle_move_to_spam is confirmed idempotent-set, not a true toggle — see
references/api-reference.md).

Usage:
  python pancake_spam_report.py
  python pancake_spam_report.py --tag RÁC --page 1
  python pancake_spam_report.py --date 2026-08-21 --dry-run   # backfill/testing, no report written

Requires: pip install requests
Env vars: same as pancake_auto_spam_tagged.py (scripts/.env).
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from pancake_client import PAGE_SLUGS, _known_pages, _load_env, _to_unix, page_name
from pancake_auto_spam_tagged import find_and_spam_tagged

_load_env()

PROJECT_ROOT = Path(__file__).resolve().parents[4]  # scripts -> ak-pancake-integration -> skills -> .claude -> root
REPORTS_DIR = PROJECT_ROOT / "plans" / "reports"


def _conversation_link(page_id, c_id):
    slug = PAGE_SLUGS.get(page_id)
    return f"https://pancake.vn/{slug}?c_id={c_id}" if slug else c_id


FULL_DAY_WINDOW = "00:00–23:59:59"
AFTERNOON_CUTOFF_WINDOW = "00:00–16:59:59"


ROW_RE = re.compile(r"^\| \[.*?\]\(.*?c_id=(?P<c_id>[\w_]+)\).*?\| (?P<inserted_at>[\d\-T:.]+) \| (?P<status>\w+) \|$")


def _parse_existing_rows(section_text):
    """Extract {c_id: (inserted_at, status, row_markdown)} from an already-written day section."""
    rows = {}
    for line in section_text.splitlines():
        m = ROW_RE.match(line)
        if m:
            rows[m.group("c_id")] = (m.group("inserted_at"), m.group("status"), line)
    return rows


def _write_report(target_date, tag, matched, results, window_label=FULL_DAY_WINDOW):
    """Write a per-day section into ONE report file per calendar month (report-YYYY-MM-...),
    instead of one file per day — a month's worth of daily runs stays in a single file.

    `window_label` must describe the time range the caller actually queried, and appears in the
    section heading. The 17:00 same-day job passes AFTERNOON_CUTOFF_WINDOW (it can only see
    00:00-16:59:59); the 08:30 next-morning job and any backfill pass FULL_DAY_WINDOW.

    If a section for this date already exists, its rows are MERGED with the new ones, keyed by
    conversation id (new wins on conflict), and the summary counts are recomputed from the merged
    set. Merging — rather than replacing the section wholesale — is required because a single
    date legitimately gets written more than once by different callers:
      * the 17:00 partial-day run, then the next morning's 08:30 full-day run (superset), and
      * one run per Facebook Page when a backfill is sharded by page.
    An earlier version replaced the section instead, which silently dropped every other page's
    rows for that date (caught 2026-08-24 after a page-2 re-scan wiped page-1 rows on 8 dates).
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"report-{target_date.strftime('%Y-%m')}-pancake-spam-daily.md"

    pattern = re.compile(
        rf"^## {re.escape(target_date.isoformat())}\b.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else None
    prior_match = pattern.search(existing) if existing else None

    # Start from whatever is already recorded for this date, then layer this run's rows on top.
    rows = _parse_existing_rows(prior_match.group(0)) if prior_match else {}
    for r in results:
        link = _conversation_link(r["page_id"], r["c_id"])
        label = r.get("name") or r["c_id"]  # fall back to c_id if the customer has no name on file
        line = f"| [{label}]({link}) | {page_name(r['page_id'])} | {r['inserted_at']} | {r['status']} |"
        rows[r["c_id"]] = (r["inserted_at"], r["status"], line)

    ordered = sorted(rows.items(), key=lambda kv: kv[1][0])
    n_ok = sum(1 for _, (_, st, _) in ordered if st == "ok")
    n_err = len(ordered) - n_ok
    errors = [r for r in results if r["status"] == "error"]

    section = [
        f"## {target_date.isoformat()} {window_label}",
        "",
        f"Tag: `{tag}` | Matched: {len(ordered)} | Moved to spam: {n_ok} | Errors: {n_err}",
        "",
    ]
    if ordered:
        section.append("| Khách hàng | Page | inserted_at | status |")
        section.append("|---|---|---|---|")
        section.extend(line for _, (_, _, line) in ordered)
    else:
        section.append("No conversations matched.")

    if errors:
        section.append("")
        section.append("### Errors")
        for e in errors:
            section.append(f"- `{e['c_id']}`: {e['error']}")
    section.append("")

    section_text = "\n".join(section) + "\n"

    if existing is None:
        header = f"# Pancake spam report — {target_date.strftime('%B %Y')}\n\n"
        report_path.write_text(header + section_text, encoding="utf-8")
        return report_path

    # Swap the rebuilt (merged) section in place, preserving date order. Only date-headed
    # sections match the pattern, so manually-added "## Retry note" / "## ⚠️ Data completeness
    # warning" blocks are never clobbered.
    if prior_match:
        report_path.write_text(pattern.sub(lambda _: section_text, existing, count=1), encoding="utf-8")
    else:
        with report_path.open("a", encoding="utf-8") as f:
            f.write(section_text)

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Same-day (00:00-16:59:59) tagged-conversation spam + report")
    parser.add_argument("--tag", default="RÁC", help="Exact tag label to match (case-sensitive, default: RÁC)")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD to process instead of today (for backfill/testing)")
    parser.add_argument("--page", type=int, default=None, help="Restrict to one configured page index; default all configured pages")
    parser.add_argument("--dry-run", action="store_true", help="List matches without calling toggle_move_to_spam or writing a report")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()
    since = _to_unix(f"{target_date.isoformat()}T00:00:00")
    until = _to_unix(f"{target_date.isoformat()}T17:00:00")  # exclusive upper bound — covers up to 16:59:59

    pages = _known_pages()
    if not pages:
        print("ERROR: no pages configured in scripts/.env")
        sys.exit(1)
    target_pages = {args.page: pages[args.page]} if args.page else pages

    matched, results = find_and_spam_tagged(args.tag, since, until, target_pages, dry_run=args.dry_run)

    ok = sum(1 for r in results if r["status"] == "ok")
    errors = [r for r in results if r["status"] == "error"]
    print(f"Date: {target_date.isoformat()} 00:00-16:59:59 | Tag: {args.tag!r} | "
          f"Matched: {len(matched)} | Spammed: {ok} | Errors: {len(errors)}", file=sys.stderr)

    if args.dry_run:
        return

    report_path = _write_report(target_date, args.tag, matched, results,
                                 window_label=AFTERNOON_CUTOFF_WINDOW)
    print(f"Report written: {report_path}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
