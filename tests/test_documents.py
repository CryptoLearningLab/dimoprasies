import sqlite3

from tender_radar.db import import_attachment_download, import_eshidis_resource, list_downloaded_attachments
from tender_radar.documents import classify_document_name, extract_text_sample, render_markdown_report
from tender_radar.sources.eshidis import EshidisAttachmentListing, EshidisTenderDetails


def test_classify_document_name_recognizes_greek_filenames() -> None:
    assert classify_document_name("ΔΙΑΚΗΡΥΞΗ ΑΔΑ ΑΙ.pdf").document_type == "tender_declaration"
    assert classify_document_name("ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ signed.pdf").document_type == "technical_description"
    assert classify_document_name("ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ signed.pdf").document_type == "budget"
    assert classify_document_name("espd-request.xml").document_type == "espd"


def test_extract_xml_text_sample(tmp_path) -> None:
    xml_path = tmp_path / "espd.xml"
    xml_path.write_text("<root><name>Δοκιμαστικό ESPD</name></root>", encoding="utf-8")

    status, count, sample, error = extract_text_sample(xml_path)

    assert status == "TEXT_EXTRACTED"
    assert count is None
    assert sample == "Δοκιμαστικό ESPD"
    assert error is None


def test_list_downloaded_attachments(tmp_path) -> None:
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
    import_eshidis_resource(db_path, details, EshidisAttachmentListing(row_count=1, filenames=("file.pdf",)))
    import_attachment_download(db_path, "221744", "file.pdf", "work/download_audit/file.pdf", 123, "abc")

    attachments = list_downloaded_attachments(db_path, "221744")

    assert len(attachments) == 1
    assert attachments[0].original_name == "file.pdf"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_render_markdown_report_includes_types_and_files() -> None:
    markdown = render_markdown_report(
        {
            "eshidis_id": "221744",
            "documents_analyzed": 1,
            "documents": [
                {
                    "document_type": "budget",
                    "page_or_sheet_count": 4,
                    "extraction_status": "TEXT_EXTRACTED",
                    "original_name": "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
                    "text_sample": "sample",
                }
            ],
        }
    )

    assert "`budget`" in markdown
    assert "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf" in markdown
