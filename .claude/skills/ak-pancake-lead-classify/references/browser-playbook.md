# Browser Playbook — selector, cơ chế, và tối ưu token

Đọc file này khi cần chi tiết kỹ thuật ngoài phần tóm tắt trong SKILL.md.

## 1. Bộ selector đã kiểm chứng

### Pancake (`pancake.vn/<page-slug>`)

| Selector | Là gì | Lưu ý |
|---|---|---|
| `.rc-virtual-list-holder` | Vùng cuộn của danh sách hội thoại | Thao tác `scrollTop` trên phần tử này |
| `.rc-virtual-list-holder-inner > *` | Các dòng đang render | **Chỉ ~10-11 dòng** bất kể tổng số. `nth(0)` = dòng trên cùng hiện tại, **không phải** chỉ số logic |
| `.conv-action-btn.color-primary` | Icon ⓘ "Thông tin hội thoại" | **TOGGLE** — click lần 2 sẽ đóng lại |
| `.open-in-messenger-button` | Icon mũi tên "Xem trên Facebook" | Chỉ tồn tại khi panel ⓘ đang mở |
| `button[name="Lọc theo"]` (role) | Nút mở bộ lọc | Bị ẩn khi ô "Tìm kiếm" đang focus → `.blur()` |
| `.filter-by-time` | Icon lịch ở thanh trái | Mở panel khoảng thời gian |
| `.ant-segmented` (đầu tiên) | Tab "Thời gian tạo" / "Thời gian cập nhật" | Đọc `outerHTML`, tìm `aria-selected="true"` |
| `textbox[name="Ngày bắt đầu" / "Ngày kết thúc"]` (role) | 2 ô ngày | Dùng `.type()`, **không** `.fill()` |
| `.ant-picker-cell.ant-picker-cell-in-view .ant-picker-cell-inner` | Ô ngày trong lịch | Click phải `{force:true}` |
| `input[type="checkbox"]` | Toàn bộ checkbox trong panel lọc | Dò index mỗi lần, **không hardcode** |
| `textbox[name="Nhập ghi chú (Enter để gửi)"]` (role) | Ô ghi chú | **KHÔNG DÙNG** — có bug, ghi note qua API |
| `textbox[name="Tìm kiếm"]` (role) | Ô tìm kiếm | **KHÔNG DÙNG** — xoá bộ lọc, race condition |

### Meta Business Suite (`business.facebook.com/latest/inbox/...`)

| Selector | Là gì |
|---|---|
| `role=combobox[name=/Stage Selector/i]` | Dropdown "Giai đoạn khách hàng tiềm năng" |
| `role=option[name='Đủ tiêu chuẩn', exact:true]` | Lựa chọn cần đặt — **exact bắt buộc** |
| Text `Đánh dấu là khách hàng tiềm năng` | Nút khởi tạo khi lead chưa từng được đánh dấu; click nó rồi mới có combobox |

Thứ tự stage của tài khoản này: `Tiếp nhận, Spam, Đủ tiêu chuẩn, Đã cho số điện thoại, Re, Sắp lại cột đa chuyển đổi, Đã chuyển đổi, Bị mất, Không đủ tiêu chuẩn`.
→ `Không đủ tiêu chuẩn` **đứng cuối**, nên `.last()` sẽ chọn đúng nó. Đây chính là cách đã gây đặt nhầm. Luôn `exact: true`.

## 2. Cơ chế virtual list (rc-virtual-list)

- Chỉ ~10-11 dòng có mặt trong DOM tại một thời điểm; cuộn xuống → dòng trên bị gỡ, dòng dưới được thêm. **Thứ tự tương đối luôn đúng**, nhưng chỉ số DOM thì trượt.
- Chiều cao trung bình ~94px, **nhưng không đồng đều** (dòng nhiều thẻ tag bị wrap cao hơn) → **mọi công thức nhảy theo px đều tích luỹ sai số**. Thực đo: nhảy theo công thức đã bỏ sót "Hoàng Kim" + "Thảo Nguyễn" và vọt thẳng tới dòng cách đó 2 vị trí.
- **Cách đúng duy nhất:** cuộn 12px/lần, đọc lại tên dòng đầu, lặp. Chậm hơn ~2 giây/hội thoại nhưng không bao giờ sai.
- **Lazy-load (đo 2026-09-09, rất quan trọng):** `scrollHeight` **chỉ bao vùng đã nạp** — đo được 6880px khi mới nạp ~79/164 dòng, và chỉ tăng khi cuộn tới gần đáy. Do đó **mọi cú nhảy xa đều bị kẹp** ở biên vùng đã nạp (thực đo: nhắm pos81, dừng ở pos51 vì `scrollTop` bị clamp). Muốn đi xa phải cuộn **nhiều nấc** (600px/nấc, chờ ~400ms) để app nạp dần.
- **Cuối danh sách:** khi số dòng còn lại ≤ kích thước cửa sổ, `scrollTop` chạm đáy và `nth(0)` **đứng yên vĩnh viễn**.
- **→ Kết luận: định vị bằng "quét cửa sổ" thay vì kéo dòng lên đầu.** Mỗi nấc cuộn, đọc `rows.allInnerTexts()` và tìm tên trong đó; thấy thì click thẳng `rows.nth(k)`. Cách này đi được khoảng cách xa tuỳ ý, tự nạp thêm dữ liệu, xử lý luôn phần đuôi, và cho phép gom các vị trí **không liền nhau** vào cùng một lô. Chạm đáy vẫn chưa thấy → `scrollTop = 0` rồi quét lại một lượt (phòng đã vọt qua).

## 3. Vì sao không dùng link trực tiếp `?c_id=` (đã đo kỹ)

| Cách | Quan sát thực tế |
|---|---|
| `page.goto('.../<slug>?c_id=X')` | URL bị strip `c_id` trong ~300ms. Lấy mẫu tại 300/800/1500/2500/4000ms → **luôn** là danh sách mặc định, chưa bao giờ đúng hội thoại. Network trace cho thấy app có gọi fetch (một lần với `customer_id=null`) rồi thua race với effect "tự chọn hội thoại đầu tiên". |
| `history.pushState()` + `dispatchEvent(new PopStateEvent('popstate'))` | Thành công **duy nhất 1 lần** — với hội thoại đã mở trước đó trong phiên (đã nằm trong store client-side). Thử lại với hội thoại chưa từng mở → thất bại y hệt `goto()`. |
| pushState qua URL trung gian rồi quay lại | Không ăn thua — DOM không thực sự unmount/remount. |

**Kết luận:** app chỉ fetch dữ liệu hội thoại khi có **click thật** vào dòng trong danh sách đã render. Không có hook store/API nào truy cập được từ ngoài để chọn hội thoại chưa cache. Đây là giới hạn kiến trúc của Pancake, không phải lỗi automation.

## 4. Bẫy scope trang (page context)

App giữ state "fanpage đang active" **độc lập với URL**. Có phiên vào đúng `/bacsidacquang` nhưng danh sách hiển thị dữ liệu mặc định không liên quan; phiên khác `goto()` sạch lại đúng ngay.

- **Cách phát hiện rẻ nhất:** sau khi áp bộ lọc, so 2-3 tên đầu với `page-<id>-ordered.json`.
- **Cách sửa:** click tên tài khoản góc trên bên phải → dropdown liệt kê các kênh đã kết nối (Zalo OA, TikTok, các fanpage) → chọn đúng, hoặc đơn giản `goto()` lại URL slug rồi kiểm tra lại.
- Panel thông tin bên phải có dòng `page_id: <id>` — dùng để xác nhận chắc chắn khi nghi ngờ.

## 5. Tối ưu token (yêu cầu rõ ràng của user)

- **Không** `browser_take_screenshot` / `browser_snapshot` sau mỗi click. Chỉ dùng khi triage bug thật (giao diện lạ, trạng thái kẹt).
- Gộp tối đa thao tác vào **một** `browser_run_code_unsafe`, trả về JSON nhỏ. Một lô 20-25 hội thoại = **1 tool call**, thay vì ~100 call lẻ.
- Xác minh bằng đọc hẹp: `innerText` của đúng 1 phần tử, hoặc `outerHTML.slice(0, 400)`.
- Thao tác **xuyên tab** (mở/đọc tab MBS) vẫn nằm trong cùng script được, nhờ `page.context().waitForEvent('page')` — không cần `browser_tabs` riêng cho từng hội thoại.
- Gửi note theo lô 15-25 ca, không gọi API từng ca.
- Đọc file danh sách bằng `Read` **một lần** đầu phiên, giữ trong context, thay vì đọc lại mỗi lô.
