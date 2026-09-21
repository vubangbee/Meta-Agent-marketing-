# Meta Agent Marketing

Repo skill marketing: Pancake (chat/CRM), Ads (Google/Meta/TikTok), browser tự động (Playwright MCP).
Tác giả skill: `vubangdigital`.

## Skill có trong repo

| Skill | Dùng khi |
|---|---|
| `pancake-integration` | Đối soát hội thoại Pancake với quảng cáo Meta (`ad_id`), tag sale, SĐT, báo cáo funnel/lag/rechat |
| `pancake-lead-classify` | Phân loại "Giai đoạn khách hàng tiềm năng" trên Meta Business Suite + ghi note qua Pancake API |
| `pancake-profile-classify` | Soi profile Facebook cá nhân, gắn thẻ `Remarketing` / `Clone` |
| `pancake-crm` | Thao tác trực tiếp Pancake CRM (lead/deal/order/ticket/product) qua REST API |
| `ads-management` | Tạo/tối ưu quảng cáo Google/Meta/TikTok + sinh creative bằng AI |
| `agent-browser` | Browser automation không cần profile thật (screenshot, form, scraping, QA) |

## Yêu cầu

- [Claude Code](https://code.claude.com) (cấu hình MCP nằm ở `.mcp.json`)
- Node.js (cho `npx @playwright/mcp`), Python 3 (cho các script `*.py`)

## 1. Cấu hình `.mcp.json` (browser Playwright)

File `.mcp.json` ở root đã khai báo sẵn server `meta-agent-browser`:

```json
{
  "mcpServers": {
    "meta-agent-browser": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--user-data-dir", "${CLAUDE_PROJECT_DIR:-.}/browser-profile", "--browser", "chrome"]
    }
  }
}
```

- `--user-data-dir` là đường dẫn **tương đối** (`${CLAUDE_PROJECT_DIR}` = root dự án) nên chép cả dự án sang máy khác chạy ngay, không sửa path.
- `browser-profile/` đã gitignore — cookie/login chỉ nằm local, không lên git.
- Các bước chạy lần đầu:
  1. Mở dự án bằng Claude Code → approve MCP `meta-agent-browser` khi được hỏi.
  2. Đăng nhập tay **một lần** vào `pancake.vn` và `business.facebook.com` trong cửa sổ browser đó.
  3. Kiểm tra: mở `pancake.vn` → thấy danh sách hội thoại (không phải màn hình login).
  4. Đầu mỗi phiên browser: resize rộng ≥ 1300px (`browser_resize` 1400×900) — Pancake ẩn nút thao tác khi cửa sổ hẹp.

## 2. Cấu hình `.env` cho `ads-management`

```bash
cp .claude/skills/ads-management/scripts/.env.example .claude/skills/ads-management/scripts/.env
```

Mở `.env` và điền token thật (xem mẫu trong `.env.example`):

- **Google Ads**: `GOOGLE_ADS_DEVELOPER_TOKEN`, `CLIENT_ID`, `CLIENT_SECRET`, `REFRESH_TOKEN`, `CUSTOMER_ID`, `LOGIN_CUSTOMER_ID` (MCC).
- **Meta Ads**: `META_APP_ID`, `META_APP_SECRET`, `META_ACCESS_TOKEN` (system user token), `META_AD_ACCOUNT_ID` (dạng `act_123...`). Nhiều tài khoản thì đánh số `META_AD_ACCOUNT_ID_1`, `_2`,...
- **TikTok Ads**: `TIKTOK_APP_ID`, `TIKTOK_APP_SECRET`, `TIKTOK_ACCESS_TOKEN`, `TIKTOK_ADVERTISER_ID`.

Kiểm tra:

```bash
cd .claude/skills/ads-management/scripts
python meta-ads-manager.py billing        # số dư / trạng thái các tài khoản Meta
python meta-ads-manager.py report --preset last_30d --level campaign
```

Cần `pip install facebook-business` (Meta) / `google-ads` (Google) trước khi chạy.

## 3. Cấu hình `.env` cho `pancake-integration`

```bash
cp .claude/skills/pancake-integration/scripts/.env.example .claude/skills/pancake-integration/scripts/.env
```

### 3a. Token public API (theo từng Fanpage)

Trong Pancake, mỗi Fanpage có **"Public API access token"** riêng (không phải token đăng nhập tài khoản).
Thêm một cặp đánh số cho mỗi Page quản lý:

```
PANCAKE_PAGE_ID_1=108067022357425
page_access_token_1=<token của page đó>
PANCAKE_PAGE_ID_2=...
page_access_token_2=...
```

Kiểm tra:

```bash
cd .claude/skills/pancake-integration/scripts
python pancake_client.py test-connection   # kỳ vọng ok=True cho từng page
```

### 3b. Session token dashboard (cho auto-spam / toggle-spam)

`PANCAKE_INTERNAL_SESSION_TOKEN` là JWT login tài khoản Pancake (~3 tháng hết hạn), khác với token từng Page ở trên.
Cách lấy: mở dashboard Pancake trên browser → DevTools > Network → làm một thao tác `/api/v1/` → copy `access_token` trên URL request.

### 3c. Funnel stages (cho `funnel-report`)

Định nghĩa các stage chuyển đổi theo tag Pancake (xem mẫu trong `.env.example`):

```
FUNNEL_STAGE_1_NAME=Tong tin nhan moi
FUNNEL_STAGE_1_TAGS=ALL
FUNNEL_STAGE_2_NAME=Hen lich
FUNNEL_STAGE_2_TAGS=Hen lich
```

Từ khóa đặc biệt trong `TAGS`: `ALL` (mọi hội thoại), `HAS_PHONE` (đã có SĐT), `HAS_AD_ID` (có ad_id Meta).
Đếm **cộng dồn** theo từng tiêu chí trong stage (không khử trùng) — thiết kế TAGS lưu ý điểm này.

## Bảo mật

- Mọi file `.env` đã gitignore — **không bao giờ commit token, không paste token vào chat**.
- Output script chứa PII khách hàng (tên, SĐT: `*.csv`, `rechat*.csv`, `watch_tag_state.json`) — chỉ ghi ra file, không paste vào chat, và đã gitignore.
- `browser-profile/` chứa cookie đăng nhập — local only.
