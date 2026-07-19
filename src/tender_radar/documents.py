from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


MIN_TEXT_CHARS_BEFORE_OCR = 80
OCR_MAX_PAGES = 3


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
    ocr_status: str
    ocr_error: str | None

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
    extraction = extract_text_with_metadata(path)
    return DocumentAnalysis(
        document_type=classification.document_type,
        classification_confidence=classification.confidence,
        matched_terms=classification.matched_terms,
        extraction_status=extraction.status,
        page_or_sheet_count=extraction.page_or_sheet_count,
        text_sample=extraction.text_sample,
        full_text=extraction.full_text,
        extraction_error=extraction.extraction_error,
        ocr_status=extraction.ocr_status,
        ocr_error=extraction.ocr_error,
    )


@dataclass(frozen=True)
class TextExtraction:
    status: str
    page_or_sheet_count: int | None
    text_sample: str | None
    full_text: str | None
    extraction_error: str | None
    ocr_status: str = "NOT_APPLICABLE"
    ocr_error: str | None = None


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
    extraction = extract_text_with_metadata(path, max_chars=max_chars)
    return (
        extraction.status,
        extraction.page_or_sheet_count,
        extraction.text_sample,
        extraction.full_text,
        extraction.extraction_error,
    )


def extract_text_with_metadata(path: Path, max_chars: int = 4000) -> TextExtraction:
    suffix = path.suffix.lower()
    if not path.exists():
        return TextExtraction("MISSING_FILE", None, None, None, f"File does not exist: {path}")
    if suffix == ".xml":
        status, count, sample, full_text, error = _extract_xml_text(path, max_chars)
        return TextExtraction(status, count, sample, full_text, error)
    if suffix == ".pdf":
        return _extract_pdf_text(path, max_chars)
    return TextExtraction("UNSUPPORTED_TYPE", None, None, None, f"Unsupported document type: {suffix or 'no extension'}")


def _extract_xml_text(path: Path, max_chars: int) -> tuple[str, int | None, str | None, str | None, str | None]:
    try:
        tree = ET.parse(path)
        text = _clean_text(" ".join(item for item in tree.getroot().itertext() if item.strip()))
    except Exception as exc:
        return "EXTRACTION_FAILED", None, None, None, repr(exc)
    return "TEXT_EXTRACTED", None, text[:max_chars] or None, text or None, None


def _extract_pdf_text(path: Path, max_chars: int) -> TextExtraction:
    if importlib.util.find_spec("pypdf"):
        status, count, sample, full_text, error = _extract_pdf_with_pypdf(path, max_chars)
    elif importlib.util.find_spec("PyPDF2"):
        status, count, sample, full_text, error = _extract_pdf_with_pypdf2(path, max_chars)
    else:
        status, count, sample, full_text, error = (
            "NO_TEXT_EXTRACTOR",
            None,
            None,
            None,
            "Install pypdf or PyPDF2 to extract PDF text.",
        )
    if not needs_ocr(status, full_text):
        return TextExtraction(status, count, sample, full_text, error, "NOT_NEEDED", None)
    ocr_status, ocr_text, ocr_error = _ocr_pdf_text(path, page_count=count)
    if ocr_text:
        text = _clean_text(" ".join(item for item in (full_text, ocr_text) if item))
        return TextExtraction(
            "TEXT_EXTRACTED_WITH_OCR",
            count,
            text[:max_chars] or None,
            text or None,
            error,
            ocr_status,
            ocr_error,
        )
    return TextExtraction(status, count, sample, full_text, error, ocr_status, ocr_error)


def needs_ocr(status: str, full_text: str | None) -> bool:
    if status in {"EXTRACTION_FAILED", "NO_TEXT_FOUND", "NO_TEXT_EXTRACTOR"}:
        return True
    return len(_clean_text(full_text or "")) < MIN_TEXT_CHARS_BEFORE_OCR


def _ocr_pdf_text(path: Path, *, page_count: int | None) -> tuple[str, str | None, str | None]:
    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not pdftoppm or not tesseract:
        missing = ", ".join(name for name, value in (("pdftoppm", pdftoppm), ("tesseract", tesseract)) if not value)
        return "OCR_TOOL_MISSING", None, f"Missing OCR tool(s): {missing}"
    max_pages = min(page_count or OCR_MAX_PAGES, OCR_MAX_PAGES)
    try:
        with tempfile.TemporaryDirectory(prefix="tender-radar-ocr-") as tmp:
            prefix = str(Path(tmp) / "page")
            subprocess.run(
                [pdftoppm, "-f", "1", "-l", str(max_pages), "-r", "200", "-png", str(path), prefix],
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            texts: list[str] = []
            for image_path in sorted(Path(tmp).glob("page-*.png")):
                completed = subprocess.run(
                    [tesseract, str(image_path), "stdout", "-l", "ell+eng", "--psm", "6"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                if completed.returncode != 0:
                    return "OCR_FAILED", None, completed.stderr.strip() or f"tesseract exited {completed.returncode}"
                if completed.stdout.strip():
                    texts.append(completed.stdout)
            text = _clean_text(" ".join(texts))
            return ("OCR_TEXT_EXTRACTED" if text else "OCR_NO_TEXT_FOUND"), text or None, None
    except (OSError, subprocess.SubprocessError) as exc:
        return "OCR_FAILED", None, repr(exc)


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
        "| Type | Pages | Status | OCR | File |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for item in documents:
        if not isinstance(item, dict):
            continue
        doc_type = item.get("document_type") or "other"
        pages = item.get("page_or_sheet_count")
        status = item.get("extraction_status") or "UNKNOWN"
        ocr_status = item.get("ocr_status") or "UNKNOWN"
        name = str(item.get("original_name") or "")
        lines.append(f"| `{doc_type}` | {pages or ''} | `{status}` | `{ocr_status}` | {name} |")
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
