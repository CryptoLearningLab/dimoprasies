from tender_radar.sources.eshidis_browser import (
    adf_response_metrics,
    parse_excel_export_candidates,
    parse_adf_response_candidates,
    parse_discovery_candidates,
    report_response_bodies,
    render_discovery_markdown,
)


def test_discovery_candidate_parser_extracts_visible_grid_row() -> None:
    snapshot = {
        "candidate_rows": [
            {
                "text": (
                    "Προβολή 221744 ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027 "
                    "ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΟΣ 15-07-2026 00:44:36 07-08-2026 10:00:00"
                ),
                "cells": [
                    "Προβολή",
                    "221744",
                    "ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027",
                    "ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΟΣ",
                    "15-07-2026 00:44:36",
                    "07-08-2026 10:00:00",
                ],
                "links": [{"id": "pc1:t1:0:cl1", "text": "Προβολή", "href": "#"}],
            }
        ]
    }

    candidates = parse_discovery_candidates(snapshot)

    assert len(candidates) == 1
    assert candidates[0].eshidis_id == "221744"
    assert candidates[0].status == "DISCOVERED_ACTIVE_CANDIDATE"
    assert candidates[0].submission_deadline == "07-08-2026 10:00:00"
    assert candidates[0].authority_name == "ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΟΣ"


def test_render_discovery_markdown_keeps_uncertain_status() -> None:
    report = {
        "target_url": "https://example.test/search",
        "status_filter": {"label": "ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ"},
        "candidate_status": "DISCOVERED_ACTIVE_CANDIDATE",
        "navigation_error": None,
        "coverage": {"visible_rows_seen": 1},
        "candidates": [
            {
                "eshidis_id": "221744",
                "status": "DISCOVERED_ACTIVE_CANDIDATE",
                "submission_deadline": "07-08-2026 10:00:00",
                "title": "ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ",
            }
        ],
    }

    markdown = render_discovery_markdown(report)

    assert "DISCOVERED_ACTIVE_CANDIDATE" in markdown
    assert "221744" in markdown


def test_adf_response_candidate_parser_extracts_hidden_grid_rows() -> None:
    body = """
    <partial-response><changes><update id="pc1:t1"><![CDATA[
    <table _rowCount="1"><tr role="row">
      <td id="pc1:t1:0:c2"><a href="#">221348</a></td>
      <td id="pc1:t1:0:c3">Διακήρυξη για την Αναβάθμιση εγκαταστάσεων ΕΡΤ στην Ορεστιάδα</td>
      <td id="pc1:t1:0:c5"><span>ΚΤΙΡΙΑΚΗ ΚΑΙ ΛΕΙΤΟΥΡΓΙΚΗ ΑΝΑΒΑΘΜΙΣΗ</span></td>
      <td id="pc1:t1:0:c13">Ιδία μέσα/ΕΡΤ Α.Ε.</td>
      <td id="pc1:t1:0:c11">1.200.000,00</td>
      <td id="pc1:t1:0:c9">15-07-2026 11:00:00</td>
      <td id="pc1:t1:0:c10">20-07-2026 10:00:00</td>
      <td id="pc1:t1:0:c1">05-08-2026 10:00:00</td>
    </tr></table>
    ]]></update></changes></partial-response>
    """

    candidates = parse_adf_response_candidates([{"body_sample": body}])

    assert len(candidates) == 1
    assert candidates[0].eshidis_id == "221348"
    assert candidates[0].title == "Διακήρυξη για την Αναβάθμιση εγκαταστάσεων ΕΡΤ στην Ορεστιάδα"
    assert candidates[0].submission_deadline == "05-08-2026 10:00:00"


def test_adf_response_candidate_parser_prefers_full_grid_body_over_sample() -> None:
    sample = '<partial-response><update id="pc1:t1"><![CDATA[<table _rowCount="2"></table>]]></update>'
    full_body = """
    <partial-response><changes><update id="pc1:t1"><![CDATA[
    <table _rowCount="2">
      <tr role="row">
        <td id="pc1:t1:0:c2"><a href="#">221111</a></td>
        <td id="pc1:t1:0:c3">Πρώτο έργο</td>
        <td id="pc1:t1:0:c1">01-08-2026 10:00:00</td>
      </tr>
      <tr role="row">
        <td id="pc1:t1:1:c2"><a href="#">221112</a></td>
        <td id="pc1:t1:1:c3">Δεύτερο έργο</td>
        <td id="pc1:t1:1:c1">02-08-2026 10:00:00</td>
      </tr>
    </table>
    ]]></update></changes></partial-response>
    """

    response_bodies = [{"body_sample": sample, "_body_text": full_body}]

    candidates = parse_adf_response_candidates(response_bodies, limit=10)
    metrics = adf_response_metrics(response_bodies)
    report_bodies = report_response_bodies(response_bodies)

    assert [candidate.eshidis_id for candidate in candidates] == ["221111", "221112"]
    assert metrics == {"declared_row_count": 2, "rows_parsed": 2}
    assert "_body_text" not in report_bodies[0]


def test_excel_export_candidate_parser_extracts_full_export_rows() -> None:
    export_html = """
    <html><body><table>
      <tr>
        <th>AA Συστήματος</th><th>Συνοπτικός Τίτλος/Αρ. Διακήρυξης</th>
        <th>Τίτλος Έργου/Μελέτη</th><th>Χρηματοδοτήσεις</th>
        <th>Συνολικός Προϋπολογισμός (με ΦΠΑ)</th><th>Ημερομηνία Δημοσίευσης</th>
        <th>Ημερομηνία Έναρξης Υποβολής Προσφορών</th>
        <th>Καταληκτική ημ/νία υποβολής προσφορών</th><th>Κωδικός CPV</th>
        <th>Περιγραφή CPV</th><th>Αναθέτουσα Αρχή</th>
      </tr>
      <tr>
        <td>221527</td><td>ΣΥΝΤΗΡΗΣΗ ΗΛΕΚΤΡΟΦΩΤΙΣΜΟΥ 2026</td>
        <td>ΣΥΝΤΗΡΗΣΗ ΗΛΕΚΤΡΟΦΩΤΙΣΜΟΥ 2026</td><td>Τακτικός Προϋπολογισμός</td>
        <td>300.000,00</td><td>14-07-2026 09:02:30</td><td>14-07-2026 09:02:30</td>
        <td>29-07-2026 10:00:00</td><td>45316110-9</td><td>Εγκατάσταση εξοπλισμού φωτισμού οδών</td>
        <td>ΔΗΜΟΣ ΚΗΦΙΣΙΑΣ, Δ/ΝΣΗ ΤΕΧΝΙΚΩΝ ΥΠΗΡΕΣΙΩΝ</td>
      </tr>
      <tr>
        <td>221622</td><td>ΑΝΑΚΑΙΝΙΣΗ ΚΤΙΡΙΟΥ ΑΡΣΗΣ ΒΑΡΩΝ</td>
        <td>ΑΝΑΚΑΙΝΙΣΗ ΚΤΙΡΙΟΥ ΑΡΣΗΣ ΒΑΡΩΝ «ΑΡΚΑΔΙ»</td><td>ΠΔΕ</td>
        <td>250.000,00</td><td>13-07-2026 14:00:00</td><td>13-07-2026 14:00:00</td>
        <td>29-07-2026 10:00:00</td><td>45212290-5</td><td>Επισκευή αθλητικών εγκαταστάσεων</td>
        <td>ΔΗΜΟΣ ΡΕΘΥΜΝΗΣ</td>
      </tr>
    </table></body></html>
    """

    candidates = parse_excel_export_candidates(export_html, limit=10)

    assert [candidate.eshidis_id for candidate in candidates] == ["221527", "221622"]
    assert candidates[0].title == "ΣΥΝΤΗΡΗΣΗ ΗΛΕΚΤΡΟΦΩΤΙΣΜΟΥ 2026"
    assert candidates[0].authority_name == "ΔΗΜΟΣ ΚΗΦΙΣΙΑΣ, Δ/ΝΣΗ ΤΕΧΝΙΚΩΝ ΥΠΗΡΕΣΙΩΝ"
    assert candidates[0].submission_deadline == "29-07-2026 10:00:00"
    assert candidates[0].status_confidence == 0.9
