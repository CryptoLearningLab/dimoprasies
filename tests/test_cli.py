from contextlib import redirect_stdout
from io import StringIO
import unittest

from tender_radar.cli import _import_resource_payload, _parse_row_indexes, main


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

    def test_sources_help_lists_live_fetch_commands(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["sources", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("discover-active", output.getvalue())
        self.assertIn("fetch-resource", output.getvalue())
        self.assertIn("download-attachment", output.getvalue())

    def test_documents_help_lists_analyze(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                main(["documents", "--help"])
        self.assertEqual(0, exc.exception.code)
        self.assertIn("analyze", output.getvalue())

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
