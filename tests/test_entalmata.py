from __future__ import annotations

from datetime import date
import json
import sqlite3

import tender_radar.entalmata as entalmata
from tender_radar.entalmata import list_entalmata, safe_request_url, scan_entalmata


def write_config(path) -> None:
    path.write_text(
        """
api:
  search_url: "https://diavgeia.gov.gr/opendata/search.json"
  size: 40
  page: 0
  sort: "recent"
  status: "published"
visible_window_days: 15
organizations:
  - id: "50051"
    name: "Περιφέρεια Δυτικής Ελλάδας"
keywords:
  - "ΛΑΤΩ"
  - "ΓΕΩΡΓΑΚΟΠΟΥΛΟΙ"
""",
        encoding="utf-8",
    )


def test_scan_entalmata_keeps_keyword_matches_and_rejects_nonmatches(tmp_path) -> None:
    config_path = tmp_path / "diavgeia_entalmata.yml"
    write_config(config_path)
    db_path = tmp_path / "state.sqlite"
    download_dir = tmp_path / "downloads"

    def json_fetcher(url: str):
        assert "org=50051" in url
        return {
            "decisions": [
                {
                    "ada": "MATCH1",
                    "subject": "Πληρωμή λογαριασμού ΛΑΤΩ για δημόσιο έργο",
                    "protocolNumber": "12/2026",
                    "issueDate": "2026-07-19",
                    "documentUrl": "https://example.test/match.pdf",
                },
                {
                    "ada": "REJECT1",
                    "subject": "Άσχετη διοικητική απόφαση",
                    "protocolNumber": "13/2026",
                    "issueDate": "2026-07-19",
                    "documentUrl": "https://example.test/reject.pdf",
                },
                {
                    "ada": "OLD1",
                    "subject": "Πληρωμή ΛΑΤΩ εκτός παραθύρου",
                    "protocolNumber": "01/2026",
                    "issueDate": "2026-06-01",
                    "documentUrl": "https://example.test/old.pdf",
                },
            ]
        }

    report = scan_entalmata(
        db_path=db_path,
        config_path=config_path,
        download_dir=download_dir,
        today=date(2026, 7, 19),
        json_fetcher=json_fetcher,
        bytes_fetcher=lambda url: b"%PDF-1.4 fake",
    )

    assert report["ok"] is True
    assert report["summary"]["decisions_seen"] == 3
    assert report["summary"]["matched"] == 1
    assert report["summary"]["rejected"] == 1
    assert report["summary"]["outside_window"] == 1
    records = list_entalmata(db_path, today=date(2026, 7, 19), visible_window_days=15)
    assert [record.ada for record in records] == ["MATCH1"]
    assert records[0].matched_keywords == ["ΛΑΤΩ"]

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT ada, status, matched_keywords_json FROM diavgeia_entalmata ORDER BY ada"
        ).fetchall()
    assert rows == [
        ("MATCH1", "VISIBLE", json.dumps(["ΛΑΤΩ"], ensure_ascii=False)),
        ("REJECT1", "REJECTED", "[]"),
    ]


def test_scan_entalmata_archives_visible_rows_that_leave_window(tmp_path) -> None:
    config_path = tmp_path / "diavgeia_entalmata.yml"
    write_config(config_path)
    db_path = tmp_path / "state.sqlite"
    download_dir = tmp_path / "downloads"

    payload = {
        "decisions": [
            {
                "ada": "MATCH1",
                "subject": "Πληρωμή ΛΑΤΩ για δημόσιο έργο",
                "protocolNumber": "12/2026",
                "issueDate": "2026-07-19",
                "documentUrl": "https://example.test/match.pdf",
            }
        ]
    }

    scan_entalmata(
        db_path=db_path,
        config_path=config_path,
        download_dir=download_dir,
        today=date(2026, 7, 19),
        json_fetcher=lambda url: payload,
        bytes_fetcher=lambda url: b"%PDF-1.4 fake",
    )
    assert (download_dir / "12_2026.pdf").exists()

    report = scan_entalmata(
        db_path=db_path,
        config_path=config_path,
        download_dir=download_dir,
        today=date(2026, 8, 10),
        json_fetcher=lambda url: payload,
        bytes_fetcher=lambda url: b"%PDF-1.4 fake",
    )

    assert report["summary"]["archived"] == 1
    assert not list_entalmata(db_path, today=date(2026, 8, 10), visible_window_days=15)
    assert (download_dir / "old" / "12_2026.pdf").exists()

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status, archive_path FROM diavgeia_entalmata WHERE ada = 'MATCH1'"
        ).fetchone()
    assert row[0] == "ARCHIVED"
    assert row[1].endswith("old/12_2026.pdf")


def test_safe_request_url_percent_encodes_greek_paths() -> None:
    url = "https://diavgeia.gov.gr/doc/Ψ123Ω-ΑΒΓ?filename=Απόφαση.pdf"

    encoded = safe_request_url(url)

    assert encoded.startswith("https://diavgeia.gov.gr/doc/%CE%A8")
    assert "%CE%91%CF%80%CF%8C%CF%86%CE%B1%CF%83%CE%B7.pdf" in encoded


def test_scan_entalmata_matches_keyword_inside_pdf_text(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "diavgeia_entalmata.yml"
    write_config(config_path)
    db_path = tmp_path / "state.sqlite"
    download_dir = tmp_path / "downloads"
    monkeypatch.setattr(entalmata, "extract_pdf_text", lambda path: "Επωνυμία δικαιούχου ΛΑΤΩ ΑΤΕ")

    report = scan_entalmata(
        db_path=db_path,
        config_path=config_path,
        download_dir=download_dir,
        today=date(2026, 7, 19),
        json_fetcher=lambda url: {
            "decisions": [
                {
                    "ada": "PDFMATCH",
                    "subject": "ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ 1739-08/07/2026",
                    "protocolNumber": "1739",
                    "issueDate": "2026-07-08",
                    "documentUrl": "https://example.test/1739.pdf",
                }
            ]
        },
        bytes_fetcher=lambda url: b"%PDF-1.4 fake",
    )

    assert report["summary"]["matched"] == 1
    records = list_entalmata(db_path, today=date(2026, 7, 19), visible_window_days=15)
    assert [record.ada for record in records] == ["PDFMATCH"]
    assert records[0].matched_keywords == ["ΛΑΤΩ"]
