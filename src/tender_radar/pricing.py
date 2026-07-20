from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import re
import shutil
import sqlite3
import subprocess
import unicodedata
import uuid
from pathlib import Path
from typing import Any
import zipfile

from tender_radar.db import connect, initialize
from tender_radar.documents import analyze_document, extract_text_with_metadata
from tender_radar.sources.eshidis import parse_eshidis_attachment_xml, parse_eshidis_resource_text
from tender_radar.sources.eshidis_browser import discover_active_candidates_audit, download_attachment_audit, fetch_resource_audit


ARTICLE_RE = re.compile(
    r"^\s*(?P<row>\d{1,3})\s+(?P<article>[A-ZΑ-ΩΒB][A-ZΑ-ΩΒB0-9./-]*\d+(?:[.-]\d+)*)\s+(?P<rest>.*)$"
)
TABLE_ROW_RE = re.compile(r"^\s*(?P<row>\d{1,3})\s+(?P<rest>.+)$")
MERGED_BUDGET_SOURCE_DOCUMENT = "__PROJECT_BUDGET_MERGED__"
NUMERIC_RE = re.compile(r"^\d+(?:[.,]\d{1,3})*\*?$")
REVISION_RE = re.compile(
    r"(?:(?P<pct>\d+(?:[.,]\d+)?)\s*%)?\s*(?P<code>[A-ZΑ-ΩΟ∆Δ.]{2,8})\s*[-–—]?\s*(?P<num>\d+[A-ZΑ-ΩA-Z0-9]*)",
    re.IGNORECASE,
)
PERCENT_REVISION_RE = re.compile(
    r"(?P<pct>\d+(?:[.,]\d+)?)\s*%\s*(?P<code>Ο[∆Δ]Ο|O[∆Δ]O|ΟΙΚ|ΥΔΡ|ΠΡΣ|ΗΛΜ|ΛΙΜ)\s*[-–—]?\s*(?P<num>\d+[A-ZΑ-ΩA-Z0-9]*)",
    re.IGNORECASE,
)
KNOWN_UNITS = {
    "m",
    "m2",
    "m3",
    "μ2",
    "μ3",
    "kg",
    "kgr",
    "tn",
    "ton",
    "t",
    "tkm",
    "ton.k",
    "tonx1",
    "tonx10m",
    "ημ/σ",
    "τεμ",
    "τεμ.",
    "τεμαχ",
    "τεμαχι",
    "τεμαχιο",
    "τ.μ",
    "τ.μ.",
    "μ",
    "μ.μ",
    "μ.μ.",
    "mm",
    "μμ",
    "κ.α",
    "κ.α.",
    "m*cm",
    "dm2",
    "στρ",
    "h",
    "km",
    "lt",
}
ARTICLE_CODE_PREFIXES = {
    "ΝΑΟΔΟ",
    "ΝΟΔΟ",
    "ΟΔΟ",
    "ΝΑΥΔΡ",
    "ΥΔΡ",
    "ΝΑΟΙΚ",
    "ΟΙΚ",
    "ΠΡΣ",
    "ΝΑΠΡΣ",
    "ΗΛΜ",
    "ΝΑΗΛΜ",
    "ΑΤΗΕ",
    "ΛΙΜ",
}


@dataclass(frozen=True)
class PricingBudgetRow:
    row_number: int | None
    article_code: str
    canonical_article_code: str
    description: str
    revision_codes: list[str]
    unit: str | None
    quantity: float | None
    unit_price: float | None
    amount: float | None
    raw_text: str
    confidence: float


def ensure_pricing_tables(db_path: Path) -> None:
    initialize(db_path)
    connection = connect(db_path)
    try:
        connection.executescript(PRICING_SCHEMA_SQL)
        connection.commit()
    finally:
        connection.close()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PRICING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pricing_projects (
    eshidis_id TEXT PRIMARY KEY,
    official_url TEXT,
    title TEXT,
    authority_name TEXT,
    region TEXT,
    budget_display TEXT,
    deadline_at TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS pricing_documents (
    id INTEGER PRIMARY KEY,
    eshidis_id TEXT NOT NULL,
    source_url TEXT,
    local_path TEXT,
    document_name TEXT,
    document_type TEXT,
    sha256 TEXT,
    fetched_at TEXT,
    extraction_status TEXT,
    text_path TEXT,
    text_sample TEXT,
    heavy_file_deleted_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(eshidis_id, document_name)
);

CREATE INDEX IF NOT EXISTS idx_pricing_documents_eshidis
ON pricing_documents(eshidis_id);

CREATE TABLE IF NOT EXISTS pricing_budget_rows (
    id INTEGER PRIMARY KEY,
    eshidis_id TEXT NOT NULL,
    document_id INTEGER REFERENCES pricing_documents(id),
    source_document TEXT,
    row_number INTEGER,
    article_code TEXT NOT NULL,
    canonical_article_code TEXT NOT NULL,
    description TEXT,
    revision_codes_json TEXT NOT NULL DEFAULT '[]',
    unit TEXT,
    quantity REAL,
    unit_price REAL,
    amount REAL,
    raw_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    extracted_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(eshidis_id, source_document, row_number, canonical_article_code, description)
);

CREATE INDEX IF NOT EXISTS idx_pricing_budget_rows_article
ON pricing_budget_rows(canonical_article_code);

CREATE TABLE IF NOT EXISTS pricing_article_aliases (
    id INTEGER PRIMARY KEY,
    canonical_article_code TEXT NOT NULL,
    alias TEXT NOT NULL,
    source TEXT,
    first_seen_at TEXT NOT NULL,
    UNIQUE(canonical_article_code, alias)
);

CREATE TABLE IF NOT EXISTS pricing_runs (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);
"""


def canonical_article_code(value: str) -> str:
    text = strip_accents(value).upper()
    text = text.replace("B", "Β")
    text = re.sub(r"\s+", "", text)
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("Β-", "Β")
    return text


def canonical_revision_code(value: str) -> str:
    text = strip_accents(value).upper()
    replacements = {
        "∆": "Δ",
        "O": "Ο",
        "D": "Δ",
        " ": "",
        ".": "",
        "–": "-",
        "—": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("ΟΔΟ", "ΟΔΟ")
    return text


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def parse_greek_decimal(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip().replace(" ", "").rstrip("*")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        head, tail = text.rsplit(".", 1)
        text = head.replace(".", "") + "." + tail
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def extract_budget_text(path: Path) -> str:
    if path.suffix.lower() in {".txt", ".text"}:
        return path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".pdf":
        try:
            completed = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                text = completed.stdout
                if _looks_like_partial_budget_text(text):
                    ocr_text = _ocr_pdf_for_budget(path)
                    if ocr_text:
                        text = f"{text}\n\n{ocr_text}"
                return text
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    extraction = extract_text_with_metadata(path, max_chars=500_000)
    return extraction.full_text or extraction.text_sample or ""


def _looks_like_partial_budget_text(text: str) -> bool:
    normalized = strip_accents(text).upper()
    if "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ" not in normalized:
        return False
    row_numbers = [int(match.group(1)) for match in re.finditer(r"(?m)^\s*(\d{1,3})\s+", text)]
    return bool(row_numbers) and min(row_numbers) > 1 and len(set(row_numbers)) <= 10


def _ocr_pdf_for_budget(path: Path, *, max_pages: int = 12) -> str | None:
    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not pdftoppm or not tesseract:
        return None
    try:
        with subprocess.Popen(
            ["pdfinfo", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ) as proc:
            stdout, _ = proc.communicate(timeout=10)
        page_match = re.search(r"^Pages:\s+(\d+)", stdout or "", re.MULTILINE)
        page_count = int(page_match.group(1)) if page_match else max_pages
    except Exception:
        page_count = max_pages
    pages = min(page_count, max_pages)
    try:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="tender-pricing-ocr-") as tmp:
            prefix = str(Path(tmp) / "page")
            rendered = subprocess.run(
                [pdftoppm, "-f", "1", "-l", str(pages), "-r", "220", "-png", str(path), prefix],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if rendered.returncode != 0:
                return None
            texts: list[str] = []
            for image_path in sorted(Path(tmp).glob("page-*.png")):
                completed = subprocess.run(
                    [tesseract, str(image_path), "stdout", "-l", "ell+eng", "--psm", "6"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if completed.returncode == 0 and completed.stdout.strip():
                    texts.append(completed.stdout)
            return _clean_text("\n".join(texts)) or None
    except Exception:
        return None


def parse_budget_rows_from_text(text: str) -> list[PricingBudgetRow]:
    unit_price_before_quantity = _unit_price_before_quantity(text)
    at_unit_prices = _extract_at_unit_prices(text)
    table_rows = _parse_budget_table_lines(text, unit_price_before_quantity=unit_price_before_quantity)
    if table_rows:
        table_rows = _apply_at_unit_prices_from_text(
            text,
            table_rows,
            unit_price_before_quantity=unit_price_before_quantity,
        )
        table_rows = _filter_invalid_amount_table_rows(table_rows)
        table_rows = _renumber_local_restarted_article_rows(table_rows)
        table_rows = _renumber_decimal_at_layout_rows(table_rows)
        by_key: dict[tuple[int | None, str, str], PricingBudgetRow] = {}
        for row in table_rows:
            by_key[(row.row_number, row.canonical_article_code, row.description)] = row
        return list(by_key.values())
    blocks = _budget_row_blocks(text)
    rows = [row for block in blocks if (row := _parse_budget_block(block)) is not None]
    return rows


def _apply_at_unit_prices_from_text(
    text: str,
    rows: list[PricingBudgetRow],
    *,
    unit_price_before_quantity: bool,
) -> list[PricingBudgetRow]:
    unit_prices = _extract_at_unit_prices(text)
    if not unit_prices:
        return rows
    adjusted: list[PricingBudgetRow] = []
    for row in rows:
        if row.row_number is None or row.row_number not in unit_prices:
            adjusted.append(row)
            continue
        if _raw_budget_row_has_complete_numeric_tail(row, unit_price_before_quantity=unit_price_before_quantity):
            adjusted.append(row)
            continue
        quantity = _quantity_from_budget_row_raw_text(row, unit_price_before_quantity=unit_price_before_quantity)
        if quantity is None:
            quantity = _quantity_from_budget_row_raw_text(row, unit_price_before_quantity=not unit_price_before_quantity)
        unit_price = unit_prices[row.row_number]
        if quantity is None or unit_price is None:
            adjusted.append(row)
            continue
        amount = round(float(quantity) * float(unit_price), 2)
        current_amount = row.amount
        if current_amount is not None and abs(float(current_amount) - amount) <= 0.02:
            adjusted.append(row)
            continue
        adjusted.append(
            replace(
                row,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                confidence=max(row.confidence, 0.92),
            )
        )
    return adjusted


def _raw_budget_row_has_complete_numeric_tail(
    row: PricingBudgetRow,
    *,
    unit_price_before_quantity: bool,
) -> bool:
    if row.row_number is None or not row.unit:
        return False
    tokens = _clean_text(row.raw_text).split()
    row_token = f"{row.row_number:03d}"
    clean_unit = row.unit.lower().rstrip(".")
    for row_index, token in enumerate(tokens):
        if _clean_token(token) not in {row_token, str(row.row_number)}:
            continue
        for unit_index in range(row_index + 1, min(len(tokens), row_index + 14)):
            if tokens[unit_index].lower().rstrip(".") != clean_unit:
                continue
            numeric_after_unit = [
                item
                for item in tokens[unit_index + 1 : min(len(tokens), unit_index + 6)]
                if NUMERIC_RE.match(item)
            ]
            if len(numeric_after_unit) < 3:
                return False
            if unit_price_before_quantity:
                unit_price = parse_greek_decimal(numeric_after_unit[0])
                quantity = parse_greek_decimal(numeric_after_unit[1])
            else:
                quantity = parse_greek_decimal(numeric_after_unit[0])
                unit_price = parse_greek_decimal(numeric_after_unit[1])
            amount = parse_greek_decimal(numeric_after_unit[2])
            if quantity is None or unit_price is None or amount is None:
                return False
            return abs(round(float(quantity) * float(unit_price), 2) - float(amount)) <= 0.02
    return False


def _complete_budget_lines_with_at_unit_prices(
    text: str,
    unit_prices: dict[int, float],
    *,
    unit_price_before_quantity: bool,
) -> str:
    if not unit_prices:
        return text
    completed_lines: list[str] = []
    for line in text.splitlines():
        match = TABLE_ROW_RE.match(line)
        if not match:
            completed_lines.append(line)
            continue
        tokens = _clean_text(match.group("rest")).split()
        numeric_positions = [index for index, token in enumerate(tokens) if NUMERIC_RE.match(token)]
        if len(numeric_positions) >= 3:
            completed_lines.append(line)
            continue
        at_index = next(
            (
                index
                for index, token in enumerate(tokens)
                if re.fullmatch(r"\d{3}", _clean_token(token)) and int(_clean_token(token)) in unit_prices
            ),
            None,
        )
        if at_index is None:
            completed_lines.append(line)
            continue
        unit_end = _find_unit_end(tokens, len(tokens))
        if unit_end is None:
            completed_lines.append(line)
            continue
        unit_index, _unit = unit_end
        numeric_after_unit = [
            token
            for token in tokens[unit_index + 1 :]
            if NUMERIC_RE.match(token)
        ]
        if not numeric_after_unit:
            completed_lines.append(line)
            continue
        quantity_token = numeric_after_unit[1] if unit_price_before_quantity and len(numeric_after_unit) > 1 else numeric_after_unit[0]
        quantity = parse_greek_decimal(quantity_token)
        unit_price = unit_prices[int(_clean_token(tokens[at_index]))]
        if quantity is None:
            completed_lines.append(line)
            continue
        amount = round(float(quantity) * float(unit_price), 2)
        completed_lines.append(f"{line} {_number_token(unit_price)} {_number_token(amount)}")
    return "\n".join(completed_lines)


def _number_token(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _extract_at_unit_prices(text: str) -> dict[int, float]:
    lines = text.splitlines()
    at_indexes: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = re.search(r"\bA\.?\s*T\.?\s*:\s*(\d{1,3})\b", line, flags=re.IGNORECASE)
        if not match:
            continue
        at_indexes.append((index, int(match.group(1))))
    unit_prices: dict[int, float] = {}
    for position, (start, at_number) in enumerate(at_indexes):
        end = at_indexes[position + 1][0] if position + 1 < len(at_indexes) else min(len(lines), start + 80)
        block = "\n".join(lines[start:end])
        match = re.search(r"\(Αριθμητικώς\)\s*:\s*(\d+(?:[.,]\d{1,3})*)", block, flags=re.IGNORECASE)
        if not match:
            continue
        unit_price = parse_greek_decimal(match.group(1))
        if unit_price is not None:
            unit_prices[at_number] = float(unit_price)
    return unit_prices


def _quantity_from_budget_row_raw_text(
    row: PricingBudgetRow,
    *,
    unit_price_before_quantity: bool,
) -> float | None:
    if row.row_number is None or not row.unit:
        return None
    tokens = _clean_text(row.raw_text).split()
    row_token = f"{row.row_number:03d}"
    row_indexes = [
        index
        for index, token in enumerate(tokens)
        if _clean_token(token) == row_token or _clean_token(token) == str(row.row_number)
    ]
    clean_unit = row.unit.lower().rstrip(".")
    for row_index in row_indexes:
        for unit_index in range(row_index + 1, min(len(tokens), row_index + 14)):
            if tokens[unit_index].lower().rstrip(".") != clean_unit:
                continue
            numeric_after_unit = [
                token
                for token in tokens[unit_index + 1 : min(len(tokens), unit_index + 6)]
                if NUMERIC_RE.match(token)
            ]
            if unit_price_before_quantity:
                if len(numeric_after_unit) >= 2:
                    return parse_greek_decimal(numeric_after_unit[1])
            elif numeric_after_unit:
                return parse_greek_decimal(numeric_after_unit[0])
    return None


def _unit_price_before_quantity(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", strip_accents(text).upper())
    if re.search(r"(?:ΠΟΣΟΤ\w*|ΠΟΣΟ\s+ΤΗΤΑ).{0,120}ΤΙΜ", normalized):
        return False
    if re.search(r"ΠΟΣΟΤΗΤΑ.{0,80}ΜΟΝΑΔΑΣ", normalized):
        return False
    return bool(
        re.search(r"ΜΟΝΑΔΑΣ\s+ΠΟΣΟΤΗΤΑ", normalized)
        or re.search(r"ΤΙΜΗ\s+(?:ΜΟΝΑΔ|ΜΟΝ)\S*\s+ΠΟΣΟΤ", normalized)
        or re.search(r"ΤΙΜΗ.{0,240}ΠΟΣΟΤ", normalized)
    )


def _parse_budget_table_lines(text: str, *, unit_price_before_quantity: bool = False) -> list[PricingBudgetRow]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    parsed: list[PricingBudgetRow] = []
    for index, line in enumerate(lines):
        previous_line = lines[index - 1] if index > 0 else ""
        previous_lines = lines[max(0, index - 3) : index]
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        next_lines = lines[index + 1 : min(len(lines), index + 4)]
        row = _parse_budget_table_line(
            line,
            previous_line=previous_line,
            previous_lines=previous_lines,
            next_line=next_line,
            next_lines=next_lines,
            unit_price_before_quantity=unit_price_before_quantity,
        )
        if row is not None:
            parsed.append(row)
            continue
        prefixed_row = _parse_prefixed_article_table_line(
            line,
            previous_line=previous_line,
            next_line=next_line,
            unit_price_before_quantity=unit_price_before_quantity,
        )
        if prefixed_row is not None:
            parsed.append(prefixed_row)
    return parsed


def _filter_invalid_amount_table_rows(rows: list[PricingBudgetRow]) -> list[PricingBudgetRow]:
    valid_rows = [row for row in rows if _budget_row_amount_is_valid(row)]
    if len(valid_rows) < 3:
        return rows
    return [
        row
        for row in rows
        if row.quantity is None
        or row.unit_price is None
        or row.amount is None
        or _budget_row_amount_is_valid(row)
    ]


def _parse_budget_table_line(
    line: str,
    *,
    previous_line: str = "",
    previous_lines: list[str] | None = None,
    next_line: str = "",
    next_lines: list[str] | None = None,
    unit_price_before_quantity: bool = False,
) -> PricingBudgetRow | None:
    match = TABLE_ROW_RE.match(line)
    if not match:
        return None
    row_number = int(match.group("row"))
    tokens = _clean_text(match.group("rest")).split()
    line_for_raw = line
    numeric_positions = [index for index, token in enumerate(tokens) if NUMERIC_RE.match(token)]
    if len(numeric_positions) < 3:
        expanded_tokens = _expand_table_row_numeric_tail(tokens, next_lines or ([next_line] if next_line else []))
        if expanded_tokens is not None:
            tokens = expanded_tokens
            line_for_raw = f"{line} {' '.join(next_lines or [next_line])}"
            next_line = ""
            numeric_positions = [index for index, token in enumerate(tokens) if NUMERIC_RE.match(token)]
    if len(numeric_positions) < 3:
        return None
    amount_pos = numeric_positions[-1]
    if unit_price_before_quantity:
        unit_price_pos, quantity_pos = numeric_positions[-3], numeric_positions[-2]
    else:
        quantity_pos, unit_price_pos = numeric_positions[-3], numeric_positions[-2]
    unit_search_pos = unit_price_pos if unit_price_before_quantity else quantity_pos
    unit_end = _find_unit_end(tokens, unit_search_pos)
    if unit_end is None:
        return None
    unit_start, unit = unit_end
    prefix_tokens = tokens[:unit_start]
    post_unit_tokens = tokens[unit_start + 1 : unit_price_pos] if unit_price_before_quantity else []
    revision_tokens: list[str] = []
    article_code: str | None = None
    description_tokens: list[str] = []
    at_first_article = _split_at_first_article_prefix(prefix_tokens)
    if at_first_article is not None:
        row_number, article_code, description_tokens, revision_tokens = at_first_article
    else:
        wrapped_article = _split_wrapped_article_across_lines(
            prefix_tokens,
            previous_lines or ([previous_line] if previous_line else []),
            next_lines or ([next_line] if next_line else []),
        )
        if wrapped_article is not None:
            row_number, article_code, description_tokens, revision_tokens = wrapped_article
            next_line = ""
            previous_line = ""
    if article_code is None:
        local_after_unit = _split_local_article_budget_prefix(post_unit_tokens, allow_empty_description=True)
        if local_after_unit is not None:
            article_code, article_description_tokens, revision_tokens = local_after_unit
            description_tokens = [*prefix_tokens, *article_description_tokens]
        else:
            work_budget_structured = _split_work_budget_prefix(prefix_tokens, next_line=next_line)
            if work_budget_structured is not None:
                row_number, article_code, description_tokens, revision_tokens, consumed_next_line = work_budget_structured
                previous_line = ""
                if consumed_next_line:
                    next_line = ""
            else:
                structured = _split_structured_table_prefix(prefix_tokens, next_line=next_line)
                if structured is not None:
                    row_number, article_code, description_tokens, revision_tokens, consumed_next_line = structured
                    previous_line = ""
                    if consumed_next_line:
                        next_line = ""
                else:
                    local_article = _split_local_article_budget_prefix(prefix_tokens)
                    if local_article is not None:
                        article_code, description_tokens, revision_tokens = local_article
                        previous_line = ""
                    else:
                        article_code, description_tokens = _split_article_and_description(prefix_tokens)
                        if not revision_tokens and _tokens_are_only_revision_codes(description_tokens) and _is_description_continuation(previous_line):
                            revision_tokens = description_tokens
                            description_tokens = []
    if article_code and re.fullmatch(r"\d{3}", _clean_token(article_code)):
        surrounding_article = _split_article_from_surrounding_lines(prefix_tokens, previous_line, next_line)
        if surrounding_article is not None:
            row_number, article_code, description_tokens, revision_tokens = surrounding_article
            next_line = ""
            previous_line = ""
    if not article_code:
        surrounding_article = _split_article_from_surrounding_lines(prefix_tokens, previous_line, next_line)
        if surrounding_article is not None:
            row_number, article_code, description_tokens, revision_tokens = surrounding_article
            next_line = ""
            previous_line = ""
    if not article_code:
        article_code, description_tokens = _article_from_neighbor(previous_line, row_number, description_tokens)
    description_parts = [" ".join(description_tokens)]
    if _should_prepend_previous_description(previous_line, description_tokens):
        description_parts.insert(0, previous_line)
    if _is_description_continuation(next_line):
        description_parts.append(next_line)
    revision_codes = _revision_codes_from_tokens(revision_tokens) or _extract_revision_codes(" ".join(revision_tokens))
    description = _clean_description(" ".join(description_parts), revision_codes)
    if not article_code or not description:
        return None
    return PricingBudgetRow(
        row_number=row_number,
        article_code=article_code,
        canonical_article_code=canonical_article_code(article_code),
        description=description,
        revision_codes=revision_codes,
        unit=unit,
        quantity=parse_greek_decimal(tokens[quantity_pos]),
        unit_price=parse_greek_decimal(tokens[unit_price_pos]),
        amount=parse_greek_decimal(tokens[amount_pos]),
        raw_text=_clean_text(line_for_raw),
        confidence=0.9,
    )


def _parse_prefixed_article_table_line(
    line: str,
    *,
    previous_line: str = "",
    next_line: str = "",
    unit_price_before_quantity: bool = False,
) -> PricingBudgetRow | None:
    tokens = _clean_text(line).split()
    if len(tokens) < 9:
        return None
    prefix = strip_accents(tokens[0]).upper().rstrip(".")
    if prefix not in ARTICLE_CODE_PREFIXES:
        return None
    article_suffix = _clean_token(tokens[1])
    if not re.search(r"\d", article_suffix):
        return None
    row_index = 2
    if not re.fullmatch(r"\d{1,3}", _clean_token(tokens[row_index])):
        return None
    row_number = int(_clean_token(tokens[row_index]))
    unit_end = _find_unit_end(tokens, len(tokens))
    if unit_end is None:
        return None
    unit_index, unit = unit_end
    numeric_after_unit = [
        token for token in tokens[unit_index + 1 :] if NUMERIC_RE.match(token)
    ]
    if len(numeric_after_unit) < 3:
        return None
    if unit.lower().rstrip(".") == "m":
        previous_tokens = _clean_text(previous_line).split()
        next_tokens = _clean_text(next_line).split()
        if previous_tokens and previous_tokens[-1] in {"2", "3"}:
            unit = f"m{previous_tokens[-1]}"
        elif next_tokens and next_tokens[0] in {"2", "3"}:
            unit = f"m{next_tokens[0]}"
    if unit_price_before_quantity:
        unit_price_token, quantity_token, amount_token = numeric_after_unit[:3]
    else:
        quantity_token, unit_price_token, amount_token = numeric_after_unit[:3]
    revision_start = _find_revision_start_before_unit(tokens, unit_index)
    if revision_start is None or revision_start <= row_index + 1:
        return None
    article_code = f"{tokens[0]} {article_suffix}"
    description_tokens = tokens[row_index + 2 : revision_start]
    if _should_prepend_previous_description(previous_line, description_tokens):
        description_tokens = [*_clean_text(previous_line).split(), *description_tokens]
    if not description_tokens:
        return None
    revision_tokens = tokens[revision_start:unit_index]
    revision_codes = _revision_codes_from_tokens(revision_tokens) or _extract_revision_codes(" ".join(revision_tokens))
    return PricingBudgetRow(
        row_number=row_number,
        article_code=article_code,
        canonical_article_code=canonical_article_code(article_code),
        description=_clean_description(" ".join(description_tokens), revision_codes),
        revision_codes=revision_codes,
        unit=unit,
        quantity=parse_greek_decimal(quantity_token),
        unit_price=parse_greek_decimal(unit_price_token),
        amount=parse_greek_decimal(amount_token),
        raw_text=_clean_text(line),
        confidence=0.9,
    )


def _find_revision_start_before_unit(tokens: list[str], unit_index: int) -> int | None:
    for index in range(unit_index - 1, 2, -1):
        token = _clean_token(tokens[index])
        previous = _clean_token(tokens[index - 1]) if index > 0 else ""
        if _extract_revision_codes(token):
            return index
        if (
            strip_accents(previous).upper().rstrip(".") in ARTICLE_CODE_PREFIXES
            and re.fullmatch(r"\d+[A-ZΑ-ΩA-Z0-9.]*", token, flags=re.IGNORECASE)
        ):
            return index - 1
    return None


def _expand_table_row_numeric_tail(tokens: list[str], next_lines: list[str]) -> list[str] | None:
    next_tokens = _clean_text(" ".join(next_lines)).split()
    unit_suffix: str | None = None
    unit_end = _find_unit_end(tokens, len(tokens))
    if unit_end is not None:
        unit_start, unit = unit_end
        if unit.lower().rstrip(".") == "m" and next_tokens and next_tokens[0] in {"2", "3"}:
            unit_suffix = next_tokens[0]
            tokens = [*tokens[:unit_start], f"m{unit_suffix}", *tokens[unit_start + 1 :]]
            next_tokens = next_tokens[1:]
    next_numeric = [token for token in next_tokens if NUMERIC_RE.match(token)]
    if len(next_numeric) < 3:
        return None
    if _find_unit_end(tokens, len(tokens)) is None:
        return None
    return [*tokens, *next_numeric[:3]]


def _split_structured_table_prefix(tokens: list[str], *, next_line: str = "") -> tuple[int, str, list[str], list[str], bool] | None:
    if len(tokens) < 3 or not (tokens[-1].isdigit() or _is_decimal_at_token(tokens[-1])):
        return None
    row_number = int(tokens[-1]) if tokens[-1].isdigit() else 0
    work_tokens = tokens[:-1]
    split_continuation = _split_article_prefix_from_next_line(work_tokens, next_line)
    article_index = _find_structured_article_index(work_tokens)
    if article_index is None:
        split_article = split_continuation or _split_article_from_next_line(work_tokens, next_line)
        if split_article is None:
            return None
        article_code, description_tokens, revision_tokens = split_article
        return row_number, article_code, description_tokens, revision_tokens, True
    article_code = " ".join(work_tokens[article_index : article_index + 2])
    description_tokens = work_tokens[:article_index]
    revision_tokens = work_tokens[article_index + 2 :]
    if not description_tokens or not revision_tokens:
        split_article = split_continuation or _split_article_from_next_line(work_tokens, next_line)
        if split_article is None:
            return None
        article_code, description_tokens, revision_tokens = split_article
        return row_number, article_code, description_tokens, revision_tokens, True
    if split_continuation is not None and not re.search(r"\d", article_code):
        article_code, description_tokens, revision_tokens = split_continuation
        return row_number, article_code, description_tokens, revision_tokens, True
    return row_number, article_code, description_tokens, revision_tokens, False


def _is_decimal_at_token(token: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}\.\d{2}", _clean_token(token)))


def _row_has_decimal_at_marker(row: PricingBudgetRow) -> bool:
    tokens = _clean_text(row.raw_text).split()
    for index, token in enumerate(tokens[:-1]):
        if not _is_decimal_at_token(token):
            continue
        unit_token = tokens[index + 1].lower().rstrip(".")
        if unit_token in {unit.rstrip(".") for unit in KNOWN_UNITS}:
            return True
    return False


def _renumber_local_restarted_article_rows(rows: list[PricingBudgetRow]) -> list[PricingBudgetRow]:
    row_numbers = [row.row_number for row in rows if row.row_number is not None]
    if len(row_numbers) < 3 or len(set(row_numbers)) == len(row_numbers):
        return rows
    if not all(_looks_like_local_article_code(row.article_code) for row in rows):
        return rows
    return [replace(row, row_number=index) for index, row in enumerate(rows, start=1)]


def _looks_like_local_article_code(value: str) -> bool:
    clean = strip_accents(value).upper()
    return bool(re.fullmatch(r"[A-ZΑ-ΩΒ]+[-_/]?\d+[A-ZΑ-ΩA-Z0-9.]*", clean))


def _renumber_decimal_at_layout_rows(rows: list[PricingBudgetRow]) -> list[PricingBudgetRow]:
    if len(rows) < 3:
        return rows
    marker_count = sum(1 for row in rows if _row_has_decimal_at_marker(row))
    if marker_count < max(3, len(rows) // 2):
        return rows
    return [replace(row, row_number=index) for index, row in enumerate(rows, start=1)]


def _split_work_budget_prefix(tokens: list[str], *, next_line: str = "") -> tuple[int, str, list[str], list[str], bool] | None:
    at_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if re.fullmatch(r"\d{3}", _clean_token(token))
        ),
        None,
    )
    if at_index is None or at_index < 2:
        return None
    row_number = int(_clean_token(tokens[at_index]))
    before_at = tokens[:at_index]
    revision_tokens = tokens[at_index + 1 :]
    if not revision_tokens:
        return None
    article_start = _find_work_budget_article_start(before_at)
    if article_start is None or article_start == 0:
        return None
    article_tokens = before_at[article_start:]
    description_tokens = before_at[:article_start]
    consumed_next_line = False
    next_tokens = _clean_text(next_line).split()
    if next_tokens:
        suffix_index = _find_article_suffix_index(next_tokens)
        if suffix_index == 0:
            article_tokens = [*article_tokens, next_tokens[0]]
            description_tokens = [*description_tokens, *next_tokens[1:]]
            consumed_next_line = True
    article_code = " ".join(article_tokens)
    return row_number, article_code, description_tokens, revision_tokens, consumed_next_line


def _split_at_first_article_prefix(tokens: list[str]) -> tuple[int, str, list[str], list[str]] | None:
    if len(tokens) < 3 or not re.fullmatch(r"\d{3}", _clean_token(tokens[0])):
        return None
    article_tokens = tokens[1:]
    article_start = _find_work_budget_article_start(article_tokens)
    if article_start is None:
        return None
    article_code = " ".join(article_tokens[article_start:])
    if not re.search(r"\d", article_code):
        return None
    return int(_clean_token(tokens[0])), article_code, article_tokens[:article_start], []


def _split_local_article_budget_prefix(
    tokens: list[str],
    *,
    allow_empty_description: bool = False,
) -> tuple[str, list[str], list[str]] | None:
    """Split tables whose article code is a local AT such as HLM-1.

    Some authority budgets use columns like:
    description | unit | AT | price-origin | revision | unit-price | qty | amount
    where the row number is only local to the current subgroup. The real
    searchable article for our index is still the AT column.
    """
    min_tokens = 2 if allow_empty_description else 4
    if len(tokens) < min_tokens:
        return None
    article_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if re.fullmatch(r"[A-ZΑ-ΩΒ]+(?:[-_/]?\d+[A-ZΑ-ΩA-Z0-9.]*)+", _clean_token(token), flags=re.IGNORECASE)
        ),
        None,
    )
    if article_index is None or (article_index == 0 and not allow_empty_description):
        return None
    article_code = _clean_token(tokens[article_index])
    suffix = tokens[article_index + 1 :]
    revision_tokens = [token for token in suffix if _extract_revision_codes(token)]
    if not revision_tokens and suffix:
        last = _clean_token(suffix[-1])
        if re.fullmatch(r"[A-ZΑ-ΩΒ]+\d+[A-ZΑ-ΩA-Z0-9.]*", last, flags=re.IGNORECASE):
            revision_tokens = [suffix[-1]]
    description_tokens = tokens[:article_index]
    if not description_tokens and not allow_empty_description:
        return None
    return article_code, description_tokens, revision_tokens


def _find_work_budget_article_start(tokens: list[str]) -> int | None:
    for index in range(0, len(tokens) - 1):
        current = strip_accents(tokens[index]).upper().rstrip(".")
        nxt = strip_accents(tokens[index + 1]).upper().rstrip(".")
        if current == "ΝΕΤ":
            return index
        if current in ARTICLE_CODE_PREFIXES and re.search(r"\d", tokens[index + 1]):
            return index
        if current in {"ΟΙΚ", "ΥΔΡ", "ΗΛΜ", "ΝΑΟΙΚ", "ΝΑΥΔΡ"} and re.search(r"\d", tokens[index + 1]):
            return index
        if current.startswith(("ΟΙΚ", "ΥΔΡ", "ΗΛΜ", "ΑΤΗΕ")) and re.search(r"\d", current):
            return index
        if current == "ΑΤΗΕ" and (nxt.startswith("ΗΛΜ") or re.search(r"\d", tokens[index + 1])):
            return index
    if tokens:
        last = strip_accents(tokens[-1]).upper().rstrip(".")
        if last in {"ΑΤΗΕ", "ΝΕΤ", "ΝΑΟΙΚ", "ΝΑΥΔΡ", "ΟΙΚ", "ΥΔΡ"}:
            return len(tokens) - 1
    return None


def _split_wrapped_article_across_lines(
    tokens: list[str],
    previous_lines: list[str],
    next_lines: list[str],
) -> tuple[int, str, list[str], list[str]] | None:
    at_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if re.fullmatch(r"\d{3}", _clean_token(token))
        ),
        None,
    )
    if at_index is None:
        return None
    current_description_tokens: list[str] = []
    current_article_tokens: list[str] = []
    if at_index > 0:
        fragment_start = _find_article_fragment_suffix_start(tokens[:at_index])
        if fragment_start is None:
            current_description_tokens = tokens[:at_index]
        else:
            current_description_tokens = tokens[:fragment_start]
            current_article_tokens = tokens[fragment_start:at_index]
    suffix_tokens: list[str] = []
    suffix_line_index: int | None = None
    suffix_index: int | None = None
    for line_index, line in enumerate(next_lines[:3]):
        line_tokens = _clean_text(line).split()
        found = _find_article_suffix_index(line_tokens)
        if found is not None:
            suffix_tokens = line_tokens
            suffix_line_index = line_index
            suffix_index = found
            break
    if suffix_index is None or suffix_line_index is None:
        return None
    prefix_line_tokens: list[str] = []
    prefix_index: int | None = None
    for line in reversed(previous_lines[-3:]):
        line_tokens = _clean_text(line).split()
        found = _find_wrapped_article_prefix_index(line_tokens)
        if found is not None:
            prefix_line_tokens = line_tokens
            prefix_index = found
            break
    if prefix_index is None:
        return None
    suffix_description_tokens = suffix_tokens[:suffix_index]
    suffix_article_connector: list[str] = []
    if suffix_description_tokens and _tokens_look_like_article_connector([suffix_description_tokens[-1]]):
        suffix_article_connector = [suffix_description_tokens[-1]]
        suffix_description_tokens = suffix_description_tokens[:-1]
    article_tokens = [
        *prefix_line_tokens[prefix_index : prefix_index + 2],
        *current_article_tokens,
        *suffix_article_connector,
        suffix_tokens[suffix_index],
    ]
    article_code = " ".join(token for token in article_tokens if token)
    if not re.search(r"\d", article_code):
        return None
    description_tokens = [*prefix_line_tokens[:prefix_index], *current_description_tokens]
    for line in next_lines[:suffix_line_index]:
        description_tokens.extend(_clean_text(line).split())
    description_tokens.extend(suffix_description_tokens)
    revision_codes = _extract_revision_codes(" ".join(previous_lines[-3:]))
    revision_tokens = revision_codes or prefix_line_tokens[prefix_index + 2 :]
    return int(_clean_token(tokens[at_index])), article_code, description_tokens, revision_tokens


def _find_wrapped_article_prefix_index(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens):
        clean = strip_accents(_clean_token(token)).upper().rstrip(".")
        if clean == "ΝΕΤ":
            return index
        if clean in {"ΝΕΟ", "ΝΕΟ_ΗΛΜ", "ΝΕΟΗΛΜ", "ΣΧΕΤ_ΟΔΟ", "ΣΧΕΤ_ΟΔ", "ΣΧΕΤΟΔ"}:
            return index
    return None


def _tokens_look_like_article_fragment(tokens: list[str]) -> bool:
    if not tokens or len(tokens) > 3:
        return False
    if any(re.search(r"[a-zα-ωάέήίόύώϊϋΐΰ]", token) for token in tokens):
        return False
    text = strip_accents(" ".join(tokens)).upper()
    if any(prefix in text for prefix in ARTICLE_CODE_PREFIXES):
        return True
    return bool(re.fullmatch(r"[A-ZΑ-ΩΒ0-9.\\/_ -]+", text))


def _find_article_fragment_suffix_start(tokens: list[str]) -> int | None:
    if not tokens:
        return 0
    for start in range(max(0, len(tokens) - 3), len(tokens)):
        if _tokens_look_like_article_fragment(tokens[start:]):
            return start
    return None


def _find_structured_article_index(tokens: list[str]) -> int | None:
    for index in range(0, len(tokens) - 1):
        prefix = strip_accents(tokens[index]).upper().rstrip(".")
        next_token = tokens[index + 1]
        if prefix in ARTICLE_CODE_PREFIXES and re.search(r"\d", next_token):
            return index
    return None


def _split_article_from_next_line(tokens: list[str], next_line: str) -> tuple[str, list[str], list[str]] | None:
    next_tokens = _clean_text(next_line).split()
    if not next_tokens:
        return None
    for index in range(0, len(tokens) - 1):
        prefix = strip_accents(tokens[index]).upper().rstrip(".")
        revision_prefix = strip_accents(tokens[index + 1]).upper().rstrip(".")
        if prefix not in ARTICLE_CODE_PREFIXES or revision_prefix not in ARTICLE_CODE_PREFIXES:
            continue
        suffix_index = _find_article_suffix_index(next_tokens)
        if suffix_index is None:
            return None
        article_code = f"{tokens[index]} {next_tokens[suffix_index]}"
        description_tokens = [*tokens[:index], *next_tokens[:suffix_index]]
        revision_tokens = tokens[index + 1 :]
        if description_tokens and revision_tokens:
            return article_code, description_tokens, revision_tokens
    return None


def _split_article_from_surrounding_lines(
    tokens: list[str],
    previous_line: str,
    next_line: str,
) -> tuple[int, str, list[str], list[str]] | None:
    if not tokens or not re.fullmatch(r"\d{3}", _clean_token(tokens[-1])):
        return None
    previous_tokens = _clean_text(previous_line).split()
    next_tokens = _clean_text(next_line).split()
    if len(previous_tokens) < 2 or not next_tokens:
        return None
    prefix_index = next(
        (
            index
            for index, token in enumerate(previous_tokens[:-1])
            if strip_accents(token).upper().rstrip(".") == "ΝΕΤ"
            or strip_accents(token).upper().rstrip(".") in ARTICLE_CODE_PREFIXES
        ),
        None,
    )
    if prefix_index is None:
        return None
    suffix_index = _find_article_suffix_index(next_tokens)
    if suffix_index is None:
        return None
    article_tokens = previous_tokens[prefix_index : prefix_index + 2]
    connector_tokens = next_tokens[:suffix_index]
    if connector_tokens and _tokens_look_like_article_connector(connector_tokens):
        article_tokens = [*article_tokens, *connector_tokens]
        description_suffix_tokens: list[str] = []
    elif connector_tokens and _tokens_look_like_article_connector([connector_tokens[-1]]):
        article_tokens = [*article_tokens, connector_tokens[-1]]
        description_suffix_tokens = connector_tokens[:-1]
    else:
        description_suffix_tokens = connector_tokens
    row_number = int(_clean_token(tokens[-1]))
    article_code = " ".join([*article_tokens, next_tokens[suffix_index]])
    description_tokens = [*previous_tokens[:prefix_index], *tokens[:-1], *description_suffix_tokens]
    if not description_tokens:
        return None
    revision_tokens = previous_tokens[prefix_index + 2 :]
    return row_number, article_code, description_tokens, revision_tokens


def _tokens_look_like_article_connector(tokens: list[str]) -> bool:
    if not tokens or len(tokens) > 2:
        return False
    for token in tokens:
        if re.search(r"[a-zα-ωάέήίόύώϊϋΐΰ]", token):
            return False
        clean = strip_accents(_clean_token(token)).upper().rstrip(".")
        if not clean or not re.fullmatch(r"[A-ZΑ-Ω-]+", clean):
            return False
    return True


def _split_article_prefix_from_next_line(tokens: list[str], next_line: str) -> tuple[str, list[str], list[str]] | None:
    next_tokens = _clean_text(next_line).split()
    if not next_tokens:
        return None
    suffix_index = _find_article_suffix_index(next_tokens)
    if suffix_index is None:
        return None
    prefix_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if strip_accents(tokens[index]).upper().rstrip(".") in ARTICLE_CODE_PREFIXES
        ),
        None,
    )
    if prefix_index is None:
        return None
    description_tokens = [*tokens[:prefix_index], *next_tokens[:suffix_index]]
    if not description_tokens:
        return None
    article_code = f"{tokens[prefix_index]} {next_tokens[suffix_index]}"
    revision_tokens = tokens[prefix_index + 1 :]
    return article_code, description_tokens, revision_tokens


def _find_article_suffix_index(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens):
        clean = _clean_token(token)
        if re.fullmatch(r"\d+[A-ZΑ-ΩA-Z0-9]*", clean, flags=re.IGNORECASE):
            return index
        if re.fullmatch(r"[A-ZΑ-ΩΒB][-_]?\d+(?:[./-][A-ZΑ-ΩA-Z0-9]+)*", clean, flags=re.IGNORECASE):
            return index
        if re.fullmatch(r"[A-ZΑ-ΩΒB]?[\\/A-ZΑ-ΩΒB]*\d+(?:[./-][A-ZΑ-ΩA-Z0-9]+)+", clean, flags=re.IGNORECASE):
            return index
    return None


def _find_unit_end(tokens: list[str], before_index: int) -> tuple[int, str] | None:
    for index in range(before_index - 1, -1, -1):
        token = tokens[index].lower().rstrip(".")
        if token == "αποκοπή" and index > 0 and tokens[index - 1].lower().startswith("κατ"):
            return index - 1, "κατ' αποκοπή"
        if token in {unit.rstrip(".") for unit in KNOWN_UNITS}:
            return index, tokens[index]
    return None


def _split_article_and_description(tokens: list[str]) -> tuple[str | None, list[str]]:
    if not tokens:
        return None, []
    first = tokens[0].strip()
    if first.startswith("Ν") and len(tokens) > 1 and tokens[1].startswith("("):
        article_tokens = [first]
        for token in tokens[1:]:
            article_tokens.append(token)
            if token.endswith(")"):
                break
        return " ".join(article_tokens), tokens[len(article_tokens) :]
    if first in {"ΛΙΜ", "ΟΔΟ", "ΥΔΡ", "ΟΙΚ", "ΠΡΣ", "ΗΛΜ", "ΥΣΦ"} and len(tokens) > 1:
        return " ".join(tokens[:2]), tokens[2:]
    if re.search(r"\d", first):
        return first, tokens[1:]
    return None, tokens


def _article_from_neighbor(previous_line: str, row_number: int, description_tokens: list[str]) -> tuple[str | None, list[str]]:
    if re.match(r"^\s*\d+\.\s+", previous_line):
        return None, description_tokens
    match = TABLE_ROW_RE.match(previous_line)
    if not match:
        previous_tokens = _clean_text(previous_line).split()
        article_code, extra_description = _split_article_and_description(previous_tokens)
        return article_code, [*extra_description, *description_tokens]
    previous_row = int(match.group("row"))
    if previous_row != row_number:
        return None, description_tokens
    previous_tokens = _clean_text(match.group("rest")).split()
    article_code, extra_description = _split_article_and_description(previous_tokens)
    return article_code, [*extra_description, *description_tokens]


def _is_description_continuation(line: str) -> bool:
    clean = _clean_text(line)
    if not clean or TABLE_ROW_RE.match(clean):
        return False
    tokens = clean.split()
    if tokens and len([token for token in tokens if NUMERIC_RE.match(token)]) >= min(3, len(tokens)):
        return False
    upper = strip_accents(clean).upper()
    if upper.startswith(("ΟΜΑΔΑ", "ΣΥΝΟΛΟ", "Γ.Ε.", "ΑΘΡΟΙΣΜΑ", "ΑΠΡΟΒΛ", "ΑΝΑΘΕΩΡΗΣΗ", "Φ.Π.Α.", "ΓΕΝΙΚΟ")):
        return False
    if "ΣΕΛΙΔΑ" in upper or "ΤΕΥΧΗ ΔΗΜΟΠΡΑΤΗΣΗΣ" in upper:
        return False
    return True


def _should_prepend_previous_description(previous_line: str, description_tokens: list[str]) -> bool:
    if not _is_description_continuation(previous_line):
        return False
    if not description_tokens:
        return True
    first = description_tokens[0]
    return bool(first) and first[0].islower()


def _revision_codes_from_tokens(tokens: list[str]) -> list[str]:
    text = " ".join(tokens)
    if not text or text == "-":
        return []
    return _extract_revision_codes(text)


def _tokens_are_only_revision_codes(tokens: list[str]) -> bool:
    if not tokens:
        return False
    for token in tokens:
        if not REVISION_RE.fullmatch(token):
            return False
    return True


def _budget_row_blocks(text: str) -> list[list[str]]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    row_indexes = [index for index, line in enumerate(lines) if ARTICLE_RE.match(line)]
    blocks: list[list[str]] = []
    for position, index in enumerate(row_indexes):
        next_index = row_indexes[position + 1] if position + 1 < len(row_indexes) else len(lines)
        start = max(0, index - 2)
        article_match = ARTICLE_RE.match(lines[index])
        row_token_count = 0
        if article_match:
            row_token_count = len([token for token in article_match.group("rest").split() if NUMERIC_RE.match(token)])
        end = min(next_index, index + 3) if row_token_count >= 3 else next_index
        blocks.append(lines[start:end])
    return blocks


def _parse_budget_block(lines: list[str]) -> PricingBudgetRow | None:
    article_index = next((index for index, line in enumerate(lines) if ARTICLE_RE.match(line)), -1)
    if article_index < 0:
        return None
    match = ARTICLE_RE.match(lines[article_index])
    if not match:
        return None
    row_number = int(match.group("row"))
    article_code = _clean_token(match.group("article"))
    row_rest = _clean_text(match.group("rest"))
    row_tokens = row_rest.split()
    numeric_positions = [index for index, token in enumerate(row_tokens) if NUMERIC_RE.match(token)]
    context_lines = [*lines[:article_index], " ".join(row_tokens), *lines[article_index + 1 :]]
    context_tokens = _clean_text(" ".join(context_lines)).split()
    if len(numeric_positions) < 3:
        row_tokens = context_tokens
        numeric_positions = [index for index, token in enumerate(row_tokens) if NUMERIC_RE.match(token)]
    if len(numeric_positions) < 3:
        return None
    amount_pos, unit_price_pos, quantity_pos = numeric_positions[-1], numeric_positions[-2], numeric_positions[-3]
    unit_pos = quantity_pos - 1
    unit = row_tokens[unit_pos] if unit_pos >= 0 else None
    if unit and unit.lower().rstrip(".") not in KNOWN_UNITS:
        unit = row_tokens[unit_pos]
    quantity = parse_greek_decimal(row_tokens[quantity_pos])
    unit_price = parse_greek_decimal(row_tokens[unit_price_pos])
    amount = parse_greek_decimal(row_tokens[amount_pos])
    if row_tokens is context_tokens:
        leading_text = " ".join(row_tokens[: max(unit_pos, 0)])
    else:
        leading_text = " ".join(
            [
                *lines[:article_index],
                " ".join(row_tokens[: max(unit_pos, 0)]),
                *lines[article_index + 1 :],
            ]
        )
    revision_codes = _extract_revision_codes(leading_text)
    description = _clean_description(leading_text, revision_codes)
    confidence = 0.95 if article_code and description and unit and amount is not None else 0.65
    return PricingBudgetRow(
        row_number=row_number,
        article_code=article_code,
        canonical_article_code=canonical_article_code(article_code),
        description=description,
        revision_codes=revision_codes,
        unit=unit,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
        raw_text=_clean_text(" ".join(lines)),
        confidence=confidence,
    )


def _extract_revision_codes(text: str) -> list[str]:
    found: list[str] = []
    for match in PERCENT_REVISION_RE.finditer(text):
        code = f"{match.group('code')}-{match.group('num')}"
        canonical = canonical_revision_code(code)
        value = f"{match.group('pct')}%{canonical}"
        if value not in found:
            found.append(value)
    for match in REVISION_RE.finditer(text):
        code = f"{match.group('code')}-{match.group('num')}"
        canonical = canonical_revision_code(code)
        if canonical.startswith(("ΟΔΟ", "ΟΙΚ", "ΥΔΡ", "ΠΡΣ", "ΗΛΜ", "ΛΙΜ")) and not any(item.endswith(canonical) for item in found):
            pct = match.group("pct")
            found.append(f"{pct}%{canonical}" if pct else canonical)
    return found


def _clean_description(text: str, revision_codes: list[str]) -> str:
    description = text
    description = re.sub(r"\d+(?:[.,]\d+)?\s*%\s*[A-ZΑ-ΩΟ∆Δ.]{2,8}\s*[-–—]?\s*\d+[A-ZΑ-ΩA-Z0-9]*", " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\b[A-ZΑ-ΩΟ∆Δ.]{2,8}\s*[-–—]?\s*\d+[A-ZΑ-ΩA-Z0-9]*\b", " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\s*\+\s*", " ", description)
    return _clean_text(description)


def _clean_token(value: str) -> str:
    return value.strip().strip(".,;:")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def upsert_pricing_project(
    db_path: Path,
    *,
    eshidis_id: str,
    official_url: str | None = None,
    title: str | None = None,
    authority_name: str | None = None,
    region: str | None = None,
    budget_display: str | None = None,
    deadline_at: str | None = None,
    status: str = "ACTIVE",
    metadata: dict[str, Any] | None = None,
) -> None:
    ensure_pricing_tables(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO pricing_projects (
                eshidis_id, official_url, title, authority_name, region, budget_display,
                deadline_at, status, first_seen_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(eshidis_id) DO UPDATE SET
                official_url = excluded.official_url,
                title = COALESCE(excluded.title, pricing_projects.title),
                authority_name = COALESCE(excluded.authority_name, pricing_projects.authority_name),
                region = COALESCE(excluded.region, pricing_projects.region),
                budget_display = COALESCE(excluded.budget_display, pricing_projects.budget_display),
                deadline_at = COALESCE(excluded.deadline_at, pricing_projects.deadline_at),
                status = excluded.status,
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json
            """,
            (
                eshidis_id,
                official_url,
                title,
                authority_name,
                region,
                budget_display,
                deadline_at,
                status,
                now,
                now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def upsert_pricing_document(
    db_path: Path,
    *,
    eshidis_id: str,
    document_name: str,
    local_path: str | None = None,
    source_url: str | None = None,
    document_type: str | None = None,
    extraction_status: str | None = None,
    text_path: str | None = None,
    text_sample: str | None = None,
    sha256: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    ensure_pricing_tables(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO pricing_documents (
                eshidis_id, source_url, local_path, document_name, document_type,
                sha256, fetched_at, extraction_status, text_path, text_sample, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(eshidis_id, document_name) DO UPDATE SET
                source_url = COALESCE(excluded.source_url, pricing_documents.source_url),
                local_path = COALESCE(excluded.local_path, pricing_documents.local_path),
                document_type = COALESCE(excluded.document_type, pricing_documents.document_type),
                sha256 = COALESCE(excluded.sha256, pricing_documents.sha256),
                fetched_at = COALESCE(excluded.fetched_at, pricing_documents.fetched_at),
                extraction_status = COALESCE(excluded.extraction_status, pricing_documents.extraction_status),
                text_path = COALESCE(excluded.text_path, pricing_documents.text_path),
                text_sample = COALESCE(excluded.text_sample, pricing_documents.text_sample),
                metadata_json = excluded.metadata_json
            """,
            (
                eshidis_id,
                source_url,
                local_path,
                document_name,
                document_type,
                sha256,
                now,
                extraction_status,
                text_path,
                text_sample,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        row = connection.execute(
            "SELECT id FROM pricing_documents WHERE eshidis_id = ? AND document_name = ?",
            (eshidis_id, document_name),
        ).fetchone()
        connection.commit()
        return int(row[0] if row else cursor.lastrowid)
    finally:
        connection.close()


def upsert_pricing_budget_rows(
    db_path: Path,
    *,
    eshidis_id: str,
    document_id: int | None,
    source_document: str,
    rows: list[PricingBudgetRow],
) -> int:
    ensure_pricing_tables(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            DELETE FROM pricing_budget_rows
            WHERE eshidis_id = ? AND source_document = ?
            """,
            (eshidis_id, source_document),
        )
        inserted = 0
        for row in rows:
            connection.execute(
                """
                INSERT INTO pricing_budget_rows (
                    eshidis_id, document_id, source_document, row_number, article_code,
                    canonical_article_code, description, revision_codes_json, unit,
                    quantity, unit_price, amount, raw_text, confidence, extracted_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eshidis_id,
                    document_id,
                    source_document,
                    row.row_number,
                    row.article_code,
                    row.canonical_article_code,
                    row.description,
                    json.dumps(row.revision_codes, ensure_ascii=False),
                    row.unit,
                    row.quantity,
                    row.unit_price,
                    row.amount,
                    row.raw_text,
                    row.confidence,
                    now,
                    "{}",
                ),
            )
            for alias in {row.article_code, row.canonical_article_code}:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO pricing_article_aliases (
                        canonical_article_code, alias, source, first_seen_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (row.canonical_article_code, alias, "budget_parser", now),
                )
            inserted += 1
        connection.commit()
        return inserted
    finally:
        connection.close()


def consolidate_pricing_project_budget(db_path: Path, *, eshidis_id: str) -> dict[str, Any]:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        stored_rows = connection.execute(
            """
            SELECT *
            FROM pricing_budget_rows
            WHERE eshidis_id = ?
              AND source_document != ?
              AND row_number IS NOT NULL
            ORDER BY row_number, source_document
            """,
            (eshidis_id, MERGED_BUDGET_SOURCE_DOCUMENT),
        ).fetchall()
    finally:
        connection.close()

    best_by_number: dict[int, PricingBudgetRow] = {}
    source_by_number: dict[int, str] = {}
    for row in stored_rows:
        row_number = int(row["row_number"])
        candidate = PricingBudgetRow(
            row_number=row_number,
            article_code=str(row["article_code"] or ""),
            canonical_article_code=str(row["canonical_article_code"] or ""),
            description=str(row["description"] or ""),
            revision_codes=json.loads(str(row["revision_codes_json"] or "[]")),
            unit=row["unit"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            amount=row["amount"],
            raw_text=str(row["raw_text"] or ""),
            confidence=float(row["confidence"] or 0.0),
        )
        source_document = str(row["source_document"] or "")
        current = best_by_number.get(row_number)
        current_source = source_by_number.get(row_number, "")
        if current is None or _budget_row_score(candidate, source_document) > _budget_row_score(current, current_source):
            best_by_number[row_number] = candidate
            source_by_number[row_number] = source_document

    merged_rows = [best_by_number[number] for number in sorted(best_by_number)]
    inserted = upsert_pricing_budget_rows(
        db_path,
        eshidis_id=eshidis_id,
        document_id=None,
        source_document=MERGED_BUDGET_SOURCE_DOCUMENT,
        rows=merged_rows,
    )
    row_numbers = [row.row_number for row in merged_rows if row.row_number is not None]
    missing_numbers: list[int] = []
    if row_numbers:
        expected = set(range(min(row_numbers), max(row_numbers) + 1))
        missing_numbers = sorted(expected.difference(row_numbers))
    amount_total = sum(float(row.amount or 0) for row in merged_rows)
    amount_validation = validate_budget_row_amounts(merged_rows)
    source_documents = sorted(set(source_by_number.values()))
    document_total_validation = validate_budget_document_totals(
        db_path,
        eshidis_id=eshidis_id,
        amount_total=amount_total,
        source_documents=source_documents,
    )
    summary = {
        "rows_merged": len(merged_rows),
        "rows_upserted": inserted,
        "row_number_min": min(row_numbers) if row_numbers else None,
        "row_number_max": max(row_numbers) if row_numbers else None,
        "missing_row_numbers": missing_numbers,
        "amount_total": amount_total,
        "amount_validation": amount_validation,
        "document_total_validation": document_total_validation,
        "source_documents": source_documents,
    }
    _store_pricing_project_budget_audit(db_path, eshidis_id=eshidis_id, summary=summary)
    return summary


def reprocess_pricing_project_from_texts(db_path: Path, *, eshidis_id: str) -> dict[str, Any]:
    """Rebuild a pricing project budget from already extracted text artifacts.

    This is intentionally download-free. It lets parser improvements repair
    existing pricing rows without touching ESHIDIS, browser automation, OCR, or
    stored source documents.
    """
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        documents = connection.execute(
            """
            SELECT id, document_name, text_path
            FROM pricing_documents
            WHERE eshidis_id = ?
              AND text_path IS NOT NULL
            ORDER BY document_name
            """,
            (eshidis_id,),
        ).fetchall()
    finally:
        connection.close()

    document_reports: list[dict[str, Any]] = []
    rows_total = 0
    failed = 0
    for document in documents:
        text_path = Path(str(document["text_path"]))
        if not text_path.is_absolute():
            text_path = Path.cwd() / text_path
        report: dict[str, Any] = {
            "document_id": int(document["id"]),
            "document_name": str(document["document_name"] or ""),
            "text_path": str(text_path),
            "rows_extracted": 0,
            "rows_upserted": 0,
            "status": "PENDING",
        }
        if not text_path.exists():
            failed += 1
            report["status"] = "TEXT_PATH_MISSING"
            document_reports.append(report)
            continue
        text = text_path.read_text(encoding="utf-8", errors="ignore")
        rows = parse_budget_rows_from_text(text)
        inserted = upsert_pricing_budget_rows(
            db_path,
            eshidis_id=eshidis_id,
            document_id=int(document["id"]),
            source_document=str(document["document_name"] or ""),
            rows=rows,
        )
        rows_total += inserted
        report.update(
            {
                "rows_extracted": len(rows),
                "rows_upserted": inserted,
                "status": "REPROCESSED",
            }
        )
        document_reports.append(report)

    merged_budget = consolidate_pricing_project_budget(db_path, eshidis_id=eshidis_id)
    document_total_validation = merged_budget.get("document_total_validation") or {}
    amount_validation = merged_budget.get("amount_validation") or {}
    return {
        "ok": failed == 0 and bool(amount_validation.get("ok")) and bool(document_total_validation.get("ok")),
        "eshidis_id": eshidis_id,
        "summary": {
            "documents_seen": len(documents),
            "documents_reprocessed": sum(1 for item in document_reports if item.get("status") == "REPROCESSED"),
            "failed": failed,
            "pricing_budget_rows_upserted": rows_total,
            "merged_budget_rows": merged_budget.get("rows_merged"),
            "merged_budget_amount_total": merged_budget.get("amount_total"),
            "merged_budget_missing_row_numbers": merged_budget.get("missing_row_numbers"),
            "merged_budget_document_total_validation": document_total_validation,
        },
        "documents": document_reports,
        "merged_budget": merged_budget,
    }


def reprocess_existing_pricing_projects(
    db_path: Path,
    *,
    eshidis_ids: list[str] | None = None,
    only_incomplete: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        if eshidis_ids:
            projects = [{"eshidis_id": str(value)} for value in eshidis_ids]
        else:
            query = "SELECT eshidis_id FROM pricing_projects ORDER BY eshidis_id"
            projects = [dict(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()

    items: list[dict[str, Any]] = []
    completed = 0
    skipped_complete = 0
    failed = 0
    inspected = 0
    for project in projects:
        if limit is not None and inspected >= limit:
            break
        eshidis_id = str(project.get("eshidis_id") or "").strip()
        if not eshidis_id:
            continue
        if only_incomplete and _pricing_project_is_complete(db_path, eshidis_id=eshidis_id):
            skipped_complete += 1
            items.append({"eshidis_id": eshidis_id, "status": "SKIPPED_ALREADY_COMPLETE"})
            continue
        inspected += 1
        try:
            result = reprocess_pricing_project_from_texts(db_path, eshidis_id=eshidis_id)
        except Exception as exc:  # pragma: no cover - maintenance boundary
            failed += 1
            items.append({"eshidis_id": eshidis_id, "status": "FAILED_EXCEPTION", "error": repr(exc)})
            continue
        status = "OK" if result.get("ok") else "NEEDS_REVIEW"
        if status == "OK":
            completed += 1
        else:
            failed += 1
        items.append(
            {
                "eshidis_id": eshidis_id,
                "status": status,
                "summary": result.get("summary"),
            }
        )

    summary = {
        "projects_seen": len(projects),
        "projects_inspected": inspected,
        "completed": completed,
        "skipped_complete": skipped_complete,
        "needs_review_or_failed": failed,
        "limit": limit,
        "only_incomplete": only_incomplete,
    }
    return {
        "ok": failed == 0,
        "summary": summary,
        "items": items,
    }


def _store_pricing_project_budget_audit(db_path: Path, *, eshidis_id: str, summary: dict[str, Any]) -> None:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT metadata_json FROM pricing_projects WHERE eshidis_id = ?",
            (eshidis_id,),
        ).fetchone()
        if row is None:
            return
        try:
            metadata = json.loads(str(row[0] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        metadata["pricing_budget_audit"] = {
            "audited_at": _utc_now_iso(),
            "rows_merged": summary["rows_merged"],
            "row_number_min": summary["row_number_min"],
            "row_number_max": summary["row_number_max"],
            "missing_row_numbers": summary["missing_row_numbers"],
            "amount_total": summary["amount_total"],
            "amount_validation": summary["amount_validation"],
            "document_total_validation": summary["document_total_validation"],
            "source_documents": summary["source_documents"],
        }
        connection.execute(
            """
            UPDATE pricing_projects
            SET metadata_json = ?, updated_at = ?
            WHERE eshidis_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), _utc_now_iso(), eshidis_id),
        )
        connection.commit()
    finally:
        connection.close()


def validate_budget_row_amounts(
    rows: list[PricingBudgetRow],
    *,
    tolerance: float = 0.02,
    relative_tolerance: float = 0.005,
) -> dict[str, Any]:
    checked = 0
    skipped = 0
    mismatches: list[dict[str, Any]] = []
    for row in rows:
        if row.quantity is None or row.unit_price is None or row.amount is None:
            skipped += 1
            continue
        checked += 1
        expected, actual, difference = _budget_row_amount_delta(row)
        if _budget_row_amount_is_valid(row, tolerance=tolerance, relative_tolerance=relative_tolerance):
            continue
        mismatches.append(
            {
                "row_number": row.row_number,
                "article_code": row.article_code,
                "quantity": row.quantity,
                "unit_price": row.unit_price,
                "amount": row.amount,
                "expected_amount": expected,
                "difference": difference,
                "description": row.description[:160],
            }
        )
    return {
        "checked": checked,
        "skipped": skipped,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "ok": not mismatches,
        "tolerance": tolerance,
        "relative_tolerance": relative_tolerance,
    }


def validate_budget_document_totals(
    db_path: Path,
    *,
    eshidis_id: str,
    amount_total: float,
    source_documents: list[str],
    tolerance: float = 0.02,
    relative_tolerance: float = 0.001,
) -> dict[str, Any]:
    candidates = _budget_total_candidates_for_project(
        db_path,
        eshidis_id=eshidis_id,
        source_documents=source_documents,
    )
    if not candidates:
        return {
            "ok": None,
            "status": "NO_REFERENCE_TOTAL_FOUND",
            "amount_total": amount_total,
            "candidate_count": 0,
            "candidates": [],
        }
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -float(candidate["confidence"]),
            abs(float(candidate["amount"]) - float(amount_total)),
        ),
    )
    best = ranked[0]
    difference = round(float(amount_total) - float(best["amount"]), 4)
    allowed = max(tolerance, abs(float(best["amount"])) * relative_tolerance)
    ok = abs(difference) <= allowed
    return {
        "ok": ok,
        "status": "OK" if ok else "MISMATCH",
        "amount_total": amount_total,
        "reference_total": best["amount"],
        "difference": difference,
        "allowed_difference": allowed,
        "reference": best,
        "candidate_count": len(candidates),
        "candidates": ranked[:10],
    }


def _budget_total_candidates_for_project(
    db_path: Path,
    *,
    eshidis_id: str,
    source_documents: list[str],
) -> list[dict[str, Any]]:
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT document_name, text_path
            FROM pricing_documents
            WHERE eshidis_id = ?
              AND text_path IS NOT NULL
            """,
            (eshidis_id,),
        ).fetchall()
    finally:
        connection.close()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        text_path = Path(str(row["text_path"]))
        if not text_path.exists():
            continue
        try:
            text = text_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for candidate in extract_budget_total_candidates(text):
            candidates.append({**candidate, "source_document": row["document_name"]})
    return candidates


def extract_budget_total_candidates(text: str) -> list[dict[str, Any]]:
    amount_re = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}")
    candidates: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        clean = _clean_text(line)
        if not clean:
            continue
        normalized = strip_accents(clean).upper()
        if any(marker in normalized for marker in ("ΦΠΑ", "Φ.Π.Α", "ΤΕΛΙΚΗ", "ΑΠΡΟΒΛ", "ΑΝΑΘΕΩΡΗΣ", "Γ.Ε", "ΓΕ & ΟΕ")):
            continue
        confidence = 0.0
        if "ΣΥΝΟΛΟ Α+Β" in normalized:
            confidence = 1.0
        elif "ΣΥΝΟΛΟ ΚΟΣΤΟΥΣ ΕΡΓΑΣΙΩΝ" in normalized:
            confidence = 0.98
        elif "ΔΑΠΑΝΗ ΕΡΓΑΣΙΩΝ" in normalized:
            confidence = 0.95
        elif "ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ" in normalized:
            confidence = 0.9
        elif normalized.startswith("ΣΥΝΟΛΟ ") and "ΕΡΓΑΣ" in normalized:
            confidence = 0.85
        if confidence <= 0:
            continue
        amounts = [parse_greek_decimal(match.group(0)) for match in amount_re.finditer(clean)]
        amounts = [amount for amount in amounts if amount is not None]
        if not amounts:
            continue
        candidates.append(
            {
                "amount": amounts[-1],
                "line_number": line_number,
                "label": clean[:220],
                "confidence": confidence,
            }
        )
    return candidates


def _budget_row_score(row: PricingBudgetRow, source_document: str) -> tuple[int, int, int, float, int]:
    source_upper = strip_accents(source_document).upper()
    source_score = 0
    if "ΠΡΟΥΠΟΛΟΓΙΣ" in source_upper:
        source_score = 30
    elif "ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ" in source_upper or "ΤΕΧΝΙΚΗ ΕΚΘΕΣΗ" in source_upper:
        source_score = 20
    elif "ΤΙΜΟΛΟΓ" in source_upper:
        source_score = 10
    completeness = sum(1 for value in (row.unit, row.quantity, row.unit_price, row.amount) if value is not None)
    amount_score = _budget_row_amount_score(row)
    at_alignment_score = _budget_row_at_alignment_score(row)
    return source_score, at_alignment_score, amount_score, row.confidence, completeness


def _budget_row_at_alignment_score(row: PricingBudgetRow) -> int:
    if row.row_number is None:
        return 0
    tokens = [_clean_token(token) for token in _clean_text(row.raw_text).split()]
    unit_index = None
    if row.unit:
        clean_unit = row.unit.lower().rstrip(".")
        unit_index = next((index for index, token in enumerate(tokens) if token.lower().rstrip(".") == clean_unit), None)
    candidate_tokens = tokens[:unit_index] if unit_index is not None else tokens
    at_tokens = [token for token in candidate_tokens if re.fullmatch(r"\d{3}", token)]
    if not at_tokens:
        return 0
    expected = f"{row.row_number:03d}"
    if at_tokens[0] == expected:
        return 30
    if expected in at_tokens:
        return 20
    return -30


def _budget_row_amount_delta(row: PricingBudgetRow) -> tuple[float, float, float]:
    expected = round(float(row.quantity or 0) * float(row.unit_price or 0), 2)
    actual = round(float(row.amount or 0), 2)
    return expected, actual, round(actual - expected, 2)


def _budget_row_amount_is_valid(
    row: PricingBudgetRow,
    *,
    tolerance: float = 0.02,
    relative_tolerance: float = 0.005,
) -> bool:
    if row.quantity is None or row.unit_price is None or row.amount is None:
        return False
    expected, _actual, difference = _budget_row_amount_delta(row)
    if abs(difference) <= tolerance:
        return True
    if expected and abs(difference) / abs(expected) <= relative_tolerance:
        return True
    return False


def _budget_row_amount_score(row: PricingBudgetRow) -> int:
    if row.quantity is None or row.unit_price is None or row.amount is None:
        return 0
    return 10 if _budget_row_amount_is_valid(row) else -10


def _pricing_document_snapshot(db_path: Path, *, eshidis_id: str, document_name: str) -> dict[str, Any] | None:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT id, local_path, document_type, sha256, extraction_status, text_path
            FROM pricing_documents
            WHERE eshidis_id = ? AND document_name = ?
            """,
            (eshidis_id, document_name),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        connection.close()


def _pricing_document_is_indexed(db_path: Path, *, eshidis_id: str, document_name: str) -> bool:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    try:
        row_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM pricing_budget_rows
            WHERE eshidis_id = ? AND source_document = ?
            """,
            (eshidis_id, document_name),
        ).fetchone()[0]
        if int(row_count) > 0:
            return True
        snapshot = connection.execute(
            """
            SELECT document_type, extraction_status, text_path
            FROM pricing_documents
            WHERE eshidis_id = ? AND document_name = ?
            """,
            (eshidis_id, document_name),
        ).fetchone()
        if snapshot is None:
            return False
        document_type, extraction_status, text_path = snapshot
        if extraction_status == "SKIPPED_NON_PRICING_DOCUMENT":
            return True
        if text_path and Path(str(text_path)).exists():
            return True
        if document_type == "archive" and extraction_status in {"ARCHIVE_EXTRACTED", "ARCHIVE_SKIPPED_EXISTING"}:
            child_prefix = f"{document_name}/"
            child_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM pricing_documents
                WHERE eshidis_id = ? AND document_name >= ? AND document_name < ?
                """,
                (eshidis_id, child_prefix, child_prefix + "\U0010ffff"),
            ).fetchone()[0]
            return int(child_count) > 0
        return False
    finally:
        connection.close()


def _recover_partial_pricing_project(db_path: Path, *, eshidis_id: str) -> dict[str, Any] | None:
    """Finish cheap consolidation for projects that already have parsed rows.

    This protects batch runs from re-entering expensive browser/download/OCR
    work when a previous process was interrupted after raw budget rows were
    persisted but before the project-level merged budget was written.
    """
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    try:
        raw_rows = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM pricing_budget_rows
                WHERE eshidis_id = ?
                  AND source_document != ?
                """,
                (eshidis_id, MERGED_BUDGET_SOURCE_DOCUMENT),
            ).fetchone()[0]
        )
        merged_rows = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM pricing_budget_rows
                WHERE eshidis_id = ?
                  AND source_document = ?
                """,
                (eshidis_id, MERGED_BUDGET_SOURCE_DOCUMENT),
            ).fetchone()[0]
        )
        document_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM pricing_documents WHERE eshidis_id = ?",
                (eshidis_id,),
            ).fetchone()[0]
        )
    finally:
        connection.close()

    if raw_rows <= 0 or merged_rows > 0:
        return None

    merged_budget = consolidate_pricing_project_budget(db_path, eshidis_id=eshidis_id)
    return {
        "ok": True,
        "eshidis_id": eshidis_id,
        "summary": {
            "attachments_found": None,
            "attachments_requested": 0,
            "downloaded": 0,
            "skipped_download": document_count,
            "skipped_indexed": document_count,
            "failed": 0,
            "pricing_budget_rows_upserted": 0,
            "merged_budget_rows": merged_budget["rows_merged"],
            "merged_budget_amount_total": merged_budget["amount_total"],
            "merged_budget_missing_row_numbers": merged_budget["missing_row_numbers"],
            "merged_budget_document_total_validation": merged_budget["document_total_validation"],
            "heavy_files_deleted": 0,
            "partial_recovered": True,
            "raw_budget_rows_reused": raw_rows,
        },
        "project": _pricing_project_snapshot(db_path, eshidis_id=eshidis_id),
        "documents": [],
        "merged_budget": merged_budget,
        "guard": {
            "status": "PARTIAL_PROJECT_RECOVERED_WITHOUT_REFETCH",
            "reason": "raw budget rows existed but merged project budget was missing",
        },
    }


def _pricing_project_snapshot(db_path: Path, *, eshidis_id: str) -> dict[str, Any]:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT title, authority_name, region, budget_display, deadline_at
            FROM pricing_projects
            WHERE eshidis_id = ?
            """,
            (eshidis_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        connection.close()


def _pricing_project_is_complete(db_path: Path, *, eshidis_id: str) -> bool:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM pricing_documents WHERE eshidis_id = ?) AS document_count,
                (SELECT COUNT(*) FROM pricing_documents WHERE eshidis_id = ? AND text_path IS NOT NULL) AS text_count,
                (SELECT COUNT(*) FROM pricing_budget_rows WHERE eshidis_id = ? AND source_document = ?) AS merged_row_count
            """,
            (eshidis_id, eshidis_id, eshidis_id, MERGED_BUDGET_SOURCE_DOCUMENT),
        ).fetchone()
        if row is None:
            return False
        if not (int(row[0] or 0) > 0 and int(row[1] or 0) > 0 and int(row[2] or 0) > 0):
            return False
        audit_row = connection.execute(
            "SELECT metadata_json FROM pricing_projects WHERE eshidis_id = ?",
            (eshidis_id,),
        ).fetchone()
        if audit_row is None:
            return False
        try:
            metadata = json.loads(str(audit_row[0] or "{}"))
        except json.JSONDecodeError:
            return False
        audit = metadata.get("pricing_budget_audit") or {}
        amount_validation = audit.get("amount_validation") or {}
        document_total_validation = audit.get("document_total_validation") or {}
        return bool(amount_validation.get("ok") is True and document_total_validation.get("ok") is True)
    finally:
        connection.close()


def _pricing_run_insert(db_path: Path, *, run_id: str, mode: str, started_at: str) -> None:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO pricing_runs (run_id, mode, started_at, status, summary_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, mode, started_at, "RUNNING", "{}"),
        )
        connection.commit()
    finally:
        connection.close()


def _pricing_run_finish(db_path: Path, *, run_id: str, status: str, summary: dict[str, Any]) -> None:
    ensure_pricing_tables(db_path)
    connection = connect(db_path)
    try:
        connection.execute(
            """
            UPDATE pricing_runs
               SET finished_at = ?, status = ?, summary_json = ?
             WHERE run_id = ?
            """,
            (_utc_now_iso(), status, json.dumps(summary, ensure_ascii=False, sort_keys=True), run_id),
        )
        connection.commit()
    finally:
        connection.close()


def ingest_pricing_budget_pdf(
    db_path: Path,
    *,
    eshidis_id: str,
    pdf_path: Path,
    document_name: str | None = None,
) -> dict[str, Any]:
    text = extract_budget_text(pdf_path)
    rows = parse_budget_rows_from_text(text)
    upsert_pricing_project(db_path, eshidis_id=eshidis_id)
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id=eshidis_id,
        document_name=document_name or pdf_path.name,
        local_path=str(pdf_path),
        document_type="budget",
        extraction_status="TEXT_EXTRACTED" if text.strip() else "NO_TEXT",
        text_sample=text[:4000] if text else None,
    )
    inserted = upsert_pricing_budget_rows(
        db_path,
        eshidis_id=eshidis_id,
        document_id=document_id,
        source_document=document_name or pdf_path.name,
        rows=rows,
    )
    return {
        "ok": True,
        "eshidis_id": eshidis_id,
        "document_id": document_id,
        "rows_extracted": len(rows),
        "rows_upserted": inserted,
        "rows": [asdict(row) for row in rows],
    }


def ingest_pricing_eshidis_project(
    db_path: Path,
    *,
    eshidis_id: str,
    work_dir: Path = Path("work/pricing"),
    limit: int = 50,
    allow_insecure_tls: bool = False,
    keep_heavy_files: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    if not eshidis_id.isdigit():
        raise ValueError("Pricing ESHIDIS ingest accepts only a numeric ESHIDIS id.")
    if limit < 1:
        raise ValueError("limit must be positive.")
    ensure_pricing_tables(db_path)
    if not force:
        recovered = _recover_partial_pricing_project(db_path, eshidis_id=eshidis_id)
        if recovered is not None:
            recovered["db_path"] = str(db_path)
            recovered["work_dir"] = str(work_dir)
            return recovered
    audit_dir = work_dir / "source_audit"
    download_dir = work_dir / "downloads" / eshidis_id
    text_dir = work_dir / "extracted_text" / eshidis_id
    archive_dir = work_dir / "archives" / eshidis_id
    audit_path = audit_dir / f"eshidis_resource_audit_{eshidis_id}.json"
    resource_payload = fetch_resource_audit(
        eshidis_id,
        audit_path,
        allow_insecure_tls=allow_insecure_tls,
    )
    details = parse_eshidis_resource_text(
        str(resource_payload.get("target_url") or ""),
        str(resource_payload.get("snapshot", {}).get("bodyTextSample") or ""),
    )
    attachment_body = _find_attachment_body(resource_payload)
    attachment_listing = parse_eshidis_attachment_xml(attachment_body) if attachment_body else None
    filenames = list(attachment_listing.filenames if attachment_listing else ())
    upsert_pricing_project(
        db_path,
        eshidis_id=eshidis_id,
        official_url=details.source_url,
        title=details.title or details.project_title,
        authority_name=details.contracting_authority,
        region=details.location,
        budget_display=details.budget_with_vat,
        deadline_at=details.submission_deadline,
        metadata={
            "source": "eshidis_pricing_ingest",
            "audit_path": str(audit_path),
            "cpv": details.cpv,
            "publication_date": details.publication_date,
            "attachment_rows": attachment_listing.row_count if attachment_listing else None,
        },
    )
    documents: list[dict[str, Any]] = []
    downloaded = 0
    skipped_download = 0
    skipped_indexed = 0
    failed = 0
    rows_total = 0
    cleanup_deleted = 0
    for row_index, filename in enumerate(filenames[:limit]):
        download_audit_path = audit_dir / f"eshidis_download_audit_{eshidis_id}_{row_index}.json"
        existing = _pricing_document_snapshot(db_path, eshidis_id=eshidis_id, document_name=filename)
        download_payload: dict[str, Any] = {}
        downloaded_file: dict[str, Any] | None = None
        if not force and existing and existing.get("local_path") and Path(str(existing["local_path"])).exists():
            skipped_download += 1
            downloaded_file = {
                "name": filename,
                "path": str(existing["local_path"]),
                "size_bytes": Path(str(existing["local_path"])).stat().st_size,
                "sha256": existing.get("sha256"),
            }
        else:
            download_payload = download_attachment_audit(
                eshidis_id,
                row_index,
                download_audit_path,
                download_dir,
                allow_insecure_tls=allow_insecure_tls,
            )
            raw_downloaded_file = download_payload.get("downloaded_file")
            downloaded_file = raw_downloaded_file if isinstance(raw_downloaded_file, dict) else None
        doc_report: dict[str, Any] = {
            "row_index": row_index,
            "document_name": filename,
            "download_audit_path": str(download_audit_path),
            "download_status": "failed",
            "download_error": download_payload.get("download_error"),
            "rows_extracted": 0,
        }
        if not isinstance(downloaded_file, dict) or not downloaded_file.get("path"):
            failed += 1
            documents.append(doc_report)
            continue
        if download_payload:
            downloaded += 1
        local_path = Path(str(downloaded_file["path"]))
        if not force and _pricing_document_is_indexed(db_path, eshidis_id=eshidis_id, document_name=filename):
            skipped_indexed += 1
            indexed = {
                "document_type": existing.get("document_type") if existing else None,
                "extraction_status": existing.get("extraction_status") if existing else "SKIPPED_INDEXED",
                "ocr_status": "SKIPPED_INDEXED",
                "text_path": existing.get("text_path") if existing else None,
                "rows_extracted": 0,
                "rows_upserted": 0,
                "skipped_reason": "already indexed",
            }
        else:
            indexed = _index_pricing_document_path(
                db_path,
                eshidis_id=eshidis_id,
                source_url=details.source_url,
                document_name=filename,
                local_path=local_path,
                row_index=row_index,
                text_dir=text_dir,
                archive_dir=archive_dir,
                keep_heavy_files=keep_heavy_files,
                metadata={"download_audit_path": str(download_audit_path), "size_bytes": downloaded_file.get("size_bytes")},
                force=force,
            )
        rows_inserted = int(indexed.get("rows_upserted") or 0)
        rows_total += rows_inserted
        if not keep_heavy_files and download_payload:
            try:
                local_path.unlink()
                cleanup_deleted += 1
            except FileNotFoundError:
                pass
        doc_report.update(
            {
                "download_status": "downloaded" if download_payload else "skipped_existing",
                "local_path": str(local_path) if keep_heavy_files else None,
                "size_bytes": downloaded_file.get("size_bytes"),
                "sha256": downloaded_file.get("sha256"),
                "document_type": indexed.get("document_type"),
                "extraction_status": indexed.get("extraction_status"),
                "ocr_status": indexed.get("ocr_status"),
                "text_path": indexed.get("text_path"),
                "rows_extracted": indexed.get("rows_extracted", 0),
                "rows_upserted": rows_inserted,
                "index_status": "skipped_existing" if indexed.get("skipped_reason") else "indexed",
            }
        )
        if indexed.get("extracted_documents"):
            doc_report["extracted_documents"] = indexed["extracted_documents"]
        documents.append(doc_report)
    merged_budget = consolidate_pricing_project_budget(db_path, eshidis_id=eshidis_id)
    return {
        "ok": failed == 0,
        "eshidis_id": eshidis_id,
        "db_path": str(db_path),
        "work_dir": str(work_dir),
        "official_url": details.source_url,
        "summary": {
            "attachments_found": len(filenames),
            "attachments_requested": min(len(filenames), limit),
            "downloaded": downloaded,
            "skipped_download": skipped_download,
            "skipped_indexed": skipped_indexed,
            "failed": failed,
            "pricing_budget_rows_upserted": rows_total,
            "merged_budget_rows": merged_budget["rows_merged"],
            "merged_budget_amount_total": merged_budget["amount_total"],
            "merged_budget_missing_row_numbers": merged_budget["missing_row_numbers"],
            "merged_budget_document_total_validation": merged_budget["document_total_validation"],
            "heavy_files_deleted": cleanup_deleted,
        },
        "project": {
            "title": details.title or details.project_title,
            "authority_name": details.contracting_authority,
            "region": details.location,
            "budget_display": details.budget_with_vat,
            "deadline_at": details.submission_deadline,
        },
        "documents": documents,
        "merged_budget": merged_budget,
    }


def ingest_pricing_active_candidates(
    db_path: Path,
    *,
    candidates_payload: dict[str, Any],
    work_dir: Path = Path("work/pricing"),
    attachment_limit: int = 50,
    project_limit: int | None = None,
    max_new_projects: int | None = None,
    allow_insecure_tls: bool = False,
    keep_heavy_files: bool = False,
    force: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Ingest a whole active ESHIDIS candidate list with explicit run accounting."""
    if attachment_limit < 1:
        raise ValueError("attachment_limit must be positive.")
    if project_limit is not None and project_limit < 1:
        raise ValueError("project_limit must be positive when provided.")
    if max_new_projects is not None and max_new_projects < 1:
        raise ValueError("max_new_projects must be positive when provided.")
    if project_limit is not None and max_new_projects is not None:
        raise ValueError("project_limit and max_new_projects cannot be combined.")

    ensure_pricing_tables(db_path)
    started_at = _utc_now_iso()
    run_id = run_id or f"pricing-active-{uuid.uuid4().hex}"
    _pricing_run_insert(db_path, run_id=run_id, mode="ESHIDIS_ACTIVE_PRICING_BATCH", started_at=started_at)

    candidates = _pricing_candidates_from_payload(candidates_payload)
    candidate_count = len(candidates)
    selected = candidates[:project_limit] if project_limit is not None else candidates
    items: list[dict[str, Any]] = []
    completed = 0
    skipped_existing = 0
    failed = 0
    partial = 0
    skipped_invalid = 0
    attempted_new = 0
    target_reached = False
    inspected_count = 0

    for candidate in selected:
        if max_new_projects is not None and attempted_new >= max_new_projects:
            target_reached = True
            break
        inspected_count += 1
        eshidis_id = candidate.get("eshidis_id")
        if not eshidis_id or not str(eshidis_id).isdigit():
            skipped_invalid += 1
            items.append(
                {
                    "eshidis_id": eshidis_id,
                    "status": "SKIPPED_INVALID_IDENTIFIER",
                    "reason": "candidate does not expose a numeric ESHIDIS id",
                    "candidate": candidate,
                }
            )
            continue
        eshidis_id = str(eshidis_id)
        if not force and _pricing_project_is_complete(db_path, eshidis_id=eshidis_id):
            skipped_existing += 1
            snapshot = _pricing_project_snapshot(db_path, eshidis_id=eshidis_id)
            items.append(
                {
                    "eshidis_id": eshidis_id,
                    "status": "SKIPPED_ALREADY_COMPLETE",
                    "project": snapshot,
                    "candidate": candidate,
                }
            )
            continue
        attempted_new += 1
        try:
            result = ingest_pricing_eshidis_project(
                db_path,
                eshidis_id=eshidis_id,
                work_dir=work_dir,
                limit=attachment_limit,
                allow_insecure_tls=allow_insecure_tls,
                keep_heavy_files=keep_heavy_files,
                force=force,
            )
        except Exception as exc:  # pragma: no cover - live source defensive boundary
            failed += 1
            items.append(
                {
                    "eshidis_id": eshidis_id,
                    "status": "FAILED_EXCEPTION",
                    "error": repr(exc),
                    "candidate": candidate,
                }
            )
            continue

        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        merged_rows = int(summary.get("merged_budget_rows") or 0)
        item_status = "COMPLETED" if result.get("ok") and merged_rows > 0 else "PARTIAL_OR_FAILED"
        if item_status == "COMPLETED":
            completed += 1
        elif result.get("ok"):
            partial += 1
        else:
            failed += 1
        items.append(
            {
                "eshidis_id": eshidis_id,
                "status": item_status,
                "ok": bool(result.get("ok")),
                "summary": summary,
                "project": result.get("project"),
                "candidate": candidate,
                "error": result.get("error"),
            }
        )

    not_selected = max(candidate_count - inspected_count, 0)
    if project_limit is not None:
        not_selected = max(candidate_count - len(selected), 0)
    target_remaining = max((max_new_projects or 0) - attempted_new, 0) if max_new_projects is not None else 0
    summary = {
        "run_id": run_id,
        "mode": "ESHIDIS_ACTIVE_PRICING_BATCH",
        "started_at": started_at,
        "candidate_count": candidate_count,
        "selected_count": inspected_count if project_limit is None else len(selected),
        "inspected_count": inspected_count if project_limit is None else len(selected),
        "not_selected_due_to_limit": not_selected,
        "completed": completed,
        "skipped_existing": skipped_existing,
        "attempted_new": attempted_new,
        "max_new_projects": max_new_projects,
        "target_new_remaining": target_remaining,
        "target_reached": target_reached or (max_new_projects is not None and attempted_new >= max_new_projects),
        "partial": partial,
        "failed": failed,
        "skipped_invalid": skipped_invalid,
        "remaining_unprocessed": target_remaining if max_new_projects is not None else not_selected,
        "remaining_candidates_not_scanned_after_target": not_selected if max_new_projects is not None else 0,
        "attachment_limit": attachment_limit,
        "project_limit": project_limit,
        "source_coverage": candidates_payload.get("coverage") if isinstance(candidates_payload.get("coverage"), dict) else None,
    }
    if max_new_projects is not None:
        status = "COMPLETED" if failed == 0 and partial == 0 and skipped_invalid == 0 and target_remaining == 0 else "INCOMPLETE"
    else:
        status = "COMPLETED" if failed == 0 and partial == 0 and skipped_invalid == 0 and not_selected == 0 else "INCOMPLETE"
    _pricing_run_finish(db_path, run_id=run_id, status=status, summary={**summary, "items": items})
    return {
        "ok": status == "COMPLETED",
        "run_id": run_id,
        "status": status,
        "summary": summary,
        "items": items,
    }


def ingest_pricing_active_eshidis(
    db_path: Path,
    *,
    work_dir: Path = Path("work/pricing"),
    discovery_limit: int = 500,
    attachment_limit: int = 50,
    project_limit: int | None = None,
    max_new_projects: int | None = None,
    allow_insecure_tls: bool = False,
    keep_heavy_files: bool = False,
    force: bool = False,
    report_path: Path = Path("work/reports/pricing_active_candidates.json"),
) -> dict[str, Any]:
    if discovery_limit < 1:
        raise ValueError("discovery_limit must be positive.")
    payload = discover_active_candidates_audit(
        report_path,
        status_value="2",
        limit=discovery_limit,
        allow_insecure_tls=allow_insecure_tls,
    )
    batch = ingest_pricing_active_candidates(
        db_path,
        candidates_payload=payload,
        work_dir=work_dir,
        attachment_limit=attachment_limit,
        project_limit=project_limit,
        max_new_projects=max_new_projects,
        allow_insecure_tls=allow_insecure_tls,
        keep_heavy_files=keep_heavy_files,
        force=force,
    )
    return {
        **batch,
        "discovery_report_path": str(report_path),
        "discovery": {
            "candidates_found": len(payload.get("candidates") if isinstance(payload.get("candidates"), list) else []),
            "coverage": payload.get("coverage"),
            "navigation_error": payload.get("navigation_error"),
        },
    }


def _pricing_candidates_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        return []
    deduped: dict[str, dict[str, Any]] = {}
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        eshidis_id = str(candidate.get("eshidis_id") or "").strip()
        if not eshidis_id:
            continue
        deduped.setdefault(eshidis_id, dict(candidate))
    return sorted(
        deduped.values(),
        key=lambda item: (_pricing_deadline_sort_key(str(item.get("submission_deadline") or "")), str(item.get("eshidis_id") or "")),
    )


def _pricing_deadline_sort_key(value: str) -> str:
    parsed = _parse_eshidis_datetime(value)
    return parsed.isoformat() if parsed else "9999-12-31T23:59:59+00:00"


def _parse_eshidis_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    formats = ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _find_attachment_body(payload: dict[str, Any]) -> str | None:
    response_bodies = payload.get("response_bodies")
    if not isinstance(response_bodies, list):
        return None
    for item in response_bodies:
        if not isinstance(item, dict):
            continue
        sample = item.get("body_sample")
        if isinstance(sample, str) and '_rowCount="' in sample and "t1:" in sample:
            return sample
    return None


def _index_pricing_document_path(
    db_path: Path,
    *,
    eshidis_id: str,
    source_url: str | None,
    document_name: str,
    local_path: Path,
    row_index: int,
    text_dir: Path,
    archive_dir: Path,
    keep_heavy_files: bool,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    suffix = local_path.suffix.lower()
    if suffix in {".zip", ".rar"}:
        destination = archive_dir / f"{row_index}_{_safe_path_part(local_path.stem)}"
        extracted = _extract_pricing_archive(local_path, destination, force=force)
        child_reports: list[dict[str, Any]] = []
        rows_total = 0
        for child_path in extracted.get("files", []):
            if not isinstance(child_path, Path):
                continue
            child_name = f"{document_name}/{child_path.relative_to(extracted['directory'])}"
            child_report = _index_pricing_document_path(
                db_path,
                eshidis_id=eshidis_id,
                source_url=source_url,
                document_name=child_name,
                local_path=child_path,
                row_index=row_index,
                text_dir=text_dir,
                archive_dir=archive_dir,
                keep_heavy_files=True,
                metadata={**(metadata or {}), "archive_path": str(local_path)},
                force=force,
            )
            rows_total += int(child_report.get("rows_upserted") or 0)
            child_reports.append(child_report)
        upsert_pricing_document(
            db_path,
            eshidis_id=eshidis_id,
            document_name=document_name,
            local_path=str(local_path) if keep_heavy_files else None,
            source_url=source_url,
            document_type="archive",
            extraction_status=str(extracted.get("status") or "ARCHIVE_EXTRACTED"),
            metadata={**(metadata or {}), "archive_error": extracted.get("error"), "extracted_files": len(child_reports)},
        )
        return {
            "document_type": "archive",
            "extraction_status": str(extracted.get("status") or "ARCHIVE_EXTRACTED"),
            "ocr_status": "NOT_APPLICABLE",
            "text_path": None,
            "rows_extracted": rows_total,
            "rows_upserted": rows_total,
            "extracted_documents": child_reports,
        }

    if not _is_pricing_candidate_document(document_name, local_path):
        document_id = upsert_pricing_document(
            db_path,
            eshidis_id=eshidis_id,
            document_name=document_name,
            local_path=str(local_path),
            source_url=source_url,
            document_type=local_path.suffix.lower().lstrip(".") or "unknown",
            extraction_status="SKIPPED_NON_PRICING_DOCUMENT",
            metadata=metadata or {},
        )
        return {
            "document_name": document_name,
            "document_id": document_id,
            "document_type": local_path.suffix.lower().lstrip(".") or "unknown",
            "extraction_status": "SKIPPED_NON_PRICING_DOCUMENT",
            "ocr_status": "NOT_ATTEMPTED",
            "text_path": None,
            "rows_extracted": 0,
            "rows_upserted": 0,
        }

    analysis = analyze_document(local_path, original_name=document_name)
    full_text = extract_budget_text(local_path)
    if not full_text.strip():
        full_text = analysis.full_text or ""
    text_path = _write_pricing_text_artifact(text_dir, eshidis_id, row_index, document_name, full_text)
    extraction_status = analysis.extraction_status if analysis.full_text else ("TEXT_EXTRACTED" if full_text.strip() else analysis.extraction_status)
    document_id = upsert_pricing_document(
        db_path,
        eshidis_id=eshidis_id,
        document_name=document_name,
        local_path=str(local_path),
        source_url=source_url,
        document_type=analysis.document_type,
        extraction_status=extraction_status,
        text_path=str(text_path) if text_path else None,
        text_sample=analysis.text_sample or (full_text[:4000] if full_text else None),
        metadata={
            **(metadata or {}),
            "ocr_status": analysis.ocr_status,
            "ocr_error": analysis.ocr_error,
            "extraction_error": analysis.extraction_error,
            "page_or_sheet_count": analysis.page_or_sheet_count,
        },
    )
    budget_rows = parse_budget_rows_from_text(full_text or "")
    rows_inserted = 0
    if budget_rows:
        rows_inserted = upsert_pricing_budget_rows(
            db_path,
            eshidis_id=eshidis_id,
            document_id=document_id,
            source_document=document_name,
            rows=budget_rows,
        )
    return {
        "document_name": document_name,
        "document_type": analysis.document_type,
        "extraction_status": extraction_status,
        "ocr_status": analysis.ocr_status,
        "text_path": str(text_path) if text_path else None,
        "rows_extracted": len(budget_rows),
        "rows_upserted": rows_inserted,
    }


def _is_pricing_candidate_document(document_name: str, local_path: Path) -> bool:
    suffix = local_path.suffix.lower()
    if suffix in {".txt", ".text"}:
        return True
    if suffix != ".pdf":
        return False
    normalized = strip_accents(f"{document_name} {local_path.name}").upper()
    compact = re.sub(r"[^A-ZΑ-Ω0-9]+", "", normalized)
    candidate_terms = (
        "ΠΡΟΥΠΟΛΟΓ",
        "ΤΙΜΟΛΟΓ",
        "ΟΙΚΟΝΟΜΙΚ",
        "ΤΕΧΝΙΚΗΕΚΘΕΣΗ",
        "ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ",
        "ΜΕΛΕΤΗ",
    )
    return any(term in normalized or term in compact for term in candidate_terms)


def _extract_pricing_archive(path: Path, destination: Path, *, force: bool = False) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    existing_files = [
        item for item in sorted(destination.rglob("*")) if item.is_file() and item.suffix.lower() in {".pdf", ".xml", ".txt", ".zip", ".rar"}
    ]
    if existing_files and not force:
        return {"status": "ARCHIVE_SKIPPED_EXISTING", "directory": destination, "files": existing_files, "error": None}
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                archive.extractall(destination)
        else:
            unar = shutil.which("unar")
            if not unar:
                return {"status": "ARCHIVE_TOOL_MISSING", "directory": destination, "files": [], "error": "Missing unar."}
            completed = subprocess.run(
                [unar, "-quiet", "-force-overwrite", "-output-directory", str(destination), str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if completed.returncode != 0:
                return {
                    "status": "ARCHIVE_EXTRACTION_FAILED",
                    "directory": destination,
                    "files": [],
                    "error": completed.stderr.strip() or completed.stdout.strip() or f"unar exited {completed.returncode}",
                }
    except Exception as exc:
        return {"status": "ARCHIVE_EXTRACTION_FAILED", "directory": destination, "files": [], "error": repr(exc)}
    files = [item for item in sorted(destination.rglob("*")) if item.is_file() and item.suffix.lower() in {".pdf", ".xml", ".txt", ".zip", ".rar"}]
    return {"status": "ARCHIVE_EXTRACTED", "directory": destination, "files": files, "error": None}


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^0-9A-Za-zΑ-Ωα-ω._-]+", "_", value)[:90].strip("._") or "archive"


def _write_pricing_text_artifact(
    text_dir: Path,
    eshidis_id: str,
    row_index: int,
    document_name: str,
    full_text: str | None,
) -> Path | None:
    if not full_text:
        return None
    text_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_path_part(document_name)
    path = text_dir / f"{eshidis_id}_{row_index}_{safe_name or 'document'}.txt"
    path.write_text(full_text, encoding="utf-8")
    return path


def search_pricing_rows(db_path: Path, query: str, *, limit: int = 50) -> dict[str, Any]:
    ensure_pricing_tables(db_path)
    normalized_query = canonical_article_code(query)
    text_query = strip_accents(query).casefold()
    connection = connect(db_path)
    try:
        merged_exists = connection.execute(
            "SELECT 1 FROM pricing_budget_rows WHERE source_document = ? LIMIT 1",
            (MERGED_BUDGET_SOURCE_DOCUMENT,),
        ).fetchone()
        source_clause = (
            "pricing_budget_rows.source_document = ?"
            if merged_exists
            else "pricing_budget_rows.source_document != ?"
        )
        rows = connection.execute(
            f"""
            SELECT pricing_budget_rows.eshidis_id, pricing_projects.title, pricing_projects.authority_name,
                   pricing_projects.deadline_at, pricing_budget_rows.article_code,
                   pricing_budget_rows.canonical_article_code, pricing_budget_rows.description,
                   pricing_budget_rows.revision_codes_json, pricing_budget_rows.unit,
                   pricing_budget_rows.quantity, pricing_budget_rows.unit_price,
                   pricing_budget_rows.amount, pricing_budget_rows.source_document,
                   pricing_budget_rows.confidence
            FROM pricing_budget_rows
            LEFT JOIN pricing_projects ON pricing_projects.eshidis_id = pricing_budget_rows.eshidis_id
            WHERE {source_clause}
              AND (
                   pricing_budget_rows.canonical_article_code LIKE ?
                OR pricing_budget_rows.description LIKE ?
                OR pricing_budget_rows.revision_codes_json LIKE ?
              )
            ORDER BY pricing_projects.deadline_at IS NULL, pricing_projects.deadline_at, pricing_budget_rows.eshidis_id
            LIMIT ?
            """,
            (MERGED_BUDGET_SOURCE_DOCUMENT, f"%{normalized_query}%", f"%{query}%", f"%{text_query}%", limit),
        ).fetchall()
    finally:
        connection.close()
    results = []
    for row in rows:
        try:
            revision_codes = json.loads(str(row[7] or "[]"))
        except json.JSONDecodeError:
            revision_codes = []
        results.append(
            {
                "eshidis_id": row[0],
                "title": row[1],
                "authority_name": row[2],
                "deadline_at": row[3],
                "article_code": row[4],
                "canonical_article_code": row[5],
                "description": row[6],
                "revision_codes": revision_codes,
                "unit": row[8],
                "quantity": row[9],
                "unit_price": row[10],
                "amount": row[11],
                "source_document": row[12],
                "confidence": row[13],
            }
        )
    return {
        "ok": True,
        "query": query,
        "summary": {"matches": len(results)},
        "results": results,
    }
