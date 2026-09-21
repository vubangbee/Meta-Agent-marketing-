# Setup — dựng môi trường từ đầu

Chỉ đọc khi máy chưa từng chạy quy trình này.

## 1. Trình duyệt tự động có profile lưu cookie

Cần một MCP server Playwright dùng **profile riêng, cố định** để giữ đăng nhập Pancake + Facebook giữa các phiên.

MCP server Playwright (`meta-agent-browser`) đã khai báo sẵn trong `.mcp.json` ở root dự án (Claude Code project scope) — mở dự án bằng Claude Code và approve MCP khi được hỏi, không cần `claude mcp add` tay:

```json
// .mcp.json
{
  "mcpServers": {
    "meta-agent-browser": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--user-data-dir", "${CLAUDE_PROJECT_DIR:-.}/browser-profile", "--browser", "chrome"]
    }
  }
}
```

- `--user-data-dir` nằm trong thư mục dự án (`browser-profile/`), đã gitignore nên không lộ cookie/login. Đường dẫn dùng `${CLAUDE_PROJECT_DIR}` (tương đối) nên chép cả dự án sang máy khác chạy ngay, không cần sửa path.
- Sau khi thêm, nhờ user **đăng nhập tay một lần** vào `pancake.vn` và `business.facebook.com` trong cửa sổ trình duyệt đó. Cookie sẽ được giữ cho các phiên sau.
- Kiểm tra: mở `pancake.vn` → thấy danh sách hội thoại chứ không phải màn hình đăng nhập.

### 1b. Độ rộng cửa sổ tối thiểu 1300px (BẮT BUỘC)

Đầu mỗi phiên, trước mọi thao tác:

```
browser_resize  width: 1400  height: 900
```

Dưới **1300px**, Pancake chuyển sang bố cục thu gọn và **không render** icon ⓘ "Thông tin hội thoại" cùng nút "Xem trên Facebook" — hai phần tử cốt lõi của cả quy trình. Khi đó mọi selector đều fail dù code đúng, và lỗi trả về (`NO_INFO_PANEL`, `waitForEvent 'page'` timeout) trông y hệt các lỗi khác → rất dễ debug nhầm hướng hàng chục phút. Nếu MCP không có `browser_resize`, dùng trong script:

```js
await page.setViewportSize({ width: 1400, height: 900 });
```

## 2. Token API Pancake (cho enumerate + note)

Dùng lại skill `pancake-integration`:

```
.claude/skills/pancake-integration/scripts/.env
```

```
PANCAKE_PAGE_ID_1=108067022357425
page_access_token_1=<Public API access token của page đó>
PANCAKE_PAGE_ID_2=107684028988499
page_access_token_2=<...>
```

- Lấy token: trong Pancake, mỗi Fanpage có mục **"Public API access token"** riêng. **Không** dùng token đăng nhập tài khoản — loại đó không hoạt động với API này.
- Kiểm tra:
  ```bash
  cd .claude/skills/pancake-integration/scripts && python pancake_client.py test-connection
  # kỳ vọng: ok=True cho từng page
  ```

## 3. Xác nhận nhãn thẻ tag thật của tài khoản

Nhãn tag phải khớp **chính xác từng ký tự** (kể cả dấu tiếng Việt và viết hoa):

```bash
python -c "
import sys; sys.path.insert(0, '.claude/skills/pancake-integration/scripts')
import pancake_client as pc
pages = pc._known_pages()
for idx,(pid,tok) in pages.items():
    print(pid, [t.get('text') for t in pc.get_tags(pid)])
"
```

Bộ 10 thẻ đã xác nhận cho tài khoản Bác sĩ Đắc Quang:
`QM, A, B, C, LIÊN LẠC KHÁC, Remarketing, Đã pt, Đã lên tv, Hẹn lịch, Tiềm năng`

## 4. Fanpage đang chạy ads (mặc định của tài khoản này)

| Slug | page_id |
|---|---|
| `bacsidacquang` | `108067022357425` |
| `drDacQuang` | `107684028988499` |

## 5. Khi `pancake.vn/multi_pages` hiện trang trắng

URL hộp thư gộp cần state client-side mà `page.goto()` không tái tạo được.

- **Cách sửa đã xác nhận:** vào `pancake.vn/dashboard` → "Gộp trang" cho 2 fanpage trên.
- `browser_navigate_back` cũng khôi phục được nếu trang trắng xuất hiện sau một `goto()`.
- **Nhưng:** quy trình này **không dùng `/multi_pages`** — luôn xử lý từng fanpage riêng qua URL slug, vừa tránh lỗi này vừa loại bỏ nguy cơ trùng tên khách giữa 2 page.
