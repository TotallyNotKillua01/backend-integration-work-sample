PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_code TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registered','received','processing','completed')) DEFAULT 'registered',
    registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_id INTEGER NOT NULL UNIQUE,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')) DEFAULT 'queued',
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (kit_id) REFERENCES kits(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_id INTEGER NOT NULL UNIQUE,
    report_version TEXT NOT NULL,
    summary TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kit_id) REFERENCES kits(id) ON DELETE CASCADE
);
