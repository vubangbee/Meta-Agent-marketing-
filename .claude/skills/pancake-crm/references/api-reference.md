# Pancake CRM API — full reference

Source: https://crm.pancake.vn/developers/ (Stoplight docs, API v2.0.0). Base URL for every path below: `https://crm.pancake.vn/api`. Every request needs `?api_key=...` appended (see SKILL.md for how to obtain it). All monetary fields across every schema are **integers in the smallest currency unit** — for VND that's the dong, no decimals.

## Table of contents

1. [Body wrapping — read this first](#body-wrapping--read-this-first)
2. [Records (lead / account / contact)](#records-lead--account--contact)
3. [Deals](#deals)
4. [Module Statuses](#module-statuses)
5. [Orders](#orders)
6. [Tickets](#tickets)
7. [Products](#products)
8. [Sources](#sources)
9. [Pancake Tags](#pancake-tags)
10. [Filter object grammar](#filter-object-grammar)

---

## Body wrapping — read this first

The API is not consistent about whether a write body is the resource itself or nested under a key. This trips up every endpoint below if assumed rather than checked:

| Resource | Create body | Update body |
|---|---|---|
| Record | flat (the record fields directly) | flat — same endpoint as create, POST with `id` set |
| Deal | `{"deal": {...}}` | `{"deal": {...}}` |
| Order | `{"order": {...}}` | `{"order": {...}}` |
| Ticket | flat | flat |
| Product | flat | **`{"data": {...}}`** — and `data.id` must match the `{id}` in the URL |

Product is the one to double-check every time: create is flat, update is wrapped in `data`. Get this backwards and the update either 422s or silently updates nothing.

---

## Records (lead / account / contact)

Three tables share one set of endpoints: `lead` (pre-sale prospect), `account`, `contact` (the table Deals/Tickets link to). Pass the table name as `{table_name}` in the path.

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/{table_name}/records` | List records. Query: `cursor` (pagination, from previous response), `filter` (JSON-encoded, see [grammar](#filter-object-grammar)), `view_id` (pass `all` to ignore view scoping) |
| POST | `/workspaces/{workspace_id}/{table_name}/records` | Upsert — include `id` to update an existing record, omit it to create |
| DELETE | `/workspaces/{workspace_id}/{table_name}/records` | Bulk delete. Query: `record_ids[]` (required, array of UUIDs) |
| GET | `/workspaces/{workspace_id}/record/{record_id}` | Get one record. Note the path is singular `record`, not `records`. Query: `table_name` (required) |

**Schema (Record):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Omit to create, provide to update |
| `name` | string, **required** | |
| `phone_number` | string | |
| `email` | string | |
| `birthday` | date-time (ISO 8601) | |
| `pancake_tags` | array[string] | Pancake Tag **IDs** — resolve names via [Pancake Tags](#pancake-tags) first |
| `source` | array[string\<int\>] | Source **IDs** — resolve via [Sources](#sources) first |
| `full_address` | string | |
| `owner` | array[uuid] | User IDs who own this record |
| `interested_product` | array[string] | Lead table only; absent for account/contact |
| `created_by` / `modified_by` / `created_on` / `modified_on` | — | Server-set, read-only |

---

## Deals

Pipeline opportunities. Body wrapped in `deal` for both create and update (see table above).

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/deals` | List, paginated with `page`/`page_size` (default 30). See query params below |
| POST | `/workspaces/{workspace_id}/deals` | Create. Link to a contact/account by sending its record `id` in `contact`/`account` |
| GET | `/workspaces/{workspace_id}/deals/{id}` | Get one |
| PUT | `/workspaces/{workspace_id}/deals/{id}` | Update — only fields present in the body change; omitted fields are untouched |

**List deals query parameters:** `page`, `page_size` (default 30), `filter` (JSON, shape `{"search_all": "..."}` — matches deal name, and phone-shaped values also match the linked contact/account phone), `ids[]`, `status[]` (status UUIDs), `owner[]` (assignee or related_owner match; pass the literal string `null` for unassigned), `contact_id`, `type[]` (`new_customer`/`returning_customer`), `success_rate[]`, `closed_reason[]`, `created_by[]`, `created_on` (preset range: `today`, `yesterday`, `tomorrow`, `thisWeek`, `lastWeek`, `nextWeek`, `thirtyDaysAgo`, `thisMonth`, `monthAgo`, `nextMonth`), `view=kanban` (groups response by status ID, each group also gets `total_revenue`), `view_id=due_at` (overdue deals only: past `due_date` and not yet `system.success`).

**Two hard rules on writes:**
- **No delete endpoint.** Soft-delete with `{"deal": {"is_removed": true}}`.
- **Terminal statuses lock the deal.** A deal in `system.success` or `system.failure` rejects any update with 422 *except* that same `is_removed: true` soft-delete.

**Schema (Deal):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `workspace_id` | integer | |
| `display_id` | integer | Human-readable sequential ID, read-only |
| `name` | string, **required** | |
| `status` | uuid | References a Module Status where `table_id: deals` — look up first, don't invent |
| `revenue` | integer, default 0 | Expected revenue |
| `success_rate` | enum or null | `"0%" "10%" "25%" "50%" "75%" "100%"` |
| `type` | enum or null | `new_customer` \| `returning_customer` |
| `due_date` | date-time or null | Expected closing date |
| `assignee` | uuid or null | User in charge |
| `related_owner` | array[uuid] or null | Other users following the deal |
| `creator_id` | uuid or null | |
| `source` | array[string] or null | Source IDs |
| `product_ids` | array[uuid] or null | Products quoted |
| `products` | array[Product] | Resolved server-side, read-only |
| `closed_reason` | array[string] | Reasons recorded on close |
| `note` | string or null | |
| `extra_info` | object or null | Dynamic custom fields; also stores the UI quotation (line items, discounts, surcharges) |
| `contact` / `account` | array[Record] | Resolved from `record_relations`, read-only on responses — to *link*, send the record `id` under these keys on write |
| `phone_number` | string or null | Convenience copy of the linked contact/account's phone, read-only |
| `record_relations` | array[object] | `{table_name, type, record_id, related_id, record}` |
| `is_removed` | boolean, default false | Soft-delete flag |
| `inserted_at` / `updated_at` | date-time | |

---

## Module Statuses

Pipeline stages, scoped per workspace and per module (`deals`, `task`, `calendar`, `rating`, …). Status UUIDs differ between workspaces — always resolve by name/value here rather than hardcoding an ID from a prior session.

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/module_statuses` | List, ordered by `position`. Query: `table_id` (e.g. `deals`) to filter to one module, omit for all |

A new workspace starts with these deal statuses in order: `system.new`, `system.introduce`, `system.negotiate`, `system.priceQuote`, `system.success` (terminal), `system.failure` (terminal).

**Schema (Module Status):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | This is the value stored in `Deal.status` |
| `workspace_id` | integer | |
| `table_id` | string | e.g. `"deals"` |
| `name` | string | `system.*` key for built-ins, custom label otherwise |
| `value` | string | Localized display label — show this to the user, not `name` |
| `color` | hex string | |
| `position` | integer | Ascending order in the pipeline |
| `is_default` | boolean | Built-in status; can't be renamed/deleted |
| `is_removed` | boolean | |

---

## Orders

Sales orders with line items. Body wrapped in `order` for both create and update.

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/orders` | List, paginated (`page`/`page_size`, default 30) |
| POST | `/workspaces/{workspace_id}/orders` | Create |
| GET | `/workspaces/{workspace_id}/orders/{id}` | Get one, includes line items and related records |
| PUT | `/workspaces/{workspace_id}/orders/{id}` | Update — same shape as create; only provided fields change |

**List orders query parameters:** `page`, `page_size`, `search` (matches order code like `OD00012` or bare `12`, `custom_id`, or billing phone), `filter` (JSON, structured — same style as Records', see [grammar](#filter-object-grammar)), `deal_id` (orders linked to a given deal).

**Create requires a contact link:** either `contact_id` (existing record UUID) or a `contact` object (`name`, usually `phone_number`) which the API upserts into the contact table and links automatically — useful when you haven't already looked the customer up.

**Line items on update are reconciled, not replaced wholesale:** items with an existing `item_id` are updated in place, items without one are inserted as new, and existing items you omit from the list are removed. This differs from Products' variations, which fully replace on every write — don't confuse the two.

**No delete endpoint.** Soft-delete with `{"order": {"is_removed": true}}` (confirm with the user first).

Totals — `total_quantity`, `total_discount`, `cod`, `prepaid`, `cash` — are all **computed server-side** from `items` and the payment fields (`discount`, `transfer_money`, `surcharge`, `deposit`). Don't compute and send these yourself; send the inputs and let the server derive them.

**Schema (Order):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `workspace_id` | integer | |
| `display_id` | integer | Rendered as `OD{display_id}` |
| `custom_id` | string or null | Custom order code |
| `status` | string, default `"new"` | Free-form per workspace, not a Module Status UUID like Deal |
| `bill_phone_number` / `bill_full_name` / `bill_email` | string or null | Default from the linked contact |
| `note` / `note_image` | string / array[url] | |
| `assigning_seller_id` | uuid or null | |
| `creator_id` | uuid or null | |
| `related_owner` | array[uuid] or null | |
| `total_quantity` | integer, computed | |
| `discount` | integer | Order-level discount input |
| `total_discount` | integer, computed | Sum of line-item discounts |
| `transfer_money` | integer | Paid by bank transfer |
| `surcharge` | integer | |
| `cod` | integer, computed | `= sum(item totals) + surcharge − discount − prepaid` |
| `prepaid` | integer, computed | `= deposit + cash + transfer_money` |
| `deposit` | integer | |
| `cash` | integer, computed, response-only | `= prepaid − transfer_money − deposit` |
| `source_ids` | array[string] or null | |
| `is_removed` | boolean | |
| `extra_infor` | object or null | *(sic — no "e")* Dynamic fields, also stores `item_product_ids`/`item_prices` helpers |
| `items` | array[Order Item] | See below |
| `record_relations` | array[object] | Linked contact/account/deal/calendar |
| `rating` | object or null | Latest rating on the order, if any |
| `inserted_at` / `updated_at` | date-time | |

**Order Item:**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Use as `item_id` when updating to match an existing line |
| `order_id` | uuid | |
| `product_id` | uuid or null | |
| `variation_id` | uuid or null | SKU, if the product has variations |
| `quantity` | integer | |
| `price` | integer | Unit price |
| `discount` | integer | Per-unit discount |
| `total_discount` | integer, computed | |
| `total_price` | integer, computed | `= subtotal − total_discount` |
| `variation_info` | object or null | Snapshot of the product/variation at order time |
| `workspace_id` | integer | |
| `inserted_at` / `updated_at` | date-time | |

---

## Tickets

Work items (issues, tasks) linked to a contact. Body is flat for both create and update.

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/tickets` | List. Query: `cursor` |
| POST | `/workspaces/{workspace_id}/tickets` | Create |
| GET | `/workspaces/{workspace_id}/tickets/{ticket_id}` | Get one |
| PUT | `/workspaces/{workspace_id}/tickets/{ticket_id}` | Update — only provided fields change |
| DELETE | `/workspaces/{workspace_id}/tickets/{ticket_id}` | Delete (tickets, unlike Deals/Orders, do have a real delete endpoint — confirm with the user first) |

**Schema (Ticket):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `display_id` | integer | Sequential, read-only |
| `ticket_id` | string or null | Custom zero-padded code, e.g. `"00001"` |
| `title` | string, **required** | |
| `description` / `note` | string or null | |
| `category` | string or null | Free-form, e.g. `"order"` |
| `status` | enum, default `"new"` | `new` \| `in_progress` \| `completed` |
| `priority` | enum or null | `low` \| `medium` \| `high` \| `null` |
| `due_date` | date-time or null | |
| `completed_at` | date-time or null | |
| `assignee_ids` | array[uuid], **required, exactly 1 item** | Despite the plural name, exactly one assignee — sending 0 or 2+ fails validation |
| `related_owner` | array[uuid] or null | Everyone else related to the ticket |
| `creator_id` | uuid | |
| `extra_info` | object or null | Dynamic custom fields |
| `kanban_order` | string or null | Sort key for kanban view |
| `source` | array[string\<int\>] | Source IDs |
| `record_relations` | array[object] | Other linked tasks/orders/deals/records/tickets |
| `contact_id` | uuid, **required** | Must be an existing `contact`-table record `id` — resolve via Records search first |
| `is_removed` | boolean | |
| `inserted_at` / `updated_at` | date-time | |

---

## Products

Products, services, and service packages. **Body wrapping differs between create and update** — see the [table at the top](#body-wrapping--read-this-first).

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/products` | List. See query params below |
| POST | `/workspaces/{workspace_id}/products` | Create — flat body |
| GET | `/workspaces/{workspace_id}/products/{id}` | Get one |
| PUT | `/workspaces/{workspace_id}/products/{id}` | Update — body is `{"data": {...}}`, and `data.id` must equal the URL `{id}` |

**List products query parameters:** `category_ids`, `ids`, `filter` (JSON structured filter, same grammar as Records), `get_info=true` (wraps the response in a paginated envelope with `total_entries`/`total_pages` — otherwise `data` is just the bare entries array), `show_products=true` (return parent products with their `variations` array nested; **default behavior flattens each variation into its own entry** in the list, with the variation's own `id`/`custom_id`/prices/`remain_quantity`/`images` overriding the parent's and `product_id` pointing back to the parent — decide which shape you want before parsing the response).

`type` determines behavior: `product` (tracks `remain_quantity`), `service` (has `duration` in minutes, ignores `remain_quantity`), `service_package` (bundle via `service_package_product`, ignores both `remain_quantity` and `duration`). Type-specific fields are stripped server-side regardless of what you send.

**Schema (Product):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Omit on create, required on update (and must match URL) |
| `name` | string, **required** | |
| `type` | enum, default `product` | `product` \| `service` \| `service_package` |
| `custom_id` | string or null | Unique per workspace |
| `description` | string or null | |
| `images` | array[url] or null | |
| `category_ids` | array[uuid] or null | |
| `retail_price` | integer, default 0 | |
| `import_price` | integer, default 0 | Cost price |
| `remain_quantity` | integer, default 0 | Only meaningful for `type: product` |
| `duration` | integer or null | Minutes; only meaningful for `type: service` |
| `is_removed` | boolean | |
| `product_attributes` | array[Product Attribute] | Defines the axes used to build variations, e.g. Color/Size |
| `variations` | array[Product Variation] | **Fully replaces on write**: rows whose `custom_id` isn't in the new list are deleted, matches are updated, new ones inserted |
| `service_package_product` | array[Service Package Component] | Only for `type: service_package`; fully replaces on write |

**Product Attribute:** `name` (required, e.g. `"Color"`), `values` (array[string], e.g. `["Red","Blue","Green"]`), `keyword` (array[object], optional search/recognition metadata).

**Product Variation:**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Omit on create |
| `custom_id` | string, **required** | The merge key on update — this is what matches a variation to an existing row, not `id` |
| `retail_price` / `import_price` | integer, default 0 | |
| `remain_quantity` | integer, default 0 | |
| `images` | array[url] | Falls back to the parent product's images if empty |
| `sort_variation_attributes` | string or null | Canonical attribute-value string for sorting, e.g. `"Red\|L"` |
| `extra_info` | object | Free-form, e.g. `{"fb_catalog_id": "..."}` |
| `is_removed` | boolean | |

**Service Package Component:** `id` (required, the component service product's ID), `service_package_product_quantity` (integer — quantity of that service per package).

---

## Sources

Shared, workspace-wide list of customer origins (Facebook, Google, TikTok, Zalo, Shopee, etc.). Read-only via this API — no create/update/delete endpoints exposed.

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/sources` | List all sources in the workspace |

**Schema (Source):**

| Field | Type | Notes |
|---|---|---|
| `id` | string\<integer\> | Reference this in `Record.source` / `Deal.source` |
| `name` | string, **required** | e.g. `"Facebook"` |
| `parent_id` | integer or null | For hierarchical sources |
| `image` | url or null | |
| `custom_id` | string or null | |
| `link` | string or null | |
| `is_removed` | boolean | |

---

## Pancake Tags

Shared, workspace-wide labels used to segment/filter records. Read-only via this API.

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces/{workspace_id}/pages/pancake_tags` | List all tags in the workspace — note the `/pages/` segment, it's not just `/pancake_tags` |

**Schema (Pancake Tag):**

| Field | Type | Notes |
|---|---|---|
| `id` | string, **required** | Reference this in `Record.pancake_tags`, e.g. `"104943019063372_11"` |
| `text` | string, **required** | Display label, e.g. `"Quality Check"` |
| `description` | string or null | |
| `color` | hex string | Primary color |
| `lighten_color` | rgba string | Background/lightened color |

---

## Filter object grammar

Used by the `filter` query parameter on **List records** and **List products** (List deals uses a much simpler `{"search_all": "..."}`-only shape — see the Deals section). The value is a JSON object, URL-encoded into the query string:

```json
{
  "search_all": "0972273341",
  "is_group": false,
  "fields": [
    {
      "field_name": "phone_number",
      "type": "$having_value",
      "value": null,
      "is_filter_exclude": false
    }
  ]
}
```

| Property | Type | Meaning |
|---|---|---|
| `search_all` | string, optional | Full-text search across text/phone/number fields (name, phone_number, email, …). Use this alone for a simple "search box" lookup — it's usually all you need |
| `is_group` | boolean, optional | `true` combines `fields` conditions with OR; `false`/omitted combines with AND |
| `fields` | array, optional | Structured field conditions, combined per `is_group` |

Each entry in `fields`:

| Property | Type | Meaning |
|---|---|---|
| `field_name` | string | Field to filter on, e.g. `phone_number`, `name`, `email` |
| `type` | string | Operator — see table below |
| `value` | any, optional | Depends on operator: single value, numeric string, or array. Omit/`null` for `$having_value`/`$having_no_value` |
| `is_filter_exclude` | boolean, optional | `true` negates the condition (NOT) |

**Operators (`type`):**

| Operator | Meaning |
|---|---|
| `$having_value` | Field is non-empty |
| `$having_no_value` | Field is empty |
| `$enter_value` | Field equals/contains `value` |
| `$select_multi` | Field matches any value in the `value` array |
| `$date_time` | Field falls within `[from, to]` given in `value` |
| `$greater_than` / `$less_than` / `$greater_than_equal` / `$less_than_equal` | Numeric comparison — pass the number as a string in `value` |
| `$association` | Field references one of the record IDs in `value` |
| `$duplicate` | Field's value is duplicated across records |

For most conversational requests ("tìm khách có SĐT ...", "search for customer named ...") a bare `{"search_all": "..."}` is enough — reach for the `fields` grammar only when the user needs a precise condition a full-text search can't express (e.g. "leads with no email", "deals over 10 triệu").
