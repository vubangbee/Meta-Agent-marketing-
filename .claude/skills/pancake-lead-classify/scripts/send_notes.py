"""Gửi note "Đã phân loại" (hoặc nội dung khác) vào hồ sơ khách Pancake theo LÔ, qua public API.

Vì sao không gõ vào UI: ô ghi chú trên web Pancake có bug thật - handleNoteSubmit ném
TypeError "Cannot read properties of undefined (reading '0')", Enter chỉ xuống dòng, phải
reload mới thoát. Endpoint API luôn trả 200 và không có bug này.

CHỈ gửi note cho những hội thoại ĐÃ xác minh/đặt được stage trên Facebook.
Bỏ qua mọi ca FB_ERROR / MISMATCH / NO_INFO_PANEL - gửi note cho ca chưa xử lý sẽ khiến
lần chạy sau tưởng đã xong và bỏ sót vĩnh viễn.

Dùng:
  python send_notes.py --items '[{"i":3,"page_id":"1080...","pcid":"764f3c24-..."}]'
  python send_notes.py --file done-batch-1.json --message "Đã phân loại"

Trường "i" chỉ là nhãn để đối chiếu trong log, không gửi đi đâu cả.
"""
import argparse
import json
import sys
from pathlib import Path


def _resolve_client_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "pancake-integration" / "scripts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--items", help='JSON inline: [{"i":0,"page_id":"...","pcid":"..."}]')
    src.add_argument("--file", help="Đường dẫn file JSON cùng định dạng với --items")
    ap.add_argument("--message", default="Đã phân loại", help="Nội dung note")
    ap.add_argument("--client-dir", default=None)
    args = ap.parse_args()

    client_dir = _resolve_client_dir(args.client_dir)
    if not (client_dir / "pancake_client.py").exists():
        print(json.dumps({"error": f"không tìm thấy pancake_client.py trong {client_dir}"}, ensure_ascii=False))
        return 1
    sys.path.insert(0, str(client_dir))
    import pancake_client as pc  # noqa: E402

    raw = Path(args.file).read_text(encoding="utf-8") if args.file else args.items
    items = json.loads(raw)

    results = []
    for it in items:
        label = it.get("i")
        try:
            # add_note(page_id, page_customer_id, message) - tự tra token theo page_id.
            # page_customer_id KHÁC c_id trong link pancake.vn/...?c_id=...
            pc.add_note(it["page_id"], it["pcid"], args.message)
            results.append({"i": label, "status": "ok"})
        except Exception as exc:  # noqa: BLE001 - báo lỗi từng ca, không dừng cả lô
            results.append({"i": label, "status": "error", "error": str(exc)[:200]})

    print(json.dumps(results, ensure_ascii=False))
    failed = [r for r in results if r["status"] != "ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
