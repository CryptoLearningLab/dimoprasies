from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_MODEL = "gpt-4.1-mini"
RESPONSES_URL = "https://api.openai.com/v1/responses"

KEEP_DECISIONS = {"KEEP_ACTIVE_TENDER", "REVIEW_TENDER_CANDIDATE", "EARLY_SIGNAL"}

PUBLIC_WORKS_TERMS = (
    "εργο",
    "εργασι",
    "οδοποι",
    "ασφαλ",
    "αναπλα",
    "κατασκευ",
    "επισκευ",
    "συντηρη",
    "αποκαταστα",
    "τεχνικ",
    "διακηρυ",
    "τευχ",
    "προυπολογισ",
    "μελετη",
    "υποβολη προσφορ",
    "δημοσια συμβασ",
)

ADMIN_DROP_TERMS = (
    "κανονισμος λειτουργιας",
    "αποφαση γενικου διευθυντη",
    "ανακοινωση σοχ",
    "προσληψη προσωπικου",
    "προγραμμα εκλογων",
    "εντολη μισθωσης",
    "νεος προεδρος",
    "συνεδριαση",
    "εκτος εδρας",
    "ορισμος αντιδημαρχ",
)

SUPPLY_SERVICE_DROP_TERMS = (
    "εκπαιδευση",
    "εξομοιωτ",
    "flight simulator",
    "κλιβανος",
    "αποστειρωση",
    "πλυντηριο χειρουργικ",
    "τροφ",
    "φαρμακ",
)


@dataclass(frozen=True)
class DeterministicSignals:
    has_eshidis_id: bool
    has_kimdis_proc_id: bool
    has_document_links: bool
    public_works_terms: list[str]
    admin_drop_terms: list[str]
    supply_service_drop_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_eshidis_id": self.has_eshidis_id,
            "has_kimdis_proc_id": self.has_kimdis_proc_id,
            "has_document_links": self.has_document_links,
            "public_works_terms": self.public_works_terms,
            "admin_drop_terms": self.admin_drop_terms,
            "supply_service_drop_terms": self.supply_service_drop_terms,
        }


def build_ai_triage_report(
    rows: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    batch_size: int = 20,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive.")
    key = api_key or load_openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY was not found in the environment or .env.local.")
    model_name = model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    prepared = [_triage_input(row) for row in rows]
    classifications: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index in range(0, len(prepared), batch_size):
        batch = prepared[index : index + batch_size]
        try:
            classifications.extend(
                classify_batch_with_openai(batch, api_key=key, model=model_name, timeout_seconds=timeout_seconds)
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"batch_start": index, "batch_size": len(batch), "message": str(exc)})
    by_key = {str(item.get("row_key") or ""): item for item in classifications}
    rows_out = []
    for item in prepared:
        row_key = str(item.get("row_key") or "")
        classification = by_key.get(row_key) or {
            "row_key": row_key,
            "decision": "REVIEW_TENDER_CANDIDATE",
            "confidence": 0.0,
            "reason": "AI classification missing; keep for human review.",
            "eshidis_id_candidates": [],
        }
        rows_out.append({**item, "ai": _normalize_classification(classification)})
    summary = _summary(rows_out, errors)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "input_rows": len(rows),
        "summary": summary,
        "rows": rows_out,
        "errors": errors,
        "safety_note": (
            "AI triage is advisory. It must not promote candidates to VERIFIED_ACTIVE "
            "or delete provenance/source records."
        ),
    }


def classify_batch_with_openai(
    batch: list[dict[str, Any]],
    *,
    api_key: str,
    model: str,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    prompt = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": _prompt_text(batch),
            }
        ],
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You classify Greek public procurement discovery rows for a contractor dashboard. "
                            "Return strict JSON only. Never mark verified active. Prefer REVIEW when uncertain."
                        ),
                    }
                ],
            },
            prompt,
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "tender_radar_ai_triage",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "row_key": {"type": "string"},
                                    "decision": {
                                        "type": "string",
                                        "enum": [
                                            "KEEP_ACTIVE_TENDER",
                                            "REVIEW_TENDER_CANDIDATE",
                                            "EARLY_SIGNAL",
                                            "DROP_ADMIN",
                                            "DROP_OUT_OF_SCOPE_SUPPLY_SERVICE",
                                            "DROP_NOT_PUBLIC_WORKS",
                                        ],
                                    },
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                    "reason": {"type": "string"},
                                    "eshidis_id_candidates": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": [
                                    "row_key",
                                    "decision",
                                    "confidence",
                                    "reason",
                                    "eshidis_id_candidates",
                                ],
                            },
                        }
                    },
                    "required": ["classifications"],
                },
            }
        },
        "temperature": 0,
        "max_output_tokens": 6000,
    }
    request = Request(
        RESPONSES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8", errors="replace"))
    text = _response_text(response_payload)
    parsed = json.loads(_strip_json_fence(text))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("classifications"), list):
        raise ValueError("OpenAI response did not include classifications array.")
    return [item for item in parsed["classifications"] if isinstance(item, dict)]


def load_openai_api_key(env_path: Path | None = None) -> str | None:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    path = env_path or Path.cwd() / ".env.local"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "OPENAI_API_KEY" and value.strip():
            return value.strip().strip("'\"")
    return None


def write_ai_triage_report(report: dict[str, Any], report_path: Path, markdown_path: Path | None = None) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_ai_triage_markdown(report), encoding="utf-8")


def render_ai_triage_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# AI Discovery Triage Report",
        "",
        f"- Generated at: `{report.get('generated_at')}`",
        f"- Model: `{report.get('model')}`",
        f"- Input rows: `{report.get('input_rows')}`",
        f"- Keep/review/early signal: `{summary.get('kept_total', 0)}`",
        f"- Drop: `{summary.get('dropped_total', 0)}`",
        f"- Errors: `{summary.get('errors', 0)}`",
        "- Safety: AI triage is advisory; provenance is retained and status verification remains separate.",
        "",
        "| Decision | Confidence | Id | Source | Title | Authority | Reason | ESHIDIS hints |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        ai = row.get("ai") if isinstance(row.get("ai"), dict) else {}
        lines.append(
            "| {decision} | {confidence} | `{row_key}` | {source} | {title} | {authority} | {reason} | {eshidis} |".format(
                decision=_cell(ai.get("decision") or ""),
                confidence=_cell(ai.get("confidence") or ""),
                row_key=_cell(row.get("row_key") or ""),
                source=_cell(row.get("source_label") or row.get("source") or ""),
                title=_cell(row.get("title") or ""),
                authority=_cell(row.get("authority_name") or row.get("authority") or ""),
                reason=_cell(ai.get("reason") or ""),
                eshidis=_cell(", ".join(str(value) for value in ai.get("eshidis_id_candidates") or [])),
            )
        )
    return "\n".join(lines) + "\n"


def _triage_input(row: dict[str, Any]) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("eshidis_id") or row.get("official_id") or row.get("display_id") or "")
    text = " ".join(
        str(row.get(key) or "")
        for key in (
            "official_id",
            "display_id",
            "source_label",
            "record_type",
            "authority_record_type",
            "title",
            "authority_name",
            "authority",
            "region",
            "status",
            "published_at",
            "current_deadline_at",
            "submission_deadline",
            "official_url",
            "attachment_url",
            "interest_reason",
            "row_text",
        )
    )
    signals = deterministic_signals(row, text)
    return {
        "row_key": row_key,
        "display_id": row.get("display_id") or row.get("official_id") or row.get("eshidis_id"),
        "source": row.get("source"),
        "source_label": row.get("source_label") or row.get("source"),
        "record_type": row.get("record_type") or row.get("authority_record_type"),
        "title": row.get("title"),
        "authority_name": row.get("authority_name") or row.get("authority"),
        "deadline": row.get("current_deadline_at") or row.get("submission_deadline"),
        "budget": row.get("budget_with_vat") or row.get("budget"),
        "official_url": row.get("official_url") or row.get("source_url"),
        "attachment_urls_count": len(row.get("attachment_urls") or []),
        "deterministic_signals": signals.to_dict(),
        "text_sample": text[:1200],
    }


def deterministic_signals(row: dict[str, Any], text: str | None = None) -> DeterministicSignals:
    combined = _normalize(text or json.dumps(row, ensure_ascii=False))
    official_id = str(row.get("official_id") or row.get("display_id") or row.get("eshidis_id") or "")
    attachment_urls = row.get("attachment_urls") if isinstance(row.get("attachment_urls"), list) else []
    return DeterministicSignals(
        has_eshidis_id=bool(re.search(r"\b\d{5,7}\b", official_id)) or "eshidis" in combined or "εσηδης" in combined,
        has_kimdis_proc_id=bool(re.search(r"\b\d{2}proc\d{9}\b", official_id.casefold()))
        or bool(re.search(r"\b\d{2}proc\d{9}\b", combined)),
        has_document_links=bool(attachment_urls or row.get("attachment_url") or ".pdf" in combined or ".zip" in combined),
        public_works_terms=[term for term in PUBLIC_WORKS_TERMS if term in combined],
        admin_drop_terms=[term for term in ADMIN_DROP_TERMS if term in combined],
        supply_service_drop_terms=[term for term in SUPPLY_SERVICE_DROP_TERMS if term in combined],
    )


def _prompt_text(batch: list[dict[str, Any]]) -> str:
    return (
        "Classify each row for a Greek public works contractor's daily dashboard.\n"
        "Decisions:\n"
        "- KEEP_ACTIVE_TENDER: looks like a current tender/procurement row for public works or technical works.\n"
        "- REVIEW_TENDER_CANDIDATE: may be a tender/public works row but evidence is incomplete.\n"
        "- EARLY_SIGNAL: a decision/announcement that may precede a future public works tender, but is not currently a tender.\n"
        "- DROP_ADMIN: administrative/news/personnel/elections/meeting row, not a tender.\n"
        "- DROP_OUT_OF_SCOPE_SUPPLY_SERVICE: procurement is supplies/services unrelated to construction/public works.\n"
        "- DROP_NOT_PUBLIC_WORKS: not a public works opportunity for contractors.\n"
        "Return JSON object exactly: {\"classifications\":[{\"row_key\":\"...\",\"decision\":\"...\","
        "\"confidence\":0.0,\"reason\":\"short Greek reason\",\"eshidis_id_candidates\":[\"221744\"]}]}.\n"
        "Do not invent ESHIDIS ids. Extract only explicit 5-7 digit ESHIDIS-like ids when text/link context supports it.\n"
        "Rows:\n"
        f"{json.dumps(batch, ensure_ascii=False)}"
    )


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for output in payload.get("output") or []:
        if not isinstance(output, dict):
            continue
        for content in output.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    text = "".join(parts).strip()
    if not text:
        raise ValueError("OpenAI response contained no text.")
    return text


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def _normalize_classification(item: dict[str, Any]) -> dict[str, Any]:
    decision = str(item.get("decision") or "REVIEW_TENDER_CANDIDATE").strip()
    if decision not in {
        "KEEP_ACTIVE_TENDER",
        "REVIEW_TENDER_CANDIDATE",
        "EARLY_SIGNAL",
        "DROP_ADMIN",
        "DROP_OUT_OF_SCOPE_SUPPLY_SERVICE",
        "DROP_NOT_PUBLIC_WORKS",
    }:
        decision = "REVIEW_TENDER_CANDIDATE"
    try:
        confidence = float(item.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    hints = [str(value) for value in item.get("eshidis_id_candidates") or [] if re.fullmatch(r"\d{5,7}", str(value))]
    return {
        "decision": decision,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(item.get("reason") or ""),
        "eshidis_id_candidates": list(dict.fromkeys(hints)),
        "keep_for_daily_review": decision in KEEP_DECISIONS,
    }


def _summary(rows: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    kept = 0
    dropped = 0
    for row in rows:
        ai = row.get("ai") if isinstance(row.get("ai"), dict) else {}
        decision = str(ai.get("decision") or "REVIEW_TENDER_CANDIDATE")
        counts[decision] = counts.get(decision, 0) + 1
        if ai.get("keep_for_daily_review"):
            kept += 1
        else:
            dropped += 1
    return {"decisions": counts, "kept_total": kept, "dropped_total": dropped, "errors": len(errors)}


def _normalize(value: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", without_accents)


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:180]
