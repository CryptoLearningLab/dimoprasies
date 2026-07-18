from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import Message
import hashlib
import json
from pathlib import Path
import re
import ssl
import time
import unicodedata
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen
import zipfile

from tender_radar.config import load_config
from tender_radar.documents import analyze_document, classify_document_name


OPEN_PROC_STATUS = "SUBMISSION_OPEN_CANDIDATE"
FETCHED_STATUS = "ATTACHMENT_FETCHED_PENDING_DOCUMENT_REVIEW"
SKIPPED_STATUS = "ATTACHMENT_ALREADY_FETCHED_PENDING_DOCUMENT_REVIEW"
FAILED_STATUS = "FETCH_FAILED"


@dataclass(frozen=True)
class KimdisFetchResult:
    official_id: str
    title: str | None
    authority: str | None
    budget: str | None
    submission_deadline: str | None
    source_url: str | None
    attachment_url: str | None
    matched_scopes: list[str]
    candidate_status: str
    verification_status: str
    retrieved_at: str
    local_path: str | None
    original_filename: str | None
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    text_path: str | None
    document_analysis: dict[str, object] | None
    document_evidence: dict[str, object] | None
    zip_entries: list[dict[str, object]] | None
    linked_eshidis_ids: list[str]
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fetch_kimdis_open_proc_candidates(
    *,
    expanded_report_path: Path,
    download_dir: Path,
    timeout_seconds: int = 30,
    allow_insecure_tls: bool = False,
    limit: int | None = None,
    official_id: str | None = None,
    force: bool = False,
    sources_config_path: Path | None = None,
    text_dir: Path | None = None,
    retry_count: int = 0,
    retry_delay_seconds: float = 10.0,
    request_delay_seconds: float = 0.0,
) -> dict[str, Any]:
    source_report = json.loads(expanded_report_path.read_text(encoding="utf-8"))
    scope_aliases = _scope_aliases(sources_config_path) if sources_config_path else {}
    candidates = _open_proc_candidates(source_report)
    if official_id:
        candidates = [candidate for candidate in candidates if str(candidate.get("official_id") or "") == official_id]
    if limit is not None:
        candidates = candidates[: max(0, limit)]

    checked_at = datetime.now(timezone.utc).isoformat()
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    results: list[KimdisFetchResult] = []
    download_dir.mkdir(parents=True, exist_ok=True)
    if text_dir:
        text_dir.mkdir(parents=True, exist_ok=True)

    for index, candidate in enumerate(candidates):
        result = _fetch_one_candidate(
            candidate,
            download_dir=download_dir,
            timeout_seconds=timeout_seconds,
            context=context,
            force=force,
            retrieved_at=checked_at,
            scope_aliases=scope_aliases,
            text_dir=text_dir,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
        )
        results.append(result)
        if (
            request_delay_seconds > 0
            and result.verification_status != SKIPPED_STATUS
            and index < len(candidates) - 1
        ):
            time.sleep(request_delay_seconds)

    result_dicts = [item.to_dict() for item in results]
    summary = {
        "candidates_checked": len(candidates),
        "downloaded": sum(1 for item in results if item.verification_status == FETCHED_STATUS),
        "already_present": sum(1 for item in results if item.verification_status == SKIPPED_STATUS),
        "failed": sum(1 for item in results if item.verification_status == FAILED_STATUS),
        "text_extracted": sum(
            1
            for item in results
            if item.document_analysis and item.document_analysis.get("extraction_status") == "TEXT_EXTRACTED"
        ),
        "zip_files": sum(1 for item in results if item.zip_entries is not None),
        "document_evidence_found": sum(
            1
            for item in results
            if item.document_evidence and item.document_evidence.get("evidence_status") == "DOCUMENT_EVIDENCE_FOUND"
        ),
        "unsupported_or_unread": sum(
            1
            for item in results
            if item.document_analysis and item.document_analysis.get("extraction_status") != "TEXT_EXTRACTED"
        ),
        "linked_eshidis_ids_found": sum(1 for item in results if item.linked_eshidis_ids),
    }
    return {
        "checked_at": checked_at,
        "expanded_report_path": str(expanded_report_path),
        "download_dir": str(download_dir),
        "text_dir": str(text_dir) if text_dir else None,
        "sources_config_path": str(sources_config_path) if sources_config_path else None,
        "summary": summary,
        "shortlist": result_dicts,
        "deduplication": {
            "method": "official KIMDIS PROC id only",
            "title_only_merge": False,
        },
        "status_note": (
            "KIMDIS PROC records remain SUBMISSION_OPEN_CANDIDATE until their official "
            "documents and later notices are reviewed. This command never emits VERIFIED_ACTIVE."
        ),
    }


def write_kimdis_fetch_report(report: dict[str, Any], report_path: Path, markdown_path: Path | None = None) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_kimdis_fetch_markdown(report), encoding="utf-8")


def write_kimdis_document_index(
    report: dict[str, Any],
    index_path: Path,
    *,
    merge_existing: bool = False,
) -> dict[str, Any]:
    index = kimdis_document_index(report)
    if merge_existing and index_path.exists():
        index = _merge_kimdis_document_index(_read_json(index_path), index)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _merge_kimdis_document_index(existing: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged_documents: dict[str, dict[str, Any]] = {}
    for source in (existing, update):
        documents = source.get("documents") if isinstance(source.get("documents"), list) else []
        for document in documents:
            if not isinstance(document, dict):
                continue
            official_id = str(document.get("official_id") or "").strip()
            if official_id:
                merged_documents[official_id] = document
    return {
        **existing,
        "generated_at": update.get("generated_at") or existing.get("generated_at"),
        "source_report": update.get("source_report") or existing.get("source_report"),
        "fetch_report_summary": update.get("fetch_report_summary") or existing.get("fetch_report_summary") or {},
        "status_note": update.get("status_note") or existing.get("status_note"),
        "deduplication": update.get("deduplication") or existing.get("deduplication") or {},
        "documents": list(merged_documents.values()),
    }


def kimdis_document_index(report: dict[str, Any]) -> dict[str, Any]:
    shortlist = report.get("shortlist") if isinstance(report.get("shortlist"), list) else []
    documents = []
    for item in shortlist:
        if not isinstance(item, dict):
            continue
        documents.append(
            {
                "source": "KIMDIS",
                "record_type": "PROC",
                "official_id": item.get("official_id"),
                "title": item.get("title"),
                "authority": item.get("authority"),
                "budget": item.get("budget"),
                "submission_deadline": item.get("submission_deadline"),
                "source_url": item.get("source_url"),
                "attachment_url": item.get("attachment_url"),
                "matched_scopes": item.get("matched_scopes") or [],
                "candidate_status": item.get("candidate_status"),
                "verification_status": item.get("verification_status"),
                "retrieved_at": item.get("retrieved_at"),
                "local_path": item.get("local_path"),
                "original_filename": item.get("original_filename"),
                "content_type": item.get("content_type"),
                "size_bytes": item.get("size_bytes"),
                "sha256": item.get("sha256"),
                "text_path": item.get("text_path"),
                "document_analysis": item.get("document_analysis"),
                "document_evidence": item.get("document_evidence"),
                "zip_entries": item.get("zip_entries"),
                "linked_eshidis_ids": item.get("linked_eshidis_ids") or [],
            }
        )
    return {
        "generated_at": report.get("checked_at"),
        "source_report": report.get("expanded_report_path"),
        "fetch_report_summary": report.get("summary") or {},
        "status_note": report.get("status_note"),
        "deduplication": report.get("deduplication") or {},
        "documents": documents,
    }


def render_kimdis_fetch_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    shortlist = report.get("shortlist") if isinstance(report.get("shortlist"), list) else []
    lines = [
        "# KIMDIS Open PROC Fetch Report",
        "",
        f"- Checked at: `{report.get('checked_at')}`",
        f"- Expanded report: `{report.get('expanded_report_path')}`",
        f"- Candidates checked: `{summary.get('candidates_checked', 0)}`",
        f"- Downloaded: `{summary.get('downloaded', 0)}`",
        f"- Already present: `{summary.get('already_present', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        f"- Text extracted: `{summary.get('text_extracted', 0)}`",
        f"- ZIP files inspected: `{summary.get('zip_files', 0)}`",
        f"- Document evidence found: `{summary.get('document_evidence_found', 0)}`",
        f"- Linked ESHIDIS ids found: `{summary.get('linked_eshidis_ids_found', 0)}`",
        "- Status: candidate-only; no record is promoted to `VERIFIED_ACTIVE` by this report.",
        "- Deduplication: official KIMDIS PROC id only; title-only merge is disabled.",
        "",
        "| Official id | Status | Title | Authority | Budget | Deadline | File | SHA-256 | Links |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in shortlist:
        if not isinstance(item, dict):
            continue
        links = []
        if item.get("source_url"):
            links.append(str(item["source_url"]))
        if item.get("attachment_url"):
            links.append(str(item["attachment_url"]))
        lines.append(
            "| {official_id} | `{status}` | {title} | {authority} | {budget} | {deadline} | {file} | `{sha}` | {links} |".format(
                official_id=_cell(item.get("official_id") or ""),
                status=_cell(item.get("verification_status") or ""),
                title=_cell(item.get("title") or ""),
                authority=_cell(item.get("authority") or ""),
                budget=_cell(item.get("budget") or ""),
                deadline=_cell(item.get("submission_deadline") or ""),
                file=_cell(item.get("local_path") or ""),
                sha=_cell(str(item.get("sha256") or "")[:16]),
                links=_cell(" ".join(links)),
            )
        )
    if not shortlist:
        lines.append("| | `NO_OPEN_PROC_CANDIDATES` | | | | | | | |")

    lines.extend(["", "## Document Inspection", ""])
    for item in shortlist:
        if not isinstance(item, dict):
            continue
        lines.append(f"### {_cell(item.get('official_id') or '')}")
        analysis = item.get("document_analysis") if isinstance(item.get("document_analysis"), dict) else None
        evidence = item.get("document_evidence") if isinstance(item.get("document_evidence"), dict) else None
        zip_entries = item.get("zip_entries") if isinstance(item.get("zip_entries"), list) else None
        if analysis:
            lines.append(
                "- `{type}`: `{status}`, pages `{pages}`".format(
                    type=_cell(analysis.get("document_type") or "other"),
                    status=_cell(analysis.get("extraction_status") or "UNKNOWN"),
                    pages=_cell(analysis.get("page_or_sheet_count") or ""),
                )
            )
        if evidence:
            lines.append(
                "- Evidence: `{status}`; authority `{authority}`; scope `{scope}`".format(
                    status=_cell(evidence.get("evidence_status") or "UNKNOWN"),
                    authority=_cell(evidence.get("authority_match") or ""),
                    scope=_cell(", ".join(evidence.get("scope_alias_matches") or [])),
                )
            )
        if zip_entries:
            lines.append(f"- ZIP entries: `{len(zip_entries)}`")
            for entry in zip_entries[:12]:
                if not isinstance(entry, dict):
                    continue
                lines.append(
                    f"  - `{_cell(entry.get('name') or '')}` -> `{_cell(entry.get('document_type') or 'other')}`"
                )
        linked_eshidis_ids = item.get("linked_eshidis_ids") if isinstance(item.get("linked_eshidis_ids"), list) else []
        if linked_eshidis_ids:
            lines.append(f"- Linked ESHIDIS ids: `{_cell(', '.join(str(value) for value in linked_eshidis_ids))}`")
        if item.get("error"):
            lines.append(f"- Error: `{_cell(item.get('error') or '')}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _open_proc_candidates(source_report: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = source_report.get("focus_open_proc_candidates")
    if not isinstance(candidates, list):
        return []
    return [
        item
        for item in candidates
        if isinstance(item, dict)
        and item.get("source") == "KIMDIS"
        and item.get("record_type") == "PROC"
        and item.get("status") == OPEN_PROC_STATUS
        and item.get("official_id")
        and item.get("attachment_url")
    ]


def _fetch_one_candidate(
    candidate: dict[str, Any],
    *,
    download_dir: Path,
    timeout_seconds: int,
    context: ssl.SSLContext | None,
    force: bool,
    retrieved_at: str,
    scope_aliases: dict[str, list[str]],
    text_dir: Path | None,
    retry_count: int,
    retry_delay_seconds: float,
) -> KimdisFetchResult:
    official_id = str(candidate.get("official_id") or "")
    attachment_url = str(candidate.get("attachment_url") or "")
    target_dir = download_dir / _safe_path_part(official_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    if not force:
        existing_files = sorted(path for path in target_dir.iterdir() if path.is_file())
        if existing_files:
            target_path = existing_files[0]
            digest = _sha256(target_path.read_bytes())
            analysis, evidence, zip_entries, text_path, linked_eshidis_ids = _inspect_download(
                target_path,
                target_path.name,
                candidate,
                scope_aliases,
                text_dir,
            )
            return _result_from_candidate(
                candidate,
                retrieved_at=retrieved_at,
                verification_status=SKIPPED_STATUS,
                local_path=str(target_path),
                original_filename=target_path.name,
                content_type=None,
                size_bytes=target_path.stat().st_size,
                sha256=digest,
                text_path=text_path,
                document_analysis=analysis,
                document_evidence=evidence,
                zip_entries=zip_entries,
                linked_eshidis_ids=linked_eshidis_ids,
                error=None,
            )
    last_error: str | None = None
    for attempt in range(retry_count + 1):
        if attempt:
            time.sleep(retry_delay_seconds)
        try:
            return _download_one_candidate(
                candidate,
                official_id=official_id,
                attachment_url=attachment_url,
                target_dir=target_dir,
                timeout_seconds=timeout_seconds,
                context=context,
                force=force,
                retrieved_at=retrieved_at,
                scope_aliases=scope_aliases,
                text_dir=text_dir,
            )
        except HTTPError as exc:
            last_error = str(exc)
            if exc.code != 429 or attempt >= retry_count:
                break
            continue
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            break
    return _result_from_candidate(
        candidate,
        retrieved_at=retrieved_at,
        verification_status=FAILED_STATUS,
        local_path=None,
        original_filename=None,
        content_type=None,
        size_bytes=None,
        sha256=None,
        text_path=None,
        document_analysis=None,
        document_evidence=None,
        zip_entries=None,
        linked_eshidis_ids=[],
        error=last_error,
    )


def _download_one_candidate(
    candidate: dict[str, Any],
    *,
    official_id: str,
    attachment_url: str,
    target_dir: Path,
    timeout_seconds: int,
    context: ssl.SSLContext | None,
    force: bool,
    retrieved_at: str,
    scope_aliases: dict[str, list[str]],
    text_dir: Path | None,
) -> KimdisFetchResult:
    request = Request(
        attachment_url,
        headers={"User-Agent": "TenderRadar/0.1 kimdis-fetch", "Accept": "*/*"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type")
        filename = _response_filename(response.headers, official_id, content_type)
    target_path = _target_path(target_dir, filename, force=force)
    if target_path.exists() and not force:
        digest = _sha256(target_path.read_bytes())
        size = target_path.stat().st_size
        status = SKIPPED_STATUS
    else:
        target_path.write_bytes(content)
        digest = _sha256(content)
        size = len(content)
        status = FETCHED_STATUS
    analysis, evidence, zip_entries, text_path, linked_eshidis_ids = _inspect_download(
        target_path, filename, candidate, scope_aliases, text_dir
    )
    return _result_from_candidate(
        candidate,
        retrieved_at=retrieved_at,
        verification_status=status,
        local_path=str(target_path),
        original_filename=filename,
        content_type=content_type,
        size_bytes=size,
        sha256=digest,
        text_path=text_path,
        document_analysis=analysis,
        document_evidence=evidence,
        zip_entries=zip_entries,
        linked_eshidis_ids=linked_eshidis_ids,
        error=None,
    )


def _result_from_candidate(
    candidate: dict[str, Any],
    *,
    retrieved_at: str,
    verification_status: str,
    local_path: str | None,
    original_filename: str | None,
    content_type: str | None,
    size_bytes: int | None,
    sha256: str | None,
    text_path: str | None,
    document_analysis: dict[str, object] | None,
    document_evidence: dict[str, object] | None,
    zip_entries: list[dict[str, object]] | None,
    linked_eshidis_ids: list[str],
    error: str | None,
) -> KimdisFetchResult:
    matched_scopes = candidate.get("matched_scopes") if isinstance(candidate.get("matched_scopes"), list) else []
    return KimdisFetchResult(
        official_id=str(candidate.get("official_id") or ""),
        title=_none_or_str(candidate.get("title")),
        authority=_none_or_str(candidate.get("authority")),
        budget=_none_or_str(candidate.get("budget")),
        submission_deadline=_none_or_str(candidate.get("submission_deadline")),
        source_url=_none_or_str(candidate.get("source_url")),
        attachment_url=_none_or_str(candidate.get("attachment_url")),
        matched_scopes=[str(item) for item in matched_scopes],
        candidate_status=str(candidate.get("status") or OPEN_PROC_STATUS),
        verification_status=verification_status,
        retrieved_at=retrieved_at,
        local_path=local_path,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        text_path=text_path,
        document_analysis=document_analysis,
        document_evidence=document_evidence,
        zip_entries=zip_entries,
        linked_eshidis_ids=linked_eshidis_ids,
        error=error,
    )


def _inspect_download(
    path: Path,
    filename: str,
    candidate: dict[str, Any],
    scope_aliases: dict[str, list[str]],
    text_dir: Path | None,
) -> tuple[dict[str, object] | None, dict[str, object] | None, list[dict[str, object]] | None, str | None, list[str]]:
    if path.suffix.lower() == ".zip":
        zip_entries = _zip_entries(path)
        linked_eshidis_ids = extract_eshidis_ids_from_text(
            filename,
            candidate.get("title"),
            candidate.get("authority"),
            *(entry.get("name") for entry in zip_entries if isinstance(entry, dict)),
        )
        return None, None, zip_entries, None, linked_eshidis_ids
    analysis = analyze_document(path, original_name=filename)
    payload = analysis.to_dict()
    evidence = _document_evidence(analysis.full_text, candidate, scope_aliases)
    text_path = _write_text_artifact(analysis.full_text, candidate, text_dir)
    linked_eshidis_ids = extract_eshidis_ids_from_text(
        filename,
        candidate.get("title"),
        candidate.get("authority"),
        candidate.get("source_url"),
        analysis.full_text,
    )
    payload.pop("full_text", None)
    return payload, evidence, None, text_path, linked_eshidis_ids


def extract_eshidis_ids_from_text(*values: object) -> list[str]:
    text = " ".join(str(value or "") for value in values)
    if not text.strip():
        return []
    normalized = _normalize_eshidis_labels(_normalize_text(text))
    linked: list[str] = []
    patterns = [
        r"(?:εσηδησ|εσηδης)\W{0,40}(?:α\s*/?\s*α)?\W{0,20}(\d{5,7})(?!\d)",
        r"(?:α\s*/?\s*α|αα)\W{0,40}(?:εσηδησ|εσηδης|συστημα(?:τοσ)?)\W{0,30}(\d{5,7})(?!\d)",
        r"(?:συστημα(?:τοσ)?)\W{0,40}(?:εσηδησ|εσηδης)?\W{0,20}(?:α\s*/?\s*α|αα)?\W{0,20}(\d{5,7})(?!\d)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            value = match.group(1)
            if value not in linked:
                linked.append(value)
    return linked


def _normalize_eshidis_labels(value: str) -> str:
    return re.sub(r"ε\s*\.?\s*σ\s*\.?\s*η\s*\.?\s*δ\s*\.?\s*η\s*\.?\s*[σς]", "εσηδησ", value)


def _write_text_artifact(full_text: str | None, candidate: dict[str, Any], text_dir: Path | None) -> str | None:
    if not full_text or not text_dir:
        return None
    official_id = _safe_path_part(str(candidate.get("official_id") or "unknown"))
    path = text_dir / f"{official_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(full_text, encoding="utf-8")
    return str(path)


def _document_evidence(
    full_text: str | None,
    candidate: dict[str, Any],
    scope_aliases: dict[str, list[str]],
) -> dict[str, object]:
    if not full_text:
        return {
            "evidence_status": "NO_TEXT_FOR_EVIDENCE_CHECK",
            "authority_match": None,
            "scope_alias_matches": [],
        }
    normalized = _normalize_text(full_text)
    tokens = set(_tokens(normalized))
    authority = _none_or_str(candidate.get("authority"))
    authority_match = authority if authority and _normalize_text(authority) in normalized else None
    matched_scopes = candidate.get("matched_scopes") if isinstance(candidate.get("matched_scopes"), list) else []
    alias_matches: list[str] = []
    for scope in matched_scopes:
        scope_name = str(scope)
        aliases = [scope_name, *scope_aliases.get(scope_name, [])]
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if _alias_matches(normalized_alias, normalized, tokens):
                alias_matches.append(alias)
                break
    evidence_found = bool(authority_match or alias_matches)
    return {
        "evidence_status": "DOCUMENT_EVIDENCE_FOUND" if evidence_found else "DOCUMENT_TEXT_EXTRACTED_NO_SCOPE_AUTHORITY_MATCH",
        "authority_match": authority_match,
        "scope_alias_matches": alias_matches,
    }


def _zip_entries(path: Path) -> list[dict[str, object]]:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                classification = classify_document_name(info.filename)
                entries.append(
                    {
                        "name": info.filename,
                        "size_bytes": info.file_size,
                        "document_type": classification.document_type,
                        "classification_confidence": classification.confidence,
                        "matched_terms": list(classification.matched_terms),
                    }
                )
            return entries
    except zipfile.BadZipFile:
        return [{"name": path.name, "document_type": "other", "error": "Bad ZIP file."}]


def _response_filename(headers: Message, official_id: str, content_type: str | None) -> str:
    disposition = headers.get("Content-Disposition")
    if disposition:
        filename_star = re.search(r"filename\*=([^']*)''([^;]+)", disposition, flags=re.IGNORECASE)
        if filename_star:
            decoded = unquote(filename_star.group(2).strip().strip('"'))
            return _safe_filename(decoded)
        filename = re.search(r'filename="?([^";]+)"?', disposition, flags=re.IGNORECASE)
        if filename:
            return _safe_filename(unquote(filename.group(1).strip()))
    return _safe_filename(f"{official_id}{_extension_from_content_type(content_type)}")


def _extension_from_content_type(content_type: str | None) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
    }.get(normalized, ".bin")


def _target_path(target_dir: Path, filename: str, *, force: bool) -> Path:
    target = target_dir / filename
    if force or not target.exists():
        return target
    return target


def _safe_filename(value: str) -> str:
    cleaned = value.replace("\x00", "").replace("/", "_").replace("\\", "_").strip()
    return cleaned or "attachment.bin"


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _none_or_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:180]


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    normalized = unicodedata.normalize("NFC", without_accents)
    return re.sub(r"\s+", " ", normalized).strip()


def _scope_aliases(config_path: Path) -> dict[str, list[str]]:
    config = load_config(config_path)
    aliases_by_scope: dict[str, list[str]] = {}
    for scope in config.get("scopes") or []:
        if not isinstance(scope, dict):
            continue
        name = str(scope.get("name") or scope.get("id") or "")
        aliases_by_scope[name] = [str(alias) for alias in scope.get("aliases") or [] if str(alias).strip()]
    return aliases_by_scope


def _alias_matches(alias: str, haystack: str, tokens: set[str]) -> bool:
    alias_tokens = _tokens(alias)
    if not alias_tokens:
        return False
    if len(alias_tokens) == 1:
        token = alias_tokens[0]
        return token in tokens if len(token) <= 4 else token in tokens or f" {token} " in f" {haystack} "
    return " ".join(alias_tokens) in haystack


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9α-ω]+", value)
