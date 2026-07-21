from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from tender_radar.config import load_config
from tender_radar.db import initialize
from tender_radar.documents import extract_text_with_metadata


JsonFetcher = Callable[[str], dict[str, Any]]
BytesFetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class EntalmaRecord:
    ada: str
    org_id: str
    org_name: str
    subject: str
    protocol_number: str | None
    issue_date: str | None
    published_at: str | None
    document_url: str | None
    local_path: str | None
    status: str
    matched_keywords: list[str]
    text_sample: str | None
    archive_path: str | None = None
    project_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ada": self.ada,
            "org_id": self.org_id,
            "org_name": self.org_name,
            "subject": self.subject,
            "protocol_number": self.protocol_number,
            "issue_date": self.issue_date,
            "published_at": self.published_at,
            "document_url": self.document_url,
            "local_path": self.local_path,
            "archive_path": self.archive_path,
            "project_title": self.project_title,
            "status": self.status,
            "matched_keywords": self.matched_keywords,
            "text_sample": self.text_sample,
        }


def scan_entalmata(
    *,
    db_path: Path,
    config_path: Path,
    download_dir: Path,
    today: date | None = None,
    max_pages: int | None = None,
    json_fetcher: JsonFetcher | None = None,
    bytes_fetcher: BytesFetcher | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    visible_days = int(config.get("visible_window_days") or 15)
    as_of = today or date.today()
    cutoff = as_of - timedelta(days=visible_days - 1)
    keywords = [str(item) for item in config.get("keywords") or [] if str(item).strip()]
    api = config.get("api") if isinstance(config.get("api"), dict) else {}
    json_fetch = json_fetcher or fetch_json
    bytes_fetch = bytes_fetcher or fetch_bytes

    initialize(db_path)
    download_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "ok": True,
        "checked_organizations": 0,
        "pages_checked": 0,
        "decisions_seen": 0,
        "outside_window": 0,
        "without_document": 0,
        "skipped_existing": 0,
        "matched": 0,
        "rejected": 0,
        "errors": 0,
        "archived": 0,
    }
    errors: list[dict[str, str]] = []
    visible_records: list[EntalmaRecord] = []

    for organization in config.get("organizations") or []:
        if not isinstance(organization, dict):
            continue
        org_id = str(organization.get("id") or "").strip()
        org_name = str(organization.get("name") or org_id).strip()
        if not org_id:
            continue
        summary["checked_organizations"] += 1
        start_page = int(api.get("start_page") or api.get("page") or 0)
        page_limit = int(max_pages if max_pages is not None else api.get("max_pages") or 1)
        for page in range(start_page, start_page + page_limit):
            url = search_url(api, org_id, page=page)
            try:
                payload = json_fetch(url)
            except Exception as exc:  # pragma: no cover - network fallback
                summary["errors"] += 1
                errors.append({"org_id": org_id, "stage": "search", "page": str(page), "error": str(exc)})
                continue
            decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
            if not decisions:
                break
            summary["pages_checked"] += 1
            page_outside_window = 0
            for decision in decisions:
                if not isinstance(decision, dict):
                    continue
                summary["decisions_seen"] += 1
                issue = decision_issue_date(decision)
                if issue is None or issue < cutoff:
                    summary["outside_window"] += 1
                    page_outside_window += 1
                    continue
                document_url = str(decision.get("documentUrl") or "").strip() or None
                if not document_url:
                    summary["without_document"] += 1
                    continue
                try:
                    cached = reusable_entalma_record(db_path, decision=decision, document_url=document_url)
                    if cached:
                        summary["skipped_existing"] += 1
                        record = cached
                    else:
                        record = process_decision(
                            decision,
                            org_id=org_id,
                            org_name=org_name,
                            download_dir=download_dir,
                            keywords=keywords,
                            bytes_fetcher=bytes_fetch,
                        )
                except Exception as exc:  # pragma: no cover - network/filesystem fallback
                    summary["errors"] += 1
                    errors.append({"org_id": org_id, "stage": "decision", "page": str(page), "error": str(exc)})
                    continue
                metadata = {
                    "source_search_url": url,
                    "source_page": page,
                    "project_title": record.project_title,
                }
                upsert_entalma_record(db_path, record, metadata=metadata)
                if record.status == "VISIBLE":
                    summary["matched"] += 1
                    visible_records.append(record)
                else:
                    summary["rejected"] += 1
            if page_outside_window == len(decisions):
                break

    summary["archived"] = archive_old_entalmata(db_path, download_dir / "old", cutoff)
    return {
        "ok": not errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "download_dir": str(download_dir),
        "visible_window_days": visible_days,
        "cutoff_date": cutoff.isoformat(),
        "summary": summary,
        "records": [record.to_dict() for record in sorted(visible_records, key=entalma_sort_key, reverse=True)],
        "errors": errors,
    }


def search_url(api: dict[str, Any], org_id: str, *, page: int | None = None) -> str:
    base = str(api.get("search_url") or "https://diavgeia.gov.gr/opendata/search.json")
    params = {
        "org": org_id,
        "size": int(api.get("size") or 40),
        "page": int(page if page is not None else api.get("start_page") or api.get("page") or 0),
    }
    if api.get("order"):
        params["order"] = str(api.get("order"))
    else:
        params["sort"] = str(api.get("sort") or "recent")
    if api.get("status"):
        params["status"] = str(api.get("status"))
    return f"{base}?{urlencode(params)}"


def reusable_entalma_record(db_path: Path, *, decision: dict[str, Any], document_url: str | None) -> EntalmaRecord | None:
    ada = decision_ada(decision)
    if not ada or not document_url:
        return None
    initialize(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT ada, org_id, org_name, subject, protocol_number, issue_date,
                   published_at, document_url, local_path, archive_path, status,
                   matched_keywords_json, text_sample, metadata_json
            FROM diavgeia_entalmata
            WHERE ada = ?
            """,
            (ada,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    if str(row["document_url"] or "") != document_url:
        return None
    if row["status"] not in {"VISIBLE", "REJECTED"}:
        return None
    if not row["text_sample"] and not row["matched_keywords_json"]:
        return None
    local_path = Path(str(row["local_path"])) if row["local_path"] else None
    if not local_path or not local_path.exists():
        return None
    return _record_from_row(row)


def decision_ada(decision: dict[str, Any]) -> str:
    ada = str(decision.get("ada") or decision.get("adaCode") or "").strip()
    return ada or stable_decision_key(decision)


def process_decision(
    decision: dict[str, Any],
    *,
    org_id: str,
    org_name: str,
    download_dir: Path,
    keywords: list[str],
    bytes_fetcher: BytesFetcher,
) -> EntalmaRecord:
    ada = decision_ada(decision)
    subject = str(decision.get("subject") or "").strip() or ada
    protocol_number = _none_or_str(decision.get("protocolNumber"))
    document_url = str(decision.get("documentUrl") or "").strip() or None
    issue = decision_issue_date(decision)
    published = decision_published_at(decision)
    filename = safe_filename(f"{protocol_number or ada}.pdf")
    local_path = download_dir / filename
    if document_url and not local_path.exists():
        local_path.write_bytes(bytes_fetcher(document_url))
    text = extract_pdf_text(local_path) if local_path.exists() else ""
    if not text:
        text = " ".join(str(decision.get(key) or "") for key in ("subject", "protocolNumber", "ada"))
    matched = matched_keywords(text, keywords)
    return EntalmaRecord(
        ada=ada,
        org_id=org_id,
        org_name=org_name,
        subject=subject,
        protocol_number=protocol_number,
        issue_date=issue.isoformat() if issue else None,
        published_at=published,
        document_url=document_url,
        local_path=str(local_path) if local_path.exists() else None,
        archive_path=None,
        project_title=extract_project_title(text),
        status="VISIBLE" if matched else "REJECTED",
        matched_keywords=matched,
        text_sample=short_text_sample(text),
    )


def upsert_entalma_record(db_path: Path, record: EntalmaRecord, *, metadata: dict[str, object] | None = None) -> None:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO diavgeia_entalmata (
                ada, org_id, org_name, subject, protocol_number, issue_date,
                published_at, document_url, local_path, status,
                matched_keywords_json, text_sample, fetched_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ada) DO UPDATE SET
                org_id = excluded.org_id,
                org_name = excluded.org_name,
                subject = excluded.subject,
                protocol_number = excluded.protocol_number,
                issue_date = excluded.issue_date,
                published_at = excluded.published_at,
                document_url = excluded.document_url,
                local_path = COALESCE(excluded.local_path, diavgeia_entalmata.local_path),
                status = excluded.status,
                matched_keywords_json = excluded.matched_keywords_json,
                text_sample = excluded.text_sample,
                fetched_at = excluded.fetched_at,
                metadata_json = excluded.metadata_json
            """,
            (
                record.ada,
                record.org_id,
                record.org_name,
                record.subject,
                record.protocol_number,
                record.issue_date,
                record.published_at,
                record.document_url,
                record.local_path,
                record.status,
                json.dumps(record.matched_keywords, ensure_ascii=False),
                record.text_sample,
                now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def list_entalmata(db_path: Path, *, today: date | None = None, visible_window_days: int = 15) -> list[EntalmaRecord]:
    initialize(db_path)
    cutoff = (today or date.today()) - timedelta(days=visible_window_days - 1)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT ada, org_id, org_name, subject, protocol_number, issue_date,
                   published_at, document_url, local_path, archive_path, status,
                   matched_keywords_json, text_sample, metadata_json
            FROM diavgeia_entalmata
            WHERE status = 'VISIBLE'
              AND (issue_date IS NULL OR issue_date >= ?)
            ORDER BY issue_date DESC, fetched_at DESC, ada
            """,
            (cutoff.isoformat(),),
        ).fetchall()
    finally:
        connection.close()
    return [_record_from_row(row) for row in rows]


def list_archived_entalmata(db_path: Path, *, limit: int = 50) -> list[EntalmaRecord]:
    initialize(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT ada, org_id, org_name, subject, protocol_number, issue_date,
                   published_at, document_url, local_path, archive_path, status,
                   matched_keywords_json, text_sample, metadata_json
            FROM diavgeia_entalmata
            WHERE status = 'ARCHIVED'
            ORDER BY archived_at DESC, issue_date DESC, ada
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()
    return [_record_from_row(row) for row in rows]


def archived_entalmata_count(db_path: Path) -> int:
    initialize(db_path)
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT COUNT(*) FROM diavgeia_entalmata WHERE status = 'ARCHIVED'").fetchone()
    finally:
        connection.close()
    return int(row[0] if row else 0)


def entalma_file_path(db_path: Path, ada: str) -> Path | None:
    initialize(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT local_path, archive_path FROM diavgeia_entalmata WHERE ada = ?",
            (ada,),
        ).fetchone()
    finally:
        connection.close()
    if not row:
        return None
    for key in ("local_path", "archive_path"):
        value = row[key]
        if value:
            path = Path(str(value))
            if path.exists() and path.is_file():
                return path
    return None


def archive_old_entalmata(db_path: Path, archive_dir: Path, cutoff: date) -> int:
    initialize(db_path)
    archive_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    archived = 0
    try:
        rows = connection.execute(
            """
            SELECT ada, local_path
            FROM diavgeia_entalmata
            WHERE status = 'VISIBLE'
              AND issue_date IS NOT NULL
              AND issue_date < ?
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        for row in rows:
            local_path = Path(str(row["local_path"])) if row["local_path"] else None
            archive_path = None
            if local_path and local_path.exists():
                archive_path = archive_dir / unique_name(local_path.name, {item.name for item in archive_dir.iterdir()})
                shutil.move(str(local_path), archive_path)
            connection.execute(
                """
                UPDATE diavgeia_entalmata
                SET status = 'ARCHIVED', archive_path = ?, archived_at = ?
                WHERE ada = ?
                """,
                (str(archive_path) if archive_path else None, now, row["ada"]),
            )
            archived += 1
        connection.commit()
    finally:
        connection.close()
    return archived


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(safe_request_url(url), headers={"Accept": "application/json", "User-Agent": "TenderRadar/0.1 entalmata"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    request = Request(safe_request_url(url), headers={"User-Agent": "TenderRadar/0.1 entalmata"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def safe_request_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/%"),
            quote(parts.query, safe="=&%/:;+?,@"),
            quote(parts.fragment, safe="=&%/:;+?,@"),
        )
    )


def extract_pdf_text(path: Path) -> str:
    try:
        import fitz  # type: ignore
    except Exception:
        extraction = extract_text_with_metadata(path)
        return extraction.full_text or extraction.text_sample or ""
    try:
        with fitz.open(path) as document:
            return "\n".join(page.get_text("text") for page in document).strip()
    except Exception:
        extraction = extract_text_with_metadata(path)
        return extraction.full_text or extraction.text_sample or ""


def matched_keywords(text: str, keywords: list[str]) -> list[str]:
    normalized_text = normalize_greek(text)
    return [keyword for keyword in keywords if normalize_greek(keyword) in normalized_text]


def extract_project_title(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return None
    patterns = [
        r"ΚΩΔΙΚΟΣ\s+ΕΡΓΟΥ\s*:?\s*[A-ZΑ-Ω0-9/.\-]+\s+(?P<title>.+?)(?:\s+ΤΙΤΛΟΣ\s+ΕΡΓΟΥ|\s+ΥΠΟΕΡΓΟ|\s+ΚΩΔΙΚΟΣ\s+ΥΠΟΕΡΓΟΥ|$)",
        r"ΤΙΤΛΟΣ\s+ΕΡΓΟΥ\s*:?\s*(?P<title>.+?)(?:\s+ΥΠΟΕΡΓΟ|\s+ΚΩΔΙΚΟΣ|\s+Π/Υ|\s+ΙΒΑΝ|\s+Επωνυμία\s+δικαιούχου|\s+ΑΠΟΦΑΣΙΖΟΥΜΕ|$)",
        r"για\s+το\s+έργο/α\s*:?\s*(?P<title>.+?)(?:\s+Επωνυμία\s+δικαιούχου|\s+ΑΠΟΦΑΣΗ|\s+Έχοντας\s+υπόψη|$)",
        r"με\s+τίτλο\s+(?P<title>.+?)(?:\s+συνολικού\s+ποσού|\s+προϋπολογισμού|\s+για\s+το\s+έργο/α|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        title = normalize_project_title(match.group("title"))
        if title:
            return title
    return None


def normalize_project_title(value: str) -> str | None:
    title = re.sub(r"\s+", " ", value or "").strip(" .:-")
    if not title:
        return None
    normalized = normalize_greek(title)
    if "iban" in normalized or re.match(r"^gr\d{10,}", normalized):
        return None
    title = re.sub(r"^\d{4}[A-ZΑ-Ω0-9/.\-]+\s+", "", title)
    if len(title) < 8:
        return None
    return title[:240]


def decision_issue_date(decision: dict[str, Any]) -> date | None:
    for key in ("issueDate", "submissionTimestamp", "publishTimestamp", "date"):
        parsed = parse_diavgeia_date(decision.get(key))
        if parsed:
            return parsed
    return None


def decision_published_at(decision: dict[str, Any]) -> str | None:
    for key in ("submissionTimestamp", "publishTimestamp", "issueDate"):
        parsed = parse_diavgeia_datetime(decision.get(key))
        if parsed:
            return parsed.isoformat()
    return None


def parse_diavgeia_date(value: object) -> date | None:
    parsed = parse_diavgeia_datetime(value)
    return parsed.date() if parsed else None


def parse_diavgeia_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_diavgeia_datetime(int(text))
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text.replace("Z", "+0000"), fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def stable_decision_key(decision: dict[str, Any]) -> str:
    source = "|".join(str(decision.get(key) or "") for key in ("subject", "protocolNumber", "documentUrl"))
    return "NOADA-" + re.sub(r"[^0-9a-f]", "", hashlib.sha1(source.encode("utf-8")).hexdigest())[:16]


def safe_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip())
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    return sanitized or "document.pdf"


def unique_name(name: str, used_names: set[str]) -> str:
    candidate = name
    stem = Path(name).stem or "document"
    suffix = Path(name).suffix
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


def short_text_sample(value: str, limit: int = 280) -> str | None:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return None
    return text[:limit]


def normalize_greek(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", without_accents)).strip()


def entalma_sort_key(record: EntalmaRecord) -> tuple[str, str]:
    return (record.issue_date or "", record.ada)


def _record_from_row(row: sqlite3.Row) -> EntalmaRecord:
    try:
        keywords = json.loads(row["matched_keywords_json"] or "[]")
    except json.JSONDecodeError:
        keywords = []
    metadata: dict[str, Any] = {}
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except (KeyError, json.JSONDecodeError):
        metadata = {}
    return EntalmaRecord(
        ada=str(row["ada"]),
        org_id=str(row["org_id"]),
        org_name=str(row["org_name"] or ""),
        subject=str(row["subject"] or ""),
        protocol_number=_none_or_str(row["protocol_number"]),
        issue_date=_none_or_str(row["issue_date"]),
        published_at=_none_or_str(row["published_at"]),
        document_url=_none_or_str(row["document_url"]),
        local_path=_none_or_str(row["local_path"]),
        archive_path=_none_or_str(row["archive_path"]),
        project_title=_none_or_str(metadata.get("project_title")),
        status=str(row["status"] or "UNKNOWN"),
        matched_keywords=[str(item) for item in keywords if str(item).strip()],
        text_sample=_none_or_str(row["text_sample"]),
    )


def _none_or_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
