from unittest.mock import patch

from tender_radar.sources.authority import discover_authority_candidates
from tender_radar.sources.expanded_report import build_expanded_report


class Response:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.text.encode("utf-8")


def test_drupal_authority_listing_extracts_detail_attachments_and_kimdis_id() -> None:
    listing = """
    <article class="block">
      <h2><a href="/el/test-tender">Πρόσκληση για υποβολή προσφοράς</a></h2>
      <time datetime="2026-07-07T10:00:00+03:00">07/07/2026</time>
    </article>
    """
    detail = """
    <main>
      <p>Αφορά το ΚΗΜΔΗΣ 26PROC019350955 και τον Δήμο Πατρέων.</p>
      <a href="/sites/default/files/2026-07/prosklisi.pdf">PDF</a>
    </main>
    """
    config = {
        "authority_adapters": [
            {
                "id": "epatras_tenders",
                "name": "Δήμος Πατρέων - Διαγωνισμοί",
                "scope_id": "patras",
                "scope_name": "Δήμος Πατρέων",
                "source_family": "municipal_html",
                "adapter": "drupal_listing",
                "url": "https://e-patras.gr/el/tenders",
            }
        ]
    }

    def fake_urlopen(request, **kwargs):
        url = request.full_url
        return Response(detail if url.endswith("/el/test-tender") else listing)

    with patch("tender_radar.sources.authority.urlopen", side_effect=fake_urlopen):
        candidates, errors, pages = discover_authority_candidates(config)

    assert not errors
    assert pages[0]["items_returned"] == 1
    assert candidates[0].official_id == "26PROC019350955"
    assert candidates[0].record_type == "PROC"
    assert candidates[0].attachment_url == "https://e-patras.gr/sites/default/files/2026-07/prosklisi.pdf"
    assert candidates[0].status == "AUTHORITY_DISCOVERY_CANDIDATE"


def test_authority_reference_detection_handles_dotted_eshidis() -> None:
    listing = """
    <article class="block">
      <h2><a href="/el/test-tender">Διακήρυξη έργου</a></h2>
    </article>
    """
    detail = """
    <p>του ΟΠΣ Ε.Σ.Η.Δ.Η.Σ Α/Α:207024 URL: http://pwgopendata.eprocurement.gov.gr</p>
    """
    config = {
        "authority_adapters": [
            {
                "id": "source",
                "name": "Source",
                "scope_id": "scope",
                "scope_name": "Scope",
                "adapter": "drupal_listing",
                "url": "https://example.test/list",
            }
        ]
    }

    def fake_urlopen(request, **kwargs):
        return Response(detail if request.full_url.endswith("/el/test-tender") else listing)

    with patch("tender_radar.sources.authority.urlopen", side_effect=fake_urlopen):
        candidates, _, _ = discover_authority_candidates(config)

    assert candidates[0].official_id == "207024"
    assert candidates[0].record_type == "ESHIDIS"


def test_expanded_report_includes_authority_candidates(tmp_path) -> None:
    config_path = tmp_path / "sources.yml"
    config_path.write_text(
        """
version: 1
global_sources: []
collection_order: []
rules: []
scopes:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα"]
    sources: []
authority_adapters:
  - id: epatras_tenders
    name: "Δήμος Πατρέων - Διαγωνισμοί"
    scope_id: patras
    scope_name: "Δήμος Πατρέων"
    adapter: drupal_listing
    url: "https://e-patras.gr/el/tenders"
""",
        encoding="utf-8",
    )
    listing = """
    <article><h2><a href="/el/tender">Έργο στην Πάτρα</a></h2></article>
    """
    detail = "<p>ΟΠΣ ΕΣΗΔΗΣ Α/Α 221365</p>"

    def fake_urlopen(request, **kwargs):
        return Response(detail if request.full_url.endswith("/el/tender") else listing)

    with patch("tender_radar.sources.authority.urlopen", side_effect=fake_urlopen):
        report = build_expanded_report(
            sources_config_path=config_path,
            eshidis_candidates_path=None,
            kimdis_pages=0,
            authority_limit_per_source=10,
        )

    assert report["summary"]["authority_candidates"] == 1
    assert report["summary"]["focus_authority_candidates"] == 1
    assert report["focus_authority_candidates"][0]["official_id"] == "221365"
    assert report["deduplication"]["title_only_merge"] is False
