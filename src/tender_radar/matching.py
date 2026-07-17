from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from tender_radar.config import load_config
from tender_radar.db import SearchableDocument


@dataclass(frozen=True)
class SearchProfile:
    profile_id: str
    name: str
    include_document_types: set[str]
    exact_phrases: tuple[str, ...]
    optional_terms: tuple[str, ...]
    revision_codes: tuple[str, ...]
    minimum_confidence: float


@dataclass(frozen=True)
class MatchResult:
    tender_id: int
    eshidis_id: str | None
    tender_title: str
    document_id: int
    document_type: str
    original_name: str
    local_path: str | None
    match_type: str
    term: str
    confidence: float
    context: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_search_profile(path: Path) -> SearchProfile:
    data = load_config(path)
    profile = data.get("profile", {}) if isinstance(data, dict) else {}
    document_types = data.get("document_types", {}) if isinstance(data, dict) else {}
    terms = data.get("terms", {}) if isinstance(data, dict) else {}
    codes = data.get("codes", {}) if isinstance(data, dict) else {}
    matching = data.get("matching", {}) if isinstance(data, dict) else {}
    return SearchProfile(
        profile_id=str(profile.get("id") or path.stem),
        name=str(profile.get("name") or path.stem),
        include_document_types=set(_string_list(document_types.get("include"))),
        exact_phrases=tuple(_string_list(terms.get("exact_phrases"))),
        optional_terms=tuple(_string_list(terms.get("optional_terms"))),
        revision_codes=tuple(_string_list(codes.get("revision_codes"))),
        minimum_confidence=float(matching.get("minimum_confidence") or 0.60),
    )


def match_profile(profile: SearchProfile, documents: list[SearchableDocument]) -> list[MatchResult]:
    results: list[MatchResult] = []
    for document in documents:
        if profile.include_document_types and document.document_type not in profile.include_document_types:
            continue
        results.extend(_match_terms(document, profile.exact_phrases, "exact_phrase", 0.90))
        results.extend(_match_terms(document, profile.optional_terms, "optional_term", 0.65))
        results.extend(_match_terms(document, profile.revision_codes, "revision_code", 0.60))
    return _dedupe_matches([result for result in results if result.confidence >= profile.minimum_confidence])


def render_search_markdown(profile: SearchProfile, matches: list[MatchResult]) -> str:
    lines = [
        "# Search Report",
        "",
        f"- Profile: `{profile.profile_id}` - {profile.name}",
        f"- Matches: `{len(matches)}`",
        "",
    ]
    if not matches:
        lines.append("_No matches found._")
        return "\n".join(lines)
    lines.extend(["| Confidence | Type | Document | Term |", "| ---: | --- | --- | --- |"])
    for match in matches:
        lines.append(
            f"| {match.confidence:.2f} | `{match.match_type}` | {match.original_name} | `{match.term}` |"
        )
    lines.extend(["", "## Evidence", ""])
    for index, match in enumerate(matches, start=1):
        lines.extend(
            [
                f"### {index}. {match.original_name}",
                "",
                f"- ESHIDIS: `{match.eshidis_id}`",
                f"- Document type: `{match.document_type}`",
                f"- Match: `{match.term}`",
                f"- Confidence: `{match.confidence:.2f}`",
                "",
                match.context,
                "",
            ]
        )
    return "\n".join(lines)


def _match_terms(
    document: SearchableDocument,
    terms: tuple[str, ...],
    match_type: str,
    confidence: float,
) -> list[MatchResult]:
    text = _document_text(document)
    normalized_text = _normalize(text)
    results = []
    for term in terms:
        normalized_term = _normalize(term)
        if not normalized_term:
            continue
        index = normalized_text.find(normalized_term)
        if index == -1:
            continue
        results.append(
            MatchResult(
                tender_id=document.tender_id,
                eshidis_id=document.eshidis_id,
                tender_title=document.tender_title,
                document_id=document.document_id,
                document_type=document.document_type,
                original_name=document.original_name,
                local_path=document.local_path,
                match_type=match_type,
                term=term,
                confidence=confidence,
                context=_context(text, index, len(normalized_term)),
            )
        )
    return results


def _dedupe_matches(matches: list[MatchResult]) -> list[MatchResult]:
    deduped: list[MatchResult] = []
    for match in matches:
        similar_index = next(
            (
                index
                for index, existing in enumerate(deduped)
                if existing.document_id == match.document_id
                and existing.match_type == match.match_type
                and _contexts_similar(existing.context, match.context)
            ),
            None,
        )
        if similar_index is None:
            deduped.append(match)
        elif _rank(match) > _rank(deduped[similar_index]):
            deduped[similar_index] = match
    return sorted(deduped, key=lambda item: (-item.confidence, item.document_id, item.term))


def _rank(match: MatchResult) -> tuple[float, int]:
    return (match.confidence, len(match.term))


def _contexts_similar(left: str, right: str) -> bool:
    left_words = set(_normalize(left).split())
    right_words = set(_normalize(right).split())
    if not left_words or not right_words:
        return False
    overlap = len(left_words & right_words)
    return overlap / min(len(left_words), len(right_words)) >= 0.70


def _document_text(document: SearchableDocument) -> str:
    if document.text_path:
        path = Path(document.text_path)
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return document.text_sample or ""


def _context(text: str, normalized_index: int, term_length: int, radius: int = 180) -> str:
    # Normalization usually preserves length for Greek accents in our corpus; use this
    # as approximate evidence context, not as a byte-perfect locator.
    start = max(0, normalized_index - radius)
    end = min(len(text), normalized_index + term_length + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _normalize(value: str) -> str:
    lowered = value.lower().replace("_", " ")
    without_accents = str.maketrans("άέήίόύώϊΐϋΰ", "αεηιουωιιυυ")
    return re.sub(r"\s+", " ", lowered.translate(without_accents)).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]
