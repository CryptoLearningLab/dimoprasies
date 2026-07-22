import sqlite3

from tender_radar.db import (
    create_admin_session,
    delete_admin_session,
    delete_stale_verified_tender_links,
    dismiss_tender,
    get_admin_session,
    get_source_document,
    get_source_state,
    ignored_tender_keys,
    import_attachment_download,
    import_eshidis_resource,
    list_source_documents,
    list_tender_dismissals,
    list_verified_tender_links,
    notification_already_sent,
    record_notification_sent,
    record_source_run,
    remove_tender_dismissal,
    triage_overrides_by_key,
    user_triage_overrides_by_key,
    upsert_source_document,
    upsert_source_state,
    upsert_triage_override,
    upsert_user_triage_override,
    upsert_verified_tender_link,
)
from tender_radar.sources.eshidis import EshidisAttachmentListing, EshidisTenderDetails


def test_tender_dismissal_can_be_removed(tmp_path) -> None:
    db_path = tmp_path / "runtime.sqlite"

    dismiss_tender(db_path, row_key="AUTHORITY:AUTH-1", title="Κρυμμένο έργο")
    assert ignored_tender_keys(db_path) == {"AUTHORITY:AUTH-1"}
    assert list_tender_dismissals(db_path)[0]["title"] == "Κρυμμένο έργο"

    remove_tender_dismissal(db_path, row_key="AUTHORITY:AUTH-1")

    assert ignored_tender_keys(db_path) == set()
    assert list_tender_dismissals(db_path) == []


def test_admin_sessions_are_persisted_and_deleted(tmp_path) -> None:
    db_path = tmp_path / "runtime.sqlite"

    create_admin_session(
        db_path,
        token_hash="session-hash",
        email="owner@example.test",
        role="admin",
        expires_at="2999-01-01T00:00:00+00:00",
    )

    session = get_admin_session(db_path, "session-hash")
    assert session is not None
    assert session.email == "owner@example.test"
    assert session.role == "admin"

    delete_admin_session(db_path, "session-hash")

    assert get_admin_session(db_path, "session-hash") is None


def test_triage_overrides_are_keyed_by_row(tmp_path) -> None:
    db_path = tmp_path / "runtime.sqlite"

    upsert_triage_override(db_path, row_key="AUTHORITY:AUTH-1", action="FORCE_KEEP", reason="είναι έργο")

    override = triage_overrides_by_key(db_path)["AUTHORITY:AUTH-1"]
    assert override["action"] == "FORCE_KEEP"
    assert override["reason"] == "είναι έργο"


def test_user_triage_overrides_are_keyed_by_user_and_row(tmp_path) -> None:
    db_path = tmp_path / "runtime.sqlite"

    upsert_user_triage_override(
        db_path,
        user_email="Owner@Example.Test",
        row_key="AUTHORITY:AUTH-1",
        action="CONFIRM_DROP",
        reason="σωστά κόπηκε",
    )
    upsert_user_triage_override(
        db_path,
        user_email="other@example.test",
        row_key="AUTHORITY:AUTH-1",
        action="FORCE_KEEP",
        reason="το θέλω",
    )

    owner = user_triage_overrides_by_key(db_path, user_email="owner@example.test")["AUTHORITY:AUTH-1"]
    other = user_triage_overrides_by_key(db_path, user_email="other@example.test")["AUTHORITY:AUTH-1"]
    assert owner["action"] == "CONFIRM_DROP"
    assert other["action"] == "FORCE_KEEP"
    assert owner["user_email"] == "owner@example.test"


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


def test_source_state_tracks_fingerprint_changes(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"

    first = upsert_source_state(
        db_path,
        source_id="nafpaktos_tenders",
        source_family="municipal_html",
        source_url="https://www.nafpaktos.gr/el/prokirixeis-diagonismoi",
        fingerprint="etag-1",
        checked_at="2026-07-18T10:00:00+00:00",
        status="OK",
        metadata={"http_status": 200},
    )
    second = upsert_source_state(
        db_path,
        source_id="nafpaktos_tenders",
        source_family="municipal_html",
        source_url="https://www.nafpaktos.gr/el/prokirixeis-diagonismoi",
        fingerprint="etag-1",
        checked_at="2026-07-18T11:00:00+00:00",
        status="UNCHANGED",
    )
    third = upsert_source_state(
        db_path,
        source_id="nafpaktos_tenders",
        source_family="municipal_html",
        source_url="https://www.nafpaktos.gr/el/prokirixeis-diagonismoi",
        fingerprint="etag-2",
        checked_at="2026-07-18T12:00:00+00:00",
        status="CHANGED",
    )

    assert first.last_changed_at == "2026-07-18T10:00:00+00:00"
    assert second.last_changed_at == "2026-07-18T10:00:00+00:00"
    assert third.last_changed_at == "2026-07-18T12:00:00+00:00"
    assert get_source_state(db_path, "nafpaktos_tenders").fingerprint == "etag-2"


def test_source_runs_are_audited(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"

    run_row_id = record_source_run(
        db_path,
        run_id="run-1",
        source_id="eshidis_active",
        started_at="2026-07-18T10:00:00+00:00",
        finished_at="2026-07-18T10:00:05+00:00",
        status="SKIPPED_UNCHANGED",
        fingerprint="abc",
        changed=False,
        item_count=0,
        metadata={"reason": "fingerprint match"},
    )

    assert run_row_id == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT source_id, status, changed, item_count, metadata_json FROM source_runs"
        ).fetchone()
    assert row[0:4] == ("eshidis_active", "SKIPPED_UNCHANGED", 0, 0)
    assert '"fingerprint match"' in row[4]


def test_tender_dismissals_are_persisted(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"

    dismiss_tender(
        db_path,
        row_key="KIMDIS:26PROC000000001",
        display_id="26PROC000000001",
        source_label="ΚΗΜΔΗΣ",
        title="Άσχετη προμήθεια",
        reason="Δεν με ενδιαφέρει",
        ignored_at="2026-07-18T10:00:00+00:00",
    )
    dismiss_tender(db_path, row_key="KIMDIS:26PROC000000001", title="Δεν αλλάζει το κλειδί")

    assert ignored_tender_keys(db_path) == {"KIMDIS:26PROC000000001"}
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM tender_dismissals").fetchone()[0]
    assert count == 1


def test_notification_log_prevents_duplicate_email_alerts(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"

    assert notification_already_sent(
        db_path,
        row_key="ESHIDIS:221744",
        channel="email",
        recipient="user@example.test",
    ) is False

    record_notification_sent(
        db_path,
        row_key="ESHIDIS:221744",
        channel="email",
        recipient="user@example.test",
        subject="Νέο έργο",
        sent_at="2026-07-18T10:00:00+00:00",
    )

    assert notification_already_sent(
        db_path,
        row_key="ESHIDIS:221744",
        channel="email",
        recipient="user@example.test",
    ) is True


def test_source_documents_track_fetch_provenance(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"

    upsert_source_document(
        db_path,
        row_key="AUTHORITY:AUTH-work",
        document_url="https://example.test/work.pdf",
        source_url="https://example.test/work",
        local_path="/tmp/work.pdf",
        size_bytes=123,
        sha256="abc123",
        fetched_at="2026-07-18T10:00:00+00:00",
        source_signature="sig-1",
        metadata={"linked_eshidis_ids": ["221473"]},
    )

    document = get_source_document(
        db_path,
        row_key="AUTHORITY:AUTH-work",
        document_url="https://example.test/work.pdf",
    )

    assert document is not None
    assert document.local_path == "/tmp/work.pdf"
    assert document.sha256 == "abc123"
    assert document.source_signature == "sig-1"
    assert document.metadata["linked_eshidis_ids"] == ["221473"]
    assert [item.document_url for item in list_source_documents(db_path, row_key="AUTHORITY:AUTH-work")] == [
        "https://example.test/work.pdf"
    ]


def test_verified_tender_links_are_persisted(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"

    upsert_verified_tender_link(
        db_path,
        source_row_key="KIMDIS:26PROC000000001",
        source_identifier="26PROC000000001",
        source_label="ΚΗΜΔΗΣ",
        source_url="https://example.test/kimdis",
        target_eshidis_id="221744",
        verification_status="VERIFIED_ESHIDIS_RESOURCE",
        verified_at="2026-07-19T10:00:00+00:00",
        source_signature="sig-1",
        evidence={"official_fetch_ok": True},
    )

    links = list_verified_tender_links(db_path, source_row_key="KIMDIS:26PROC000000001")

    assert len(links) == 1
    assert links[0].target_eshidis_id == "221744"
    assert links[0].source_label == "ΚΗΜΔΗΣ"
    assert links[0].source_signature == "sig-1"
    assert links[0].evidence["official_fetch_ok"] is True


def test_stale_verified_tender_links_are_deleted_for_source(tmp_path) -> None:
    db_path = tmp_path / "tenders.sqlite"
    for eshidis_id in ("221473", "221691"):
        upsert_verified_tender_link(
            db_path,
            source_row_key="KIMDIS:26PROC019417347",
            source_identifier="26PROC019417347",
            source_label="ΚΗΜΔΗΣ",
            target_eshidis_id=eshidis_id,
            verification_status="VERIFIED_ESHIDIS_RESOURCE",
            verified_at="2026-07-19T10:00:00+00:00",
            evidence={"official_fetch_ok": True},
        )

    deleted = delete_stale_verified_tender_links(
        db_path,
        source_row_key="KIMDIS:26PROC019417347",
        keep_target_eshidis_ids={"221691"},
    )
    links = list_verified_tender_links(db_path, source_row_key="KIMDIS:26PROC019417347")

    assert deleted == 1
    assert [link.target_eshidis_id for link in links] == ["221691"]
