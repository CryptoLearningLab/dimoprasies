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
    document_analysis: dict[str, object] | None
    document_evidence: dict[str, object] | None
    zip_entries: list[dict[str, object]] | None
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
    force: bool = False,
    sources_config_path: Path | None = None,
    retry_count: int = 0,
    retry_delay_seconds: float = 10.0,
    request_delay_seconds: float = 0.0,
) -> dict[str, Any]:
    source_report = json.loads(expanded_report_path.read_text(encoding="utf-8"))
    scope_aliases = _scope_aliases(sources_config_path) if sources_config_path else {}
    candidates = _open_proc_candidates(source_report)
    if limit is not None:
        candidates = candidates[: max(0, limit)]

    checked_at = datetime.now(timezone.utc).isoformat()
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    results: list[KimdisFetchResult] = []
    download_dir.mkdir(parents=True, exist_ok=True)

    for index, candidate in enumerate(candidates):
        result = _fetch_one_candidate(
            candidate,
            download_dir=download_dir,
            timeout_seconds=timeout_seconds,
            context=context,
            force=force,
            retrieved_at=checked_at,
            scope_aliases=scope_aliases,
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
    }
    return {
        "checked_at": checked_at,
        "expanded_report_path": str(expanded_report_path),
        "download_dir": str(download_dir),
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
            analysis, evidence, zip_entries = _inspect_download(target_path, target_path.name, candidate, scope_aliases)
            return _result_from_candidate(
                candidate,
                retrieved_at=retrieved_at,
                verification_status=SKIPPED_STATUS,
                local_path=str(target_path),
                original_filename=target_path.name,
                content_type=None,
                size_bytes=target_path.stat().st_size,
                sha256=digest,
                document_analysis=analysis,
                document_evidence=evidence,
                zip_entries=zip_entries,
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
        document_analysis=None,
        document_evidence=None,
        zip_entries=None,
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
    analysis, evidence, zip_entries = _inspect_download(target_path, filename, candidate, scope_aliases)
    return _result_from_candidate(
        candidate,
        retrieved_at=retrieved_at,
        verification_status=status,
        local_path=str(target_path),
        original_filename=filename,
        content_type=content_type,
        size_bytes=size,
        sha256=digest,
        document_analysis=analysis,
        document_evidence=evidence,
        zip_entries=zip_entries,
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
    document_analysis: dict[str, object] | None,
    document_evidence: dict[str, object] | None,
    zip_entries: list[dict[str, object]] | None,
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
        document_analysis=document_analysis,
        document_evidence=document_evidence,
        zip_entries=zip_entries,
        error=error,
    )


def _inspect_download(
    path: Path,
    filename: str,
    candidate: dict[str, Any],
    scope_aliases: dict[str, list[str]],
) -> tuple[dict[str, object] | None, dict[str, object] | None, list[dict[str, object]] | None]:
    if path.suffix.lower() == ".zip":
        return None, None, _zip_entries(path)
    analysis = analyze_document(path, original_name=filename)
    payload = analysis.to_dict()
    evidence = _document_evidence(analysis.full_text, candidate, scope_aliases)
    payload.pop("full_text", None)
    return payload, evidence, None


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


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:180]


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


def _normalize_text(value: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", without_accents)
