from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any


ESHIDIS_SEARCH_URL = (
    "https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/"
    "active_search_main.jspx"
)
RESOURCE_URL = "http://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{eshidis_id}"


@dataclass(frozen=True)
class EshidisDiscoveryCandidate:
    eshidis_id: str
    status: str
    status_confidence: float
    source_url: str
    row_text: str
    title: str | None = None
    authority_name: str | None = None
    submission_deadline: str | None = None
    published_at: str | None = None
    detail_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eshidis_id": self.eshidis_id,
            "status": self.status,
            "status_confidence": self.status_confidence,
            "title": self.title,
            "authority_name": self.authority_name,
            "submission_deadline": self.submission_deadline,
            "published_at": self.published_at,
            "detail_hint": self.detail_hint,
            "source_url": self.source_url,
            "row_text": self.row_text,
        }


def discover_active_candidates_audit(
    out_path: Path,
    *,
    status_value: str = "2",
    limit: int = 25,
    allow_insecure_tls: bool = False,
    headful: bool = False,
) -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path: Path | None = out_path.with_suffix(".png")

    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    response_bodies: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headful)
        context = browser.new_context(ignore_https_errors=allow_insecure_tls)
        page = context.new_page()
        page.on(
            "request",
            lambda request: requests.append(
                {
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "post_data": request.post_data if request.method == "POST" else None,
                }
            ),
        )

        def record_response(response: Any) -> None:
            entry = {
                "status": response.status,
                "url": response.url,
                "content_type": response.headers.get("content-type"),
            }
            responses.append(entry)
            content_type = entry["content_type"] or ""
            if len(response_bodies) < 30 and (
                "text" in content_type or "html" in content_type or "xml" in content_type or "json" in content_type
            ):
                try:
                    body = response.text()
                except Exception as exc:  # pragma: no cover - diagnostic payload only
                    body = f"<body read failed: {exc!r}>"
                response_bodies.append({**entry, "body_sample": body[:100000]})

        page.on("response", record_response)

        navigation_error = None
        search_attempt: dict[str, Any]
        try:
            page.goto(ESHIDIS_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            search_attempt = search_eshidis_grid(page, status_value=status_value)
        except Exception as exc:
            navigation_error = repr(exc)
            search_attempt = {"clicked": False, "error": repr(exc)}

        snapshot = snapshot_search_results(page, limit=limit)
        try:
            page.screenshot(path=str(screenshot_path), full_page=True, timeout=10_000)
        except Exception:
            screenshot_path = None
        browser.close()

    candidates = parse_discovery_candidates(snapshot, source_url=ESHIDIS_SEARCH_URL, limit=limit)
    if len(candidates) < limit:
        candidates.extend(
            _new_candidates(
                parse_adf_response_candidates(response_bodies, source_url=ESHIDIS_SEARCH_URL, limit=limit),
                existing_ids={candidate.eshidis_id for candidate in candidates},
                limit=limit - len(candidates),
            )
        )
    payload = {
        "target_url": ESHIDIS_SEARCH_URL,
        "status_filter": {
            "value": status_value,
            "label": "ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ" if status_value == "2" else None,
        },
        "candidate_status": "DISCOVERED_ACTIVE_CANDIDATE",
        "navigation_error": navigation_error,
        "search_attempt": search_attempt,
        "coverage": {
            "requested_limit": limit,
            "visible_rows_seen": snapshot.get("visible_rows_seen", 0),
            "candidates_found": len(candidates),
            "table_count": snapshot.get("table_count", 0),
            "adf_response_bodies_checked": len(response_bodies),
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
        "snapshot": snapshot,
        "request_count": len(requests),
        "response_count": len(responses),
        "requests": requests[:220],
        "responses": responses[:220],
        "response_bodies": response_bodies,
        "screenshot": str(screenshot_path) if screenshot_path else None,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def search_eshidis_grid(page: Any, *, status_value: str = "2") -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    status_changed = False
    status_select = page.locator("#qryId1\\:val00\\:\\:content")
    if status_select.count() == 1:
        status_select.select_option(status_value, timeout=5_000)
        status_changed = True

    search_button = page.locator("#qryId1\\:\\:search")
    if search_button.count() != 1:
        return {"clicked": False, "status_value": status_value, "reason": "Known search button was not unique."}
    search_button.click(timeout=5_000)
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    return {
        "clicked": True,
        "status_value": status_value,
        "status_changed": status_changed,
        "status_input_id": "qryId1:val00::content",
        "button_id": "qryId1::search",
    }


def snapshot_search_results(page: Any, *, limit: int = 25) -> dict[str, Any]:
    return page.evaluate(
        """
        (limit) => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          const tables = Array.from(document.querySelectorAll('table')).map((table, tableIndex) => {
            const rows = Array.from(table.querySelectorAll('tr')).slice(0, Math.max(limit * 3, 30)).map((row, rowIndex) => ({
              tableIndex,
              rowIndex,
              text: clean(row.innerText).slice(0, 2500),
              cells: Array.from(row.querySelectorAll('th,td')).map((cell) => clean(cell.innerText)).filter(Boolean),
              links: Array.from(row.querySelectorAll('a')).map((a) => ({
                id: a.id || null,
                text: clean(a.innerText),
                title: a.getAttribute('title'),
                href: a.getAttribute('href'),
              })),
            })).filter((row) => row.text || row.links.length);
            return {
              tableIndex,
              id: table.id || null,
              className: table.className || null,
              textSample: clean(table.innerText).slice(0, 4000),
              rows,
            };
          }).filter((table) => table.textSample || table.rows.length);
          const candidateRows = [];
          for (const table of tables) {
            for (const row of table.rows) {
              const compact = row.text.replace(/\\s+/g, ' ');
              if (/\\b\\d{5,7}\\b/.test(compact) && compact.length > 20 && !compact.includes('XXXXXX')) {
                candidateRows.push(row);
              }
            }
          }
          return {
            url: location.href,
            title: document.title,
            bodyTextSample: clean(document.body ? document.body.innerText : '').slice(0, 12000),
            table_count: tables.length,
            visible_rows_seen: candidateRows.length,
            candidate_rows: candidateRows.slice(0, limit),
            tables: tables.slice(0, 25),
          };
        }
        """,
        limit,
    )


def parse_discovery_candidates(
    snapshot: dict[str, Any],
    *,
    source_url: str = ESHIDIS_SEARCH_URL,
    limit: int = 25,
) -> list[EshidisDiscoveryCandidate]:
    candidates: list[EshidisDiscoveryCandidate] = []
    seen: set[str] = set()
    rows = snapshot.get("candidate_rows") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_text = _clean_text(str(row.get("text") or ""))
        if _is_header_or_filter_row(row_text):
            continue
        eshidis_id = _first_system_id(row_text)
        if not eshidis_id or eshidis_id in seen:
            continue
        seen.add(eshidis_id)
        cells = [str(cell) for cell in row.get("cells", []) if str(cell).strip()]
        dates = _dates_from_text(row_text)
        links = row.get("links") if isinstance(row.get("links"), list) else []
        detail_hint = _detail_hint(links)
        candidates.append(
            EshidisDiscoveryCandidate(
                eshidis_id=eshidis_id,
                status="DISCOVERED_ACTIVE_CANDIDATE",
                status_confidence=0.55,
                title=_best_title(cells, row_text, eshidis_id),
                authority_name=_best_authority(cells),
                published_at=dates[0] if dates else None,
                submission_deadline=dates[-1] if len(dates) > 1 else None,
                detail_hint=detail_hint,
                source_url=source_url,
                row_text=row_text[:2000],
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def parse_adf_response_candidates(
    response_bodies: list[dict[str, Any]],
    *,
    source_url: str = ESHIDIS_SEARCH_URL,
    limit: int = 25,
) -> list[EshidisDiscoveryCandidate]:
    candidates: list[EshidisDiscoveryCandidate] = []
    seen: set[str] = set()
    for response in response_bodies:
        body = response.get("body_sample")
        if not isinstance(body, str) or "pc1:t1" not in body or "_rowCount" not in body:
            continue
        decoded = html.unescape(body)
        for row_html in re.findall(r"<tr\b[^>]*role=\"row\"[^>]*>.*?</tr>", decoded, flags=re.IGNORECASE | re.DOTALL):
            cells = _adf_row_cells(row_html)
            row_text = _clean_text(" ".join(cells))
            eshidis_id = _first_system_id(row_text)
            if not eshidis_id or eshidis_id in seen:
                continue
            seen.add(eshidis_id)
            dates = _dates_from_text(row_text)
            candidates.append(
                EshidisDiscoveryCandidate(
                    eshidis_id=eshidis_id,
                    status="DISCOVERED_ACTIVE_CANDIDATE",
                    status_confidence=0.65,
                    title=_adf_value(cells, 1) or _best_title(cells, row_text, eshidis_id),
                    authority_name=_best_authority(cells),
                    published_at=dates[0] if dates else None,
                    submission_deadline=dates[-1] if len(dates) > 1 else None,
                    detail_hint=f"pc1:t1 row for {eshidis_id}",
                    source_url=source_url,
                    row_text=row_text[:2000],
                )
            )
            if len(candidates) >= limit:
                return candidates
    return candidates


def render_discovery_markdown(report: dict[str, Any]) -> str:
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    lines = [
        "# ESHIDIS Active Candidate Discovery",
        "",
        f"- Source: `{report.get('target_url')}`",
        f"- Status filter: `{report.get('status_filter', {}).get('label') or report.get('status_filter', {}).get('value')}`",
        f"- Candidate status: `{report.get('candidate_status')}`",
        f"- Candidates found: `{len(candidates)}`",
        f"- Visible rows seen: `{coverage.get('visible_rows_seen', 0)}`",
        f"- Navigation error: `{report.get('navigation_error')}`",
        "",
    ]
    if not candidates:
        lines.extend(
            [
                "No candidates were extracted from the visible grid rows.",
                "",
                "This does not prove that no active tenders exist; it only means the current",
                "browser/grid audit did not expose parsable rows.",
            ]
        )
        return "\n".join(lines) + "\n"
    lines.append("| ESHIDIS | Status | Deadline | Title |")
    lines.append("| --- | --- | --- | --- |")
    for candidate in candidates:
        lines.append(
            "| {eshidis_id} | {status} | {deadline} | {title} |".format(
                eshidis_id=candidate.get("eshidis_id") or "",
                status=candidate.get("status") or "",
                deadline=candidate.get("submission_deadline") or "",
                title=_markdown_cell(candidate.get("title") or ""),
            )
        )
    return "\n".join(lines) + "\n"


def fetch_resource_audit(
    eshidis_id: str,
    out_path: Path,
    *,
    allow_insecure_tls: bool = False,
    headful: bool = False,
) -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path: Path | None = out_path.with_suffix(".png")

    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    response_bodies: list[dict[str, Any]] = []
    target_url = RESOURCE_URL.format(eshidis_id=eshidis_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headful)
        context = browser.new_context(ignore_https_errors=allow_insecure_tls)
        page = context.new_page()

        page.on(
            "request",
            lambda request: requests.append(
                {
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "post_data": request.post_data if request.method == "POST" else None,
                }
            ),
        )

        def record_response(response: Any) -> None:
            entry = {
                "status": response.status,
                "url": response.url,
                "content_type": response.headers.get("content-type"),
            }
            responses.append(entry)
            content_type = entry["content_type"] or ""
            if len(response_bodies) < 20 and (
                "text" in content_type or "html" in content_type or "xml" in content_type or "json" in content_type
            ):
                try:
                    body = response.text()
                except Exception as exc:  # pragma: no cover - diagnostic payload only
                    body = f"<body read failed: {exc!r}>"
                response_bodies.append({**entry, "body_sample": body[:50000]})

        page.on("response", record_response)

        navigation_error = None
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
        except Exception as exc:
            navigation_error = repr(exc)

        snapshot = snapshot_page(page)
        attachments_attempt = try_open_attachments(page)
        attachments_snapshot = snapshot_page(page)
        attachment_links = extract_attachment_links(attachments_snapshot)
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            pass
        attachment_response_snapshot = snapshot_page(page)
        try:
            page.screenshot(path=str(screenshot_path), full_page=True, timeout=10_000)
        except Exception:
            screenshot_path = None
        browser.close()

    payload = {
        "target_url": target_url,
        "eshidis_id": eshidis_id,
        "navigation_error": navigation_error,
        "snapshot": snapshot,
        "attachments_attempt": attachments_attempt,
        "attachments_snapshot": attachments_snapshot,
        "attachment_response_snapshot": attachment_response_snapshot,
        "attachment_links": attachment_links,
        "request_count": len(requests),
        "response_count": len(responses),
        "requests": requests[:120],
        "responses": responses[:120],
        "response_bodies": response_bodies,
        "screenshot": str(screenshot_path) if screenshot_path else None,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def download_attachment_audit(
    eshidis_id: str,
    row_index: int,
    out_path: Path,
    download_dir: Path,
    *,
    allow_insecure_tls: bool = False,
    headful: bool = False,
) -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    target_url = RESOURCE_URL.format(eshidis_id=eshidis_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headful)
        context = browser.new_context(ignore_https_errors=allow_insecure_tls, accept_downloads=True)
        page = context.new_page()
        page.on(
            "request",
            lambda request: requests.append(
                {
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "post_data": request.post_data if request.method == "POST" else None,
                }
            ),
        )
        page.on(
            "response",
            lambda response: responses.append(
                {
                    "status": response.status,
                    "url": response.url,
                    "content_type": response.headers.get("content-type"),
                    "content_disposition": response.headers.get("content-disposition"),
                }
            ),
        )

        navigation_error = None
        download_error = None
        downloaded_file: dict[str, Any] | None = None
        before_snapshot: dict[str, Any] | None = None

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            page.locator("#sdi2\\:\\:disAcr").click(timeout=5_000)
            button = page.locator(f"#t1\\:{row_index}\\:cb1 a")
            button.wait_for(state="visible", timeout=15_000)
            before_snapshot = snapshot_download_buttons(page)
            with page.expect_download(timeout=30_000) as download_info:
                button.click(timeout=5_000)
            download = download_info.value
            suggested = sanitize_filename(download.suggested_filename or f"eshidis_{eshidis_id}_{row_index}")
            saved_path = download_dir / suggested
            download.save_as(saved_path)
            downloaded_file = file_metadata(saved_path)
        except Exception as exc:
            if navigation_error is None and "goto" in repr(exc).lower():
                navigation_error = repr(exc)
            else:
                download_error = repr(exc)
        finally:
            browser.close()

    payload = {
        "target_url": target_url,
        "eshidis_id": eshidis_id,
        "row_index": row_index,
        "navigation_error": navigation_error,
        "download_error": download_error,
        "before_snapshot": before_snapshot,
        "downloaded_file": downloaded_file,
        "request_count": len(requests),
        "response_count": len(responses),
        "requests": requests[:160],
        "responses": responses[:160],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def snapshot_page(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          return {
            url: location.href,
            title: document.title,
            bodyTextSample: clean(document.body ? document.body.innerText : '').slice(0, 12000),
            links: Array.from(document.querySelectorAll('a')).slice(0, 200).map((a) => ({
              id: a.id || null,
              text: clean(a.innerText),
              title: a.getAttribute('title'),
              href: a.getAttribute('href'),
              rowText: a.closest('tr') ? clean(a.closest('tr').innerText).slice(0, 1000) : null,
            })),
            tables: Array.from(document.querySelectorAll('table')).slice(0, 80).map((table, tableIndex) => ({
              tableIndex,
              id: table.id || null,
              textSample: clean(table.innerText).slice(0, 2500),
              rows: Array.from(table.querySelectorAll('tr')).slice(0, 30).map((row, rowIndex) => ({
                rowIndex,
                text: clean(row.innerText).slice(0, 1500),
                links: Array.from(row.querySelectorAll('a')).map((a) => ({
                  id: a.id || null,
                  text: clean(a.innerText),
                  title: a.getAttribute('title'),
                  href: a.getAttribute('href'),
                })),
              })).filter((row) => row.text || row.links.length),
            })).filter((table) => table.textSample || table.rows.length),
          };
        }
        """
    )


def try_open_attachments(page: Any) -> dict[str, Any]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        tab = page.locator("#sdi2\\:\\:disAcr")
        if tab.count() != 1:
            return {"clicked": False, "reason": "Attachments tab was not uniquely found."}
        tab.click(timeout=5_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightTimeoutError:
            pass
        return {"clicked": True, "tab_id": "sdi2::disAcr"}
    except Exception as exc:
        return {"clicked": False, "error": repr(exc)}


def extract_attachment_links(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    links = []
    for link in snapshot.get("links", []):
        text = " ".join(
            str(part or "")
            for part in (link.get("text"), link.get("title"), link.get("href"), link.get("rowText"))
        )
        if any(token in text.lower() for token in ("pdf", "doc", "zip", "λήψη", "download", "αρχ")):
            links.append(link)
    return links


def snapshot_download_buttons(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          return {
            url: location.href,
            buttons: Array.from(document.querySelectorAll('[id^="t1:"][id$=":cb1"]')).map((el) => ({
              id: el.id,
              text: clean(el.innerText),
              rowText: el.closest('tr') ? clean(el.closest('tr').innerText).slice(0, 1200) : null,
            })),
          };
        }
        """
    )


def sanitize_filename(value: str) -> str:
    forbidden = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in forbidden else ch for ch in value).strip()
    return cleaned or "download.bin"


def file_metadata(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _new_candidates(
    candidates: list[EshidisDiscoveryCandidate],
    *,
    existing_ids: set[str],
    limit: int,
) -> list[EshidisDiscoveryCandidate]:
    selected: list[EshidisDiscoveryCandidate] = []
    for candidate in candidates:
        if candidate.eshidis_id in existing_ids:
            continue
        existing_ids.add(candidate.eshidis_id)
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def _adf_row_cells(row_html: str) -> list[str]:
    cells: list[str] = []
    for cell_html in re.findall(r"<td\b[^>]*>.*?</td>", row_html, flags=re.IGNORECASE | re.DOTALL):
        text = re.sub(r"<script\b.*?</script>", " ", cell_html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        cleaned = _clean_text(html.unescape(text).replace("\xa0", " "))
        cells.append(cleaned)
    return cells


def _adf_value(cells: list[str], index: int) -> str | None:
    if index >= len(cells):
        return None
    value = cells[index].strip()
    return value or None


def _first_system_id(text: str) -> str | None:
    for match in re.finditer(r"\b(\d{5,7})\b", text):
        value = match.group(1)
        if value.startswith(("19", "20")) and len(value) == 4:
            continue
        return value
    return None


def _dates_from_text(text: str) -> list[str]:
    return re.findall(r"\b\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b", text)


def _best_title(cells: list[str], row_text: str, eshidis_id: str) -> str | None:
    candidates = [
        cell
        for cell in cells
        if eshidis_id not in cell
        and not re.fullmatch(r"\d{2}[-/]\d{2}[-/]\d{4}.*", cell)
        and len(cell) >= 10
        and "Προβολ" not in cell
    ]
    if candidates:
        return max(candidates, key=len)[:300]
    cleaned = row_text.replace(eshidis_id, " ")
    cleaned = re.sub(r"\b\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b", " ", cleaned)
    cleaned = _clean_text(cleaned)
    return cleaned[:300] or None


def _best_authority(cells: list[str]) -> str | None:
    for cell in cells:
        upper = cell.upper()
        if any(token in upper for token in ("ΔΗΜΟΣ", "ΠΕΡΙΦΕΡΕΙΑ", "ΥΠΟΥΡΓ", "ΕΦΟΡΕΙΑ", "ΑΡΧΗ")):
            return cell[:200]
    return None


def _detail_hint(links: list[Any]) -> str | None:
    for link in links:
        if not isinstance(link, dict):
            continue
        hint = link.get("href") or link.get("id") or link.get("title") or link.get("text")
        if hint:
            return str(hint)
    return None


def _is_header_or_filter_row(text: str) -> bool:
    upper = text.upper()
    return (
        "ΚΑΤΑΣΤΑΣΗ" in upper
        and "CPV" in upper
        and ("ΑΡΧΙΖΕΙ" in upper or "ΤΕΛΕΙΩΝΕΙ" in upper)
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:180]
