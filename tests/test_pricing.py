from pathlib import Path

from tender_radar.pricing import (
    canonical_article_code,
    canonical_revision_code,
    consolidate_pricing_project_budget,
    ingest_pricing_budget_pdf,
    ingest_pricing_eshidis_project,
    parse_budget_rows_from_text,
    search_pricing_rows,
    upsert_pricing_budget_rows,
    upsert_pricing_document,
    upsert_pricing_project,
)


def test_article_code_canonicalizes_greek_and_latin_beta() -> None:
    assert canonical_article_code("Β-18.6") == "Β18.6"
    assert canonical_article_code("B18.6") == "Β18.6"
    assert canonical_article_code(" b - 18.6 ") == "Β18.6"


def test_revision_code_canonicalizes_odo_variants() -> None:
    assert canonical_revision_code("Ο∆Ο-2312") == "ΟΔΟ-2312"
    assert canonical_revision_code("ODO 2653") == "ΟΔΟ2653"


def test_parse_budget_rows_extracts_b18_6_fixture_row() -> None:
    text = """
       23     Β-18.6      Φράκτης απορρόφησης ενεργείας
                           μέχρι 2000 kJ ύψους 5 m
                           30%Ο∆Ο-2312+
                           40%Ο∆Ο-2653+
                           30%Ο∆Ο-2311
                           m        100.00       1.680.00      168.000.00
    """

    rows = parse_budget_rows_from_text(text)

    assert len(rows) == 1
    row = rows[0]
    assert row.row_number == 23
    assert row.article_code == "Β-18.6"
    assert row.canonical_article_code == "Β18.6"
    assert "Φράκτης απορρόφησης ενεργείας" in row.description
    assert "30%ΟΔΟ-2312" in row.revision_codes
    assert "40%ΟΔΟ-2653" in row.revision_codes
    assert "30%ΟΔΟ-2311" in row.revision_codes
    assert row.unit == "m"
    assert row.quantity == 100
    assert row.unit_price == 1680
    assert row.amount == 168000


def test_parse_budget_rows_uses_at_column_when_group_numbers_restart() -> None:
    text = """
      1 Γενικές Εκσκαφές σε έδαφος     ΝΑΟΔΟ Α02      ΝΟΔΟ 1123.Α    1            m3    6.500,00               3,55    23.075,00
        γαιώδες - ημιβραχώδες
      2 Αποξηλωση ασφαλτοταπήτων       ΝΑΟΔΟ Α02.1    ΝΟΔΟ 1123.Α    2            m3      200,00               8,25     1.650,00
        και στρώσεων οδοστρωσίας
        Σύνολο : 1. ΧΩΜΑΤΟΥΡΓΙΚΑ-TEXNIKA                                                                          302.126,25      302.126,25
        2. ΟΔΟΣΤΡΩΣΙΑ-ΑΣΦΑΛΤΙΚΑ
      1 Υπόβαση οδοστρωσίας             ΝΑΟΔΟ Γ01.1   ΝΟΔΟ 3121Β    30          m3      120,00        19,10         2.292,00
        μεταβλητού πάχους
      2 Βάση πάχους 0,10 m (Π.Τ.Π.      ΝΑΟΔΟ Γ02.2   ΝΟΔΟ 3211Β    31          m2     1.200,00            8,80    10.560,00
        Ο-155)
        3. ΣΗΜΑΝΣΗ-ΑΣΦΑΛΕΙΑ
      1 Μονόπλευρα χαλύβδινα            ΝΑΟΔΟ         ΝΟΔΟ 2653     36          m       400,00        70,00        28.000,00
        στηθαία ασφαλείας, ικανότητας   Ε01.2.3
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 30, 31, 36]
    assert [row.article_code for row in rows] == ["ΝΑΟΔΟ Α02", "ΝΑΟΔΟ Α02.1", "ΝΑΟΔΟ Γ01.1", "ΝΑΟΔΟ Γ02.2", "ΝΑΟΔΟ Ε01.2.3"]
    assert rows[2].quantity == 120
    assert rows[2].unit_price == 19.10
    assert rows[2].amount == 2292
    assert rows[4].amount == 28000


def test_ingest_and_search_pricing_rows_from_text_pdf_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    pdf_text_path = tmp_path / "budget.txt"
    pdf_text_path.write_text(
        """
        23 Β-18.6 Φράκτης απορρόφησης ενεργείας μέχρι 2000 kJ ύψους 5 m
           30%Ο∆Ο-2312+ 40%Ο∆Ο-2653+ 30%Ο∆Ο-2311 m 100.00 1.680.00 168.000.00
        """,
        encoding="utf-8",
    )

    payload = ingest_pricing_budget_pdf(db_path, eshidis_id="221314", pdf_path=pdf_text_path)
    search_payload = search_pricing_rows(db_path, "Β18.6")

    assert payload["rows_extracted"] == 1
    assert search_payload["summary"]["matches"] == 1
    assert search_payload["results"][0]["eshidis_id"] == "221314"
    assert search_payload["results"][0]["canonical_article_code"] == "Β18.6"


def test_reingesting_same_budget_document_replaces_previous_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    pdf_text_path = tmp_path / "budget.txt"
    pdf_text_path.write_text(
        """
        23 Β-18.6 Φράκτης απορρόφησης ενεργείας μέχρι 2000 kJ ύψους 5 m
           30%Ο∆Ο-2312+ 40%Ο∆Ο-2653+ 30%Ο∆Ο-2311 m 100.00 1.680.00 168.000.00
        """,
        encoding="utf-8",
    )

    first = ingest_pricing_budget_pdf(db_path, eshidis_id="221314", pdf_path=pdf_text_path)
    second = ingest_pricing_budget_pdf(db_path, eshidis_id="221314", pdf_path=pdf_text_path)
    search_payload = search_pricing_rows(db_path, "Β18.6")

    assert first["rows_upserted"] == 1
    assert second["rows_upserted"] == 1
    assert search_payload["summary"]["matches"] == 1


def test_consolidates_project_budget_rows_from_best_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    upsert_pricing_project(db_path, eshidis_id="221566")
    technical_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="01-ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ.pdf",
        document_type="technical_report",
    )
    budget_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="03-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="budget",
    )
    technical_rows = parse_budget_rows_from_text(
        """
        1 Ν1 (ΛΙΜ 2.01) Εκσκαφές πυθμένα m3 ΛΙΜ 1210 10,00 2,00 20,00
        2 ΛΙΜ 3.01 Ύφαλες επιχώσεις m3 ΛΙΜ 1312 5,00 12,00 60,00
        """
    )
    budget_rows = parse_budget_rows_from_text(
        """
        2 ΛΙΜ 3.01 Ύφαλες επιχώσεις από καθαρό προϋπολογισμό m3 ΛΙΜ 1312 5,00 12,00 60,00
        3 ΟΔΟ Γ-1.2 Υπόβαση οδοστρωσίας m2 ΟΔΟ 3111.Β 3,00 1,00 3,00
        """
    )

    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221566",
        document_id=technical_id,
        source_document="01-ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ.pdf",
        rows=technical_rows,
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221566",
        document_id=budget_id,
        source_document="03-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        rows=budget_rows,
    )

    summary = consolidate_pricing_project_budget(db_path, eshidis_id="221566")
    search_payload = search_pricing_rows(db_path, "ΛΙΜ 3.01")

    assert summary["rows_merged"] == 3
    assert summary["missing_row_numbers"] == []
    assert summary["amount_total"] == 83
    assert search_payload["summary"]["matches"] == 1
    assert search_payload["results"][0]["source_document"] == "__PROJECT_BUDGET_MERGED__"
    assert "καθαρό προϋπολογισμό" in search_payload["results"][0]["description"]


def test_ingest_eshidis_project_downloads_and_indexes_budget_rows(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    work_dir = tmp_path / "pricing"

    def fake_fetch_resource_audit(eshidis_id, out_path, *, allow_insecure_tls=False):
        assert eshidis_id == "221566"
        return {
            "target_url": "https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/221566",
                "snapshot": {
                    "bodyTextSample": (
                        "ΑΑ Συστήματος: 221566 "
                        "Αναθέτουσα Αρχή: ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ "
                        "Τοποθεσίες Έργου: Ναύπακτος "
                        "Τίτλος Έργου/Μελέτη: ΛΙΜΕΝΙΚΗ ΕΓΚΑΤΑΣΤΑΣΗ "
                        "Χρηματοδοτήσεις: "
                        "Συνολικός Προϋπολογισμός (με ΦΠΑ): 4.216.000,00 EUR "
                        "Ημερομηνία Δημοσίευσης: 01-07-2026 "
                        "Καταληκτική Ημ/νία Υποβολής Προσφορών : 21-07-2026 10:00:00 "
                        "Ποσό Κατακύρωσης:"
                    )
                },
                "response_bodies": [
                    {
                        "body_sample": (
                            '<partial-response><changes><update id="t1"><![CDATA['
                            '<table _rowCount="1">'
                            '<span id="t1:0:it2::content">2_-προυπολογισμός.pdf</span>'
                            "</table>"
                            "t1:0:cb1"
                            "]]></update></changes></partial-response>"
                        )
                }
            ],
        }

    def fake_download_attachment_audit(
        eshidis_id,
        row_index,
        out_path,
        download_dir,
        *,
        allow_insecure_tls=False,
        headful=False,
    ):
        download_dir.mkdir(parents=True, exist_ok=True)
        path = download_dir / "budget.txt"
        path.write_text(
            """
            23 Β-18.6 Φράκτης απορρόφησης ενεργείας μέχρι 2000 kJ ύψους 5 m
               30%Ο∆Ο-2312+ 40%Ο∆Ο-2653+ 30%Ο∆Ο-2311 m 100.00 1.680.00 168.000.00
            """,
            encoding="utf-8",
        )
        return {
            "eshidis_id": eshidis_id,
            "row_index": row_index,
            "download_error": None,
            "downloaded_file": {
                "name": "2_-προυπολογισμός.pdf",
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": "fixture",
            },
        }

    monkeypatch.setattr("tender_radar.pricing.fetch_resource_audit", fake_fetch_resource_audit)
    monkeypatch.setattr("tender_radar.pricing.download_attachment_audit", fake_download_attachment_audit)

    payload = ingest_pricing_eshidis_project(
        db_path,
        eshidis_id="221566",
        work_dir=work_dir,
        allow_insecure_tls=True,
    )
    search_payload = search_pricing_rows(db_path, "Β18.6")

    assert payload["ok"] is True
    assert payload["summary"]["attachments_found"] == 1
    assert payload["summary"]["downloaded"] == 1
    assert payload["summary"]["pricing_budget_rows_upserted"] == 1
    assert payload["project"]["authority_name"] == "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ"
    assert search_payload["summary"]["matches"] == 1
    assert search_payload["results"][0]["eshidis_id"] == "221566"


def test_ingest_eshidis_project_skips_existing_download_and_index(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    work_dir = tmp_path / "pricing"
    download_calls = {"count": 0}

    def fake_fetch_resource_audit(eshidis_id, out_path, *, allow_insecure_tls=False):
        return {
            "target_url": f"https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{eshidis_id}",
            "snapshot": {
                "bodyTextSample": (
                    f"ΑΑ Συστήματος: {eshidis_id} "
                    "Αναθέτουσα Αρχή: ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ "
                    "Τίτλος Έργου/Μελέτη: ΛΙΜΕΝΙΚΗ ΕΓΚΑΤΑΣΤΑΣΗ "
                    "Καταληκτική Ημ/νία Υποβολής Προσφορών : 21-07-2026 10:00:00 "
                    "Ποσό Κατακύρωσης:"
                )
            },
            "response_bodies": [
                {
                    "body_sample": (
                        '<partial-response><changes><update id="t1"><![CDATA['
                        '<table _rowCount="1">'
                        '<span id="t1:0:it2::content">2_-προυπολογισμός.pdf</span>'
                        "</table>"
                        "t1:0:cb1"
                        "]]></update></changes></partial-response>"
                    )
                }
            ],
        }

    def fake_download_attachment_audit(
        eshidis_id,
        row_index,
        out_path,
        download_dir,
        *,
        allow_insecure_tls=False,
        headful=False,
    ):
        download_calls["count"] += 1
        download_dir.mkdir(parents=True, exist_ok=True)
        path = download_dir / "budget.txt"
        path.write_text(
            """
            23 Β-18.6 Φράκτης απορρόφησης ενεργείας μέχρι 2000 kJ ύψους 5 m
               30%Ο∆Ο-2312+ 40%Ο∆Ο-2653+ 30%Ο∆Ο-2311 m 100.00 1.680.00 168.000.00
            """,
            encoding="utf-8",
        )
        return {
            "eshidis_id": eshidis_id,
            "row_index": row_index,
            "download_error": None,
            "downloaded_file": {
                "name": "2_-προυπολογισμός.pdf",
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": "fixture",
            },
        }

    monkeypatch.setattr("tender_radar.pricing.fetch_resource_audit", fake_fetch_resource_audit)
    monkeypatch.setattr("tender_radar.pricing.download_attachment_audit", fake_download_attachment_audit)

    first = ingest_pricing_eshidis_project(
        db_path,
        eshidis_id="221566",
        work_dir=work_dir,
        allow_insecure_tls=True,
    )
    second = ingest_pricing_eshidis_project(
        db_path,
        eshidis_id="221566",
        work_dir=work_dir,
        allow_insecure_tls=True,
    )

    assert first["summary"]["downloaded"] == 1
    assert second["summary"]["downloaded"] == 0
    assert second["summary"]["skipped_download"] == 1
    assert second["summary"]["skipped_indexed"] == 1
    assert second["summary"]["merged_budget_rows"] == 1
    assert download_calls["count"] == 1
