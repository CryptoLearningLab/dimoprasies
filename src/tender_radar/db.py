from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import sqlite3
from pathlib import Path
import unicodedata

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


@dataclass(frozen=True)
class SourceState:
    source_id: str
    source_family: str | None
    source_url: str | None
    fingerprint: str | None
    last_checked_at: str | None
    last_changed_at: str | None
    last_status: str
    last_error: str | None
    metadata: dict[str, object]


@dataclass(frozen=True)
class SourceDocument:
    row_key: str
    document_url: str
    source_url: str | None
    local_path: str | None
    size_bytes: int | None
    sha256: str | None
    fetched_at: str | None
    fetch_error: str | None
    source_signature: str | None
    metadata: dict[str, object]


@dataclass(frozen=True)
class VerifiedTenderLink:
    source_row_key: str
    source_identifier: str | None
    source_label: str | None
    source_url: str | None
    target_eshidis_id: str
    target_tender_id: int | None
    verification_status: str
    verified_at: str
    source_signature: str | None
    evidence: dict[str, object]


@dataclass(frozen=True)
class AdminUser:
    id: int
    email: str
    role: str
    password_hash: str | None
    enabled: bool
    invited_at: str | None
    accepted_at: str | None
    password_set_at: str | None
    last_login_at: str | None


@dataclass(frozen=True)
class AdminInvite:
    token_hash: str
    email: str
    role: str
    created_by: str | None
    created_at: str
    expires_at: str
    used_at: str | None


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
        _ensure_runtime_state_tables(connection)
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
            normalized_original_name = normalize_attachment_name(original_name)
            rows = connection.execute(
                """
                SELECT attachments.id, attachments.original_name
                FROM attachments
                JOIN tenders ON tenders.id = attachments.tender_id
                WHERE tenders.eshidis_id = ?
                  AND attachments.is_latest = 1
                ORDER BY attachments.id DESC
                """,
                (eshidis_id,),
            ).fetchall()
            matches = [item for item in rows if normalize_attachment_name(str(item[1] or "")) == normalized_original_name]
            if len(matches) == 1:
                row = matches[0]
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


def normalize_attachment_name(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return re.sub(r"\s+", " ", normalized).strip()


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
    ocr_status: str | None = None,
    ocr_error: str | None = None,
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
                    text_sample = ?, text_path = ?, extraction_error = ?,
                    ocr_status = ?, ocr_error = ?, analyzed_at = ?
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
                    ocr_status,
                    ocr_error,
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
                    extraction_error, ocr_status, ocr_error, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ocr_status,
                    ocr_error,
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


def upsert_admin_user(
    db_path: Path,
    *,
    email: str,
    role: str,
    password_hash: str | None = None,
    enabled: bool = True,
    mark_accepted: bool = False,
) -> AdminUser:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    normalized_email = email.strip().lower()
    connection = connect(db_path)
    try:
        row = connection.execute("SELECT email FROM admin_users WHERE email = ?", (normalized_email,)).fetchone()
        if row:
            connection.execute(
                """
                UPDATE admin_users
                SET role = ?, password_hash = COALESCE(?, password_hash),
                    enabled = ?, accepted_at = CASE WHEN ? THEN COALESCE(accepted_at, ?) ELSE accepted_at END,
                    password_set_at = CASE WHEN ? IS NOT NULL THEN ? ELSE password_set_at END
                WHERE email = ?
                """,
                (
                    role,
                    password_hash,
                    1 if enabled else 0,
                    1 if mark_accepted else 0,
                    now,
                    password_hash,
                    now,
                    normalized_email,
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO admin_users (
                    email, role, password_hash, enabled, invited_at, accepted_at,
                    password_set_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    normalized_email,
                    role,
                    password_hash,
                    1 if enabled else 0,
                    now,
                    now if mark_accepted else None,
                    now if password_hash else None,
                ),
            )
        connection.commit()
    finally:
        connection.close()
    user = get_admin_user(db_path, normalized_email)
    if not user:
        raise RuntimeError("Admin user was not persisted.")
    return user


def get_admin_user(db_path: Path, email: str) -> AdminUser | None:
    initialize(db_path)
    normalized_email = email.strip().lower()
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT rowid, email, role, password_hash, enabled, invited_at, accepted_at,
                   password_set_at, last_login_at
            FROM admin_users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
    finally:
        connection.close()
    return _admin_user_from_row(row) if row else None


def list_admin_users(db_path: Path) -> list[AdminUser]:
    initialize(db_path)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT rowid, email, role, password_hash, enabled, invited_at, accepted_at,
                   password_set_at, last_login_at
            FROM admin_users
            ORDER BY role, email
            """
        ).fetchall()
    finally:
        connection.close()
    return [_admin_user_from_row(row) for row in rows]


def create_admin_invite(
    db_path: Path,
    *,
    token_hash: str,
    email: str,
    role: str,
    expires_at: str,
    created_by: str | None = None,
) -> AdminInvite:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    normalized_email = email.strip().lower()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO admin_invites (
                token_hash, email, role, created_by, created_at, expires_at, used_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (token_hash, normalized_email, role, created_by, now, expires_at),
        )
        connection.commit()
    finally:
        connection.close()
    return AdminInvite(token_hash, normalized_email, role, created_by, now, expires_at, None)


def get_admin_invite(db_path: Path, token_hash: str) -> AdminInvite | None:
    initialize(db_path)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT token_hash, email, role, created_by, created_at, expires_at, used_at
            FROM admin_invites
            WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
    finally:
        connection.close()
    return _admin_invite_from_row(row) if row else None


def mark_admin_invite_used(db_path: Path, token_hash: str) -> None:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute("UPDATE admin_invites SET used_at = ? WHERE token_hash = ?", (now, token_hash))
        connection.commit()
    finally:
        connection.close()


def record_admin_user_login(db_path: Path, email: str) -> None:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute("UPDATE admin_users SET last_login_at = ? WHERE email = ?", (now, email.strip().lower()))
        connection.commit()
    finally:
        connection.close()


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


def upsert_source_state(
    db_path: Path,
    *,
    source_id: str,
    source_family: str | None = None,
    source_url: str | None = None,
    fingerprint: str | None = None,
    checked_at: str | None = None,
    changed_at: str | None = None,
    status: str = "UNKNOWN",
    error: str | None = None,
    metadata: dict[str, object] | None = None,
) -> SourceState:
    initialize(db_path)
    if not source_id.strip():
        raise ValueError("source_id is required")
    now = checked_at or datetime.now(timezone.utc).isoformat()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    connection = connect(db_path)
    try:
        current = connection.execute(
            "SELECT fingerprint, last_changed_at FROM source_state WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        previous_fingerprint = str(current[0]) if current and current[0] is not None else None
        previous_changed_at = str(current[1]) if current and current[1] is not None else None
        next_changed_at = changed_at
        if next_changed_at is None:
            next_changed_at = now if fingerprint is not None and fingerprint != previous_fingerprint else previous_changed_at
        connection.execute(
            """
            INSERT INTO source_state (
                source_id, source_family, source_url, fingerprint,
                last_checked_at, last_changed_at, last_status, last_error,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_family = excluded.source_family,
                source_url = excluded.source_url,
                fingerprint = excluded.fingerprint,
                last_checked_at = excluded.last_checked_at,
                last_changed_at = excluded.last_changed_at,
                last_status = excluded.last_status,
                last_error = excluded.last_error,
                metadata_json = excluded.metadata_json
            """,
            (
                source_id,
                source_family,
                source_url,
                fingerprint,
                now,
                next_changed_at,
                status,
                error,
                metadata_json,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT source_id, source_family, source_url, fingerprint,
                   last_checked_at, last_changed_at, last_status, last_error,
                   metadata_json
            FROM source_state
            WHERE source_id = ?
            """,
            (source_id,),
        ).fetchone()
    finally:
        connection.close()
    return _source_state_from_row(row)


def get_source_state(db_path: Path, source_id: str) -> SourceState | None:
    initialize(db_path)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT source_id, source_family, source_url, fingerprint,
                   last_checked_at, last_changed_at, last_status, last_error,
                   metadata_json
            FROM source_state
            WHERE source_id = ?
            """,
            (source_id,),
        ).fetchone()
    finally:
        connection.close()
    return _source_state_from_row(row) if row else None


def list_source_states(db_path: Path) -> list[SourceState]:
    initialize(db_path)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT source_id, source_family, source_url, fingerprint,
                   last_checked_at, last_changed_at, last_status, last_error,
                   metadata_json
            FROM source_state
            ORDER BY source_id
            """
        ).fetchall()
    finally:
        connection.close()
    return [_source_state_from_row(row) for row in rows]


def record_source_run(
    db_path: Path,
    *,
    run_id: str,
    source_id: str,
    started_at: str,
    finished_at: str | None,
    status: str,
    fingerprint: str | None = None,
    changed: bool = False,
    item_count: int | None = None,
    error: str | None = None,
    metadata: dict[str, object] | None = None,
) -> int:
    initialize(db_path)
    if get_source_state(db_path, source_id) is None:
        upsert_source_state(db_path, source_id=source_id, status="UNKNOWN")
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO source_runs (
                run_id, source_id, started_at, finished_at, status, fingerprint,
                changed, item_count, error, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_id,
                started_at,
                finished_at,
                status,
                fingerprint,
                1 if changed else 0,
                item_count,
                error,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def dismiss_tender(
    db_path: Path,
    *,
    row_key: str,
    display_id: str | None = None,
    source_label: str | None = None,
    title: str | None = None,
    reason: str | None = None,
    ignored_at: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    initialize(db_path)
    if not row_key.strip():
        raise ValueError("row_key is required")
    ignored_at = ignored_at or datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO tender_dismissals (
                row_key, display_id, source_label, title, reason, ignored_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(row_key) DO UPDATE SET
                display_id = COALESCE(excluded.display_id, tender_dismissals.display_id),
                source_label = COALESCE(excluded.source_label, tender_dismissals.source_label),
                title = COALESCE(excluded.title, tender_dismissals.title),
                reason = COALESCE(excluded.reason, tender_dismissals.reason),
                ignored_at = tender_dismissals.ignored_at,
                metadata_json = excluded.metadata_json
            """,
            (
                row_key,
                display_id,
                source_label,
                title,
                reason,
                ignored_at,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def ignored_tender_keys(db_path: Path) -> set[str]:
    initialize(db_path)
    connection = connect(db_path)
    try:
        rows = connection.execute("SELECT row_key FROM tender_dismissals").fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def list_tender_dismissals(db_path: Path) -> list[dict[str, object]]:
    initialize(db_path)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT row_key, display_id, source_label, title, reason, ignored_at, metadata_json
            FROM tender_dismissals
            ORDER BY ignored_at DESC
            """
        ).fetchall()
    finally:
        connection.close()
    items: list[dict[str, object]] = []
    for row in rows:
        try:
            metadata = json.loads(row[6] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        items.append(
            {
                "row_key": row[0],
                "display_id": row[1],
                "source_label": row[2],
                "title": row[3],
                "reason": row[4],
                "ignored_at": row[5],
                "metadata": metadata,
            }
        )
    return items


def remove_tender_dismissal(db_path: Path, *, row_key: str) -> None:
    initialize(db_path)
    connection = connect(db_path)
    try:
        connection.execute("DELETE FROM tender_dismissals WHERE row_key = ?", (row_key,))
        connection.commit()
    finally:
        connection.close()


def upsert_triage_override(
    db_path: Path,
    *,
    row_key: str,
    action: str,
    reason: str | None = None,
    created_at: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    initialize(db_path)
    if not row_key.strip():
        raise ValueError("row_key is required")
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO triage_overrides (
                row_key, action, reason, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(row_key) DO UPDATE SET
                action = excluded.action,
                reason = excluded.reason,
                metadata_json = excluded.metadata_json
            """,
            (row_key, action, reason, created_at, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        connection.commit()
    finally:
        connection.close()


def triage_overrides_by_key(db_path: Path) -> dict[str, dict[str, object]]:
    initialize(db_path)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT row_key, action, reason, created_at, metadata_json
            FROM triage_overrides
            """
        ).fetchall()
    finally:
        connection.close()
    items: dict[str, dict[str, object]] = {}
    for row in rows:
        try:
            metadata = json.loads(row[4] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        items[str(row[0])] = {
            "row_key": row[0],
            "action": row[1],
            "reason": row[2],
            "created_at": row[3],
            "metadata": metadata,
        }
    return items


def record_notification_sent(
    db_path: Path,
    *,
    row_key: str,
    channel: str,
    recipient: str,
    subject: str | None = None,
    sent_at: str | None = None,
    metadata: dict[str, object] | None = None,
) -> int:
    initialize(db_path)
    if not row_key.strip():
        raise ValueError("row_key is required")
    sent_at = sent_at or datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO notification_log (
                row_key, channel, recipient, sent_at, subject, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(row_key, channel, recipient) DO UPDATE SET
                sent_at = excluded.sent_at,
                subject = excluded.subject,
                metadata_json = excluded.metadata_json
            """,
            (
                row_key,
                channel,
                recipient,
                sent_at,
                subject,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = connection.execute(
            """
            SELECT id FROM notification_log
            WHERE row_key = ? AND channel = ? AND recipient = ?
            """,
            (row_key, channel, recipient),
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def notification_already_sent(db_path: Path, *, row_key: str, channel: str, recipient: str) -> bool:
    initialize(db_path)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT 1 FROM notification_log
            WHERE row_key = ? AND channel = ? AND recipient = ?
            """,
            (row_key, channel, recipient),
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def upsert_source_document(
    db_path: Path,
    *,
    row_key: str,
    document_url: str,
    source_url: str | None = None,
    local_path: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    fetched_at: str | None = None,
    fetch_error: str | None = None,
    source_signature: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    initialize(db_path)
    if not row_key.strip():
        raise ValueError("row_key is required")
    if not document_url.strip():
        raise ValueError("document_url is required")
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO source_documents (
                row_key, document_url, source_url, local_path, size_bytes,
                sha256, fetched_at, fetch_error, source_signature,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(row_key, document_url) DO UPDATE SET
                source_url = excluded.source_url,
                local_path = excluded.local_path,
                size_bytes = excluded.size_bytes,
                sha256 = excluded.sha256,
                fetched_at = excluded.fetched_at,
                fetch_error = excluded.fetch_error,
                source_signature = excluded.source_signature,
                metadata_json = excluded.metadata_json
            """,
            (
                row_key,
                document_url,
                source_url,
                local_path,
                size_bytes,
                sha256,
                fetched_at,
                fetch_error,
                source_signature,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def get_source_document(db_path: Path, *, row_key: str, document_url: str) -> SourceDocument | None:
    initialize(db_path)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT row_key, document_url, source_url, local_path, size_bytes,
                   sha256, fetched_at, fetch_error, source_signature,
                   metadata_json
            FROM source_documents
            WHERE row_key = ? AND document_url = ?
            """,
            (row_key, document_url),
        ).fetchone()
    finally:
        connection.close()
    return _source_document_from_row(row) if row else None


def list_source_documents(db_path: Path, *, row_key: str | None = None) -> list[SourceDocument]:
    initialize(db_path)
    where = ""
    params: tuple[str, ...] = ()
    if row_key:
        where = "WHERE row_key = ?"
        params = (row_key,)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT row_key, document_url, source_url, local_path, size_bytes,
                   sha256, fetched_at, fetch_error, source_signature,
                   metadata_json
            FROM source_documents
            {where}
            ORDER BY row_key, document_url
            """,
            params,
        ).fetchall()
    finally:
        connection.close()
    return [_source_document_from_row(row) for row in rows]


def upsert_verified_tender_link(
    db_path: Path,
    *,
    source_row_key: str,
    target_eshidis_id: str,
    source_identifier: str | None = None,
    source_label: str | None = None,
    source_url: str | None = None,
    target_tender_id: int | None = None,
    verification_status: str = "VERIFIED_ESHIDIS_RESOURCE",
    verified_at: str | None = None,
    source_signature: str | None = None,
    evidence: dict[str, object] | None = None,
) -> None:
    initialize(db_path)
    if not source_row_key.strip():
        raise ValueError("source_row_key is required")
    if not str(target_eshidis_id).strip().isdigit():
        raise ValueError("target_eshidis_id must be numeric")
    verified_at = verified_at or datetime.now(timezone.utc).isoformat()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO verified_tender_links (
                source_row_key, source_identifier, source_label, source_url,
                target_eshidis_id, target_tender_id, verification_status,
                verified_at, source_signature, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_row_key, target_eshidis_id) DO UPDATE SET
                source_identifier = excluded.source_identifier,
                source_label = excluded.source_label,
                source_url = excluded.source_url,
                target_tender_id = COALESCE(excluded.target_tender_id, verified_tender_links.target_tender_id),
                verification_status = excluded.verification_status,
                verified_at = excluded.verified_at,
                source_signature = excluded.source_signature,
                evidence_json = excluded.evidence_json
            """,
            (
                source_row_key,
                source_identifier,
                source_label,
                source_url,
                str(target_eshidis_id),
                target_tender_id,
                verification_status,
                verified_at,
                source_signature,
                json.dumps(evidence or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def delete_stale_verified_tender_links(
    db_path: Path,
    *,
    source_row_key: str,
    keep_target_eshidis_ids: set[str],
) -> int:
    initialize(db_path)
    keep_ids = {str(value).strip() for value in keep_target_eshidis_ids if str(value).strip().isdigit()}
    connection = connect(db_path)
    try:
        if keep_ids:
            placeholders = ",".join("?" for _ in keep_ids)
            cursor = connection.execute(
                f"""
                DELETE FROM verified_tender_links
                WHERE source_row_key = ?
                  AND target_eshidis_id NOT IN ({placeholders})
                """,
                (source_row_key, *sorted(keep_ids)),
            )
        else:
            cursor = connection.execute(
                "DELETE FROM verified_tender_links WHERE source_row_key = ?",
                (source_row_key,),
            )
        connection.commit()
        return int(cursor.rowcount or 0)
    finally:
        connection.close()


def list_verified_tender_links(
    db_path: Path,
    *,
    source_row_key: str | None = None,
    target_eshidis_id: str | None = None,
) -> list[VerifiedTenderLink]:
    initialize(db_path)
    where_parts: list[str] = []
    params: list[str] = []
    if source_row_key:
        where_parts.append("source_row_key = ?")
        params.append(source_row_key)
    if target_eshidis_id:
        where_parts.append("target_eshidis_id = ?")
        params.append(str(target_eshidis_id))
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT source_row_key, source_identifier, source_label, source_url,
                   target_eshidis_id, target_tender_id, verification_status,
                   verified_at, source_signature, evidence_json
            FROM verified_tender_links
            {where}
            ORDER BY source_row_key, target_eshidis_id
            """,
            tuple(params),
        ).fetchall()
    finally:
        connection.close()
    return [_verified_tender_link_from_row(row) for row in rows]


def _ensure_document_columns(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
    additions = {
        "text_sample": "TEXT",
        "text_path": "TEXT",
        "extraction_error": "TEXT",
        "ocr_status": "TEXT",
        "ocr_error": "TEXT",
        "analyzed_at": "TEXT",
    }
    for column, column_type in additions.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE documents ADD COLUMN {column} {column_type}")


def _ensure_runtime_state_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_state (
            source_id TEXT PRIMARY KEY,
            source_family TEXT,
            source_url TEXT,
            fingerprint TEXT,
            last_checked_at TEXT,
            last_changed_at TEXT,
            last_status TEXT NOT NULL DEFAULT 'UNKNOWN',
            last_error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS source_runs (
            id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            fingerprint TEXT,
            changed INTEGER NOT NULL DEFAULT 0,
            item_count INTEGER,
            error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(source_id) REFERENCES source_state(source_id)
        );

        CREATE INDEX IF NOT EXISTS idx_source_runs_source_started
        ON source_runs(source_id, started_at);

        CREATE TABLE IF NOT EXISTS tender_dismissals (
            row_key TEXT PRIMARY KEY,
            display_id TEXT,
            source_label TEXT,
            title TEXT,
            reason TEXT,
            ignored_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY,
            row_key TEXT NOT NULL,
            channel TEXT NOT NULL,
            recipient TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            subject TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(row_key, channel, recipient)
        );

        CREATE TABLE IF NOT EXISTS triage_overrides (
            row_key TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS admin_users (
            email TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            password_hash TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            invited_at TEXT,
            accepted_at TEXT,
            password_set_at TEXT,
            last_login_at TEXT
        );

        CREATE TABLE IF NOT EXISTS admin_invites (
            token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        );

        CREATE TABLE IF NOT EXISTS source_documents (
            id INTEGER PRIMARY KEY,
            row_key TEXT NOT NULL,
            document_url TEXT NOT NULL,
            source_url TEXT,
            local_path TEXT,
            size_bytes INTEGER,
            sha256 TEXT,
            fetched_at TEXT,
            fetch_error TEXT,
            source_signature TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(row_key, document_url)
        );

        CREATE INDEX IF NOT EXISTS idx_source_documents_row_key
        ON source_documents(row_key);

        CREATE TABLE IF NOT EXISTS verified_tender_links (
            id INTEGER PRIMARY KEY,
            source_row_key TEXT NOT NULL,
            source_identifier TEXT,
            source_label TEXT,
            source_url TEXT,
            target_eshidis_id TEXT NOT NULL,
            target_tender_id INTEGER REFERENCES tenders(id),
            verification_status TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            source_signature TEXT,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(source_row_key, target_eshidis_id)
        );

        CREATE INDEX IF NOT EXISTS idx_verified_tender_links_source
        ON verified_tender_links(source_row_key);

        CREATE INDEX IF NOT EXISTS idx_verified_tender_links_target
        ON verified_tender_links(target_eshidis_id);
        """
    )


def _source_state_from_row(row: sqlite3.Row | tuple[object, ...]) -> SourceState:
    metadata: dict[str, object] = {}
    try:
        loaded = json.loads(str(row[8] or "{}"))
        if isinstance(loaded, dict):
            metadata = loaded
    except json.JSONDecodeError:
        metadata = {}
    return SourceState(
        source_id=str(row[0]),
        source_family=str(row[1]) if row[1] is not None else None,
        source_url=str(row[2]) if row[2] is not None else None,
        fingerprint=str(row[3]) if row[3] is not None else None,
        last_checked_at=str(row[4]) if row[4] is not None else None,
        last_changed_at=str(row[5]) if row[5] is not None else None,
        last_status=str(row[6]),
        last_error=str(row[7]) if row[7] is not None else None,
        metadata=metadata,
    )


def _source_document_from_row(row: sqlite3.Row | tuple[object, ...]) -> SourceDocument:
    metadata: dict[str, object] = {}
    try:
        metadata = json.loads(str(row[9] or "{}"))
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return SourceDocument(
        row_key=str(row[0]),
        document_url=str(row[1]),
        source_url=str(row[2]) if row[2] is not None else None,
        local_path=str(row[3]) if row[3] is not None else None,
        size_bytes=int(row[4]) if row[4] is not None else None,
        sha256=str(row[5]) if row[5] is not None else None,
        fetched_at=str(row[6]) if row[6] is not None else None,
        fetch_error=str(row[7]) if row[7] is not None else None,
        source_signature=str(row[8]) if row[8] is not None else None,
        metadata=metadata,
    )


def _verified_tender_link_from_row(row: sqlite3.Row | tuple[object, ...]) -> VerifiedTenderLink:
    evidence: dict[str, object] = {}
    try:
        loaded = json.loads(str(row[9] or "{}"))
        if isinstance(loaded, dict):
            evidence = loaded
    except (TypeError, json.JSONDecodeError):
        evidence = {}
    return VerifiedTenderLink(
        source_row_key=str(row[0]),
        source_identifier=str(row[1]) if row[1] is not None else None,
        source_label=str(row[2]) if row[2] is not None else None,
        source_url=str(row[3]) if row[3] is not None else None,
        target_eshidis_id=str(row[4]),
        target_tender_id=int(row[5]) if row[5] is not None else None,
        verification_status=str(row[6]),
        verified_at=str(row[7]),
        source_signature=str(row[8]) if row[8] is not None else None,
        evidence=evidence,
    )


def _admin_user_from_row(row: sqlite3.Row | tuple[object, ...]) -> AdminUser:
    return AdminUser(
        id=int(row[0]),
        email=str(row[1]),
        role=str(row[2]),
        password_hash=str(row[3]) if row[3] is not None else None,
        enabled=bool(row[4]),
        invited_at=str(row[5]) if row[5] is not None else None,
        accepted_at=str(row[6]) if row[6] is not None else None,
        password_set_at=str(row[7]) if row[7] is not None else None,
        last_login_at=str(row[8]) if row[8] is not None else None,
    )


def _admin_invite_from_row(row: sqlite3.Row | tuple[object, ...]) -> AdminInvite:
    return AdminInvite(
        token_hash=str(row[0]),
        email=str(row[1]),
        role=str(row[2]),
        created_by=str(row[3]) if row[3] is not None else None,
        created_at=str(row[4]),
        expires_at=str(row[5]),
        used_at=str(row[6]) if row[6] is not None else None,
    )


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
