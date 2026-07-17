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
                message="Reachable.",
            ).to_dict()
        ],
    }

    markdown = render_source_audit_markdown(report)

    assert "Source Whitelist Audit" in markdown
    assert "Δοκιμή" in markdown
    assert "`REACHABLE`" in markdown
