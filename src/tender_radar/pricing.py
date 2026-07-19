from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import re
import sqlite3
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from tender_radar.db import connect, initialize
from tender_radar.documents import extract_text_with_metadata


ARTICLE_RE = re.compile(
    r"^\s*(?P<row>\d{1,3})\s+(?P<article>[A-ZΑ-ΩΒB][A-ZΑ-ΩΒB0-9./-]*\d+(?:[.-]\d+)*)\s+(?P<rest>.*)$"
)
NUMERIC_RE = re.compile(r"^\d+(?:[.,]\d{2,3})*$")
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
    "kg",
    "tn",
    "τεμ",
    "τεμαχ",
    "στρ",
    "h",
    "km",
    "lt",
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
    text = value.strip().replace(" ", "")
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
                return completed.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    extraction = extract_text_with_metadata(path, max_chars=500_000)
    return extraction.full_text or extraction.text_sample or ""


def parse_budget_rows_from_text(text: str) -> list[PricingBudgetRow]:
    blocks = _budget_row_blocks(text)
    return [row for block in blocks if (row := _parse_budget_block(block)) is not None]


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


def search_pricing_rows(db_path: Path, query: str, *, limit: int = 50) -> dict[str, Any]:
    ensure_pricing_tables(db_path)
    normalized_query = canonical_article_code(query)
    text_query = strip_accents(query).casefold()
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT pricing_budget_rows.eshidis_id, pricing_projects.title, pricing_projects.authority_name,
                   pricing_projects.deadline_at, pricing_budget_rows.article_code,
                   pricing_budget_rows.canonical_article_code, pricing_budget_rows.description,
                   pricing_budget_rows.revision_codes_json, pricing_budget_rows.unit,
                   pricing_budget_rows.quantity, pricing_budget_rows.unit_price,
                   pricing_budget_rows.amount, pricing_budget_rows.source_document,
                   pricing_budget_rows.confidence
            FROM pricing_budget_rows
            LEFT JOIN pricing_projects ON pricing_projects.eshidis_id = pricing_budget_rows.eshidis_id
            WHERE pricing_budget_rows.canonical_article_code LIKE ?
               OR pricing_budget_rows.description LIKE ?
               OR pricing_budget_rows.revision_codes_json LIKE ?
            ORDER BY pricing_projects.deadline_at IS NULL, pricing_projects.deadline_at, pricing_budget_rows.eshidis_id
            LIMIT ?
            """,
            (f"%{normalized_query}%", f"%{query}%", f"%{text_query}%", limit),
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
