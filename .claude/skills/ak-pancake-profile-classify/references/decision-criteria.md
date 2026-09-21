# Tiêu chí phân loại — trục đánh giá, tín hiệu, kho ví dụ đã chấm

Đọc file này trước khi chấm BẤT KỲ ca nào. Đây là bộ tiêu chí đã được chốt qua nhiều lượt
hiệu chỉnh trực tiếp với chủ tài khoản (Bác sĩ Đắc Quang) — không tự suy diễn khác đi.

## 1. Trục đánh giá THẬT SỰ

Câu hỏi cần trả lời **KHÔNG** phải "người thật hay nick ảo", mà là:

> **"Có phải khách hàng thẩm mỹ tiềm năng không?"**

Một profile hoàn toàn là người thật vẫn **KHÔNG** được gắn `Remarketing` nếu nhìn không có
khả năng/nhu cầu chi trả dịch vụ thẩm mỹ. Đây là lỗi đánh giá phổ biến nhất — đừng dừng lại
ở "người thật hay giả" rồi kết luận.

**Why:** tài khoản này chạy quảng cáo bám đuổi (remarketing) cho phòng khám thẩm mỹ. Gắn thẻ
cho người không có khả năng mua là đốt tiền quảng cáo vô ích. Ngược lại gắn nhầm khách thật
tiềm năng thành rác thì mất khách — và nếu lỡ tay gắn thẳng `RÁC`, một cron job tự động khác
sẽ đẩy hồ sơ đó vào Spam Facebook, **không hoàn tác được**.

## 2. Ba nhóm kết quả

| Kết quả | Điều kiện | Hành động |
|---|---|---|
| `Remarketing` | Người thật **VÀ** nhìn có khả năng/nhu cầu là khách thẩm mỹ | Gắn thẻ `Remarketing` |
| `Clone` | Nick ảo / tool-tạo / phone-farm — **cần bằng chứng ảnh chụp** trước khi chốt | Gắn thẻ `Clone` |
| (không thẻ) | Người thật nhưng không hợp tệp khách hàng, HOẶC chưa đủ căn cứ (vd profile khoá) | Để trống, đưa vào danh sách soi tay |

**⚠️ Ràng buộc bất di bất dịch: KHÔNG BAO GIỜ gắn `RÁC` trực tiếp từ luồng này**, kể cả khi
chắc chắn 100% là clone/spam. Lý do: tài khoản có sẵn 1 cron job khác tự động đẩy mọi hội thoại
gắn `RÁC` vào Spam Facebook — hành động đó không hoàn tác được. `Clone` là thẻ trung gian an
toàn, tách biệt hoàn toàn khỏi cơ chế auto-spam đó.

## 3. Tín hiệu nick ảo / clone

ít bạn bè · không có ảnh cá nhân · tên vô nghĩa · mới lập · toàn ảnh gái xinh · không có
tương tác · share bài vô nghĩa từ page khác quá nhiều (lướt 5 bài toàn thấy share về)

⚠️ **Đuôi số trong URL profile** (`.56`, `.363236`, hoặc dạng `profile.php?id=6157...`) **KHÔNG
TỰ NÓ là dấu hiệu nick ảo** — Facebook tự thêm hậu tố số khi trùng tên, và cấp `profile.php?id=`
là format bình thường cho tài khoản cũ/không đặt username tuỳ chỉnh. Chỉ có giá trị khi **kết
hợp** với các tín hiệu khác (ít bạn bè + không ảnh cá nhân + không hoạt động).

## 4. Tín hiệu người thật

Chữ trên profile phải thể hiện **quan điểm, hoạt động, sự kiện trong đời sống cá nhân** —
KHÔNG tính bài share bằng tool của người khác về tường (share hàng loạt từ page khác không
kèm quan điểm riêng). Cộng thêm: **cập nhật nhiều hình ảnh thật** (không phải ảnh mạng/ảnh đại
diện thay đổi 1 lần duy nhất).

**Là người thật KHÔNG đủ để kết luận `Remarketing`** — xem mục 1. Còn cần tín hiệu kinh tế/
thẩm mỹ dưới đây.

## 5. Tín hiệu "khách thẩm mỹ tiềm năng" (thứ phân biệt Remarketing khỏi không-thẻ)

Trong ảnh và bài viết, tìm **bối cảnh kinh tế và mức độ chăm chút ngoại hình**: nhà cửa, đồ
dùng, phong cách sống, trang điểm/làm tóc, quần áo, phụ kiện, ảnh dàn dựng có đầu tư.

- **Người bán hàng online nhỏ lẻ NHƯNG chăm ngoại hình** (tóc nhuộm, trang điểm, đồ đẹp, ảnh
  dàn dựng) → **vẫn Remarketing**. Buôn bán nhỏ tự nó **không phải** căn cứ loại. Tín hiệu
  quyết định là **còn trẻ + quan tâm ngoại hình**, không phải nghề nghiệp/mức thu nhập nhìn thấy.
- **Người thật, lớn tuổi hơn, ảnh thuần sinh hoạt gia đình/bếp núc, không có tín hiệu chăm sóc
  bản thân** → **không thẻ** (soi tay). Ảnh đời thường chân thực chỉ chứng minh *là người
  thật*, KHÔNG chứng minh *là khách tiềm năng*.

## 6. Nhóm profile KHOÁ (private, không xem được nội dung)

**Không xem được nội dung → luôn `không thẻ` (soi tay), KHÔNG BAO GIỜ gắn `Clone`** — bất kể
số bạn bè nhiều hay ít. Khoá trang là hành vi phổ biến của người dùng thật (nick ảo/tool hiếm
khi bận tâm khoá riêng tư); thiếu bằng chứng không đồng nghĩa là clone.

## 7. Quy tắc số điện thoại tìm thấy trên tường

Regex quét: `0[35789]` + 8 số nữa, cho phép `. -` hoặc khoảng trắng xen giữa các nhóm số
(xem `assets/scan-profile.js`).

Khi tìm thấy số:
1. **Search Google số đó.** Có kết quả khớp tên+SĐT ở kênh khác (shop, rao vặt, fanpage) →
   **củng cố** đây là profile thật. **0 kết quả KHÔNG phải dấu hiệu xấu** — SĐT cá nhân người
   Việt thường không để lại dấu vết Google; kỹ thuật này chỉ có giá trị *khẳng định*, không có
   giá trị *phủ định*. Chỉ thực sự hữu ích với người bán hàng/chủ shop đăng công khai.
2. **Luôn ghi chú vào Pancake** qua `add_note`, đúng định dạng: `Sdt trên tường: <sdt>` —
   không tự ý đổi câu chữ. Dùng `apply_verdict.py` (tham số `phone_on_wall`) để gộp bước này
   vào cùng lần gắn thẻ.

## 8. Đối chiếu Zalo — mạnh hơn Google cho số Việt Nam

Nếu trình duyệt đã đăng nhập sẵn Zalo Web (`chat.zalo.me`), tra số điện thoại tìm được ở đó.
Quy trình chi tiết (bắt buộc xem full avatar mới đánh giá, không dừng ở thumbnail 48px):
xem `references/browser-mechanics.md` mục 4.

🚫 **TUYỆT ĐỐI không bấm "Kết bạn" / "Nhắn tin" / "Gửi kết bạn"** — Zalo này là tài khoản thật
của chủ tài khoản, chỉ được dùng để TRA CỨU.

Thang đánh giá tín hiệu:
- **Có tài khoản Zalo** đang hoạt động → ủng hộ "người thật" (nick tool/phone farm hiếm khi
  công khai số cá nhân kèm bài bán hàng cá nhân trên nền tảng khác).
- **Tên Zalo trùng/gần tên Facebook** → tín hiệu MẠNH.
- **Avatar Zalo trùng ảnh Facebook** → tín hiệu MẠNH.
- ⚠️ **Tên/avatar KHÔNG khớp → tín hiệu YẾU, KHÔNG phải dấu hiệu xấu.** Người Việt rất hay dùng
  nickname + ảnh phong cảnh trên Zalo. Đừng hạ điểm một profile chỉ vì điều này.
- **Ảnh bìa/avatar Zalo lộ tín hiệu chăm ngoại hình** (trang điểm, làm tóc, đồ hiệu, giày cao
  gót...) dù Facebook trông "quê mùa" → đây là tín hiệu **mạnh cho Remarketing**, đã từng đảo
  ngược một đánh giá ban đầu sai (xem ca Lan Vĩ Hạc bên dưới). **Đừng chốt đánh giá khi chưa
  xem avatar Zalo full**, nếu có số điện thoại để tra.

## 9. Bộ lọc RẺ NHẤT — áp TRƯỚC KHI mở bất kỳ profile Facebook nào

Theo thứ tự chi phí tăng dần, dừng sớm nếu bước trước đã đủ căn cứ:

### 9a. Thẻ `B` hoặc `QM` do sale gắn sẵn
Sale trực page gắn `B` hoặc `QM` = khách **đã cho số điện thoại qua chat** và là **tin nhắn
tiềm năng** — đây là phán đoán của người thật đã đọc hội thoại.

→ **Có `B` hoặc `QM` ⇒ gắn `Remarketing` ngay, KHÔNG cần mở Facebook.** `find_worklist.py`
đã tính sẵn cờ `sale_tag_hit` cho từng dòng — lọc và xử lý nhóm này trước tiên.

Kiểm chứng thực tế (lô 09-10/09/2026, 14 ca): chỉ 1 ca có `B`+`QM`, và đúng là ca duy nhất
`has_phone=true`, `message_count=82` (gấp ~7 lần trung bình các ca còn lại). Ba tín hiệu độc
lập trùng khớp hoàn toàn — độ tin cậy cao.

### 9b. `message_count` + `snippet` + `has_phone` (có sẵn trong API, không tốn lượt mở)
- **message_count cao + has_phone=true** → khách thật, đang quan tâm dịch vụ → gần chắc chắn
  `Remarketing`. Đây nên là căn cứ CHÍNH, profile Facebook chỉ là bằng chứng phụ trợ.
- ⚠️ **message_count thấp KHÔNG phải dấu hiệu nick ảo** — chỉ là **lead nguội** (khách chạm
  nhẹ rồi im, thường sau câu hỏi kịch bản mở đầu của phòng khám mà không trả lời). Đừng gắn
  `Clone` chỉ vì ít tin nhắn.
- Thang tham chiếu thực đo: ~80 tin nhắn = rất nóng · ~10-15 = có tương tác thật · 5-9 = chạm
  nhẹ rồi im (đa số các ca thuộc dạng này, vẫn cần soi profile).

### 9c. Chỉ khi 9a và 9b chưa đủ căn cứ → mới mở profile Facebook (mục 10 trở xuống)

## 10. Cách thao tác đã chốt

- **Bắt buộc chụp ảnh mỗi profile mở ra** — tín hiệu chữ thuần không đủ để đánh giá (một ca
  thực tế trích được 0 bài viết qua text-scrape dù ảnh chụp cho thấy 9 ảnh + 1 bài chia sẻ rõ
  ràng). Tiêu chí quyết định (ảnh thật/ảnh gái xinh/bối cảnh sống) về bản chất là hình ảnh.
- Chụp ở **scale 0.5** (giảm ~4 lần token so với full-res), sau khi **cuộn tới vùng có mục Ảnh
  + bài đầu tiên** — không chụp ngay đầu trang (thường chỉ có cover/intro, thiếu tín hiệu).
- Vẫn lấy song song số bạn bè + trạng thái khoá + SĐT trên tường bằng
  `assets/scan-profile.js` (rẻ, không cần nhìn ảnh).

## 11. Kho ví dụ đã chấm (tham chiếu khi gặp ca tương tự)

### Xuân Thím — 54 bạn bè — KHÔNG gắn thẻ (soi tay)
Ảnh: mẹ bế con trên bộ ngựa gỗ, trẻ con sân quê, bánh khọt đổ khuôn gang, tô bún tự nấu — bối
cảnh nông thôn, đồ đạc giản dị, không tín hiệu chăm ngoại hình.
→ Người thật rõ ràng nhưng **không hợp tệp khách thẩm mỹ**. Đừng nhầm "ảnh đời thường chân
thực" với "là khách tiềm năng".

### Lan Vĩ Hạc — SĐT 0369637307 — **Remarketing**
Facebook: bài tự viết giọng cá nhân (chia sẻ chồng đi làm mua được nấm linh chi để bán lại),
ảnh biển dàn dựng (váy hoa, túi trắng, lắc vàng, đồng hồ) xen ảnh sản phẩm. Google SĐT: 0 kết
quả (bình thường). Zalo: có tài khoản, tên khác hẳn (nickname kiểu Việt Nam thường thấy) —
nhưng **avatar full lộ**: phụ nữ trẻ, tóc bob nhuộm nâu sáng, áo trễ vai, short jean, giày cao
gót, chụp ở công viên.
→ Đánh giá ban đầu chỉ dựa Facebook nghiêng "không thẻ" (nghĩ thu nhập thấp vì bán nấm rừng) —
**sai**. Avatar Zalo full mới lộ tín hiệu quyết định: còn trẻ + chăm ngoại hình. **Bán hàng nhỏ
lẻ không phải căn cứ loại** khi có tín hiệu ngoại hình đi kèm.

### Vo Kim — 512 bạn bè — profile KHOÁ — **không thẻ (soi tay)**
Facebook hiện "đã khóa bảo vệ trang cá nhân", "Không có bài viết", không ảnh, không SĐT truy
cập được. Click avatar không mở được ảnh full (chỉ hiện tooltip báo khoá).
→ Không xem được nội dung = không đủ căn cứ, dù bạn bè nhiều. **Khoá là hành vi người thật,
không được suy diễn thành `Clone`.**

## 12. Tóm tắt bảng quyết định (áp trước, chỉ hỏi người vận hành khi gặp tình huống mới hẳn)

| Tình huống | Kết luận |
|---|---|
| Sale đã gắn `B` hoặc `QM` | `Remarketing` — không cần mở Facebook |
| `message_count` cao + `has_phone=true` | `Remarketing` — profile chỉ để xác nhận thêm |
| Người thật + trẻ + tín hiệu chăm ngoại hình (kể cả bán hàng nhỏ lẻ) | `Remarketing` |
| Người thật, lớn tuổi/ảnh thuần sinh hoạt gia đình, không chăm ngoại hình | không thẻ (soi tay) |
| Profile khoá, không xem được nội dung | không thẻ (soi tay) — KHÔNG `Clone` |
| Nick ảo/tool/farm — đủ dấu hiệu mục 3, có ảnh chụp xác nhận | `Clone` |
| Bất kỳ trường hợp nào không khớp rõ các dòng trên | Hỏi người vận hành, rồi thêm ca mới vào mục 11 |

## 13. Hiệu chỉnh liên tục (bắt buộc với người vận hành mới/lần chạy đầu)

Đây là hệ tiêu chí được xây từ ví dụ thật, **chưa hoàn chỉnh 100%**. Khi gặp ca:
- Khớp rõ với mục 12 → tự quyết theo bảng, không cần hỏi.
- **Không khớp rõ, hoặc mâu thuẫn giữa các tín hiệu** (vd: nhiều bạn bè nhưng ảnh nghi dàn
  dựng; có B/QM nhưng profile trông rất giả) → hỏi người vận hành lấy quyết định, rồi **thêm
  một mục mới vào phần 11** đúng format các ca hiện có (mô tả tín hiệu quan sát được → quyết
  định của người vận hành → quy tắc rút ra), để lần sau tự quyết được.
- Càng nhiều ca đã chấm trong mục 11, càng nên tự tin tự quyết mà không hỏi lại những ca tương
  tự pattern đã có.
