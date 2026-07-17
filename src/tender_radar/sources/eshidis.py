from __future__ import annotations

from dataclasses import dataclass
import html as html_lib
from html.parser import HTMLParser
import re
import ssl
from typing import Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen


ACTIVE_WORKS_SEARCH_URL = (
    "https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/"
    "active_search_main.jspx"
)


@dataclass(frozen=True)
class SourceHealth:
    source: str
    url: str
    reachable: bool
    status_code: int | None
    needs_javascript: bool
    oracle_adf_loopback: bool
    session_hint: bool
    message: str


@dataclass(frozen=True)
class TenderReference:
    source_url: str
    title: str | None
    eshidis_id: str | None
    attachment_links: tuple[str, ...]


@dataclass(frozen=True)
class EshidisTenderDetails:
    source_url: str
    eshidis_id: str | None
    title: str | None
    cpv: str | None
    contracting_authority: str | None
    location: str | None
    project_title: str | None
    budget_with_vat: str | None
    publication_date: str | None
    submission_deadline: str | None


@dataclass(frozen=True)
class EshidisAttachmentListing:
    row_count: int | None
    filenames: tuple[str, ...]


def inspect_eshidis_html(html: str, status_code: int | None = None) -> SourceHealth:
    needs_javascript = "requires a JavaScript enabled browser" in html
    oracle_adf_loopback = "AdfLoopbackUtils.runLoopback" in html
    session_hint = "jsessionid=" in html
    reachable = status_code is None or 200 <= status_code < 400
    if oracle_adf_loopback:
        message = "Oracle ADF loopback received; browser automation is required."
    elif needs_javascript:
        message = "JavaScript-required page received."
    elif reachable:
        message = "Endpoint reachable."
    else:
        message = "Endpoint not reachable."
    return SourceHealth(
        source="eshidis_public_works_active_search",
        url=ACTIVE_WORKS_SEARCH_URL,
        reachable=reachable,
        status_code=status_code,
        needs_javascript=needs_javascript,
        oracle_adf_loopback=oracle_adf_loopback,
        session_hint=session_hint,
        message=message,
    )


def health_check(timeout_seconds: int = 20, allow_insecure_tls: bool = False) -> SourceHealth:
    request = Request(
        ACTIVE_WORKS_SEARCH_URL,
        headers={"User-Agent": "TenderRadar/0.1 source-audit"},
    )
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    try:
        with urlopen(request, timeout=timeout_seconds, context=context) as response:
            body = response.read().decode("utf-8", errors="replace")
            health = inspect_eshidis_html(body, response.status)
            if allow_insecure_tls:
                return SourceHealth(
                    source=health.source,
                    url=health.url,
                    reachable=health.reachable,
                    status_code=health.status_code,
                    needs_javascript=health.needs_javascript,
                    oracle_adf_loopback=health.oracle_adf_loopback,
                    session_hint=health.session_hint,
                    message=health.message + " TLS verification was disabled for audit.",
                )
            return health
    except URLError as exc:
        return SourceHealth(
            source="eshidis_public_works_active_search",
            url=ACTIVE_WORKS_SEARCH_URL,
            reachable=False,
            status_code=None,
            needs_javascript=False,
            oracle_adf_loopback=False,
            session_hint=False,
            message=f"HTTP failure: {exc}",
        )


class AuthorityTenderParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_heading = False
        self._heading_done = False
        self._heading_parts: list[str] = []
        self._links: list[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"h1", "h2", "h3"} and not self._heading_done:
            self._in_heading = True
        if tag == "a":
            href = attrs_dict.get("href")
            if href and _looks_like_attachment(href):
                self._links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = False
            if self._heading_parts:
                self._heading_done = True

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            text = " ".join(data.split())
            if text:
                self._heading_parts.append(text)

    @property
    def title(self) -> str | None:
        title = " ".join(self._heading_parts).strip()
        return title or None

    @property
    def attachment_links(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._links))


def inspect_authority_page(source_url: str, html: str) -> TenderReference:
    parser = AuthorityTenderParser()
    parser.feed(html)
    return TenderReference(
        source_url=source_url,
        title=parser.title,
        eshidis_id=_find_eshidis_id(html),
        attachment_links=parser.attachment_links,
    )


def parse_eshidis_resource_text(source_url: str, text: str) -> EshidisTenderDetails:
    normalized = _normalize_text(text)
    return EshidisTenderDetails(
        source_url=source_url,
        eshidis_id=_field_after(normalized, "ΑΑ Συστήματος:", ("Κωδικός CPV:",)),
        title=_field_after(normalized, "Συνοπτικός Τίτλος/Αρ. Διακήρυξης:", ("ΑΑ Συστήματος:",)),
        cpv=_field_after(normalized, "Κωδικός CPV:", ("Πρόσθετη περιγραφή",)),
        contracting_authority=_field_after(normalized, "Αναθέτουσα Αρχή:", ("Τοποθεσίες Έργου:",)),
        location=_field_after(normalized, "Τοποθεσίες Έργου:", ("Τίτλος Έργου/Μελέτη:",)),
        project_title=_field_after(normalized, "Τίτλος Έργου/Μελέτη:", ("Χρηματοδοτήσεις:",)),
        budget_with_vat=_field_after(normalized, "Συνολικός Προϋπολογισμός (με ΦΠΑ):", ("Ημερομηνία Δημοσίευσης:",)),
        publication_date=_field_after(normalized, "Ημερομηνία Δημοσίευσης:", ("Καταληκτική",)),
        submission_deadline=_field_after(
            normalized,
            "Καταληκτική Ημ/νία Υποβολής Προσφορών :",
            ("Ποσό Κατακύρωσης:",),
        ),
    )


def parse_eshidis_attachment_xml(xml_text: str) -> EshidisAttachmentListing:
    unescaped = html_lib.unescape(xml_text)
    row_count_match = re.search(r'_rowCount="(\d+)"', unescaped)
    filenames = []
    for match in re.finditer(r'id="t1:\d+:it2::content"[^>]*>(.*?)</span>', unescaped, re.DOTALL):
        filename = _normalize_text(_strip_tags(match.group(1)))
        if filename:
            filenames.append(filename)
    return EshidisAttachmentListing(
        row_count=int(row_count_match.group(1)) if row_count_match else None,
        filenames=tuple(dict.fromkeys(filenames)),
    )


def _find_eshidis_id(text: str) -> str | None:
    normalized = " ".join(text.split())
    markers = ("Α/Α συστήματος", "Α/Α Συστήματος", "Α/Α ΕΣΗΔΗΣ", "Συστήματος ΕΣΗΔΗΣ")
    for marker in markers:
        index = normalized.find(marker)
        if index == -1:
            continue
        tail = normalized[index : index + 160]
        digits = "".join(ch if ch.isdigit() else " " for ch in tail).split()
        for candidate in digits:
            if len(candidate) >= 5:
                return candidate
    return None


def _looks_like_attachment(href: str) -> bool:
    lowered = href.lower().split("?", 1)[0]
    return lowered.endswith((".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".xml"))


def _field_after(text: str, marker: str, end_markers: tuple[str, ...]) -> str | None:
    start = text.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = len(text)
    for end_marker in end_markers:
        candidate = text.find(end_marker, start)
        if candidate != -1:
            end = min(end, candidate)
    value = text[start:end].strip(" :")
    return value or None


def _normalize_text(text: str) -> str:
    return " ".join(html_lib.unescape(text).split())


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)
