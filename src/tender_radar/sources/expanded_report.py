from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
from typing import Any
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tender_radar.config import load_config


KIMDIS_FAMILIES = {
    "khmdhs_notice": {
        "record_type": "PROC",
        "url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice?page={page}",
        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice/attachment/{reference}",
    },
    "khmdhs_auction": {
        "record_type": "AWRD",
        "url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction?page={page}",
        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction/attachment/{reference}",
    },
    "khmdhs_contract": {
        "record_type": "SYMV",
        "url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract?page={page}",
        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract/attachment/{reference}",
    },
}


@dataclass(frozen=True)
class ExpandedTenderCandidate:
    source: str
    record_type: str
    official_id: str
    title: str | None
    authority: str | None
    budget: str | None
    published_at: str | None
    submission_deadline: str | None
    source_url: str
    attachment_url: str | None
    matched_scopes: list[str]
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_expanded_report(
    *,
    sources_config_path: Path,
    eshidis_candidates_path: Path | None,
    kimdis_pages: int = 5,
    timeout_seconds: int = 20,
    allow_insecure_tls: bool = False,
) -> dict[str, Any]:
    sources_config = load_config(sources_config_path)
    scope_aliases = _scope_aliases(sources_config)
    checked_at = datetime.now(timezone.utc).isoformat()
    candidates: list[ExpandedTenderCandidate] = []
    errors: list[dict[str, object]] = []

    if eshidis_candidates_path and eshidis_candidates_path.exists():
        payload = json.loads(eshidis_candidates_path.read_text(encoding="utf-8"))
        candidates.extend(_eshidis_candidates(payload, scope_aliases))
    elif eshidis_candidates_path:
        errors.append(
            {
                "source": "ESHIDIS",
                "path": str(eshidis_candidates_path),
                "message": "ESHIDIS candidates report not found.",
            }
        )

    kimdis_candidates, kimdis_errors = _fetch_kimdis_candidates(
        scope_aliases,
        pages=kimdis_pages,
        timeout_seconds=timeout_seconds,
        allow_insecure_tls=allow_insecure_tls,
    )
    candidates.extend(kimdis_candidates)
    errors.extend(kimdis_errors)

    unique_candidates = _dedupe_by_official_source_id(candidates)
    focus_candidates = [candidate for candidate in unique_candidates if candidate.matched_scopes]
    return {
        "checked_at": checked_at,
        "sources_config_path": str(sources_config_path),
        "eshidis_candidates_path": str(eshidis_candidates_path) if eshidis_candidates_path else None,
        "kimdis_pages": kimdis_pages,
        "summary": {
            "total_candidates": len(unique_candidates),
            "focus_candidates": len(focus_candidates),
            "eshidis_candidates": sum(1 for item in unique_candidates if item.source == "ESHIDIS"),
            "kimdis_candidates": sum(1 for item in unique_candidates if item.source == "KIMDIS"),
            "errors": len(errors),
        },
        "focus_candidates": [candidate.to_dict() for candidate in focus_candidates],
        "all_candidates": [candidate.to_dict() for candidate in unique_candidates],
        "errors": errors,
        "deduplication": {
            "method": "official source id only",
            "title_only_merge": False,
        },
    }


def write_expanded_report(report: dict[str, Any], report_path: Path, markdown_path: Path | None = None) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_expanded_report_markdown(report), encoding="utf-8")


def render_expanded_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    focus = report.get("focus_candidates") if isinstance(report.get("focus_candidates"), list) else []
    all_candidates = report.get("all_candidates") if isinstance(report.get("all_candidates"), list) else []
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Expanded Tender Discovery Report",
        "",
        f"- Checked at: `{report.get('checked_at')}`",
        f"- Total candidates: `{summary.get('total_candidates', 0)}`",
        f"- Focus candidates: `{summary.get('focus_candidates', 0)}`",
        f"- ESHIDIS candidates: `{summary.get('eshidis_candidates', 0)}`",
        f"- KIMDIS candidates: `{summary.get('kimdis_candidates', 0)}`",
        f"- Errors: `{summary.get('errors', 0)}`",
        "- Deduplication: official source id only; title-only merge is disabled.",
        "",
        "## Focus Area Candidates",
        "",
    ]
    if focus:
        lines.extend(_candidate_table(focus))
    else:
        lines.append("No focus-area candidates were found in this controlled pass.")
    lines.extend(["", "## All Candidates", ""])
    lines.extend(_candidate_table(all_candidates[:100]) if all_candidates else ["No candidates found."])
    if errors:
        lines.extend(["", "## Runtime Errors", ""])
        for error in errors:
            lines.append(f"- `{_cell(error.get('source') or '')}`: {_cell(error.get('message') or '')}")
    return "\n".join(lines) + "\n"


def _fetch_kimdis_candidates(
    scope_aliases: dict[str, list[str]],
    *,
    pages: int,
    timeout_seconds: int,
    allow_insecure_tls: bool,
) -> tuple[list[ExpandedTenderCandidate], list[dict[str, object]]]:
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    candidates: list[ExpandedTenderCandidate] = []
    errors: list[dict[str, object]] = []
    body = json.dumps({"contractType": "10"}).encode("utf-8")
    for source_id, family in KIMDIS_FAMILIES.items():
        for page in range(max(0, pages)):
            url = str(family["url"]).format(page=page)
            request = Request(
                url,
                data=body,
                headers={
                    "User-Agent": "TenderRadar/0.1 expanded-report",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=timeout_seconds, context=context) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                errors.append({"source": source_id, "url": url, "message": str(exc)})
                continue
            for item in payload.get("content") or []:
                if not isinstance(item, dict):
                    continue
                reference = str(item.get("referenceNumber") or "")
                if not reference:
                    continue
                candidates.append(
                    ExpandedTenderCandidate(
                        source="KIMDIS",
                        record_type=str(family["record_type"]),
                        official_id=reference,
                        title=_none_or_str(item.get("title")),
                        authority=_organization_name(item),
                        budget=_budget(item),
                        published_at=_none_or_str(item.get("submissionDate") or item.get("signedDate")),
                        submission_deadline=None,
                        source_url=url,
                        attachment_url=str(family["attachment_url"]).format(reference=reference),
                        matched_scopes=_matched_scopes(item, scope_aliases),
                        status="DISCOVERED_KIMDIS_RECORD",
                    )
                )
    return candidates, errors


def _eshidis_candidates(payload: dict[str, Any], scope_aliases: dict[str, list[str]]) -> list[ExpandedTenderCandidate]:
    candidates: list[ExpandedTenderCandidate] = []
    for item in payload.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        eshidis_id = str(item.get("eshidis_id") or "")
        if not eshidis_id:
            continue
        candidates.append(
            ExpandedTenderCandidate(
                source="ESHIDIS",
                record_type="ESHIDIS",
                official_id=eshidis_id,
                title=_none_or_str(item.get("title")),
                authority=_none_or_str(item.get("authority_name")),
                budget=_budget(item),
                published_at=_none_or_str(item.get("published_at")),
                submission_deadline=_none_or_str(item.get("submission_deadline")),
                source_url=f"https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{eshidis_id}",
                attachment_url=None,
                matched_scopes=_matched_scopes(item, scope_aliases),
                status=str(item.get("status") or "DISCOVERED_ACTIVE_CANDIDATE"),
            )
        )
    return candidates


def _scope_aliases(config: dict[str, Any]) -> dict[str, list[str]]:
    scopes: dict[str, list[str]] = {}
    for scope in config.get("scopes") or []:
        if not isinstance(scope, dict):
            continue
        name = str(scope.get("name") or scope.get("id") or "")
        aliases = [_normalize_text(str(alias)) for alias in scope.get("aliases") or [] if str(alias).strip()]
        scopes[name] = aliases
    return scopes


def _matched_scopes(item: dict[str, Any], scope_aliases: dict[str, list[str]]) -> list[str]:
    haystack = _normalize_text(json.dumps(item, ensure_ascii=False))
    tokens = set(_tokens(haystack))
    return [scope for scope, aliases in scope_aliases.items() if any(_alias_matches(alias, haystack, tokens) for alias in aliases)]


def _dedupe_by_official_source_id(candidates: list[ExpandedTenderCandidate]) -> list[ExpandedTenderCandidate]:
    seen: set[tuple[str, str, str]] = set()
    selected: list[ExpandedTenderCandidate] = []
    for candidate in candidates:
        key = (candidate.source, candidate.record_type, candidate.official_id)
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    return selected


def _candidate_table(candidates: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Source | Type | Official id | Title | Authority | Budget | Deadline | Scope | Link |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        link = item.get("source_url") or item.get("attachment_url") or ""
        lines.append(
            "| {source} | {kind} | `{official_id}` | {title} | {authority} | {budget} | {deadline} | {scope} | {link} |".format(
                source=_cell(item.get("source") or ""),
                kind=_cell(item.get("record_type") or ""),
                official_id=_cell(item.get("official_id") or ""),
                title=_cell(item.get("title") or ""),
                authority=_cell(item.get("authority") or ""),
                budget=_cell(item.get("budget") or ""),
                deadline=_cell(item.get("submission_deadline") or ""),
                scope=_cell(", ".join(item.get("matched_scopes") or [])),
                link=_cell(link),
            )
        )
    return lines


def _organization_name(item: dict[str, Any]) -> str | None:
    organization = item.get("organization")
    if isinstance(organization, dict):
        return _none_or_str(organization.get("value") or organization.get("name"))
    return _none_or_str(item.get("organizationName") or item.get("authorityName"))


def _budget(item: dict[str, Any]) -> str | None:
    for key in ("budget", "totalCost", "estimatedValue", "estTotalCost", "awardTotalCost"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    row_text = item.get("row_text")
    if isinstance(row_text, str):
        return _extract_budget_from_text(row_text)
    return None


def _extract_budget_from_text(text: str) -> str | None:
    import re

    match = re.search(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", text)
    return match.group(0) if match else None


def _none_or_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:180]


def _alias_matches(alias: str, haystack: str, tokens: set[str]) -> bool:
    alias_tokens = _tokens(alias)
    if not alias_tokens:
        return False
    if len(alias_tokens) == 1:
        token = alias_tokens[0]
        return token in tokens if len(token) <= 4 else token in tokens or f" {token} " in f" {haystack} "
    return " ".join(alias_tokens) in haystack


def _tokens(value: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9α-ω]+", value)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", without_accents)
