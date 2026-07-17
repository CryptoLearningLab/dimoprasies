from __future__ import annotations

import argparse
import json
from pathlib import Path

from tender_radar.sources.eshidis_browser import download_attachment_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit one ESHIDIS attachment download action.")
    parser.add_argument("eshidis_id")
    parser.add_argument("--row-index", type=int, default=0)
    parser.add_argument("--out", default=None)
    parser.add_argument("--download-dir", default="work/download_audit")
    parser.add_argument("--allow-insecure-tls", action="store_true")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out or f"work/source_audit/eshidis_download_audit_{args.eshidis_id}_{args.row_index}.json")
    payload = download_attachment_audit(
        args.eshidis_id,
        args.row_index,
        out_path,
        Path(args.download_dir),
        allow_insecure_tls=args.allow_insecure_tls,
        headful=args.headful,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("downloaded_file") else 1


if __name__ == "__main__":
    raise SystemExit(main())
