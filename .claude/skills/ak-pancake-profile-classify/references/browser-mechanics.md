# Cơ chế trình duyệt — extension, click avatar, chụp ảnh, đối chiếu Zalo

Đọc file này khi cần chi tiết kỹ thuật ngoài phần tóm tắt trong SKILL.md. Viết theo API
Playwright chuẩn (đa số MCP browser đều bọc quanh Playwright) — đổi tên hàm cho khớp công cụ
trình duyệt cụ thể đang dùng nếu khác.

## 1. Vì sao KHÔNG dùng Pancake API để lấy link Facebook cá nhân

Object hội thoại Pancake có trường `fb_id` (PSID — Page-Scoped ID). Đây **KHÔNG PHẢI** ID
profile công khai — `facebook.com/<fb_id>` trả về "Bạn hiện không xem được nội dung này".
Không có API public nào của Pancake hay Facebook trả về link profile công khai từ 1 cuộc
hội thoại Messenger. Đừng đi tìm lại, đã kiểm chứng.

**Cách duy nhất:** click vào avatar khách trong danh sách hội thoại trên Pancake. Việc này
hoạt động được là nhờ **extension trình duyệt "Pancake v2"** (proprietary, do Pancake phát
triển) — nó chặn/diễn giải click đó và tự mở đúng profile Facebook công khai tương ứng trong
tab mới. Đây là năng lực của extension, KHÔNG phải của API.

## 2. Kiểm tra extension "Pancake v2" đã bật chưa

Làm 1 lần đầu phiên, trước khi thao tác:

```js
// Điều hướng tới chrome://extensions, đọc qua shadow DOM (Chrome extensions page dùng
// custom elements lồng nhiều lớp shadow root)
await page.goto('chrome://extensions');
const enabled = await page.evaluate(() => {
  const mgr = document.querySelector('extensions-manager');
  const list = mgr?.shadowRoot?.querySelector('extensions-item-list');
  const items = list?.shadowRoot?.querySelectorAll('extensions-item') || [];
  for (const item of items) {
    const name = item.shadowRoot?.querySelector('#name')?.textContent || '';
    if (/pancake/i.test(name)) {
      return { name, enabled: item.hasAttribute('enabled') };
    }
  }
  return null;
});
```

- Không tìm thấy extension → yêu cầu người vận hành cài đặt thủ công (extension riêng của
  Pancake, không có trên Chrome Web Store công khai — hỏi Pancake support hoặc người quản lý
  tài khoản).
- Tìm thấy nhưng `enabled: false` → bật lại qua UI (`extensions-item` có toggle riêng trong
  shadow DOM, hoặc đơn giản mở `chrome://extensions` bằng tay và bật).
- Nếu click avatar vẫn không mở tab dù extension báo `enabled: true` → tắt rồi bật lại
  extension 1 lần (một số phiên bản cần reload sau khi trang Pancake đã load sẵn).

**Đã kiểm chứng thực chiến:** extension v0.5.57, 1 lần bật là chạy ổn định liên tục qua hàng
chục ca không cần khởi động lại trong cùng phiên.

## 3. Click avatar → bắt tab Facebook mới mở

Avatar khách trong danh sách hội thoại Pancake nằm trong `<span class="chat-menu-avatar-badge">`
— đây là `<span>` với JS click handler, **không phải** `<a href>`, nên **không thể** bulk-extract
link bằng cách đọc DOM hàng loạt. Phải click từng dòng, bắt tab mới bằng sự kiện `page`:

```js
const [fbPage] = await Promise.all([
  page.context().waitForEvent('page', { timeout: 8000 }),
  page.locator('.chat-menu-avatar-badge').first().click(),
]);
await fbPage.waitForLoadState('domcontentloaded');
await fbPage.waitForTimeout(2000);
const profileUrl = fbPage.url();
```

⚠️ Trước khi click avatar, phải **đang mở đúng hội thoại của đúng khách** trong khung chat —
việc định vị đúng dòng trong danh sách (cuộn ảo, xác minh tên trước khi click) dùng đúng cơ
chế đã mô tả ở `ak-pancake-lead-classify/references/browser-playbook.md` mục 1-2 (virtual list,
lazy-load, quét cửa sổ thay vì nhảy theo công thức px) — tái sử dụng nguyên xi, không viết lại.

**Ca lỗi:** click không mở tab nào → thử lại 1 lần; vẫn lỗi → bỏ qua ca đó, đưa vào danh sách
báo cáo cho người vận hành soi tay (xem `references/troubleshooting.md`).

## 4. Quét tín hiệu chữ (rẻ, không cần nhìn ảnh)

Trên `fbPage` (tab profile vừa mở), dán `assets/scan-profile.js` vào công cụ chạy-JS-trong-trang.
Trả về `{url, friends, locked, noPosts, phones}` — dùng làm tín hiệu phụ, KHÔNG thay thế bước
chụp ảnh (mục 5) vì tiêu chí quyết định (ảnh thật/dàn dựng, bối cảnh kinh tế) về bản chất là
hình ảnh, không trích xuất được bằng text scrape.

## 5. Chụp ảnh xác nhận (bắt buộc mỗi profile)

1. Cuộn `fbPage` tới vùng có mục **Ảnh** + **bài viết đầu tiên** — đừng chụp ngay khi trang vừa
   load (đầu trang thường chỉ có cover/intro, thiếu tín hiệu quyết định).
   ```js
   await fbPage.evaluate(() => window.scrollBy(0, 900));
   await fbPage.waitForTimeout(800);
   ```
2. Chụp ở **scale 0.5** để giảm ~4 lần token so với ảnh full-res. Cách làm tuỳ công cụ trình
   duyệt: nếu có action `screenshot` nhận tham số `scale` (0.1-1) thì truyền `scale: 0.5`; nếu
   dùng Playwright `page.screenshot()` trực tiếp thì chụp full-res rồi resize ảnh 50% bằng công
   cụ xử lý ảnh sẵn có (Playwright bản thân không có tham số scale-down tích hợp).
3. Đọc ảnh để đánh giá theo tiêu chí `decision-criteria.md` mục 4, 5, 10 — người thật/dàn dựng,
   bối cảnh kinh tế, tín hiệu chăm ngoại hình.

**KHÔNG chụp ảnh sau mỗi thao tác nhỏ khác** (chỉ chụp đúng 1 lần/profile ở bước này) — xem
nguyên tắc tối ưu token ở SKILL.md.

## 6. Đối chiếu Zalo (khi có số điện thoại từ mục 4 hoặc từ Pancake)

Chỉ áp dụng nếu trình duyệt **đã đăng nhập sẵn** Zalo Web (`chat.zalo.me`) — không tự đăng
nhập hộ, không tạo tài khoản mới.

🚫 **TUYỆT ĐỐI không bấm "Kết bạn" / "Nhắn tin" / "Gửi kết bạn"** trong toàn bộ quy trình dưới
đây — tài khoản Zalo đó là của người vận hành thật, đây CHỈ LÀ tra cứu thụ động.

**3 bước để xem avatar full (thumbnail tìm kiếm chỉ 48px, gần như vô dụng để đánh giá):**

1. Front tab `chat.zalo.me` → gõ số điện thoại vào ô tìm kiếm → tìm dòng kết quả
   "Tìm bạn qua số điện thoại" → click để mở khung hội thoại 1:1.
2. Click **avatar trên header hội thoại** (`img.a-child`, phần tử thứ 2 khớp selector đó,
   thường ở toạ độ khoảng x≈425 y≈42 — toạ độ có thể lệch theo kích thước cửa sổ, xác minh bằng
   `read_page`/`find` trước khi click theo toạ độ) → mở thẻ **"Thông tin tài khoản"** (hiện
   Bio/Giới tính/Ngày sinh cùng avatar nhỏ).
3. Click **avatar 80×80 bên trong thẻ đó** (không có `div[role="dialog"]` bọc quanh trang này
   → selector theo dialog sẽ fail, phải định vị bằng toạ độ hoặc kích thước ảnh cụ thể, thường
   quanh x≈816 y≈358) → mở **ảnh full 720×720** — đủ nét để đánh giá tín hiệu ngoại hình.

Đóng bằng `Escape` — **đúng 1 lần cho mỗi lớp đang mở** (ảnh full → thẻ thông tin → khung chat).
Bấm `Escape` thừa 1 lần sẽ đóng luôn thẻ thông tin đang cần xem tiếp, phải mở lại từ bước 2.

Áp dụng thang tín hiệu ở `decision-criteria.md` mục 8 sau khi có avatar full — **đừng chốt
đánh giá dựa trên thumbnail nhỏ hoặc chỉ tên hiển thị.**

## 7. Nguyên tắc tối ưu token

- Chỉ chụp ảnh **1 lần/profile**, đúng lúc mô tả ở mục 5. Không chụp lại "cho chắc".
- Gộp bước quét chữ (`scan-profile.js`) và các thao tác cuộn/click vào cùng 1 lệnh chạy-JS khi
  công cụ cho phép, thay vì tách nhiều lời gọi nhỏ.
- Đọc kết quả quét bằng JSON nhỏ, không dump `innerText`/`outerHTML` toàn trang trừ khi đang
  triage lỗi thật.
- Giới hạn tự áp ~100 lượt mở profile Facebook thường/ngày (khác với ngưỡng rate-limit Meta
  Business Suite 170-200 của `ak-pancake-lead-classify` — đó là mở tab MBS, quy trình này mở
  tab Facebook thường, cơ chế hạn chế khác nhau) — xem SKILL.md §6.
