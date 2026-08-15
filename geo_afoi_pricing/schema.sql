CREATE TABLE IF NOT EXISTS geo_projects (
    id INTEGER PRIMARY KEY,
    project_key TEXT NOT NULL UNIQUE,
    source_root TEXT NOT NULL,
    project_path TEXT NOT NULL,
    project_name TEXT NOT NULL,
    inferred_title TEXT,
    inferred_budget REAL,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS geo_source_files (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES geo_projects(id),
    source_path TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT,
    size_bytes INTEGER,
    modified_at TEXT,
    sha256 TEXT,
    document_role TEXT NOT NULL DEFAULT 'UNKNOWN',
    candidate_reason TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'PENDING',
    extracted_text_path TEXT,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_geo_source_files_project
ON geo_source_files(project_id);

CREATE INDEX IF NOT EXISTS idx_geo_source_files_role
ON geo_source_files(document_role);

CREATE TABLE IF NOT EXISTS geo_budget_chapters (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES geo_projects(id),
    source_file_id INTEGER REFERENCES geo_source_files(id),
    chapter_code TEXT,
    chapter_title TEXT NOT NULL,
    repaired_chapter_title TEXT,
    canonical_chapter_title TEXT,
    row_order INTEGER,
    amount REAL,
    raw_text TEXT,
    confidence REAL NOT NULL DEFAULT 0.0,
    chapter_quality_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, source_file_id, chapter_code, chapter_title)
);

CREATE TABLE IF NOT EXISTS geo_budget_rows (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES geo_projects(id),
    source_file_id INTEGER REFERENCES geo_source_files(id),
    chapter_id INTEGER REFERENCES geo_budget_chapters(id),
    article_identity_id INTEGER REFERENCES geo_article_identities(id),
    row_number INTEGER,
    article_code TEXT,
    canonical_article_code TEXT,
    repaired_article_code TEXT,
    repaired_canonical_article_code TEXT,
    revision_codes_json TEXT NOT NULL DEFAULT '[]',
    repaired_revision_codes_json TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    unit TEXT,
    quantity REAL,
    unit_price REAL,
    amount REAL,
    page_number INTEGER,
    sheet_name TEXT,
    line_ref TEXT,
    raw_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    article_quality_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    usable_for_stats INTEGER NOT NULL DEFAULT 0,
    extracted_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, source_file_id, chapter_id, row_number, canonical_article_code, description)
);

CREATE INDEX IF NOT EXISTS idx_geo_budget_rows_article
ON geo_budget_rows(canonical_article_code);

CREATE INDEX IF NOT EXISTS idx_geo_budget_rows_chapter
ON geo_budget_rows(chapter_id);

CREATE TABLE IF NOT EXISTS geo_article_identities (
    id INTEGER PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    canonical_article_code TEXT NOT NULL,
    canonical_revision_codes_json TEXT NOT NULL DEFAULT '[]',
    canonical_unit TEXT,
    canonical_chapter_title TEXT,
    status TEXT NOT NULL DEFAULT 'NEEDS_REVIEW',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_geo_article_identities_article
ON geo_article_identities(canonical_article_code);

CREATE TABLE IF NOT EXISTS geo_article_aliases (
    id INTEGER PRIMARY KEY,
    identity_id INTEGER NOT NULL REFERENCES geo_article_identities(id),
    alias_type TEXT NOT NULL,
    alias_value TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    review_status TEXT NOT NULL DEFAULT 'NEEDS_REVIEW',
    rationale TEXT,
    first_seen_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(identity_id, alias_type, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_geo_article_aliases_normalized
ON geo_article_aliases(alias_type, normalized_alias);

CREATE TABLE IF NOT EXISTS geo_article_stats (
    id INTEGER PRIMARY KEY,
    article_identity_id INTEGER REFERENCES geo_article_identities(id),
    canonical_article_code TEXT NOT NULL,
    chapter_title TEXT,
    unit TEXT,
    sample_count INTEGER NOT NULL,
    project_count INTEGER NOT NULL,
    mean_unit_price REAL,
    median_unit_price REAL,
    min_unit_price REAL,
    max_unit_price REAL,
    stdev_unit_price REAL,
    computed_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(canonical_article_code, chapter_title, unit)
);

CREATE TABLE IF NOT EXISTS geo_extraction_events (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id INTEGER REFERENCES geo_projects(id),
    source_file_id INTEGER REFERENCES geo_source_files(id),
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_geo_extraction_events_run
ON geo_extraction_events(run_id);

CREATE TABLE IF NOT EXISTS geo_runs (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL,
    source_root TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);
