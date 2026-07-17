from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from tender_radar.db import import_eshidis_resource, list_latest_attachments, upsert_document_analysis
from tender_radar.sources.eshidis import EshidisAttachmentListing, EshidisTenderDetails
from tender_radar.status import ATHENS, parse_athens_deadline, verify_tender_status


class StatusVerificationTests(unittest.TestCase):
    def test_parse_athens_deadline_returns_aware_datetime(self) -> None:
        parsed = parse_athens_deadline("27-07-2026 10:00:00")

        self.assertIsNotNone(parsed)
        self.assertEqual(datetime(2026, 7, 27, 10, 0, tzinfo=ATHENS), parsed)

    def test_future_deadline_is_advisory_possibly_active_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "radar.sqlite"
            summary = _sample_tender(db_path, ("Διακήρυξη.pdf",))
            attachment = list_latest_attachments(db_path, summary.eshidis_id)[0]
            upsert_document_analysis(
                db_path,
                attachment.attachment_id,
                "tender_declaration",
                0.9,
                "TEXT_EXTRACTED",
                12,
                "Όροι διακήρυξης και αποσφράγιση προσφορών.",
                None,
                None,
            )

            result = verify_tender_status(
                db_path,
                "999001",
                now=datetime(2026, 7, 17, 12, 0, tzinfo=ATHENS),
            )

        self.assertEqual("POSSIBLY_ACTIVE", result.recommended_status)
        self.assertFalse(result.verified_active)
        self.assertEqual(1, result.documents_checked)
        self.assertEqual(1, result.latest_attachments_checked)
        self.assertTrue(any(signal.signal_type == "procedural_mention" for signal in result.signals))
        self.assertFalse(any(signal.decisive for signal in result.signals))

    def test_status_changing_filename_keeps_unknown_for_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "radar.sqlite"
            _sample_tender(db_path, ("Απόφαση Κατακύρωσης.pdf",))

            result = verify_tender_status(
                db_path,
                "999001",
                now=datetime(2026, 7, 17, 12, 0, tzinfo=ATHENS),
            )

        self.assertEqual("UNKNOWN", result.recommended_status)
        self.assertFalse(result.verified_active)
        self.assertEqual(0, result.documents_checked)
        self.assertEqual(1, result.latest_attachments_checked)
        self.assertTrue(any(signal.signal_type == "final_award" and signal.decisive for signal in result.signals))


def _sample_tender(db_path: Path, filenames: tuple[str, ...]):
    return import_eshidis_resource(
        db_path,
        EshidisTenderDetails(
            source_url="https://example.test/999001",
            eshidis_id="999001",
            title="Δοκιμαστικός διαγωνισμός",
            cpv="45200000-9",
            contracting_authority="Δοκιμαστική αρχή",
            location="EL000",
            project_title="Δοκιμαστικό έργο",
            budget_with_vat="1000",
            publication_date="01-07-2026 10:00:00",
            submission_deadline="27-07-2026 10:00:00",
        ),
        EshidisAttachmentListing(row_count=len(filenames), filenames=filenames),
        raw_path=Path("audit.json"),
    )
