from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    confidence: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class DocumentAnalysis:
    document_type: str
    classification_confidence: float
    matched_terms: tuple[str, ...]
    extraction_status: str
    page_or_sheet_count: int | None
    text_sample: str | None
    full_text: str | None
    extraction_error: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DOCUMENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("technical_description", ("τεχνικη περιγραφη", "τεχνική περιγραφή")),
    ("tender_declaration", ("διακηρυξη", "διακήρυξη")),
    ("budget", ("προυπολογισμος", "προϋπολογισμος", "προϋπολογισμός")),
    ("price_list", ("τιμολογιο μελετης", "τιμολόγιο μελέτης", "τιμολογιο")),
    ("special_conditions", ("εσυ", "ειδικη συγγραφη", "ειδική συγγραφή")),
    ("financial_offer_form", ("οικονομικη προσφορα", "οικονομική προσφορά")),
    ("espd", ("espd", "εεεσ")),
)


def analyze_document(path: Path, original_name: str | None = None) -> DocumentAnalysis:
    classification = classify_document_name(original_name or path.name)
    status, count, sample, full_text, error = extract_text(path)
    return DocumentAnalysis(
        document_type=classification.document_type,
        classification_confidence=classification.confidence,
        matched_terms=classification.matched_terms,
        extraction_status=status,
        page_or_sheet_count=count,
        text_sample=sample,
        full_text=full_text,
        extraction_error=error,
    )


def classify_document_name(filename: str) -> DocumentClassification:
    normalized = _normalize(filename)
    best_type = "other"
    best_terms: tuple[str, ...] = ()
    for document_type, terms in DOCUMENT_RULES:
        matched = tuple(term for term in terms if _normalize(term) in normalized)
        if matched:
            best_type = document_type
            best_terms = matched
            break
    confidence = 0.95 if best_terms else 0.2
    return DocumentClassification(best_type, confidence, best_terms)


def extract_text_sample(path: Path, max_chars: int = 4000) -> tuple[str, int | None, str | None, str | None]:
    status, count, sample, _full_text, error = extract_text(path, max_chars=max_chars)
    return status, count, sample, error


def extract_text(path: Path, max_chars: int = 4000) -> tuple[str, int | None, str | None, str | None, str | None]:
    suffix = path.suffix.lower()
    if not path.exists():
        return "MISSING_FILE", None, None, None, f"File does not exist: {path}"
    if suffix == ".xml":
        return _extract_xml_text(path, max_chars)
    if suffix == ".pdf":
        return _extract_pdf_text(path, max_chars)
    return "UNSUPPORTED_TYPE", None, None, None, f"Unsupported document type: {suffix or 'no extension'}"


def _extract_xml_text(path: Path, max_chars: int) -> tuple[str, int | None, str | None, str | None, str | None]:
    try:
        tree = ET.parse(path)
        text = _clean_text(" ".join(item for item in tree.getroot().itertext() if item.strip()))
    except Exception as exc:
        return "EXTRACTION_FAILED", None, None, None, repr(exc)
    return "TEXT_EXTRACTED", None, text[:max_chars] or None, text or None, None


def _extract_pdf_text(path: Path, max_chars: int) -> tuple[str, int | None, str | None, str | None, str | None]:
    if importlib.util.find_spec("pypdf"):
        return _extract_pdf_with_pypdf(path, max_chars)
    if importlib.util.find_spec("PyPDF2"):
        return _extract_pdf_with_pypdf2(path, max_chars)
    return "NO_TEXT_EXTRACTOR", None, None, None, "Install pypdf or PyPDF2 to extract PDF text."


def _extract_pdf_with_pypdf(path: Path, max_chars: int) -> tuple[str, int | None, str | None, str | None, str | None]:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = _clean_text(" ".join((page.extract_text() or "") for page in reader.pages))
        return "TEXT_EXTRACTED" if text else "NO_TEXT_FOUND", len(reader.pages), text[:max_chars] or None, text or None, None
    except Exception as exc:
        return "EXTRACTION_FAILED", None, None, None, repr(exc)


def _extract_pdf_with_pypdf2(path: Path, max_chars: int) -> tuple[str, int | None, str | None, str | None, str | None]:
    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = _clean_text(" ".join((page.extract_text() or "") for page in reader.pages))
        return "TEXT_EXTRACTED" if text else "NO_TEXT_FOUND", len(reader.pages), text[:max_chars] or None, text or None, None
    except Exception as exc:
        return "EXTRACTION_FAILED", None, None, None, repr(exc)


def _normalize(value: str) -> str:
    lowered = value.lower().replace("_", " ")
    without_accents = str.maketrans("άέήίόύώϊΐϋΰ", "αεηιουωιιυυ")
    return _clean_text(lowered.translate(without_accents))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def render_markdown_report(report: dict[str, object]) -> str:
    documents = report.get("documents")
    if not isinstance(documents, list):
        documents = []
    lines = [
        "# Document Analysis",
        "",
        f"- ESHIDIS id: `{report.get('eshidis_id') or 'ALL'}`",
        f"- Documents analyzed: `{report.get('documents_analyzed')}`",
        "",
        "| Type | Pages | Status | File |",
        "| --- | ---: | --- | --- |",
    ]
    for item in documents:
        if not isinstance(item, dict):
            continue
        doc_type = item.get("document_type") or "other"
        pages = item.get("page_or_sheet_count")
        status = item.get("extraction_status") or "UNKNOWN"
        name = str(item.get("original_name") or "")
        lines.append(f"| `{doc_type}` | {pages or ''} | `{status}` | {name} |")
    lines.extend(["", "## Text Samples", ""])
    for item in documents:
        if not isinstance(item, dict):
            continue
        name = str(item.get("original_name") or "")
        doc_type = item.get("document_type") or "other"
        sample = str(item.get("text_sample") or "")
        if len(sample) > 900:
            sample = sample[:900].rstrip() + "..."
        lines.extend(
            [
                f"### {name}",
                "",
                f"- Type: `{doc_type}`",
                f"- Status: `{item.get('extraction_status') or 'UNKNOWN'}`",
                "",
                sample or "_No extracted text sample._",
                "",
            ]
        )
    return "\n".join(lines)
