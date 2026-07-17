from __future__ import annotations

import argparse
import json
from pathlib import Path

from tender_radar.sources.eshidis_browser import fetch_resource_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit direct ESHIDIS public works resource URLs.")
    parser.add_argument("eshidis_id")
    parser.add_argument("--out", default=None)
    parser.add_argument("--allow-insecure-tls", action="store_true")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out or f"work/source_audit/eshidis_resource_audit_{args.eshidis_id}.json")
    payload = fetch_resource_audit(
        args.eshidis_id,
        out_path,
        allow_insecure_tls=args.allow_insecure_tls,
        headful=args.headful,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
