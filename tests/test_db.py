import sqlite3

from tender_radar.db import import_attachment_download, import_eshidis_resource
from tender_radar.sources.eshidis import EshidisAttachmentListing, EshidisTenderDetails


def test_import_eshidis_resource_persists_tender_and_attachments(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"
    details = EshidisTenderDetails(
        source_url="https://example.test/resources/search/221744",
        eshidis_id="221744",
        title="ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027",
        cpv="45233141-9",
        contracting_authority="ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΟΣ",
        location="EL631 - Αιτωλοακαρνανία",
        project_title="ΣΥΝΤΗΡΗΣΕΙΣ ΕΠΑΡΧΙΑΚΟΥ ΟΔΙΚΟΥ ΔΙΚΤΥΟΥ",
        budget_with_vat="2.500.000,00",
        publication_date="15-07-2026 00:44:36",
        submission_deadline="07-08-2026 10:00:00",
    )
    attachments = EshidisAttachmentListing(
        row_count=2,
        filenames=("ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ.pdf", "espd-request.xml"),
    )

    summary = import_eshidis_resource(db_path, details, attachments)

    assert summary.attachments_imported == 2
    with sqlite3.connect(db_path) as connection:
        tender = connection.execute(
            "SELECT eshidis_id, cpv_code, title, budget_with_vat, current_deadline_at FROM tenders"
        ).fetchone()
        assert tender == (
            "221744",
            "45233141-9",
            "ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027",
            2500000.0,
            "07-08-2026 10:00:00",
        )
        attachment_count = connection.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
        assert attachment_count == 2


def test_import_attachment_download_updates_latest_attachment(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"
    details = EshidisTenderDetails(
        source_url="https://example.test/resources/search/221744",
        eshidis_id="221744",
        title="Tender",
        cpv=None,
        contracting_authority=None,
        location=None,
        project_title=None,
        budget_with_vat=None,
        publication_date=None,
        submission_deadline=None,
    )
    attachments = EshidisAttachmentListing(row_count=1, filenames=("file.pdf",))
    import_eshidis_resource(db_path, details, attachments)

    summary = import_attachment_download(
        db_path,
        "221744",
        "file.pdf",
        "work/download_audit/file.pdf",
        123,
        "abc123",
    )

    assert summary.size_bytes == 123
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT local_path, size_bytes, sha256 FROM attachments WHERE original_name = 'file.pdf'"
        ).fetchone()
        assert row == ("work/download_audit/file.pdf", 123, "abc123")


def test_import_attachment_download_matches_normalized_whitespace(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"
    details = EshidisTenderDetails(
        source_url="https://example.test/resources/search/221744",
        eshidis_id="221744",
        title="Tender",
        cpv=None,
        contracting_authority=None,
        location=None,
        project_title=None,
        budget_with_vat=None,
        publication_date=None,
        submission_deadline=None,
    )
    attachments = EshidisAttachmentListing(row_count=1, filenames=("1. ΑΠΟΦΑΣΗ ΕΝΤΑΞΗΣ.pdf",))
    import_eshidis_resource(db_path, details, attachments)

    summary = import_attachment_download(
        db_path,
        "221744",
        "1. ΑΠΟΦΑΣΗ  ΕΝΤΑΞΗΣ.pdf",
        "work/download_audit/1. ΑΠΟΦΑΣΗ  ΕΝΤΑΞΗΣ.pdf",
        123,
        "abc123",
    )

    assert summary.size_bytes == 123
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT local_path, size_bytes, sha256 FROM attachments WHERE original_name = '1. ΑΠΟΦΑΣΗ ΕΝΤΑΞΗΣ.pdf'"
        ).fetchone()
        assert row == ("work/download_audit/1. ΑΠΟΦΑΣΗ  ΕΝΤΑΞΗΣ.pdf", 123, "abc123")


def test_reimport_eshidis_resource_preserves_download_metadata(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"
    details = EshidisTenderDetails(
        source_url="https://example.test/resources/search/221744",
        eshidis_id="221744",
        title="Tender",
        cpv=None,
        contracting_authority=None,
        location=None,
        project_title=None,
        budget_with_vat=None,
        publication_date=None,
        submission_deadline=None,
    )
    attachments = EshidisAttachmentListing(row_count=1, filenames=("file.pdf",))
    import_eshidis_resource(db_path, details, attachments)
    import_attachment_download(
        db_path,
        "221744",
        "file.pdf",
        "work/download_audit/file.pdf",
        123,
        "abc123",
    )

    import_eshidis_resource(db_path, details, attachments)

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT local_path, size_bytes, sha256, is_latest FROM attachments WHERE original_name = 'file.pdf'"
        ).fetchall()
        assert rows == [("work/download_audit/file.pdf", 123, "abc123", 1)]


def test_reimport_prefers_existing_download_metadata_when_duplicates_exist(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"
    details = EshidisTenderDetails(
        source_url="https://example.test/resources/search/221744",
        eshidis_id="221744",
        title="Tender",
        cpv=None,
        contracting_authority=None,
        location=None,
        project_title=None,
        budget_with_vat=None,
        publication_date=None,
        submission_deadline=None,
    )
    attachments = EshidisAttachmentListing(row_count=1, filenames=("file.pdf",))
    import_eshidis_resource(db_path, details, attachments)
    import_attachment_download(db_path, "221744", "file.pdf", "work/download_audit/file.pdf", 123, "abc123")
    with sqlite3.connect(db_path) as connection:
        tender_id = connection.execute("SELECT id FROM tenders WHERE eshidis_id = '221744'").fetchone()[0]
        connection.execute(
            """
            INSERT INTO attachments (tender_id, original_name, source_url, retrieved_at, is_latest)
            VALUES (?, 'file.pdf', 'https://example.test/resources/search/221744', 'now', 1)
            """,
            (tender_id,),
        )
        connection.commit()

    import_eshidis_resource(db_path, details, attachments)

    with sqlite3.connect(db_path) as connection:
        latest_rows = connection.execute(
            """
            SELECT local_path, size_bytes, sha256
            FROM attachments
            WHERE original_name = 'file.pdf' AND is_latest = 1
            """
        ).fetchall()
        assert latest_rows == [("work/download_audit/file.pdf", 123, "abc123")]
