from tender_radar.sources.whitelist import SourceAuditResult, render_source_audit_markdown


def test_render_source_audit_markdown_lists_statuses() -> None:
    report = {
        "config_path": "config/sources.yml",
        "checked_at": "2026-07-17T00:00:00+00:00",
        "allow_insecure_tls": False,
        "summary": {"total": 1, "reachable": 1, "failed": 0, "adapter_required": 0},
        "results": [
            SourceAuditResult(
                source_id="test",
                name="Δοκιμή",
                url="https://example.test",
                source_type="web",
                scope_id=None,
                scope_name=None,
                method="GET",
                status="REACHABLE",
                status_code=200,
                content_type="text/html",
                requires_browser_hint=False,
                adapter_required=False,
                fallback_available=False,
                records_sampled=None,
                message="Reachable.",
            ).to_dict()
        ],
    }

    markdown = render_source_audit_markdown(report)

    assert "Source Whitelist Audit" in markdown
    assert "Δοκιμή" in markdown
    assert "`REACHABLE`" in markdown


def test_render_source_audit_markdown_shows_fallback_and_records() -> None:
    report = {
        "config_path": "config/sources.yml",
        "checked_at": "2026-07-17T00:00:00+00:00",
        "allow_insecure_tls": True,
        "summary": {
            "total": 2,
            "reachable": 1,
            "failed": 1,
            "adapter_required": 0,
            "unresolved_blockers": 0,
        },
        "results": [
            SourceAuditResult(
                source_id="khmdhs_notice",
                name="ΚΗΜΔΗΣ Διακηρύξεις",
                url="https://example.test/notice?page=0",
                source_type="api_post",
                scope_id=None,
                scope_name=None,
                method="POST",
                status="ADAPTER_READY",
                status_code=200,
                content_type="application/json",
                requires_browser_hint=False,
                adapter_required=False,
                fallback_available=False,
                records_sampled=20,
                message="Documented POST probe succeeded.",
            ).to_dict(),
            SourceAuditResult(
                source_id="patras_source_1",
                name="Δήμος Πατρέων source 1",
                url="https://example.test/tenders",
                source_type="web",
                scope_id="patras",
                scope_name="Δήμος Πατρέων",
                method="GET",
                status="FAILED",
                status_code=None,
                content_type=None,
                requires_browser_hint=False,
                adapter_required=False,
                fallback_available=True,
                records_sampled=None,
                message="timed out; scope fallback source is reachable.",
            ).to_dict(),
        ],
    }

    markdown = render_source_audit_markdown(report)

    assert "`ADAPTER_READY`" in markdown
    assert "| 20 |" in markdown
    assert "| yes |" in markdown
    assert "Unresolved blockers" in markdown
