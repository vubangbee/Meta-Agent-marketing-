---
name: pancake-lead-classify
description: Hàng loạt phân loại "Giai đoạn khách hàng tiềm năng" = Đủ tiêu chuẩn trên Facebook Meta Business Suite cho các hội thoại Pancake khớp bộ thẻ tag + khoảng ngày tạo, rồi ghi note "Đã phân loại" qua Pancake API. Dùng khi user yêu cầu "phân loại hội thoại/khách hàng tiềm năng" cho hôm nay, hôm qua, tháng này, tháng trước, hoặc một khoảng ngày bất kỳ.
metadata:
  author: vubangdigital
---

# Pancake → Meta Business Suite Lead Classification

> **Mega-prompt tự chứa.** Đọc hết file này trước khi thao tác. Mọi quyết định kiến trúc dưới đây đã được kiểm chứng thực chiến trên 333 hội thoại (2 fanpage, tháng 7 + tháng 8/2026) — **không tự ý "tối ưu" lại các bước đã chốt**, mỗi bước đều là kết quả sửa một lỗi thật đã từng làm hỏng dữ liệu hoặc treo cả batch.

---

## 1. Mục tiêu cốt lõi

Với mỗi hội thoại Pancake thỏa **(có ÍT NHẤT 1 trong N thẻ tag mục tiêu) VÀ (được tạo trong khoảng ngày X→Y) VÀ (thuộc fanpage đang chạy ads)**:

1. Mở hội thoại đó trên **Meta Business Suite** (qua nút "Xem trên Facebook" của Pancake).
2. Đặt trường **"Giai đoạn khách hàng tiềm năng" → "Đủ tiêu chuẩn"** (nếu chưa phải giá trị đó).
3. Ghi note **"Đã phân loại"** vào hồ sơ khách trên Pancake **qua API** (không gõ tay vào UI).

**Ràng buộc bất di bất dịch:**
- Facebook **KHÔNG có API** cho trường "Giai đoạn khách hàng tiềm năng" → bước 2 **bắt buộc** phải qua trình duyệt. Đừng đi tìm API, đã tìm rồi, không có.
- **Chỉ gửi note khi đã thật sự xác minh/đặt được stage.** Hội thoại lỗi không mở được Facebook → **KHÔNG gửi note**, đưa vào danh sách báo cáo cho user kiểm tra tay. Gửi note cho ca chưa xử lý = nói dối dữ liệu, sau này không ai biết ca nào còn sót.
- Sai sót thầm lặng (mở nhầm khách, đặt nhầm stage) **nguy hiểm hơn** chạy chậm. Luôn xác minh tên trước khi click, fail loud khi lệch.

---

## 2. Kiến trúc đã chốt (và những gì đã bị loại bỏ)

**Kiến trúc lai (hybrid) — dùng đúng công cụ cho đúng việc:**

| Giai đoạn | Công cụ | Lý do |
|---|---|---|
| Liệt kê danh sách mục tiêu | **Pancake public API** | Nguồn sự thật duy nhất, ổn định, không phụ thuộc UI. Bộ lọc UI của Pancake trả kết quả **không ổn định giữa các lần reload** (thực đo: 119 → 102 hội thoại cho cùng 1 điều kiện). |
| Mở + đặt stage | **Trình duyệt Playwright (UI)** | Facebook không có API cho trường này. |
| Ghi note | **Pancake public API** (`add_note`) | UI có bug `handleNoteSubmit` (crash `Cannot read properties of undefined (reading '0')`), Enter chỉ xuống dòng. API luôn 200. |

**Đã thử và LOẠI BỎ — đừng lặp lại (đã tốn nhiều giờ):**

| Cách tiếp cận | Kết quả thực đo | Kết luận |
|---|---|---|
| Mở link trực tiếp `pancake.vn/<slug>?c_id=...` bằng `page.goto()` | Param `c_id` bị app xóa trong ~300ms, luôn rơi về hội thoại mặc định. Đo tại 300ms/800ms/1.5s/2.5s/4s — **không có cửa sổ nào đúng**. | ❌ Không dùng |
| `history.pushState()` + `PopStateEvent` (giả lập click link nội bộ) | Chỉ hoạt động với hội thoại **đã được cache client-side** từ trước. Với hội thoại mới → thất bại y hệt `goto()`. | ❌ Không dùng |
| Gõ tên vào ô "Tìm kiếm" của Pancake | Xóa sạch bộ lọc tag+ngày; nút "Lọc theo" biến mất khi ô search có focus; kết quả server trả sau 1.5-2s → chờ 700ms sẽ **click nhầm khách** (đã xảy ra 2 lần, tạo 2 kết quả "đã phân loại" giả). | ❌ Không dùng |
| Nhảy nhanh theo công thức `scrollTop += (posĐích - posHiệnTại) * 94px` | Chiều cao dòng không đồng đều (dòng nhiều tag bị wrap) → tích lũy sai số, **vọt qua và bỏ sót hội thoại** (đã bỏ sót 2 ca). | ❌ Không dùng |

**→ Cách duy nhất đáng tin để mở 1 hội thoại: áp bộ lọc trên UI rồi CLICK vào dòng trong danh sách, cuộn từng bước nhỏ, xác minh bằng tên trước mỗi lần click.** App Pancake chỉ fetch dữ liệu hội thoại khi có click thật vào dòng — URL chỉ là gợi ý bị ghi đè.

---

## 3. Tiền điều kiện

| Thành phần | Kiểm tra | Nếu thiếu |
|---|---|---|
| MCP browser Playwright có profile lưu cookie | Tool `mcp__<tên-server>__browser_*` khả dụng | Yêu cầu user setup (xem `references/setup.md`) |
| **Cửa sổ trình duyệt rộng ≥ 1300px** | `browser_resize` width ≥ 1300 ngay đầu phiên | **Bắt buộc** — hẹp hơn, giao diện Pancake co lại và **ẩn luôn các nút cần thao tác** (icon ⓘ, "Xem trên Facebook") → mọi selector đều fail dù code đúng |
| Đã đăng nhập sẵn Pancake + Facebook trong profile đó | Mở `pancake.vn` không thấy màn login | Nhờ user đăng nhập tay 1 lần, cookie sẽ được giữ |
| Skill `pancake-integration` + file `scripts/.env` có token | `python scripts/pancake_client.py test-connection` → `ok=True` | Yêu cầu user cấu hình `page_access_token_N` |
| Biết `page_id` các fanpage mục tiêu | Có trong `.env` | Hỏi user |
| Biết bộ thẻ tag mục tiêu | Mặc định 10 thẻ ở §4.1 | Hỏi user, đừng đoán |

---

## 4. Quy trình thực thi chuẩn (7 phase)

### Phase 0 — Chốt tham số với user (30 giây, không bỏ qua)

Xác nhận đúng 3 thứ, nếu user đã nói rõ thì không cần hỏi lại:
- **Khoảng ngày** + phải theo **thời gian TẠO** (`inserted_at`), không phải thời gian cập nhật.
- **Bộ thẻ tag** và logic **HOẶC (OR)** — có ít nhất 1 thẻ là đủ.
- **Danh sách fanpage**.

> ⚠️ "Tháng trước" là tương đối. Ngày 08/09 mà user nói "tháng 7" thì **không** được bấm nút "Tháng trước" (nó ra tháng 8) — phải nhập khoảng ngày tùy chỉnh.

### Phase 1 — Liệt kê danh sách mục tiêu qua API

```bash
python .claude/skills/pancake-lead-classify/scripts/enumerate_conversations.py \
  --since 2026-07-01 --until 2026-08-01 \
  --pages 108067022357425,107684028988499 \
  --out-dir <scratchpad>/lead-classify-2026-07
```

`--until` là **exclusive** (đầu ngày hôm sau). Script tự:
- Gọi `fetch_conversations_complete(..., order_by="inserted_at", types=["INBOX"])` — tự chia nhỏ cửa sổ khi chạm trần 60 hội thoại/lần gọi.
- Lọc client-side theo **giao** với bộ tag (logic OR).
- Tách **theo từng page**, giữ nguyên thứ tự mới→cũ (khớp đúng thứ tự UI sẽ hiển thị).
- Phát hiện **tên trùng** trong cùng page và cảnh báo.
- In cảnh báo nếu tổng ≥ ngưỡng rate-limit (§6).

Output trong `--out-dir`:
- `target-conversations.json` — đầy đủ (chứa PII, **không bao giờ paste vào chat**, chỉ báo con số).
- `page-<page_id>-ordered.json` — `[{pos, name, pcid, c_id}]` theo đúng thứ tự UI.
- `page-<page_id>-names.json` — mảng tên thuần, để paste vào script trình duyệt.
- `summary.json` — số lượng/page, tên trùng, khoảng ngày.

**Xác nhận với user tổng số lượng trước khi chạy tiếp.**

### Phase 2 — Mở đúng fanpage, đặt kích thước cửa sổ, kiểm tra scope

Làm **từng page một**, xong page 1 mới sang page 2 (yêu cầu rõ ràng của user, cũng tránh nhầm dữ liệu chéo).

**2a. Đặt độ rộng cửa sổ TRƯỚC KHI làm bất cứ việc gì** (làm 1 lần đầu phiên):

```
browser_resize  width: 1400  height: 900
```

> ⚠️ **Tối thiểu 1300px.** Dưới ngưỡng này Pancake chuyển sang bố cục thu gọn và **ẩn hẳn các nút cần thao tác** — icon ⓘ "Thông tin hội thoại" và nút "Xem trên Facebook" không render ra DOM. Triệu chứng sẽ giống hệt lỗi khác (`NO_INFO_PANEL`, `waitForEvent 'page'` timeout) khiến mất thời gian debug nhầm hướng, dù code hoàn toàn đúng. **Kiểm tra độ rộng trước khi nghi ngờ selector.**

**2b. Mở fanpage:**

```js
await page.goto('https://pancake.vn/<slug>', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
// Xác nhận viewport đủ rộng (nếu MCP không có browser_resize)
await page.setViewportSize({ width: 1400, height: 900 });
```

> ⚠️ **Bẫy scope trang:** App có state "trang đang active" **độc lập với URL**. Có lúc vào đúng URL `/bacsidacquang` nhưng danh sách hiển thị lại là dữ liệu mặc định của trang khác. Triệu chứng: tên trong danh sách hoàn toàn xa lạ so với danh sách API.
> **Cách xử lý:** sau khi áp bộ lọc (Phase 3), **luôn đối chiếu 2-3 tên đầu tiên với `page-<id>-ordered.json`**. Nếu không khớp → click vào tên tài khoản góc trên bên phải (mở dropdown chọn kênh) rồi thử lại. Không khớp mà vẫn chạy = phân loại nhầm hàng loạt.

### Phase 3 — Áp bộ lọc trên UI (tag + ngày tạo)

Dùng `assets/browser-apply-filter.js` (copy vào `browser_run_code_unsafe`). Trình tự bắt buộc:

1. **Click "Lọc theo"** → dò lại chỉ số checkbox **mới hoàn toàn** mỗi lần:
   > ⚠️ Chỉ số checkbox **KHÔNG ổn định** giữa các trang và các phiên (thực đo: lệch giữa `/multi_pages` ↔ `/bacsidacquang`, và giữa 2 fanpage). Luôn duyệt toàn bộ `input[type="checkbox"]`, leo lên `closest('label') || parentElement` tối đa 4 cấp lấy `innerText` đầu tiên khác rỗng, dựng map `tên → index` tại chỗ. **Không hardcode.**
2. **Kiểm tra "Điều kiện"** — phải là **HOẶC**. Mặc định **khác nhau tùy page** (thực đo: page A mặc định HOẶC, page B mặc định VÀ). Nếu đang là VÀ → click vào "Điều kiện" → chọn radio "Thẻ A HOẶC Thẻ B".
3. **Click icon lịch `.filter-by-time`**.
4. **KIỂM TRA TAB "Thời gian tạo"** trước khi chọn ngày:
   ```js
   const seg = await page.locator('.ant-segmented').first().evaluate(el => el.outerHTML);
   // Phải thấy: title="Thời gian tạo" ... aria-selected="true"
   ```
   > ⚠️ Mặc định thường là **"Thời gian cập nhật"** → nếu bỏ qua bước này, bộ lọc chạy sai hoàn toàn và kéo về đầy hội thoại cũ đã xử lý. Đây là yêu cầu user nhấn mạnh nhiều lần.
5. **Nhập khoảng ngày:**
   - Quick-pick ("Hôm nay"/"Hôm qua"/"Tháng này"/"Tháng trước") chỉ dùng khi khớp **chính xác** ý user tại thời điểm chạy.
   - Ngày tùy chỉnh: **dùng `.type()` chứ KHÔNG dùng `.fill()`** — `.fill()` khiến ô còn lại bị xóa trắng. Nhập lần lượt `01/07/2026 00:00:00` và `31/07/2026 23:59:59`, rồi **đọc lại `inputValue()` cả 2 ô để xác nhận cả hai đều có giá trị** trước khi bấm "Lọc".
   - Nếu ô bị loạn: điều hướng lịch bằng nút prev-month rồi click ô ngày với `{ force: true }` (có div trong suốt chặn pointer events).
6. **Click "Lọc"** (quick-pick thì tự áp dụng, không cần).
7. **Đối chiếu 2-3 tên đầu với danh sách API** (Phase 2). Khớp → chạy tiếp. Lệch → dừng, báo user.

### Phase 4 — Duyệt & phân loại theo lô

Dùng `assets/browser-classify-batch.js`. Điền `EXPECTED_NAMES` = một lát cắt **liên tục** 15-25 tên từ `page-<id>-names.json` (đúng thứ tự).

> 🔑 **Cơ chế nạp dữ liệu (đo 2026-09-09):** danh sách **lazy-load** — `scrollHeight` chỉ bao vùng đã nạp (đo được 6880px khi mới nạp ~79/164 dòng) và **chỉ tăng khi cuộn tới gần đáy**. Hệ quả: **không thể nhảy vượt vùng đã nạp** — mọi cú `scrollTop += <khoảng cách lớn>` đều bị kẹp lại (thực đo: nhắm pos81 nhưng dừng ở pos51). Phải cuộn thành nhiều nấc để app nạp dần.

**Phương pháp: quét cửa sổ + click thẳng theo chỉ số** (thay cho việc kéo từng dòng lên đầu):

```
findIndex(tên):
  lặp tối đa 120 lần:
    đọc rows.allInnerTexts() -> mảng tên đang render
    nếu có tên -> trả về chỉ số k
    scrollTop += 600, chờ 400ms
    nếu scrollTop không đổi -> đã chạm đáy, thoát
  chạm đáy vẫn không thấy -> scrollTop = 0, quét lại 1 lượt (phòng đã vọt qua)
```

Ưu điểm so với cách kéo dòng lên đầu: đi được **khoảng cách xa tuỳ ý**, tự nạp thêm dữ liệu, và **tự nhiên xử lý được phần đuôi danh sách** (không cần nhánh riêng khi cửa sổ ảo ngừng trượt). Không cần đưa dòng lên vị trí 0 — chỉ cần tìm thấy rồi click.

> ⚠️ Chỉ an toàn khi tên **không nằm trong nhóm trùng tên** (`summary.json` → `duplicate_names`). Với tên trùng, phải duyệt tuần tự và bám vị trí, không dùng tìm-theo-tên.

Vòng lặp cho mỗi tên:

```
1. k = findIndex(tên). k < 0 -> ghi NOT_FOUND, sang tên kế tiếp.
2. Đọc lại tên tại rows.nth(k) NGAY TRƯỚC KHI CLICK (cửa sổ có thể đã dịch).
   Lệch -> ghi MISMATCH, không click.
3. Click rows.nth(k) → chờ 700ms.
3. ensureInfoOpen(): nếu `.open-in-messenger-button` chưa hiện → click
   `.conv-action-btn.color-primary`; vẫn chưa hiện → click lần nữa (nút này
   là TOGGLE, trạng thái panel giữ lại giữa các hội thoại).
4. Mở Facebook: Promise.all([ context().waitForEvent('page', {timeout:8000}),
   click('.open-in-messenger-button') ]).
5. Chờ domcontentloaded + 3500ms. Đọc combobox `role=combobox[name=/Stage Selector/i]`.
6. Nếu KHÔNG bắt đầu bằng "Đủ tiêu chuẩn":
   click combobox → click role=option name='Đủ tiêu chuẩn' **{ exact: true }**.
7. fbPage.close().
8. catch: ghi lỗi + ĐÓNG tab Facebook lạc (tránh rác tab).
```

> 🔥 **`exact: true` là bắt buộc.** Không có nó, Playwright khớp cả `"Không đủ tiêu chuẩn"` (chứa nguyên chuỗi `"Đủ tiêu chuẩn"`). Đã từng đặt nhầm 1 khách thành **"Không đủ tiêu chuẩn"** vì dùng `.last()` để né lỗi strict-mode. Sau khi đặt stage, **đọc lại combobox để xác nhận giá trị đúng**.

> ⚠️ **Không dùng công thức nhảy theo px để định vị.** Ngoài lý do chiều cao dòng không đều, còn bị chặn bởi lazy-load ở trên. Cách quét cửa sổ đã bao trùm cả hai vấn đề.

> ✅ **Xử lý ca lỗi rải rác:** vì `findIndex` quét được cả danh sách, có thể gom các vị trí **không liền nhau** (vd pos 2, 81, 90, 114) vào cùng một lô — không cần chạy tuần tự từ đầu.

### Phase 5 — Gửi note qua API (theo lô)

Sau **mỗi lô** Phase 4, gửi note cho **đúng những ca `status: ok`**:

```bash
python .claude/skills/pancake-lead-classify/scripts/send_notes.py \
  --items '[{"i":3,"page_id":"108067022357425","pcid":"764f3c24-..."}, ...]'
# hoặc: --file <đường dẫn json>  --message "Đã phân loại"
```

- **Bỏ qua mọi ca `FB_ERROR` / `MISMATCH` / `NO_INFO_PANEL`.**
- `pcid` = `page_customer_id` (UUID trong `page-<id>-ordered.json`), **khác** `c_id` trong link.
- Gộp 15-25 ca/lần gọi, đừng gọi từng ca.

### Phase 6 — Báo cáo

Báo cho user (tiếng Việt, ngắn gọn):
- Số đã xong / tổng, theo từng page.
- **Danh sách ca lỗi kèm lý do**, ghi rõ "chưa gửi note, cần kiểm tra tay".
- **Các ca stage ban đầu bất thường** đã bị ghi đè — `Đã chuyển đổi`, `Spam`, `Sắp lại cột đã chuyển đổi` → nêu tên để user xác nhận có đúng ý không (khách đã chốt bị hạ về "Đủ tiêu chuẩn" có thể ngoài ý muốn).
- Bất kỳ sai sót nào tự gây ra và đã sửa (nêu thẳng, đừng giấu).

---

## 5. Bảng bẫy chí mạng (tra nhanh)

| # | Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|---|
| 0 | **Không tìm thấy nút ⓘ / "Xem trên Facebook"** dù code đúng | **Cửa sổ < 1300px** → Pancake thu gọn giao diện, không render các nút này | `browser_resize` width ≥ 1300. **Kiểm tra đầu tiên** trước khi nghi selector |
| 1 | Danh sách toàn tên lạ dù URL đúng | State "trang active" ≠ URL | Đối chiếu tên với API; click tên tài khoản góc phải |
| 2 | Lọc ra hội thoại cũ đã xử lý | Tab đang là "Thời gian cập nhật" | Kiểm tra `aria-selected` trước khi chọn ngày |
| 3 | Click nhầm checkbox tag | Index checkbox đổi theo page/phiên | Dò lại map tên→index mỗi lần |
| 4 | Lọc ra quá ít hội thoại | Điều kiện đang là **VÀ** | Đổi sang HOẶC |
| 5 | Ô ngày bắt đầu bị trắng | Dùng `.fill()` | Dùng `.type()`, đọc lại cả 2 ô |
| 6 | Đặt nhầm "Không đủ tiêu chuẩn" | Thiếu `exact: true` | Luôn `{ exact: true }` + đọc lại xác nhận |
| 7 | Nút "Xem trên Facebook" không hiện | `.conv-action-btn` là toggle | `ensureInfoOpen()` click tối đa 2 lần |
| 8 | Vọt qua hội thoại | Nhảy theo công thức px | Chỉ cuộn từng bước 12px |
| 9 | `gotoRow` kẹt ở 1 tên | Đã tới cuối danh sách | Chuyển sang `rows.nth(k)` trực tiếp |
| 10 | Combobox timeout ~3% số ca | Thread Facebook lỗi riêng lẻ | Thử lại 1 lần; vẫn lỗi → ghi nhận, **không gửi note**, báo user |
| 11 | **Mọi** tab MBS lỗi liên tiếp | Facebook rate-limit / khóa | §6 — dừng ngay |

---

## 6. Guardrail: rate-limit của Meta (BẮT BUỘC)

**Sự cố thật 2026-09-08:** sau ~165-170 lượt mở MBS (batch tháng 8, chạy êm) rồi nối tiếp ~130 lượt nữa (batch tháng 7) trong cùng ngày → **~290-300 lượt tích lũy**, Facebook **tạm khóa toàn bộ Meta Business Suite** của tài khoản. Mọi tab MBS — kể cả Hộp thư tổng không kèm `c_id` — đều trả trang lỗi *"Chúng tôi gặp sự cố khi hoàn thành yêu cầu của bạn"*. Chờ 20 phút không hết.

**Quy tắc (user chốt):**
- Sau Phase 1, nếu tổng số hội thoại (cộng cả các page) **≥ ~170-200** → **cảnh báo user trước khi bắt đầu Phase 4**, để user quyết định: chạy tiếp / chia nhỏ / để hôm khác. Không tự ý chạy tiếp.
- **Không** thêm delay nhân tạo giữa từng hội thoại, **không** đặt hạn mức cứng theo ngày. Một batch cỡ 1 tháng (~150-200) là đơn vị an toàn đã biết. Rủi ro nằm ở việc **chồng batch lớn thứ hai trong cùng ngày**.
- **Khi nghi bị khóa:** mở URL Hộp thư tổng **không kèm `c_id`**. Nếu chính nó cũng lỗi → khóa cấp tài khoản, không phải lỗi thread. **Dừng ngay**, báo user, đề nghị họ tự mở Facebook bằng trình duyệt cá nhân để xem có yêu cầu xác minh không. Tối đa 1-2 lần kiểm tra lại, **không lặp vô hạn**.

---

## 7. Ví dụ end-to-end (rút gọn, chạy thật)

```
User: "Phân loại hội thoại được tạo trong tháng 7/2026"

[Phase 0] Xác nhận: 01/07→31/07/2026, theo ngày tạo, 10 thẻ mặc định logic OR,
          2 fanpage bacsidacquang + drDacQuang. → user đồng ý.

[Phase 1] $ python scripts/enumerate_conversations.py --since 2026-07-01 \
            --until 2026-08-01 --pages 108067022357425,107684028988499 \
            --out-dir <scratchpad>/lead-classify-2026-07
          → {"total":170,"by_page":{"108067022357425":164,"107684028988499":6},
             "duplicate_names":{"108067022357425":["Thảo Nguyễn","Thanh Thanh",...]},
             "rate_limit_warning":true}
          → Báo user: "170 hội thoại, chạm ngưỡng cảnh báo rate-limit. Chạy tiếp?"

[Phase 2] goto pancake.vn/bacsidacquang

[Phase 3] Lọc 10 tag (dò index mới) → Điều kiện = HOẶC → icon lịch →
          xác nhận "Thời gian tạo" aria-selected=true →
          .type("01/07/2026 00:00:00") + .type("31/07/2026 23:59:59") →
          đọc lại cả 2 ô OK → "Lọc"
          → 3 tên đầu: Thao Ho / Lê Thị Thu Liễu / Chi Linhh
          → khớp page-108067022357425-ordered.json pos 0,1,2 ✓

[Phase 4] Lô 1 = 20 tên đầu → 19 ok, 1 FB_ERROR (Chi Linhh, combobox timeout)
[Phase 5] send_notes.py cho 19 ca ok (bỏ Chi Linhh)
          ... lặp cho các lô tiếp theo ...

[Phase 6] "Trang bacsidacquang: 122/164 xong. Lỗi cần kiểm tra tay: Chi Linhh,
           Tâm Băng, Phương Nguyễn, Anh Nguyen, Thu Anh (chưa gửi note).
           Lưu ý: Lài Đinh / Nguyễn An / Linh Hoàng trước đó ở 'Sắp lại cột đã
           chuyển đổi', đã ghi đè thành 'Đủ tiêu chuẩn' — xác nhận giúp."
```

---

## 8. Tài liệu tham chiếu (đọc khi cần)

- `references/browser-playbook.md` — bộ selector đầy đủ, cơ chế virtual list, tối ưu token.
- `references/troubleshooting.md` — cây quyết định cho từng chế độ lỗi.
- `references/setup.md` — dựng MCP browser profile + `.env` từ đầu.
- `assets/browser-apply-filter.js` — script áp bộ lọc (copy-paste).
- `assets/browser-classify-batch.js` — script chạy lô phân loại (copy-paste, chỉ sửa `EXPECTED_NAMES`).

## 9. Nguyên tắc tối ưu token (user yêu cầu rõ)

- **Không** `browser_take_screenshot` / `browser_snapshot` sau mỗi click. Chỉ chụp khi **triage bug** thật.
- Gộp nhiều thao tác vào **một** lệnh `browser_run_code_unsafe` trả về JSON nhỏ (`{expected, status, stageBefore, action}`), thay vì mỗi micro-step một tool call.
- Xác minh bằng đọc hẹp (`innerText` 1 phần tử) thay vì snapshot toàn trang.
- Gửi note theo lô, không từng ca.
