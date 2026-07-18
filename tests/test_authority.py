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


def test_html_listing_skips_public_authority_landing_pages() -> None:
    listing = """
    <div class="premium-blog-post-outer-container">
      <h2><a href="/el/erga-drasis/">Έργα & Δράσεις</a></h2>
    </div>
    <div class="premium-blog-post-outer-container">
      <h2><a href="/el/prokirikseis/24844/">Διακήρυξη έργου</a></h2>
    </div>
    """
    detail = "<p>ΚΗΜΔΗΣ 26PROC019417347</p>"
    config = {
        "authority_adapters": [
            {
                "id": "pde_prokirikseis",
                "name": "Περιφέρεια Δυτικής Ελλάδας - Προκηρύξεις",
                "scope_id": "aitoloakarnania",
                "scope_name": "Περιφέρεια Δυτικής Ελλάδας / Π.Ε. Αιτωλοακαρνανίας",
                "adapter": "html_listing",
                "url": "https://pde.gov.gr/el/diafaneia/prokirikseis/",
            }
        ]
    }

    def fake_urlopen(request, **kwargs):
        return Response(detail if request.full_url.endswith("/el/prokirikseis/24844/") else listing)

    with patch("tender_radar.sources.authority.urlopen", side_effect=fake_urlopen):
        candidates, errors, pages = discover_authority_candidates(config)

    assert not errors
    assert pages[0]["items_returned"] == 1
    assert candidates[0].title == "Διακήρυξη έργου"
    assert candidates[0].official_id == "26PROC019417347"


def test_wordpress_category_extracts_attachment_links() -> None:
    config = {
        "authority_adapters": [
            {
                "id": "wp",
                "name": "WP",
                "scope_id": "scope",
                "scope_name": "Scope",
                "adapter": "wordpress_category",
                "url": "https://example.test/wp-json/wp/v2/posts",
                "query_params": {"categories": 18, "per_page": 2},
            }
        ]
    }
    payload = """
    [
      {
        "date": "2026-07-18T10:00:00",
        "link": "https://example.test/post",
        "title": {"rendered": "Διακήρυξη έργου"},
        "excerpt": {"rendered": "Περίληψη"},
        "content": {"rendered": "<p>ΚΗΜΔΗΣ 26PROC019417347</p><a href='/files/diakiryxi.pdf'>PDF</a>"}
      }
    ]
    """

    with patch("tender_radar.sources.authority.urlopen", return_value=Response(payload)):
        candidates, errors, pages = discover_authority_candidates(config)

    assert not errors
    assert pages[0]["items_returned"] == 1
    assert candidates[0].official_id == "26PROC019417347"
    assert candidates[0].attachment_urls == ["https://example.test/files/diakiryxi.pdf"]


def test_wordpress_page_table_extracts_table_rows() -> None:
    config = {
        "authority_adapters": [
            {
                "id": "table",
                "name": "Table",
                "scope_id": "scope",
                "scope_name": "Scope",
                "adapter": "wordpress_page_table",
                "url": "https://example.test/wp-json/wp/v2/pages",
                "query_params": {"slug": "diagonismoi-2"},
            }
        ]
    }
    payload = """
    [
      {
        "content": {
          "rendered": "<table><tr><td><a href='/detail'>Έργο Μεσολογγίου</a></td><td>18/07/2026</td><td><a href='/files/budget.pdf'>PDF</a></td></tr></table>"
        }
      }
    ]
    """

    with patch("tender_radar.sources.authority.urlopen", return_value=Response(payload)):
        candidates, _, _ = discover_authority_candidates(config)

    assert candidates[0].title == "Έργο Μεσολογγίου"
    assert candidates[0].detail_url == "https://example.test/detail"
    assert candidates[0].attachment_url == "https://example.test/files/budget.pdf"


def test_diavgeia_api_extracts_decisions_as_candidate_only() -> None:
    config = {
        "authority_adapters": [
            {
                "id": "diavgeia",
                "name": "Διαύγεια",
                "scope_id": "scope",
                "scope_name": "Scope",
                "adapter": "diavgeia_api",
                "url": "https://diavgeia.gov.gr/opendata/search.json",
                "query_params": {"org": "nafpaktia", "size": 1},
            }
        ]
    }
    payload = """
    {
      "decisions": [
        {
          "ada": "6ΤΛΡΩΚΓ-9ΡΟ",
          "subject": "Απόφαση για έργο Ναυπάκτου",
          "issueDate": "2026-07-18",
          "documentUrl": "https://diavgeia.gov.gr/doc/6ΤΛΡΩΚΓ-9ΡΟ"
        }
      ]
    }
    """

    with patch("tender_radar.sources.authority.urlopen", return_value=Response(payload)):
        candidates, _, _ = discover_authority_candidates(config)

    assert candidates[0].title == "Απόφαση για έργο Ναυπάκτου"
    assert candidates[0].record_type == "AUTHORITY_WEB"
    assert candidates[0].status == "AUTHORITY_DISCOVERY_CANDIDATE"


def test_ted_api_extracts_notice_links() -> None:
    config = {
        "authority_adapters": [
            {
                "id": "ted",
                "name": "TED",
                "scope_id": "scope",
                "scope_name": "Scope",
                "adapter": "ted_api",
                "url": "https://api.ted.europa.eu/v3/notices/search",
                "body": {"query": "buyer-country = GRC", "limit": 1},
            }
        ]
    }
    payload = """
    {
      "notices": [
        {
          "publication-number": "449222-2026",
          "notice-title": {"ell": "Δημόσιο έργο"},
          "publication-date": "2026-07-18",
          "links": {
            "html": {"ELL": "https://ted.europa.eu/el/notice/-/detail/449222-2026"},
            "pdf": {"ELL": "https://ted.europa.eu/el/notice/449222-2026/pdf"}
          }
        }
      ]
    }
    """

    with patch("tender_radar.sources.authority.urlopen", return_value=Response(payload)):
        candidates, _, _ = discover_authority_candidates(config)

    assert candidates[0].title == "Δημόσιο έργο"
    assert candidates[0].detail_url == "https://ted.europa.eu/el/notice/-/detail/449222-2026"
    assert candidates[0].attachment_url == "https://ted.europa.eu/el/notice/449222-2026/pdf"


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
