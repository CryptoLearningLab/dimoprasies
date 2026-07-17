from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

from tender_radar.sources.eshidis import EshidisAttachmentListing, EshidisTenderDetails


@dataclass(frozen=True)
class ImportSummary:
    db_path: Path
    tender_id: int
    eshidis_id: str | None
    attachments_imported: int


@dataclass(frozen=True)
class DownloadImportSummary:
    db_path: Path
    attachment_id: int
    original_name: str
    local_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class AttachmentStatus:
    row_index: int
    attachment_id: int
    original_name: str
    local_path: str | None
    size_bytes: int | None
    sha256: str | None


@dataclass(frozen=True)
class DownloadedAttachment:
    attachment_id: int
    tender_id: int
    eshidis_id: str
    original_name: str
    local_path: str
    size_bytes: int | None
    sha256: str | None


@dataclass(frozen=True)
class DocumentUpsertSummary:
    db_path: Path
    document_id: int
    attachment_id: int
    document_type: str
    extraction_status: str


@dataclass(frozen=True)
class SearchableDocument:
    tender_id: int
    eshidis_id: str | None
    tender_title: str
    document_id: int
    attachment_id: int
    document_type: str
    original_name: str
    local_path: str | None
    text_sample: str | None
    text_path: str | None


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(db_path: Path, schema_path: Path | None = None) -> None:
    if schema_path is None:
        schema_path = Path(__file__).with_name("schema.sql")
    connection = connect(db_path)
    try:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _ensure_document_columns(connection)
        connection.commit()
    finally:
        connection.close()


def import_eshidis_resource(
    db_path: Path,
    details: EshidisTenderDetails,
    attachments: EshidisAttachmentListing,
    raw_path: Path | None = None,
) -> ImportSummary:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    title = details.title or details.project_title or f"ESHIDIS {details.eshidis_id or 'UNKNOWN'}"

    connection = connect(db_path)
    try:
        tender_id = _upsert_tender(connection, details, title, now)
        connection.execute(
            """
            INSERT INTO tender_sources (
                tender_id, source_type, source_url, retrieved_at, evidence_summary, raw_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tender_id,
                "eshidis_public_resource",
                details.source_url,
                now,
                json.dumps(
                    {
                        "eshidis_id": details.eshidis_id,
                        "attachment_rows": attachments.row_count,
                        "submission_deadline": details.submission_deadline,
                    },
                    ensure_ascii=False,
                ),
                str(raw_path) if raw_path else None,
            ),
        )
        connection.execute("UPDATE attachments SET is_latest = 0 WHERE tender_id = ?", (tender_id,))
        for filename in attachments.filenames:
            existing_attachment = connection.execute(
                """
                SELECT id
                FROM attachments
                WHERE tender_id = ? AND original_name = ?
                ORDER BY
                    CASE WHEN local_path IS NOT NULL AND sha256 IS NOT NULL THEN 0 ELSE 1 END,
                    id DESC
                LIMIT 1
                """,
                (tender_id, filename),
            ).fetchone()
            if existing_attachment:
                connection.execute(
                    """
                    UPDATE attachments
                    SET source_url = ?, retrieved_at = ?, is_latest = 1
                    WHERE id = ?
                    """,
                    (details.source_url, now, int(existing_attachment[0])),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO attachments (
                        tender_id, original_name, source_url, retrieved_at, is_latest
                    ) VALUES (?, ?, ?, ?, 1)
                    """,
                    (tender_id, filename, details.source_url, now),
                )
        connection.commit()
    finally:
        connection.close()

    return ImportSummary(
        db_path=db_path,
        tender_id=tender_id,
        eshidis_id=details.eshidis_id,
        attachments_imported=len(attachments.filenames),
    )


def import_attachment_download(
    db_path: Path,
    eshidis_id: str,
    original_name: str,
    local_path: str,
    size_bytes: int,
    sha256: str,
) -> DownloadImportSummary:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT attachments.id
            FROM attachments
            JOIN tenders ON tenders.id = attachments.tender_id
            WHERE tenders.eshidis_id = ?
              AND attachments.original_name = ?
              AND attachments.is_latest = 1
            ORDER BY attachments.id DESC
            LIMIT 1
            """,
            (eshidis_id, original_name),
        ).fetchone()
        if row is None:
            raise ValueError(f"No latest attachment found for ESHIDIS {eshidis_id}: {original_name}")
        attachment_id = int(row[0])
        connection.execute(
            """
            UPDATE attachments
            SET local_path = ?, size_bytes = ?, sha256 = ?, retrieved_at = ?
            WHERE id = ?
            """,
            (local_path, size_bytes, sha256, now, attachment_id),
        )
        connection.commit()
    finally:
        connection.close()

    return DownloadImportSummary(
        db_path=db_path,
        attachment_id=attachment_id,
        original_name=original_name,
        local_path=local_path,
        size_bytes=size_bytes,
        sha256=sha256,
    )


def list_latest_attachments(db_path: Path, eshidis_id: str) -> list[AttachmentStatus]:
    initialize(db_path)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT attachments.id, attachments.original_name, attachments.local_path,
                   attachments.size_bytes, attachments.sha256
            FROM attachments
            JOIN tenders ON tenders.id = attachments.tender_id
            WHERE tenders.eshidis_id = ?
              AND attachments.is_latest = 1
            ORDER BY attachments.id
            """,
            (eshidis_id,),
        ).fetchall()
    finally:
        connection.close()
    return [
        AttachmentStatus(
            row_index=index,
            attachment_id=int(row[0]),
            original_name=str(row[1]),
            local_path=str(row[2]) if row[2] is not None else None,
            size_bytes=int(row[3]) if row[3] is not None else None,
            sha256=str(row[4]) if row[4] is not None else None,
        )
        for index, row in enumerate(rows)
    ]


def list_downloaded_attachments(db_path: Path, eshidis_id: str | None = None) -> list[DownloadedAttachment]:
    initialize(db_path)
    where = "attachments.is_latest = 1 AND attachments.local_path IS NOT NULL"
    params: tuple[str, ...] = ()
    if eshidis_id:
        where += " AND tenders.eshidis_id = ?"
        params = (eshidis_id,)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT attachments.id, attachments.tender_id, tenders.eshidis_id,
                   attachments.original_name, attachments.local_path,
                   attachments.size_bytes, attachments.sha256
            FROM attachments
            JOIN tenders ON tenders.id = attachments.tender_id
            WHERE {where}
            ORDER BY tenders.eshidis_id, attachments.id
            """,
            params,
        ).fetchall()
    finally:
        connection.close()
    return [
        DownloadedAttachment(
            attachment_id=int(row[0]),
            tender_id=int(row[1]),
            eshidis_id=str(row[2]),
            original_name=str(row[3]),
            local_path=str(row[4]),
            size_bytes=int(row[5]) if row[5] is not None else None,
            sha256=str(row[6]) if row[6] is not None else None,
        )
        for row in rows
    ]


def upsert_document_analysis(
    db_path: Path,
    attachment_id: int,
    document_type: str,
    classification_confidence: float,
    extraction_status: str,
    page_or_sheet_count: int | None,
    text_sample: str | None,
    text_path: str | None,
    extraction_error: str | None,
) -> DocumentUpsertSummary:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT id FROM documents WHERE attachment_id = ? ORDER BY id DESC LIMIT 1",
            (attachment_id,),
        ).fetchone()
        if row:
            document_id = int(row[0])
            connection.execute(
                """
                UPDATE documents
                SET document_type = ?, classification_confidence = ?,
                    extraction_status = ?, page_or_sheet_count = ?,
                    text_sample = ?, text_path = ?, extraction_error = ?, analyzed_at = ?
                WHERE id = ?
                """,
                (
                    document_type,
                    classification_confidence,
                    extraction_status,
                    page_or_sheet_count,
                    text_sample,
                    text_path,
                    extraction_error,
                    now,
                    document_id,
                ),
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO documents (
                    attachment_id, document_type, classification_confidence,
                    extraction_status, page_or_sheet_count, text_sample, text_path,
                    extraction_error, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    document_type,
                    classification_confidence,
                    extraction_status,
                    page_or_sheet_count,
                    text_sample,
                    text_path,
                    extraction_error,
                    now,
                ),
            )
            document_id = int(cursor.lastrowid)
        connection.commit()
    finally:
        connection.close()
    return DocumentUpsertSummary(
        db_path=db_path,
        document_id=document_id,
        attachment_id=attachment_id,
        document_type=document_type,
        extraction_status=extraction_status,
    )


def list_searchable_documents(
    db_path: Path,
    *,
    eshidis_id: str | None = None,
    document_types: set[str] | None = None,
) -> list[SearchableDocument]:
    initialize(db_path)
    where = "((documents.text_path IS NOT NULL AND documents.text_path != '') OR (documents.text_sample IS NOT NULL AND documents.text_sample != ''))"
    params: list[str] = []
    if eshidis_id:
        where += " AND tenders.eshidis_id = ?"
        params.append(eshidis_id)
    if document_types:
        placeholders = ",".join("?" for _ in document_types)
        where += f" AND documents.document_type IN ({placeholders})"
        params.extend(sorted(document_types))
    connection = connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT tenders.id, tenders.eshidis_id, tenders.title,
                   documents.id, attachments.id, documents.document_type,
                   attachments.original_name, attachments.local_path,
                   documents.text_sample, documents.text_path
            FROM documents
            JOIN attachments ON attachments.id = documents.attachment_id
            JOIN tenders ON tenders.id = attachments.tender_id
            WHERE {where}
            ORDER BY tenders.eshidis_id, documents.id
            """,
            tuple(params),
        ).fetchall()
    finally:
        connection.close()
    return [
        SearchableDocument(
            tender_id=int(row[0]),
            eshidis_id=str(row[1]) if row[1] is not None else None,
            tender_title=str(row[2]),
            document_id=int(row[3]),
            attachment_id=int(row[4]),
            document_type=str(row[5]),
            original_name=str(row[6]),
            local_path=str(row[7]) if row[7] is not None else None,
            text_sample=str(row[8]) if row[8] is not None else None,
            text_path=str(row[9]) if row[9] is not None else None,
        )
        for row in rows
    ]


def create_search_run(db_path: Path, profile_id: str | None, request_path: Path | None) -> int:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO search_runs (profile_id, request_path, started_at, status)
            VALUES (?, ?, ?, 'RUNNING')
            """,
            (profile_id, str(request_path) if request_path else None, now),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def insert_search_hit(
    db_path: Path,
    *,
    search_run_id: int,
    tender_id: int,
    document_id: int,
    match_type: str,
    confidence: float,
    matched_text: str,
    provenance: dict[str, object],
) -> int:
    initialize(db_path)
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO search_hits (
                search_run_id, tender_id, document_id, match_type,
                confidence, matched_text, provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                search_run_id,
                tender_id,
                document_id,
                match_type,
                confidence,
                matched_text,
                json.dumps(provenance, ensure_ascii=False),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def finish_search_run(db_path: Path, search_run_id: int, status: str, summary: dict[str, object]) -> None:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            UPDATE search_runs
            SET finished_at = ?, status = ?, summary_json = ?
            WHERE id = ?
            """,
            (now, status, json.dumps(summary, ensure_ascii=False), search_run_id),
        )
        connection.commit()
    finally:
        connection.close()


def _ensure_document_columns(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
    additions = {
        "text_sample": "TEXT",
        "text_path": "TEXT",
        "extraction_error": "TEXT",
        "analyzed_at": "TEXT",
    }
    for column, column_type in additions.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE documents ADD COLUMN {column} {column_type}")


def _upsert_tender(
    connection: sqlite3.Connection,
    details: EshidisTenderDetails,
    title: str,
    now: str,
) -> int:
    budget_with_vat = _parse_greek_number(details.budget_with_vat)
    existing = None
    if details.eshidis_id:
        existing = connection.execute(
            "SELECT id FROM tenders WHERE eshidis_id = ?",
            (details.eshidis_id,),
        ).fetchone()
    if existing:
        tender_id = int(existing[0])
        connection.execute(
            """
            UPDATE tenders
            SET cpv_code = ?, title = ?, authority_name = ?, region = ?,
                published_at = ?, current_deadline_at = ?, budget_with_vat = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                details.cpv,
                title,
                details.contracting_authority,
                details.location,
                details.publication_date,
                details.submission_deadline,
                budget_with_vat,
                now,
                tender_id,
            ),
        )
        return tender_id

    cursor = connection.execute(
        """
        INSERT INTO tenders (
            eshidis_id, cpv_code, title, authority_name, region, status,
            status_confidence, published_at, current_deadline_at,
            budget_with_vat, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'UNKNOWN', 0.0, ?, ?, ?, ?, ?)
        """,
        (
            details.eshidis_id,
            details.cpv,
            title,
            details.contracting_authority,
            details.location,
            details.publication_date,
            details.submission_deadline,
            budget_with_vat,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _parse_greek_number(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.replace(".", "").replace(",", ".")
    digits = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
    if not digits:
        return None
    return float(digits)
