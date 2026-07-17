from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tender_radar.config import load_config
from tender_radar.evaluation import normalize_evaluation_config, save_evaluation_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
COMMAND_LOCK = threading.Lock()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Tender Radar UI server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="Open the UI in the default browser.")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), TenderRadarHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Tender Radar UI running at {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Tender Radar UI.")
    finally:
        server.server_close()
    return 0


class TenderRadarHandler(BaseHTTPRequestHandler):
    server_version = "TenderRadarUI/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
            return
        if parsed.path == "/styles.css":
            self._send_text(STYLES_CSS, "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_text(APP_JS, "application/javascript; charset=utf-8")
            return
        if parsed.path == "/api/status":
            self._send_json(status_payload())
            return
        if parsed.path == "/api/candidates":
            self._send_json(candidates_payload())
            return
        if parsed.path == "/api/evaluation-profile":
            query = parse_qs(parsed.query)
            profile_path = safe_evaluation_profile_path(query.get("path", [""])[0])
            self._send_json(evaluation_profile_payload(profile_path))
            return
        if parsed.path == "/api/report":
            query = parse_qs(parsed.query)
            path = report_path(query.get("path", [""])[0])
            if not path:
                self._send_json({"error": "Unknown report path."}, status=404)
                return
            self._send_file(path)
            return
        self._send_json({"error": "Not found."}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/discover":
                self._send_json(
                    run_cli_command(
                        [
                            "sources",
                            "discover-active",
                            "--allow-insecure-tls",
                            "--limit",
                            str(int(payload.get("limit") or 25)),
                            "--report",
                            "work/reports/eshidis_active_candidates.json",
                            "--markdown-report",
                            "work/reports/eshidis_active_candidates.md",
                        ]
                    )
                )
                return
            if parsed.path == "/api/fetch-resource":
                eshidis_id = require_eshidis_id(payload)
                self._send_json(run_cli_command(["sources", "fetch-resource", eshidis_id, "--allow-insecure-tls"]))
                return
            if parsed.path == "/api/download-all":
                eshidis_id = require_eshidis_id(payload)
                self._send_json(
                    run_cli_command(
                        ["sources", "download-attachment", eshidis_id, "--all", "--limit", "50", "--allow-insecure-tls"]
                    )
                )
                return
            if parsed.path == "/api/analyze":
                eshidis_id = require_eshidis_id(payload)
                self._send_json(
                    run_cli_command(
                        [
                            "documents",
                            "analyze",
                            "--eshidis-id",
                            eshidis_id,
                            "--report",
                            f"work/reports/document_analysis_{eshidis_id}.json",
                            "--markdown-report",
                            f"work/reports/document_analysis_{eshidis_id}.md",
                        ]
                    )
                )
                return
            if parsed.path == "/api/search":
                eshidis_id = require_eshidis_id(payload)
                profile = str(payload.get("profile") or "config/search_profiles/road_maintenance.yml")
                profile_id = Path(profile).stem
                self._send_json(
                    run_cli_command(
                        [
                            "search",
                            "run",
                            "--profile",
                            profile,
                            "--eshidis-id",
                            eshidis_id,
                            "--report",
                            f"work/reports/search_{profile_id}_{eshidis_id}.json",
                            "--markdown-report",
                            f"work/reports/search_{profile_id}_{eshidis_id}.md",
                        ]
                    )
                )
                return
            if parsed.path == "/api/evaluate":
                eshidis_id = require_eshidis_id(payload)
                profile = str(payload.get("profile") or "config/evaluation_profiles/public_works_dynamic.yml")
                profile_id = Path(profile).stem
                self._send_json(
                    run_cli_command(
                        [
                            "evaluate",
                            "run",
                            "--profile",
                            profile,
                            "--eshidis-id",
                            eshidis_id,
                            "--report",
                            f"work/reports/evaluation_{profile_id}_{eshidis_id}.json",
                            "--markdown-report",
                            f"work/reports/evaluation_{profile_id}_{eshidis_id}.md",
                        ]
                    )
                )
                return
            if parsed.path == "/api/evaluation-profile":
                profile_path = safe_evaluation_profile_path(str(payload.get("path") or ""))
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise ValueError("Evaluation profile payload must contain a data object.")
                saved = save_evaluation_config(profile_path, data)
                self._send_json({"ok": True, "path": str(profile_path.relative_to(REPO_ROOT)), "data": saved})
                return
            self._send_json({"error": "Not found."}, status=404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        self._send_text(html, "text/html; charset=utf-8")

    def _send_text(self, text: str, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_cli_command(args: list[str]) -> dict[str, Any]:
    if not COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another command is already running. Wait for it to finish."}
    try:
        command = [sys.executable, "-m", "tender_radar", *args]
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": " ".join(args),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "candidates": candidates_payload(),
        }
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": f"Command timed out: {exc!r}", "command": " ".join(args)}
    finally:
        COMMAND_LOCK.release()


def require_eshidis_id(payload: dict[str, Any]) -> str:
    value = str(payload.get("eshidis_id") or "").strip()
    if not value.isdigit() or len(value) < 5 or len(value) > 7:
        raise ValueError("ESHIDIS id must be a 5-7 digit number.")
    return value


def status_payload() -> dict[str, Any]:
    document_types_path = REPO_ROOT / "config/document_types.yml"
    document_types_data = load_config(document_types_path) if document_types_path.exists() else {}
    document_types = document_types_data.get("document_types", {}) if isinstance(document_types_data, dict) else {}
    return {
        "repo_root": str(REPO_ROOT),
        "python": sys.executable,
        "reports": {
            "candidates_json": str(REPO_ROOT / "work/reports/eshidis_active_candidates.json"),
            "candidates_markdown": str(REPO_ROOT / "work/reports/eshidis_active_candidates.md"),
        },
        "profiles": [
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in sorted((REPO_ROOT / "config/search_profiles").glob("*.yml"))
        ],
        "evaluation_profiles": [
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in sorted((REPO_ROOT / "config/evaluation_profiles").glob("*.yml"))
        ],
        "document_types": sorted(document_types.keys()) if isinstance(document_types, dict) else [],
    }


def candidates_payload() -> dict[str, Any]:
    path = REPO_ROOT / "work/reports/eshidis_active_candidates.json"
    if not path.exists():
        return {"exists": False, "path": str(path), "candidates": [], "coverage": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "path": str(path),
        "markdown_path": str(REPO_ROOT / "work/reports/eshidis_active_candidates.md"),
        "candidate_status": payload.get("candidate_status"),
        "coverage": payload.get("coverage") or {},
        "candidates": payload.get("candidates") or [],
        "navigation_error": payload.get("navigation_error"),
    }


def report_path(value: str) -> Path | None:
    if value not in {"candidates.md", "candidates.json"}:
        return None
    name = "eshidis_active_candidates.md" if value == "candidates.md" else "eshidis_active_candidates.json"
    path = (REPO_ROOT / "work/reports" / name).resolve()
    reports_dir = (REPO_ROOT / "work/reports").resolve()
    if reports_dir not in path.parents or not path.exists():
        return None
    return path


def safe_evaluation_profile_path(value: str) -> Path:
    relative = value or "config/evaluation_profiles/public_works_dynamic.yml"
    if "\\" in relative:
        relative = relative.replace("\\", "/")
    path = (REPO_ROOT / relative).resolve()
    profiles_dir = (REPO_ROOT / "config/evaluation_profiles").resolve()
    if profiles_dir not in path.parents or path.suffix.lower() not in {".yml", ".yaml"}:
        raise ValueError("Unknown evaluation profile path.")
    if not path.exists():
        raise ValueError("Evaluation profile does not exist.")
    return path


def evaluation_profile_payload(path: Path) -> dict[str, Any]:
    data = load_config(path)
    if not isinstance(data, dict):
        raise ValueError("Evaluation profile must be a YAML mapping.")
    normalized = normalize_evaluation_config(data, fallback_id=path.stem)
    return {
        "ok": True,
        "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "data": normalized,
    }


INDEX_HTML = """<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tender Radar</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <aside class="sidebar">
    <div class="brand">
      <span class="mark">TR</span>
      <div>
        <h1>Tender Radar</h1>
        <p>Local control panel</p>
      </div>
    </div>
    <nav>
      <button class="nav active" data-view="discover">Discovery</button>
      <button class="nav" data-view="tender">Tender</button>
      <button class="nav" data-view="rules">Rules</button>
      <button class="nav" data-view="reports">Reports</button>
    </nav>
  </aside>
  <main>
    <header>
      <div>
        <h2>Public Works Tender Radar</h2>
        <p id="statusText">Ready</p>
      </div>
      <button id="refreshBtn" class="secondary">Refresh</button>
    </header>

    <section id="discover" class="view active">
      <div class="toolbar">
        <label>Limit <input id="limitInput" type="number" min="1" max="100" value="25"></label>
        <button id="discoverBtn">Run Discovery</button>
      </div>
      <div class="metrics">
        <div><span id="candidateCount">0</span><small>Candidates</small></div>
        <div><span id="visibleRows">0</span><small>Visible rows</small></div>
        <div><span id="adfBodies">0</span><small>ADF bodies</small></div>
      </div>
      <div class="tableWrap">
        <table>
          <thead>
            <tr><th>A/A ΕΣΗΔΗΣ</th><th>Προθεσμία</th><th>Τίτλος</th><th>Status</th><th></th></tr>
          </thead>
          <tbody id="candidateRows"></tbody>
        </table>
      </div>
    </section>

    <section id="tender" class="view">
      <div class="toolbar">
        <label>A/A ΕΣΗΔΗΣ <input id="eshidisInput" type="text" inputmode="numeric" placeholder="π.χ. 221348"></label>
        <button id="fetchBtn">Fetch Detail</button>
        <button id="downloadBtn" class="secondary">Download All</button>
        <button id="analyzeBtn" class="secondary">Analyze Docs</button>
      </div>
      <div class="toolbar compact">
        <label>Profile <select id="profileSelect"></select></label>
        <button id="searchBtn">Run Search</button>
      </div>
      <div class="toolbar compact">
        <label>Evaluation <select id="evaluationProfileSelect"></select></label>
        <button id="evaluateBtn">Evaluate</button>
      </div>
      <pre id="commandOutput"></pre>
    </section>

    <section id="rules" class="view">
      <div class="toolbar">
        <label>Evaluation profile <select id="ruleProfileSelect"></select></label>
        <button id="loadRulesBtn" class="secondary">Load</button>
        <button id="saveRulesBtn">Save Rules</button>
      </div>
      <div class="rulesGrid">
        <div class="panel">
          <div class="panelHeader">
            <h3>Rules</h3>
            <button id="newRuleBtn" class="secondary">New</button>
          </div>
          <div id="ruleList" class="ruleList"></div>
        </div>
        <div class="panel">
          <div class="panelHeader">
            <h3>Rule editor</h3>
            <button id="deleteRuleBtn" class="secondary">Delete</button>
          </div>
          <div class="editorGrid">
            <label>Rule id <input id="ruleIdInput" type="text" placeholder="foundation_excavation_price_gt_5"></label>
            <label>Label <input id="ruleLabelInput" type="text" placeholder="Εκσκαφές θεμελίων > 5 ευρώ"></label>
            <label>Severity
              <select id="ruleSeverityInput">
                <option value="info">info</option>
                <option value="important">important</option>
                <option value="critical">critical</option>
              </select>
            </label>
            <label>Score <input id="ruleScoreInput" type="number" step="0.5" value="1"></label>
            <label>Document types <input id="ruleDocumentTypesInput" type="text" placeholder="budget, price_list"></label>
            <label>Numeric filter
              <span class="inlineControls">
                <select id="ruleOperatorInput">
                  <option value="">none</option>
                  <option value=">">&gt;</option>
                  <option value=">=">&gt;=</option>
                  <option value="<">&lt;</option>
                  <option value="<=">&lt;=</option>
                  <option value="=">=</option>
                </select>
                <input id="ruleThresholdInput" type="number" step="0.01" placeholder="5.00">
              </span>
            </label>
            <label class="wide">Phrases <textarea id="rulePhrasesInput" rows="6" placeholder="μία φράση ανά γραμμή"></textarea></label>
          </div>
          <div class="toolbar editorActions">
            <button id="applyRuleBtn">Apply Rule</button>
            <span id="rulesStatus" class="noteText">Load a profile to edit rules.</span>
          </div>
        </div>
      </div>
    </section>

    <section id="reports" class="view">
      <div class="toolbar">
        <a class="button" href="/api/report?path=candidates.md" target="_blank">Open Candidates Markdown</a>
        <a class="button secondary" href="/api/report?path=candidates.json" target="_blank">Open Candidates JSON</a>
      </div>
      <p class="note">Οι υποψήφιοι μένουν candidate-only μέχρι να γίνει fetch του επίσημου detail resource.</p>
    </section>
  </main>
  <script src="/app.js"></script>
</body>
</html>
"""


STYLES_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --panel: #ffffff;
  --line: #d9dde5;
  --text: #1c2430;
  --muted: #647084;
  --accent: #146b63;
  --accent-dark: #0d4f49;
  --warn: #9a5b10;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  display: grid;
  grid-template-columns: 248px 1fr;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: Segoe UI, system-ui, -apple-system, sans-serif;
  font-size: 14px;
}
.sidebar {
  background: #202832;
  color: white;
  padding: 20px 14px;
}
.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 4px 6px 22px;
}
.mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid #8cbdb6;
  color: #b8e7df;
  font-weight: 700;
}
h1, h2, p { margin: 0; }
h1 { font-size: 17px; }
h2 { font-size: 21px; }
.brand p, header p, .note { color: var(--muted); }
nav { display: grid; gap: 6px; }
button, .button {
  border: 0;
  border-radius: 6px;
  background: var(--accent);
  color: white;
  min-height: 38px;
  padding: 0 14px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: inline-grid;
  place-items: center;
}
button:hover, .button:hover { background: var(--accent-dark); }
button:disabled { opacity: .55; cursor: wait; }
.secondary { background: #edf1f5; color: #23303f; border: 1px solid var(--line); }
.secondary:hover { background: #e1e7ee; }
.nav {
  justify-content: start;
  background: transparent;
  color: #dce6ef;
  border: 1px solid transparent;
}
.nav.active { background: #31404f; border-color: #4c6174; }
main { padding: 22px; min-width: 0; }
header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 18px;
}
.view { display: none; }
.view.active { display: block; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
  padding: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin-bottom: 14px;
}
.toolbar.compact { margin-top: -4px; }
label { display: grid; gap: 6px; color: var(--muted); font-size: 12px; font-weight: 700; }
input, select {
  min-height: 38px;
  min-width: 180px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0 10px;
  font: inherit;
  color: var(--text);
  background: white;
}
textarea {
  min-height: 128px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  font: inherit;
  color: var(--text);
  background: white;
  resize: vertical;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.metrics div {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.metrics span { display: block; font-size: 24px; font-weight: 750; }
.metrics small { color: var(--muted); }
.tableWrap {
  overflow: auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
table { width: 100%; border-collapse: collapse; min-width: 880px; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { font-size: 12px; color: var(--muted); background: #f1f4f7; }
td:first-child { font-weight: 700; white-space: nowrap; }
td:nth-child(2) { white-space: nowrap; }
pre {
  margin: 0;
  min-height: 320px;
  max-height: 520px;
  overflow: auto;
  background: #151b22;
  color: #dce6ef;
  border-radius: 8px;
  padding: 14px;
  white-space: pre-wrap;
}
.note {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.rulesGrid {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  gap: 14px;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.panelHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
h3 {
  margin: 0;
  font-size: 16px;
}
.ruleList {
  display: grid;
  gap: 8px;
}
.ruleItem {
  width: 100%;
  min-height: 54px;
  justify-content: start;
  text-align: left;
  background: #f5f7fa;
  color: var(--text);
  border: 1px solid var(--line);
}
.ruleItem.active {
  background: #dcefeb;
  border-color: #8ac1b8;
}
.ruleItem small {
  color: var(--muted);
  font-weight: 600;
}
.editorGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 12px;
}
.editorGrid .wide {
  grid-column: 1 / -1;
}
.inlineControls {
  display: grid;
  grid-template-columns: 92px minmax(120px, 1fr);
  gap: 8px;
}
.inlineControls select,
.inlineControls input {
  min-width: 0;
}
.editorActions {
  margin: 14px 0 0;
}
.noteText {
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 820px) {
  body { grid-template-columns: 1fr; }
  .sidebar { position: static; }
  nav { grid-template-columns: repeat(4, 1fr); }
  main { padding: 14px; }
  .metrics { grid-template-columns: 1fr; }
  .rulesGrid,
  .editorGrid {
    grid-template-columns: 1fr;
  }
  .editorGrid .wide {
    grid-column: auto;
  }
}
"""


APP_JS = """
const state = {
  selected: null,
  profiles: [],
  evaluationProfiles: [],
  documentTypes: [],
  ruleProfilePath: null,
  evaluationConfig: null,
  selectedRuleId: null,
};
const $ = (id) => document.getElementById(id);

document.querySelectorAll('.nav').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
    button.classList.add('active');
    $(button.dataset.view).classList.add('active');
  });
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function splitList(value) {
  return String(value || '')
    .split(/[,\\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function setBusy(isBusy, text = 'Ready') {
  $('statusText').textContent = text;
  document.querySelectorAll('button').forEach((button) => { button.disabled = isBusy; });
}

function renderCandidates(payload) {
  const coverage = payload.coverage || {};
  $('candidateCount').textContent = payload.candidates.length;
  $('visibleRows').textContent = coverage.visible_rows_seen || 0;
  $('adfBodies').textContent = coverage.adf_response_bodies_checked || 0;
  const rows = $('candidateRows');
  rows.innerHTML = '';
  for (const candidate of payload.candidates) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(candidate.eshidis_id || '')}</td>
      <td>${escapeHtml(candidate.submission_deadline || '')}</td>
      <td>${escapeHtml(candidate.title || '')}</td>
      <td>${escapeHtml(candidate.status || '')}</td>
      <td><button class="secondary selectTender" data-id="${escapeHtml(candidate.eshidis_id)}">Use</button></td>
    `;
    rows.appendChild(tr);
  }
  document.querySelectorAll('.selectTender').forEach((button) => {
    button.addEventListener('click', () => {
      state.selected = button.dataset.id;
      $('eshidisInput').value = state.selected;
      document.querySelector('[data-view="tender"]').click();
    });
  });
}

async function refresh() {
  const status = await api('/api/status');
  state.profiles = status.profiles || [];
  state.evaluationProfiles = status.evaluation_profiles || [];
  state.documentTypes = status.document_types || [];
  const select = $('profileSelect');
  select.innerHTML = '';
  for (const profile of state.profiles) {
    const option = document.createElement('option');
    option.value = profile;
    option.textContent = profile.split('/').pop();
    select.appendChild(option);
  }
  const evaluationSelect = $('evaluationProfileSelect');
  evaluationSelect.innerHTML = '';
  for (const profile of state.evaluationProfiles) {
    const option = document.createElement('option');
    option.value = profile;
    option.textContent = profile.split('/').pop();
    evaluationSelect.appendChild(option);
  }
  const ruleProfileSelect = $('ruleProfileSelect');
  ruleProfileSelect.innerHTML = '';
  for (const profile of state.evaluationProfiles) {
    const option = document.createElement('option');
    option.value = profile;
    option.textContent = profile.split('/').pop();
    ruleProfileSelect.appendChild(option);
  }
  renderCandidates(await api('/api/candidates'));
  if (!state.evaluationConfig && ruleProfileSelect.value) {
    await loadRules();
  }
}

async function runAction(path, body, label) {
  setBusy(true, label);
  $('commandOutput').textContent = `${label}\\n`;
  try {
    const result = await api(path, { method: 'POST', body: JSON.stringify(body || {}) });
    $('commandOutput').textContent = JSON.stringify(result, null, 2);
    if (result.candidates) renderCandidates(result.candidates);
    $('statusText').textContent = result.ok === false ? 'Finished with errors' : 'Done';
  } catch (error) {
    $('commandOutput').textContent = String(error);
    $('statusText').textContent = 'Error';
  } finally {
    setBusy(false, $('statusText').textContent);
  }
}

function selectedId() {
  return $('eshidisInput').value.trim();
}

async function loadRules() {
  const path = $('ruleProfileSelect').value || $('evaluationProfileSelect').value;
  if (!path) return;
  const result = await api(`/api/evaluation-profile?path=${encodeURIComponent(path)}`);
  state.ruleProfilePath = result.path;
  state.evaluationConfig = result.data;
  state.selectedRuleId = (result.data.rules[0] || {}).id || null;
  renderRules();
  fillRuleForm(currentRule());
  $('rulesStatus').textContent = `Loaded ${result.data.rules.length} rules.`;
}

function currentRule() {
  const rules = ((state.evaluationConfig || {}).rules || []);
  return rules.find((rule) => rule.id === state.selectedRuleId) || null;
}

function renderRules() {
  const list = $('ruleList');
  list.innerHTML = '';
  const rules = ((state.evaluationConfig || {}).rules || []);
  if (!rules.length) {
    list.innerHTML = '<p class="noteText">No rules yet.</p>';
    return;
  }
  for (const rule of rules) {
    const button = document.createElement('button');
    button.className = `ruleItem ${rule.id === state.selectedRuleId ? 'active' : ''}`;
    button.dataset.id = rule.id;
    button.innerHTML = `
      <span>${escapeHtml(rule.label || rule.id)}</span>
      <small>${escapeHtml(rule.id)} · +${escapeHtml(rule.score || 0)} · ${escapeHtml(rule.severity || 'info')}</small>
    `;
    button.addEventListener('click', () => {
      state.selectedRuleId = rule.id;
      renderRules();
      fillRuleForm(rule);
    });
    list.appendChild(button);
  }
}

function fillRuleForm(rule) {
  $('ruleIdInput').value = rule?.id || '';
  $('ruleLabelInput').value = rule?.label || '';
  $('ruleSeverityInput').value = rule?.severity || 'info';
  $('ruleScoreInput').value = rule?.score ?? 1;
  $('ruleDocumentTypesInput').value = (rule?.document_types || []).join(', ');
  $('rulePhrasesInput').value = (rule?.phrases || []).join('\\n');
  $('ruleOperatorInput').value = rule?.numeric?.operator || '';
  $('ruleThresholdInput').value = rule?.numeric?.threshold ?? '';
}

function ruleFromForm() {
  const id = $('ruleIdInput').value.trim();
  const phrases = splitList($('rulePhrasesInput').value);
  if (!id) throw new Error('Rule id is required.');
  if (!phrases.length) throw new Error('At least one phrase is required.');
  const rule = {
    id,
    label: $('ruleLabelInput').value.trim() || id,
    severity: $('ruleSeverityInput').value,
    score: Number($('ruleScoreInput').value || 1),
    document_types: splitList($('ruleDocumentTypesInput').value),
    phrases,
  };
  const operator = $('ruleOperatorInput').value;
  const threshold = $('ruleThresholdInput').value;
  if (operator && threshold !== '') {
    rule.numeric = { operator, threshold: Number(threshold) };
  }
  return rule;
}

function applyRule() {
  if (!state.evaluationConfig) {
    state.evaluationConfig = { profile: { id: 'public_works_dynamic', name: 'Dynamic public works evaluation', description: '' }, rules: [] };
  }
  const rule = ruleFromForm();
  const rules = state.evaluationConfig.rules || [];
  const index = rules.findIndex((item) => item.id === state.selectedRuleId || item.id === rule.id);
  if (index >= 0) {
    rules[index] = rule;
  } else {
    rules.push(rule);
  }
  state.evaluationConfig.rules = rules;
  state.selectedRuleId = rule.id;
  renderRules();
  $('rulesStatus').textContent = 'Rule applied locally. Press Save Rules to write it.';
}

async function saveRules() {
  applyRule();
  const path = state.ruleProfilePath || $('ruleProfileSelect').value;
  const result = await api('/api/evaluation-profile', {
    method: 'POST',
    body: JSON.stringify({ path, data: state.evaluationConfig }),
  });
  state.evaluationConfig = result.data;
  state.ruleProfilePath = result.path;
  renderRules();
  $('rulesStatus').textContent = `Saved ${result.data.rules.length} rules.`;
}

function newRule() {
  state.selectedRuleId = null;
  fillRuleForm({
    id: `rule_${Date.now()}`,
    label: '',
    severity: 'info',
    score: 1,
    document_types: [],
    phrases: [],
  });
  renderRules();
  $('rulesStatus').textContent = 'Fill the new rule and press Apply Rule.';
}

function deleteRule() {
  if (!state.evaluationConfig || !state.selectedRuleId) return;
  state.evaluationConfig.rules = (state.evaluationConfig.rules || []).filter((rule) => rule.id !== state.selectedRuleId);
  state.selectedRuleId = (state.evaluationConfig.rules[0] || {}).id || null;
  renderRules();
  fillRuleForm(currentRule());
  $('rulesStatus').textContent = 'Rule removed locally. Press Save Rules to write it.';
}

$('refreshBtn').addEventListener('click', refresh);
$('discoverBtn').addEventListener('click', () => runAction('/api/discover', { limit: $('limitInput').value }, 'Running discovery...'));
$('fetchBtn').addEventListener('click', () => runAction('/api/fetch-resource', { eshidis_id: selectedId() }, 'Fetching official detail...'));
$('downloadBtn').addEventListener('click', () => runAction('/api/download-all', { eshidis_id: selectedId() }, 'Downloading attachments...'));
$('analyzeBtn').addEventListener('click', () => runAction('/api/analyze', { eshidis_id: selectedId() }, 'Analyzing documents...'));
$('searchBtn').addEventListener('click', () => runAction('/api/search', { eshidis_id: selectedId(), profile: $('profileSelect').value }, 'Running search profile...'));
$('evaluateBtn').addEventListener('click', () => runAction('/api/evaluate', { eshidis_id: selectedId(), profile: $('evaluationProfileSelect').value }, 'Running evaluation rules...'));
$('loadRulesBtn').addEventListener('click', () => loadRules().catch((error) => { $('rulesStatus').textContent = String(error); }));
$('saveRulesBtn').addEventListener('click', () => saveRules().catch((error) => { $('rulesStatus').textContent = String(error); }));
$('applyRuleBtn').addEventListener('click', () => {
  try { applyRule(); } catch (error) { $('rulesStatus').textContent = String(error); }
});
$('newRuleBtn').addEventListener('click', newRule);
$('deleteRuleBtn').addEventListener('click', deleteRule);

refresh().catch((error) => { $('statusText').textContent = String(error); });
"""


if __name__ == "__main__":
    raise SystemExit(main())
