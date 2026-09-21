"""Ap ket qua soi profile vao Pancake theo LO, qua public API: gan the (Remarketing/Clone)
va, neu co, ghi note "Sdt tren tuong: <sdt>". Khong bao gio gan RAC truc tiep tu luong nay
(xem SKILL.md - RAC kich hoat cron auto-spam khong the hoan tac, Clone la buoc trung gian an toan).

Tra ID the bang pancake_client.find_tag_id(page_id, label) TAI THOI DIEM CHAY - khong hardcode
tag_id vi no co the khac nhau giua cac page.

Dung:
  python apply_verdict.py --items '[
    {"i":0,"page_id":"108067022357425","c_id":"108067022357425_123","pcid":"764f3c24-...",
     "verdict":"Remarketing"},
    {"i":1,"page_id":"108067022357425","c_id":"108067022357425_456","pcid":"a1b2c3d4-...",
     "verdict":"Clone"},
    {"i":2,"page_id":"108067022357425","c_id":"108067022357425_789","pcid":"e5f6a7b8-...",
     "verdict":"Remarketing","phone_on_wall":"0912345678"}
  ]'
  python apply_verdict.py --file batch-1.json

Truong "i" chi la nhan doi chieu trong log. "verdict" phai la dung nhan the tren Pancake
(vd "Remarketing" hoac "Clone"). "phone_on_wall" la tuy chon - khi co, ghi them note dung
dinh dang "Sdt tren tuong: <sdt>" (xem decision-criteria.md).
"""
import argparse
import json
import sys
from pathlib import Path

# Windows console mac dinh dung cp1252, crash khi print() gap dau tieng Viet (vd ten khach
# hang, --help text). Ep UTF-8 de script chay on dinh tren moi may, khong rieng gi may nay.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def _resolve_client_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "pancake-integration" / "scripts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--items", help="JSON inline, xem docstring cho định dạng")
    src.add_argument("--file", help="Đường dẫn file JSON cùng định dạng với --items")
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

    tag_id_cache: dict[tuple[str, str], int | None] = {}

    def tag_id_for(page_id: str, label: str) -> int | None:
        key = (page_id, label)
        if key not in tag_id_cache:
            tag_id_cache[key] = pc.find_tag_id(page_id, label)
        return tag_id_cache[key]

    results = []
    for it in items:
        label = it.get("i")
        page_id = it["page_id"]
        verdict = it["verdict"]
        if verdict == "RÁC":
            results.append({"i": label, "status": "refused",
                             "error": "verdict=RÁC bị từ chối - dùng verdict=Clone, không gắn RÁC trực tiếp"})
            continue
        try:
            tag_id = tag_id_for(page_id, verdict)
            if tag_id is None:
                results.append({"i": label, "status": "error",
                                 "error": f"không tìm thấy thẻ '{verdict}' trên page {page_id}"})
                continue
            pc.set_conversation_tag(page_id, it["c_id"], tag_id, action="add")
            note_status = None
            phone = it.get("phone_on_wall")
            if phone:
                pc.add_note(page_id, it["pcid"], f"Sdt trên tường: {phone}")
                note_status = "sent"
            results.append({"i": label, "status": "ok", "tag": verdict, "note": note_status})
        except Exception as exc:  # noqa: BLE001 - báo lỗi từng ca, không dừng cả lô
            results.append({"i": label, "status": "error", "error": str(exc)[:200]})

    print(json.dumps(results, ensure_ascii=False))
    failed = [r for r in results if r["status"] != "ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
