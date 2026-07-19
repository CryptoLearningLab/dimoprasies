from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from tender_radar.documents import analyze_document
from tender_radar.sources.kimdis_fetch import extract_eshidis_ids_from_text


KIMDIS_OPEN_DATA_BASE_URL = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/"


@dataclass(frozen=True)
class KimdisConnectedAttachment:
    reference_number: str
    act_type: str
    attachment_url: str
    local_path: str | None
    content_type: str | None
    size_bytes: int | None
    text_path: str | None
    linked_eshidis_ids: list[str]
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KimdisConnectedActsResult:
    official_id: str
    checked_at: str
    chain_url: str
    chain_status: str
    chain: dict[str, list[str]]
    attachment_results: list[KimdisConnectedAttachment]
    linked_eshidis_ids: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["attachment_results"] = [item.to_dict() for item in self.attachment_results]
        return payload


def connected_acts_chain_url(reference_number: str, *, base_url: str = KIMDIS_OPEN_DATA_BASE_URL) -> str:
    return urljoin(base_url.rstrip("/") + "/", f"adamChain/{reference_number.strip()}")


def connected_attachment_url(
    reference_number: str,
    *,
    base_url: str = KIMDIS_OPEN_DATA_BASE_URL,
) -> str | None:
    normalized = reference_number.upper()
    endpoint = None
    for prefix, candidate_endpoint in (
        ("26REQ", "request"),
        ("26PROC", "notice"),
        ("26AWRD", "auction"),
        ("26SYMV", "contract"),
        ("26PAY", "payment"),
    ):
        if normalized.startswith(prefix):
            endpoint = candidate_endpoint
            break
    if not endpoint:
        return None
    return urljoin(base_url.rstrip("/") + "/", f"{endpoint}/attachment/{reference_number}")


def parse_connected_acts_chain(payload: bytes | str | dict[str, Any]) -> dict[str, list[str]]:
    if isinstance(payload, bytes):
        raw: Any = json.loads(payload.decode("utf-8", "replace"))
    elif isinstance(payload, str):
        raw = json.loads(payload)
    else:
        raw = payload
    if not isinstance(raw, dict):
        return {}
    chain: dict[str, list[str]] = {}
    for key in ("requests", "approvedRequests", "notices", "auctions", "contracts", "payments"):
        values = raw.get(key)
        if not isinstance(values, list):
            chain[key] = []
            continue
        chain[key] = [str(value).strip() for value in values if str(value or "").strip()]
    return chain


def fetch_kimdis_connected_acts(
    official_id: str,
    *,
    download_dir: Path,
    text_dir: Path | None = None,
    timeout_seconds: int = 30,
    allow_insecure_tls: bool = False,
    max_attachments: int = 12,
    base_url: str = KIMDIS_OPEN_DATA_BASE_URL,
) -> KimdisConnectedActsResult:
    checked_at = datetime.now(timezone.utc).isoformat()
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    chain_url = connected_acts_chain_url(official_id, base_url=base_url)
    errors: list[str] = []
    chain: dict[str, list[str]] = {}
    attachment_results: list[KimdisConnectedAttachment] = []
    try:
        request = Request(
            chain_url,
            headers={"User-Agent": "TenderRadar/0.1 kimdis-connected-acts", "Accept": "application/json"},
            method="GET",
        )
        with urlopen(request, timeout=timeout_seconds, context=context) as response:
            chain = parse_connected_acts_chain(response.read())
    except Exception as exc:  # pragma: no cover - defensive HTTP boundary
        errors.append(f"adamChain fetch failed: {exc}")
        return KimdisConnectedActsResult(
            official_id=official_id,
            checked_at=checked_at,
            chain_url=chain_url,
            chain_status="FETCH_FAILED",
            chain=chain,
            attachment_results=[],
            linked_eshidis_ids=[],
            errors=errors,
        )

    linked_ids = extract_eshidis_ids_from_text(chain_url, json.dumps(chain, ensure_ascii=False))
    references = connected_references(chain)
    download_dir.mkdir(parents=True, exist_ok=True)
    if text_dir:
        text_dir.mkdir(parents=True, exist_ok=True)
    for reference_number, act_type in references[: max(0, max_attachments)]:
        attachment_url = connected_attachment_url(reference_number, base_url=base_url)
        if not attachment_url:
            attachment_results.append(
                KimdisConnectedAttachment(
                    reference_number=reference_number,
                    act_type=act_type,
                    attachment_url="",
                    local_path=None,
                    content_type=None,
                    size_bytes=None,
                    text_path=None,
                    linked_eshidis_ids=[],
                    error="Unsupported KIMDIS reference type.",
                )
            )
            continue
        attachment = _fetch_connected_attachment(
            reference_number,
            act_type,
            attachment_url,
            download_dir=download_dir,
            text_dir=text_dir,
            timeout_seconds=timeout_seconds,
            context=context,
        )
        attachment_results.append(attachment)
        for eshidis_id in attachment.linked_eshidis_ids:
            if eshidis_id not in linked_ids:
                linked_ids.append(eshidis_id)

    return KimdisConnectedActsResult(
        official_id=official_id,
        checked_at=checked_at,
        chain_url=chain_url,
        chain_status="FETCHED",
        chain=chain,
        attachment_results=attachment_results,
        linked_eshidis_ids=linked_ids,
        errors=errors,
    )


def connected_references(chain: dict[str, list[str]]) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    for act_type in ("notices", "requests", "approvedRequests", "auctions", "contracts", "payments"):
        for reference_number in chain.get(act_type, []):
            item = (reference_number, act_type)
            if item not in ordered:
                ordered.append(item)
    return ordered


def _fetch_connected_attachment(
    reference_number: str,
    act_type: str,
    attachment_url: str,
    *,
    download_dir: Path,
    text_dir: Path | None,
    timeout_seconds: int,
    context: ssl.SSLContext | None,
) -> KimdisConnectedAttachment:
    try:
        request = Request(
            attachment_url,
            headers={"User-Agent": "TenderRadar/0.1 kimdis-connected-acts", "Accept": "*/*"},
            method="GET",
        )
        with urlopen(request, timeout=timeout_seconds, context=context) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type")
    except Exception as exc:  # pragma: no cover - defensive HTTP boundary
        return KimdisConnectedAttachment(
            reference_number=reference_number,
            act_type=act_type,
            attachment_url=attachment_url,
            local_path=None,
            content_type=None,
            size_bytes=None,
            text_path=None,
            linked_eshidis_ids=[],
            error=str(exc),
        )

    target_path = download_dir / f"{reference_number}{_extension_for_content_type(content_type)}"
    target_path.write_bytes(content)
    text_path: str | None = None
    raw_text = content.decode("utf-8", "replace")
    linked_ids = extract_eshidis_ids_from_text(reference_number, attachment_url, raw_text)
    try:
        analysis = analyze_document(target_path, original_name=target_path.name)
        for eshidis_id in extract_eshidis_ids_from_text(reference_number, attachment_url, analysis.full_text):
            if eshidis_id not in linked_ids:
                linked_ids.append(eshidis_id)
        if text_dir and analysis.full_text:
            artifact = text_dir / f"{reference_number}.txt"
            artifact.write_text(analysis.full_text, encoding="utf-8")
            text_path = str(artifact)
    except Exception as exc:  # pragma: no cover - document libraries differ by host
        return KimdisConnectedAttachment(
            reference_number=reference_number,
            act_type=act_type,
            attachment_url=attachment_url,
            local_path=str(target_path),
            content_type=content_type,
            size_bytes=len(content),
            text_path=text_path,
            linked_eshidis_ids=linked_ids,
            error=f"Document analysis failed: {exc}",
        )
    return KimdisConnectedAttachment(
        reference_number=reference_number,
        act_type=act_type,
        attachment_url=attachment_url,
        local_path=str(target_path),
        content_type=content_type,
        size_bytes=len(content),
        text_path=text_path,
        linked_eshidis_ids=linked_ids,
        error=None,
    )


def _extension_for_content_type(content_type: str | None) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "application/json": ".json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
    }.get(normalized, ".bin")
