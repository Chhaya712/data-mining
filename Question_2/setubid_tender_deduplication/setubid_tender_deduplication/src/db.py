"""
Section B(d) -- the retrieval structure gets a home and an access path.

Design notes that the DDL below encodes:

* `band_bucket` is the structure A(c) consults at lookup time. It is declared
  WITHOUT ROWID with primary key (band_no, band_hash, notice_id). In SQLite a
  WITHOUT ROWID table *is* a B-tree keyed on the primary key: the row lives in
  the index leaf. A probe for one band key is therefore a single descent to the
  leftmost matching leaf followed by a sequential scan of physically adjacent
  entries -- the members of one bucket sit next to each other on the same page.
  A conventional rowid table with a secondary index on (band_no, band_hash)
  would descend the index B-tree, collect rowids, and then perform one extra
  descent of the *table* B-tree per matching row. That second descent is the
  cost we refuse to pay, because a bucket probe returns many rows and we want
  all of them. exp_d measures both.

* `signature` holds the reduced form as a BLOB (K uint32, little-endian). It
  survives process restart, which is the whole point: a nightly run that dies
  at minute 12 restarts from the database, not from the Parquet files.

* `opportunity` / `notice_opportunity` / `opportunity_alias` implement the
  head of product's second constraint. See src/cluster.py.
"""
from __future__ import annotations

import os
import sqlite3

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS notice (
    notice_id       TEXT PRIMARY KEY,
    portal_id       TEXT NOT NULL,
    published_at    TEXT,
    title           TEXT,
    estimated_value REAL,
    closing_date    TEXT,
    shingle_count   INTEGER NOT NULL,
    content_key     TEXT NOT NULL          -- hash of the normalised text
);
CREATE INDEX IF NOT EXISTS ix_notice_portal ON notice(portal_id);

CREATE TABLE IF NOT EXISTS signature (
    notice_id TEXT PRIMARY KEY REFERENCES notice(notice_id),
    k         INTEGER NOT NULL,
    sig       BLOB    NOT NULL
) WITHOUT ROWID;

-- the retrieval structure -------------------------------------------------
CREATE TABLE IF NOT EXISTS band_bucket (
    band_no    INTEGER NOT NULL,
    band_hash  INTEGER NOT NULL,
    notice_id  TEXT    NOT NULL,
    PRIMARY KEY (band_no, band_hash, notice_id)
) WITHOUT ROWID;

-- the same data in the rejected physical layout, built only by exp_d so the
-- comparison is like-for-like on identical rows.
CREATE TABLE IF NOT EXISTS band_bucket_rowid (
    band_no    INTEGER NOT NULL,
    band_hash  INTEGER NOT NULL,
    notice_id  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bucket_stat (
    band_no   INTEGER NOT NULL,
    band_hash INTEGER NOT NULL,
    members   INTEGER NOT NULL,
    suppressed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (band_no, band_hash)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS pair_score (
    a   TEXT NOT NULL,
    b   TEXT NOT NULL,
    est REAL NOT NULL,
    PRIMARY KEY (a, b)
) WITHOUT ROWID;

-- stable identity ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunity (
    opportunity_id TEXT PRIMARY KEY,
    seq            INTEGER NOT NULL,      -- mint order; oldest wins on merge
    anchor_notice  TEXT NOT NULL,
    created_run    INTEGER NOT NULL,
    retired_run    INTEGER
);

CREATE TABLE IF NOT EXISTS notice_opportunity (
    notice_id      TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunity(opportunity_id),
    assigned_run   INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_no_opp ON notice_opportunity(opportunity_id);

-- a bookmark to a retired id must keep resolving
CREATE TABLE IF NOT EXISTS opportunity_alias (
    old_id     TEXT PRIMARY KEY,
    new_id     TEXT NOT NULL,
    merged_run INTEGER NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS run (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    notices    INTEGER,
    candidates INTEGER,
    merges     INTEGER,
    seconds    REAL,
    note       TEXT
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA cache_size = -200000;")   # ~200 MB page cache
    con.execute("PRAGMA temp_store = MEMORY;")
    return con


def init(path: str, fresh: bool = False) -> sqlite3.Connection:
    if fresh and os.path.exists(path):
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    con = connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


def resolve_bookmark(con: sqlite3.Connection, opportunity_id: str) -> str:
    """Follow the alias chain. A card id a bidder bookmarked in March still
    resolves to whatever opportunity absorbed it by September."""
    seen = set()
    cur = opportunity_id
    while True:
        if cur in seen:
            raise RuntimeError(f"alias cycle at {cur}")
        seen.add(cur)
        row = con.execute("SELECT new_id FROM opportunity_alias WHERE old_id=?", (cur,)).fetchone()
        if row is None:
            return cur
        cur = row[0]
