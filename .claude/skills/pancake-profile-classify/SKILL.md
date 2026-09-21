---
name: pancake-profile-classify
description: Soi profile Facebook cá nhân của khách nhắn tin Pancake (hôm qua + hôm nay), đánh giá bằng mắt xem có phải khách hàng thẩm mỹ tiềm năng thật không, rồi gắn thẻ Remarketing (thật + phù hợp) hoặc Clone (nick ảo/spam, chắc chắn cao) trên Pancake. Dùng khi user yêu cầu "soi profile khách", "lọc nick ảo/clone", "kiểm tra khách hôm qua hôm nay xem thật hay giả", hoặc nhắc tới việc gắn thẻ Remarketing/Clone dựa trên đánh giá Facebook cá nhân.
metadata:
  author: vubangdigital
---

# Pancake → Facebook Profile Authenticity Classification

> **Mega-prompt tự chứa.** Đọc hết file này trước khi thao tác. Đây là quy trình soi-bằng-mắt
> (không phải rule cứng), nên **luôn đọc `references/decision-criteria.md` trước khi chấm bất
> kỳ ca nào** — đó là kho tiêu chí + ví dụ đã chốt qua hiệu chỉnh thật với chủ tài khoản, và là
> phần **quan trọng nhất** của skill này. Bỏ qua nó sẽ dẫn tới sai lệch trục đánh giá (xem §1).

---

## 1. Mục tiêu cốt lõi

Với mỗi hội thoại Pancake được **tạo trong khoảng ngày X→Y** (mặc định hôm qua + hôm nay) và
**chưa từng bị gắn `RÁC` hoặc `Clone`**:

1. Xác định danh tính khách qua **profile Facebook cá nhân thật** của họ (không phải qua tin
   nhắn Messenger — đó chỉ là kênh liên hệ).
2. Đánh giá bằng mắt (đọc chữ + xem ảnh): đây có phải **khách hàng thẩm mỹ tiềm năng thật** hay
   không, theo đúng trục ở `references/decision-criteria.md` mục 1.
3. Gắn thẻ tương ứng trên Pancake qua API:
   - Thật + phù hợp tệp khách → `Remarketing`
   - Chắc chắn cao là nick ảo/tool/phone-farm, có ảnh chụp xác nhận → `Clone`
   - Còn lại (thật nhưng không hợp tệp, hoặc chưa đủ căn cứ) → **không gắn thẻ gì**, đưa vào
     danh sách soi tay cho người vận hành.

**Ràng buộc bất di bất dịch:**

- **TRỤC ĐÁNH GIÁ LÀ "KHÁCH THẨM MỸ TIỀM NĂNG", KHÔNG PHẢI "THẬT HAY GIẢ".** Một profile hoàn
  toàn là người thật vẫn không được `Remarketing` nếu không hợp tệp khách hàng. Đây là lỗi hay
  gặp nhất khi mới làm quy trình này — xem `decision-criteria.md` mục 1 và ví dụ Xuân Thím.
- **KHÔNG BAO GIỜ gắn thẳng `RÁC`** từ luồng này, kể cả khi chắc chắn 100% là spam. Tài khoản
  có sẵn 1 cron job khác tự động đẩy mọi hội thoại gắn `RÁC` vào Spam Facebook — không hoàn tác
  được. `Clone` là thẻ trung gian an toàn, tách biệt hoàn toàn khỏi cơ chế đó.
- **`Clone` bắt buộc phải có ảnh chụp xác nhận** trước khi gắn — không suy diễn thuần từ text.
  Đặt ngưỡng cao: gắn nhầm `Clone` cho khách thật = mất khách vĩnh viễn (nặng hơn chạy chậm).
- **Facebook không có API** cho việc lấy link profile công khai từ 1 cuộc hội thoại Messenger
  — bước mở profile bắt buộc phải qua trình duyệt + extension "Pancake v2" (xem §2, §3).
- Sai sót thầm lặng (soi nhầm khách, gắn nhầm thẻ) nguy hiểm hơn chạy chậm. Luôn xác minh tên
  trước khi thao tác; khi không chắc, hỏi người vận hành thay vì đoán.

---

## 2. Kiến trúc đã chốt

**Kiến trúc lai — dùng đúng công cụ cho đúng việc:**

| Giai đoạn | Công cụ | Lý do |
|---|---|---|
| Liệt kê danh sách cần soi | **Pancake public API** (`scripts/find_worklist.py`) | Nguồn sự thật ổn định; đồng thời lấy sẵn tín hiệu rẻ (message_count/snippet/has_phone/tags) để lọc bớt trước khi mở Facebook |
| Mở đúng profile Facebook cá nhân | **Trình duyệt + extension "Pancake v2"** | Facebook/Pancake không có API trả link profile công khai từ 1 hội thoại; chỉ extension proprietary này biết cách resolve đúng link khi click avatar |
| Đánh giá thật/giả/phù hợp tệp | **Người vận hành hoặc AI đọc ảnh chụp + chữ** | Đây là phán đoán chủ quan có tiêu chí, không phải rule cứng — xem §1 và `decision-criteria.md` |
| Gắn thẻ + ghi note | **Pancake public API** (`scripts/apply_verdict.py`) | Idempotent với gắn thẻ, ổn định hơn thao tác tay trên UI |

**Đã thử và loại bỏ / không dùng:**

| Cách tiếp cận | Vì sao không dùng |
|---|---|
| Dùng trường `fb_id` (PSID) trong object hội thoại làm link profile | Không phải ID công khai — `facebook.com/<fb_id>` trả "Bạn hiện không xem được nội dung này" |
| Chỉ trích xuất text (`innerText`) để đánh giá, không chụp ảnh | Tiêu chí quyết định (ảnh thật/dàn dựng, bối cảnh kinh tế) về bản chất là hình ảnh — thực đo trích được 0 bài viết bằng text-scrape dù ảnh chụp cho thấy nội dung rõ ràng |
| Gắn `RÁC` trực tiếp cho ca nghi clone | Kích hoạt cron auto-spam không hoàn tác được — xem §1 |

---

## 3. Tiền điều kiện

| Thành phần | Kiểm tra | Nếu thiếu |
|---|---|---|
| MCP browser có profile lưu cookie, **đã cài extension "Pancake v2"** | Xem `references/browser-mechanics.md` mục 2 | Cài extension (liên hệ Pancake/người quản lý tài khoản), hoặc yêu cầu người vận hành cài tay |
| Cửa sổ trình duyệt rộng ≥ 1300px | `browser_resize` width ≥ 1300 đầu phiên | Bắt buộc — Pancake ẩn nút thao tác khi hẹp hơn (cùng ràng buộc như `pancake-lead-classify`) |
| Đã đăng nhập sẵn Pancake + Facebook trong profile trình duyệt đó | Mở `pancake.vn` không thấy màn login | Nhờ người vận hành đăng nhập tay 1 lần |
| (Tuỳ chọn, tăng độ chính xác) Đã đăng nhập sẵn Zalo Web | Mở `chat.zalo.me` không thấy màn login | Bỏ qua bước đối chiếu Zalo nếu không có — vẫn chạy được phần còn lại |
| Skill `pancake-integration` + `.env` có token | `python .claude/skills/pancake-integration/scripts/pancake_client.py test-connection` → `ok=True` | Cấu hình `page_access_token_N` |
| Thẻ `Clone` đã tồn tại trên Pancake | `get_tags(page_id)` thấy nhãn `Clone` | Tạo thẻ mới tên `Clone` trên Pancake trước khi chạy |
| Biết `page_id` các fanpage mục tiêu | Mặc định `bacsidacquang` (108067022357425) + `drDacQuang` (107684028988499) | Hỏi người vận hành nếu khác |

---

## 4. Quy trình thực thi chuẩn (6 phase)

### Phase 0 — Chốt tham số (nếu người vận hành chưa nói rõ)

- **Khoảng ngày**: mặc định hôm qua + hôm nay, theo **thời gian TẠO** (`inserted_at`).
- **Fanpage**: mặc định cả 2 (`bacsidacquang`, `drDacQuang`).
- **Thẻ loại trừ** (đã xử lý rồi, không soi lại): mặc định `RÁC,Clone`.

Không cần hỏi lại nếu người vận hành đã nói rõ trong yêu cầu ban đầu.

### Phase 1 — Liệt kê worklist + tín hiệu rẻ

```bash
python .claude/skills/pancake-profile-classify/scripts/find_worklist.py \
  --since 2026-09-09 --until 2026-09-11 \
  --pages 108067022357425,107684028988499 \
  --out-dir <scratchpad>/profile-classify-2026-09-10
```

(Không truyền `--since`/`--until` thì script tự tính "hôm qua + hôm nay".)

Output (xem docstring script để biết đầy đủ trường): `page-<id>-ordered.json` có sẵn
`message_count`, `snippet`, `has_phone`, `tags`, `sale_tag_hit` cho từng dòng — dùng ngay ở
Phase 2, không cần mở lại API.

**Báo tổng số cho người vận hành trước khi mở bất kỳ profile Facebook nào.** Nếu
`summary.json` báo `daily_open_warning: true` (≥ ~100 ca có thể phải mở), hỏi người vận hành có
muốn chia nhỏ theo ngày không (xem §6).

### Phase 2 — Áp bộ lọc rẻ trước (KHÔNG mở Facebook)

Theo đúng thứ tự chi phí ở `decision-criteria.md` mục 9:

1. Mọi dòng `sale_tag_hit: true` (có thẻ `B` hoặc `QM`) → verdict `Remarketing` ngay, **không**
   mở Facebook cho các dòng này.
2. Trong các dòng còn lại, dòng nào `has_phone: true` **và** `message_count` cao bất thường so
   với phần còn lại của lô (tự so sánh tương đối, không có ngưỡng tuyệt đối cứng) → verdict
   `Remarketing`, profile Facebook chỉ mở thêm nếu muốn có bằng chứng phụ.
3. Phần còn lại → sang Phase 3, mở Facebook để đánh giá.

Gom các verdict đã quyết ở bước 1-2 lại, gửi cùng đợt Phase 5 (không cần chờ xong Phase 3-4).

### Phase 3 — Chuẩn bị trình duyệt

1. `browser_resize` width ≥ 1300 (một lần đầu phiên).
2. Xác nhận extension "Pancake v2" đang bật — `references/browser-mechanics.md` mục 2.
3. Mở đúng fanpage đang xử lý trên Pancake (`pancake.vn/<slug>`), áp bộ lọc tag/ngày nếu cần
   định vị bằng UI — tái sử dụng cơ chế cuộn virtual-list đã có ở
   `pancake-lead-classify/references/browser-playbook.md` mục 1-2 (quét cửa sổ, xác minh tên
   trước khi click, không nhảy theo công thức px).

### Phase 4 — Duyệt & đánh giá từng ca (phần còn lại sau Phase 2)

Với mỗi hội thoại còn lại trong worklist:

1. Định vị đúng dòng trong danh sách Pancake, xác minh tên khớp trước khi click.
2. Click avatar khách (`.chat-menu-avatar-badge`) → bắt tab Facebook mới mở
   (`references/browser-mechanics.md` mục 3). Lỗi không mở được tab → xem
   `references/troubleshooting.md` mục A, bỏ qua ca đó nếu vẫn lỗi sau 1 lần thử lại.
3. Trên tab profile: chạy `assets/scan-profile.js` lấy tín hiệu chữ rẻ (bạn bè/khoá/SĐT trên
   tường) — `references/browser-mechanics.md` mục 4.
   - **Nếu `locked: true`** → verdict thẳng "không thẻ" (soi tay), **không** cần chụp ảnh, sang
     ca kế tiếp (`decision-criteria.md` mục 6).
4. Cuộn tới vùng Ảnh + bài đầu tiên, chụp 1 ảnh ở scale 0.5 (`references/browser-mechanics.md`
   mục 5). Đọc ảnh + chữ, đối chiếu `decision-criteria.md` mục 3-5, 11 (kho ví dụ).
5. Nếu bước 3 tìm thấy SĐT trên tường: Google-search số đó, và nếu có Zalo Web đã đăng nhập,
   đối chiếu theo `decision-criteria.md` mục 7-8 + `browser-mechanics.md` mục 6 (xem avatar
   full, không dừng ở thumbnail nhỏ). **Không bao giờ bấm Kết bạn/Nhắn tin.**
6. Ra verdict theo bảng quyết định `decision-criteria.md` mục 12:
   - Khớp rõ pattern đã có → tự quyết, ghi lại lý do ngắn gọn.
   - Không khớp rõ / mâu thuẫn tín hiệu → hỏi người vận hành, rồi bổ sung ca vào
     `decision-criteria.md` mục 11 theo format sẵn có (xem mục 13 file đó).
7. Đóng tab Facebook trước khi sang ca kế tiếp (tránh tích rác tab).

Gom verdict theo lô 10-20 ca trước khi sang Phase 5 (không gọi API từng ca một).

### Phase 5 — Áp verdict qua API (theo lô)

```bash
python .claude/skills/pancake-profile-classify/scripts/apply_verdict.py --items '[
  {"i":0,"page_id":"108067022357425","c_id":"108067022357425_123",
   "pcid":"764f3c24-...","verdict":"Remarketing"},
  {"i":1,"page_id":"108067022357425","c_id":"108067022357425_456",
   "pcid":"a1b2c3d4-...","verdict":"Clone"},
  {"i":2,"page_id":"108067022357425","c_id":"108067022357425_789",
   "pcid":"e5f6a7b8-...","verdict":"Remarketing","phone_on_wall":"0912345678"}
]'
```

- Chỉ gửi các ca đã có verdict `Remarketing` hoặc `Clone`. Ca "không thẻ" **không** cần gọi API
  gì cả — chỉ liệt kê trong báo cáo Phase 6.
- `verdict: "RÁC"` bị script từ chối có chủ đích — xem §1.
- Có SĐT trên tường → kèm `phone_on_wall`, script tự ghi note đúng định dạng
  `Sdt trên tường: <sdt>` cùng lúc gắn thẻ.

### Phase 6 — Báo cáo

Báo người vận hành (ngắn gọn):
- Tổng số ca đã soi / tổng worklist, chia theo: auto-Remarketing (lọc rẻ), Remarketing (soi
  tay), Clone, không thẻ (soi tay), lỗi kỹ thuật (chưa xử lý được).
- Danh sách ca lỗi kỹ thuật kèm lý do (không mở được tab, profile unavailable...).
- Danh sách ca đã hỏi người vận hành trong phiên này + verdict, xác nhận đã ghi vào
  `decision-criteria.md` mục 11.
- Bất kỳ sai sót tự gây ra và đã sửa — nêu thẳng.

---

## 5. Bảng bẫy chí mạng (tra nhanh)

| # | Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|---|
| 0 | Đề xuất `Remarketing` cho người thật rõ ràng nhưng bị bác | Nhầm trục đánh giá: "thật" ≠ "phù hợp tệp khách" | Đọc lại `decision-criteria.md` mục 1, 5, ví dụ Xuân Thím |
| 1 | Click avatar không mở tab nào | Extension "Pancake v2" tắt/lỗi | `browser-mechanics.md` mục 2 |
| 2 | Trích text được 0 nội dung dù profile có ảnh/bài | Facebook render bằng JS, text-scrape không đủ | Luôn chụp ảnh, đừng chỉ dựa `scan-profile.js` |
| 3 | Gắn `Clone` cho profile khoá | Nhầm "không xem được" với "chắc chắn giả" | `decision-criteria.md` mục 6 — khoá luôn là "không thẻ" |
| 4 | Đánh giá thấp một ca chỉ vì buôn bán nhỏ lẻ | Bỏ qua tín hiệu chăm ngoại hình | `decision-criteria.md` mục 5, ví dụ Lan Vĩ Hạc |
| 5 | Chốt sai vì chỉ nhìn thumbnail Zalo 48px | Chưa xem avatar full | `browser-mechanics.md` mục 6, làm đủ 3 bước |
| 6 | Lỡ bấm Kết bạn/Nhắn tin trên Zalo | Thao tác ngoài phạm vi tra cứu | KHÔNG BAO GIỜ làm việc này — xem §1, mục 8 |
| 7 | `apply_verdict.py` từ chối `verdict=RÁC` | Cố ý — chống gắn nhầm RÁC | Đổi verdict thành `Clone` |
| 8 | Google SĐT ra 0 kết quả, nghi profile giả | Hiểu sai giá trị của bước này | `decision-criteria.md` mục 7 — 0 kết quả là bình thường với số cá nhân |
| 9 | Ca không khớp rõ tiêu chí nào | Bộ tiêu chí đang hoàn thiện dần | Hỏi người vận hành, bổ sung ví dụ mới vào mục 11 |

---

## 6. Guardrail: giới hạn mở profile Facebook / ngày

Khác với `pancake-lead-classify` (mở tab Meta Business Suite, ngưỡng rate-limit ~170-200 do
Facebook khoá cấp tài khoản doanh nghiệp), quy trình này mở **profile Facebook thường** bằng
phiên trình duyệt cá nhân đã đăng nhập. Người vận hành tự đặt ngưỡng: **~100 lượt mở/ngày** để
tránh bị Facebook hạn chế phiên đăng nhập đó.

- `find_worklist.py` tự cảnh báo (`daily_open_warning`) khi worklist còn lại ≥ ngưỡng này.
- Áp bộ lọc rẻ ở Phase 2 **trước** để giảm số phải mở thật sự — nhiều lô thực tế chỉ cần mở
  Facebook cho một phần nhỏ worklist.
- Nghi bị hạn chế (nhiều ca liên tiếp lỗi B/C ở `troubleshooting.md`) → dừng ngay, không retry
  liên tục, báo người vận hành — xem `references/troubleshooting.md` mục F.

---

## 7. Ví dụ end-to-end (rút gọn)

```
User: "Soi profile khách hôm qua với hôm nay, 2 trang"

[Phase 0] Mặc định: hôm qua+hôm nay, 2 fanpage, loại trừ RÁC/Clone đã có. → không cần hỏi thêm.

[Phase 1] $ python scripts/find_worklist.py --out-dir <scratchpad>/profile-classify-2026-09-10
          → {"total":14,"sale_tag_hit_count":1,"by_page":{...},"daily_open_warning":false}
          → Báo user: "14 hội thoại cần soi, dưới ngưỡng 100/ngày."

[Phase 2] 1 ca có sale_tag_hit (B+QM, message_count=82, has_phone=true) → verdict Remarketing
          ngay, không mở Facebook. Còn 13 ca cần soi.

[Phase 3] browser_resize 1400x900 → xác nhận extension Pancake v2 enabled → mở
          pancake.vn/bacsidacquang.

[Phase 4] Từng ca trong 13 ca còn lại: click avatar → tab Facebook mới → scan-profile.js →
          (nếu khoá → "không thẻ", bỏ qua chụp ảnh) → chụp ảnh scale 0.5 → đọc, đối chiếu
          decision-criteria.md → verdict (tự quyết nếu khớp pattern, hỏi user nếu không).
          Kết quả ví dụ: 4 Remarketing, 0 Clone (chưa đủ bằng chứng ảnh ca nào), 6 không thẻ,
          3 lỗi kỹ thuật (không mở được tab).

[Phase 5] apply_verdict.py cho 5 ca Remarketing (1 từ Phase 2 + 4 từ Phase 4) — bỏ qua 6 ca
          không thẻ và 3 ca lỗi.

[Phase 6] "14 ca: 5 Remarketing (đã gắn thẻ), 0 Clone, 6 không thẻ (soi tay: <tên>...),
           3 lỗi kỹ thuật chưa xử lý được (<tên>... - không mở được tab Facebook, cần kiểm tra
           tay). Đã hỏi user 2 ca mới, đã ghi vào decision-criteria.md mục 11."
```

---

## 8. Tài liệu tham chiếu (đọc khi cần)

- `references/decision-criteria.md` — **đọc trước tiên**, tiêu chí đánh giá + kho ví dụ đã chấm.
- `references/browser-mechanics.md` — extension, click avatar, chụp ảnh, đối chiếu Zalo.
- `references/troubleshooting.md` — cây quyết định cho từng chế độ lỗi.
- `scripts/find_worklist.py` — liệt kê worklist + tín hiệu rẻ (copy-paste dòng lệnh, đổi ngày/page).
- `scripts/apply_verdict.py` — gắn thẻ + ghi note qua API theo lô.
- `assets/scan-profile.js` — quét tín hiệu chữ trên tab profile Facebook (copy-paste).
- `pancake-lead-classify/references/browser-playbook.md` mục 1-2 — cơ chế virtual-list/
  lazy-load của danh sách hội thoại Pancake (dùng chung, không viết lại).

## 9. Nguyên tắc tối ưu token

- Chụp ảnh **đúng 1 lần/profile**, ở scale 0.5, sau khi cuộn tới đúng vùng cần xem.
- Gộp thao tác quét chữ + cuộn vào cùng 1 lệnh chạy-JS khi công cụ cho phép.
- Gắn thẻ + ghi note theo lô 10-20 ca, không gọi API từng ca.
- Đọc `decision-criteria.md` một lần đầu phiên, giữ trong ngữ cảnh, không đọc lại mỗi ca.

## 10. Hiệu chỉnh liên tục — đây là một skill "học dần"

Bộ tiêu chí ở `decision-criteria.md` được xây từ ví dụ thật, không phải rule cứng đầy đủ ngay
từ đầu. Khi vận hành skill này ở một tài khoản/bối cảnh mới:

- Vài ca đầu tiên: **ưu tiên hỏi người vận hành** ngay cả khi có vẻ khớp pattern, để hiệu chỉnh
  đúng "gu" của tài khoản đó trước.
- Càng nhiều ca đã chấm và ghi vào mục 11, càng tự tin tự quyết với ca tương tự mà không hỏi.
- Luôn ghi lại ca mới theo đúng format đã có (tín hiệu quan sát được → quyết định → quy tắc rút
  ra) — đây là cách duy nhất để skill "thông minh hơn" qua thời gian mà không cần sửa lại
  SKILL.md.
