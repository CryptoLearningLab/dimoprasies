from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import sys
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tender_radar.pricing import (  # noqa: E402
    PricingBudgetRow,
    _ocr_pdf_for_budget,
    canonical_article_code,
    extract_budget_text,
    parse_budget_rows_from_text,
    parse_greek_decimal,
    strip_accents,
)
from tender_radar.simple_yaml import load_yaml  # noqa: E402


DEFAULT_CONFIG_PATH = REPO_ROOT / "geo_afoi_pricing/config.example.yml"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "geo_afoi_pricing/schema.sql"
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class FileClassification:
    role: str
    reason: str
    score: int
    ignored: bool = False


@dataclass(frozen=True)
class ChapterCandidate:
    line_number: int
    chapter_code: str | None
    chapter_title: str
    confidence: float


@dataclass(frozen=True)
class ArticleResolution:
    identity_key: str | None
    repaired_article_code: str
    repaired_canonical_article_code: str
    repaired_revision_codes: list[str]
    canonical_unit: str
    article_quality_status: str
    usable_for_stats: bool
    method: str
    confidence: float
    warnings: list[str]
    aliases: dict[str, list[str]]
    canonical_chapter_title: str | None
    description_hint: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_for_match(value: str) -> str:
    text = strip_accents(value).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def looks_like_greek_font_mojibake(text: str) -> bool:
    normalized = strip_accents(text).upper()
    suspicious_tokens = (
        "ΠΡΟΥΠΟΛΟΓΘ",
        "ΜΕΛΕΣΗ",
        "ΝΑΟΓΟ",
        "ΟΓΟΝ",
        "ΣΕΥΝΘΚ",
        "ΥΩΜΑΣ",
    )
    hits = sum(normalized.count(token) for token in suspicious_tokens)
    return hits >= 3


MOJIBAKE_CODE_TOKEN_REPAIRS = {
    "ΝΑΟΓΟ": "ΝΑΟΔΟ",
    "ΟΓΟΝ": "ΟΔΟΝ",
    "ΤΓΡ": "ΥΔΡ",
    "ΝΑΤΓΡ": "ΝΑΥΔΡ",
}

MOJIBAKE_CHAPTER_REPAIRS = {
    "ΣΕΥΝΘΚΑ": "ΤΕΧΝΙΚΑ",
    "ΟΔΟ΢ΣΡΩ΢ΘΑ": "ΟΔΟΣΤΡΩΣΙΑ",
    "ΟΔΟΣΣΡΩΣΘΑ": "ΟΔΟΣΤΡΩΣΙΑ",
    "Α΢ΦΑΛΣΘΚΑ": "ΑΣΦΑΛΤΙΚΑ",
    "ΑΣΦΑΛΣΘΚΑ": "ΑΣΦΑΛΤΙΚΑ",
    "ΥΩΜΑΣΟΤΡΓΘΚΑ": "ΧΩΜΑΤΟΥΡΓΙΚΑ",
    "ΚΑΘΑΘΡΕ΢ΕΘ΢": "ΚΑΘΑΙΡΕΣΕΙΣ",
    "ΚΑΘΑΘΡΕΣΕΘΣ": "ΚΑΘΑΙΡΕΣΕΙΣ",
}

ARTICLE_PREFIXES = {
    "ΝΑΟΔΟ",
    "ΝΑΥΔΡ",
    "ΝΑΟΙΚ",
    "ΝΑΠΡΣ",
    "ΝΑΗΛΜ",
    "ΗΛΜ",
    "ΑΤΗΕ",
    "ΟΙΚ",
    "ΠΡΣ",
    "ΛΙΜ",
    "ΟΔΟ",
}

NUMERIC_OIK_ARTICLE_ALIASES = {
    "77.10": {
        "canonical": "ΝΑΟΙΚ 77.10",
        "revision": "ΟΙΚ-7725",
        "description_terms": ("υδροχρωματισμοι", "σκυροδεματος", "τσιμεντοκονιαματος", "τσιμεντοχρωμα"),
    },
    "77.30": {
        "canonical": "ΝΑΟΙΚ 77.30",
        "revision": "ΟΙΚ-7735",
        "description_terms": ("υποστρωμα", "ασταρι", "τσιμεντοχρωματων", "ακρυλικες", "διαλυτου"),
    },
}

MISREAD_ARTICLE_ALIASES = {
    "ΝΑΟΔΟΓ03": {
        "canonical": "ΝΑΟΔΟ Δ03",
        "revision": "ΟΔΟ-4110",
        "description_terms_any": ("ασφαλτικ", "αζθαιηη"),
    },
}

REVISION_PREFIX_REPAIRS = {
    "ODO": "ΟΔΟ",
    "ΝΟΔΟ": "ΟΔΟ",
    "ΟΔΟΝ": "ΟΔΟ",
    "ΟΓΟΝ": "ΟΔΟ",
    "ΥΔΡ": "ΥΔΡ",
    "ΤΓΡ": "ΥΔΡ",
    "ΟΙΚ": "ΟΙΚ",
    "ΗΛΜ": "ΗΛΜ",
    "ΠΡΣ": "ΠΡΣ",
    "ΛΙΜ": "ΛΙΜ",
}


def repair_mojibake_code_tokens(value: str) -> str:
    text = value
    for raw, repaired in MOJIBAKE_CODE_TOKEN_REPAIRS.items():
        text = re.sub(rf"\b{re.escape(raw)}\b", repaired, text, flags=re.IGNORECASE)
    return text


def repair_mojibake_chapter_title(value: str | None) -> str | None:
    if not value:
        return None
    text = value
    text = text.replace("΢", "Σ")
    for raw, repaired in {**MOJIBAKE_CODE_TOKEN_REPAIRS, **MOJIBAKE_CHAPTER_REPAIRS}.items():
        text = re.sub(rf"\b{re.escape(raw)}\b", repaired, text, flags=re.IGNORECASE)
    return " ".join(text.split())


def chapter_quality_status(raw_title: str | None, repaired_title: str | None) -> str:
    text = normalize_alias(repaired_title or raw_title or "")
    suspicious = ("ΣΕΥΝΘΚΑ", "ΟΔΟΣΡΩΘΑ", "ΟΔΟΣΣΡΩΣΘΑ", "ΑΣΦΑΛΣΘΚΑ", "ΥΩΜΑΣ", "ΚΑΘΑΘΡΕ")
    return "NEEDS_REVIEW" if any(token in text for token in suspicious) else "READY"


def normalize_alias(value: str) -> str:
    return re.sub(r"\s+", "", strip_accents(value).upper().replace("–", "-").replace("—", "-"))


def canonical_unit_key(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "UNKNOWN"
    text = strip_accents(str(value)).casefold().strip()
    text = text.replace("²", "2").replace("³", "3")
    text = text.replace(".", "")
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"[μµ]([23])?", text) or text == "μμ":
        text = text.replace("μ", "m").replace("µ", "m")
    aliases = {
        "m": "m",
        "mm": "m",
        "μμ": "m",
        "m2": "m2",
        "m3": "m3",
        "kg": "kg",
        "kgr": "kg",
        "κιλ": "kg",
        "t": "ton",
        "tn": "ton",
        "ton": "ton",
        "tons": "ton",
        "tonx1": "ton",
        "τεμ": "τεμ",
        "τεμαχιο": "τεμ",
        "τεμαχια": "τεμ",
        "στρ": "στρ",
        "στρεμμα": "στρ",
        "στρεμματα": "στρ",
        "ημ/σ": "ημ/σ",
        "hm/s": "ημ/σ",
        "κα": "κ.α.",
        "κa": "κ.α.",
    }
    return aliases.get(text, text or "UNKNOWN")


def description_fingerprint(value: str) -> str:
    normalized = normalize_for_match(value)
    normalized = re.sub(r"[^0-9a-zα-ω]+", " ", normalized)
    normalized = " ".join(normalized.split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return digest


def is_local_new_price_article(value: str) -> bool:
    text = strip_accents(value).upper()
    replacements = {
        "N": "Ν",
        "T": "Τ",
        " ": "",
        "-": "",
        "_": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return bool(re.fullmatch(r"Ν\.?Τ\.?\d*", text))


def _article_has_known_prefix(value: str) -> bool:
    canonical = normalize_alias(value)
    return any(canonical.startswith(prefix) for prefix in ARTICLE_PREFIXES)


def _article_suffix(value: str) -> str:
    repaired = repair_mojibake_code_tokens(value).strip()
    parts = repaired.split()
    if len(parts) > 1 and parts[0] in REVISION_PREFIX_REPAIRS:
        return " ".join(parts[1:])
    return repaired


def normalize_article_suffix(value: str) -> str:
    text = repair_mojibake_code_tokens(value).strip().upper()
    text = text.replace("A", "Α").replace("B", "Β").replace("E", "Ε")
    text = re.sub(r"^N\.\s*", "Ν.", text)
    text = re.sub(r"\s+", " ", text)
    net_match = re.fullmatch(r"ΝΕΤ\s+ΟΔΟ-ΜΕ\s+(.+)", text)
    if net_match:
        return f"ΝΑΟΔΟ {normalize_article_suffix(net_match.group(1))}"
    net_match = re.fullmatch(r"ΝΕΤ\s+ΟΙΚ-Α\s+(.+)", text)
    if net_match:
        return f"ΝΑΟΙΚ {normalize_article_suffix(net_match.group(1))}"
    net_match = re.fullmatch(r"ΝΕΤ\s+ΥΔΡ-Α\s+(.+)", text)
    if net_match:
        return f"ΝΑΥΔΡ {normalize_article_suffix(net_match.group(1))}"
    net_match = re.fullmatch(r"ΝΕΤ\s+ΠΡΣ\s+(.+)", text)
    if net_match:
        return f"ΝΑΠΡΣ {normalize_article_suffix(net_match.group(1))}"
    match = re.fullmatch(r"([ΑΒΓΔΕ])[-.\s](\d)(.*)", text)
    if match:
        if match.group(3) and match.group(3)[0].isdigit():
            return f"{match.group(1)}{match.group(2)}{match.group(3)}"
        trailing = "" if match.group(3) == "." else match.group(3)
        return f"{match.group(1)}0{match.group(2)}{trailing}"
    match = re.fullmatch(r"([ΑΒΓΔΕ])(\d)", text)
    if match:
        return f"{match.group(1)}0{match.group(2)}"
    text = re.sub(r"^([ΑΒΓΔΕ])[-.\s](\d{2,}.*)", r"\1\2", text)
    text = re.sub(r"^Ν\.\s*([ΑΒΓΔΕ])[-.\s](\d{2,}.*)", r"Ν.\1\2", text)
    return text


def _find_article_prefix(raw_text: str, suffix: str) -> str | None:
    if not suffix:
        return None
    repaired = repair_mojibake_code_tokens(strip_accents(raw_text).upper())
    suffix_pattern = re.escape(strip_accents(suffix).upper()).replace(r"\ ", r"\s+")
    prefix_pattern = "|".join(sorted(ARTICLE_PREFIXES, key=len, reverse=True))
    match = re.search(rf"\b(?P<prefix>{prefix_pattern})\s+{suffix_pattern}\b", repaired)
    if match:
        return match.group("prefix")
    if re.search(r"\d", suffix) and "ΝΑΥΔΡ" in repaired:
        return "ΝΑΥΔΡ"
    if re.search(r"\b(?:ΝΟΔΟ|ΟΔΟΝ|ΟΔΟ)\s*-?\s*\d", repaired):
        return "ΝΑΟΔΟ"
    if re.fullmatch(r"[ΑΒΓΔΕ][0-9].*", normalize_article_suffix(suffix)):
        return "ΝΑΟΔΟ"
    return None


def _numeric_oik_article_alias(article_code: str, description: str, revisions: list[str]) -> str | None:
    article_norm = normalize_alias(article_code)
    alias = NUMERIC_OIK_ARTICLE_ALIASES.get(article_norm)
    if not alias:
        return None
    revision_norms = {normalize_alias(value) for value in revisions}
    if normalize_alias(alias["revision"]) not in revision_norms:
        return None
    description_norm = normalize_for_match(description)
    if not all(term in description_norm for term in alias["description_terms"]):
        return None
    return str(alias["canonical"])


def _misread_article_alias(article_code: str, description: str, revisions: list[str]) -> str | None:
    alias = MISREAD_ARTICLE_ALIASES.get(canonical_article_code(article_code))
    if not alias:
        return None
    revision_norms = {normalize_alias(value) for value in revisions}
    if normalize_alias(alias["revision"]) not in revision_norms:
        return None
    description_norm = normalize_for_match(description)
    if not any(term in description_norm for term in alias["description_terms_any"]):
        return None
    return str(alias["canonical"])


def _should_promote_bare_article_to_prs(raw_article_code: str, repaired_article_code: str, revisions: list[str]) -> bool:
    if _article_has_known_prefix(raw_article_code) or is_local_new_price_article(raw_article_code):
        return False
    if not repaired_article_code.startswith("ΝΑΟΔΟ "):
        return False
    if not any(normalize_alias(revision).startswith("ΠΡΣ") for revision in revisions):
        return False
    parts = repaired_article_code.split(maxsplit=1)
    suffix_source = parts[1] if len(parts) == 2 and parts[0] in ARTICLE_PREFIXES else repaired_article_code
    suffix = normalize_article_suffix(suffix_source)
    return bool(re.fullmatch(r"[ΔΕΖΗΘ][0-9].*", suffix))


LATIN_TO_GREEK_REVISION_LETTERS = str.maketrans(
    {
        "A": "Α",
        "B": "Β",
        "E": "Ε",
        "H": "Η",
        "I": "Ι",
        "K": "Κ",
        "M": "Μ",
        "N": "Ν",
        "O": "Ο",
        "P": "Ρ",
        "T": "Τ",
        "X": "Χ",
        "Y": "Υ",
        "Z": "Ζ",
    }
)


def normalize_revision_number(value: str) -> str:
    number = value.replace(",", ".").replace(" ", "").upper()
    number = number.translate(LATIN_TO_GREEK_REVISION_LETTERS)
    number = re.sub(r"\.([Α-Ω])", r"\1", number)
    return number


def _extract_repaired_revision_codes(raw_text: str, article_code: str) -> list[str]:
    repaired = repair_mojibake_code_tokens(strip_accents(raw_text).upper())
    article_norm = normalize_alias(article_code)
    codes: list[str] = []
    pattern = re.compile(
        r"\b(?P<prefix>ODO|ΝΟΔΟ|ΟΔΟΝ|ΟΔΟ|ΟΓΟΝ|ΥΔΡ|ΤΓΡ|ΟΙΚ|ΗΛΜ|ΠΡΣ|ΛΙΜ)\s*-?\s*(?P<num>\d+[Α-ΩA-Z0-9.,]*)\b"
    )
    for match in pattern.finditer(repaired):
        prefix = REVISION_PREFIX_REPAIRS.get(match.group("prefix"), match.group("prefix"))
        number = normalize_revision_number(match.group("num"))
        code = f"{prefix}-{number}"
        code_norm = normalize_alias(code)
        if (
            code_norm == article_norm
            or code_norm.replace("-", "") == article_norm.replace("-", "")
            or canonical_article_code(code).replace("-", "") == canonical_article_code(article_code).replace("-", "")
        ):
            continue
        if code not in codes:
            codes.append(code)
    return codes


def _format_greek_amount(value: float | None) -> str | None:
    if value is None:
        return None
    formatted = f"{float(value):,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def description_hint_from_ocr(ocr_text: str, row: PricingBudgetRow) -> str | None:
    amount = _format_greek_amount(row.amount)
    if not ocr_text or not amount:
        return None
    for raw_line in ocr_text.splitlines():
        clean = " ".join(raw_line.split())
        if len(clean) > 420:
            continue
        if amount not in clean:
            continue
        repaired = repair_mojibake_code_tokens(clean)
        article_match = re.search(
            r"\b(?:ΝΑΟΔΟ|ΝΑΥΔΡ|ΝΑΟΙΚ|ΟΙΚ|ΑΤΗΕ|ΠΡΣ|ΛΙΜ)\s+[A-ZΑ-Ω0-9.\\/]+",
            repaired,
        )
        if not article_match:
            continue
        prefix_text = repaired[: article_match.start()]
        prefix_text = re.sub(r"^\s*\d{1,3}[\]|)]?\s*", "", prefix_text)
        hint = " ".join(prefix_text.split())
        hint_norm = strip_accents(hint).upper()
        if len(hint) > 180 or any(token in hint_norm for token in ("ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ", "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ", "ΔΗΜΟΣ:")):
            continue
        return hint[:180] or None
    return None


def resolve_article_identity(
    row: PricingBudgetRow,
    *,
    chapter: ChapterCandidate | None,
    ocr_text: str = "",
) -> ArticleResolution:
    warnings: list[str] = []
    aliases: dict[str, list[str]] = {
        "article_code": [row.article_code],
        "canonical_article_code": [row.canonical_article_code],
        "revision_code": list(row.revision_codes),
    }
    repaired_raw = repair_mojibake_code_tokens(row.raw_text)
    repaired_article = normalize_article_suffix(repair_mojibake_code_tokens(row.article_code))
    local_new_price = is_local_new_price_article(repaired_article)
    suffix = _article_suffix(repaired_article)
    prefix = _find_article_prefix(repaired_raw, suffix) or _find_article_prefix(row.description, suffix)
    if prefix and not _article_has_known_prefix(repaired_article) and not local_new_price:
        repaired_article = f"{prefix} {suffix}".strip()
    elif prefix == "ΝΑΥΔΡ" and repaired_article.startswith("ΥΔΡ "):
        repaired_article = f"ΝΑΥΔΡ {suffix}".strip()
    repaired_canonical = canonical_article_code(repaired_article)
    repaired_revisions = _extract_repaired_revision_codes(repaired_raw, repaired_article)
    if _should_promote_bare_article_to_prs(row.article_code, repaired_article, repaired_revisions):
        parts = repaired_article.split(maxsplit=1)
        suffix = parts[1] if len(parts) == 2 and parts[0] in ARTICLE_PREFIXES else _article_suffix(repaired_article)
        repaired_article = f"ΝΑΠΡΣ {suffix}".strip()
        repaired_canonical = canonical_article_code(repaired_article)
    numeric_oik_alias = _numeric_oik_article_alias(repaired_article, row.description, repaired_revisions)
    if numeric_oik_alias:
        repaired_article = numeric_oik_alias
        repaired_canonical = canonical_article_code(repaired_article)
    misread_article_alias = _misread_article_alias(repaired_article, row.description, repaired_revisions)
    if misread_article_alias:
        repaired_article = misread_article_alias
        repaired_canonical = canonical_article_code(repaired_article)
    canonical_chapter = repair_mojibake_chapter_title(chapter.chapter_title if chapter else None)
    description_hint = description_hint_from_ocr(ocr_text, row)

    method = "raw"
    confidence = 0.75
    if repaired_article != row.article_code or repaired_revisions != row.revision_codes:
        method = "mojibake_token_repair"
        confidence = 0.86
    if numeric_oik_alias:
        method = "reviewed_numeric_oik_alias"
        confidence = 0.9
    if misread_article_alias:
        method = "reviewed_misread_article_alias"
        confidence = 0.9
    if description_hint:
        method = f"{method}+ocr_description_hint"

    if local_new_price:
        method = "local_new_price_identity"
        confidence = 0.82
    if not _article_has_known_prefix(repaired_article) and not local_new_price:
        warnings.append("article_prefix_missing_or_unrecognized")
    if any(token in normalize_alias(repaired_article) for token in ("ΝΑΟΓΟ", "ΤΓΡ", "ΟΓΟΝ", "ΝΑΤΓΡ")):
        warnings.append("article_code_still_contains_mojibake_token")
    if row.unit is None or row.unit == "":
        warnings.append("unit_missing")
    if row.quantity is None or row.unit_price is None or row.amount is None:
        warnings.append("numeric_fields_incomplete")

    unit_key = canonical_unit_key(row.unit)
    zero_amount_or_quantity = float(row.quantity or 0) == 0 or float(row.amount or 0) == 0
    if local_new_price and not warnings:
        revision_key = "+".join(normalize_alias(value) for value in repaired_revisions) or "NOREVISION"
        fingerprint = description_fingerprint(row.description)
        identity_key = f"LOCAL_NT|{revision_key}|{unit_key}|{fingerprint}"
        repaired_canonical = f"LOCAL_NT_{fingerprint}"
        status = "READY_ZERO_AMOUNT" if zero_amount_or_quantity else "READY"
        usable_for_stats = status == "READY"
    else:
        status = "READY" if not warnings else "NEEDS_REVIEW"
        usable_for_stats = status == "READY"
        identity_key = f"{repaired_canonical}|{unit_key}" if status == "READY" else None
    aliases["article_code"].append(repaired_article)
    aliases["canonical_article_code"].append(repaired_canonical)
    aliases["revision_code"].extend(repaired_revisions)
    return ArticleResolution(
        identity_key=identity_key,
        repaired_article_code=repaired_article,
        repaired_canonical_article_code=repaired_canonical,
        repaired_revision_codes=repaired_revisions,
        canonical_unit=unit_key,
        article_quality_status=status,
        usable_for_stats=usable_for_stats,
        method=method,
        confidence=confidence,
        warnings=warnings,
        aliases={key: sorted(set(value for value in values if value)) for key, values in aliases.items()},
        canonical_chapter_title=canonical_chapter,
        description_hint=description_hint,
    )


def extract_declared_work_total(*texts: str) -> float | None:
    for text in texts:
        if not text:
            continue
        lines = [" ".join(line.split()) for line in text.splitlines()]
        for index, line in enumerate(lines):
            normalized_line = strip_accents(line).lower()
            if "εργασιες προυπολογισμου" not in normalized_line:
                continue
            for candidate in lines[index + 1 : index + 6]:
                if re.fullmatch(r"\d{1,9}(?:\.\d{3})*(?:[,.]\d{1,2})?", candidate):
                    return parse_greek_decimal(candidate)
        normalized = strip_accents(text)
        match = re.search(
            r"\bΑθροισμα\s+(\d{1,9}(?:\.\d{3})*(?:[,.]\d{1,2})?)",
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            return parse_greek_decimal(match.group(1))
    return None


def project_key(source_root: Path, project_path: Path) -> str:
    try:
        relative = str(project_path.relative_to(source_root))
    except ValueError:
        relative = str(project_path)
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
    return f"geo-{digest}"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", XLSX_NS):
        strings.append("".join(node.text or "" for node in item.findall(".//a:t", XLSX_NS)))
    return strings


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value = cell.find("a:v", XLSX_NS)
    if value is None or value.text is None:
        return ""
    text = value.text
    if cell.get("t") == "s" and text.isdigit():
        index = int(text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        number = float(text)
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")
    return text


def _xlsx_sheet_rows(path: Path) -> list[tuple[str, int, list[str]]]:
    rows: list[tuple[str, int, list[str]]] = []
    with zipfile.ZipFile(path) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        worksheet_names = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        for worksheet_name in worksheet_names:
            sheet_name = Path(worksheet_name).stem
            root = ET.fromstring(archive.read(worksheet_name))
            for row in root.findall(".//a:row", XLSX_NS):
                values = [_xlsx_cell_value(cell, shared_strings) for cell in row.findall("a:c", XLSX_NS)]
                while values and values[-1] == "":
                    values.pop()
                if values:
                    rows.append((sheet_name, int(row.get("r") or 0), values))
    return rows


def extract_xlsx_text(path: Path) -> str:
    lines: list[str] = []
    current_sheet = None
    for sheet_name, _row_index, values in _xlsx_sheet_rows(path):
        if sheet_name != current_sheet:
            current_sheet = sheet_name
            lines.append(f"### SHEET {sheet_name}")
        if any(value.strip() for value in values):
            lines.append(" ".join(value.replace("\n", " ").strip() for value in values if value.strip()))
    return "\n".join(lines)


def extract_word_text(path: Path, output_root: Path) -> str:
    conversion_key = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    output_dir = output_root / f"word-{conversion_key}"
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(output_dir),
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {completed.stderr or completed.stdout}".strip())
    text_path = output_dir / f"{path.stem}.txt"
    if not text_path.exists():
        candidates = sorted(output_dir.glob("*.txt"))
        if not candidates:
            raise RuntimeError("LibreOffice conversion did not create a text file")
        text_path = candidates[0]
    return text_path.read_text(encoding="utf-8", errors="replace")


def extract_geo_budget_text(path: Path, *, text_dir: Path | None = None) -> str:
    if path.suffix.casefold() == ".xlsx":
        return extract_xlsx_text(path)
    if path.suffix.casefold() in {".doc", ".docx", ".rtf", ".odt"}:
        return extract_word_text(path, text_dir or (REPO_ROOT / "geo_afoi_pricing/work/extracted_text"))
    return extract_budget_text(path)


def _parse_xlsx_number(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return parse_greek_decimal(value)
    return int(number) if number.is_integer() else round(number, 4)


def _parse_word_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    match = re.match(r"^-?(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[,.]\d+)?)", text)
    if not match:
        return None
    return parse_greek_decimal(match.group(0))


def _looks_like_word_unit(value: str) -> bool:
    text = normalize_alias(value).casefold()
    return text in {"m", "m2", "m3", "t", "kg", "kgr", "τεμ", "τεμ.", "μμ", "mm", "στρ", "στρ."}


def parse_budget_rows_from_word_text(text: str) -> list[PricingBudgetRow]:
    clean_lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in clean_lines if line]
    rows: list[PricingBudgetRow] = []
    index = 0
    while index < len(lines) - 7:
        local_number = _parse_word_number(lines[index])
        if local_number is None or not float(local_number).is_integer():
            index += 1
            continue
        description = lines[index + 1]
        article_code = lines[index + 2]
        if not re.match(r"^(ΝΕΤ|ΝΕΟ)\b", strip_accents(article_code).upper()):
            index += 1
            continue
        at_number = _parse_word_number(lines[index + 3])
        if at_number is None or not float(at_number).is_integer():
            index += 1
            continue
        unit_index = None
        for candidate_index in range(index + 4, min(len(lines), index + 9)):
            if _looks_like_word_unit(lines[candidate_index]):
                unit_index = candidate_index
                break
        if unit_index is None or unit_index + 3 >= len(lines):
            index += 1
            continue
        revision_lines = lines[index + 4 : unit_index]
        quantity = _parse_word_number(lines[unit_index + 1])
        unit_price = _parse_word_number(lines[unit_index + 2])
        if quantity is None or unit_price is None:
            index += 1
            continue
        amount = None
        amount_index = unit_index + 3
        while amount_index < min(len(lines), unit_index + 7):
            candidate = lines[amount_index]
            if not candidate.startswith("("):
                amount = _parse_word_number(candidate)
                if amount is not None:
                    break
            amount_index += 1
        if amount is None:
            index += 1
            continue
        raw_lines = lines[index : amount_index + 1]
        raw_text = " ".join(raw_lines)
        revision_codes = _extract_repaired_revision_codes(" ".join(revision_lines), article_code)
        rows.append(
            PricingBudgetRow(
                row_number=int(at_number),
                article_code=article_code,
                canonical_article_code=canonical_article_code(article_code),
                description=description,
                revision_codes=revision_codes,
                unit=lines[unit_index],
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                raw_text=raw_text,
                confidence=0.86,
            )
        )
        index = amount_index + 1
    return rows


FIXED_COLUMN_UNIT_PATTERN = r"(?:μ3|μ2|μ|m3|m2|m|kgr|kg|ton|t|τεμ|στρ)"
FIXED_COLUMN_ROW_RE = re.compile(
    rf"^\s*(?P<row>\d{{1,3}})\s+"
    rf"(?P<article>[A-ZΑ-Ωα-ωΝν.Ττ0-9/-]+)\s+"
    rf"(?P<body>.*?)\s+"
    rf"(?P<revision_num>\d+[Α-ΩA-Z.0-9]*)\s+"
    rf"(?P<unit>{FIXED_COLUMN_UNIT_PATTERN})\s+"
    rf"(?P<quantity>\d{{1,9}}(?:[.,]\d+)?)\s+"
    rf"(?P<unit_price>\d{{1,9}}(?:[.,]\d+)?)\s+"
    rf"(?P<amount>\d{{1,3}}(?:\.\d{{3}})*(?:,\d{{2}})?|\d+(?:,\d{{2}})?)"
    rf"(?:\s+\d{{1,3}}(?:\.\d{{3}})*(?:,\d{{2}})?)?\s*$",
    flags=re.IGNORECASE,
)
FIXED_COLUMN_ROW_WITHOUT_NUMBER_RE = re.compile(
    rf"^\s*(?P<article>[A-ZΑ-Ωα-ωΝν.Ττ0-9/-]+)\s+"
    rf"(?P<body>.*?)\s+"
    rf"(?P<revision_num>\d+[Α-ΩA-Z.0-9]*)\s+"
    rf"(?P<unit>{FIXED_COLUMN_UNIT_PATTERN})\s+"
    rf"(?P<quantity>\d{{1,9}}(?:[.,]\d+)?)\s+"
    rf"(?P<unit_price>\d{{1,9}}(?:[.,]\d+)?)\s+"
    rf"(?P<amount>\d{{1,3}}(?:\.\d{{3}})*(?:,\d{{2}})?|\d+(?:,\d{{2}})?)"
    rf"(?:\s+\d{{1,3}}(?:\.\d{{3}})*(?:,\d{{2}})?)?\s*$",
    flags=re.IGNORECASE,
)


def _fixed_column_revision_prefix(context: str) -> str | None:
    repaired = repair_mojibake_code_tokens(strip_accents(context).upper()).replace("ODO", "ΟΔΟ")
    matches = list(re.finditer(r"\b(?P<prefix>ΟΔΟ|ΥΔΡ|ΠΡΣ|ΟΙΚ)\s*-?", repaired))
    if not matches:
        return None
    return REVISION_PREFIX_REPAIRS.get(matches[-1].group("prefix"), matches[-1].group("prefix"))


def _fixed_column_context_description(context_lines: list[str], body: str) -> str:
    ignored_tokens = (
        "ΥΠΕΧΩΔΕ",
        "ΠΙΝΑΚΑΣ ΤΙΜΩΝ",
        "ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ",
        "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ",
        "AKAVAL/YPEHODE",
        "ΝΑ ΠΡΟΣΤΙΘΕΤΑΙ",
        "ΔΑΠΑΝΗ ΜΕΤΑΦΟΡΑΣ",
        "ΟΜΑΔΑ",
        "ΑΡΘΡΟ",
        "ΜΟΝΑΔΑ",
        "ΤΙΜΟΛΟΓ",
        "ΑΝΑΘΕΩΡΗΣΗΣ",
        "ΠΟΣΟΤΗΤΑ",
    )
    pieces: list[str] = []
    for line in context_lines[-8:]:
        clean = " ".join(line.split())
        if not clean:
            continue
        normalized = strip_accents(clean).upper()
        if any(token in normalized for token in ignored_tokens):
            continue
        if re.fullmatch(r"\d{1,3}", clean):
            continue
        pieces.append(clean)
    pieces.append(body)
    return " ".join(" ".join(pieces).split())


def parse_fixed_column_ypehode_rows(text: str) -> list[PricingBudgetRow]:
    if "ΠΙΝΑΚΑΣ ΤΙΜΩΝ ΜΟΝΑΔΟΣ" not in strip_accents(text).upper():
        return []
    rows: list[PricingBudgetRow] = []
    context_lines: list[str] = []
    for raw_line in text.splitlines():
        clean = " ".join(raw_line.split())
        if not clean:
            continue
        match = FIXED_COLUMN_ROW_RE.match(clean)
        inferred_row_number = None
        if not match and rows:
            missing_number_match = FIXED_COLUMN_ROW_WITHOUT_NUMBER_RE.match(clean)
            if missing_number_match:
                match = missing_number_match
                inferred_row_number = rows[-1].row_number + 1
        if not match:
            context_lines.append(clean)
            continue
        revision_prefix = _fixed_column_revision_prefix(" ".join([*context_lines[-8:], clean]))
        revision_num = normalize_revision_number(match.group("revision_num"))
        revision_codes = [f"{revision_prefix}-{revision_num}"] if revision_prefix else []
        article_code = " ".join(match.group("article").split())
        description = _fixed_column_context_description(context_lines, match.group("body"))
        quantity = parse_greek_decimal(match.group("quantity"))
        unit_price = parse_greek_decimal(match.group("unit_price"))
        amount = parse_greek_decimal(match.group("amount"))
        row_number = int(match.group("row")) if "row" in match.groupdict() and match.groupdict().get("row") else int(inferred_row_number or 0)
        raw_text = " ".join(
            str(value)
            for value in (
                article_code,
                " ".join(revision_codes),
                match.group("unit"),
                quantity,
                unit_price,
                amount,
            )
            if value not in (None, "")
        )
        rows.append(
            PricingBudgetRow(
                row_number=row_number,
                article_code=article_code,
                canonical_article_code=canonical_article_code(article_code),
                description=description,
                revision_codes=revision_codes,
                unit=match.group("unit"),
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                raw_text=raw_text,
                confidence=0.84,
            )
        )
        context_lines = []
    return rows


def parse_budget_rows_from_xlsx(path: Path) -> list[PricingBudgetRow]:
    rows: list[PricingBudgetRow] = []
    for sheet_name, row_index, values in _xlsx_sheet_rows(path):
        if len(values) < 9:
            continue
        local_number = _parse_xlsx_number(values[0])
        at_number = _parse_xlsx_number(values[4]) if len(values) > 4 else None
        quantity = _parse_xlsx_number(values[6]) if len(values) > 6 else None
        unit_price = _parse_xlsx_number(values[7]) if len(values) > 7 else None
        amount = _parse_xlsx_number(values[8]) if len(values) > 8 else None
        if local_number is None or quantity is None or unit_price is None or amount is None:
            continue
        article_code = " ".join(str(values[2]).split())
        description = " ".join(str(values[1]).split())
        if not article_code or not description:
            continue
        revision_codes = []
        revision_text = " ".join(str(values[3]).split()) if len(values) > 3 else ""
        if revision_text:
            revision_codes.append(revision_text)
        unit = " ".join(str(values[5]).split()) if len(values) > 5 else None
        row_number = int(at_number) if at_number is not None and float(at_number).is_integer() else int(local_number)
        raw_text = " ".join(str(value).replace("\n", " ").strip() for value in values if str(value).strip())
        rows.append(
            PricingBudgetRow(
                row_number=row_number,
                article_code=article_code,
                canonical_article_code=canonical_article_code(article_code),
                description=description,
                revision_codes=revision_codes,
                unit=unit or None,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                raw_text=raw_text,
                confidence=0.92,
            )
        )
    return rows


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = load_yaml(path)
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return config


def classify_source_file(path: Path, config: dict[str, Any]) -> FileClassification:
    inventory = config.get("inventory") if isinstance(config.get("inventory"), dict) else {}
    candidates = (
        config.get("budget_document_candidates")
        if isinstance(config.get("budget_document_candidates"), dict)
        else {}
    )
    ignored_names = {str(item) for item in inventory.get("ignored_names", [])}
    ignored_extensions = {str(item).casefold() for item in inventory.get("ignored_extensions", [])}
    extension = path.suffix.casefold()
    if path.name in ignored_names or extension in ignored_extensions:
        return FileClassification("IGNORED", "ignored_name_or_extension", 0, ignored=True)

    normalized = normalize_for_match(" ".join(path.parts[-4:]))
    excluded_terms = [normalize_for_match(str(item)) for item in candidates.get("excluded_offer_terms", [])]
    if any(term and term in normalized for term in excluded_terms):
        return FileClassification("OFFER_EXCLUDED", "excluded_offer_term", -100, ignored=True)

    strong_terms = [normalize_for_match(str(item)) for item in candidates.get("strong_filename_terms", [])]
    weak_terms = [normalize_for_match(str(item)) for item in candidates.get("weak_filename_terms", [])]
    if any(term and term in normalized for term in strong_terms):
        score = 100
        if extension == ".pdf":
            score += 20
        if extension in {".xls", ".xlsx", ".ods"}:
            score += 10
        return FileClassification("BUDGET_CANDIDATE", "strong_filename_term", score)
    if any(term and term in normalized for term in weak_terms):
        return FileClassification("WEAK_BUDGET_CANDIDATE", "weak_filename_term", 30)
    return FileClassification("UNKNOWN", "no_budget_signal", 0)


def init_database(db_path: Path, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _migrate_database(connection)
        connection.commit()
    finally:
        connection.close()


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _migrate_database(connection: sqlite3.Connection) -> None:
    chapter_columns = _table_columns(connection, "geo_budget_chapters")
    chapter_additions = {
        "repaired_chapter_title": "TEXT",
        "canonical_chapter_title": "TEXT",
        "chapter_quality_status": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    }
    for column, definition in chapter_additions.items():
        if column not in chapter_columns:
            connection.execute(f"ALTER TABLE geo_budget_chapters ADD COLUMN {column} {definition}")
    row_columns = _table_columns(connection, "geo_budget_rows")
    row_additions = {
        "article_identity_id": "INTEGER REFERENCES geo_article_identities(id)",
        "repaired_article_code": "TEXT",
        "repaired_canonical_article_code": "TEXT",
        "repaired_revision_codes_json": "TEXT NOT NULL DEFAULT '[]'",
        "article_quality_status": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
        "usable_for_stats": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in row_additions.items():
        if column not in row_columns:
            connection.execute(f"ALTER TABLE geo_budget_rows ADD COLUMN {column} {definition}")
    stats_columns = _table_columns(connection, "geo_article_stats")
    if "article_identity_id" not in stats_columns:
        connection.execute("ALTER TABLE geo_article_stats ADD COLUMN article_identity_id INTEGER REFERENCES geo_article_identities(id)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_geo_budget_rows_identity ON geo_budget_rows(article_identity_id)"
    )


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def upsert_project(
    connection: sqlite3.Connection,
    *,
    source_root: Path,
    project_path: Path,
    run_at: str,
) -> int:
    key = project_key(source_root, project_path)
    connection.execute(
        """
        INSERT INTO geo_projects (
            project_key, source_root, project_path, project_name,
            first_seen_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_key) DO UPDATE SET
            source_root = excluded.source_root,
            project_path = excluded.project_path,
            project_name = excluded.project_name,
            updated_at = excluded.updated_at
        """,
        (key, str(source_root), str(project_path), project_path.name, run_at, run_at),
    )
    row = connection.execute(
        "SELECT id FROM geo_projects WHERE project_key = ?",
        (key,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Failed to upsert project: {project_path}")
    return int(row["id"])


def upsert_source_file(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    source_root: Path,
    source_path: Path,
    classification: FileClassification,
    run_at: str,
    sha256: str | None = None,
) -> int:
    stat = source_path.stat()
    try:
        relative = str(source_path.relative_to(source_root))
    except ValueError:
        relative = source_path.name
    modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO geo_source_files (
            project_id, source_path, relative_path, file_name, extension,
            size_bytes, modified_at, sha256, document_role, candidate_reason,
            first_seen_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            project_id = excluded.project_id,
            relative_path = excluded.relative_path,
            file_name = excluded.file_name,
            extension = excluded.extension,
            size_bytes = excluded.size_bytes,
            modified_at = excluded.modified_at,
            sha256 = COALESCE(excluded.sha256, geo_source_files.sha256),
            document_role = excluded.document_role,
            candidate_reason = excluded.candidate_reason,
            updated_at = excluded.updated_at
        """,
        (
            project_id,
            str(source_path),
            relative,
            source_path.name,
            source_path.suffix.casefold(),
            stat.st_size,
            modified_at,
            sha256,
            classification.role,
            classification.reason,
            run_at,
            run_at,
        ),
    )
    row = connection.execute(
        "SELECT id FROM geo_source_files WHERE source_path = ?",
        (str(source_path),),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Failed to upsert source file: {source_path}")
    return int(row["id"])


def extract_chapter_candidates(text: str) -> list[ChapterCandidate]:
    chapters: list[ChapterCandidate] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        clean = " ".join(raw_line.split())
        if not clean:
            continue
        normalized = strip_accents(clean).upper()
        if "ΣΥΝΟΛ" in normalized:
            continue
        if re.search(r"\d{1,3}(?:[.,]\d{2,3})", clean):
            continue
        match = re.match(
            r"^(?:(ΟΜΑΔΑ|ΥΠΟΟΜΑΔΑ|ΚΕΦΑΛΑΙΟ)\s+([Α-ΩA-Z0-9]+)\s*[:.-]?\s+|(\d{1,2})[.)]\s+)(.+)$",
            clean,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        title = match.group(4).strip()
        title_norm = strip_accents(title).upper()
        if len(title) < 4 or any(token in title_norm for token in ("ΠΡΟΥΠΟΛΟΓΙΣ", "ΣΕΛΙΔΑ")):
            continue
        code = match.group(2) or match.group(3)
        chapters.append(
            ChapterCandidate(
                line_number=line_number,
                chapter_code=code,
                chapter_title=title,
                confidence=0.75,
            )
        )
    return chapters


def locate_row_line(text: str, row: PricingBudgetRow, *, start_line: int = 1) -> int | None:
    lines = text.splitlines()
    article = normalize_for_match(row.article_code).replace(" ", "")
    canonical = normalize_for_match(row.canonical_article_code).replace(" ", "")
    for index, raw_line in enumerate(lines[start_line - 1 :], start=start_line):
        normalized = normalize_for_match(raw_line).replace(" ", "")
        if article and article in normalized:
            return index
        if canonical and canonical in normalized:
            return index
        article_tokens = [normalize_for_match(token).replace(" ", "") for token in row.article_code.split()]
        if len(article_tokens) >= 2 and article_tokens[0] and article_tokens[0] in normalized:
            lookahead = " ".join(lines[index : min(len(lines), index + 3)])
            normalized_lookahead = normalize_for_match(lookahead).replace(" ", "")
            if any(token and re.search(r"\d", token) and token in normalized_lookahead for token in article_tokens[1:]):
                return index
    return None


def chapter_for_line(chapters: list[ChapterCandidate], line_number: int | None) -> ChapterCandidate | None:
    if line_number is None:
        return None
    previous = [chapter for chapter in chapters if chapter.line_number <= line_number]
    return previous[-1] if previous else None


def upsert_chapter(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    source_file_id: int,
    chapter: ChapterCandidate,
) -> int:
    repaired_title = repair_mojibake_chapter_title(chapter.chapter_title)
    canonical_title = normalize_for_match(repaired_title or chapter.chapter_title).upper()
    quality_status = chapter_quality_status(chapter.chapter_title, repaired_title)
    connection.execute(
        """
        INSERT INTO geo_budget_chapters (
            project_id, source_file_id, chapter_code, chapter_title,
            repaired_chapter_title, canonical_chapter_title, row_order,
            confidence, chapter_quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, source_file_id, chapter_code, chapter_title)
        DO UPDATE SET
            repaired_chapter_title = excluded.repaired_chapter_title,
            canonical_chapter_title = excluded.canonical_chapter_title,
            row_order = excluded.row_order,
            confidence = excluded.confidence,
            chapter_quality_status = excluded.chapter_quality_status
        """,
        (
            project_id,
            source_file_id,
            chapter.chapter_code,
            chapter.chapter_title,
            repaired_title,
            canonical_title,
            chapter.line_number,
            chapter.confidence,
            quality_status,
        ),
    )
    row = connection.execute(
        """
        SELECT id FROM geo_budget_chapters
        WHERE project_id = ? AND source_file_id = ?
          AND COALESCE(chapter_code, '') = COALESCE(?, '')
          AND chapter_title = ?
        """,
        (project_id, source_file_id, chapter.chapter_code, chapter.chapter_title),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Failed to upsert chapter: {chapter.chapter_title}")
    return int(row["id"])


def upsert_article_identity(
    connection: sqlite3.Connection,
    *,
    resolution: ArticleResolution,
    run_at: str,
) -> int | None:
    if not resolution.identity_key:
        return None
    connection.execute(
        """
        INSERT INTO geo_article_identities (
            identity_key, canonical_article_code, canonical_revision_codes_json,
            canonical_unit, canonical_chapter_title, status, first_seen_at,
            updated_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(identity_key) DO UPDATE SET
            canonical_article_code = excluded.canonical_article_code,
            canonical_revision_codes_json = excluded.canonical_revision_codes_json,
            canonical_unit = excluded.canonical_unit,
            canonical_chapter_title = COALESCE(geo_article_identities.canonical_chapter_title, excluded.canonical_chapter_title),
            status = CASE
                WHEN geo_article_identities.status = 'READY' AND excluded.status = 'NEEDS_REVIEW' THEN geo_article_identities.status
                ELSE excluded.status
            END,
            updated_at = excluded.updated_at,
            metadata_json = excluded.metadata_json
        """,
        (
            resolution.identity_key,
            resolution.repaired_canonical_article_code,
            json.dumps(resolution.repaired_revision_codes, ensure_ascii=False),
            resolution.canonical_unit,
            resolution.canonical_chapter_title,
            resolution.article_quality_status,
            run_at,
            run_at,
            json.dumps(
                {
                    "method": resolution.method,
                    "confidence": resolution.confidence,
                    "warnings": resolution.warnings,
                    "description_hint": resolution.description_hint,
                    "canonical_unit": resolution.canonical_unit,
                },
                ensure_ascii=False,
            ),
        ),
    )
    row = connection.execute(
        "SELECT id FROM geo_article_identities WHERE identity_key = ?",
        (resolution.identity_key,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Failed to upsert article identity: {resolution.identity_key}")
    identity_id = int(row["id"])
    for alias_type, values in resolution.aliases.items():
        for value in values:
            connection.execute(
                """
                INSERT OR IGNORE INTO geo_article_aliases (
                    identity_id, alias_type, alias_value, normalized_alias,
                    source, confidence, review_status, rationale, first_seen_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity_id,
                    alias_type,
                    value,
                    normalize_alias(value),
                    resolution.method,
                    resolution.confidence,
                    resolution.article_quality_status,
                    "; ".join(resolution.warnings) or "accepted by pilot article resolver",
                    run_at,
                    json.dumps({"identity_key": resolution.identity_key}, ensure_ascii=False),
                ),
            )
    return identity_id


def replace_budget_rows(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    source_file_id: int,
    rows: list[PricingBudgetRow],
    text: str,
    ocr_text: str,
    run_at: str,
) -> dict[str, Any]:
    connection.execute(
        "DELETE FROM geo_budget_rows WHERE project_id = ? AND source_file_id = ?",
        (project_id, source_file_id),
    )
    connection.execute(
        "DELETE FROM geo_budget_chapters WHERE project_id = ? AND source_file_id = ?",
        (project_id, source_file_id),
    )
    chapters = extract_chapter_candidates(text)
    chapter_ids: dict[tuple[str | None, str], int] = {}
    last_line = 1
    unassigned = 0
    inserted = 0
    ready_articles = 0
    ready_non_stats_articles = 0
    needs_review_articles = 0
    usable_for_stats = 0
    repaired_article_changes = 0
    identities_linked: set[int] = set()
    row_quality_samples: list[dict[str, Any]] = []
    needs_review_rows: list[dict[str, Any]] = []
    non_stat_rows: list[dict[str, Any]] = []
    for row in rows:
        line_number = locate_row_line(text, row, start_line=last_line) or locate_row_line(text, row)
        if line_number:
            last_line = line_number + 1
        chapter = chapter_for_line(chapters, line_number)
        chapter_id = None
        if chapter:
            key = (chapter.chapter_code, chapter.chapter_title)
            chapter_id = chapter_ids.get(key)
            if chapter_id is None:
                chapter_id = upsert_chapter(
                    connection,
                    project_id=project_id,
                    source_file_id=source_file_id,
                    chapter=chapter,
                )
                chapter_ids[key] = chapter_id
        else:
            unassigned += 1
        resolution = resolve_article_identity(row, chapter=chapter, ocr_text=ocr_text)
        identity_id = upsert_article_identity(connection, resolution=resolution, run_at=run_at)
        if identity_id is not None:
            identities_linked.add(identity_id)
        if resolution.article_quality_status == "READY":
            ready_articles += 1
        elif resolution.article_quality_status == "NEEDS_REVIEW":
            needs_review_articles += 1
        else:
            ready_non_stats_articles += 1
        row_summary = {
            "row_number": row.row_number,
            "raw_article_code": row.article_code,
            "repaired_article_code": resolution.repaired_article_code,
            "repaired_canonical_article_code": resolution.repaired_canonical_article_code,
            "repaired_revision_codes": resolution.repaired_revision_codes,
            "identity_key": resolution.identity_key,
            "status": resolution.article_quality_status,
            "unit": row.unit,
            "canonical_unit": resolution.canonical_unit,
            "quantity": row.quantity,
            "unit_price": row.unit_price,
            "amount": row.amount,
            "description": row.description,
            "warnings": resolution.warnings,
        }
        if resolution.article_quality_status == "NEEDS_REVIEW" and len(needs_review_rows) < 100:
            needs_review_rows.append(row_summary)
        elif not resolution.usable_for_stats and len(non_stat_rows) < 100:
            non_stat_rows.append(row_summary)
        if resolution.usable_for_stats:
            usable_for_stats += 1
        if resolution.repaired_canonical_article_code != row.canonical_article_code:
            repaired_article_changes += 1
        if len(row_quality_samples) < 40:
            row_quality_samples.append(
                {
                    "row_number": row.row_number,
                    "raw_article_code": row.article_code,
                    "raw_canonical_article_code": row.canonical_article_code,
                    "repaired_article_code": resolution.repaired_article_code,
                    "repaired_canonical_article_code": resolution.repaired_canonical_article_code,
                    "repaired_revision_codes": resolution.repaired_revision_codes,
                    "identity_key": resolution.identity_key,
                    "canonical_unit": resolution.canonical_unit,
                    "status": resolution.article_quality_status,
                    "usable_for_stats": resolution.usable_for_stats,
                    "method": resolution.method,
                    "warnings": resolution.warnings,
                    "description_hint": resolution.description_hint,
                }
            )
        connection.execute(
            """
            INSERT OR REPLACE INTO geo_budget_rows (
                project_id, source_file_id, chapter_id, article_identity_id,
                row_number, article_code, canonical_article_code,
                repaired_article_code, repaired_canonical_article_code,
                revision_codes_json, repaired_revision_codes_json,
                description, unit, quantity, unit_price, amount, line_ref,
                raw_text, confidence, article_quality_status, usable_for_stats,
                extracted_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                source_file_id,
                chapter_id,
                identity_id,
                row.row_number,
                row.article_code,
                row.canonical_article_code,
                resolution.repaired_article_code,
                resolution.repaired_canonical_article_code,
                json.dumps(row.revision_codes, ensure_ascii=False),
                json.dumps(resolution.repaired_revision_codes, ensure_ascii=False),
                row.description,
                row.unit,
                row.quantity,
                row.unit_price,
                row.amount,
                f"line:{line_number}" if line_number else None,
                row.raw_text,
                row.confidence,
                resolution.article_quality_status,
                1 if resolution.usable_for_stats else 0,
                run_at,
                json.dumps({"row": asdict(row), "article_resolution": asdict(resolution)}, ensure_ascii=False),
            ),
        )
        inserted += 1
    return {
        "rows_inserted": inserted,
        "chapter_candidates": len(chapters),
        "chapters_linked": len(chapter_ids),
        "unassigned_rows": unassigned,
        "article_quality": {
            "ready": ready_articles,
            "ready_non_stats": ready_non_stats_articles,
            "needs_review": needs_review_articles,
            "usable_for_stats": usable_for_stats,
            "repaired_article_changes": repaired_article_changes,
            "identities_linked": len(identities_linked),
            "row_samples": row_quality_samples,
            "needs_review_rows": needs_review_rows,
            "non_stat_rows": non_stat_rows,
        },
    }


def refresh_article_stats(connection: sqlite3.Connection, *, run_at: str) -> dict[str, Any]:
    live_identity_ids = """
        SELECT DISTINCT article_identity_id
        FROM geo_budget_rows
        WHERE article_identity_id IS NOT NULL
    """
    connection.execute(
        f"DELETE FROM geo_article_aliases WHERE identity_id NOT IN ({live_identity_ids})"
    )
    connection.execute(
        f"DELETE FROM geo_article_identities WHERE id NOT IN ({live_identity_ids})"
    )
    connection.execute("DELETE FROM geo_article_stats")
    groups: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in connection.execute(
        """
        SELECT
            br.project_id,
            br.article_identity_id,
            br.unit_price,
            ai.canonical_article_code,
            ai.canonical_unit,
            COALESCE(
                c.canonical_chapter_title,
                c.repaired_chapter_title,
                c.chapter_title,
                'UNKNOWN'
            ) AS chapter_title
        FROM geo_budget_rows br
        JOIN geo_article_identities ai ON ai.id = br.article_identity_id
        LEFT JOIN geo_budget_chapters c ON c.id = br.chapter_id
        WHERE br.usable_for_stats = 1
          AND br.article_identity_id IS NOT NULL
          AND br.unit_price IS NOT NULL
        """
    ):
        groups.setdefault((int(row["article_identity_id"]), str(row["chapter_title"])), []).append(row)

    inserted = 0
    for (identity_id, chapter_title), rows in groups.items():
        prices = [float(row["unit_price"]) for row in rows]
        if not prices:
            continue
        project_count = len({int(row["project_id"]) for row in rows})
        connection.execute(
            """
            INSERT INTO geo_article_stats (
                article_identity_id, canonical_article_code, chapter_title, unit,
                sample_count, project_count, mean_unit_price, median_unit_price,
                min_unit_price, max_unit_price, stdev_unit_price, computed_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_article_code, chapter_title, unit) DO UPDATE SET
                article_identity_id = excluded.article_identity_id,
                sample_count = excluded.sample_count,
                project_count = excluded.project_count,
                mean_unit_price = excluded.mean_unit_price,
                median_unit_price = excluded.median_unit_price,
                min_unit_price = excluded.min_unit_price,
                max_unit_price = excluded.max_unit_price,
                stdev_unit_price = excluded.stdev_unit_price,
                computed_at = excluded.computed_at,
                metadata_json = excluded.metadata_json
            """,
            (
                identity_id,
                str(rows[0]["canonical_article_code"]),
                chapter_title,
                str(rows[0]["canonical_unit"] or "UNKNOWN"),
                len(prices),
                project_count,
                round(statistics.fmean(prices), 6),
                round(statistics.median(prices), 6),
                min(prices),
                max(prices),
                round(statistics.pstdev(prices), 6) if len(prices) > 1 else 0.0,
                run_at,
                json.dumps(
                    {
                        "source": "geo_afoi_pricing.refresh_article_stats",
                        "grouping": "article_identity_id+canonical_chapter_title+canonical_unit",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        inserted += 1

    reusable_groups = connection.execute(
        "SELECT COUNT(*) FROM geo_article_stats WHERE sample_count >= 2"
    ).fetchone()[0]
    return {
        "stats_rows": inserted,
        "reusable_stats_rows": int(reusable_groups),
    }


def write_event(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    level: str,
    event_type: str,
    message: str,
    project_id: int | None = None,
    source_file_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO geo_extraction_events (
            run_id, project_id, source_file_id, level, event_type,
            message, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            project_id,
            source_file_id,
            level,
            event_type,
            message,
            utc_now_iso(),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def iter_project_files(project_path: Path, *, max_depth: int) -> list[Path]:
    root_depth = len(project_path.parts)
    files: list[Path] = []
    for path in sorted(project_path.rglob("*")):
        if not path.is_file():
            continue
        depth = len(path.parts) - root_depth
        if depth > max_depth:
            continue
        files.append(path)
    return files


def run_one_project(
    *,
    config_path: Path,
    project_path: Path,
    document_path: Path | None = None,
    db_path: Path | None = None,
    report_prefix: Path | None = None,
    max_candidate_documents: int | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    source_root = Path(str(config["source_root"]))
    database_path = db_path or (REPO_ROOT / str(config["database_path"]))
    reports_dir = REPO_ROOT / str(config.get("reports_dir", "geo_afoi_pricing/reports"))
    report_prefix = report_prefix or (reports_dir / "pilot_one_project")
    inventory = config.get("inventory") if isinstance(config.get("inventory"), dict) else {}
    pilot = config.get("pilot") if isinstance(config.get("pilot"), dict) else {}
    max_depth = int(inventory.get("max_depth") or 8)
    max_candidate_documents = int(max_candidate_documents or pilot.get("max_candidate_documents_per_project") or 5)
    run_at = utc_now_iso()
    run_id = f"geo-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    init_database(database_path)
    report_prefix.parent.mkdir(parents=True, exist_ok=True)
    text_dir = REPO_ROOT / str(config.get("work_dir", "geo_afoi_pricing/work")) / "extracted_text"
    text_dir.mkdir(parents=True, exist_ok=True)

    connection = connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO geo_runs (run_id, mode, source_root, started_at, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, "pilot_one_project", str(source_root), run_at, "RUNNING"),
        )
        project_id = upsert_project(
            connection,
            source_root=source_root,
            project_path=project_path,
            run_at=run_at,
        )
        inventory_mode = "direct_document" if document_path else "project_scan"
        if document_path:
            files = [document_path]
            classification = classify_source_file(document_path, config)
            if classification.ignored:
                raise ValueError(f"Direct document is excluded by classification: {document_path}")
            candidate_paths = [(document_path, classification)]
            classifications = candidate_paths
        else:
            files = iter_project_files(project_path, max_depth=max_depth)
            classifications = [(path, classify_source_file(path, config)) for path in files]
            candidate_paths = [
                (path, classification)
                for path, classification in classifications
                if classification.role == "BUDGET_CANDIDATE"
            ]
            candidate_paths.sort(key=lambda item: (-item[1].score, str(item[0])))

        source_file_ids: dict[Path, int] = {}
        paths_to_persist = {candidate for candidate, _ in candidate_paths[:max_candidate_documents]}
        for path, classification in classifications:
            if path not in paths_to_persist:
                continue
            digest = None
            if path in paths_to_persist:
                digest = sha256_file(path)
            source_file_ids[path] = upsert_source_file(
                connection,
                project_id=project_id,
                source_root=source_root,
                source_path=path,
                classification=classification,
                run_at=run_at,
                sha256=digest,
            )

        extracted_documents: list[dict[str, Any]] = []
        failed_documents: list[dict[str, Any]] = []
        for path, classification in candidate_paths[:max_candidate_documents]:
            source_file_id = source_file_ids[path]
            supported_extensions = {".pdf", ".txt", ".text", ".xlsx", ".doc", ".docx", ".rtf", ".odt"}
            if path.suffix.casefold() not in supported_extensions:
                failed_documents.append(
                    {
                        "path": str(path),
                        "status": "SKIPPED_UNSUPPORTED_EXTENSION",
                        "reason": "pilot supports PDF/TXT/XLSX/Word budget extraction first",
                    }
                )
                write_event(
                    connection,
                    run_id=run_id,
                    project_id=project_id,
                    source_file_id=source_file_id,
                    level="WARNING",
                    event_type="SKIPPED_UNSUPPORTED_EXTENSION",
                    message="Pilot extraction currently supports PDF/TXT/XLSX/Word budget documents first.",
                    metadata={"path": str(path), "extension": path.suffix},
                )
                continue
            try:
                text = extract_geo_budget_text(path, text_dir=text_dir)
                text_path = text_dir / f"{project_key(source_root, project_path)}-{source_file_id}.txt"
                text_path.write_text(text, encoding="utf-8")
                text_layer_mojibake = path.suffix.casefold() == ".pdf" and looks_like_greek_font_mojibake(text)
                ocr_text = ""
                ocr_text_path = None
                if text_layer_mojibake and path.suffix.casefold() == ".pdf":
                    ocr_text = _ocr_pdf_for_budget(path, max_pages=6) or ""
                    if ocr_text:
                        ocr_text_path = text_dir / f"{project_key(source_root, project_path)}-{source_file_id}.ocr.txt"
                        ocr_text_path.write_text(ocr_text, encoding="utf-8")
                extension = path.suffix.casefold()
                if extension == ".xlsx":
                    rows = parse_budget_rows_from_xlsx(path)
                elif extension in {".doc", ".docx", ".rtf", ".odt"}:
                    rows = parse_budget_rows_from_word_text(text)
                else:
                    fixed_column_rows = parse_fixed_column_ypehode_rows(text)
                    rows = fixed_column_rows or parse_budget_rows_from_text(text)
                extraction = replace_budget_rows(
                    connection,
                    project_id=project_id,
                    source_file_id=source_file_id,
                    rows=rows,
                    text=text,
                    ocr_text=ocr_text,
                    run_at=run_at,
                )
                row_amount_total = sum(float(row.amount or 0) for row in rows)
                declared_work_total = extract_declared_work_total(ocr_text, text)
                amount_validation: dict[str, Any] = {
                    "row_amount_total": row_amount_total,
                    "declared_work_total": declared_work_total,
                    "delta": None,
                    "status": "UNKNOWN",
                }
                if declared_work_total is not None:
                    delta = round(row_amount_total - float(declared_work_total), 2)
                    amount_validation.update(
                        {
                            "delta": delta,
                            "status": "PASS" if abs(delta) <= 1 else "MISMATCH",
                        }
                    )
                source_metadata = {
                    "text_quality": {
                        "text_layer_mojibake": text_layer_mojibake,
                        "ocr_text_path": str(ocr_text_path) if ocr_text_path else None,
                        "ocr_text_chars": len(ocr_text),
                    },
                    "amount_validation": amount_validation,
                }
                connection.execute(
                    """
                    UPDATE geo_source_files
                    SET extraction_status = ?, extracted_text_path = ?,
                        metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "EXTRACTED" if rows else "NO_ROWS",
                        str(text_path),
                        json.dumps(source_metadata, ensure_ascii=False),
                        utc_now_iso(),
                        source_file_id,
                    ),
                )
                extracted_documents.append(
                    {
                        "path": str(path),
                        "role": classification.role,
                        "reason": classification.reason,
                        "score": classification.score,
                        "text_chars": len(text),
                        "text_layer_mojibake": text_layer_mojibake,
                        "ocr_text_chars": len(ocr_text),
                        "ocr_text_path": str(ocr_text_path) if ocr_text_path else None,
                        "amount_validation": amount_validation,
                        **extraction,
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive runtime audit
                failed_documents.append(
                    {"path": str(path), "status": "FAILED", "error": str(exc)}
                )
                connection.execute(
                    "UPDATE geo_source_files SET extraction_status = ?, updated_at = ? WHERE id = ?",
                    ("FAILED", utc_now_iso(), source_file_id),
                )
                write_event(
                    connection,
                    run_id=run_id,
                    project_id=project_id,
                    source_file_id=source_file_id,
                    level="ERROR",
                    event_type="EXTRACTION_FAILED",
                    message=str(exc),
                    metadata={"path": str(path)},
                )

        stats_summary = refresh_article_stats(connection, run_at=run_at)
        summary = {
            "run_id": run_id,
            "inventory_mode": inventory_mode,
            "project_path": str(project_path),
            "direct_document": str(document_path) if document_path else None,
            "project_id": project_id,
            "files_seen": len(files),
            "budget_candidates": len(candidate_paths),
            "candidate_documents": [
                {
                    "path": str(path),
                    "role": classification.role,
                    "reason": classification.reason,
                    "score": classification.score,
                }
                for path, classification in candidate_paths[:20]
            ],
            "extracted_documents": extracted_documents,
            "failed_documents": failed_documents,
            "rows_inserted": sum(int(item.get("rows_inserted") or 0) for item in extracted_documents),
            "article_stats": stats_summary,
        }
        status = "OK" if extracted_documents and not failed_documents else "WARNING"
        connection.execute(
            "UPDATE geo_runs SET finished_at = ?, status = ?, summary_json = ? WHERE run_id = ?",
            (utc_now_iso(), status, json.dumps(summary, ensure_ascii=False), run_id),
        )
        connection.commit()
    finally:
        connection.close()

    json_path = report_prefix.with_suffix(".json")
    md_path = report_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown_report(summary), encoding="utf-8")
    return {**summary, "report_json": str(json_path), "report_markdown": str(md_path)}


def render_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# GEO_AFOI Pilot One-Project Report",
        "",
        f"- Run: `{summary['run_id']}`",
        f"- Project: `{summary['project_path']}`",
        f"- Files seen: `{summary['files_seen']}`",
        f"- Budget candidates: `{summary['budget_candidates']}`",
        f"- Rows inserted: `{summary['rows_inserted']}`",
        f"- Article stats rows: `{(summary.get('article_stats') or {}).get('stats_rows', 0)}`",
        f"- Reusable stats rows: `{(summary.get('article_stats') or {}).get('reusable_stats_rows', 0)}`",
        "",
        "## Extracted Documents",
        "",
    ]
    for item in summary.get("extracted_documents", []):
        article_quality = item.get("article_quality") if isinstance(item.get("article_quality"), dict) else {}
        lines.extend(
            [
                f"- `{item['path']}`",
                f"  - rows: `{item.get('rows_inserted', 0)}`",
                f"  - chapters linked: `{item.get('chapters_linked', 0)}`",
                f"  - unassigned rows: `{item.get('unassigned_rows', 0)}`",
                f"  - text chars: `{item.get('text_chars', 0)}`",
                f"  - text layer mojibake: `{item.get('text_layer_mojibake')}`",
                f"  - OCR text chars: `{item.get('ocr_text_chars', 0)}`",
                f"  - amount validation: `{(item.get('amount_validation') or {}).get('status', 'UNKNOWN')}`",
                f"  - article identities linked: `{article_quality.get('identities_linked', 0)}`",
                f"  - article quality ready: `{article_quality.get('ready', 0)}`",
                f"  - article quality ready non-stats: `{article_quality.get('ready_non_stats', 0)}`",
                f"  - article quality needs review: `{article_quality.get('needs_review', 0)}`",
                f"  - usable for stats: `{article_quality.get('usable_for_stats', 0)}`",
                f"  - repaired article changes: `{article_quality.get('repaired_article_changes', 0)}`",
            ]
        )
        samples = article_quality.get("row_samples") if isinstance(article_quality.get("row_samples"), list) else []
        changed_samples = [
            sample
            for sample in samples
            if sample.get("raw_canonical_article_code") != sample.get("repaired_canonical_article_code")
            or sample.get("repaired_revision_codes")
            or sample.get("status") != "READY"
        ][:12]
        if changed_samples:
            lines.append("  - article repair samples:")
            for sample in changed_samples:
                lines.append(
                    "    - "
                    f"`{sample.get('raw_article_code')}` -> `{sample.get('repaired_article_code')}` "
                    f"({sample.get('status')}, `{sample.get('identity_key')}`)"
                )
        needs_review_rows = article_quality.get("needs_review_rows")
        if isinstance(needs_review_rows, list) and needs_review_rows:
            lines.append("  - needs review rows:")
            for row in needs_review_rows[:20]:
                revisions = ", ".join(row.get("repaired_revision_codes") or [])
                lines.append(
                    "    - "
                    f"AT `{row.get('row_number')}`: `{row.get('raw_article_code')}` -> "
                    f"`{row.get('repaired_article_code')}`; revision `{revisions or 'UNKNOWN'}`; "
                    f"unit `{row.get('unit')}`; qty `{row.get('quantity')}`; "
                    f"unit price `{row.get('unit_price')}`; amount `{row.get('amount')}`"
                )
        non_stat_rows = article_quality.get("non_stat_rows")
        if isinstance(non_stat_rows, list) and non_stat_rows:
            lines.append("  - ready but excluded from stats:")
            for row in non_stat_rows[:20]:
                lines.append(
                    "    - "
                    f"AT `{row.get('row_number')}`: `{row.get('raw_article_code')}` -> "
                    f"`{row.get('repaired_canonical_article_code')}` "
                    f"({row.get('status')}); qty `{row.get('quantity')}`; amount `{row.get('amount')}`"
                )
    if not summary.get("extracted_documents"):
        lines.append("- None")
    lines.extend(["", "## Candidate Documents", ""])
    for item in summary.get("candidate_documents", []):
        lines.append(f"- `{item['path']}` ({item['role']}, score `{item['score']}`)")
    lines.extend(["", "## Failures", ""])
    for item in summary.get("failed_documents", []):
        lines.append(f"- `{item['path']}`: `{item.get('status')}` {item.get('error') or item.get('reason') or ''}")
    if not summary.get("failed_documents"):
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pilot import one GEO_AFOI project budget.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--document", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--report-prefix", type=Path)
    parser.add_argument("--max-candidate-documents", type=int)
    args = parser.parse_args(argv)
    payload = run_one_project(
        config_path=args.config,
        project_path=args.project,
        document_path=args.document,
        db_path=args.db,
        report_prefix=args.report_prefix,
        max_candidate_documents=args.max_candidate_documents,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
