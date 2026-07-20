from pathlib import Path

from tender_radar.pricing import (
    _is_pricing_candidate_document,
    PricingBudgetRow,
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


def test_parse_budget_rows_handles_split_m3_and_starred_unit_prices() -> None:
    text = """
                                                                                  Κωδικός                     Τιμή                           Δαπάνη (Ευρώ)
                                                                                                Μονάδα
    α/α      Κωδικός άρθρου                    Είδος εργασίας                                               Μονάδας       Ποσότητα       Μερική
                                                                               Αναθεώρησης     Μέτρησης                                             Ολική Δαπάνη
      1            Α-12               Καθαίρεση οπλισμένων σκυροδεμάτων            ΟΙΚ-2227        m
                                                                                                   3
                                                                                                          27,45*        50,00        1.372,50
      2          Β-29.4.4            Μικροκατασκευές με σκυρόδεμα C20/25          ΟΔΟ-2551         m
                                                                                                   3
                                                                                                         143,00         15,00        2.145,00
      3            Β-51                Πρόχυτα κράσπεδα από σκυρόδεμα             ΟΔΟ-2921          m          9,60          20,00        192,00
      4           Β-85_α           ανακατασκευαζομένου πεζοδρομίου έως 0,50       ΟΔΟ-2548         τεμ.        40,30         70,00        2.821,00
      5           Β-85_β                                                          ΟΔΟ-2548         τεμ.        80,60         15,00        1.209,00
                              ανακατασκευαζομένου πεζοδρομίου > 0,50 m2
      6           Β-85_γ                                                          ΟΔΟ-2548         τεμ.       322,40         3,00         967,20
                              ανακατασκευαζομένου πεζοδρομίου > 0,50 m2
                                  Απόξεση ασφαλτικού οδοστρώματος
      7           Δ-2.1                          (φρεζάρισμα)                     ΟΔΟ-1132         m2          1,15        10.350,00     11.902,50
      8            Δ-4                  Ασφαλτική συγκολλητική επάλειψη           ΟΔΟ-4120         m2          0,45        10.350,00      4.657,50
                                Ασφαλτικές στρώσεις μεταβλητού πάχους
      9            Δ-6                                                            ΟΔΟ-4421Β        ton         79,30*       180,00       14.274,00
     10            Δ-8Α            Ασφαλτική στρώση κυκλοφορίας αστικής οδού      ΟΔΟ-4521Β        m2          9,54*       10.350,00     98.713,13
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == list(range(1, 11))
    assert rows[0].unit == "m3"
    assert rows[0].unit_price == 27.45
    assert rows[1].unit == "m3"
    assert rows[8].unit_price == 79.30
    assert rows[9].unit_price == 9.54
    assert sum(row.amount or 0 for row in rows) == 138253.83


def test_parse_budget_rows_handles_split_backslash_articles_and_special_units() -> None:
    text = """
                                                                                                       Τιμή            Δαπάνη (Ευρώ)
                                          Κωδικός        Κωδικός                 Μον.
    A/A            Είδος Εργασιών                                            Α.Τ.          Ποσότητα      Μονάδας        Μερική             Ολική
                                          Άρθρου       Αναθεώρησης               Mετρ.
      1 ΦΟΡΤΗΓΟ ΑΥΤΟΚΙΝΗΤΟ             ΝΑΟΔΟ          ΝΟΔΟ 1133Β     1           ΗΜ/Σ       10,00      450,00         4.500,00
                                       Α\\ΝΑ01.1                                  ΘΙΟ
      8 ΕΠΟΥΛΩΣΗ ΛΑΚΚΩΝ ΜΕ              ΝΑΟΔΟ         ΝΟΔΟ 4720Α    45         Kgr     6.000,00              0,50     3.000,00
        ΨΥΧΡΟ ΑΣΦΑΛΤΟΜΙΓΜΑ              Α\\ΝΔ08.3
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 45]
    assert rows[0].article_code == "ΝΑΟΔΟ Α\\ΝΑ01.1"
    assert rows[0].unit == "ΗΜ/Σ"
    assert rows[0].quantity == 10
    assert rows[0].unit_price == 450
    assert rows[0].amount == 4500
    assert rows[1].article_code == "ΝΑΟΔΟ Α\\ΝΔ08.3"
    assert rows[1].unit == "Kgr"
    assert rows[1].quantity == 6000
    assert rows[1].unit_price == 0.5
    assert rows[1].amount == 3000


def test_parse_budget_rows_handles_decimal_at_layout_with_suffix_articles() -> None:
    text = """
       1 Μεταφορές με αυτοκίνητο δια    ΝΑΟΙΚ          ΟΙΚ 1136      1.01     ton.k    900,00               0,35      315,00
         μέσου οδών καλής βατότητας     10.07.01                                m
       5 Καθαίρεση ειδών υγιεινής       ΝΑΟΙΚ          ΟΙΚ 2222      1.05      ΤΕΜ      10,00          15,70          157,00
                                        22.04.ΝΒΠ1
       9 Θύρες σιδηρές σύνθετου         ΝΑΟΙΚ          ΟΙΚ 6201      4.10     τεμαχι     1,00       7.500,00      7.500,00
         σχεδίου                         62.22.ΣΜ                                ο
      31 Υδραυλικός ανελκυστήρας και     ΑΤΗΕ          ΗΛΜ 63        6.32     τεμαχι     1,00      35.100,00     35.100,00
         κατασκευή φρεάτιου.             9000                                    ο
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 4]
    assert rows[0].article_code == "ΝΑΟΙΚ 10.07.01"
    assert rows[1].article_code == "ΝΑΟΙΚ 22.04.ΝΒΠ1"
    assert rows[2].article_code == "ΝΑΟΙΚ 62.22.ΣΜ"
    assert rows[3].article_code == "ΑΤΗΕ 9000"
    assert [row.amount for row in rows] == [315, 157, 7500, 35100]


def test_pricing_candidate_document_accepts_meleti_budget_bundle() -> None:
    assert _is_pricing_candidate_document(
        "ΜΕΛΕΤΗ συντηρηση και επισκευη αυλειων χωρων 7_2021_Π_Μ_Π.pdf",
        Path("ΜΕΛΕΤΗ συντηρηση και επισκευη αυλειων χωρων 7_2021_Π_Μ_Π.pdf"),
    )


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
    assert summary["amount_validation"]["ok"] is True
    assert summary["amount_validation"]["checked"] == 3
    assert summary["amount_validation"]["mismatch_count"] == 0
    assert search_payload["summary"]["matches"] == 1
    assert search_payload["results"][0]["source_document"] == "__PROJECT_BUDGET_MERGED__"
    assert "καθαρό προϋπολογισμό" in search_payload["results"][0]["description"]


def test_consolidate_reports_row_amount_mismatches(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    upsert_pricing_project(db_path, eshidis_id="221566")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="03-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="budget",
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221566",
        document_id=document_id,
        source_document="03-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        rows=[
            PricingBudgetRow(
                row_number=1,
                article_code="ΝΑΟΔΟ Α02",
                canonical_article_code="ΝΑΟΔΟΑ02",
                description="Γενικές εκσκαφές",
                revision_codes=[],
                unit="m3",
                quantity=10,
                unit_price=3.55,
                amount=99,
                raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10,00 3,55 99,00",
                confidence=0.9,
            )
        ],
    )

    summary = consolidate_pricing_project_budget(db_path, eshidis_id="221566")

    assert summary["amount_validation"]["ok"] is False
    assert summary["amount_validation"]["mismatch_count"] == 1
    mismatch = summary["amount_validation"]["mismatches"][0]
    assert mismatch["row_number"] == 1
    assert mismatch["expected_amount"] == 35.5
    assert mismatch["amount"] == 99


def test_consolidate_prefers_amount_valid_duplicate_row_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    upsert_pricing_project(db_path, eshidis_id="221271")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221271",
        document_name="ΜΕΛΕΤΗ.pdf",
        document_type="budget",
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221271",
        document_id=document_id,
        source_document="ΜΕΛΕΤΗ.pdf",
        rows=[
            PricingBudgetRow(
                row_number=3,
                article_code="BAD",
                canonical_article_code="BAD",
                description="Wrong table carry-over",
                revision_codes=[],
                unit="mm",
                quantity=4,
                unit_price=75,
                amount=5,
                raw_text="3 Wrong table carry-over mm 4 75 5",
                confidence=0.9,
            ),
            PricingBudgetRow(
                row_number=3,
                article_code="ΟΙΚ Ν8537.2",
                canonical_article_code="ΟΙΚΝ8537.2",
                description="Αποξηλώσεις υφιστάμενων ειδών υγιεινής",
                revision_codes=[],
                unit="Τεμ.",
                quantity=130,
                unit_price=15,
                amount=1950,
                raw_text="3 Αποξηλώσεις υφιστάμενων ΟΙΚ Ν8537.2 Τεμ. 130 15,00 1950,00",
                confidence=0.9,
            ),
        ],
    )

    summary = consolidate_pricing_project_budget(db_path, eshidis_id="221271")
    search_payload = search_pricing_rows(db_path, "ΟΙΚ Ν8537.2")

    assert summary["amount_validation"]["ok"] is True
    assert summary["amount_validation"]["mismatch_count"] == 0
    assert search_payload["summary"]["matches"] == 1
    assert search_payload["results"][0]["article_code"] == "ΟΙΚ Ν8537.2"


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


def test_ingest_eshidis_project_recovers_partial_rows_without_refetch(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    work_dir = tmp_path / "pricing"
    upsert_pricing_project(db_path, eshidis_id="221566", title="Partial project")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(tmp_path / "budget.txt"),
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221566",
        document_id=document_id,
        source_document="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        rows=[
            PricingBudgetRow(
                row_number=1,
                article_code="ΝΑΟΔΟ Α02",
                canonical_article_code="ΝΑΟΔΟΑ02",
                description="Γενικές εκσκαφές",
                revision_codes=["ΝΟΔΟ-1123"],
                unit="m3",
                quantity=100,
                unit_price=3.55,
                amount=355,
                raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές ΝΟΔΟ-1123 m3 100,00 3,55 355,00",
                confidence=0.9,
            )
        ],
    )

    def fail_fetch(*args, **kwargs):
        raise AssertionError("partial recovery must not refetch ESHIDIS")

    monkeypatch.setattr("tender_radar.pricing.fetch_resource_audit", fail_fetch)
    monkeypatch.setattr("tender_radar.pricing.download_attachment_audit", fail_fetch)

    payload = ingest_pricing_eshidis_project(
        db_path,
        eshidis_id="221566",
        work_dir=work_dir,
        allow_insecure_tls=True,
    )

    assert payload["summary"]["partial_recovered"] is True
    assert payload["summary"]["downloaded"] == 0
    assert payload["summary"]["merged_budget_rows"] == 1
    assert payload["guard"]["status"] == "PARTIAL_PROJECT_RECOVERED_WITHOUT_REFETCH"
