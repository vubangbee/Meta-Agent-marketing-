# Troubleshooting — cây quyết định theo từng chế độ lỗi

## A. Click avatar không mở tab Facebook nào (`waitForEvent 'page'` timeout)

0. **Kiểm tra extension "Pancake v2" trước tiên** (`references/browser-mechanics.md` mục 2) —
   nguyên nhân phổ biến nhất. Nếu `enabled: false` → bật lại rồi thử lại đúng ca đó.
1. Kiểm tra đang **đúng hội thoại đang mở** trong khung chat (không phải khung mặc định/trống).
2. Extension đã bật mà vẫn lỗi → tắt/bật lại extension 1 lần, thử lại **1 lần**.
3. Vẫn lỗi → **không lặp vô hạn với cùng 1 ca**. Ghi nhận `NO_PROFILE_TAB`, bỏ qua, đưa vào
   danh sách báo cáo cho người vận hành soi tay bằng tay.

## B. Tab Facebook mở nhưng vào trang lỗi / yêu cầu đăng nhập lại

Cookie phiên Facebook trong profile trình duyệt có thể đã hết hạn hoặc bị Facebook yêu cầu
xác thực lại (checkpoint). Đây **không phải lỗi thao tác**.

- Đóng tab, thử lại **1 lần**.
- Vẫn lỗi → dừng cả lô đang chạy, báo người vận hành: có thể cần đăng nhập lại Facebook thủ
  công trong đúng profile trình duyệt đó.

## C. Profile hiện "Nội dung này hiện không có sẵn" / bị chặn xem

Khác với "đã khóa bảo vệ trang cá nhân" (locked, xem mục D) — đây thường là tài khoản đã bị
Facebook khoá/gỡ, hoặc chặn người xem cụ thể.

→ Ghi nhận `PROFILE_UNAVAILABLE`, **không thẻ** (đưa vào soi tay) — không đủ căn cứ để kết
luận `Clone`, vì tài khoản bị Facebook tự khoá không đồng nghĩa là nick ảo phục vụ mục đích
spam (có thể là tài khoản thật bị report oan, hoặc đang trong quá trình xác thực).

## D. Profile "đã khóa bảo vệ trang cá nhân"

Đây là kết quả hợp lệ, không phải lỗi. Theo `decision-criteria.md` mục 6: **luôn `không thẻ`
(soi tay), không bao giờ `Clone`** — khoá trang là hành vi phổ biến của người dùng thật.

## E. `assets/scan-profile.js` trả về tất cả field rỗng/null dù trang đã load

Kiểm tra đã đợi đủ `waitForLoadState('domcontentloaded')` + timeout vài giây trước khi chạy
script — Facebook render nội dung bằng JS, chạy quá sớm sẽ đọc phải DOM rỗng. Thử lại với
`waitForTimeout(2000-3000)` trước khi quét.

Nếu vẫn rỗng và trang rõ ràng có nội dung khi xem bằng mắt (qua ảnh chụp) → có thể Facebook đã
đổi cấu trúc DOM/class name; coi `scan-profile.js` là tín hiệu phụ không bắt buộc, vẫn tiếp tục
đánh giá bằng ảnh chụp.

## F. Nghi bị Facebook hạn chế do mở quá nhiều profile trong ngày

Khác với rate-limit của Meta Business Suite (`pancake-lead-classify` — mở tab MBS, dùng
xác thực doanh nghiệp), đây là việc mở **profile Facebook thường** bằng phiên trình duyệt cá
nhân/đã đăng nhập. Người vận hành đã tự đặt ngưỡng ~100 lượt/ngày để tránh việc này (xem
SKILL.md §6). Nếu bắt đầu thấy:
- Nhiều ca liên tiếp đều rơi vào mục B (yêu cầu đăng nhập lại) hoặc C (chặn xem) dù trước đó
  chạy êm, VÀ
- Đã mở gần/vượt ngưỡng ~100 lượt trong cùng ngày

→ Dừng batch, báo người vận hành. Đề nghị nghỉ vài giờ hoặc để hôm sau, KHÔNG cố mở tiếp bằng
cách retry liên tục — càng retry càng có khả năng làm nặng thêm hạn chế của Facebook đối với
phiên đăng nhập đó.

## G. Zalo: click avatar trong thẻ "Thông tin tài khoản" không mở được ảnh full

Trang không có `div[role="dialog"]` bọc quanh, nên selector theo dialog sẽ không khớp. Dùng
`find`/`read_page` để xác nhận toạ độ avatar 80×80 hiện tại (có thể lệch theo kích thước cửa
sổ) rồi click theo toạ độ — xem `references/browser-mechanics.md` mục 6 bước 3.

Lỗi hay gặp khi debug: bấm `Escape` 2 lần liên tiếp khi chỉ có 1 lớp đang mở → đóng luôn thẻ
"Thông tin tài khoản" đang cần xem, phải mở lại từ bước 2 (click avatar header).

## H. Gửi note/gắn thẻ qua `apply_verdict.py` bị lỗi

- `verdict=RÁC bị từ chối` → **đây là hành vi cố ý**, không phải bug. Đổi `verdict` thành
  `Clone` — xem `decision-criteria.md` mục 2 về lý do không bao giờ gắn `RÁC` trực tiếp.
- `không tìm thấy thẻ '<verdict>' trên page <id>` → nhãn thẻ trên Pancake không khớp chính xác
  (kể cả dấu tiếng Việt/viết hoa). Kiểm tra bằng `pancake_client.get_tags(page_id)`, đối chiếu
  lại đúng chuỗi nhãn.
- `no page_access_token configured for page_id` → thiếu cấu hình `.env` của skill
  `pancake-integration` — xem `pancake-lead-classify/references/setup.md` mục 2.
- `pcid` sai / lỗi ghi note → chắc chắn đang dùng `page_customer_id` (UUID), KHÔNG phải `c_id`
  (dạng `<page_id>_<số>`).
- Lỗi mạng/500 lẻ tẻ → chạy lại đúng lô đó; `set_conversation_tag` đã xác nhận idempotent (gắn
  lại thẻ đã có không tạo bản trùng), an toàn để retry. `add_note` KHÔNG idempotent — gửi trùng
  sẽ tạo 2 dòng note giống nhau (vô hại nhưng thừa), tránh gọi 2 lần cho cùng 1 ca nếu không
  chắc lần trước có thành công hay không.

## I. Ca không khớp rõ bất kỳ mục nào trong `decision-criteria.md`

Đây không phải lỗi kỹ thuật — dừng lại, KHÔNG tự đoán. Hỏi người vận hành lấy quyết định, rồi
bổ sung ca đó vào mục 11 của `decision-criteria.md` theo đúng format các ca hiện có, để những
lần chạy sau tự quyết được với ca tương tự (xem `decision-criteria.md` mục 13).
