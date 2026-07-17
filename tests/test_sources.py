from tender_radar.sources.eshidis import (
    inspect_authority_page,
    inspect_eshidis_html,
    parse_eshidis_attachment_xml,
    parse_eshidis_resource_text,
)
from tender_radar.sources.eshidis_browser import parse_discovery_candidates, render_discovery_markdown
from tender_radar.sources.eshidis_browser import try_open_attachments


def test_eshidis_loopback_html_is_detected() -> None:
    html = """
    <html><head><script>AdfLoopbackUtils.runLoopback(
    ';jsessionid=abc123'
    );</script><noscript>This page uses JavaScript and requires a JavaScript enabled browser.</noscript></head></html>
    """
    result = inspect_eshidis_html(html, 200)
    assert result.reachable
    assert result.needs_javascript
    assert result.oracle_adf_loopback
    assert result.session_hint


def test_authority_page_extracts_tender_reference() -> None:
    html = """
    <h3>Διακήρυξη ανοικτού ηλεκτρονικού διαγωνισμού για έργο</h3>
    <p>Ο Α/Α συστήματος είναι 219879.</p>
    <a href="https://example.test/files/declaration.pdf">ΔΙΑΚΗΡΥΞΗ</a>
    <a href="https://example.test/files/study.zip">ΜΕΛΕΤΗ</a>
    """
    result = inspect_authority_page("https://example.test/tender", html)
    assert result.eshidis_id == "219879"
    assert result.title == "Διακήρυξη ανοικτού ηλεκτρονικού διαγωνισμού για έργο"
    assert len(result.attachment_links) == 2


def test_eshidis_resource_text_extracts_tender_details() -> None:
    text = """
    Διαγωνισμός Συνημμένα Αρχεία
    Συνοπτικός Τίτλος/Αρ. Διακήρυξης: ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027
    ΑΑ Συστήματος: 221744
    Κωδικός CPV: 45233141-9
    Πρόσθετη περιγραφή ειδών/Υπηρεσιών: ΟΔΟΣΤΡΩΣΙΑ
    Αναθέτουσα Αρχή: ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΟΣ
    Τοποθεσίες Έργου: EL631 - Αιτωλοακαρνανία (Aitoloakarnania)
    Τίτλος Έργου/Μελέτη: ΣΥΝΤΗΡΗΣΕΙΣ ΕΠΑΡΧΙΑΚΟΥ ΟΔΙΚΟΥ ΔΙΚΤΥΟΥ
    Χρηματοδοτήσεις: ΠΔΕ
    Συνολικός Προϋπολογισμός (με ΦΠΑ): 2.500.000,00
    Ημερομηνία Δημοσίευσης: 15-07-2026 00:44:36
    Καταληκτική Ημ/νία Υποβολής Προσφορών : 07-08-2026 10:00:00
    Ποσό Κατακύρωσης:
    """
    result = parse_eshidis_resource_text("https://example.test/221744", text)
    assert result.eshidis_id == "221744"
    assert result.cpv == "45233141-9"
    assert result.budget_with_vat == "2.500.000,00"
    assert result.submission_deadline == "07-08-2026 10:00:00"


def test_eshidis_attachment_xml_extracts_listing() -> None:
    xml = """
    <update id="t1"><![CDATA[
    <table _rowCount="2">
      <span id="t1:0:it2::content">&#932;&#917;&#935;&#925;&#921;&#922;&#919; signed.pdf</span>
      <span id="t1:1:it2::content">espd-request.xml</span>
    </table>
    ]]></update>
    """
    result = parse_eshidis_attachment_xml(xml)
    assert result.row_count == 2
    assert result.filenames == ("ΤΕΧΝΙΚΗ signed.pdf", "espd-request.xml")


class _FakeLocator:
    def __init__(self, count_value: int) -> None:
        self._count_value = count_value
        self.clicked = False

    def count(self) -> int:
        return self._count_value

    def click(self, timeout: int) -> None:
        self.clicked = True

    def wait_for(self, state: str, timeout: int) -> None:
        return None

    @property
    def first(self) -> "_FakeLocator":
        return self


class _FakePage:
    def __init__(self) -> None:
        self.locators = {
            "#sdi2\\:\\:disAcr": _FakeLocator(1),
            "#t1\\:\\:db": _FakeLocator(1),
            '[id^="t1:"][id$=":cb1"]': _FakeLocator(3),
            "#t1\\:\\:db tr": _FakeLocator(3),
        }

    def locator(self, selector: str) -> _FakeLocator:
        return self.locators[selector]

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        return None


def test_try_open_attachments_waits_for_loaded_table() -> None:
    result = try_open_attachments(_FakePage())

    assert result["clicked"] is True
    assert result["table_attached"] is True
    assert result["buttons_seen"] == 3
    assert result["rows_seen"] == 3
