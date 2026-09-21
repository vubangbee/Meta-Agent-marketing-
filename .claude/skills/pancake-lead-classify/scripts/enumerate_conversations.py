"""Liệt kê hội thoại Pancake khớp (BẤT KỲ thẻ tag nào trong bộ) + (khoảng thời gian TẠO)
cho một hoặc nhiều fanpage, xuất ra các file JSON dùng cho pha phân loại trên trình duyệt.

Vì sao tồn tại: bộ lọc trên UI Pancake trả kết quả không ổn định giữa các lần reload
(thực đo 119 -> 102 hội thoại cho cùng điều kiện). API là nguồn sự thật duy nhất; thứ tự
API trả về (mới -> cũ theo inserted_at) khớp đúng thứ tự UI hiển thị, nên nó đồng thời là
"bản đồ vị trí" để xác minh từng dòng trước khi click.

Tái sử dụng pancake_client.fetch_conversations_complete (tự xử lý trần 60 hội thoại/lần gọi
bằng cách chia đôi cửa sổ đệ quy) thay vì viết lại logic phân trang.

Output (trong --out-dir):
  target-conversations.json    bản đầy đủ, CHỨA PII - không bao giờ paste vào chat
  page-<page_id>-ordered.json  [{pos, name, pcid, c_id, inserted_at, tags_matched}]
  page-<page_id>-names.json    ["Tên 1", "Tên 2", ...] - paste vào script trình duyệt
  summary.json                 số lượng, tên trùng, cảnh báo rate-limit (an toàn để in ra)
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# 10 thẻ mặc định của tài khoản Bác sĩ Đắc Quang - đổi bằng --tags nếu dùng cho account khác
DEFAULT_TAGS = "QM,A,B,C,LIÊN LẠC KHÁC,Remarketing,Đã pt,Đã lên tv,Hẹn lịch,Tiềm năng"

# Ngưỡng cảnh báo rate-limit của Meta Business Suite: xem SKILL.md §6.
# Sự cố thật 2026-09-08: ~290-300 lượt mở MBS tích luỹ trong ngày -> khoá tài khoản.
RATE_LIMIT_WARN_THRESHOLD = 170


def _resolve_client_dir(explicit: str | None) -> Path:
    """Tìm thư mục scripts của skill pancake-integration (nơi có pancake_client.py)."""
    if explicit:
        return Path(explicit)
    # .../skills/pancake-lead-classify/scripts/this_file.py -> .../skills/
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "pancake-integration" / "scripts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", required=True, help="Ngày bắt đầu YYYY-MM-DD (tính theo giờ Asia/Bangkok)")
    ap.add_argument("--until", required=True, help="Ngày kết thúc YYYY-MM-DD, EXCLUSIVE (đầu ngày hôm sau)")
    ap.add_argument("--pages", required=True, help="Danh sách page_id, phân tách bằng dấu phẩy")
    ap.add_argument("--tags", default=DEFAULT_TAGS, help="Thẻ tag mục tiêu, phân tách bằng dấu phẩy (logic OR)")
    ap.add_argument("--out-dir", required=True, help="Thư mục ghi output (nên dùng scratchpad của phiên)")
    ap.add_argument("--client-dir", default=None, help="Ghi đè đường dẫn tới scripts của pancake-integration")
    args = ap.parse_args()

    client_dir = _resolve_client_dir(args.client_dir)
    if not (client_dir / "pancake_client.py").exists():
        print(json.dumps({"error": f"không tìm thấy pancake_client.py trong {client_dir}"}, ensure_ascii=False))
        return 1
    sys.path.insert(0, str(client_dir))
    import pancake_client as pc  # noqa: E402

    target_tags = {t.strip() for t in args.tags.split(",") if t.strip()}
    target_pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    since_ts = pc._to_unix(args.since)
    until_ts = pc._to_unix(args.until)

    known = pc._known_pages()  # {index: (page_id, token)}
    token_by_page = {page_id: token for page_id, token in known.values()}

    missing = [p for p in target_pages if p not in token_by_page]
    if missing:
        print(json.dumps({"error": f"chưa cấu hình page_access_token cho: {missing}"}, ensure_ascii=False))
        return 1

    rows = []
    for page_id in target_pages:
        convs = pc.fetch_conversations_complete(
            page_id,
            token_by_page[page_id],
            since_ts,
            until_ts,
            order_by="inserted_at",  # BẮT BUỘC: since/until mới lọc theo thời gian TẠO
            types=["INBOX"],         # loại COMMENT/POST - không phải hội thoại thật
        )
        for c in convs:
            tag_labels = {t.get("text") for t in (c.get("tags") or []) if t}
            matched = sorted(tag_labels & target_tags)
            if not matched:
                continue
            customers = c.get("customers") or []
            rows.append({
                "page_id": page_id,
                "page_name": pc.page_name(page_id),
                "c_id": c.get("id"),
                "link": pc._conversation_link(page_id, c.get("id")),
                "name": (customers[0].get("name") if customers else None)
                        or (c.get("from") or {}).get("name") or "",
                "inserted_at": c.get("inserted_at", ""),
                "tags_matched": matched,
                # page_customer_id: UUID phạm vi page, dùng cho add_note. KHÁC c_id.
                "page_customer_id": customers[0].get("id") if customers else None,
            })

    # Mới -> cũ, khớp đúng thứ tự danh sách trên UI Pancake
    rows.sort(key=lambda r: r["inserted_at"], reverse=True)
    (out_dir / "target-conversations.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "since": args.since,
        "until_exclusive": args.until,
        "tags": sorted(target_tags),
        "total": len(rows),
        "by_page": {},
        "duplicate_names": {},
        "missing_page_customer_id": sum(1 for r in rows if not r["page_customer_id"]),
        "output_dir": str(out_dir),
    }

    for page_id in target_pages:
        page_rows = [r for r in rows if r["page_id"] == page_id]
        ordered = [{
            "pos": i,
            "name": r["name"],
            "pcid": r["page_customer_id"],
            "c_id": r["c_id"],
            "inserted_at": r["inserted_at"],
            "tags_matched": r["tags_matched"],
        } for i, r in enumerate(page_rows)]

        (out_dir / f"page-{page_id}-ordered.json").write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"page-{page_id}-names.json").write_text(
            json.dumps([o["name"] for o in ordered], ensure_ascii=False, indent=2), encoding="utf-8")

        summary["by_page"][page_id] = len(ordered)
        dups = sorted(n for n, cnt in Counter(o["name"] for o in ordered).items() if cnt > 1)
        if dups:
            # Tên trùng => không được tra cứu vị trí theo tên. Duyệt tuần tự vẫn an toàn
            # vì thứ tự cố định, nhưng phải xác minh từng bước, đừng "nhảy" tới tên đó.
            summary["duplicate_names"][page_id] = dups

    summary["rate_limit_warning"] = len(rows) >= RATE_LIMIT_WARN_THRESHOLD
    if summary["rate_limit_warning"]:
        summary["rate_limit_note"] = (
            f"Tổng {len(rows)} hội thoại >= ngưỡng {RATE_LIMIT_WARN_THRESHOLD}. "
            "Hỏi user trước khi bắt đầu pha mở Facebook (xem SKILL.md §6)."
        )

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # summary không chứa PII -> an toàn để in
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
