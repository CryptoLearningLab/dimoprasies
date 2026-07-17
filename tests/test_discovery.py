from tender_radar.sources.eshidis_browser import (
    parse_adf_response_candidates,
    parse_discovery_candidates,
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
