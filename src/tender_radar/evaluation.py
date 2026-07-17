from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from tender_radar.config import load_config
from tender_radar.db import SearchableDocument
from tender_radar.matching import _document_text, _normalize


@dataclass(frozen=True)
class EvaluationRule:
    rule_id: str
    label: str
    document_types: set[str]
    phrases: tuple[str, ...]
    numeric_operator: str | None
    numeric_threshold: float | None
    score: float
    severity: str


@dataclass(frozen=True)
class EvaluationProfile:
    profile_id: str
    name: str
    rules: tuple[EvaluationRule, ...]


@dataclass(frozen=True)
class EvaluationHit:
    rule_id: str
    label: str
    severity: str
    score: float
    tender_id: int
    eshidis_id: str | None
    tender_title: str
    document_id: int
    document_type: str
    original_name: str
    numeric_value: float | None
    context: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TenderEvaluation:
    tender_id: int
    eshidis_id: str | None
    tender_title: str
    total_score: float
    hit_count: int
    hits: tuple[EvaluationHit, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "tender_id": self.tender_id,
            "eshidis_id": self.eshidis_id,
            "tender_title": self.tender_title,
            "total_score": self.total_score,
            "hit_count": self.hit_count,
            "hits": [hit.to_dict() for hit in self.hits],
        }


def load_evaluation_profile(path: Path) -> EvaluationProfile:
    data = load_config(path)
    return evaluation_profile_from_config(data, path)


def evaluation_profile_from_config(data: Any, path: Path) -> EvaluationProfile:
    profile = data.get("profile", {}) if isinstance(data, dict) else {}
    rules_data = data.get("rules", []) if isinstance(data, dict) else []
    rules = []
    for index, item in enumerate(rules_data, start=1):
        if not isinstance(item, dict):
            continue
        numeric = item.get("numeric") if isinstance(item.get("numeric"), dict) else {}
        rules.append(
            EvaluationRule(
                rule_id=str(item.get("id") or f"rule_{index}"),
                label=str(item.get("label") or item.get("id") or f"Rule {index}"),
                document_types=set(_string_list(item.get("document_types"))),
                phrases=tuple(_string_list(item.get("phrases"))),
                numeric_operator=str(numeric.get("operator")) if numeric.get("operator") else None,
                numeric_threshold=float(numeric["threshold"]) if numeric.get("threshold") is not None else None,
                score=float(item.get("score") or 1.0),
                severity=str(item.get("severity") or "info"),
            )
        )
    return EvaluationProfile(
        profile_id=str(profile.get("id") or path.stem),
        name=str(profile.get("name") or path.stem),
        rules=tuple(rules),
    )


def normalize_evaluation_config(data: dict[str, Any], *, fallback_id: str) -> dict[str, Any]:
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    profile_id = _safe_identifier(str(profile.get("id") or fallback_id), fallback_id)
    normalized: dict[str, Any] = {
        "profile": {
            "id": profile_id,
            "name": str(profile.get("name") or profile_id).strip(),
            "description": str(profile.get("description") or "").strip(),
        },
        "rules": [],
    }
    rules = data.get("rules") if isinstance(data.get("rules"), list) else []
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            continue
        rule_id = _safe_identifier(str(item.get("id") or f"rule_{index}"), f"rule_{index}")
        phrases = _string_list(item.get("phrases"))
        if not phrases:
            continue
        rule: dict[str, Any] = {
            "id": rule_id,
            "label": str(item.get("label") or rule_id).strip(),
            "severity": str(item.get("severity") or "info").strip(),
            "score": float(item.get("score") or 1.0),
            "document_types": _string_list(item.get("document_types")),
            "phrases": phrases,
        }
        numeric = item.get("numeric") if isinstance(item.get("numeric"), dict) else {}
        operator = str(numeric.get("operator") or "").strip()
        threshold = numeric.get("threshold")
        if operator and threshold not in (None, ""):
            if operator not in {">", ">=", "<", "<=", "=", "=="}:
                raise ValueError(f"Unsupported numeric operator for {rule_id}: {operator}")
            rule["numeric"] = {"operator": operator, "threshold": float(threshold)}
        normalized["rules"].append(rule)
    return normalized


def save_evaluation_config(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_evaluation_config(data, fallback_id=path.stem)
    evaluation_profile_from_config(normalized, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_evaluation_yaml(normalized), encoding="utf-8")
    return normalized


def evaluate_documents(profile: EvaluationProfile, documents: list[SearchableDocument]) -> list[TenderEvaluation]:
    hits: list[EvaluationHit] = []
    for document in documents:
        for rule in profile.rules:
            if rule.document_types and document.document_type not in rule.document_types:
                continue
            hit = _evaluate_rule(rule, document)
            if hit:
                hits.append(hit)
    by_tender: dict[int, list[EvaluationHit]] = {}
    tender_meta: dict[int, tuple[str | None, str]] = {}
    for hit in hits:
        by_tender.setdefault(hit.tender_id, []).append(hit)
        tender_meta[hit.tender_id] = (hit.eshidis_id, hit.tender_title)
    evaluations = []
    for tender_id, tender_hits in by_tender.items():
        eshidis_id, title = tender_meta[tender_id]
        sorted_hits = tuple(sorted(tender_hits, key=lambda item: (-item.score, item.rule_id)))
        evaluations.append(
            TenderEvaluation(
                tender_id=tender_id,
                eshidis_id=eshidis_id,
                tender_title=title,
                total_score=round(sum(hit.score for hit in sorted_hits), 2),
                hit_count=len(sorted_hits),
                hits=sorted_hits,
            )
        )
    return sorted(evaluations, key=lambda item: (-item.total_score, item.eshidis_id or ""))


def render_evaluation_markdown(profile: EvaluationProfile, evaluations: list[TenderEvaluation]) -> str:
    lines = [
        "# Evaluation Report",
        "",
        f"- Profile: `{profile.profile_id}` - {profile.name}",
        f"- Tenders matched: `{len(evaluations)}`",
        "",
    ]
    if not evaluations:
        lines.append("_No evaluation hits found._")
        return "\n".join(lines) + "\n"
    lines.extend(["| Score | Hits | ESHIDIS | Title |", "| ---: | ---: | --- | --- |"])
    for item in evaluations:
        lines.append(
            f"| {item.total_score:.2f} | {item.hit_count} | `{item.eshidis_id or ''}` | {_markdown_cell(item.tender_title)} |"
        )
    lines.extend(["", "## Evidence", ""])
    for item in evaluations:
        lines.extend([f"### {item.eshidis_id or item.tender_id} - {item.tender_title}", ""])
        for hit in item.hits:
            value = "" if hit.numeric_value is None else f" numeric value `{hit.numeric_value:g}`"
            lines.extend(
                [
                    f"- `{hit.rule_id}` {hit.label}: +{hit.score:g} ({hit.severity}){value}",
                    f"  - Document: `{hit.document_type}` - {hit.original_name}",
                    f"  - Evidence: {hit.context}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def _evaluate_rule(rule: EvaluationRule, document: SearchableDocument) -> EvaluationHit | None:
    text = _document_text(document)
    if not text:
        return None
    normalized_text = _normalize(text)
    phrase_indexes = [_first_phrase_index(normalized_text, phrase) for phrase in rule.phrases]
    phrase_indexes = [index for index in phrase_indexes if index >= 0]
    if rule.phrases and not phrase_indexes:
        return None
    anchor = min(phrase_indexes) if phrase_indexes else 0
    context = _context(text, anchor)
    numeric_value = None
    if rule.numeric_operator and rule.numeric_threshold is not None:
        numeric_value = _best_number_near(context, anchor_text=rule.phrases[0] if rule.phrases else None)
        if numeric_value is None or not _compare(numeric_value, rule.numeric_operator, rule.numeric_threshold):
            return None
    return EvaluationHit(
        rule_id=rule.rule_id,
        label=rule.label,
        severity=rule.severity,
        score=rule.score,
        tender_id=document.tender_id,
        eshidis_id=document.eshidis_id,
        tender_title=document.tender_title,
        document_id=document.document_id,
        document_type=document.document_type,
        original_name=document.original_name,
        numeric_value=numeric_value,
        context=context,
    )


def _first_phrase_index(normalized_text: str, phrase: str) -> int:
    return normalized_text.find(_normalize(phrase))


def _context(text: str, index: int, radius: int = 260) -> str:
    start = max(0, index - radius)
    end = min(len(text), index + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _best_number_near(text: str, *, anchor_text: str | None = None) -> float | None:
    search_text = text
    if anchor_text:
        normalized = _normalize(text)
        anchor_index = normalized.find(_normalize(anchor_text))
        if anchor_index >= 0:
            search_text = text[anchor_index:]
    decimal_matches = list(re.finditer(r"\d+[,.]\d+", search_text))
    decimal_values = [_parse_greek_number(match.group(0)) for match in decimal_matches]
    decimal_values = [value for value in decimal_values if value is not None and 0 < value < 1000]
    if decimal_values:
        return min(decimal_values)
    numbers = [_parse_greek_number(match.group(0)) for match in re.finditer(r"\d+(?:[.,]\d+)*", search_text)]
    numbers = [number for number in numbers if number is not None and 0 < number < 1000]
    return min(numbers) if numbers else None


def _parse_greek_number(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _compare(left: float, operator: str, right: float) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator in {"=", "=="}:
        return left == right
    raise ValueError(f"Unsupported numeric operator: {operator}")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:180]


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
    return cleaned or fallback


def _dump_evaluation_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _dump_evaluation_yaml_simple(data)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _dump_evaluation_yaml_simple(data: dict[str, Any]) -> str:
    profile = data["profile"]
    lines = [
        "profile:",
        f"  id: {_yaml_scalar(profile['id'])}",
        f"  name: {_yaml_scalar(profile['name'])}",
    ]
    description = profile.get("description")
    if description:
        lines.extend(["  description: >", f"    {description}"])
    lines.extend(["", "rules:"])
    for rule in data["rules"]:
        lines.extend(
            [
                f"  - id: {_yaml_scalar(rule['id'])}",
                f"    label: {_yaml_scalar(rule['label'])}",
                f"    severity: {_yaml_scalar(rule['severity'])}",
                f"    score: {rule['score']}",
            ]
        )
        document_types = rule.get("document_types") or []
        if document_types:
            lines.append("    document_types:")
            lines.extend([f"      - {_yaml_scalar(item)}" for item in document_types])
        else:
            lines.append("    document_types: []")
        lines.append("    phrases:")
        lines.extend([f"      - {_yaml_scalar(item)}" for item in rule["phrases"]])
        numeric = rule.get("numeric")
        if numeric:
            lines.extend(
                [
                    "    numeric:",
                    f"      operator: {_yaml_scalar(numeric['operator'])}",
                    f"      threshold: {numeric['threshold']}",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _yaml_scalar(value: object) -> str:
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
