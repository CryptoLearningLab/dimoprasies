from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
import unittest

from tender_radar.cli import _import_resource_payload, _parse_row_indexes, build_parser, main
from tender_radar.db import connect, initialize


class FakeAnalysis:
    document_type = "tender_declaration"
    classification_confidence = 0.9
    extraction_status = "TEXT_EXTRACTED"
    page_or_sheet_count = 1
    text_sample = "sample text"
    full_text = "sample text full"
    extraction_error = None
    ocr_status = None
    ocr_error = None

    def to_dict(self) -> dict[str, object]:
        return {
            "document_type": self.document_type,
            "classification_confidence": self.classification_confidence,
            "extraction_status": self.extraction_status,
            "page_or_sheet_count": self.page_or_sheet_count,
            "text_sample": self.text_sample,
            "full_text": self.full_text,
            "extraction_error": self.extraction_error,
            "ocr_status": self.ocr_status,
            "ocr_error": self.ocr_error,
        }


class FakeUnsupportedAnalysis(FakeAnalysis):
    document_type = "other"
    classification_confidence = 0.2
    extraction_status = "UNSUPPORTED_TYPE"
    page_or_sheet_count = None
    text_sample = None
    full_text = None
    extraction_error = "Unsupported document type: .zip"
    ocr_status = "NOT_APPLICABLE"
    ocr_error = None


class CliTests(unittest.TestCase):
    def test_help_exits_successfully(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("Public works tender monitoring tool", output.getvalue())

    def test_phase_zero_placeholders_are_disabled(self) -> None:
        self.assertEqual(2, main(["scan"]))

    def test_db_init_command(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "radar.sqlite"
            self.assertEqual(0, main(["db", "init", "--path", str(db_path)]))
            self.assertTrue(db_path.exists())

    def test_runtime_help_lists_scheduled_run(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["runtime", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("scheduled-run", output.getvalue())

    def test_scheduled_run_parser_supports_dry_run(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["runtime", "scheduled-run", "--dry-run", "--limit", "10"])

        self.assertEqual("runtime", args.command)
        self.assertEqual("scheduled-run", args.runtime_command)
        self.assertTrue(args.dry_run)
        self.assertEqual(10, args.limit)

    def test_entalmata_scan_parser_has_safe_defaults(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["entalmata", "scan"])

        self.assertEqual("entalmata", args.command)
        self.assertEqual("scan", args.entalmata_command)
        self.assertEqual("config/diavgeia_entalmata.yml", args.config)
        self.assertEqual("data/tender_radar.sqlite", args.db)
        self.assertEqual("work/download_audit/diavgeia_entalmata", args.download_dir)
        self.assertEqual("work/reports/diavgeia_entalmata_latest.json", args.report)
        self.assertIsNone(args.max_pages)

        args = parser.parse_args(["entalmata", "scan", "--max-pages", "100"])
        self.assertEqual(100, args.max_pages)

    def test_sources_help_lists_live_fetch_commands(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["sources", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("audit-whitelist", output.getvalue())
        self.assertIn("expanded-report", output.getvalue())
        self.assertIn("fetch-kimdis-open-proc", output.getvalue())
        self.assertIn("discover-active", output.getvalue())
        self.assertIn("fetch-resource", output.getvalue())
        self.assertIn("download-attachment", output.getvalue())

    def test_discovery_cli_defaults_are_week_safe_depths(self) -> None:
        parser = build_parser()

        discover = parser.parse_args(["sources", "discover-active"])
        expanded = parser.parse_args(["sources", "expanded-report"])

        self.assertEqual(100, discover.limit)
        self.assertEqual(20, expanded.kimdis_pages)

    def test_documents_help_lists_analyze(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["documents", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("analyze", output.getvalue())

    def test_documents_analyze_skips_existing_text_artifact(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "radar.sqlite"
            pdf_path = root / "doc.pdf"
            report_path = root / "report.json"
            text_dir = root / "text"
            pdf_path.write_bytes(b"%PDF test")
            attachment_id = self._insert_downloaded_attachment(db_path, pdf_path)

            with patch("tender_radar.cli.analyze_document", return_value=FakeAnalysis()) as analyze:
                self.assertEqual(
                    0,
                    main(
                        [
                            "documents",
                            "analyze",
                            "--eshidis-id",
                            "221744",
                            "--db",
                            str(db_path),
                            "--report",
                            str(report_path),
                            "--text-dir",
                            str(text_dir),
                        ]
                    ),
                )
                self.assertEqual(1, analyze.call_count)

            with patch("tender_radar.cli.analyze_document", return_value=FakeAnalysis()) as analyze:
                self.assertEqual(
                    0,
                    main(
                        [
                            "documents",
                            "analyze",
                            "--eshidis-id",
                            "221744",
                            "--db",
                            str(db_path),
                            "--report",
                            str(report_path),
                            "--text-dir",
                            str(text_dir),
                        ]
                    ),
                )
                self.assertEqual(0, analyze.call_count)

            payload = __import__("json").loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(0, payload["documents_analyzed"])
            self.assertEqual(1, payload["documents_skipped"])
            self.assertEqual(attachment_id, payload["skipped_documents"][0]["attachment_id"])

    def test_documents_analyze_force_reprocesses_existing_analysis(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "radar.sqlite"
            pdf_path = root / "doc.pdf"
            report_path = root / "report.json"
            text_dir = root / "text"
            pdf_path.write_bytes(b"%PDF test")
            self._insert_downloaded_attachment(db_path, pdf_path)

            with patch("tender_radar.cli.analyze_document", return_value=FakeAnalysis()):
                self.assertEqual(
                    0,
                    main(["documents", "analyze", "--db", str(db_path), "--report", str(report_path), "--text-dir", str(text_dir)]),
                )

            with patch("tender_radar.cli.analyze_document", return_value=FakeAnalysis()) as analyze:
                self.assertEqual(
                    0,
                    main(
                        [
                            "documents",
                            "analyze",
                            "--db",
                            str(db_path),
                            "--report",
                            str(report_path),
                            "--text-dir",
                            str(text_dir),
                            "--force",
                        ]
                    ),
                )
                self.assertEqual(1, analyze.call_count)

            payload = __import__("json").loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["documents_analyzed"])
            self.assertEqual(0, payload["documents_skipped"])

    def test_documents_analyze_skips_existing_unsupported_type(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "radar.sqlite"
            zip_path = root / "bundle.zip"
            report_path = root / "report.json"
            text_dir = root / "text"
            zip_path.write_bytes(b"zip")
            self._insert_downloaded_attachment(db_path, zip_path)

            with patch("tender_radar.cli.analyze_document", return_value=FakeUnsupportedAnalysis()):
                self.assertEqual(
                    0,
                    main(["documents", "analyze", "--db", str(db_path), "--report", str(report_path), "--text-dir", str(text_dir)]),
                )

            with patch("tender_radar.cli.analyze_document", return_value=FakeUnsupportedAnalysis()) as analyze:
                self.assertEqual(
                    0,
                    main(["documents", "analyze", "--db", str(db_path), "--report", str(report_path), "--text-dir", str(text_dir)]),
                )
                self.assertEqual(0, analyze.call_count)

            payload = __import__("json").loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(0, payload["documents_analyzed"])
            self.assertEqual(1, payload["documents_skipped"])

    def test_search_help_lists_run(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["search", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("run", output.getvalue())

    def test_status_help_lists_verify(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["status", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("verify", output.getvalue())

    def test_parse_row_indexes_deduplicates_and_preserves_order(self) -> None:
        self.assertEqual([0, 2, 1], _parse_row_indexes("0, 2, 0, 1"))

    def test_import_resource_allows_missing_attachment_table(self) -> None:
        import tempfile
        from pathlib import Path

        payload = {
            "target_url": "https://example.test/221380",
            "snapshot": {
                "bodyTextSample": (
                    "Συνοπτικός Τίτλος/Αρ. Διακήρυξης: Σήμανση "
                    "ΑΑ Συστήματος: 221380 "
                    "Κωδικός CPV: 45233221-4 "
                    "Πρόσθετη περιγραφή ειδών/Υπηρεσιών: Τεχνικά Έργα "
                    "Αναθέτουσα Αρχή: ΔΗΜΟΣ ΘΕΣΣΑΛΟΝΙΚΗΣ "
                    "Τοποθεσίες Έργου: EL522 - Θεσσαλονίκη "
                    "Τίτλος Έργου/Μελέτη: Σήμανση Δήμου "
                    "Χρηματοδοτήσεις: Τακτικός Προϋπολογισμός "
                    "Συνολικός Προϋπολογισμός (με ΦΠΑ): 2.000.000,00 "
                    "Ημερομηνία Δημοσίευσης: 03-07-2026 10:00:00 "
                    "Καταληκτική Ημ/νία Υποβολής Προσφορών : 25-07-2026 14:00:00 "
                    "Ποσό Κατακύρωσης:"
                )
            },
            "response_bodies": [{"body_sample": "<html>No attachment table response</html>"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "radar.sqlite"
            summary = _import_resource_payload(payload, Path("audit.json"), db_path)

        self.assertEqual("221380", summary.eshidis_id)
        self.assertEqual(0, summary.attachments_imported)

    def _insert_downloaded_attachment(self, db_path, pdf_path) -> int:
        initialize(db_path)
        connection = connect(db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO tenders (eshidis_id, title, created_at, updated_at)
                VALUES ('221744', 'Test tender', '2026-07-21T00:00:00+00:00', '2026-07-21T00:00:00+00:00')
                """
            )
            tender_id = int(cursor.lastrowid)
            cursor = connection.execute(
                """
                INSERT INTO attachments (
                    tender_id, original_name, local_path, source_url,
                    mime_type, size_bytes, sha256, retrieved_at, is_latest
                ) VALUES (?, 'doc.pdf', ?, 'https://example.test/doc.pdf',
                          'application/pdf', 9, 'abc123', '2026-07-21T00:00:00+00:00', 1)
                """,
                (tender_id, str(pdf_path)),
            )
            attachment_id = int(cursor.lastrowid)
            connection.commit()
            return attachment_id
        finally:
            connection.close()
