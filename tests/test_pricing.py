from pathlib import Path
import json
import sqlite3

from tender_radar.pricing import (
    _extract_zip_with_greek_filename_repair,
    _guard_official_standalone_budget_route,
    _is_pricing_candidate_document,
    _pricing_document_should_preserve_until_deadline,
    _pricing_budget_router_documents,
    _pricing_rows_from_ai_payload,
    _repair_zip_member_name,
    _validate_ai_budget_rows_against_text_total,
    _unit_price_before_quantity,
    mark_pricing_document_heavy_file_deleted,
    PricingBudgetRow,
    canonical_article_code,
    canonical_revision_code,
    consolidate_pricing_project_budget,
    extract_budget_total_candidates,
    ingest_pricing_active_candidates,
    ingest_pricing_budget_pdf,
    ingest_pricing_eshidis_project,
    parse_greek_decimal,
    parse_budget_rows_from_text,
    reprocess_existing_pricing_projects,
    reprocess_pricing_project_from_texts,
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


def test_parse_greek_decimal_treats_plain_dot_triplets_as_thousands() -> None:
    assert parse_greek_decimal("1.200") == 1200
    assert parse_greek_decimal("12.500") == 12500
    assert parse_greek_decimal("100.00") == 100


def test_parse_greek_decimal_handles_english_thousands_decimal_format() -> None:
    assert parse_greek_decimal("46,750.00") == 46750
    assert parse_greek_decimal("72,649.57") == 72649.57
    assert parse_greek_decimal("1,950.00") == 1950


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


def test_budget_filename_only_accepts_numbered_budget_filename_variants(tmp_path: Path) -> None:
    pdf = tmp_path / "placeholder.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    accepted = [
        "07 ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "04. ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "06_ ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "* ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ_signed.pdf",
        "ΤΕΥΧΗ.zip/04. ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "07 ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.zip/scan001.pdf",
    ]

    for name in accepted:
        assert _is_pricing_candidate_document(name, pdf, mode="budget_filename_only"), name


def test_budget_filename_only_rejects_non_budget_pricing_like_names(tmp_path: Path) -> None:
    pdf = tmp_path / "placeholder.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    rejected = [
        "01 ΜΕΛΕΤΗ.pdf",
        "02 ΠΡΟΜΕΤΡΗΣΗ.pdf",
        "03 ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ.pdf",
        "ΣΤΑΤΙΚΗ ΜΕΛΕΤΗ.zip/ΣΟ3 ΟΠΛΙΣΜΟΙ signed.pdf",
        "OCR text artifact.txt",
    ]

    for name in rejected:
        path = tmp_path / name.replace("/", "_")
        if not path.suffix:
            path = path.with_suffix(".pdf")
        path.write_bytes(b"")
        assert not _is_pricing_candidate_document(name, path, mode="budget_filename_only"), name


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


def test_parse_budget_rows_handles_local_at_with_unit_price_before_quantity() -> None:
    text = """
                                                 ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΜΕΛΕΤΗΣ
                                                        Μον                                                          Τιμή
Α/Α                  Περιγραφή εργασιών                           ΑΤ       Προέλ. Τιμολ.          Κωδ Αναθ                   Ποσότ    Ποσόν
                                                        Μετρ                                                        Μοναδ

                                                   ΥΠΟΟΜΑΔΑ Α :ΑΠΟΞΗΛΩΣΕΙΣ-ΚΑΘΑΙΡΕΣΕΙΣ
         Εκτοποθέτηση πίλλαρ και μεταφορά του στις
 1                                                      τεμ.    ΗΛΜ-1     ΣΧ.ΑΤΗΕ 9413.1          ΗΛΜ100            76,00     44,00   3.344,00
                   αποθήκες του Δήμου
      Εκτοποθέτηση κενού πίλλαρ και μεταφορά του στις
 2                                                      τεμ.    ΗΛΜ-2     ΣΧ.ΑΤΗΕ 9413.2          ΗΛΜ100            49,00     4,00    196,00
                   αποθήκες του Δήμου
                                                           ΣΥΝΟΛΟ Α                                                                   3.540,00
                                                 ΥΠΟΟΜΑΔΑ Β : ΕΡΓΑΣΙΕΣ ΕΓΚΑΤΑΣΤΑΣΗΣ ΠΙΛΛΑΡ

                                                                  [5]
       Εγκαταστάσεις φωτισμού οδών - πίλλαρ
                                                               ΝΕΤ.ΗΛΜ
1   οδοφωτισμού - πίλλαρ οδοφωτισμού τεσσάρων   τεμ.   ΗΛΜ-3                ΗΛΜ52         2.500,00   39,00   97.500,00
                                                               60.10.80.1
                   αναχωρήσεων
        Εγκαταστάσεις φωτισμού οδών - πίλαρ
                                                               ΝΕΤ.ΗΛΜ
2     οδοφωτισμού - πίλλαρ οδοφωτισμού οκτώ     τεμ.   ΗΛΜ-4                ΗΛΜ52         2.750,00   4,00    11.000,00
                                                               60.10.80.2
                   αναχωρήσεων
        Εγκαταστάσεις φωτισμού οδών - πίλαρ
                                                               ΝΕΤ.ΗΛΜ
3     οδοφωτισμού - πίλλαρ οδοφωτισμού είκοσι   τεμ.   ΗΛΜ-5                ΗΛΜ52         3.250,00   1,00     3.250,00
                                                               60.10.80.3
                   αναχωρήσεων
                                                   ΣΥΝΟΛΟ Β                                                  111.750,00

                                                                                             ΣΥΝΟΛΟ Α+Β 115.290,00
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 4, 5]
    assert [row.article_code for row in rows] == ["ΗΛΜ-1", "ΗΛΜ-2", "ΗΛΜ-3", "ΗΛΜ-4", "ΗΛΜ-5"]
    assert [row.unit_price for row in rows] == [76, 49, 2500, 2750, 3250]
    assert [row.quantity for row in rows] == [44, 4, 39, 4, 1]
    assert sum(row.amount or 0 for row in rows) == 115290


def test_parse_budget_rows_handles_category_prefixed_article_table() -> None:
    text = """
                           ΟΜΑΔΑ Α : ΧΩΜΑΤΟΥΡΓΙΚΑ
 ΟΔΟ         Α-2      1      Α1     Γενικές εκσκαφές σε έδαφος γαιώδες -ημιβραχώδες                 ΟΔΟ-1123Α      m3        300            3,55       1.065,00

 ΟΔΟ        Α-18.3    2      Α2     Δάνεια θραυστών επίλεκτων υλικών λατομείου Κατηγ. Ε4            ΟΔΟ-1510       m3        300           15,50       4.650,00
                                                                                                                       3
 ΟΔΟ         Α-20     3      Α3     Κατασκευή επιχωμάτων                                            ΟΔΟ-1530       m         300            1,05        315,00

                                    Προσαύξηση τιμών εκσκαφών ορυγμάτων υπογείων δικτύων για
 ΥΔΡ         3.12     4      Β1                                                                     ΥΔΡ 6087       m        300,00         15,50       4.650,00
                                    την αντιμετώπιση προσθέτων δυσχερειών από διερχόμενα δίκτυα
 ΟΔΟ       Β-29.3.1   5      Β2                                                                     ΟΔΟ-2532       m3       250,00         94,20      23.550,00
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 4, 5]
    assert [row.article_code for row in rows] == ["ΟΔΟ Α-2", "ΟΔΟ Α-18.3", "ΟΔΟ Α-20", "ΥΔΡ 3.12", "ΟΔΟ Β-29.3.1"]
    assert rows[2].unit == "m3"
    assert rows[2].quantity == 300
    assert rows[2].amount == 315
    assert rows[3].description.startswith("Προσαύξηση τιμών εκσκαφών")
    assert rows[4].revision_codes == ["ΟΔΟ-2532"]
    assert sum(row.amount or 0 for row in rows) == 34230


def test_parse_budget_rows_handles_wrapped_numeric_prefix_rows() -> None:
    text = """
                                                    ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ
                                             ΚΩΔΙΚΟΣ                ΚΩΔΙΚΟΣ                               ΜΕΡΙΚΗ       ΟΛΙΙΚΗ
Α/Α                   ΠΕΡΙΓΡΑΦΗ                            Α.Τ.               Μ.Μ. ΠΟΣΟΤΗΤΑ     ΤΙΜΗ
                                             ΑΡΘΡΟΥ                ΑΝΑΘ/ΣΗΣ                               ΔΑΠΑΝΗ      ΔΑΠΑΝΗ
      1. ΧΩΜΑΤΟΥΡΓΙΚΑ
    Καθαίρεση οπλισμένων
                                                                   ΟΙΚ-2227   m3     22.50      25.40
  1 σκυροδεμάτων                             ΟΔΟ Α-12       1                                                571.50
    Σκυροδέματα - Σκυρόδεμα κατηγορίας
                                                                  ΟΔΟ 2532    m3     22.50      94.00
    τάφρων, προστασίας
  2 στεγάνωσης γεφυρών κλπ                  ΟΔΟ B-29.3.1    2                                              2,115.00
    Σιδηροί οπλισμοί - Σιδηρούν δομικό
    πλέγμα STIV (S500s) εκτός υπόγειων                             ΥΔΡ 7018   Kg    330.00      1.15
  3 έργων                                   ΟΔΟ B-30.3      3                                                379.50
  4 ορθογωνισμένες                           ΟΙΚ 73.12      4      ΟΙΚ 7312   m2    550.00      85.00     46,750.00
      ΣΥΝΟΛΟ                                                                                              49,816.00    49,816.00
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 4]
    assert [row.article_code for row in rows] == ["ΟΔΟ Α-12", "ΟΔΟ B-29.3.1", "ΟΔΟ B-30.3", "ΟΙΚ 73.12"]
    assert rows[0].revision_codes == ["ΟΙΚ-2227"]
    assert rows[0].unit == "m3"
    assert rows[0].quantity == 22.50
    assert rows[0].unit_price == 25.40
    assert rows[0].amount == 571.50
    assert rows[2].unit == "Kg"
    assert sum(row.amount or 0 for row in rows) == 49816


def test_extract_budget_total_candidates_handles_english_thousands_decimal_format() -> None:
    text = """
      ΣΥΝΟΛΟ                                                                                              49,816.00    49,816.00
      ΔΑΠΑΝΗ ΕΡΓΑΣΙΩΝ                                                                                                  72,649.57
      ΣΥΝΟΛΙΚΗ ΔΑΠΑΝΗ ΕΡΓΑΣΙΩΝ                                                                                         85,000.00
    """

    candidates = extract_budget_total_candidates(text)

    assert [candidate["amount"] for candidate in candidates] == [49816, 72649.57, 85000]


def test_extract_budget_total_candidates_handles_sparse_ocr_synolo() -> None:
    text = "ΣWΝ ΟΛΟ                                     49.460,00\nΣΥΝΟΛΟ ΑΠΟΛΟΓΙΣΤΙΚΩΝ ΕΡΓΑΣΙΩΝ 576,34"

    candidates = extract_budget_total_candidates(text)

    assert candidates[0]["amount"] == 49460


def test_extract_budget_total_candidates_ignores_quantity_totals() -> None:
    text = """
    Σύνολο = 850,00 Kgr
    ΣΥΝΟΛΟ ΧΩΡΩΝ ΠΑΙΔΙΚΟΥ ΣΤΑΘΜΟΥ 170,51τμ
    Σύνολο Κόστους Εργασιών Σ1: 93.574,13 Π1:
    """

    candidates = extract_budget_total_candidates(text)

    assert [candidate["amount"] for candidate in candidates] == [93574.13]


def test_extract_budget_total_candidates_prefers_project_total_before_p2_zero() -> None:
    text = "Σύνολο Δαπάνης του Έργου Σ2: 110.417,47 Π2: 0,00"

    candidates = extract_budget_total_candidates(text)

    assert [candidate["amount"] for candidate in candidates] == [110417.47]


def test_parse_budget_rows_handles_collapsed_ocr_table_stream() -> None:
    text = """
    ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΔΗΜΟΠΡΑΤΗΣΗΣ 1]Εκθάµνωση εδάφους µε ΝΑΟΙΚ ΟΙΚ2101 001 m2 | 4.480,00 17.920,00
    δενδρύλια περιµέτρου κορμού |20.01.01 μέχρι 0,25 m 2|Εκθάµνωση εδάφους µε ΝΑΟΙΚ OIK 2101 002 m2
    2.065,00 5,00 10.325,00 δενδρύλια περιµέτρου κορμού {20.01.02 0,26 - 0,40 m
    3 |Αποξήλωση κρασπέδων ΝΑΥΔΡ 4.05.ΣΧ | YAP 6808 003 m 280,00 8,00 2.240,00 πρόχυτων ή μή
    5] Γενικές Εκσκαφές σε έδαφος |ΙΝΑΟΔΟ Α02 ΝΟΔΟ 1123.A 005 m3 9.420,00 4,45 41.919,00
    γαιώδες - ημιβραχώδες
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 5]
    assert rows[0].article_code == "ΝΑΟΙΚ 20.01.01"
    assert rows[0].unit == "m2"
    assert rows[0].quantity == 4480
    assert rows[0].unit_price == 4
    assert rows[0].amount == 17920
    assert rows[2].article_code == "ΝΑΥΔΡ 4.05.ΣΧ"
    assert rows[2].revision_codes == ["ΥΔΡ-6808"]
    assert rows[3].canonical_article_code == "ΙΝΑΟΔΟΑ02"
    assert rows[3].amount == 41919


def test_ai_pricing_rows_are_normalized_and_amount_guarded() -> None:
    rows, rejected = _pricing_rows_from_ai_payload(
        [
            {
                "row_number": 1,
                "article_code": "ΝΑΟΔΟ Α02",
                "description": "Γενικές εκσκαφές σε έδαφος γαιώδες",
                "revision_codes": ["ΟΔΟ-1123Α"],
                "unit": "m3",
                "quantity": "100,00",
                "unit_price": "3,55",
                "amount": "355,00",
                "evidence": "1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές ΟΔΟ-1123Α m3 100,00 3,55 355,00",
            },
            {
                "row_number": 2,
                "article_code": "ΝΑΟΔΟ Γ01",
                "description": "Υπόβαση οδοστρωσίας",
                "revision_codes": ["ΟΔΟ-3121Β"],
                "unit": "m3",
                "quantity": "100,00",
                "unit_price": "10,00",
                "amount": "2.000,00",
                "evidence": "2 ΝΑΟΔΟ Γ01 Υπόβαση ΟΔΟ-3121Β m3 100,00 10,00 2.000,00",
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0].canonical_article_code == "ΝΑΟΔΟΑ02"
    assert rows[0].revision_codes == ["ΟΔΟ-1123Α"]
    assert rows[0].amount == 355
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "invalid_or_unvalidated"


def test_ai_pricing_rows_require_document_total_match() -> None:
    rows, rejected = _pricing_rows_from_ai_payload(
        [
            {
                "row_number": 1,
                "article_code": "ΝΑΟΔΟ Α02",
                "description": "Γενικές εκσκαφές",
                "revision_codes": ["ΟΔΟ-1123Α"],
                "unit": "m3",
                "quantity": "100,00",
                "unit_price": "10,00",
                "amount": "1.000,00",
                "evidence": "1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές ΟΔΟ-1123Α m3 100,00 10,00 1.000,00",
            }
        ]
    )

    assert rejected == []
    mismatch = _validate_ai_budget_rows_against_text_total(rows, "Σύνολο Κόστους Εργασιών Σ1: 900,00 Π1:")
    ok = _validate_ai_budget_rows_against_text_total(rows, "Σύνολο Κόστους Εργασιών Σ1: 1.000,00 Π1:")
    no_reference = _validate_ai_budget_rows_against_text_total(rows, "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ χωρίς καθαρό σύνολο")

    assert mismatch["ok"] is False
    assert mismatch["status"] == "MISMATCH"
    assert ok["ok"] is True
    assert no_reference["ok"] is False
    assert no_reference["status"] == "NO_REFERENCE_TOTAL_FOUND"


def test_parse_budget_rows_handles_sparse_ocr_table_with_missing_unit_prices() -> None:
    text = """
                                                                                                                       Αριθ. Τιμολ.    Αρθρο
                                       Συνοπτική περιγραφή                                                                                        Μονάδα                 Ποσότητα        ..
                                                                                                                                      Αναθεώρ.
                                                                                  Α. ΟΙΚΟΔΟΜΙΚΕΣ ΕΡΓΑΣΙΕΣ
 1   Στεγονοποίηση κεραμοσκεπών με επαλειφόμενη ελαστική πολυουρική δύο συστατικών                                 79.50 ΣΧΕΤ.        ΟΙΚ-7798                             300,00     24.000,00
 2   Αποξήλωση αρμών πλακιδίων και νέα αρμολόγηση με ειδικό στόκο στεγανοποίησης και                                71.01.ΟΙΣΧΕΤ.      ΟΙΚ-7101                             260,00       7.020,00
 3   Επάλειψη με υβριδικό ελαστομερές υδατοδιάλυτο στεγανωτικό                                                       79.70.02 ΣΧΕΤ.     ΟΙΚ-7798                              10,00        160,00
 ~   Επάλειψη επιφανειών ή πλακιδίων με διαφανή στεγανωτική μεμβράνη πολυουρεθανικής                                79.05 ΣΧΕΤ.        ΟΙΚ-7798      m2           28,00     260,00       7.280,00
 5   Ειδικά επιχρίσματα ινοπλισμένο                                                                 71.85 ΣΧΕΤ.       ΟΙΚ—7136                     m2           50,00     220,00      11.000,00
                                                                  ΣΥΝΟΛΟ                                     49.460,00
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 4, 5]
    assert rows[0].unit == "UNKNOWN"
    assert rows[0].unit_price == 80
    assert rows[3].unit == "m2"
    assert rows[3].unit_price == 260
    assert rows[4].revision_codes == ["ΟΙΚ-7136"]
    assert sum(row.amount or 0 for row in rows) == 49460


def test_consolidate_validates_merged_sum_against_document_total(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    text_path = tmp_path / "budget.txt"
    text_path.write_text("ΣΥΝΟΛΟ Α+Β 115.290,00\nΤΕΛΙΚΗ ΔΑΠΑΝΗ 200.000,00", encoding="utf-8")
    upsert_pricing_project(db_path, eshidis_id="221233")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221233",
        document_name="1_ΜΕΛΕΤΗ ΕΡΓΟΥ.pdf",
        document_type="budget",
        text_path=str(text_path),
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221233",
        document_id=document_id,
        source_document="1_ΜΕΛΕΤΗ ΕΡΓΟΥ.pdf",
        rows=[
            PricingBudgetRow(1, "ΗΛΜ-1", "ΗΛΜ1", "Εκτοποθέτηση πίλλαρ", ["ΗΛΜ100"], "τεμ.", 44, 76, 3344, "", 0.9),
            PricingBudgetRow(2, "ΗΛΜ-2", "ΗΛΜ2", "Εκτοποθέτηση κενού πίλλαρ", ["ΗΛΜ100"], "τεμ.", 4, 49, 196, "", 0.9),
            PricingBudgetRow(3, "ΗΛΜ-3", "ΗΛΜ3", "Πίλλαρ τεσσάρων αναχωρήσεων", ["ΗΛΜ52"], "τεμ.", 39, 2500, 97500, "", 0.9),
            PricingBudgetRow(4, "ΗΛΜ-4", "ΗΛΜ4", "Πίλλαρ οκτώ αναχωρήσεων", ["ΗΛΜ52"], "τεμ.", 4, 2750, 11000, "", 0.9),
            PricingBudgetRow(5, "ΗΛΜ-5", "ΗΛΜ5", "Πίλλαρ είκοσι αναχωρήσεων", ["ΗΛΜ52"], "τεμ.", 1, 3250, 3250, "", 0.9),
        ],
    )

    summary = consolidate_pricing_project_budget(db_path, eshidis_id="221233")

    assert summary["amount_total"] == 115290
    assert summary["document_total_validation"]["ok"] is True
    assert summary["document_total_validation"]["reference_total"] == 115290
    assert summary["document_total_validation"]["reference"]["source_document"] == "1_ΜΕΛΕΤΗ ΕΡΓΟΥ.pdf"
    connection = sqlite3.connect(db_path)
    try:
        stored = connection.execute(
            "SELECT metadata_json FROM pricing_projects WHERE eshidis_id = ?",
            ("221233",),
        ).fetchone()
    finally:
        connection.close()
    assert stored is not None
    audit = json.loads(stored[0])["pricing_budget_audit"]
    assert audit["document_total_validation"]["status"] == "OK"
    assert audit["amount_total"] == 115290


def test_consolidate_validates_against_offer_total_when_budget_lacks_total(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    budget_text_path = tmp_path / "budget.txt"
    budget_text_path.write_text("ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ\n1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10,00 3,55 35,50\n", encoding="utf-8")
    offer_text_path = tmp_path / "offer.txt"
    offer_text_path.write_text(
        "ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΣΦΟΡΑ\nΣύνολο Κόστους Εργασιών Σ1: 35,50 Π1:\n",
        encoding="utf-8",
    )
    upsert_pricing_project(db_path, eshidis_id="221689")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221689",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="budget",
        text_path=str(budget_text_path),
    )
    upsert_pricing_document(
        db_path,
        eshidis_id="221689",
        document_name="Οικονομική_προσφορά_Έργου.pdf",
        document_type="offer",
        text_path=str(offer_text_path),
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221689",
        document_id=document_id,
        source_document="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        rows=[
            PricingBudgetRow(1, "ΝΑΟΔΟ Α02", "ΝΑΟΔΟΑ02", "Γενικές εκσκαφές", [], "m3", 10, 3.55, 35.5, "", 0.9),
        ],
    )

    summary = consolidate_pricing_project_budget(db_path, eshidis_id="221689")

    assert summary["document_total_validation"]["ok"] is True
    assert summary["document_total_validation"]["reference_total"] == 35.5
    assert summary["document_total_validation"]["reference"]["source_document"] == "Οικονομική_προσφορά_Έργου.pdf"


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


def test_parse_budget_rows_handles_article_suffix_continuation_without_revision_column() -> None:
    text = """
      8 Επιστρώσεις με ΝΑΟΔΟ ΟΔΟΝ 2922 16 m2 490,00 35,00 17.150,00
        προκατασκευασμένους Ν\\Β52.ΣΧ6
      13 Τσιμεντόπλακες όδευσης ΝΑΟΙΚ 13 Μ2 22,00 28,50 627,00
        τυφλών. Με τετράγωνες 73.16.1.ΣΧ
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [16, 13]
    assert rows[0].article_code == "ΝΑΟΔΟ Ν\\Β52.ΣΧ6"
    assert "Επιστρώσεις με προκατασκευασμένους" in rows[0].description
    assert rows[0].revision_codes == ["ΟΔΟΝ-2922"]
    assert rows[0].unit == "m2"
    assert rows[0].quantity == 490
    assert rows[0].unit_price == 35
    assert rows[0].amount == 17150
    assert rows[1].article_code == "ΝΑΟΙΚ 73.16.1.ΣΧ"
    assert "Τσιμεντόπλακες όδευσης τυφλών" in rows[1].description
    assert rows[1].revision_codes == []
    assert rows[1].unit == "Μ2"
    assert rows[1].quantity == 22
    assert rows[1].unit_price == 28.5
    assert rows[1].amount == 627


def test_parse_budget_rows_handles_neighbor_article_code_with_at_before_unit() -> None:
    text = """
                                            ΝΕΤ ΟΔΟ-               ΟΙΚ 7902
      23    Αντιγραφιστική επάλειψη.                        068                            m2     1000       5,8      5.800,00
                                            ΜΕ Β-35                100,00%
                                            ΝΕΤ ΠΡΣ           ΠΡΣ 5340
      26    Λιπάνσεις. Λίπανση φυτών με τα             138                        Τεμ.     318      0,05           15,90
                                            ΣΤ3.1             100,00%
                                            ΝΕΤ ΠΡΣ           ΠΡΣ 5540
      27    Λιπάνσεις. Λίπανση                         139                        Στρ.       5     11,25           56,25
                                            ΣΤ3.4             100,00%
                                            ΝΕΤ ΠΡΣ           ΠΡΣ 5354
      28    μεγάλων δένδρων. Μεγάλων                   140                        Τεμ.       7      67,5          472,50
                                            ΣΤ4.3.1           100,00%
                                            ΝΕΤ ΠΡΣ           ΠΡΣ 5354
      29    μεγάλων δένδρων. Μεγάλων                   141                        Τεμ.      12      100         1.200,00
                                            ΣΤ4.3.3           100,00%
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [68, 138, 139, 140, 141]
    assert [row.article_code for row in rows] == [
        "ΝΕΤ ΟΔΟ- ΜΕ Β-35",
        "ΝΕΤ ΠΡΣ ΣΤ3.1",
        "ΝΕΤ ΠΡΣ ΣΤ3.4",
        "ΝΕΤ ΠΡΣ ΣΤ4.3.1",
        "ΝΕΤ ΠΡΣ ΣΤ4.3.3",
    ]
    assert [row.revision_codes for row in rows] == [
        ["ΟΙΚ-7902"],
        ["ΠΡΣ-5340"],
        ["ΠΡΣ-5540"],
        ["ΠΡΣ-5354"],
        ["ΠΡΣ-5354"],
    ]
    assert [row.amount for row in rows] == [5800, 15.9, 56.25, 472.5, 1200]


def test_parse_budget_rows_handles_neighbor_article_code_when_numeric_line_has_only_at() -> None:
    text = """
       Ξυλότυποι -Οπλισμοί. Καμπύλοι     ΝΕΤ ΟΙΚ-             ΟΙΚ 3821
 11                                                  023                          m2        5      22,5        112,50
       ξυλότυποι απλής καμπυλότητας.     Α 38.4               100,00%
    """

    rows = parse_budget_rows_from_text(text)

    assert len(rows) == 1
    row = rows[0]
    assert row.row_number == 23
    assert row.article_code == "ΝΕΤ ΟΙΚ- Α 38.4"
    assert row.revision_codes == ["ΟΙΚ-3821"]
    assert "Καμπύλοι ξυλότυποι απλής καμπυλότητας" in row.description
    assert row.unit == "m2"
    assert row.quantity == 5
    assert row.unit_price == 22.5
    assert row.amount == 112.5


def test_parse_budget_rows_handles_inline_article_fragment_before_at_with_later_suffix() -> None:
    text = """
       σώματος τεχνολογίας τύπου          ΝΕΟ ΗΛΜ
                                                              ΗΛΜ 103
  5     LED ασύμμετρης δέσμης, ισχύος      ΑΤΗΕ.60.     073                           Τεμ.      33     2600      85.800,00
                                                              100,00%
       έως και 30,5W, επί κορυφής           10.1
       ιστού.
    """

    rows = parse_budget_rows_from_text(text)

    assert len(rows) == 1
    row = rows[0]
    assert row.row_number == 73
    assert row.article_code == "ΝΕΟ ΗΛΜ ΑΤΗΕ.60. 10.1"
    assert row.revision_codes == ["ΗΛΜ-103"]
    assert "LED ασύμμετρης δέσμης" in row.description
    assert row.quantity == 33
    assert row.unit_price == 2600
    assert row.amount == 85800


def test_parse_budget_rows_uses_at_unit_price_when_table_row_has_only_quantity() -> None:
    text = """
       Εγκατάσταση πρασίνου. Άνοιγμα λάκκων σε χαλαρά εδάφη με
  7                                                                       119    ΝΕΤ ΠΡΣ Ε1.1        Τεμ.          35
       εργαλεία χειρός. Άνοιγμα λάκκων διαστάσεων 0,30 x 0,30 x 0,30 m
       Εγκατάσταση πρασίνου. Άνοιγμα λάκκων με χρήση εκσκαπτικού
  8                                                                       120    ΝΕΤ ΠΡΣ Ε4.3        Τεμ.          80
       μηχανήματος. Άνοιγμα λάκκων διαστάσεων 1,00 x 1,00 x 1,00 m
  9    Φυτικό υλικό. Δένδρα. Δένδρα κατηγορίας Δ9                         121    ΝΕΤ ΠΡΣ Δ1.9        Τεμ.          60

  A.T.:                   120

  ΝΕΤ ΠΡΣ Ε4.3            Εγκατάσταση πρασίνου. Άνοιγμα λάκκων με χρήση εκσκαπτικού
                          μηχανήματος. Άνοιγμα λάκκων διαστάσεων 1,00 x 1,00 x 1,00 m

  ΕΥΡΩ          (Ολογράφως):     ΤΕΣΣΕΡΑ
                (Αριθμητικώς):   4,00

  A.T.:                    121
    """

    rows = parse_budget_rows_from_text(text)

    row = next(row for row in rows if row.row_number == 120)
    assert row.article_code == "ΝΕΤ ΠΡΣ Ε4.3"
    assert row.quantity == 80
    assert row.unit_price == 4
    assert row.amount == 320


def test_unit_price_layout_detects_split_quantity_before_price_header() -> None:
    text = """
                                           Κωδικός    Αρ.       Άρθρο                   Ποσό     Τιμή                Δαπάνη
Α/Α             Είδος Εργασίας                                           Μονάδα
                                       Άρθρου     Τιμ.   Αναθεώρησης                τητα     (€)        Μερική ( € )   Ολική ( € )
    """

    assert _unit_price_before_quantity(text) is False


def test_parse_budget_rows_drops_invalid_complete_ocr_table_rows_when_valid_rows_exist() -> None:
    text = """
      1 001 Τομή οδοστρώματος με ασφαλτοκόπτη ΝΕΤ ΟΔΟ-ΜΕ Δ-1 m 600 1 600,00
      2 002 Αποξήλωση ασφαλτοταπήτων ΝΕΤ ΟΔΟ-ΜΕ Α-2.1 m3 385 4,75 1.828,75
      3 003 Καθαίρεση πλακοστρώσεων ΝΕΤ ΟΙΚ-Α 22.20.1 m2 1500 7,90 11.850,00
      4 004 Γενικές εκσκαφές ΝΕΤ ΟΔΟ-ΜΕ Α-2 m3 1500 3,85 5.775,00
      5 005 Ψευδής συμπιεσμένη γραμμή ΝΕΤ ΟΔΟ-ΜΕ Β-2 m3 1000 6 2210.1
    """

    rows = parse_budget_rows_from_text(text)

    assert [row.row_number for row in rows] == [1, 2, 3, 4]
    assert all(row.amount == round((row.quantity or 0) * (row.unit_price or 0), 2) for row in rows)


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


def test_pricing_candidate_document_skips_drawings_inside_meleti_archive() -> None:
    assert not _is_pricing_candidate_document(
        "ΣΧΕΔΙΑ ΑΡΧ.ΜΕΛΕΤΗΣ 3 .zip/ΝΕΟ Σ18 signed .pdf",
        Path("ΝΕΟ Σ18 signed .pdf"),
    )
    assert not _is_pricing_candidate_document(
        "ΣΤΑΤΙΚΗ ΜΕΛΕΤΗ .zip/ΣΟ3 ΟΠΛΙΣΜΟΙ signed.pdf",
        Path("ΣΟ3 ΟΠΛΙΣΜΟΙ signed.pdf"),
    )


def test_pricing_candidate_document_accepts_budget_inside_archive() -> None:
    assert _is_pricing_candidate_document(
        "ΤΕΥΧΗ ΔΗΜΟΠΡΑΤΗΣΗΣ.zip/2_ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        Path("2_ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf"),
    )


def test_pricing_retention_preserves_only_essential_operational_documents() -> None:
    preserved = [
        "ΠΡΟΣΚΛΗΣΗ.pdf",
        "ΔΙΑΚΗΡΥΞΗ ΕΡΓΟΥ.pdf",
        "ΤΕΧΝΙΚΗ ΕΚΘΕΣΗ.pdf",
        "ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ.pdf",
        "ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "ΤΙΜΟΛΟΓΙΟ ΜΕΛΕΤΗΣ.pdf",
    ]
    for name in preserved:
        assert _pricing_document_should_preserve_until_deadline(name), name

    secondary = [
        "ΓΕΩΛΟΓΙΚΗ ΜΕΛΕΤΗ.pdf",
        "ΠΕΡΙΒΑΛΛΟΝΤΙΚΗ ΜΕΛΕΤΗ.pdf",
        "ΣΑΥ.pdf",
        "ΦΑΥ.pdf",
        "ΟΙΚΟΔΟΜΙΚΗ ΑΔΕΙΑ.zip",
        "ΜΕΛΕΤΗ ΕΦΑΡΜΟΓΗΣ.zip",
        "ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ.pdf",
    ]
    for name in secondary:
        assert not _pricing_document_should_preserve_until_deadline(name), name


def test_mark_pricing_document_heavy_file_deleted_clears_stale_local_path(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    fake_pdf = tmp_path / "ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf"
    fake_pdf.write_bytes(b"%PDF fixture")
    upsert_pricing_document(
        db_path,
        eshidis_id="220675",
        document_name=fake_pdf.name,
        local_path=str(fake_pdf),
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
    )

    fake_pdf.unlink()
    mark_pricing_document_heavy_file_deleted(db_path, eshidis_id="220675", document_name=fake_pdf.name)

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT local_path, heavy_file_deleted_at FROM pricing_documents WHERE eshidis_id = ? AND document_name = ?",
            ("220675", fake_pdf.name),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    assert row[0] is None
    assert row[1]


def test_pricing_budget_router_prioritizes_standalone_official_budget_over_zip_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    nested_text = tmp_path / "nested.txt"
    official_text = tmp_path / "official.txt"
    nested_text.write_text(
        """
        ΣΥΝΟΠΤΙΚΟΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ
        1 ΟΔΟ Α-24.2 Επένδυση πρανών ΟΔΟ-1610 m2 1.800,00 10,50 18.900,00
        """,
        encoding="utf-8",
    )
    official_text.write_text("A.10 m 16,90 30,00\n", encoding="utf-8")
    upsert_pricing_document(
        db_path,
        eshidis_id="220675",
        document_name="ΜΕΛΕΤΗ ΕΦΑΡΜΟΓΗΣ.zip/ΣΥΝΟΠΤΙΚΟΣ ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        text_path=str(nested_text),
        text_sample=nested_text.read_text(encoding="utf-8"),
    )
    official_id = upsert_pricing_document(
        db_path,
        eshidis_id="220675",
        document_name="ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        text_path=str(official_text),
        text_sample=official_text.read_text(encoding="utf-8"),
    )

    documents = _pricing_budget_router_documents(db_path, eshidis_id="220675", max_documents=2, max_pages_per_document=4)

    assert documents[0]["document_id"] == official_id
    assert documents[0]["official_budget_priority"] > documents[1]["official_budget_priority"]


def test_pricing_budget_router_guard_overrides_nested_summary_when_official_budget_exists() -> None:
    route = {
        "budget_document": "ΜΕΛΕΤΗ ΕΦΑΡΜΟΓΗΣ.zip/ΣΥΝΟΠΤΙΚΟΣ ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        "budget_document_id": 232,
        "page_start": 16,
        "page_end": 17,
        "section_start_hint": "ΣΥΝΟΠΤΙΚΟΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ",
        "section_end_hint": "ΓΕΝΙΚΟ ΣΥΝΟΛΟ",
        "offer_document": None,
        "offer_document_id": None,
        "ignore_documents": [],
        "budget_shape": {
            "row_number_column": "Α/Α",
            "article_column": "ΑΡΘΡΟ",
            "description_column": "ΠΕΡΙΓΡΑΦΗ",
            "unit_column": "ΜΟΝΑΔΑ",
            "quantity_column": "ΠΟΣΟΤΗΤΑ",
            "unit_price_column": "ΤΙΜΗ",
            "amount_column": "ΔΑΠΑΝΗ",
            "likely_table_layout": "nested summary",
        },
        "confidence": 0.95,
        "evidence": "AI chose the nested archive summary because it had snippets.",
        "warnings": [],
    }
    documents = [
        {
            "document_id": 300,
            "document_name": "ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
            "official_budget_priority": 90,
            "score": 106,
        },
        {
            "document_id": 232,
            "document_name": "ΜΕΛΕΤΗ ΕΦΑΡΜΟΓΗΣ.zip/ΣΥΝΟΠΤΙΚΟΣ ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
            "official_budget_priority": 0,
            "score": 23,
        },
    ]

    guarded = _guard_official_standalone_budget_route(route, documents)

    assert guarded["budget_document_id"] == 300
    assert guarded["budget_document"] == "ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf"
    assert guarded["page_start"] is None
    assert guarded["page_end"] is None
    assert guarded["confidence"] == 0.8
    assert "OFFICIAL_STANDALONE_BUDGET_ROUTE_OVERRIDE" in guarded["warnings"][-1]


def test_zip_greek_filename_repair_handles_legacy_cp737_names(tmp_path: Path) -> None:
    greek_name = "ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf"
    mojibake_name = greek_name.encode("cp737").decode("cp437")
    assert _repair_zip_member_name(mojibake_name) == greek_name

    zip_path = tmp_path / "bundle.zip"
    destination = tmp_path / "extracted"
    import zipfile

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(mojibake_name, b"pdf")

    _extract_zip_with_greek_filename_repair(zip_path, destination)

    assert (destination / greek_name).read_bytes() == b"pdf"


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


def test_reprocess_project_rebuilds_rows_from_existing_text(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    text_path = tmp_path / "budget.txt"
    text_path.write_text(
        """
        ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ
        Α/Α Άρθρο Περιγραφή Μονάδα Ποσότητα Τιμή Μονάδας Δαπάνη
        1 ΝΑΟΔΟΑ02 Γενικές εκσκαφές ΟΔΟ-1123 m3 100,00 3,55 355,00
        ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ 355,00
        """,
        encoding="utf-8",
    )
    upsert_pricing_project(db_path, eshidis_id="221566", title="Reprocess project")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(text_path),
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
                description="stale wrong row",
                revision_codes=[],
                unit="m3",
                quantity=1,
                unit_price=1,
                amount=1,
                raw_text="stale wrong row",
                confidence=0.1,
            )
        ],
    )

    payload = reprocess_pricing_project_from_texts(db_path, eshidis_id="221566")

    assert payload["ok"] is True
    assert payload["summary"]["documents_reprocessed"] == 1
    assert payload["summary"]["merged_budget_rows"] == 1
    assert payload["summary"]["merged_budget_amount_total"] == 355


def test_reprocess_existing_skips_complete_projects(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    text_path = tmp_path / "budget.txt"
    text_path.write_text(
        """
        1 ΝΑΟΔΟΑ02 Γενικές εκσκαφές ΟΔΟ-1123 m3 100,00 3,55 355,00
        ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ 355,00
        """,
        encoding="utf-8",
    )
    upsert_pricing_project(db_path, eshidis_id="221566", title="Complete project")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(text_path),
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221566",
        document_id=document_id,
        source_document="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        rows=parse_budget_rows_from_text(text_path.read_text(encoding="utf-8")),
    )
    consolidate_pricing_project_budget(db_path, eshidis_id="221566")

    events: list[dict[str, object]] = []
    payload = reprocess_existing_pricing_projects(db_path, progress_callback=events.append)

    assert payload["summary"]["skipped_complete"] == 1
    assert payload["items"][0]["status"] == "SKIPPED_ALREADY_COMPLETE"
    assert [event["event"] for event in events] == ["reprocess_start", "project_skipped", "reprocess_done"]
    assert events[1]["eshidis_id"] == "221566"
    assert events[1]["status"] == "SKIPPED_ALREADY_COMPLETE"


def test_reprocess_with_ai_budget_router_uses_only_selected_document(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    wrong_text = tmp_path / "wrong.txt"
    budget_text = tmp_path / "budget.txt"
    wrong_text.write_text(
        """
        1 ΝΑΟΔΟΑ01 Λάθος πίνακας ΟΔΟ-1111 m3 1,00 999,00 999,00
        ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ 999,00
        """,
        encoding="utf-8",
    )
    budget_text.write_text(
        """
        1 ΝΑΟΔΟΑ02 Σωστός προϋπολογισμός ΟΔΟ-1123 m3 10,00 20,00 200,00
        ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ 200,00
        """,
        encoding="utf-8",
    )
    upsert_pricing_project(db_path, eshidis_id="221566", title="Routed project")
    wrong_document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="ΤΙΜΟΛΟΓΙΟ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(wrong_text),
    )
    budget_document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221566",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(budget_text),
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221566",
        document_id=wrong_document_id,
        source_document="ΤΙΜΟΛΟΓΙΟ.pdf",
        rows=parse_budget_rows_from_text(wrong_text.read_text(encoding="utf-8")),
    )

    def fake_route(*args, **kwargs):
        return {
            "ok": True,
            "model": "fake",
            "prompt_version": "test-router",
            "documents_considered": 2,
            "route": {
                "budget_document": "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
                "budget_document_id": budget_document_id,
                "page_start": 1,
                "page_end": 1,
                "confidence": 0.95,
                "evidence": "selected budget document",
                "warnings": [],
                "section_start_hint": "ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ",
                "section_end_hint": "200,00",
                "budget_shape": {},
            },
        }

    monkeypatch.setattr("tender_radar.pricing.route_pricing_budget_documents_with_ai", fake_route)

    payload = reprocess_pricing_project_from_texts(
        db_path,
        eshidis_id="221566",
        use_ai_budget_router=True,
    )

    assert payload["ok"] is True
    assert payload["summary"]["ai_budget_router_selected_document_id"] == budget_document_id
    assert payload["summary"]["documents_reprocessed"] == 1
    assert payload["summary"]["documents_skipped_by_ai_budget_router"] == 1
    assert payload["summary"]["merged_budget_rows"] == 1
    assert payload["summary"]["merged_budget_amount_total"] == 200
    assert "SKIPPED_BY_AI_BUDGET_ROUTER" in {item["status"] for item in payload["documents"]}


def test_reprocess_with_ai_budget_router_falls_back_when_routed_parse_fails(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    wrong_text = tmp_path / "wrong.txt"
    budget_text = tmp_path / "budget.txt"
    wrong_text.write_text(
        """
        1 ΝΑΟΔΟΑ01 Λάθος συνοπτικός πίνακας ΟΔΟ-1111 m3 1,00 999,00 999,00
        """,
        encoding="utf-8",
    )
    budget_text.write_text(
        """
        1 ΝΑΟΔΟΑ02 Σωστός αναλυτικός προϋπολογισμός ΟΔΟ-1123 m3 10,00 20,00 200,00
        ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ 200,00
        """,
        encoding="utf-8",
    )
    upsert_pricing_project(db_path, eshidis_id="221567", title="Fallback routed project")
    wrong_document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221567",
        document_name="ΣΥΝΟΠΤΙΚΟΣ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(wrong_text),
    )
    upsert_pricing_document(
        db_path,
        eshidis_id="221567",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        document_type="pdf",
        extraction_status="TEXT_EXTRACTED",
        text_path=str(budget_text),
    )

    def fake_route(*args, **kwargs):
        return {
            "ok": True,
            "model": "fake",
            "prompt_version": "test-router",
            "documents_considered": 2,
            "route": {
                "budget_document": "ΣΥΝΟΠΤΙΚΟΣ.pdf",
                "budget_document_id": wrong_document_id,
                "page_start": 1,
                "page_end": 1,
                "confidence": 0.95,
                "evidence": "bad route",
                "warnings": [],
                "section_start_hint": None,
                "section_end_hint": None,
                "budget_shape": {},
            },
        }

    monkeypatch.setattr("tender_radar.pricing.route_pricing_budget_documents_with_ai", fake_route)

    payload = reprocess_pricing_project_from_texts(
        db_path,
        eshidis_id="221567",
        use_ai_budget_router=True,
    )

    assert payload["ok"] is True
    assert payload["summary"]["ai_budget_router_fallback_to_full"] is True
    assert payload["summary"]["merged_budget_rows"] == 1
    assert payload["summary"]["merged_budget_amount_total"] == 200


def test_active_pricing_batch_records_every_candidate_outcome(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    calls: list[str] = []

    def fake_ingest(db_path_arg, *, eshidis_id, **kwargs):
        calls.append(eshidis_id)
        if eshidis_id == "221002":
            return {"ok": False, "summary": {"failed": 1, "merged_budget_rows": 0}, "project": {"title": "Bad"}}
        upsert_pricing_project(db_path_arg, eshidis_id=eshidis_id, title=f"Project {eshidis_id}")
        document_id = upsert_pricing_document(
            db_path_arg,
            eshidis_id=eshidis_id,
            document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
            text_path=str(tmp_path / f"{eshidis_id}.txt"),
            extraction_status="TEXT_EXTRACTED",
        )
        upsert_pricing_budget_rows(
            db_path_arg,
            eshidis_id=eshidis_id,
            document_id=document_id,
            source_document="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
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
                    amount=35.5,
                    raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10 3.55 35.5",
                    confidence=0.9,
                )
            ],
        )
        merged = consolidate_pricing_project_budget(db_path_arg, eshidis_id=eshidis_id)
        return {
            "ok": True,
            "summary": {
                "merged_budget_rows": merged["rows_merged"],
                "merged_budget_amount_validation": {"ok": True},
                "merged_budget_document_total_validation": {"ok": True},
                "failed": 0,
            },
            "project": {"title": f"Project {eshidis_id}"},
        }

    monkeypatch.setattr("tender_radar.pricing.ingest_pricing_eshidis_project", fake_ingest)

    events: list[dict[str, object]] = []
    payload = ingest_pricing_active_candidates(
        db_path,
        candidates_payload={
            "coverage": {"requested_limit": 3, "candidates_found": 3},
            "candidates": [
                {"eshidis_id": "221001", "submission_deadline": "21-07-2026 10:00:00"},
                {"eshidis_id": "221002", "submission_deadline": "22-07-2026 10:00:00"},
                {"eshidis_id": "221003", "submission_deadline": "23-07-2026 10:00:00"},
            ],
        },
        run_id="test-run",
        progress_callback=events.append,
    )

    assert payload["ok"] is False
    assert payload["status"] == "INCOMPLETE"
    assert payload["summary"]["candidate_count"] == 3
    assert payload["summary"]["completed"] == 2
    assert payload["summary"]["failed"] == 1
    assert [item["eshidis_id"] for item in payload["items"]] == ["221001", "221002", "221003"]
    assert [item["status"] for item in payload["items"]] == ["COMPLETED", "PARTIAL_OR_FAILED", "COMPLETED"]
    assert calls == ["221001", "221002", "221003"]
    assert events[0]["event"] == "active_ingest_start"
    done_events = [event for event in events if event["event"] == "active_candidate_done"]
    assert [event["eshidis_id"] for event in done_events] == ["221001", "221002", "221003"]
    assert [event["status"] for event in done_events] == ["COMPLETED", "PARTIAL_OR_FAILED", "COMPLETED"]
    assert events[-1]["event"] == "active_ingest_done"

    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT status, summary_json FROM pricing_runs WHERE run_id = ?", ("test-run",)).fetchone()
    finally:
        connection.close()
    assert row is not None
    assert row[0] == "INCOMPLETE"
    stored = json.loads(row[1])
    assert stored["candidate_count"] == 3
    assert len(stored["items"]) == 3


def test_active_pricing_batch_skips_already_complete_projects(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    upsert_pricing_project(db_path, eshidis_id="221001", title="Already done")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221001",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        text_path=str(tmp_path / "221001.txt"),
        extraction_status="TEXT_EXTRACTED",
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221001",
        document_id=document_id,
        source_document="__PROJECT_BUDGET_MERGED__",
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
                amount=35.5,
                raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10 3.55 35.5",
                confidence=0.9,
            )
        ],
    )
    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE pricing_projects SET metadata_json = ? WHERE eshidis_id = ?",
            (
                json.dumps(
                    {
                        "pricing_budget_audit": {
                            "amount_validation": {"ok": True},
                            "document_total_validation": {"ok": True},
                        }
                    }
                ),
                "221001",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    def fail_ingest(*args, **kwargs):
        raise AssertionError("already complete project must not be re-ingested")

    monkeypatch.setattr("tender_radar.pricing.ingest_pricing_eshidis_project", fail_ingest)

    payload = ingest_pricing_active_candidates(
        db_path,
        candidates_payload={"candidates": [{"eshidis_id": "221001", "submission_deadline": "21-07-2026 10:00:00"}]},
        run_id="skip-run",
    )

    assert payload["ok"] is True
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["skipped_existing"] == 1
    assert payload["items"][0]["status"] == "SKIPPED_ALREADY_COMPLETE"


def test_active_pricing_batch_marks_total_mismatch_as_partial(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"

    def fake_ingest(db_path_arg, *, eshidis_id, **kwargs):
        upsert_pricing_project(db_path_arg, eshidis_id=eshidis_id, title="Mismatch project")
        return {
            "ok": True,
            "summary": {
                "failed": 0,
                "merged_budget_rows": 1,
                "merged_budget_amount_total": 2.64,
                "merged_budget_amount_validation": {"ok": True},
                "merged_budget_document_total_validation": {
                    "ok": False,
                    "status": "MISMATCH",
                    "amount_total": 2.64,
                    "reference_total": 100,
                },
            },
            "project": {"title": "Mismatch project"},
        }

    monkeypatch.setattr("tender_radar.pricing.ingest_pricing_eshidis_project", fake_ingest)

    payload = ingest_pricing_active_candidates(
        db_path,
        candidates_payload={"candidates": [{"eshidis_id": "221155", "submission_deadline": "21-07-2026 10:00:00"}]},
        max_new_projects=1,
        run_id="mismatch-run",
    )

    assert payload["ok"] is False
    assert payload["status"] == "INCOMPLETE"
    assert payload["summary"]["completed"] == 0
    assert payload["summary"]["partial"] == 1
    assert payload["summary"]["failed"] == 0
    assert payload["items"][0]["status"] == "PARTIAL_OR_FAILED"


def test_active_pricing_batch_with_project_limit_is_incomplete(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"

    def fake_ingest(db_path_arg, *, eshidis_id, **kwargs):
        upsert_pricing_project(db_path_arg, eshidis_id=eshidis_id, title=f"Project {eshidis_id}")
        document_id = upsert_pricing_document(
            db_path_arg,
            eshidis_id=eshidis_id,
            document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
            text_path=str(tmp_path / f"{eshidis_id}.txt"),
            extraction_status="TEXT_EXTRACTED",
        )
        upsert_pricing_budget_rows(
            db_path_arg,
            eshidis_id=eshidis_id,
            document_id=document_id,
            source_document="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
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
                    amount=35.5,
                    raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10 3.55 35.5",
                    confidence=0.9,
                )
            ],
        )
        merged = consolidate_pricing_project_budget(db_path_arg, eshidis_id=eshidis_id)
        return {
            "ok": True,
            "summary": {
                "merged_budget_rows": merged["rows_merged"],
                "merged_budget_amount_validation": {"ok": True},
                "merged_budget_document_total_validation": {"ok": True},
            },
            "project": {},
        }

    monkeypatch.setattr("tender_radar.pricing.ingest_pricing_eshidis_project", fake_ingest)

    payload = ingest_pricing_active_candidates(
        db_path,
        candidates_payload={
            "candidates": [
                {"eshidis_id": "221001", "submission_deadline": "21-07-2026 10:00:00"},
                {"eshidis_id": "221002", "submission_deadline": "22-07-2026 10:00:00"},
                {"eshidis_id": "221003", "submission_deadline": "23-07-2026 10:00:00"},
            ],
        },
        project_limit=2,
        run_id="limited-run",
    )

    assert payload["ok"] is False
    assert payload["status"] == "INCOMPLETE"
    assert payload["summary"]["candidate_count"] == 3
    assert payload["summary"]["selected_count"] == 2
    assert payload["summary"]["not_selected_due_to_limit"] == 1
    assert payload["summary"]["remaining_unprocessed"] == 1
    assert [item["eshidis_id"] for item in payload["items"]] == ["221001", "221002"]


def test_active_pricing_batch_max_new_skips_existing_and_continues(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    upsert_pricing_project(db_path, eshidis_id="221001", title="Already done")
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id="221001",
        document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
        text_path=str(tmp_path / "221001.txt"),
        extraction_status="TEXT_EXTRACTED",
    )
    upsert_pricing_budget_rows(
        db_path,
        eshidis_id="221001",
        document_id=document_id,
        source_document="__PROJECT_BUDGET_MERGED__",
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
                amount=35.5,
                raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10 3.55 35.5",
                confidence=0.9,
            )
        ],
    )
    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE pricing_projects SET metadata_json = ? WHERE eshidis_id = ?",
            (
                json.dumps(
                    {
                        "pricing_budget_audit": {
                            "amount_validation": {"ok": True},
                            "document_total_validation": {"ok": True},
                        }
                    }
                ),
                "221001",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    calls: list[str] = []

    def fake_ingest(db_path_arg, *, eshidis_id, **kwargs):
        calls.append(eshidis_id)
        upsert_pricing_project(db_path_arg, eshidis_id=eshidis_id, title=f"Project {eshidis_id}")
        document_id = upsert_pricing_document(
            db_path_arg,
            eshidis_id=eshidis_id,
            document_name="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
            text_path=str(tmp_path / f"{eshidis_id}.txt"),
            extraction_status="TEXT_EXTRACTED",
        )
        upsert_pricing_budget_rows(
            db_path_arg,
            eshidis_id=eshidis_id,
            document_id=document_id,
            source_document="ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf",
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
                    amount=35.5,
                    raw_text="1 ΝΑΟΔΟ Α02 Γενικές εκσκαφές m3 10 3.55 35.5",
                    confidence=0.9,
                )
            ],
        )
        merged = consolidate_pricing_project_budget(db_path_arg, eshidis_id=eshidis_id)
        return {
            "ok": True,
            "summary": {
                "merged_budget_rows": merged["rows_merged"],
                "merged_budget_amount_validation": {"ok": True},
                "merged_budget_document_total_validation": {"ok": True},
            },
            "project": {},
        }

    monkeypatch.setattr("tender_radar.pricing.ingest_pricing_eshidis_project", fake_ingest)

    payload = ingest_pricing_active_candidates(
        db_path,
        candidates_payload={
            "candidates": [
                {"eshidis_id": "221001", "submission_deadline": "21-07-2026 10:00:00"},
                {"eshidis_id": "221002", "submission_deadline": "22-07-2026 10:00:00"},
                {"eshidis_id": "221003", "submission_deadline": "23-07-2026 10:00:00"},
                {"eshidis_id": "221004", "submission_deadline": "24-07-2026 10:00:00"},
            ],
        },
        max_new_projects=2,
        run_id="max-new-run",
    )

    assert payload["ok"] is True
    assert payload["status"] == "COMPLETED"
    assert calls == ["221002", "221003"]
    assert [item["status"] for item in payload["items"]] == [
        "SKIPPED_ALREADY_COMPLETE",
        "COMPLETED",
        "COMPLETED",
    ]
    assert payload["summary"]["candidate_count"] == 4
    assert payload["summary"]["inspected_count"] == 3
    assert payload["summary"]["attempted_new"] == 2
    assert payload["summary"]["skipped_existing"] == 1
    assert payload["summary"]["target_new_remaining"] == 0
    assert payload["summary"]["remaining_candidates_not_scanned_after_target"] == 1
