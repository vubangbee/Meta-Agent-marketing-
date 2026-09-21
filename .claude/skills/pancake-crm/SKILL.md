---
name: pancake-crm
description: Operate the user's Pancake CRM (crm.pancake.vn) workspace directly through its REST API — look up, create, and update Records (leads/accounts/contacts), Deals, Orders, Tickets, and Products, and look up Sources, Pancake Tags, and pipeline statuses. Use this whenever the user asks to find, check, create, or update a customer, lead, contact, deal, order, ticket, or product in "CRM" or "Pancake" (e.g. "tạo deal mới cho khách 0972...", "khách này có đơn hàng nào chưa", "cập nhật trạng thái deal sang đàm phán", "tag khách này là VIP", "thêm sản phẩm mới vào CRM", "doanh số tháng này", "báo cáo doanh số theo nguồn"), even if they don't say "API" or spell out "Pancake" in full — "CRM" alone is enough signal once credentials are configured. Do NOT use this for building a standalone SDK/client library as a coding deliverable (that's a normal coding task) or for Pancake's POS/e-commerce products unrelated to the CRM module.
---

# Pancake CRM operations

This skill lets you act directly on a live Pancake CRM workspace over HTTPS — there is no bundled SDK, so every operation is a plain HTTP request (curl via Bash, or WebFetch for simple GETs). The full field-by-field API reference lives in [references/api-reference.md](references/api-reference.md); read it before any endpoint you haven't used yet in this conversation, since several endpoints have non-obvious quirks (inconsistent body wrapping, terminal statuses, required links) that are easy to get wrong from memory.

## Credentials

Every request needs two things: an **API key** and a **workspace_id**. Resolve them in this order:

1. Environment variables `PANCAKE_API_KEY` and `PANCAKE_WORKSPACE_ID`, if set.
2. Otherwise, ask the user for them. Tell them where to find the key: **Pancake CRM → Settings → Tools** (the key can be auto-disabled after a period of inactivity, so if requests start failing with an auth error, that's the first thing to suspect and mention).

Never hardcode a key in a script or file, never echo it back to the user, and never write it into logs, commit messages, or files you create — treat it like a password. When building request URLs, pass it only as the `api_key` query parameter the API expects.

## Base request pattern

```
Base URL: https://crm.pancake.vn/api
Auth:     ?api_key={PANCAKE_API_KEY} appended to every request's query string
```

Example shape:

```bash
curl --request GET \
  --url "https://crm.pancake.vn/api/workspaces/${PANCAKE_WORKSPACE_ID}/deals?api_key=${PANCAKE_API_KEY}" \
  --header 'Accept: application/json'
```

For POST/PUT requests, add `--header 'Content-Type: application/json' --data '{...}'`. **Body wrapping is inconsistent across endpoints** — Deal and Order writes wrap the payload in a `deal`/`order` key, Product *update* wraps it in `data`, but Record, Product *create*, and Ticket bodies are flat. Get this wrong and you'll silently write nothing or hit a 422. The exact shape for each write endpoint is in the reference file's "Body wrapping" table — check it rather than guessing from a similar endpoint.

## Working with real customer data — confirm before anything destructive

This skill touches a live CRM with real customers, deals, and money amounts. Reads (GET) and one-off creates the user explicitly asked for are fine to run directly. But **before deleting records, bulk-deleting/updating multiple rows, or soft-removing a deal/order/product/ticket (`is_removed: true`), tell the user exactly what will be affected and get an explicit yes** — these are hard to reverse and there's no CRM "undo" from this side. Reads and single-record creates/updates the user asked for by name don't need this pause.

## Core workflows

### 1. Find a customer before creating a deal/order/ticket

Deals, Orders, and Tickets all link to a `contact`/`account` record — you almost always need that record's `id` first (or, for Orders, you may instead let the API upsert one for you — see below). Search by phone or name using `search_all`, which does a full-text match across name/phone/email:

```bash
curl -G "https://crm.pancake.vn/api/workspaces/${WS}/lead/records" \
  --data-urlencode "api_key=${PANCAKE_API_KEY}" \
  --data-urlencode 'filter={"search_all":"0972273341"}'
```

Swap `lead` for `account` or `contact` depending which table the user means (`contact` is the one Deals/Tickets link to; `lead` is a pre-sale prospect). If you're not sure which table holds the person, search `contact` first — it's the most common target — and fall back to `lead`/`account` if empty. See the reference file for the full filter-object grammar (operators like `$having_value`, `$select_multi`, `$date_time`, etc.) when a simple `search_all` isn't precise enough.

### 2. Create or update a Record (lead/account/contact)

Same endpoint does both — POST with no `id` creates, POST with an existing `id` updates:

```bash
curl -X POST "https://crm.pancake.vn/api/workspaces/${WS}/contact/records?api_key=${PANCAKE_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Nguyễn Văn A", "phone_number": "0972273341", "source": ["-11"], "pancake_tags": ["104943019063372_11"]}'
```

`source` and `pancake_tags` take **IDs**, not display names — if the user says "tag this VIP" or "nguồn Facebook", first list Sources / Pancake Tags (workflow 5) to resolve the name to an ID, don't guess one.

### 3. Create a Deal

The deal object is a top-level `deal` key, and it must link to an existing contact/account record `id`:

```bash
curl -X POST "https://crm.pancake.vn/api/workspaces/${WS}/deals?api_key=${PANCAKE_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"deal": {"name": "Cơ hội bán CRM", "contact": "<record-uuid>", "revenue": 1500000, "status": "<status-uuid>"}}'
```

`status` must be a real status UUID from that workspace's pipeline — look it up first (workflow 4), don't invent one. If the user doesn't mention a status, omit it and let the workspace default apply rather than picking one yourself.

### 4. Move a Deal through the pipeline / close it

Look up valid status IDs first — they differ per workspace:

```bash
curl -G "https://crm.pancake.vn/api/workspaces/${WS}/module_statuses" \
  --data-urlencode "api_key=${PANCAKE_API_KEY}" \
  --data-urlencode "table_id=deals"
```

Then PUT only the fields that changed (unlisted fields are left untouched):

```bash
curl -X PUT "https://crm.pancake.vn/api/workspaces/${WS}/deals/${DEAL_ID}?api_key=${PANCAKE_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"deal": {"status": "<new-status-uuid>"}}'
```

There is **no delete endpoint for deals** — a "delete this deal" request means `{"deal": {"is_removed": true}}` (confirm first, per the safety note above). Also, a deal already sitting in a terminal status (`system.success` / `system.failure`) rejects any update except that same `is_removed` soft-delete — if a PUT 422s on a closed deal, that's almost certainly why; tell the user rather than retrying with different fields.

### 5. Look up Sources / Pancake Tags (needed to resolve names → IDs)

Both are small, shared-per-workspace lookup lists — worth fetching once and reusing within the conversation rather than re-fetching per record:

```bash
curl -G "https://crm.pancake.vn/api/workspaces/${WS}/sources" --data-urlencode "api_key=${PANCAKE_API_KEY}"
curl -G "https://crm.pancake.vn/api/workspaces/${WS}/pages/pancake_tags" --data-urlencode "api_key=${PANCAKE_API_KEY}"
```

(Note the tags path really is `/pages/pancake_tags`, not `/pancake_tags` — easy to mistype.)

### 6. Create an Order

Orders wrap in `order` and need a linked contact — either an existing `contact_id`, or a `contact` object (name + usually phone) that the API will upsert for you in one call:

```bash
curl -X POST "https://crm.pancake.vn/api/workspaces/${WS}/orders?api_key=${PANCAKE_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"order": {"contact_id": "<record-uuid>", "items": [{"product_id": "<product-uuid>", "quantity": 2, "price": 75000}]}}'
```

Totals (`cod`, `prepaid`, `total_discount`, etc.) are computed server-side from `items` and the payment fields — don't compute and send them yourself. Orders have no delete endpoint either; soft-delete via `{"order": {"is_removed": true}}` after confirming.

### 7. Monthly revenue report — by source, and by lead-age for Marketing (ca cũ / ca nóng)

This workspace tracks a sales funnel (tư vấn → phẫu thuật) via custom Date fields on `contact` (not exposed by the generic Records schema — they were added through the CRM's own UI, so they won't appear in [references/api-reference.md](references/api-reference.md)'s field table):

| Field key | Meaning |
|---|---|
| `ngay_de_sdt` | Ngày khách để lại SĐT / liên hệ (Zalo, hotline) |
| `ngay_tao_hoi_thoai` | Ngày tạo hội thoại (best-effort; the real timestamp lives in Pancake's Inbox module, not exposed by this API — this field is filled manually) |
| `ngay_tv_offline` | Ngày tư vấn offline |
| `ngay_phau_thuat` | Ngày phẫu thuật (surgery date). **Single value per contact** — a repeat customer's 2nd/3rd surgery overwrites it, so treat this as "most recent surgery," not full history. To track each occurrence separately, put the date on the linked Deal (`due_date` or `extra_info`) or Order (`extra_infor`) instead, since a contact can have many Deals/Orders. |
| `ngay` | Ngày sale nhập lead báo cáo — unrelated to surgery, don't confuse with `ngay_phau_thuat` |

Orders also carry a `source_ids` array (Source IDs — see workflow 5) that this workspace uses to flag collaborator-referred sales: source id `"24895"` = **Cộng tác viên**. Any order without that id is treated as **Marketing** (Facebook `-1`, Zalo, Hotline, Booking Form, etc. — anything that isn't a CTV referral).

**To reproduce "báo cáo doanh số tháng [N]" (monthly revenue report):**

1. **Pull the month's orders**, filtered on `inserted_at`:
   ```bash
   FILTER='{"fields":[{"field_name":"inserted_at","type":"$date_time","value":["YYYY-MM-01T00:00:00","YYYY-MM-31T23:59:59"]}]}'
   curl -s -G "https://crm.pancake.vn/api/workspaces/${WS}/orders" \
     --data-urlencode "api_key=${PANCAKE_API_KEY}" --data-urlencode "page_size=100" \
     --data-urlencode "filter=${FILTER}"
   ```
   `page_size=100` covers a typical month for this workspace; bump `page`/check `total_pages` if it doesn't.

2. **Revenue per order** = `cod + prepaid` (this equals total order value regardless of payment split — see api-reference.md's Orders section). Exclude `is_removed: true`.

   **Detecting a deposit ("cọc") order — the one reliable signal is `order.deposit != 0`** (equivalently `status == "partialPayment"` in this workspace; the two always agree — verified across a full month's orders). Don't gate this on `items[].price` being 0 — that was an earlier, too-narrow guess. A deposit order comes in two shapes, both flagged the same way by `deposit != 0`:
   - **Placeholder booking** (item `price: 0`, e.g. surgery not yet scheduled/priced): `cod` and `prepaid` are equal and opposite (e.g. `cod: -95000000, prepaid: 95000000`), netting to **0** — the deposit is real cash but there's no recognized sale yet. Report it as "tiền cọc đã thu, chưa ghi nhận doanh số," separate from both totals.
   - **Priced order, partially paid** (item price already set, service may already be delivered): `cod` (still owed) and `prepaid`/`deposit` (collected so far) sum to the *real*, nonzero order value — this **does** count in "doanh số ghi nhận" at its full `cod+prepaid` total like any other order (accrual, not cash-received). Additionally surface `deposit` (thu rồi) vs `cod` (còn nợ) as a cash-collection breakdown alongside the revenue total, since the user tracks that separately.

   Either way, always report the `deposit` figure explicitly when nonzero rather than letting it disappear into a net number — that's the detail the user checks for.

3. **Split CTV vs Marketing** by checking each order's `source_ids` for `"24895"`.

4. **For Marketing orders only**, get the linked contact's date fields without a second API call — each order's `record_relations` array already embeds the full contact object (including its custom fields) under `select(.table_name=="contact").record`:
   ```bash
   jq -r '.data.entries[] | select(.is_removed != true) as $o |
     ($o.record_relations[]? | select(.table_name=="contact") | .record) as $c |
     [$o.display_id, ($o.cod+$o.prepaid), $c.ngay_de_sdt, $c.ngay_phau_thuat] | @tsv'
   ```
   Classify:
   - **Ca cũ** (old lead, long cycle): `ngay_de_sdt`'s month/year is *before* the report month.
   - **Ca nóng** (fast conversion): `ngay_de_sdt` and `ngay_phau_thuat` fall in the *same* month.
   - Missing `ngay_phau_thuat` → can't classify; report separately rather than guessing.

5. Report: tổng doanh số, doanh số CTV, doanh số Marketing (= ca cũ + ca nóng + chưa phân loại), kèm danh sách khách hàng mỗi nhóm. Always call out anomalies you notice while building it (a surgery date in the future, a lead-source order missing every date field, a net-zero order) rather than folding them silently into the totals.

## Everything else

For the full endpoint list (exact paths, query parameters, pagination style per resource), every schema field with types and defaults, the complete filter-operator grammar, and the Product/Ticket-specific quirks (variation replace-on-write semantics, the create-vs-update body-wrapping mismatch, ticket's single-assignee requirement), read [references/api-reference.md](references/api-reference.md). It's organized so you can jump straight to the resource you need rather than reading it top to bottom.
