PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenders (
    id INTEGER PRIMARY KEY,
    eshidis_id TEXT UNIQUE,
    adam TEXT,
    ada TEXT,
    cpv_code TEXT,
    title TEXT NOT NULL,
    authority_name TEXT,
    region TEXT,
    regional_unit TEXT,
    municipality TEXT,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    status_confidence REAL NOT NULL DEFAULT 0.0,
    published_at TEXT,
    current_deadline_at TEXT,
    budget_without_vat REAL,
    budget_with_vat REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tender_sources (
    id INTEGER PRIMARY KEY,
    tender_id INTEGER NOT NULL REFERENCES tenders(id),
    source_type TEXT NOT NULL,
    source_url TEXT,
    retrieved_at TEXT NOT NULL,
    evidence_summary TEXT,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    tender_id INTEGER NOT NULL REFERENCES tenders(id),
    original_name TEXT NOT NULL,
    local_path TEXT,
    source_url TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    retrieved_at TEXT,
    is_latest INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    attachment_id INTEGER NOT NULL REFERENCES attachments(id),
    document_type TEXT NOT NULL DEFAULT 'other',
    classification_confidence REAL NOT NULL DEFAULT 0.0,
    extraction_status TEXT NOT NULL DEFAULT 'PENDING',
    page_or_sheet_count INTEGER,
    text_sample TEXT,
    text_path TEXT,
    extraction_error TEXT,
    analyzed_at TEXT
);

CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY,
    profile_id TEXT,
    request_path TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS search_hits (
    id INTEGER PRIMARY KEY,
    search_run_id INTEGER NOT NULL REFERENCES search_runs(id),
    tender_id INTEGER REFERENCES tenders(id),
    document_id INTEGER REFERENCES documents(id),
    match_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    page_number INTEGER,
    sheet_name TEXT,
    row_number INTEGER,
    matched_text TEXT,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY,
    run_id INTEGER,
    stage TEXT NOT NULL,
    source_ref TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_state (
    source_id TEXT PRIMARY KEY,
    source_family TEXT,
    source_url TEXT,
    fingerprint TEXT,
    last_checked_at TEXT,
    last_changed_at TEXT,
    last_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    fingerprint TEXT,
    changed INTEGER NOT NULL DEFAULT 0,
    item_count INTEGER,
    error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(source_id) REFERENCES source_state(source_id)
);

CREATE INDEX IF NOT EXISTS idx_source_runs_source_started
ON source_runs(source_id, started_at);

CREATE TABLE IF NOT EXISTS tender_dismissals (
    row_key TEXT PRIMARY KEY,
    display_id TEXT,
    source_label TEXT,
    title TEXT,
    reason TEXT,
    ignored_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY,
    row_key TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    subject TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(row_key, channel, recipient)
);
