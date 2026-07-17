from tender_radar.db import SearchableDocument
from tender_radar.matching import SearchProfile, match_profile, render_search_markdown


def test_match_profile_finds_accent_insensitive_phrase() -> None:
    profile = SearchProfile(
        profile_id="test",
        name="Test",
        include_document_types={"technical_description"},
        exact_phrases=("τεχνική περιγραφή",),
        optional_terms=(),
        revision_codes=(),
        minimum_confidence=0.6,
    )
    document = SearchableDocument(
        tender_id=1,
        eshidis_id="221744",
        tender_title="Tender",
        document_id=10,
        attachment_id=20,
        document_type="technical_description",
        original_name="file.pdf",
        local_path="file.pdf",
        text_sample="ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ έργου",
        text_path=None,
    )

    matches = match_profile(profile, [document])

    assert len(matches) == 1
    assert matches[0].match_type == "exact_phrase"
    assert matches[0].confidence == 0.90


def test_render_search_markdown_includes_evidence() -> None:
    profile = SearchProfile("test", "Test", set(), ("foo",), (), (), 0.6)
    document = SearchableDocument(1, "221744", "Tender", 10, 20, "budget", "file.pdf", "file.pdf", "foo bar", None)
    matches = match_profile(profile, [document])

    markdown = render_search_markdown(profile, matches)

    assert "Search Report" in markdown
    assert "file.pdf" in markdown


def test_match_profile_uses_text_artifact_when_available(tmp_path) -> None:
    text_path = tmp_path / "doc.txt"
    text_path.write_text("κρυμμένη φράση πλήρους κειμένου", encoding="utf-8")
    profile = SearchProfile(
        profile_id="test",
        name="Test",
        include_document_types={"budget"},
        exact_phrases=("πλήρους κειμένου",),
        optional_terms=(),
        revision_codes=(),
        minimum_confidence=0.6,
    )
    document = SearchableDocument(
        1,
        "221744",
        "Tender",
        10,
        20,
        "budget",
        "file.pdf",
        "file.pdf",
        "sample without match",
        str(text_path),
    )

    matches = match_profile(profile, [document])

    assert len(matches) == 1


def test_match_profile_dedupes_overlapping_exact_phrases() -> None:
    profile = SearchProfile(
        profile_id="test",
        name="Test",
        include_document_types={"budget"},
        exact_phrases=("συντήρηση επαρχιακού οδικού δικτύου", "επαρχιακού οδικού δικτύου"),
        optional_terms=(),
        revision_codes=(),
        minimum_confidence=0.6,
    )
    document = SearchableDocument(
        1,
        "221744",
        "Tender",
        10,
        20,
        "budget",
        "file.pdf",
        "file.pdf",
        "ΕΡΓΟ: ΣΥΝΤΗΡΗΣΗ ΕΠΑΡΧΙΑΚΟΥ ΟΔΙΚΟΥ ΔΙΚΤΥΟΥ Δ.ΑΓΡΙΝΙΟΥ",
        None,
    )

    matches = match_profile(profile, [document])

    assert len(matches) == 1
    assert matches[0].term == "συντήρηση επαρχιακού οδικού δικτύου"
