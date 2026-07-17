from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ESHIDIS_URL = (
    "https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/"
    "active_search_main.jspx"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Browser audit for ESHIDIS public works search.")
    parser.add_argument("--eshidis-id", default=None)
    parser.add_argument("--title-query", default=None)
    parser.add_argument("--out", default="work/source_audit/eshidis_browser_audit.json")
    parser.add_argument("--status-value", default=None)
    parser.add_argument("--allow-insecure-tls", action="store_true")
    parser.add_argument("--open-first-result", action="store_true")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path = out_path.with_suffix(".png")

    observed_requests: list[dict[str, Any]] = []
    observed_responses: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        context = browser.new_context(ignore_https_errors=args.allow_insecure_tls)
        page = context.new_page()

        page.on(
            "request",
            lambda request: observed_requests.append(
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
            lambda response: observed_responses.append(
                {
                    "status": response.status,
                    "url": response.url,
                    "content_type": response.headers.get("content-type"),
                }
            ),
        )

        navigation_error = None
        try:
            page.goto(ESHIDIS_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
        except Exception as exc:  # audit output must capture the blocker.
            navigation_error = repr(exc)

        page_snapshot = snapshot_page(page)
        search_attempt = try_search(
            page,
            eshidis_id=args.eshidis_id,
            status_value=args.status_value,
            title_query=args.title_query,
        )
        post_search_snapshot = snapshot_page(page)
        result_snapshot = snapshot_results(page)
        detail_attempt = None
        detail_snapshot = None
        if args.open_first_result:
            detail_attempt = try_open_first_result(page)
            detail_snapshot = snapshot_page(page)

        try:
            page.screenshot(path=str(screenshot_path), full_page=True, timeout=10_000)
        except Exception:
            screenshot_path = None

        browser.close()

    payload = {
        "target_url": ESHIDIS_URL,
        "eshidis_id": args.eshidis_id,
        "title_query": args.title_query,
        "status_value": args.status_value,
        "allow_insecure_tls": args.allow_insecure_tls,
        "navigation_error": navigation_error,
        "page_snapshot": page_snapshot,
        "search_attempt": search_attempt,
        "post_search_snapshot": post_search_snapshot,
        "result_snapshot": result_snapshot,
        "detail_attempt": detail_attempt,
        "detail_snapshot": detail_snapshot,
        "request_count": len(observed_requests),
        "response_count": len(observed_responses),
        "requests": observed_requests[:220],
        "responses": observed_responses[:220],
        "screenshot": str(screenshot_path) if screenshot_path else None,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def snapshot_page(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """
            () => {
              const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
                .slice(0, 80)
                .map((el) => ({
                  tag: el.tagName.toLowerCase(),
                  type: el.getAttribute('type'),
                  id: el.id || null,
                  name: el.getAttribute('name'),
                  title: el.getAttribute('title'),
                  ariaLabel: el.getAttribute('aria-label'),
                  placeholder: el.getAttribute('placeholder'),
                  value: el.value || null,
                  text: clean(el.textContent),
                }));
              const buttons = Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a'))
                .slice(0, 120)
                .map((el) => ({
                  tag: el.tagName.toLowerCase(),
                  type: el.getAttribute('type'),
                  id: el.id || null,
                  name: el.getAttribute('name'),
                  href: el.getAttribute('href'),
                  title: el.getAttribute('title'),
                  text: clean(el.textContent || el.value),
                }));
              return {
                url: location.href,
                title: document.title,
                bodyTextSample: clean(document.body ? document.body.innerText : '').slice(0, 4000),
                inputs,
                buttons,
              };
            }
            """
        )
    except Exception as exc:
        return {"error": repr(exc)}


def snapshot_results(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """
            () => {
              const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const tables = Array.from(document.querySelectorAll('table'))
                .map((table, tableIndex) => {
                  const rows = Array.from(table.querySelectorAll('tr')).slice(0, 20)
                    .map((row, rowIndex) => ({
                      rowIndex,
                      text: clean(row.innerText).slice(0, 1200),
                      links: Array.from(row.querySelectorAll('a')).map((a) => ({
                        id: a.id || null,
                        text: clean(a.innerText),
                        title: a.getAttribute('title'),
                        href: a.getAttribute('href'),
                      })),
                    }))
                    .filter((row) => row.text || row.links.length);
                  return {
                    tableIndex,
                    id: table.id || null,
                    className: table.className || null,
                    textSample: clean(table.innerText).slice(0, 2000),
                    rows,
                  };
                })
                .filter((table) => table.textSample || table.rows.length);
              const likelyRows = [];
              for (const table of tables) {
                for (const row of table.rows) {
                  const hasTenderLikeId = /\\b\\d{5,7}\\b/.test(row.text);
                  const hasMeaningfulText = row.text.length > 25 && !/^Προβολή( Μορφοποίηση)?( Εξαγωγή σε Excel)?$/.test(row.text);
                  if (hasTenderLikeId || (hasMeaningfulText && row.links.some((link) => link.text.includes('Προβολή')))) {
                    likelyRows.push({ tableIndex: table.tableIndex, ...row });
                  }
                }
              }
              return { table_count: tables.length, tables: tables.slice(0, 20), likelyRows: likelyRows.slice(0, 20) };
            }
            """
        )
    except Exception as exc:
        return {"error": repr(exc)}


def try_search(
    page,
    eshidis_id: str | None = None,
    status_value: str | None = None,
    title_query: str | None = None,
) -> dict[str, Any]:
    try:
        status_changed = False
        if status_value is not None:
            status_select = page.locator("#qryId1\\:val00\\:\\:content")
            if status_select.count() == 1:
                status_select.select_option(status_value, timeout=5_000)
                status_changed = True

        title_filled = False
        if title_query:
            title_input = page.locator("#qryId1\\:val20\\:\\:content")
            if title_input.count() == 1:
                title_input.fill(title_query, timeout=5_000)
                title_filled = True

        direct_input = page.locator("#qryId1\\:val10\\:\\:content")
        if eshidis_id and direct_input.count() == 1:
            direct_input.fill(eshidis_id, timeout=5_000)
            search_button = page.locator("#qryId1\\:\\:search")
            if search_button.count() != 1:
                return {"filled": True, "clicked": False, "reason": "Known search button was not unique."}
            search_button.click(timeout=5_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass
            return {
                "filled": True,
                "clicked": True,
                "status_value": status_value,
                "status_changed": status_changed,
                "title_query": title_query,
                "title_filled": title_filled,
                "input_id": "qryId1:val10::content",
                "button_id": "qryId1::search",
            }

        if not eshidis_id:
            search_button = page.locator("#qryId1\\:\\:search")
            if search_button.count() != 1:
                return {
                    "filled": title_filled,
                    "clicked": False,
                    "reason": "Known search button was not unique.",
                }
            search_button.click(timeout=5_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass
            return {
                "filled": title_filled,
                "clicked": True,
                "status_value": status_value,
                "status_changed": status_changed,
                "title_query": title_query,
                "title_filled": title_filled,
                "button_id": "qryId1::search",
            }

        candidates = page.locator("input").evaluate_all(
            """
            (els) => els.map((el, index) => ({
              index,
              id: el.id || '',
              name: el.getAttribute('name') || '',
              title: el.getAttribute('title') || '',
              ariaLabel: el.getAttribute('aria-label') || '',
              type: el.getAttribute('type') || '',
              visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
            }))
            """
        )
        likely = [
            item
            for item in candidates
            if item["visible"]
            and any(
                token in " ".join([item["id"], item["name"], item["title"], item["ariaLabel"]]).lower()
                for token in ("α/α", "a/a", "system", "auction", "διαγωνισ", "συστ")
            )
        ]
        target = likely[0] if likely else None
        if not target:
            return {"filled": False, "reason": "No likely ESHIDIS id input found.", "candidates": candidates[:40]}

        locator = page.locator("input").nth(target["index"])
        locator.fill(eshidis_id, timeout=5_000)

        search_controls = page.locator("button, input[type=button], input[type=submit], a").evaluate_all(
            """
            (els) => els.map((el, index) => ({
              index,
              text: (el.textContent || el.value || '').replace(/\\s+/g, ' ').trim(),
              id: el.id || '',
              title: el.getAttribute('title') || '',
              visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
            }))
            """
        )
        likely_button = [
            item
            for item in search_controls
            if item["visible"]
            and any(token in " ".join([item["text"], item["id"], item["title"]]).lower() for token in ("αναζ", "search"))
        ]
        if not likely_button:
            return {"filled": True, "clicked": False, "input": target, "reason": "No likely search button found."}

        page.locator("button, input[type=button], input[type=submit], a").nth(likely_button[0]["index"]).click(
            timeout=5_000
        )
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeoutError:
            pass
        return {"filled": True, "clicked": True, "input": target, "button": likely_button[0]}
    except Exception as exc:
        return {"filled": False, "error": repr(exc)}


def try_open_first_result(page) -> dict[str, Any]:
    try:
        links = page.locator("a").evaluate_all(
            """
            (els) => els.map((el, index) => ({
              index,
              id: el.id || '',
              text: (el.textContent || '').replace(/\\s+/g, ' ').trim(),
              title: el.getAttribute('title') || '',
              href: el.getAttribute('href') || '',
              visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
              rowText: el.closest('tr') ? el.closest('tr').innerText.replace(/\\s+/g, ' ').trim().slice(0, 1000) : ''
            }))
            """
        )
        candidates = [
            item
            for item in links
            if item["visible"]
            and "Προβολή" in " ".join([item["text"], item["title"], item["rowText"]])
            and "XXXXXX" not in item["rowText"]
            and len(item["rowText"]) > 25
            and not item["rowText"].startswith("Προβολή Μορφοποίηση")
        ]
        if not candidates:
            return {"clicked": False, "reason": "No visible non-placeholder result/detail link found.", "links": links[:80]}

        target = candidates[0]
        page.locator("a").nth(target["index"]).click(timeout=5_000)
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeoutError:
            pass
        return {"clicked": True, "target": target}
    except Exception as exc:
        return {"clicked": False, "error": repr(exc)}


if __name__ == "__main__":
    raise SystemExit(main())
