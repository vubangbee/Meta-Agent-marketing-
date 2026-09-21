"""Liet ke hoi thoai Pancake trong khoang ngay TAO (inserted_at) cho mot hoac nhieu fanpage,
LOAI TRU nhung hoi thoai da mang san 1 trong cac the trong --exclude-tags (mac dinh RAC,Clone
- da xu ly roi, khong soi lai). Xuat JSON dung cho pha soi profile tren trinh duyet.

Vi sao tach rieng khoi enumerate_conversations.py (skill ak-pancake-lead-classify): quy trinh do
loc THEO the tag muc tieu (OR), quy trinh nay loc THEO khoang ngay va LOAI TRU theo the - nguoc
huong loc. Dung chung 1 script se phai nhoi 2 logic loc trai nguoc vao 1 flag, de gay nham.

Kem theo moi hang la CAC TIN HIEU RE (khong ton luot mo Facebook nao):
  message_count, snippet (tin nhan cuoi), has_phone, tags hien co.
Ly do: theo decision-criteria.md, bo loc RE NHAT la kiem the B/QM do sale gan truoc, roi moi
toi message_count/has_phone, CUOI CUNG moi mo profile Facebook. Script nay tinh san sale_tag_hit
(co B hoac QM) de agent ap dung bo loc theo dung thu tu, khong can doc lai tung the bang tay.

Output (trong --out-dir):
  target-conversations.json    ban day du, CHUA PII - khong bao gio paste vao chat
  page-<page_id>-ordered.json  [{pos, name, pcid, c_id, inserted_at, tags, message_count,
                                  snippet, has_phone, sale_tag_hit}]
  page-<page_id>-names.json    ["Ten 1", "Ten 2", ...] - dung de dinh vi dong tren UI
  summary.json                 so luong, ten trung, canh bao gioi han soi/ngay (an toan de in)
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# Windows console mac dinh dung cp1252, crash khi print() gap dau tieng Viet (vd ten khach
# hang, --help text). Ep UTF-8 de script chay on dinh tren moi may, khong rieng gi may nay.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

# 2 fanpage mac dinh cua tai khoan Bac si Dac Quang - doi bang --pages neu dung cho account khac
DEFAULT_PAGES = "108067022357425,107684028988499"

# Da xu ly roi (RAC = da phan loai rac; Clone = da danh dau nick ao) -> khong soi lai
DEFAULT_EXCLUDE_TAGS = "RÁC,Clone"

# Sale gan 1 trong 2 the nay = da co SDT qua chat + la tin nhan tiem nang (xem decision-criteria.md
# muc "LOC DAU TIEN"). Kiem chung 2026-09-10: 14 ca, chi 1 ca co B+QM, dung la ca has_phone=true
# duy nhat + message_count cao nhat (82, gap ~7 lan trung binh con lai).
SALE_HOT_TAGS = {"B", "QM"}

# Gioi han tu ap (user, 2026-09-10): "soi facebook lien tuc thi toi moi ngay khoang 100 link,
# khong qua nhieu de FB han che" - day la mo profile Facebook THUONG, KHAC voi nguong 170-200
# cua Meta Business Suite trong skill ak-pancake-lead-classify (do la mo tab MBS, co che khac).
DAILY_OPEN_WARN_THRESHOLD = 100


def _resolve_client_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "ak-pancake-integration" / "scripts"


def _default_since_until() -> tuple[str, str]:
    """Mac dinh 'hom qua + hom nay': [hom qua 00:00, ngay mai 00:00) theo gio Asia/Bangkok."""
    today = datetime.now().date()
    since = (today - timedelta(days=1)).isoformat()
    until = (today + timedelta(days=1)).isoformat()
    return since, until


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    default_since, default_until = _default_since_until()
    ap.add_argument("--since", default=default_since,
                     help=f"Ngay bat dau YYYY-MM-DD, gio Asia/Bangkok (mac dinh hom qua: {default_since})")
    ap.add_argument("--until", default=default_until,
                     help=f"Ngay ket thuc YYYY-MM-DD, EXCLUSIVE (mac dinh ngay mai: {default_until})")
    ap.add_argument("--pages", default=DEFAULT_PAGES, help="Danh sach page_id, phan tach bang dau phay")
    ap.add_argument("--exclude-tags", default=DEFAULT_EXCLUDE_TAGS,
                     help="The da xu ly, loai khoi worklist (phan tach bang dau phay)")
    ap.add_argument("--out-dir", required=True, help="Thu muc ghi output (nen dung scratchpad cua phien)")
    ap.add_argument("--client-dir", default=None, help="Ghi de duong dan toi scripts cua ak-pancake-integration")
    args = ap.parse_args()

    client_dir = _resolve_client_dir(args.client_dir)
    if not (client_dir / "pancake_client.py").exists():
        print(json.dumps({"error": f"không tìm thấy pancake_client.py trong {client_dir}"}, ensure_ascii=False))
        return 1
    sys.path.insert(0, str(client_dir))
    import pancake_client as pc  # noqa: E402

    exclude_tags = {t.strip() for t in args.exclude_tags.split(",") if t.strip()}
    target_pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    since_ts = pc._to_unix(args.since)
    until_ts = pc._to_unix(args.until)

    known = pc._known_pages()
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
            order_by="inserted_at",
            types=["INBOX"],
        )
        for c in convs:
            tag_labels = {t.get("text") for t in (c.get("tags") or []) if t}
            if tag_labels & exclude_tags:
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
                "tags": sorted(tag_labels),
                "sale_tag_hit": bool(tag_labels & SALE_HOT_TAGS),
                "message_count": c.get("message_count"),
                "snippet": c.get("snippet"),
                "has_phone": bool(c.get("has_phone")),
                "page_customer_id": customers[0].get("id") if customers else None,
            })

    rows.sort(key=lambda r: r["inserted_at"], reverse=True)
    (out_dir / "target-conversations.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "since": args.since,
        "until_exclusive": args.until,
        "exclude_tags": sorted(exclude_tags),
        "total": len(rows),
        "sale_tag_hit_count": sum(1 for r in rows if r["sale_tag_hit"]),
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
            "tags": r["tags"],
            "sale_tag_hit": r["sale_tag_hit"],
            "message_count": r["message_count"],
            "snippet": r["snippet"],
            "has_phone": r["has_phone"],
        } for i, r in enumerate(page_rows)]

        (out_dir / f"page-{page_id}-ordered.json").write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"page-{page_id}-names.json").write_text(
            json.dumps([o["name"] for o in ordered], ensure_ascii=False, indent=2), encoding="utf-8")

        summary["by_page"][page_id] = len(ordered)
        dups = sorted(n for n, cnt in Counter(o["name"] for o in ordered).items() if cnt > 1)
        if dups:
            summary["duplicate_names"][page_id] = dups

    summary["daily_open_warning"] = len(rows) >= DAILY_OPEN_WARN_THRESHOLD
    if summary["daily_open_warning"]:
        summary["daily_open_note"] = (
            f"Tổng {len(rows)} hội thoại còn phải soi >= ngưỡng tự áp {DAILY_OPEN_WARN_THRESHOLD}/ngày "
            "(mở nhiều link Facebook thường liên tục có thể bị hạn chế). Cân nhắc chia nhỏ theo ngày "
            "hoặc ưu tiên áp bộ lọc rẻ (sale_tag_hit, message_count) trước để giảm số phải mở."
        )

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
