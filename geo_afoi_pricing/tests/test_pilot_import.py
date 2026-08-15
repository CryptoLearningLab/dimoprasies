from pathlib import Path
import zipfile

from tender_radar.pricing import PricingBudgetRow

from geo_afoi_pricing.src.pilot_import import (
    ChapterCandidate,
    canonical_unit_key,
    chapter_for_line,
    classify_source_file,
    extract_declared_work_total,
    extract_chapter_candidates,
    extract_xlsx_text,
    init_database,
    description_hint_from_ocr,
    is_local_new_price_article,
    load_config,
    locate_row_line,
    looks_like_greek_font_mojibake,
    normalize_for_match,
    normalize_revision_number,
    parse_fixed_column_ypehode_rows,
    parse_budget_rows_from_word_text,
    parse_budget_rows_from_xlsx,
    project_key,
    repair_mojibake_chapter_title,
    repair_mojibake_code_tokens,
    resolve_article_identity,
)


def test_classify_budget_pdf_from_config_terms() -> None:
    config = load_config()
    result = classify_source_file(Path("1. ΕΝΤΥΠΑ/3.-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf"), config)
    assert result.role == "BUDGET_CANDIDATE"
    assert result.score > 100


def test_classify_financial_offer_is_excluded() -> None:
    config = load_config()
    result = classify_source_file(Path("1. ΠΡΟΣΦΟΡΑ/ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΣΦΟΡΑ.pdf"), config)
    assert result.role == "OFFER_EXCLUDED"
    assert result.ignored is True


def test_extract_chapter_candidates_from_budget_headings() -> None:
    text = """
    ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΜΕΛΕΤΗΣ
    1. ΧΩΜΑΤΟΥΡΓΙΚΑ
    1 ΝΑΟΔΟ Α02 Εκσκαφές ΟΔΟ-1123Α m3 100,00 3,55 355,00
    ΟΜΑΔΑ Β : ΤΕΧΝΙΚΑ ΕΡΓΑ
    2 ΝΑΟΔΟ Β29 Σκυρόδεμα ΟΔΟ-2532 m3 10,00 94,00 940,00
    ΣΥΝΟΛΟ 1.295,00
    """
    chapters = extract_chapter_candidates(text)
    assert [chapter.chapter_title for chapter in chapters] == ["ΧΩΜΑΤΟΥΡΓΙΚΑ", "ΤΕΧΝΙΚΑ ΕΡΓΑ"]


def test_chapter_for_line_uses_nearest_previous_heading() -> None:
    chapters = [
        ChapterCandidate(2, "1", "ΧΩΜΑΤΟΥΡΓΙΚΑ", 0.75),
        ChapterCandidate(10, "Β", "ΤΕΧΝΙΚΑ", 0.75),
    ]
    assert chapter_for_line(chapters, 3).chapter_title == "ΧΩΜΑΤΟΥΡΓΙΚΑ"
    assert chapter_for_line(chapters, 12).chapter_title == "ΤΕΧΝΙΚΑ"
    assert chapter_for_line(chapters, 1) is None


def test_project_key_is_stable_for_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    project = root / "2. ΕΡΓΟ"
    project.mkdir(parents=True)
    assert project_key(root, project) == project_key(root, project)
    assert project_key(root, project).startswith("geo-")


def test_normalize_for_match_removes_accents_and_spacing() -> None:
    assert normalize_for_match("  ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ   ") == "προυπολογισμος"


def test_canonical_unit_key_normalizes_common_pdf_and_spreadsheet_variants() -> None:
    assert canonical_unit_key("μ") == "m"
    assert canonical_unit_key("μμ") == "m"
    assert canonical_unit_key("Μ2") == "m2"
    assert canonical_unit_key("μ3") == "m3"
    assert canonical_unit_key("Kgr") == "kg"
    assert canonical_unit_key("Kg") == "kg"
    assert canonical_unit_key("τεμ.") == "τεμ"
    assert canonical_unit_key("Τεμ.") == "τεμ"
    assert canonical_unit_key("tonx1") == "ton"


def test_normalize_revision_number_repairs_latin_letters_and_dot_separators() -> None:
    assert normalize_revision_number("1123.A") == "1123Α"
    assert normalize_revision_number("4421.Β.1") == "4421Β.1"
    assert normalize_revision_number("2269A") == "2269Α"


def test_detects_greek_font_mojibake_text_layer() -> None:
    text = "ΠΡΟΫΠΟΛΟΓΘ΢ΜΟ΢ ΜΕΛΕΣΗ΢ ΝΑΟΓΟ ΟΓΟΝ ΣΕΥΝΘΚΑ ΥΩΜΑΣΟΤΡΓΘΚΑ"
    assert looks_like_greek_font_mojibake(text) is True


def test_repairs_mojibake_code_tokens_conservatively() -> None:
    assert repair_mojibake_code_tokens("ΝΑΟΓΟ Α02 ΟΓΟΝ 1123.Α") == "ΝΑΟΔΟ Α02 ΟΔΟΝ 1123.Α"
    assert repair_mojibake_code_tokens("ΝΑΤΓΡ ΤΓΡ 6551.7") == "ΝΑΥΔΡ ΥΔΡ 6551.7"


def test_repairs_mojibake_chapter_titles() -> None:
    assert repair_mojibake_chapter_title("ΥΩΜΑΣΟΤΡΓΘΚΑ-ΚΑΘΑΘΡΕ΢ΕΘ΢") == "ΧΩΜΑΤΟΥΡΓΙΚΑ-ΚΑΘΑΙΡΕΣΕΙΣ"
    assert repair_mojibake_chapter_title("ΣΕΥΝΘΚΑ ΕΡΓΑ") == "ΤΕΧΝΙΚΑ ΕΡΓΑ"


def test_resolve_article_identity_prepends_repaired_article_prefix() -> None:
    row = PricingBudgetRow(
        row_number=1,
        article_code="Α02",
        canonical_article_code="Α02",
        description="Γεληθέο Δθζθαθέο ζε έδαθνο ΝΑΟΓΟ",
        revision_codes=[],
        unit="m3",
        quantity=3000,
        unit_price=2.8,
        amount=8400,
        raw_text="1 Γεληθέο Δθζθαθέο ζε έδαθνο ΝΑΟΓΟ Α02 ΟΓΟΝ 1123.Α 1 m3 3.000,00 2,80 8.400,00",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(2, "1", "ΧΩΜΑΤΟΥΡΓΙΚΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.usable_for_stats is True
    assert resolution.repaired_article_code == "ΝΑΟΔΟ Α02"
    assert resolution.repaired_canonical_article_code == "ΝΑΟΔΟΑ02"
    assert resolution.repaired_revision_codes == ["ΟΔΟ-1123Α"]
    assert resolution.identity_key == "ΝΑΟΔΟΑ02|m3"


def test_resolve_article_identity_normalizes_hyphenated_spreadsheet_article() -> None:
    row = PricingBudgetRow(
        row_number=1,
        article_code="Α-2",
        canonical_article_code="Α2",
        description="Γενικές Εκσκαφές",
        revision_codes=[],
        unit="m3",
        quantity=1000,
        unit_price=1.08,
        amount=1080,
        raw_text="1 Γενικές Εκσκαφές Α-2 ΝΟΔΟ 1123.Α 1 m3 1000 1.08 1080",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(5, "1", "ΧΩΜΑΤΟΥΡΓΙΚΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΟΔΟ Α02"
    assert resolution.repaired_canonical_article_code == "ΝΑΟΔΟΑ02"
    assert resolution.repaired_revision_codes == ["ΟΔΟ-1123Α"]


def test_resolve_article_identity_drops_trailing_dot_from_single_digit_article() -> None:
    row = PricingBudgetRow(
        row_number=1,
        article_code="Α-2.",
        canonical_article_code="Α2.",
        description="Γενικές Εκσκαφές",
        revision_codes=[],
        unit="μ3",
        quantity=1000,
        unit_price=1.08,
        amount=1080,
        raw_text="Α-2. ΟΔΟ-1123Α μ3 1000 1.08 1080",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(5, "1", "ΧΩΜΑΤΟΥΡΓΙΚΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΟΔΟ Α02"
    assert resolution.repaired_revision_codes == ["ΟΔΟ-1123Α"]
    assert resolution.canonical_unit == "m3"
    assert resolution.identity_key == "ΝΑΟΔΟΑ02|m3"


def test_resolve_article_identity_promotes_bare_green_article_with_prs_revision() -> None:
    row = PricingBudgetRow(
        row_number=32,
        article_code="Ε.2.2",
        canonical_article_code="Ε.2.2",
        description="Εκσκαφή λάκκων διαστάσεων 0,50*0,50*0,50",
        revision_codes=["ΠΡΣ-5210"],
        unit="τεμ",
        quantity=24,
        unit_price=1.5,
        amount=36,
        raw_text="Ε.2.2 ΠΡΣ-5210 τεμ 24 1.5 36",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(50, "3", "ΠΡΑΣΙΝΟΥ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΠΡΣ Ε02.2"
    assert resolution.repaired_revision_codes == ["ΠΡΣ-5210"]
    assert resolution.identity_key == "ΝΑΠΡΣΕ02.2|τεμ"


def test_resolve_article_identity_keeps_two_digit_article_suffix() -> None:
    row = PricingBudgetRow(
        row_number=14,
        article_code="Α-14",
        canonical_article_code="Α14",
        description="Καθαρισμός τάφρου",
        revision_codes=[],
        unit="m",
        quantity=10,
        unit_price=0.65,
        amount=6.5,
        raw_text="7 Καθαρισμός τάφρου Α-14 ΝΟΔΟ 1310 14 m 10 0.65 6.5",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(5, "1", "ΧΩΜΑΤΟΥΡΓΙΚΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΟΔΟ Α14"
    assert resolution.repaired_canonical_article_code == "ΝΑΟΔΟΑ14"


def test_reviewed_misread_asphalt_article_alias_maps_gamma_three_to_delta_three() -> None:
    row = PricingBudgetRow(
        row_number=1,
        article_code="Γ03",
        canonical_article_code="Γ03",
        description="Αζθαιηηθή πξνεπάιεηςε ΝΑΟΓΟ",
        revision_codes=[],
        unit="m2",
        quantity=3600,
        unit_price=1.2,
        amount=4320,
        raw_text="1 Αζθαιηηθή πξνεπάιεηςε ΝΑΟΓΟ Γ03 ΟΓΟΝ 4110 25 m2 3.600,00 1,20 4.320,00",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(50, "3", "ΑΣΦΑΛΤΙΚΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΟΔΟ Δ03"
    assert resolution.repaired_revision_codes == ["ΟΔΟ-4110"]
    assert resolution.identity_key == "ΝΑΟΔΟΔ03|m2"
    assert resolution.method == "reviewed_misread_article_alias"


def test_reviewed_misread_asphalt_article_alias_does_not_touch_drainage_gamma_three() -> None:
    row = PricingBudgetRow(
        row_number=37,
        article_code="Γ-3",
        canonical_article_code="Γ3",
        description="Στρώση στράγγισης οδοστρώματος",
        revision_codes=[],
        unit="m3",
        quantity=400,
        unit_price=20.45,
        amount=8180,
        raw_text="3 Στρώση στράγγισης οδοστρώματος Γ-3 ΝΟΔΟ 3121Β 37 m3 400 20.45 8180",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(50, "3", "ΟΔΟΣΤΡΩΣΙΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΟΔΟ Γ03"
    assert resolution.repaired_revision_codes == ["ΟΔΟ-3121Β"]
    assert resolution.identity_key == "ΝΑΟΔΟΓ03|m3"


def test_resolve_article_identity_handles_road_e_group_and_hlm_articles() -> None:
    road_row = PricingBudgetRow(
        row_number=48,
        article_code="Ε-6",
        canonical_article_code="Ε6",
        description="Πλαστικός οριοδείκτης οδού",
        revision_codes=["ΥΔΡ 6620.1"],
        unit="τεμ.",
        quantity=10,
        unit_price=11.5,
        amount=115,
        raw_text="6 Πλαστικός οριοδείκτης οδού Ε-6 ΥΔΡ 6620.1 48 τεμ. 10 11.5 115",
        confidence=0.9,
    )
    hlm_row = PricingBudgetRow(
        row_number=57,
        article_code="ΗΛΜ 60.10.01.04",
        canonical_article_code="ΗΛΜ60.10.01.04",
        description="Χαλύβδινος ιστός οδοφωτισμού",
        revision_codes=["ΗΛΜ 101"],
        unit="τεμ",
        quantity=14,
        unit_price=1400,
        amount=19600,
        raw_text="1 Χαλύβδινος ιστός οδοφωτισμού ΗΛΜ 60.10.01.04 ΗΛΜ 101 57 τεμ 14 1400 19600",
        confidence=0.9,
    )

    road = resolve_article_identity(road_row, chapter=ChapterCandidate(5, "5", "ΣΗΜΑΝΣΗ", 0.75))
    hlm = resolve_article_identity(hlm_row, chapter=ChapterCandidate(5, "6", "ΟΔΟΦΩΤΙΣΜΟΣ", 0.75))

    assert road.article_quality_status == "READY"
    assert road.repaired_article_code == "ΝΑΟΔΟ Ε06"
    assert road.repaired_revision_codes == ["ΥΔΡ-6620.1"]
    assert hlm.article_quality_status == "READY"
    assert hlm.repaired_article_code == "ΗΛΜ 60.10.01.04"
    assert hlm.repaired_revision_codes == ["ΗΛΜ-101"]


def test_local_new_price_uses_description_revision_unit_identity() -> None:
    assert is_local_new_price_article("N.T.3") is True
    assert is_local_new_price_article("Ν.Τ.3") is True
    row = PricingBudgetRow(
        row_number=72,
        article_code="Ν.Τ.3",
        canonical_article_code="Ν.Τ.3",
        description="Κοπή και απομάκρυνση χόρτων, θάμνων σε δρόμους",
        revision_codes=["ΠΡΣ 5371"],
        unit="m",
        quantity=1000,
        unit_price=1.5,
        amount=1500,
        raw_text="12 Κοπή και απομάκρυνση χόρτων Ν.Τ.3 ΠΡΣ 5371 72 m 1000 1.5 1500",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(5, "7", "ΠΡΑΣΙΝΟ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.usable_for_stats is True
    assert resolution.identity_key is not None
    assert resolution.identity_key.startswith("LOCAL_NT|ΠΡΣ-5371|m|")
    assert resolution.repaired_canonical_article_code.startswith("LOCAL_NT_")
    assert resolution.repaired_revision_codes == ["ΠΡΣ-5371"]


def test_zero_amount_local_new_price_is_ready_but_excluded_from_stats() -> None:
    row = PricingBudgetRow(
        row_number=55,
        article_code="N.T.1",
        canonical_article_code="N.T.1",
        description="Τοποθέτηση Πινακίδων Στο Εθνικό Και Επαρχιακό Δίκτυο",
        revision_codes=["ΟΙΚ-6541"],
        unit="τεμ.",
        quantity=0,
        unit_price=35,
        amount=0,
        raw_text="12 Τοποθέτηση Πινακίδων N.T.1 ΟΙΚ-6541 55 τεμ. 0 35 0",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(5, "5", "ΣΗΜΑΝΣΗ", 0.75))

    assert resolution.article_quality_status == "READY_ZERO_AMOUNT"
    assert resolution.usable_for_stats is False
    assert resolution.identity_key is not None
    assert resolution.identity_key.startswith("LOCAL_NT|ΟΙΚ-6541|τεμ|")
    assert resolution.canonical_unit == "τεμ"


def test_reviewed_numeric_oik_aliases_resolve_to_naoik_articles() -> None:
    rows = [
        PricingBudgetRow(
            row_number=32,
            article_code="77.10",
            canonical_article_code="77.10",
            description="Υδροχρωματισμοί επιφανειών σκυροδέματος ή τσιμεντοκονιάματος με ακρυλικό υδατοδιαλυτό τσιμεντόχρωμα",
            revision_codes=["ΟΙΚ-7725"],
            unit="m2",
            quantity=100,
            unit_price=3.9,
            amount=390,
            raw_text="Υδροχρωματισμοί επιφανειών σκυροδέματος ή τσιμεντοκονιάματος 77.10 ΟΙΚ 7725 m2 100 3.9 390",
            confidence=0.9,
        ),
        PricingBudgetRow(
            row_number=33,
            article_code="77.30",
            canonical_article_code="77.30",
            description="Υπόστρωμα (αστάρι) τσιμεντοχρωμάτων από ακρυλικές ρητίνες βάσεως διαλύτου",
            revision_codes=["ΟΙΚ-7735"],
            unit="m2",
            quantity=100,
            unit_price=2.25,
            amount=225,
            raw_text="Υπόστρωμα αστάρι τσιμεντοχρωμάτων 77.30 ΟΙΚ 7735 m2 100 2.25 225",
            confidence=0.9,
        ),
    ]

    resolutions = [resolve_article_identity(row, chapter=ChapterCandidate(5, "4", "ΧΡΩΜΑΤΙΣΜΟΙ", 0.75)) for row in rows]

    assert [resolution.article_quality_status for resolution in resolutions] == ["READY", "READY"]
    assert [resolution.repaired_article_code for resolution in resolutions] == ["ΝΑΟΙΚ 77.10", "ΝΑΟΙΚ 77.30"]
    assert [resolution.identity_key for resolution in resolutions] == ["ΝΑΟΙΚ77.10|m2", "ΝΑΟΙΚ77.30|m2"]
    assert [resolution.method for resolution in resolutions] == ["reviewed_numeric_oik_alias", "reviewed_numeric_oik_alias"]


def test_unreviewed_numeric_oik_variant_stays_needs_review() -> None:
    row = PricingBudgetRow(
        row_number=34,
        article_code="77.34Ν",
        canonical_article_code="77.34Ν",
        description="Υδροαμμοβολή επιφανειών",
        revision_codes=["ΟΙΚ-7740"],
        unit="m2",
        quantity=100,
        unit_price=15,
        amount=1500,
        raw_text="Υδροαμμοβολή επιφανειών 77.34Ν ΟΙΚ 7740 m2 100 15 1500",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(5, "4", "ΧΡΩΜΑΤΙΣΜΟΙ", 0.75))

    assert resolution.article_quality_status == "NEEDS_REVIEW"
    assert resolution.repaired_article_code == "77.34Ν"
    assert resolution.identity_key is None


def test_resolve_article_identity_repairs_hydraulic_wrapped_article() -> None:
    row = PricingBudgetRow(
        row_number=8,
        article_code="ΤΓΡ 12.01.01.07",
        canonical_article_code="ΤΓΡ12.01.01.07",
        description="Πξνκήζεηα, κεηαθνξά ζηε ζέζε ΝΑΤΓΡ",
        revision_codes=[],
        unit="m",
        quantity=75,
        unit_price=144,
        amount=10800,
        raw_text="8 Πξνκήζεηα, κεηαθνξά ζηε ζέζε ΝΑΤΓΡ ΤΓΡ 6551.7 16 m 75,00 144,00 10.800,00",
        confidence=0.9,
    )

    resolution = resolve_article_identity(row, chapter=ChapterCandidate(80, "2", "ΣΕΥΝΘΚΑ ΕΡΓΑ", 0.75))

    assert resolution.article_quality_status == "READY"
    assert resolution.repaired_article_code == "ΝΑΥΔΡ 12.01.01.07"
    assert resolution.repaired_canonical_article_code == "ΝΑΥΔΡ12.01.01.07"
    assert resolution.repaired_revision_codes == ["ΥΔΡ-6551.7"]
    assert resolution.canonical_chapter_title == "ΤΕΧΝΙΚΑ ΕΡΓΑ"


def test_description_hint_skips_ocr_lines_containing_header_blocks() -> None:
    row = PricingBudgetRow(
        row_number=1,
        article_code="Α02",
        canonical_article_code="Α02",
        description="",
        revision_codes=[],
        unit="m3",
        quantity=3000,
        unit_price=2.8,
        amount=8400,
        raw_text="",
        confidence=0.9,
    )
    ocr = (
        "ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ ΔΗΜΟΣ: ΘΕΡΜΟΥ ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΜΕΛΕΤΗΣ "
        + "κεφαλίδα " * 50
        + "1 Γενικές Εκσκαφές ΝΑΟΔΟ A02 ΟΔΟΝ 1123.A 1 m3 3.000,00 2,80 8.400,00"
    )

    assert description_hint_from_ocr(ocr, row) is None


def test_extract_xlsx_text_reads_shared_strings_and_numbers(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "budget.xlsx"
    shared_strings = """<?xml version="1.0" encoding="UTF-8"?>
    <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <si><t>ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ</t></si>
      <si><t>Γενικές Εκσκαφές</t></si>
      <si><t>Α-2</t></si>
      <si><t>ΝΟΔΟ 1123.Α</t></si>
      <si><t>m3</t></si>
    </sst>
    """
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row><c t="s"><v>0</v></c></row>
        <row>
          <c><v>1</v></c><c t="s"><v>1</v></c><c t="s"><v>2</v></c>
          <c t="s"><v>3</v></c><c><v>1</v></c><c t="s"><v>4</v></c>
          <c><v>1000</v></c><c><v>1.08</v></c><c><v>1080</v></c>
        </row>
      </sheetData>
    </worksheet>
    """
    with zipfile.ZipFile(xlsx_path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    text = extract_xlsx_text(xlsx_path)

    assert "ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ" in text
    assert "1 Γενικές Εκσκαφές Α-2 ΝΟΔΟ 1123.Α 1 m3 1000 1.08 1080" in text
    rows = parse_budget_rows_from_xlsx(xlsx_path)
    assert len(rows) == 1
    assert rows[0].row_number == 1
    assert rows[0].article_code == "Α-2"
    assert rows[0].revision_codes == ["ΝΟΔΟ 1123.Α"]
    assert rows[0].quantity == 1000
    assert rows[0].unit_price == 1.08
    assert rows[0].amount == 1080


def test_parse_word_budget_block_layout_handles_split_price_expression() -> None:
    text = """
    1
    Γενικές εκσκαφές σε έδαφος γαιώδες -ημιβραχώδες.
    ΝΕΤ ΟΔΟ-ΜΕ  Α-2
    001
    ΟΔΟ 1123.Α 100,00%
    m3
    540
    3,1 *
    (0,7+2,4)
    1.674,00

    16
    Επισκευή φθορών και επούλωση λάκκων ασφαλτικού οδοστρώματος με την χρήση θερμού ασφαλτικού μίγματος.
    ΝΕΟ  N/4720.A.2.1
    016
    m3
    29,03
    260,94
    7.575,09
    """

    rows = parse_budget_rows_from_word_text(text)

    assert len(rows) == 2
    assert rows[0].row_number == 1
    assert rows[0].article_code == "ΝΕΤ ΟΔΟ-ΜΕ Α-2"
    assert rows[0].revision_codes == ["ΟΔΟ-1123Α"]
    assert rows[0].unit == "m3"
    assert rows[0].quantity == 540
    assert rows[0].unit_price == 3.1
    assert rows[0].amount == 1674
    assert rows[1].row_number == 16
    assert rows[1].article_code == "ΝΕΟ N/4720.A.2.1"
    assert rows[1].revision_codes == []
    assert rows[1].amount == 7575.09


def test_parse_fixed_column_ypehode_rows_handles_group_total_lines() -> None:
    text = """
    1.2 ΠΙΝΑΚΑΣ ΤΙΜΩΝ ΜΟΝΑΔΟΣ ΕΡΓΑΣΙΩΝ ΕΡΓΩΝ ΟΔΟΠΟΙΙΑΣ
          Επενδυση πρανών με ΟΔΟ-
    10 Α-24.1 φυτική γή          1610                μ2         200      0,65      130,00         10.359,00
                 Ασφαλτική
                 ισοπεδωτική στρώση  ΟΔΟ
    21      Δ6       μεταβλητού πάχους  4421Β ton                190     81,18   15.424,20         43.841,70
           Στηθαία ασφαλείας
           ικανότητας
           συγκράτισης N2
           λειτουργικού πλάτους          ΟΔΟ
    27 Ε.1.1.1 w7                            2653     μ           70     35,00    2.450,00          4.520,00
          Χυτοσιδηρά καλύματα
          φρεατίων -εσχάρες              ΥΔΡ-
    Β-49 υπονόμων                        6752    kgr        400      1,65      660,00
                 Κοπή και
                 απομάκρινση χόρτων
                 μηχανίματα και           ΠΡΣ
    29      Ν.Τ      εργάτες                  5371    στρ           3    400,00      1.200,00
                 Εκσκαφή λάκκων
                 διαστάσεων               ΠΡΣ
    32     Ε.2.2     0,50*0,50*0,50           5210    τεμ          24      1,50        36,00         1.305,60
    """

    rows = parse_fixed_column_ypehode_rows(text)

    assert [row.row_number for row in rows] == [10, 21, 27, 28, 29, 32]
    assert [row.article_code for row in rows] == ["Α-24.1", "Δ6", "Ε.1.1.1", "Β-49", "Ν.Τ", "Ε.2.2"]
    assert [row.revision_codes for row in rows] == [
        ["ΟΔΟ-1610"],
        ["ΟΔΟ-4421Β"],
        ["ΟΔΟ-2653"],
        ["ΥΔΡ-6752"],
        ["ΠΡΣ-5371"],
        ["ΠΡΣ-5210"],
    ]
    assert [row.amount for row in rows] == [130, 15424.2, 2450, 660, 1200, 36]


def test_extract_declared_work_total_from_ocr_text() -> None:
    text = "Σύνολο : 4. ΑΣΦΑΛΤΙΚΑ 55.980,00 Άθροισμα 444.207,70 Προστίθεται ΓΕ"
    assert extract_declared_work_total(text) == 444207.70


def test_extract_declared_work_total_from_word_summary_block() -> None:
    text = """
    Εργασίες Προϋπολογισμού

    173.942,11
    Γ.Ε & Ο.Ε (%)
    """
    assert extract_declared_work_total(text) == 173942.11


def test_locate_row_line_handles_article_suffix_on_next_line() -> None:
    text = """
    2. ΤΕΧΝΙΚΑ ΕΡΓΑ
      8 Προμήθεια, μεταφορά στη θέση ΝΑΥΔΡ ΥΔΡ 6551.7 16 m 75,00 144,00 10.800,00
        εγκατάστασης, και τοποθέτηση 12.01.01.07
    """
    row = PricingBudgetRow(
        row_number=16,
        article_code="ΝΑΥΔΡ 12.01.01.07",
        canonical_article_code="ΝΑΥΔΡ12.01.01.07",
        description="Προμήθεια",
        revision_codes=[],
        unit="m",
        quantity=75,
        unit_price=144,
        amount=10800,
        raw_text="",
        confidence=0.9,
    )

    assert locate_row_line(text, row) == 3


def test_init_database_creates_article_identity_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "geo.sqlite"
    init_database(db_path)

    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        row_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(geo_budget_rows)").fetchall()
        }
    finally:
        connection.close()

    assert "geo_article_identities" in tables
    assert "geo_article_aliases" in tables
    assert "article_identity_id" in row_columns
    assert "repaired_canonical_article_code" in row_columns
    assert "usable_for_stats" in row_columns
