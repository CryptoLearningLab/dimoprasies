from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

from tender_radar.db import connect, initialize


ATHENS = ZoneInfo("Europe/Athens")

STATUS_ACT_TYPES = {
    "extension",
    "amendment",
    "correction",
    "cancellation",
    "participation_table",
    "evaluation_minutes",
    "provisional_award",
    "final_award",
    "contract",
}

STATUS_FILENAME_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("extension", ("παραταση", "παράταση", "μεταθεση", "μετάθεση")),
    ("amendment", ("τροποποιηση", "τροποποίηση")),
    ("correction", ("ορθη επαναληψη", "ορθή επανάληψη", "διορθωση", "διόρθωση")),
    ("cancellation", ("ματαίωση", "ματαιωση", "ακύρωση", "ακυρωση")),
    ("participation_table", ("πινακας συμμετεχοντων", "πίνακας συμμετεχόντων")),
    ("evaluation_minutes", ("πρακτικο", "πρακτικό", "αποσφραγιση", "αποσφράγιση", "αξιολογηση", "αξιολόγηση")),
    ("provisional_award", ("προσωρινος αναδοχος", "προσωρινός ανάδοχος", "μειοδοτης", "μειοδότης")),
    ("final_award", ("κατακυρωση", "κατακύρωση")),
    ("contract", ("συμβαση", "σύμβαση")),
)


@dataclass(frozen=True)
class StatusSignal:
    signal_type: str
    source: str
    document_id: int | None
    attachment_id: int | None
    original_name: str | None
    evidence: str
    decisive: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StatusVerification:
    eshidis_id: str
    tender_id: int
    tender_title: str
    current_db_status: str
    current_db_status_confidence: float
    official_deadline: str | None
    checked_at: str
    recommended_status: str
    status_confidence: float
    verified_active: bool
    rationale: tuple[str, ...]
    signals: tuple[StatusSignal, ...]
    documents_checked: int
    latest_attachments_checked: int

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["signals"] = [signal.to_dict() for signal in self.signals]
        data["rationale"] = list(self.rationale)
        return data


def verify_tender_status(db_path: Path, eshidis_id: str, *, now: datetime | None = None) -> StatusVerification:
    initialize(db_path)
    checked_at = (now or datetime.now(ATHENS)).astimezone(ATHENS)
    connection = connect(db_path)
    try:
        tender = _fetch_tender(connection, eshidis_id)
        signals = tuple(_status_signals(connection, tender["id"]))
        documents_checked = _count_documents(connection, tender["id"])
        latest_attachments_checked = _count_latest_attachments(connection, tender["id"])
    finally:
        connection.close()

    deadline_text = tender["current_deadline_at"]
    deadline = parse_athens_deadline(deadline_text)
    decisive = [signal for signal in signals if signal.decisive]
    rationale: list[str] = []
    recommended_status = "UNKNOWN"
    confidence = 0.0

    if decisive:
        recommended_status = "UNKNOWN"
        confidence = 0.35
        rationale.append("Potential status-changing official act filenames were found; manual review is required.")
    elif deadline and deadline > checked_at:
        recommended_status = "POSSIBLY_ACTIVE"
        confidence = 0.65
        rationale.append("Official ESHIDIS detail deadline is in the future.")
        rationale.append("No decisive status-changing attachment filenames were found in the latest listed attachments.")
        rationale.append("No separate official status-transition endpoint has been implemented, so this is not VERIFIED_ACTIVE.")
    elif deadline and deadline <= checked_at:
        recommended_status = "SUBMISSION_EXPIRED"
        confidence = 0.7
        rationale.append("Official ESHIDIS detail deadline is not in the future at verification time.")
    else:
        rationale.append("No parseable official deadline was available.")

    return StatusVerification(
        eshidis_id=eshidis_id,
        tender_id=int(tender["id"]),
        tender_title=str(tender["title"]),
        current_db_status=str(tender["status"]),
        current_db_status_confidence=float(tender["status_confidence"]),
        official_deadline=deadline_text,
        checked_at=checked_at.isoformat(),
        recommended_status=recommended_status,
        status_confidence=confidence,
        verified_active=False,
        rationale=tuple(rationale),
        signals=signals,
        documents_checked=documents_checked,
        latest_attachments_checked=latest_attachments_checked,
    )


def parse_athens_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=ATHENS)
        except ValueError:
            continue
    return None


def render_status_markdown(result: StatusVerification) -> str:
    lines = [
        "# Status Verification",
        "",
        f"- ESHIDIS id: `{result.eshidis_id}`",
        f"- Tender: {result.tender_title}",
        f"- Checked at: `{result.checked_at}`",
        f"- Official deadline: `{result.official_deadline or 'UNKNOWN'}`",
        f"- Current DB status: `{result.current_db_status}` ({result.current_db_status_confidence:g})",
        f"- Recommended status: `{result.recommended_status}` ({result.status_confidence:g})",
        f"- VERIFIED_ACTIVE: `{result.verified_active}`",
        f"- Latest attachments checked: `{result.latest_attachments_checked}`",
        f"- Documents checked: `{result.documents_checked}`",
        "",
        "## Rationale",
        "",
    ]
    lines.extend(f"- {item}" for item in result.rationale)
    lines.extend(["", "## Status Signals", ""])
    if not result.signals:
        lines.append("_No status-changing attachment filenames were found._")
    else:
        lines.append("| Type | Decisive | Source | Document | Evidence |")
        lines.append("| --- | --- | --- | --- | --- |")
        for signal in result.signals:
            lines.append(
                "| {kind} | `{decisive}` | {source} | {doc} | {evidence} |".format(
                    kind=signal.signal_type,
                    decisive=signal.decisive,
                    source=signal.source,
                    doc=signal.original_name or "",
                    evidence=_markdown_cell(signal.evidence),
                )
            )
    return "\n".join(lines) + "\n"


def write_status_reports(result: StatusVerification, report_path: Path, markdown_path: Path | None = None) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_status_markdown(result), encoding="utf-8")


def _fetch_tender(connection: sqlite3.Connection, eshidis_id: str) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """
        SELECT id, eshidis_id, title, status, status_confidence, current_deadline_at
        FROM tenders
        WHERE eshidis_id = ?
        """,
        (eshidis_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No tender found for ESHIDIS {eshidis_id}.")
    return row


def _status_signals(connection: sqlite3.Connection, tender_id: int) -> list[StatusSignal]:
    rows = connection.execute(
        """
        SELECT documents.id, documents.document_type, documents.text_sample,
               attachments.id, attachments.original_name
        FROM attachments
        LEFT JOIN documents ON attachments.id = documents.attachment_id
        WHERE attachments.tender_id = ?
          AND attachments.is_latest = 1
        ORDER BY attachments.id
        """,
        (tender_id,),
    ).fetchall()
    signals: list[StatusSignal] = []
    for document_id, document_type, text_sample, attachment_id, original_name in rows:
        doc_type = str(document_type or "")
        if doc_type in STATUS_ACT_TYPES:
            signals.append(
                StatusSignal(
                    signal_type=doc_type,
                    source="document_type",
                    document_id=int(document_id) if document_id is not None else None,
                    attachment_id=int(attachment_id),
                    original_name=str(original_name),
                    evidence=f"document_type={doc_type}",
                    decisive=True,
                )
            )
        for signal_type, terms in STATUS_FILENAME_PATTERNS:
            normalized_name = _normalize(str(original_name))
            matched = [term for term in terms if _normalize(term) in normalized_name]
            if matched:
                signals.append(
                    StatusSignal(
                        signal_type=signal_type,
                        source="attachment_filename",
                        document_id=int(document_id) if document_id is not None else None,
                        attachment_id=int(attachment_id),
                        original_name=str(original_name),
                        evidence=", ".join(matched),
                        decisive=True,
                    )
                )
        if doc_type == "tender_declaration":
            for term in ("κατακύρωση", "αποσφράγιση", "σύμβαση"):
                sample = str(text_sample or "")
                if term in sample:
                    signals.append(
                        StatusSignal(
                            signal_type="procedural_mention",
                            source="tender_declaration_text_sample",
                            document_id=int(document_id),
                            attachment_id=int(attachment_id),
                            original_name=str(original_name),
                            evidence=_context(sample, term),
                            decisive=False,
                        )
                    )
    return signals


def _count_documents(connection: sqlite3.Connection, tender_id: int) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM documents
        JOIN attachments ON attachments.id = documents.attachment_id
        WHERE attachments.tender_id = ?
          AND attachments.is_latest = 1
        """,
        (tender_id,),
    ).fetchone()
    return int(row[0])


def _count_latest_attachments(connection: sqlite3.Connection, tender_id: int) -> int:
    row = connection.execute(
        "SELECT COUNT(*) FROM attachments WHERE tender_id = ? AND is_latest = 1",
        (tender_id,),
    ).fetchone()
    return int(row[0])


def _normalize(value: str) -> str:
    without_accents = str.maketrans("άέήίόύώϊΐϋΰ", "αεηιουωιιυυ")
    return re.sub(r"\s+", " ", value.lower().translate(without_accents)).strip()


def _context(text: str, term: str, radius: int = 140) -> str:
    index = text.find(term)
    if index < 0:
        return term
    return re.sub(r"\s+", " ", text[max(0, index - radius) : index + radius]).strip()


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:220]
