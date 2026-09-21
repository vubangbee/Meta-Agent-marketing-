---
name: pancake-integration
description: Resolve Facebook ad attribution (ad_id) and sale-assigned tags for Pancake CRM/Messenger conversations, confirmed working against the real Pancake public API (pages.fm) as of 2026-08-14. Use when reconciling lead/revenue Google Sheets against specific Meta Ads campaigns/targets. Pairs with ads-management for cost-per-lead / ROAS-per-target reporting.
argument-hint: "[conversation-url-or-id]"
license: MIT
metadata:
  author: vubangdigital
  version: "1.2.0"
  status: confirmed-working
---

# Pancake Integration

Query the Pancake public API for conversation data — including real Meta ad attribution (`ad_ids`), sale-assigned tags, captured phone numbers, and assigned sale rep — and reconcile it against lead/revenue Google Sheets.

## Why this exists

Pancake conversation links (e.g. `https://pancake.vn/bacsidacquang?c_id=108067022357425_27629098500062094`) don't tell you which Meta ad drove them just by looking at the link. The Pancake API does have that data (`ad_ids` field on the conversation object) — but it took real trial-and-error against a live key to find the right endpoint, auth token type, and query params. That work is done; this skill captures the result so it doesn't need repeating.

## Setup

1. In Pancake, for **each Facebook Page** you manage, get its **"Public API access token"** (per-page, not the account login session token — those look different and the session token does NOT work with this API).
2. Copy `scripts/.env.example` to `scripts/.env`. For each page, add a numbered pair:
   ```
   PANCAKE_PAGE_ID_1=108067022357425
   page_access_token_1=<token for that page>
   PANCAKE_PAGE_ID_2=...
   page_access_token_2=...
   ```
3. Verify: `python3 scripts/pancake_client.py test-connection` — should print `ok=True` for each configured page.

## Usage

```bash
# Verify all configured pages work
python3 scripts/pancake_client.py test-connection

# List recent conversations for one page (console output is PII-safe: id/ad_ids/tags/has_phone only)
python3 scripts/pancake_client.py list-conversations --page 1 --since 2026-08-01 --until 2026-08-15

# Count conversations over a date range, summed across all configured pages (auto-chunks by
# day to stay under the API's confirmed 60-per-call cap — never query a wide range in one shot).
# Defaults to --type INBOX (excludes COMMENT/POST/COMMENT_LIVESTREAM — not real conversations).
# Output includes total/with_phone per day and per page (has_phone field on each conversation).
python3 scripts/pancake_client.py count-conversations --since 2026-08-01 --until 2026-08-15

# Full conversation objects (contain customer PII) — write to file, never print
python3 scripts/pancake_client.py list-conversations --page 1 --output conversations.json

# Reconcile a lead Google Sheet (needs a column with "link" in its header) against real ad attribution
python3 scripts/pancake_client.py resolve-batch --input leads.csv --output leads_resolved.csv --since 2026-08-01 --until 2026-08-15

# Group conversation counts by tag over a date range (a conversation with multiple tags
# counts toward each) — same INBOX-only default and day-chunking as count-conversations
python3 scripts/pancake_client.py tag-report --since 2026-08-01 --until 2026-08-15

# Same, plus: how many conversations have ALL of a given set of tags (AND / intersection),
# AT LEAST ONE (OR), or NONE (exclude) — combinable, matches the dashboard's tag filter UI
# ("Có chứa thẻ" AND/OR + "Loại trừ thẻ")
python3 scripts/pancake_client.py tag-report --since 2026-08-01 --until 2026-08-15 --all-of "QM,Remarketing"
python3 scripts/pancake_client.py tag-report --since 2026-08-01 --until 2026-08-15 --any-of "QM,Remarketing"
python3 scripts/pancake_client.py tag-report --since 2026-08-01 --until 2026-08-15 --exclude "Remarketing"

# Conversion funnel report — reads FUNNEL_STAGE_N_NAME/FUNNEL_STAGE_N_TAGS from .env
# (define your own stages there first, see scripts/.env.example), reports count + %
# of top-stage + % of previous stage for each, in the order defined.
# TAGS entries can be exact tag labels or reserved keywords: ALL, HAS_PHONE, HAS_AD_ID.
# Counting is additive per criterion within a stage (not deduplicated OR) — see .env.example.
python3 scripts/pancake_client.py funnel-report --since 2026-08-01 --until 2026-08-15

# Lag report — days from a conversation's inserted_at to the first time each tag was added
# (tag_histories[]), per tag. Does NOT change funnel-report's counting (that stays anchored on
# inserted_at — the correct anchor for "conversion rate of this month's cohort"). Answers a
# different question: how long to wait before judging a cohort's downstream conversion, so a
# recent cohort isn't marked "low conversion" just because it hasn't had time to mature yet.
# Defaults to every real tag referenced by FUNNEL_STAGE_N_TAGS; override with --tags.
# n<10 for a tag is flagged low_sample=true — widen --since/--until for a more stable estimate.
python3 scripts/pancake_client.py lag-report --since 2026-08-01 --until 2026-08-15
python3 scripts/pancake_client.py lag-report --since 2026-08-01 --until 2026-08-15 --tags "Hẹn lịch,Đã pt"

# Phone-capture lag — Pancake's own API has NO timestamp for phone capture (has_phone /
# recent_phone_numbers carry no date anywhere, confirmed 2026-08-17). If sale reps log the date
# they got a customer's phone in an external Google Sheet (a column with "link" → pancake.vn URL,
# a column with "ngày"/"ngay"/"date"), this joins that sheet against Pancake by c_id and computes
# the same n/avg/median/p90/min/max lag stats as lag-report, in whole days (sheet only has dates,
# not timestamps). --since/--until must cover the full date range the sheet spans, chunked by day
# like lag-report (same 60-per-call cap applies) — this can take a while for a year of data, run
# in the background. Export the sheet as CSV first (File > Download > CSV, or the gviz CSV export
# URL if link-shareable: https://docs.google.com/spreadsheets/d/<ID>/gviz/tq?tqx=out:csv&sheet=<name>).
python3 scripts/pancake_client.py phone-lag-report --input phone-log.csv --since 2025-08-01 --until 2026-08-18 --output phone-log-resolved.csv

# "Rechat" report — conversations sale forgot (no reply/update in > 30 days, "sale bỏ quên").
# Queries with order_by=updated_at so since/until filter directly on updated_at — no need to
# scan inserted_at across all history. --since sets how far back to look; the stale cutoff
# (until) is auto-computed as today - --stale-days (default 30). Excludes RÁC/Đã pt-tagged
# conversations by default (already spam / already converted — nothing to re-nurture there).
# Rows with has_phone AND the --priority-tag (default LIÊN LẠC KHÁC) are flagged priority=true
# and sorted first — contactable leads that got tagged for other follow-up, then went cold.
python3 scripts/pancake_client.py rechat-report --since 2026-01-01 --output rechat.csv

# Override the excluded/priority tags or the staleness threshold if needed
python3 scripts/pancake_client.py rechat-report --since 2026-01-01 --stale-days 45 \
  --exclude-tags "RÁC,Đã pt,Đã lên tv" --priority-tag "LIÊN LẠC KHÁC" --output rechat.csv
```

### Internal dashboard actions (separate script, separate auth)

`pancake_dashboard_client.py` hits Pancake's **internal, undocumented dashboard API** (`pancake.vn/api/v1/...`) — a different surface from everything above (`pages.fm/api/public_api/v2`), authenticated with an **account login session token** (JWT), not a per-page API key. See `PANCAKE_INTERNAL_SESSION_TOKEN` in `scripts/.env.example` for how to capture one (browser DevTools > Network) and its known ~3-month expiry.

```bash
# Marks a customer as spam. --customer-id is the PAGE-SCOPED customer UUID
# (customers[].id / page_customer.id from a conversation object), NOT the c_id in a
# pancake.vn?c_id=... link and NOT the top-level customer_id field.
python3 scripts/pancake_dashboard_client.py toggle-spam --customer-id <page-scoped-customer-uuid> --page 1
```

⚠️ **Despite the name, calling this again does NOT reliably undo it** — confirmed 2026-08-24 by checking Meta Business Suite's Inbox > Spam folder directly: after 2 calls in a row, the customer was still in spam (not reverted). The only `action` value ever captured is `move_to_spam` — it appears to *set* spam state (idempotent), not flip it. Un-marking spam likely needs a different, not-yet-captured `action` value.

✅ Every successful `toggle-spam` (via the auto-spam scripts below) now also adds a Pancake note **"Đã chuyển đến thư mục Spam."** to the customer, via the confirmed public API notes endpoint (`pancake_client.add_note` — a third auth surface: `page_access_token` again like `/conversations`, but base path `.../v1/`, not the internal dashboard's cookie). See `references/api-reference.md`.

✅ **Confirmed working 2026-08-24** — `POST`, HTTP 200 `{"success": true}`. Required a `jwt=<session token>` cookie alongside the `access_token` query param (the actual fix — this endpoint authenticates by session cookie, not query token, unlike the public API), plus a multipart body (`action=move_to_spam`) and `Origin`/`Referer` headers. See `references/api-reference.md` for the full diagnosis trail.

```bash
# Fetch a customer's profile (gender, lives_in, etc.) from the internal dashboard API
python3 scripts/pancake_dashboard_client.py get-customer --customer-id <page-scoped-customer-uuid> --page 1
```

⚠️ **`gender` and `lives_in` are confirmed always `null` in practice (checked 2026-09-07, 16/16 sampled customers across 2 pages and dates spanning March–September 2026)** — Meta stopped exposing these fields to the Messenger Platform around 2021 for privacy reasons, so Pancake has nothing to surface here regardless of the customer. There is no age field anywhere on this API. **Do not use this endpoint to build customer demographic/geo profiles — it cannot work for any Page on this platform, not just this account.** For audience research (age/location/interest targeting), use Meta Ads Manager's Custom Audience → Lookalike flow instead, or the campaign delivery breakdown (age/gender/region) on ads that already converted this tag.

### Daily batch: auto-spam tagged conversations

`pancake_auto_spam_tagged.py` composes both clients above: finds conversations tagged a given label (default `RÁC`, exact case-sensitive match) created on a target date (default: yesterday) and moves each to spam.

```bash
# Dry run first — lists matches without mutating anything
python3 scripts/pancake_auto_spam_tagged.py --date 2026-08-21 --dry-run

# Real run for yesterday, all configured pages
python3 scripts/pancake_auto_spam_tagged.py

# Real run for a specific page / date / tag label
python3 scripts/pancake_auto_spam_tagged.py --page 1 --date 2026-08-21 --tag RÁC
```

**Scheduled 2026-08-24**: Windows Task Scheduler task `PancakeAutoSpamTagged` runs `scripts/run-daily-auto-spam.ps1` (wrapper that appends timestamped output to `scripts/logs/auto-spam-tagged.log`) daily at 08:30 local time, under the creating Windows user — local only, credentials never leave this machine.

```powershell
# Check status / last run result
schtasks /query /tn "PancakeAutoSpamTagged" /v /fo LIST

# Run it immediately (real run, not dry-run — mutates data)
schtasks /run /tn "PancakeAutoSpamTagged"

# Disable / re-enable without deleting
schtasks /change /tn "PancakeAutoSpamTagged" /disable
schtasks /change /tn "PancakeAutoSpamTagged" /enable

# Delete entirely
schtasks /delete /tn "PancakeAutoSpamTagged" /f
```

⚠️ Requires the machine to be on (not asleep) at 08:30 and `PANCAKE_INTERNAL_SESSION_TOKEN` to still be valid — check `scripts/logs/auto-spam-tagged.log` periodically, especially after ~2026-11-15 (token expiry) or if a Pancake login/password change invalidates the session early.

**Second daily pass — same-day, 17:00**: `pancake_spam_report.py` covers TODAY's conversations from `00:00:00` up to (not including) `17:00:00`, moves matches to spam (same idempotent `toggle_spam`), and **appends a dated section** to one Markdown file per calendar month — `plans/reports/report-{YYYY-MM}-pancake-spam-daily.md` (table of customer name-linked-to-conversation/page/`inserted_at`/status) — rather than one file per day. ⚠️ Contains customer names (PII) — an explicit user decision (2026-08-24), unlike this skill's usual PII-redacted-by-default output elsewhere. Keep this report file local/private accordingly. Exists so a conversation tagged in the morning doesn't sit un-spammed until the next day's 08:30 run — reuses `find_and_spam_tagged()` (shared with `pancake_auto_spam_tagged.py`) so the matching/spam logic isn't duplicated.

```powershell
schtasks /query /tn "PancakeSpamReport1700" /v /fo LIST
schtasks /run /tn "PancakeSpamReport1700"
schtasks /change /tn "PancakeSpamReport1700" /disable
schtasks /delete /tn "PancakeSpamReport1700" /f
```

Log: `scripts/logs/spam-report.log`. Same token-expiry caveat as the 08:30 job applies. A conversation this job already spammed is a harmless no-op if the next day's 08:30 job re-matches the same tag/date (confirmed idempotent-set behavior).

⚠️ **No API-based way to read the resulting spam status back** — neither the public API's conversation object nor this internal API's `GET .../customers/{id}` exposes a spam field (`is_banned` there is a different concept: blocking a customer from messaging, not spam-folder placement). Pancake's own dashboard has no Spam/Rác folder — that only exists in **Meta's Page Inbox** (business.facebook.com), which is the only place to confirm a conversation actually landed in spam.

## Polling for a tag in near-realtime (n8n / any scheduler)

There is no webhook or push event on this API for "a tag was just added" — everything above
is pull-based. `watch-tag` is the pull side of a poll loop: run it every 1-2 minutes from a
scheduler (n8n Schedule Trigger + Execute Command, Windows Task Scheduler, cron) and it reports
only conversations tagged **today** that a *previous run* of this same command has not already
reported.

```bash
# Default watches for QM; run this on a schedule
python3 scripts/pancake_client.py watch-tag

# Watch a different tag, or use a state file outside the scripts/ folder
python3 scripts/pancake_client.py watch-tag --tag "Hẹn lịch" --state-file /path/to/state.json
```

Output is JSON with a `new_items` array (empty on a run with nothing new) — each item carries
`conversation_id`, `page`, `name`, `phone_number`, `tags`, `link`, `inbox_date`. Feed this
straight into an n8n workflow: Schedule Trigger → Execute Command → parse the JSON → IF
`new_count > 0` → Split Into Items → send a Telegram/Slack message per item.

**How dedup works**: a small state file (`scripts/watch_tag_state.json` by default) tracks which
conversation ids were already reported, keyed by day (Asia/Bangkok). Each run prunes to
today + yesterday only, so the file never grows unbounded and a run just after midnight still
catches a conversation whose tag landed in the last minutes of the previous day. A missing or
corrupt state file is treated as empty rather than crashing the poll loop — worst case is one
run of duplicate notifications, recovered automatically on the next run.

This only catches a tag added **today** — it is not a general "since last run" cursor across
arbitrary days. That is deliberate: a poll loop's job is "notify me now", not backfill, and
`tag-report`/`list-by-tag` above already cover historical ranges.

## Rechat report ("sale bỏ quên" — forgotten leads to re-nurture)

> Origin note: added 2026-08-24 by a subagent during an unrelated RÁC-spam backfill task — it was
> not part of that task's scope and was never explicitly requested. Kept after review (user
> decision) because the feature is self-contained and works, but it has NOT been exercised against
> production the way the spam/note pipeline has. Treat its behavior as unverified until first real use.

`rechat-report` finds conversations sale stopped following up on: `updated_at` older than
`--stale-days` (default 30), i.e. no reply/tag change/consultation since. It queries with
`order_by=updated_at` (confirmed since/until then filter directly against `updated_at`, see
`references/api-reference.md`), so it targets exactly the stale set in one pass instead of
scanning every conversation ever created and filtering client-side.

- **Excludes** (default `--exclude-tags "RÁC,Đã pt"`): trash-tagged and already-converted
  (already had the procedure) conversations don't need re-nurturing.
- **Priority flag**: a row is `priority=true` when it both `has_phone` and carries
  `--priority-tag` (default `LIÊN LẠC KHÁC`) — a contactable lead that was tagged for other
  follow-up and then went quiet. Priority rows sort first, then by `days_stale` descending
  (most-forgotten first) within each group.
- Output columns: `priority, days_stale, inserted_at, updated_at, name, phone_number, has_phone,
  tags, sale_rep, link` — contains customer PII, always use `--output <file>` and never paste
  rows into chat (same rule as `list-by-tag`/`list-by-ad`).
- `--since` controls how far back (by `updated_at`) to look — set it to your page's earliest
  relevant date to catch very old forgotten leads; a wide range still day-chunks under the
  60/call cap, so a multi-year `--since` can take a while (run in the background).
- Like everything else in this skill, tags/`updated_at` are **live state** — re-running later
  can legitimately return a different set as sale reps act on leads.

## Benchmark & visualize lag ("độ chín của lead")

3 bước để thống kê + vẽ lại biểu đồ độ trễ tin nhắn → gắn tag, mỗi khi cần cập nhật benchmark:

1. **Thống kê**: chạy `lag-report` cho khoảng ngày cần (càng dài càng nhiều mẫu, tránh `low_sample: true`); nếu có sheet ghi tay ngày capture SĐT, chạy thêm `phone-lag-report` cho cùng khoảng ngày để có dòng SĐT (Pancake API không tự có timestamp này):
   ```bash
   python3 scripts/pancake_client.py lag-report --since 2025-08-01 --until 2026-08-17
   python3 scripts/pancake_client.py phone-lag-report --input phone-log.csv --since 2025-08-01 --until 2026-08-18
   ```
2. **Lưu benchmark**: ghi kết quả vào `plans/reports/benchmark-{date}-pancake-lag-{scope}.md` — dùng `plans/reports/benchmark-260817-1405-pancake-lag-full-year.md` làm mẫu (bảng số liệu, cách dùng benchmark, giới hạn; dòng SĐT đánh dấu ⁺ và ghi rõ khác nguồn/độ chính xác theo ngày, không theo giờ).
3. **Vẽ lại biểu đồ**: copy `assets/lag-chart-template.html`, dán số liệu bước 1 vào mảng `DATA` trong `<script>` (giữ đúng field `key/label/n/min/median/avg/p90/max`; thêm `note: true` cho dòng SĐT để tự có dấu ⁺ bên cạnh nhãn), cập nhật khoảng thời gian + tổng tin nhắn quét trong `.meta-strip` và dòng lệnh ở footer, rồi publish bằng Artifact tool (favicon `⏳`). Template đã theo `dataviz` + `artifact-design` skill (dumbbell chart, thang log, 2 sắc độ 1 hue, dark mode, hover/table view) — không cần thiết kế lại từ đầu; chỉnh D_MIN/D_MAX/gridTicks trong script chỉ khi lag mới rộng/hẹp hơn nhiều so với ~0.18–150 ngày mặc định.

⚠️ **Tags and phone capture reflect live state, not a historical snapshot** — a sale rep editing a tag after the fact means re-running the same query later can legitimately return a different number. If a count doesn't match a manual record or an earlier observation, check whether the underlying data changed before assuming the script is wrong (see `references/api-reference.md`).

`resolve-batch` output adds: `c_id`, `ad_ids` (comma-separated Meta ad IDs), `tags` (comma-separated tag labels), `sale_rep`, `resolve_status` (`resolved` / `not_in_recent_list` / `no_link`). Pass `--since`/`--until` matching the sheet's date range — the API has no confirmed pagination beyond that, so an unbounded fetch may miss older conversations (see `references/api-reference.md`).

`phone-lag-report` output adds `resolve_status` (`resolved` / `no_link` / `not_in_recent_list` / `bad_date`) and `lag_days` per row. ⚠️ **Check your sheet's date column format before trusting the result** — confirmed 2026-08-17 on a real 1,580-row sheet it was reformatted mid-use (majority D/M/Y → majority M/D/Y), and even after that ~30 rows stayed in the old format. The parser tries `%m/%d/%Y`, then `%d/%m/%Y`, then ISO per row — an unambiguous date (day or month >12) self-resolves to the right format regardless of which convention the sheet currently uses; only a truly ambiguous date (both ≤12) falls back to the first format tried (`%m/%d/%Y`). It also flags implausible results (`lag_days` outside -1..60) as `suspicious_excluded` rather than silently corrupting the median — spot-check those rows in `--output` before trusting a result with a nonzero `suspicious_excluded` count.

## Calendar-month window (`--month`)

`count-conversations`, `tag-report`, `list-by-tag`, and `funnel-report` accept `--month
YYYY-MM` as an alternative to `--since`/`--until` — matches how `meta-ads-manager.py billing`
already reports "Đã chi tháng này" without the caller doing date math.

```bash
python3 scripts/pancake_client.py tag-report --month 2026-08
python3 scripts/pancake_client.py count-conversations --month 2026-07   # a past month: whole month
```

For a **past month**, `--month` is exactly the 1st through the 1st of the next month — the
same range you'd get typing `--since`/`--until` by hand. For the **current month**, the window
stops at *right now* instead of walking into days that have not happened yet — a report run
mid-afternoon on the 27th covers the 1st through this afternoon, not the 1st through the 28th.
`--month` and `--since`/`--until` are mutually exclusive; provide one or the other.

⚠️ A full month costs roughly `days × pages × 1.5s` in API calls before retries — about 3
minutes for a 27-day month across 4 pages on this account. That's a report you run and wait
on, not something to schedule every few minutes; `watch-tag` (above) is the near-realtime tool.

## Combine with ads-management

1. Run `resolve-batch` on your lead/revenue sheet to get `ad_id` per row.
2. Look up each `ad_id` via Meta's API (`Ad(ad_id).api_get(fields=['campaign','adset'])`, same pattern `ads-management`'s scripts already use) to get the real campaign/adset.
3. Cross-reference against the campaign/adset IDs recorded in `ads-management`'s target templates (`plans/reports/export-*-template.md`, `ads-target-naming-convention` memory) to attribute revenue/leads to a specific named target ("Target 11", "Target 5", etc.) instead of relying on Meta's own lead-count proxy.

## Security

- `scripts/.env` holds live per-page tokens (and now `PANCAKE_INTERNAL_SESSION_TOKEN`, an account login session token) — never commit it, never echo its contents or print raw token values into chat. The session token is more sensitive than a page API token: it authenticates as a specific logged-in Pancake user, not a scoped page integration.
- `pancake_dashboard_client.py` mutates real customer state — confirm the `--customer-id` (and which page) before running `toggle-spam` against production data.
- Conversation objects contain customer PII (name, phone, Messenger ID). `list-conversations`' console output is redacted to safe fields by default; only `--output <file>` writes the full object, and that file should never be pasted into chat — summarize counts/status instead.
- Error handling redacts `access_token` from exception messages (a raw `resp.raise_for_status()` leaks it into the URL in the traceback — don't reintroduce that). All requests wait `REQUEST_DELAY_SECONDS` (1.5s) to stay under the confirmed rate limit (HTTP 429 observed after rapid consecutive calls).
- `phone-lag-report`'s `--input` CSV (a Google Sheet export) carries the same customer PII as Pancake itself (name, phone) — treat it exactly like a `list-conversations --output` dump: never paste rows into chat, summarize `status_counts`/`phone_lag` only. Delete a temp CSV export once done with it if it isn't meant to be kept.
- `rechat-report`'s `--output` CSV carries name/phone/link per stale conversation — same rule: always write to `--output`, never print rows to console or paste into chat; summarize the `matched`/`priority_matched` counts instead. Handing this list to a sale rep for follow-up is the intended use, but keep the file itself off chat and off any non-private channel.

## References

| Topic | File |
|-------|------|
| Confirmed endpoint, auth, query params, schema | `references/api-reference.md` |
| End-to-end attribution chain & how to join with ads-management targets | `references/attribution-matching.md` |
