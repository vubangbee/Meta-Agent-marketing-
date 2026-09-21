# Attribution matching — confirmed working chain (2026-08-14)

## The confirmed chain

```
Google Sheet row (SĐT, LINK containing c_id=<page_id>_<conv_id>)
  → pancake_client.py resolve-batch: fetch conversations for the matching page(s)
    (filtered by --since/--until to the sheet's date range)
  → match row's c_id against fetched conversation "id" field
  → conversation.ad_ids gives the real Meta ad ID(s) directly — no extra Pancake call needed
  → (optional) Meta Ads API: Ad(ad_id).api_get(fields=['campaign','adset']) to resolve to a
    known ak-ads-management target
```

This works end-to-end — verified by resolving a real lead sheet and finding ad_ids that exactly matched known ad IDs from `ak-ads-management` target templates (Target 1.1's "HMB 18tr" ad and Target Thẩm mỹ's "Mỡ 11 Ver 1" ad both appeared correctly).

## Practical notes

- **One API call per page, not per conversation.** `resolve-batch` fetches the whole conversation list for each configured page once (optionally date-filtered) and matches locally — much cheaper than looking up each lead individually. Pass `--since`/`--until` matching your sheet's date range to keep the fetch small and avoid missing older conversations past whatever the API's internal page cap is (see `api-reference.md`).
- **`resolve_status: not_in_recent_list`** means the c_id was extracted from the link but wasn't in the fetched batch — usually means the date range was too narrow, or the conversation is older than what an unfiltered call returns. Widen `--since` and retry before concluding it's unattributable.
- **A conversation can have multiple `ad_ids`** (a customer may have clicked more than one ad before messaging, or the conversation continued across multiple ad touches) — `resolve-batch` joins them comma-separated in the output; decide per-report whether to use the first, the most recent (`ads[].inserted_at`), or count it toward all of them.
- **Post ID (from `ads[].post_id`) is still not 1:1 with a campaign/target** — the same post can back multiple ads (see the original caveat, still true), but you no longer need post_id for attribution since `ad_ids` is direct. Post ID matching is now only a fallback if `ad_ids` is empty on a conversation.

## Joining against ak-ads-management targets

Once you have a resolved `ad_id`, cross-reference it against the campaign/adset IDs recorded in `ak-ads-management`'s target template reports (`plans/reports/export-*-template.md` and the `ads-target-naming-convention` memory) — either by looking up `Ad(ad_id).api_get(fields=['campaign','adset'])` via Meta's API, or by pattern-matching the ad_id prefix against known campaign ID prefixes (same account tends to produce IDs with a shared suffix, e.g. `...053` = 6707, `...613` = 5832, `...690` = 3798 — useful as a quick eyeball check, not a substitute for the real API lookup).
