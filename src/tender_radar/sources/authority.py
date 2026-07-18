from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import html as html_lib
from html.parser import HTMLParser
import hashlib
import json
import re
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DOCUMENT_EXTENSIONS = (".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods")


@dataclass(frozen=True)
class AuthorityCandidate:
    source_id: str
    source_name: str
    scope_id: str | None
    scope_name: str | None
    source_family: str
    adapter: str
    official_id: str
    record_type: str
    title: str | None
    authority: str | None
    published_at: str | None
    submission_deadline: str | None
    source_url: str
    detail_url: str | None
    attachment_url: str | None
    attachment_urls: list[str]
    retrieved_at: str
    parser_status: str
    status: str
    status_reason: str
    row_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def discover_authority_candidates(
    config: dict[str, Any],
    *,
    timeout_seconds: int = 20,
    allow_insecure_tls: bool = False,
    limit_per_source: int = 20,
    source_ids: set[str] | None = None,
) -> tuple[list[AuthorityCandidate], list[dict[str, object]], list[dict[str, object]]]:
    candidates: list[AuthorityCandidate] = []
    errors: list[dict[str, object]] = []
    source_pages: list[dict[str, object]] = []
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    for source in config.get("authority_adapters") or []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "")
        if source_ids is not None and source_id not in source_ids:
            continue
        adapter = str(source.get("adapter") or "")
        url = str(source.get("url") or "")
        try:
            parsed = _discover_one_source(
                source,
                timeout_seconds=timeout_seconds,
                context=context,
                limit=max(0, limit_per_source),
            )
            candidates.extend(parsed)
            source_pages.append(
                {
                    "source": source_id,
                    "adapter": adapter,
                    "url": url,
                    "items_returned": len(parsed),
                    "error": None,
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError) as exc:
            message = str(exc)
            errors.append({"source": source_id, "url": url, "message": message})
            source_pages.append(
                {
                    "source": source_id,
                    "adapter": adapter,
                    "url": url,
                    "items_returned": None,
                    "error": message,
                }
            )
    return candidates, errors, source_pages


def _discover_one_source(
    source: dict[str, Any],
    *,
    timeout_seconds: int,
    context: ssl.SSLContext | None,
    limit: int,
) -> list[AuthorityCandidate]:
    adapter = str(source.get("adapter") or "")
    url = _source_url_with_query(source)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    if adapter == "drupal_listing":
        html = _fetch_text(url, timeout_seconds=timeout_seconds, context=context)
        return _parse_drupal_listing(
            source,
            html,
            source_url=url,
            retrieved_at=retrieved_at,
            timeout_seconds=timeout_seconds,
            context=context,
            limit=limit,
        )
    if adapter == "wordpress_category":
        payload = _fetch_json(url, timeout_seconds=timeout_seconds, context=context)
        return _parse_wordpress_posts(source, payload, source_url=url, retrieved_at=retrieved_at, limit=limit)
    if adapter == "wordpress_page_table":
        payload = _fetch_json(url, timeout_seconds=timeout_seconds, context=context)
        return _parse_wordpress_page_table(source, payload, source_url=url, retrieved_at=retrieved_at, limit=limit)
    if adapter == "html_listing":
        html = _fetch_text(url, timeout_seconds=timeout_seconds, context=context)
        return _parse_html_listing(
            source,
            html,
            source_url=url,
            retrieved_at=retrieved_at,
            timeout_seconds=timeout_seconds,
            context=context,
            limit=limit,
        )
    if adapter == "diavgeia_api":
        payload = _fetch_json(url, timeout_seconds=timeout_seconds, context=context)
        return _parse_diavgeia(source, payload, source_url=url, retrieved_at=retrieved_at, limit=limit)
    if adapter == "ted_api":
        payload = _post_json(
            url,
            source.get("body") if isinstance(source.get("body"), dict) else {},
            timeout_seconds=timeout_seconds,
            context=context,
        )
        return _parse_ted(source, payload, source_url=url, retrieved_at=retrieved_at, limit=limit)
    raise ValueError(f"Unsupported authority adapter: {adapter}")


def _source_url_with_query(source: dict[str, Any]) -> str:
    url = str(source.get("url") or "")
    params = source.get("query_params")
    if not isinstance(params, dict) or not params:
        return url
    return f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"


def _parse_drupal_listing(
    source: dict[str, Any],
    html: str,
    *,
    source_url: str,
    retrieved_at: str,
    timeout_seconds: int,
    context: ssl.SSLContext | None,
    limit: int,
) -> list[AuthorityCandidate]:
    parser = DrupalListingParser(source_url)
    parser.feed(html)
    items = parser.items[:limit] if limit else []
    candidates: list[AuthorityCandidate] = []
    for item in items:
        detail_url = item.get("detail_url")
        detail_html = ""
        detail_links: list[str] = []
        if detail_url:
            try:
                detail_html = _fetch_text(detail_url, timeout_seconds=timeout_seconds, context=context)
                detail_parser = LinkCollector(detail_url)
                detail_parser.feed(detail_html)
                detail_links = detail_parser.document_links
            except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError):
                detail_html = ""
                detail_links = []
        attachment_urls = _dedupe([*item.get("attachment_urls", []), *detail_links])
        row_text = _clean_text(" ".join([str(item.get("title") or ""), str(item.get("published_at") or ""), detail_html[:5000]]))
        official_id, record_type = _official_reference(row_text, detail_url or source_url)
        candidates.append(
            AuthorityCandidate(
                source_id=str(source.get("id") or ""),
                source_name=str(source.get("name") or source.get("id") or ""),
                scope_id=_none_or_str(source.get("scope_id")),
                scope_name=_none_or_str(source.get("scope_name")),
                source_family=str(source.get("source_family") or "authority_html"),
                adapter=str(source.get("adapter") or "drupal_listing"),
                official_id=official_id,
                record_type=record_type,
                title=_none_or_str(item.get("title")),
                authority=_none_or_str(source.get("scope_name")),
                published_at=_none_or_str(item.get("published_at")),
                submission_deadline=None,
                source_url=source_url,
                detail_url=detail_url,
                attachment_url=attachment_urls[0] if attachment_urls else None,
                attachment_urls=attachment_urls,
                retrieved_at=retrieved_at,
                parser_status="PARSED",
                status="AUTHORITY_DISCOVERY_CANDIDATE",
                status_reason=(
                    "Public authority page candidate only; official submission status must be verified "
                    "through ESHIDIS/KIMDIS or newer official acts."
                ),
                row_text=row_text,
            )
        )
    return candidates


class DrupalListingParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self._article_depth = 0
        self._current: dict[str, Any] | None = None
        self._capture_title = False
        self._capture_time = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "article":
            self._article_depth += 1
            if self._current is None:
                self._current = {"attachment_urls": [], "text": []}
            return
        if self._current is None:
            return
        if tag == "a":
            href = attrs_dict.get("href")
            if href:
                absolute = urljoin(self.base_url, href)
                if _document_url(absolute):
                    self._current["attachment_urls"].append(absolute)
                elif self._current.get("detail_url") is None:
                    self._current["detail_url"] = absolute
                    self._capture_title = True
                    self._text_parts = []
        if tag == "time":
            self._capture_time = True
            self._text_parts = []
            if attrs_dict.get("datetime"):
                self._current["published_at"] = attrs_dict["datetime"]

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._capture_title:
            text = _clean_text(" ".join(self._text_parts))
            if text and not self._current.get("title"):
                self._current["title"] = text
            self._capture_title = False
            self._text_parts = []
        if tag == "time" and self._capture_time:
            text = _clean_text(" ".join(self._text_parts))
            if text and not self._current.get("published_at"):
                self._current["published_at"] = text
            self._capture_time = False
            self._text_parts = []
        if tag == "article":
            self._article_depth = max(0, self._article_depth - 1)
            if self._article_depth == 0:
                if self._current.get("title") or self._current.get("detail_url") or self._current.get("attachment_urls"):
                    self.items.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _clean_text(data)
        if text:
            self._current.setdefault("text", []).append(text)
        if self._capture_title or self._capture_time:
            self._text_parts.append(data)


class LinkCollector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.document_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        absolute = urljoin(self.base_url, href)
        if _document_url(absolute):
            self.document_links.append(absolute)


class GenericListingParser(HTMLParser):
    CONTAINER_CLASS_HINTS = ("views-row", "premium-blog-post", "post", "article", "blog")

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self._depth = 0
        self._current: dict[str, Any] | None = None
        self._capture_link_text = False
        self._link_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = attrs_dict.get("class", "")
        is_container = tag in {"article", "li"} or any(hint in classes for hint in self.CONTAINER_CLASS_HINTS)
        if is_container:
            self._depth += 1
            if self._current is None:
                self._current = {"attachment_urls": [], "text": []}
        if self._current is None:
            return
        if tag == "a":
            href = attrs_dict.get("href")
            if not href:
                return
            absolute = urljoin(self.base_url, href)
            if _document_url(absolute):
                self._current["attachment_urls"].append(absolute)
            elif self._current.get("detail_url") is None:
                self._current["detail_url"] = absolute
                self._capture_link_text = True
                self._link_parts = []
        if tag == "time" and attrs_dict.get("datetime"):
            self._current["published_at"] = attrs_dict["datetime"]

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._capture_link_text:
            text = _clean_text(" ".join(self._link_parts))
            if text and not self._current.get("title"):
                self._current["title"] = text
            self._capture_link_text = False
            self._link_parts = []
        if tag in {"article", "li", "div"} and self._depth:
            self._depth -= 1
            if self._depth == 0:
                if self._current.get("title") or self._current.get("detail_url") or self._current.get("attachment_urls"):
                    self.items.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _clean_text(data)
        if text:
            self._current.setdefault("text", []).append(text)
        if self._capture_link_text:
            self._link_parts.append(data)


class TableRowParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self._in_row = False
        self._current: dict[str, Any] | None = None
        self._capture_link = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "tr":
            self._in_row = True
            self._current = {"attachment_urls": [], "text": []}
            return
        if not self._in_row or self._current is None:
            return
        if tag == "a":
            href = attrs_dict.get("href")
            if not href:
                return
            absolute = urljoin(self.base_url, href)
            if _document_url(absolute):
                self._current["attachment_urls"].append(absolute)
            elif self._current.get("detail_url") is None:
                self._current["detail_url"] = absolute
            self._capture_link = True
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._capture_link:
            text = _clean_text(" ".join(self._parts))
            if text and not self._current.get("title"):
                self._current["title"] = text
            self._capture_link = False
            self._parts = []
        if tag == "tr" and self._in_row:
            if self._current.get("title") or self._current.get("detail_url") or self._current.get("attachment_urls"):
                self.items.append(self._current)
            self._current = None
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _clean_text(data)
        if text:
            self._current.setdefault("text", []).append(text)
        if self._capture_link:
            self._parts.append(data)


def _fetch_text(url: str, *, timeout_seconds: int, context: ssl.SSLContext | None) -> str:
    request = Request(url, headers={"User-Agent": "TenderRadar/0.1 authority-discovery", "Accept": "text/html"})
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, *, timeout_seconds: int, context: ssl.SSLContext | None) -> Any:
    request = Request(url, headers={"User-Agent": "TenderRadar/0.1 authority-discovery", "Accept": "application/json"})
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _post_json(url: str, body: dict[str, Any], *, timeout_seconds: int, context: ssl.SSLContext | None) -> Any:
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "User-Agent": "TenderRadar/0.1 authority-discovery",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _parse_wordpress_posts(
    source: dict[str, Any],
    payload: Any,
    *,
    source_url: str,
    retrieved_at: str,
    limit: int,
) -> list[AuthorityCandidate]:
    posts = payload if isinstance(payload, list) else []
    candidates = []
    for post in posts[:limit]:
        if not isinstance(post, dict):
            continue
        title = _strip_html(_nested_str(post, "title", "rendered"))
        content = _nested_str(post, "content", "rendered")
        excerpt = _nested_str(post, "excerpt", "rendered")
        detail_url = _none_or_str(post.get("link"))
        links = _links_from_html(content or excerpt or "", detail_url or source_url)
        row_text = _clean_text(" ".join([title or "", _strip_html(excerpt or ""), _strip_html(content or "")[:5000]]))
        candidates.append(_candidate_from_parts(source, source_url, detail_url, links, title, _none_or_str(post.get("date")), row_text, retrieved_at))
    return candidates


def _parse_wordpress_page_table(
    source: dict[str, Any],
    payload: Any,
    *,
    source_url: str,
    retrieved_at: str,
    limit: int,
) -> list[AuthorityCandidate]:
    pages = payload if isinstance(payload, list) else []
    html = _nested_str(pages[0], "content", "rendered") if pages and isinstance(pages[0], dict) else ""
    parser = TableRowParser(source_url)
    parser.feed(html)
    return [
        _candidate_from_item(source, source_url, item, "", retrieved_at)
        for item in parser.items[:limit]
    ]


def _parse_html_listing(
    source: dict[str, Any],
    html: str,
    *,
    source_url: str,
    retrieved_at: str,
    timeout_seconds: int,
    context: ssl.SSLContext | None,
    limit: int,
) -> list[AuthorityCandidate]:
    parser = GenericListingParser(source_url)
    parser.feed(html)
    candidates = []
    for item in parser.items[:limit]:
        detail_url = item.get("detail_url")
        detail_html = ""
        detail_links: list[str] = []
        if detail_url:
            try:
                detail_html = _fetch_text(str(detail_url), timeout_seconds=timeout_seconds, context=context)
                detail_links = _links_from_html(detail_html, str(detail_url))
            except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError):
                detail_html = ""
        candidates.append(_candidate_from_item(source, source_url, item, detail_html, retrieved_at, extra_links=detail_links))
    return candidates


def _parse_diavgeia(
    source: dict[str, Any],
    payload: Any,
    *,
    source_url: str,
    retrieved_at: str,
    limit: int,
) -> list[AuthorityCandidate]:
    decisions = payload.get("decisions") if isinstance(payload, dict) else []
    candidates = []
    for item in (decisions or [])[:limit]:
        if not isinstance(item, dict):
            continue
        ada = str(item.get("ada") or "")
        detail_url = _none_or_str(item.get("documentUrl")) or (f"https://diavgeia.gov.gr/doc/{ada}" if ada else None)
        title = _none_or_str(item.get("subject"))
        row_text = _clean_text(json.dumps(item, ensure_ascii=False))
        links = [detail_url] if detail_url and _document_url(detail_url) else []
        candidates.append(_candidate_from_parts(source, source_url, detail_url, links, title, _none_or_str(item.get("issueDate") or item.get("submissionTimestamp")), row_text, retrieved_at, fallback_id=ada))
    return candidates


def _parse_ted(
    source: dict[str, Any],
    payload: Any,
    *,
    source_url: str,
    retrieved_at: str,
    limit: int,
) -> list[AuthorityCandidate]:
    notices = payload.get("notices") if isinstance(payload, dict) else []
    candidates = []
    for item in (notices or [])[:limit]:
        if not isinstance(item, dict):
            continue
        publication_number = str(item.get("publication-number") or "")
        title = _ted_title(item.get("notice-title"))
        links = _ted_links(item.get("links"))
        detail_url = links[0] if links else source_url
        row_text = _clean_text(json.dumps(item, ensure_ascii=False))
        candidates.append(_candidate_from_parts(source, source_url, detail_url, links[1:], title, _none_or_str(item.get("publication-date")), row_text, retrieved_at, fallback_id=publication_number))
    return candidates


def _candidate_from_item(
    source: dict[str, Any],
    source_url: str,
    item: dict[str, Any],
    detail_html: str,
    retrieved_at: str,
    *,
    extra_links: list[str] | None = None,
) -> AuthorityCandidate:
    links = _dedupe([*item.get("attachment_urls", []), *(extra_links or [])])
    row_text = _clean_text(" ".join([str(item.get("title") or ""), str(item.get("published_at") or ""), " ".join(item.get("text") or []), _strip_html(detail_html)[:5000]]))
    return _candidate_from_parts(source, source_url, _none_or_str(item.get("detail_url")), links, _none_or_str(item.get("title")), _none_or_str(item.get("published_at")), row_text, retrieved_at)


def _candidate_from_parts(
    source: dict[str, Any],
    source_url: str,
    detail_url: str | None,
    attachment_urls: list[str],
    title: str | None,
    published_at: str | None,
    row_text: str,
    retrieved_at: str,
    *,
    fallback_id: str | None = None,
) -> AuthorityCandidate:
    official_id, record_type = _official_reference(row_text, detail_url or source_url, fallback_id=fallback_id)
    return AuthorityCandidate(
        source_id=str(source.get("id") or ""),
        source_name=str(source.get("name") or source.get("id") or ""),
        scope_id=_none_or_str(source.get("scope_id")),
        scope_name=_none_or_str(source.get("scope_name")),
        source_family=str(source.get("source_family") or "authority_html"),
        adapter=str(source.get("adapter") or ""),
        official_id=official_id,
        record_type=record_type,
        title=title,
        authority=_none_or_str(source.get("scope_name")),
        published_at=published_at,
        submission_deadline=None,
        source_url=source_url,
        detail_url=detail_url,
        attachment_url=attachment_urls[0] if attachment_urls else None,
        attachment_urls=attachment_urls,
        retrieved_at=retrieved_at,
        parser_status="PARSED",
        status="AUTHORITY_DISCOVERY_CANDIDATE",
        status_reason=(
            "Public authority page candidate only; official submission status must be verified "
            "through ESHIDIS/KIMDIS or newer official acts."
        ),
        row_text=row_text,
    )


def _official_reference(text: str, fallback_url: str, *, fallback_id: str | None = None) -> tuple[str, str]:
    proc = re.search(r"\b\d{2}PROC\d{9}\b", text, flags=re.IGNORECASE)
    if proc:
        return proc.group(0).upper(), "PROC"
    eshidis = _extract_contextual_eshidis_id(text)
    if eshidis:
        return eshidis, "ESHIDIS"
    if fallback_id:
        return f"AUTH-{hashlib.sha256(fallback_id.encode('utf-8')).hexdigest()[:16]}", "AUTHORITY_WEB"
    digest = hashlib.sha256(fallback_url.encode("utf-8")).hexdigest()[:16]
    return f"AUTH-{digest}", "AUTHORITY_WEB"


def _extract_contextual_eshidis_id(text: str) -> str | None:
    patterns = [
        r"(?:Ε\.?\s*Σ\.?\s*Η\.?\s*Δ\.?\s*Η\.?\s*Σ\.?|ΕΣΗΔΗΣ|ΕΙΣΗΔΗΣ|ΟΠΣ)\s*(?:Α/?Α|αριθ(?:μός|\.?)|διαγωνισμού)?\s*[:#-]?\s*(\d{6})",
        r"/(?:resources/search|search)/(\d{6})(?:\b|/)",
        r"(?:Α/?Α\s+Διαγωνισμού)\s*(\d{6})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _document_url(url: str) -> bool:
    lowered = url.lower().split("?", 1)[0]
    return lowered.endswith(DOCUMENT_EXTENSIONS)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_html(value: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", html_lib.unescape(value or "")))


def _nested_str(item: Any, *keys: str) -> str | None:
    value = item
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _none_or_str(value)


def _links_from_html(value: str, base_url: str) -> list[str]:
    parser = LinkCollector(base_url)
    parser.feed(value or "")
    return _dedupe(parser.document_links)


def _ted_title(value: Any) -> str | None:
    if isinstance(value, dict):
        for lang in ("ell", "ELL", "el", "eng", "ENG", "en"):
            text = value.get(lang)
            if text:
                return str(text)
        for text in value.values():
            if text:
                return str(text)
    return _none_or_str(value)


def _ted_links(value: Any) -> list[str]:
    links: list[str] = []
    if isinstance(value, dict):
        for family in ("html", "htmlDirect", "pdf", "xml"):
            entry = value.get(family)
            if isinstance(entry, dict):
                links.extend(str(url) for url in entry.values() if url)
            elif entry:
                links.append(str(entry))
    return _dedupe(links)


def _none_or_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
