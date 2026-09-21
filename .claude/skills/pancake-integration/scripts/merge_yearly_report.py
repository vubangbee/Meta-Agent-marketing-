#!/usr/bin/env python3
"""Consolidate per-month spam reports for a year into ONE yearly file.

Usage:
  python merge_yearly_report.py --year 2025
  python merge_yearly_report.py --year 2025 --dry-run

Merges plans/reports/report-{YEAR}-{MM}-pancake-spam-daily.md (12 files) into
plans/reports/report-{YEAR}-pancake-spam-daily.md, then deletes the monthly files.

Safe to re-run: it also reads the yearly file if it already exists, so a later run folds
in any straggler monthly files (e.g. ones a still-running backfill recreated after an
earlier merge) without losing what was already consolidated.

Dated sections are keyed by date and DEDUPED — when the same date appears more than once
(the original day-chunked backfill wrote one section, then the hourly re-scan of a
60/call-capped day appended a second, more complete one), the LAST occurrence wins, since
later passes are supersets. Non-dated sections ("## Retry note", "## Data completeness
warning") are preserved verbatim in an appendix, tagged with the month they came from.
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPORTS_DIR = PROJECT_ROOT / "plans" / "reports"

# A section = a "## " heading and everything up to the next "## " heading (or EOF).
SECTION_RE = re.compile(r"^## .*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
DATE_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b")


def _split_sections(text):
    """Return (dated, undated): dated is [(date_str, section_text)], undated is [section_text]."""
    dated, undated = [], []
    for m in SECTION_RE.finditer(text):
        section = m.group(0)
        d = DATE_HEADING_RE.match(section)
        (dated.append((d.group(1), section)) if d else undated.append(section))
    return dated, undated


def main():
    parser = argparse.ArgumentParser(description="Merge monthly spam reports into one yearly file")
    parser.add_argument("--year", required=True, help="e.g. 2025")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    yearly_path = REPORTS_DIR / f"report-{args.year}-pancake-spam-daily.md"
    monthly_paths = sorted(REPORTS_DIR.glob(f"report-{args.year}-[0-1][0-9]-pancake-spam-daily.md"))

    if not monthly_paths and not yearly_path.exists():
        print(f"ERROR: no report files found for {args.year} in {REPORTS_DIR}")
        sys.exit(1)

    by_date = {}        # date -> section text (last write wins)
    notes = []          # (source label, section text)

    # Seed from the existing yearly file first so a re-run keeps prior content, then let the
    # monthly files (which are newer if a job recreated them) overwrite matching dates.
    sources = ([(yearly_path, "merged")] if yearly_path.exists() else []) + \
              [(p, p.stem.split("-")[2]) for p in monthly_paths]

    for path, label in sources:
        dated, undated = _split_sections(path.read_text(encoding="utf-8"))
        for d, section in dated:
            by_date[d] = section
        for section in undated:
            if section not in [s for _, s in notes]:  # the yearly file re-reads its own appendix
                notes.append((label, section))

    days_with_rows = sum(1 for s in by_date.values() if "| Khách hàng |" in s)
    total_rows = sum(s.count("\n| [") for s in by_date.values())

    print(f"year={args.year} monthly_files={len(monthly_paths)} "
          f"dates={len(by_date)} days_with_matches={days_with_rows} rows={total_rows} notes={len(notes)}")

    if args.dry_run:
        print("(dry run — nothing written)")
        return

    out = [f"# Pancake spam report — {args.year}", ""]
    for d in sorted(by_date):
        out.append(by_date[d].rstrip() + "\n")
    if notes:
        out.append("---\n")
        out.append("# Notes & corrections\n")
        for label, section in notes:
            # Re-tag which month the note came from; the yearly file has no month in its name.
            out.append(section.rstrip().replace("## ", f"## [{args.year}-{label}] ", 1) + "\n")

    yearly_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    for p in monthly_paths:
        p.unlink()

    print(f"written: {yearly_path}")
    print(f"deleted {len(monthly_paths)} monthly files")


if __name__ == "__main__":
    main()
