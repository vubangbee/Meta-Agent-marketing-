# Pancake API — reference (confirmed working, 2026-08-14)

## Endpoint

```
GET https://pages.fm/api/public_api/v2/pages/{page_id}/conversations
```

**Auth:** query param `?access_token=<page_access_token>`. This must be a **per-page "Public API access token"** (from Pancake's page settings) — the account-level session JWT (shown as a long `eyJ...` token when you're logged into the dashboard) does **not** work here and returns `{"success":false,"message":"Invalid access_token","error_code":102}`. Each Facebook Page managed in Pancake has its own token; store them as `page_access_token_1`, `page_access_token_2`, ... paired by index with `PANCAKE_PAGE_ID_1`, `PANCAKE_PAGE_ID_2`, ... in `.env`.

There is **no single-conversation-by-id sub-route** (`/conversations/{id}` returns the SPA HTML shell, not JSON — confirmed 404-equivalent). Only the list endpoint works; fetch a batch and match locally by the `id` field (which equals the `c_id` value in `pancake.vn/...?c_id=...` links).

## Query parameters (confirmed, provided by user 2026-08-14)

| Param | Type | Meaning |
|---|---|---|
| `since` | integer | Unix timestamp in **seconds** — filter from this time (`inserted_at`/`updated_at` depending on sort) |
| `until` | integer | Unix timestamp in seconds — filter up to this time |
| `order_by` | string | `inserted_at` or `updated_at` — **changes which field `since`/`until` filter against, not just sort order.** Confirmed 2026-08-14: omitting `order_by` entirely filters by `updated_at` (picks up old conversations that merely got a new reply in the window), giving a materially different — and for "how many conversations today" questions, wrong — result than `order_by=inserted_at` (same day-window: 11 vs 4). `pancake_client.py` now defaults `list-conversations`/`resolve-batch` to `inserted_at`; only override to `updated_at` if you specifically want "touched in this window," not "started in this window." |
| `tags` | string | Comma-separated tag IDs (numeric, not labels) to filter by. Confirmed 2026-08-14: single-ID server-side `tags=<id>` matches client-side label filtering exactly (cross-verified on tag "Đã pt", id 57 → both gave 2 conversations). **Multi-ID is AND, not OR**: `tags=61,62,65` (D, Remarketing, QM) returned exactly the conversations having *all three*, matching `tag-report --all-of "D,Remarketing,QM"`'s client-side intersection count of 1 exactly. There is no server-side OR — if you need "has any of these tags," you must fetch and filter client-side (or call once per tag ID and union the results). `list-by-tag`/`tag-report` do client-side label matching (simpler — no separate ID-lookup step) since tag IDs aren't documented anywhere; discover one by fetching a small sample and reading `tags[].id` for the label you want. |
| `type` | string (single value only, despite docs saying array) | Filter by conversation type: `INBOX`, `COMMENT`, `COMMENT_LIVESTREAM`, `POST`. **Confirmed 2026-08-14: only accepts ONE value per call.** Passing two (`type=COMMENT&type=COMMENT_LIVESTREAM`) doesn't union them — it silently returns 0 results with `success: true` (no error). `pancake_client.py` now raises a clear error instead of quietly returning wrong data if you pass more than one `--type`. `POST` additionally requires a `post_ids` param (untested further — not needed for lead/conversation counting). `count-conversations` defaults to `--type INBOX` — confirmed unfiltered counts mix in `COMMENT` entries (public post comments, not real customer conversations); same 9-day window (05/08-13/08) was 83 INBOX vs 8 COMMENT, verified two independent ways (direct `--type COMMENT` filter, and unfiltered day-by-day breakdown by `type` field) — both agree on 8. |

`pancake_client.py` accepts `--since`/`--until` as `YYYY-MM-DD` and converts to unix seconds automatically — don't pass raw date strings directly to the API.

**⚠️ Timezone bug found and fixed 2026-08-14:** a bare `YYYY-MM-DD` is interpreted as midnight **Asia/Bangkok (UTC+7)**, not UTC. The first implementation used UTC midnight, which silently shifted the whole day window 7 hours forward — undercounting "today"'s conversations (missed the 00:00–07:00 VN window, counted into part of the next day instead). Verified: same query for "today" went from 9 → 11 conversations after the fix. If you ever see conversation counts that look off by a similar small amount, check this first before assuming the API itself is wrong.

Verified behavior: `since=2020-01-01&until=2020-01-02` → 0 results; `since=<today>&until=<tomorrow>` → small non-zero count. Confirms the filter is real, not ignored.

**⚠️ Confirmed hard cap: 60 conversations per call, no cursor/pagination param found — and confirmed to ACTUALLY BITE in practice 2026-08-24**, not just theoretically: a 2025 full-year auto-spam backfill on page 1 hit exactly/near 60 on 24 separate days (mostly April 2025, which had genuine high volume — daily RÁC-tag matches alone ran 20-35+, meaning total conversations that day plausibly exceeded 60). Measured cost of the bug before it was fixed: an hourly re-scan of those 24 capped days surfaced **79 RÁC-tagged conversations the day-chunked scan had missed entirely** (worst single day: 2025-04-18, 35 found vs 52 actual).

**✅ Fixed 2026-08-24 — `pancake_client.fetch_conversations_complete()`.** It fetches a window, and if the result is at/above `CAP_SPLIT_THRESHOLD` (55) it halves the window and recurses, unioning results by conversation id; it stops subdividing at `MIN_WINDOW_SECONDS` (60s) and warns if still capped there. Recursive halving adapts to actual density and costs no extra calls on quiet windows, unlike fixed hourly slicing. Verified on 2025-04-18: a plain single call returned 60 conversations / 35 RÁC, `fetch_conversations_complete` returned 100 / 52 — matching the independent hourly re-scan exactly. `find_and_spam_tagged()` (both scheduled jobs) now uses it, so the daily pipeline can no longer silently truncate. The other read-only report commands (`count-conversations`, `tag-report`, `ad-report`, `funnel-report`, `lag-report`, `rechat-report`) still use plain day-chunked `_fetch_conversations` and only print a warning — they remain vulnerable on high-volume days. Querying a 14-day range in one call silently returned only the 60 most recent (spanning just the last ~7 days of the range) — the earlier ~7 days were dropped with no error or warning. **Always chunk wide date ranges into windows small enough that no single call approaches 60** (day-by-day is safe for this account's volume — observed 3-22 conversations/day; re-check if volume grows) and sum client-side. `resolve-batch` and `list-conversations` do NOT do this chunking automatically yet — the caller (or a future script enhancement) must loop over sub-ranges for anything wider than a few days.

## Confirmed conversation object fields

```
{
  "id": str,                    // = the c_id in pancake.vn links, format "<page_id>_<conversation_id>"
  "type": str, "page_id": str, "customer_id": str,
  "inserted_at": str, "updated_at": str,
  "seen": bool, "has_phone": bool, "message_count": int,
  "from": {...}, "customers": [...], "page_customer": {...},
  "last_sent_by": {"id": str, "name": str, ...},   // sale rep who last replied
  "assignee_ids": [...], "assignee_group_id": ..., "assignee_histories": [...],
  "current_assign_users": [...],
  "recent_phone_numbers": [{"phone_number": str, "captured": str, "status": int, "length": int, "m_id": str, "offset": int}],
  // ⚠️ "captured" is NOT a timestamp — confirmed 2026-08-14 it duplicates "phone_number" itself.
  // There is no per-phone capture date anywhere in the schema; "inserted_at" (conversation
  // start) is the closest available date if you need one. "m_id" is the message ID where the
  // number appeared (could theoretically be used to look up its timestamp via a messages
  // endpoint, but no such endpoint has been found/tested yet). This is a permanent API gap,
  // not a bug to fix — `phone-lag-report` works around it by joining an externally-logged
  // phone-capture date (a Google Sheet sale reps fill in by hand) against `inserted_at`.
  "tags": [{"id": int, "text": str, "color": str, "is_lead_event": bool, "is_deactive": bool, ...}, null, ...],
  "tag_histories": [{"inserted_at": str, "conversation_id": str,
                      "payload": {"action": "add"|"remove", "editor_id": str, "editor_name": str, "tag": {...}}}, ...],
  // ✅ Confirmed 2026-08-17: unlike phone capture, each tag add/remove DOES have its own
  // timestamp here, independent of the conversation's own inserted_at. This is what
  // `lag-report` uses to measure how long after a conversation starts a given tag typically
  // gets added — NOT to re-anchor funnel/tag-report counts, which correctly stay on the
  // conversation's own inserted_at (that's the right anchor for "conversion rate of this
  // month's cohort"). Take the EARLIEST 'add' entry per tag per conversation, not the first
  // one encountered — the array is not guaranteed sorted, and a tag can be added, removed,
  // then re-added (re-tagging), which would otherwise inflate or understate the lag.
  "ad_ids": [str, ...],          // ✅ Meta ad IDs that drove this conversation
  "ads": [{"ad_id": str, "post_id": str, "inserted_at": str}, ...],  // richer per-ad detail
  "post_id": null,               // observed always null at top level — use `ads[].post_id` instead
  "snippet": str
}
```

**`ad_ids` / `ads` is the field that was missing from the earlier (wrong) endpoint guess** — this is real Meta ad attribution, verified by cross-checking returned `ad_id` values against known `ak-ads-management` target ad IDs (exact matches found for Target 1, Target 1.1, and Target Thẩm mỹ during testing).

Note: `tags` list can contain `null` entries — always filter them out (`if t` / `if t is not None`) before accessing `.get()`.

## Known limitations

- No confirmed pagination cursor beyond `since`/`until` — if a date range returns more conversations than the API's internal page cap, some may be missed. Narrow the range if `resolve-batch` reports unexpectedly low `resolved` counts for a busy period.
- `post_id` is only reliable inside each `ads[]` entry, not the top-level field (which is always `null`).
- **Rate limit confirmed: HTTP 429 after rapid consecutive calls** (hit during testing — roughly a dozen calls within ~2 minutes). `pancake_client.py` sleeps `REQUEST_DELAY_SECONDS` (1.5s) before every call. If you still hit 429 repeatedly, back off further (increase the constant).
- **Transient backend errors confirmed 2026-08-17**: the API intermittently returns `{"success": false, "message": "An error occurred. Please try again later."}` or a read timeout, even for small/simple queries (e.g. a 2-day range) — the same call succeeds on immediate retry with no param change, so this is a Pancake-side hiccup, not a script bug. `_fetch_conversations` now retries automatically (`MAX_RETRIES` attempts, exponential backoff starting at `RETRY_BACKOFF_SECONDS`) on network errors, HTTP 429/5xx, and this generic `success: false` shape; a warning prints to stderr on each retry. Non-retryable errors (bad token, bad params — other 4xx) still raise immediately. A long chunked range (many days × many pages) can still fail after retries are exhausted on a persistent outage — rerun the command if so.
- **⚠️ Tags and phone capture are live, mutable state — a query reflects "right now," not a historical snapshot.** A sale rep can add/remove a tag (e.g. "Hẹn lịch") after the fact; re-running the same date-range query later can legitimately return a different tag count even though nothing about the query changed. Confirmed 2026-08-14: investigated an apparent count mismatch this way — the underlying data had genuinely changed between observations, not a script bug. If a count doesn't match an external reference (a manual sheet, a screenshot, a memory of an earlier number), check whether the reference is a stale snapshot before assuming the query is wrong.
- Error responses now redact the access token (previously `resp.raise_for_status()` leaked the full request URL including `access_token=...` into exception messages — fixed 2026-08-14, see `_fetch_conversations`). Never re-introduce `raise_for_status()` on this endpoint without redacting first.

## Notes endpoint (public API, v1 — pancake_client.add_note)

Confirmed working 2026-08-24 (user-supplied cURL, live-tested — `HTTP 200, success: true`):

```
POST https://pages.fm/api/public_api/v1/pages/{page_id}/page_customers/{page_customer_id}/notes
?page_access_token=<per-page token>
Content-Type: application/json
{"message": "<note text>"}
```

- **Auth**: `page_access_token` query param — same per-page token as `/conversations`, NOT the internal dashboard's session cookie/token. Note the base path is `.../v1/`, while `/conversations` is `.../v2/` — different version on the same `pages.fm/api/public_api` host.
- `page_customer_id` = the same page-scoped customer UUID used everywhere else (`customers[].id` / `page_customer.id`), NOT the conversation's `c_id`.
- Response on success: `{"success": true, "message": "Ghi chú đã được bổ sung thành công", "note_id": "<uuid>", "data": [<full note history for this customer>, ...]}` — `data` includes prior notes (e.g. ones added manually by a sale rep through the dashboard), so this endpoint reads back the whole note thread, not just the one just added.
- Integrated into `find_and_spam_tagged()` (pancake_auto_spam_tagged.py): after a successful `toggle_spam`, automatically adds the note "Đã chuyển đến thư mục Spam." A note failure does not revert or fail the spam action — tracked separately as `note_status`/`note_error` in the result dict.

## Internal dashboard API (separate surface, unconfirmed — pancake_dashboard_client.py)

Discovered 2026-08-24 from a user's browser DevTools network capture, not from documentation. **Everything in this section is a different auth/base-URL surface from the confirmed public API above — do not mix the two clients' tokens.**

```
POST (default guess, unconfirmed) https://pancake.vn/api/v1/pages/{page_id}/customers/{page_customer_id}/toggle_move_to_spam
```

- **Auth:** query param `?access_token=<session_jwt>` — but this token is the **account login session JWT**, i.e. exactly the token type the public API's `test-connection` explicitly rejects (`error_code 102`). Decoding the payload (base64, no verification needed to read claims) showed: `exp` (expiry, ~3 months after `iat`), `uid`, `session_id`, `pancake_id`, `fb_id`, `fb_name` — this is a specific human's login session, not a stable service credential. It will need manual recapture from the browser when it expires or the session ends (logout, password change).
- **`page_customer_id`** in the path is **not** the conversation's `id` (c_id). Confirmed 2026-08-24 by fetching a real conversation via the public API and comparing UUIDs field-by-field: it equals `customers[].id` / `page_customer.id` on the conversation object — a page-scoped customer record ID, distinct from the conversation's own `id` (format `<page_id>_<numeric>`) and also distinct from the conversation's top-level `customer_id` field (yet another, differently-valued UUID — likely a cross-page/global customer identity). To get a `page_customer_id` for a given `c_id`, fetch the conversation via `list-conversations`/`resolve-batch` and read `customers[0].id`.
- **✅ Confirmed working end-to-end 2026-08-24** — live `POST` against a real conversation (tagged "RÁC", `inserted_at` 2026-08-21) returned `HTTP 200 {"success": true}`. Full confirmed request shape:
  - Method: `POST`
  - Query param: `?access_token=<session_jwt>` (present in every observed request, but see below — may be vestigial)
  - Body: `multipart/form-data` with exactly one field, `action=move_to_spam` (a browser `FormData` with one text field appended produces this same shape — no file, just the boundary framing)
  - Headers: `Origin: https://pancake.vn`, `Referer: https://pancake.vn/{page_slug}` (the page's own dashboard URL)
  - **Cookie: `jwt=<same session_jwt>`** — this was the actual missing piece. Diagnosis path: bare `POST` with just the query-param token → `HTTP 500 "Server internal error"`. Adding `Origin`/`Referer` + the multipart body → still `500`. Adding the `jwt` cookie → `200`. Conclusion: **this endpoint authenticates via session cookie, not the query-param token** — the public API's per-page `access_token` pattern does not carry over to this internal surface, and the `access_token` query param here may do nothing at all (untested whether dropping it still works; harmless to keep sending it).
- Rate limit on this surface still unconfirmed (only a handful of calls made during diagnosis) — `pancake_dashboard_client.py` keeps the same conservative 1.5s delay as the public API client defensively.
- Response shape on success observed as just `{"success": true}` — no further fields seen (e.g. no echoed new spam-state boolean).
- **⚠️ Despite the URL's name, this is NOT a symmetric toggle — confirmed 2026-08-24 via ground truth on Meta Business Suite.** Called 3 times in a row on the same customer, body always `action=move_to_spam` (the only action value ever captured — see above). After call 1 the user hadn't checked Meta yet; after call 2 we *assumed* it had reverted to not-spam (wrong assumption, not verified); before call 3, the user checked Meta Business Suite's own Inbox > Spam folder directly and confirmed the customer **was already in spam at that point** (i.e. after 2 calls, net state = spam, not reverted). Working conclusion: `action=move_to_spam` **sets** spam state (idempotent — calling it again while already spam is a no-op that still returns `{"success": true}`), it does not flip a boolean. "toggle_" in the URL likely refers to a UI toggle *control*, not toggle *semantics* server-side. **Un-marking spam almost certainly needs a different `action` value** (never captured — the browser-side "remove from spam" action wasn't observed). Do not assume repeated calls will undo a previous one. **Reconfirmed after a 3rd call**: user checked Meta Business Suite again post-call-3 — still spam. 3/3 calls with `action=move_to_spam` → spam every time; never reverted at any checkpoint (checked after call 2 and after call 3).
- **⚠️ No way to read spam status back from any Pancake API, confirmed 2026-08-24.** Checked both surfaces on a conversation right after toggling it: the public API's conversation object (`GET .../conversations`) has no spam-related field, and this internal API's own `GET .../customers/{customer_id}` (fields: `activities, banned_count, can_inbox, comment_count, gender, global_id, id, is_banned, last_commented_at, lives_in, notes, profile_updated_at, recent_orders, recent_phone_numbers, reported_count, thread_id`) has none either — `is_banned`/`can_inbox` are a *different* concept (blocking a customer from messaging the page), not spam-folder placement. Confirmed by the user (page owner): Pancake's own dashboard UI has **no Spam/Rác folder at all** — that folder only exists in **Meta's own Page Inbox** (business.facebook.com). Working theory: `toggle_move_to_spam` calls through to Meta's Messenger Platform to classify the thread as spam there; Pancake doesn't store or expose that state itself. **To verify a conversation's actual spam status, check Meta Business Suite's Inbox > Spam folder for the page directly — there is no API-based way to confirm it via Pancake.**

### `GET /customers/{customer_id}` — confirmed working, but demographic fields are dead

```
GET https://pancake.vn/api/v1/pages/{page_id}/customers/{customer_id}?access_token=<session_jwt>
```

Same auth as `toggle_move_to_spam` above (`jwt` cookie + `Origin`/`Referer` headers pointed at the page slug). Wrapped as `pancake_dashboard_client.py get-customer`.

**⚠️ `gender` and `lives_in` are confirmed always `null`, checked 2026-09-07** across 16 real customers sampled from 2 different pages (page 1, page 2) and 2 different time periods (March 2026, September 2026) — 16/16 null on both fields, no pattern by page or date. No `age`/birthday field exists anywhere on this object either. Root cause: Meta deprecated `gender`/`locale`/`timezone` on the Messenger Platform's user-profile API around 2021 for privacy compliance — this is a platform-wide restriction, not a Pancake bug or an account-specific permission gap, so it cannot be fixed by any token/config change here. **Conclusion: this endpoint cannot be used to build customer demographic or geo profiles for ad targeting.** The only viable Meta-side paths for that are a Custom Audience → Lookalike built from the tagged customer list, or the age/gender/region delivery breakdown on Ads Manager reporting for campaigns that already converted this audience.
