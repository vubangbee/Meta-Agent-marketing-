# Troubleshooting — cây quyết định theo từng chế độ lỗi

## A. `FB_ERROR: locator.innerText Timeout ... Stage Selector`

Tab Facebook mở được nhưng đứng ở trang Hộp thư chung, không load được đúng luồng chat.

**Phân biệt 2 trường hợp — đây là bước quan trọng nhất:**

| Dấu hiệu | Nghĩa là | Hành động |
|---|---|---|
| Lẻ tẻ ~3% số ca, các ca xung quanh vẫn chạy tốt | Lỗi riêng của thread đó phía Meta | Thử lại **1 lần**. Vẫn lỗi → ghi nhận, **KHÔNG gửi note**, đưa vào báo cáo cho user kiểm tra tay. Đã reproduce 2 lần liên tiếp với chờ 5-10s → không phải vấn đề timing, đừng tăng timeout. |
| **Nhiều ca liên tiếp** cùng lỗi (≥5 ca) | Nghi rate-limit / khoá tài khoản | Sang mục **C** ngay, dừng batch |

## B. `FB_ERROR: waitForEvent 'page' Timeout`

Click "Xem trên Facebook" **không mở tab nào cả**.

Nguyên nhân thường gặp: panel ⓘ chưa mở (nút toggle bị click nhầm 2 lần) → `.open-in-messenger-button` không tồn tại/không visible.

0. **KIỂM TRA ĐỘ RỘNG CỬA SỔ TRƯỚC TIÊN** — dưới 1300px, Pancake thu gọn giao diện và **không render** icon ⓘ lẫn nút "Xem trên Facebook". Triệu chứng giống hệt lỗi selector nhưng code hoàn toàn đúng. Sửa: `browser_resize width:1400 height:900` hoặc `page.setViewportSize({width:1400,height:900})`, rồi chạy lại lô.
1. Kiểm tra `ensureInfoOpen()` có được gọi trước không.
2. Kiểm tra thủ công: click dòng → đọc `count()` + `isVisible()` của `.open-in-messenger-button`.
3. Nếu nút có mà vẫn không mở tab → có thể đã sang trạng thái lỗi Meta, sang mục **C**.

⚠️ Lỗi hay gặp khi debug: chỉ đọc tên `rows.nth(0)` mà **quên click** vào dòng → panel vẫn đang hiển thị hội thoại cũ, chẩn đoán sai hoàn toàn. Luôn click dòng trước khi kiểm tra panel.

## C. Nghi Facebook rate-limit / khoá tài khoản

**Test quyết định (rẻ, dứt khoát):** mở URL Hộp thư tổng **không kèm `c_id`**:

```
https://business.facebook.com/latest/inbox/all?asset_id=<page_id>
```

| Kết quả | Kết luận | Hành động |
|---|---|---|
| Hộp thư hiện bình thường | Không phải khoá tài khoản; lỗi ở từng thread | Quay lại mục **A** |
| Hiện *"Chúng tôi gặp sự cố khi hoàn thành yêu cầu của bạn"* | **Khoá cấp tài khoản** | Dừng ngay |

Khi đã khoá:
1. **Dừng batch.** Gửi note cho các ca đã xử lý xong, không gửi cho phần còn lại.
2. Báo user rõ: đây là chặn phía Meta, không phải lỗi thao tác; nêu tổng số lượt mở MBS đã dùng trong ngày.
3. Chờ 15-20 phút rồi kiểm tra lại **tối đa 1-2 lần**. Sự cố thật 2026-09-08: sau 20 phút vẫn khoá, user xác nhận không vào được Meta Business Suite bằng trình duyệt cá nhân.
4. **Không lặp vô hạn.** Đề nghị user mở Facebook bằng trình duyệt riêng để xem có checkpoint/yêu cầu xác minh không, rồi hẹn chạy lại sau (vài giờ đến 24h).

## D. `MISMATCH` — dòng trên cùng không đúng tên mong đợi

| Trường hợp | Cách xử lý |
|---|---|
| Tên tìm được nằm **sau** tên mong đợi trong danh sách | Đã vọt qua → cuộn ngược `-= 15`, tinh chỉnh `-= 8` |
| Tên không đổi suốt 40 lượt thử | Đã tới cuối danh sách → duyệt `rows.nth(1..k)` trực tiếp |
| Toàn bộ tên lạ hoàn toàn | Sai scope trang hoặc bộ lọc chưa áp → SKILL.md Phase 2 & 3 |
| Tên đúng nhưng **trùng lặp** trong danh sách | Bình thường nếu duyệt tuần tự (thứ tự cố định). **Không** dùng tra cứu theo tên để nhảy tới các tên này — `summary.json` có liệt kê `duplicate_names` |

**Không bao giờ đoán mò khi lệch.** Dừng lô, xác định lại vị trí, chạy tiếp.

## E. Kết quả lọc trên UI khác số lượng của API

Đây là **hành vi đã biết** của Pancake (đo được 119 → 102 cho cùng điều kiện sau reload). Danh sách API là chuẩn.

- Chênh lệch nhỏ + thứ tự vẫn khớp → cứ chạy, xác minh từng dòng bằng tên.
- Chênh lệch lớn → kiểm tra lại: đúng tab "Thời gian tạo" chưa? Điều kiện HOẶC chưa? đủ 10 thẻ chưa? đúng fanpage chưa?

## F. Đặt nhầm stage (ví dụ thành "Không đủ tiêu chuẩn")

1. **Báo user ngay**, đừng giấu.
2. Cuộn lại đúng hội thoại đó, mở lại Facebook, đặt lại bằng `{ exact: true }`.
3. **Đọc lại combobox xác nhận** đã đúng "Đủ tiêu chuẩn" mới gửi note.

## G. Stage ban đầu bất thường (không phải "Tiếp nhận")

Gặp thực tế: `Spam`, `Đã chuyển đổi`, `Sắp lại cột đã chuyển đổi`.

Quy trình mặc định là ghi đè hết thành "Đủ tiêu chuẩn". Vẫn ghi đè cho nhất quán, **nhưng phải liệt kê tên các ca này trong báo cáo cuối** để user xác nhận — hạ một khách "Đã chuyển đổi" (đã chốt) về "Đủ tiêu chuẩn" có thể ngoài ý muốn.

## H. Note gửi API bị lỗi

- `no page_access_token configured for page_id` → thiếu cấu hình `.env`, kiểm tra `page_access_token_N`.
- `pcid` sai → chắc chắn đang dùng `page_customer_id` (UUID) chứ không phải `c_id` (dạng `<page_id>_<số>`).
- Lỗi mạng/500 lẻ tẻ → chạy lại đúng lô đó; gửi trùng note chỉ tạo thêm 1 dòng ghi chú, không phá dữ liệu.
