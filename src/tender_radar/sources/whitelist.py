from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tender_radar.config import load_config


@dataclass(frozen=True)
class SourceAuditResult:
    source_id: str
    name: str
    url: str
    source_type: str
    scope_id: str | None
    scope_name: str | None
    method: str
    status: str
    status_code: int | None
    content_type: str | None
    requires_browser_hint: bool
    adapter_required: bool
    fallback_available: bool
    records_sampled: int | None
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_source_whitelist(
    config_path: Path,
    *,
    timeout_seconds: int = 20,
    allow_insecure_tls: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    checked_at = datetime.now(timezone.utc).isoformat()
    results: list[SourceAuditResult] = []
    for source in config.get("global_sources", []):
        if not isinstance(source, dict):
            continue
        results.append(_audit_configured_source(source, None, None, timeout_seconds, allow_insecure_tls))
    for scope in config.get("scopes", []):
        if not isinstance(scope, dict):
            continue
        scope_results: list[SourceAuditResult] = []
        for index, url in enumerate(scope.get("sources") or [], start=1):
            source = {
                "id": f"{scope.get('id')}_source_{index}",
                "name": f"{scope.get('name')} source {index}",
                "type": "web",
                "url": url,
            }
            scope_results.append(
                _audit_configured_source(
                    source,
                    str(scope.get("id") or ""),
                    str(scope.get("name") or ""),
                    timeout_seconds,
                    allow_insecure_tls,
                )
            )
        results.extend(_mark_scope_fallbacks(scope_results))
    return {
        "config_path": str(config_path),
        "checked_at": checked_at,
        "allow_insecure_tls": allow_insecure_tls,
        "summary": _summary(results),
        "results": [result.to_dict() for result in results],
    }


def write_source_audit_report(report: dict[str, Any], report_path: Path, markdown_path: Path | None = None) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_source_audit_markdown(report), encoding="utf-8")


def render_source_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# Source Whitelist Audit",
        "",
        f"- Config: `{report.get('config_path')}`",
        f"- Checked at: `{report.get('checked_at')}`",
        f"- TLS audit bypass: `{report.get('allow_insecure_tls')}`",
        f"- Total sources: `{summary.get('total', 0)}`",
        f"- Reachable: `{summary.get('reachable', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        f"- Adapter required: `{summary.get('adapter_required', 0)}`",
        f"- Unresolved blockers: `{summary.get('unresolved_blockers', 0)}`",
        "",
        "| Source | Scope | Type | Status | HTTP | Records | Fallback | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("results") or []:
        lines.append(
            "| {name} | {scope} | `{kind}` | `{status}` | {code} | {records} | {fallback} | {message} |".format(
                name=_cell(str(item.get("name") or item.get("source_id") or "")),
                scope=_cell(str(item.get("scope_name") or "")),
                kind=_cell(str(item.get("source_type") or "")),
                status=_cell(str(item.get("status") or "")),
                code=item.get("status_code") or "",
                records=item.get("records_sampled")
                if item.get("records_sampled") is not None
                else "",
                fallback="yes" if item.get("fallback_available") else "",
                message=_cell(str(item.get("message") or "")),
            )
        )
    return "\n".join(lines) + "\n"


def _audit_configured_source(
    source: dict[str, Any],
    scope_id: str | None,
    scope_name: str | None,
    timeout_seconds: int,
    allow_insecure_tls: bool,
) -> SourceAuditResult:
    source_id = str(source.get("id") or "")
    name = str(source.get("name") or source_id)
    source_type = str(source.get("type") or "web")
    url = str(source.get("url") or "")
    if source_type == "api_post":
        return _http_post_api_source(
            source,
            source_id,
            name,
            url,
            source_type,
            scope_id,
            scope_name,
            timeout_seconds,
            allow_insecure_tls,
        )
    if "{" in url or source_type == "url_template":
        return _static_result(
            source_id,
            name,
            url,
            source_type,
            scope_id,
            scope_name,
            "TEMPLATE_REQUIRES_IDENTIFIER",
            "URL template is ready once a known official identifier is available.",
            adapter_required=False,
        )
    return _http_get_source(source_id, name, url, source_type, scope_id, scope_name, timeout_seconds, allow_insecure_tls)


def _http_get_source(
    source_id: str,
    name: str,
    url: str,
    source_type: str,
    scope_id: str | None,
    scope_name: str | None,
    timeout_seconds: int,
    allow_insecure_tls: bool,
) -> SourceAuditResult:
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    request = Request(url, headers={"User-Agent": "TenderRadar/0.1 source-whitelist-audit"})
    try:
        with urlopen(request, timeout=timeout_seconds, context=context) as response:
            body = response.read(8192).decode("utf-8", errors="replace")
            requires_browser = _requires_browser(body)
            known_adapter = _known_adapter(source_id)
            status = "ADAPTER_READY" if known_adapter else "REACHABLE"
            adapter_required = requires_browser and not known_adapter
            if source_type == "web_app" and not known_adapter:
                adapter_required = True
            if known_adapter:
                message = f"Reachable; existing adapter: {known_adapter}."
            elif requires_browser:
                message = "Reachable; browser adapter likely required."
            else:
                message = "Reachable."
            return SourceAuditResult(
                source_id=source_id,
                name=name,
                url=url,
                source_type=source_type,
                scope_id=scope_id,
                scope_name=scope_name,
                method="GET",
                status=status,
                status_code=int(response.status),
                content_type=response.headers.get("Content-Type"),
                requires_browser_hint=requires_browser,
                adapter_required=adapter_required,
                fallback_available=False,
                records_sampled=None,
                message=message,
            )
    except HTTPError as exc:
        known_adapter = _known_adapter(source_id)
        return SourceAuditResult(
            source_id=source_id,
            name=name,
            url=url,
            source_type=source_type,
            scope_id=scope_id,
            scope_name=scope_name,
            method="GET",
            status="HTTP_ERROR",
            status_code=int(exc.code),
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            requires_browser_hint=False,
            adapter_required=known_adapter is None,
            fallback_available=False,
            records_sampled=None,
            message=_failure_message(str(exc.reason), known_adapter),
        )
    except (URLError, TimeoutError, OSError) as exc:
        known_adapter = _known_adapter(source_id)
        return SourceAuditResult(
            source_id=source_id,
            name=name,
            url=url,
            source_type=source_type,
            scope_id=scope_id,
            scope_name=scope_name,
            method="GET",
            status="FAILED",
            status_code=None,
            content_type=None,
            requires_browser_hint=False,
            adapter_required=known_adapter is None,
            fallback_available=False,
            records_sampled=None,
            message=_failure_message(str(exc), known_adapter),
        )


def _http_post_api_source(
    source: dict[str, Any],
    source_id: str,
    name: str,
    url: str,
    source_type: str,
    scope_id: str | None,
    scope_name: str | None,
    timeout_seconds: int,
    allow_insecure_tls: bool,
) -> SourceAuditResult:
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    page_url = url.replace("{PAGE}", "0")
    body = {"contractType": str(source.get("contract_type") or "10")}
    request = Request(
        page_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "User-Agent": "TenderRadar/0.1 source-whitelist-audit",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds, context=context) as response:
            raw = response.read(65536).decode("utf-8", errors="replace")
            records_sampled = _json_content_count(raw)
            message = (
                "Documented ΚΗΜΔΗΣ POST probe succeeded with contractType=10 "
                f"on page 0; sampled {records_sampled} records."
            )
            return SourceAuditResult(
                source_id=source_id,
                name=name,
                url=page_url,
                source_type=source_type,
                scope_id=scope_id,
                scope_name=scope_name,
                method="POST",
                status="ADAPTER_READY",
                status_code=int(response.status),
                content_type=response.headers.get("Content-Type"),
                requires_browser_hint=False,
                adapter_required=False,
                fallback_available=False,
                records_sampled=records_sampled,
                message=message,
            )
    except HTTPError as exc:
        return SourceAuditResult(
            source_id=source_id,
            name=name,
            url=page_url,
            source_type=source_type,
            scope_id=scope_id,
            scope_name=scope_name,
            method="POST",
            status="HTTP_ERROR",
            status_code=int(exc.code),
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            requires_browser_hint=False,
            adapter_required=True,
            fallback_available=False,
            records_sampled=None,
            message=str(exc.reason),
        )
    except (URLError, TimeoutError, OSError) as exc:
        return SourceAuditResult(
            source_id=source_id,
            name=name,
            url=page_url,
            source_type=source_type,
            scope_id=scope_id,
            scope_name=scope_name,
            method="POST",
            status="FAILED",
            status_code=None,
            content_type=None,
            requires_browser_hint=False,
            adapter_required=True,
            fallback_available=False,
            records_sampled=None,
            message=str(exc),
        )


def _static_result(
    source_id: str,
    name: str,
    url: str,
    source_type: str,
    scope_id: str | None,
    scope_name: str | None,
    status: str,
    message: str,
    *,
    adapter_required: bool,
) -> SourceAuditResult:
    return SourceAuditResult(
        source_id=source_id,
        name=name,
        url=url,
        source_type=source_type,
        scope_id=scope_id,
        scope_name=scope_name,
        method="NONE",
        status=status,
        status_code=None,
        content_type=None,
        requires_browser_hint=False,
        adapter_required=adapter_required,
        fallback_available=False,
        records_sampled=None,
        message=message,
    )


def _requires_browser(body: str) -> bool:
    lowered = body.lower()
    return any(
        marker in lowered
        for marker in (
            "requires a javascript enabled browser",
            "adfloopbackutils",
            "captcha",
            "__next_data__",
        )
    )


def _summary(results: list[SourceAuditResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "reachable": sum(1 for result in results if result.status in {"REACHABLE", "ADAPTER_READY"}),
        "failed": sum(1 for result in results if result.status in {"FAILED", "HTTP_ERROR"}),
        "adapter_required": sum(1 for result in results if result.adapter_required),
        "templates": sum(1 for result in results if result.status == "TEMPLATE_REQUIRES_IDENTIFIER"),
        "failed_with_fallback": sum(
            1
            for result in results
            if result.status in {"FAILED", "HTTP_ERROR"} and result.fallback_available
        ),
        "unresolved_blockers": sum(
            1
            for result in results
            if result.adapter_required and not result.fallback_available
        ),
    }


def _mark_scope_fallbacks(results: list[SourceAuditResult]) -> list[SourceAuditResult]:
    has_reachable = any(result.status in {"REACHABLE", "ADAPTER_READY"} for result in results)
    if not has_reachable:
        return results
    marked = []
    for result in results:
        if result.status in {"FAILED", "HTTP_ERROR"}:
            data = result.to_dict()
            data["fallback_available"] = True
            data["adapter_required"] = False
            data["message"] = f"{result.message}; scope fallback source is reachable."
            marked.append(SourceAuditResult(**data))
        else:
            marked.append(result)
    return marked


def _json_content_count(raw: str) -> int:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw.count('"referenceNumber"')
    content = payload.get("content") if isinstance(payload, dict) else None
    return len(content) if isinstance(content, list) else 0


def _failure_message(message: str, known_adapter: str | None) -> str:
    if known_adapter:
        return f"{message}; existing adapter available for retry: {known_adapter}."
    return message


def _known_adapter(source_id: str) -> str | None:
    adapters = {
        "eshidis_active_search": "sources discover-active",
        "eshidis_tender_page": "sources fetch-resource",
    }
    return adapters.get(source_id)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:180]
