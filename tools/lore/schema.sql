PRAGMA foreign_keys = ON;

-- Build state for the derived index. `rebuild` is fail-open, so read commands
-- use this to report what the index is missing instead of failing silently:
-- how many records were skipped as invalid, and whether the canonical Markdown
-- has changed since the index was built.
CREATE TABLE IF NOT EXISTS index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('workspace', 'repository')),
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN (
            'topic_summary','decision','constraint','fix',
            'investigation','migration','incident','lesson','reference','feature'
        )
    ),
    status TEXT NOT NULL DEFAULT 'current' CHECK (
        status IN ('current','resolved','superseded','deprecated','historical')
    ),
    importance TEXT NOT NULL DEFAULT 'normal' CHECK (
        importance IN ('critical','high','normal','low')
    ),
    scope TEXT NOT NULL DEFAULT 'local' CHECK (
        scope IN ('workspace','repository','subsystem','feature','local')
    ),
    risk TEXT NOT NULL DEFAULT 'low' CHECK (
        risk IN ('critical','high','medium','low','none')
    ),
    durability TEXT NOT NULL DEFAULT 'situational' CHECK (
        durability IN ('invariant','long_lived','situational','temporary')
    ),
    evidence TEXT NOT NULL DEFAULT 'documented' CHECK (
        evidence IN ('verified','documented','observed','inferred')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    UNIQUE(collection_id, path)
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    topic_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    summary_entry_id TEXT REFERENCES entries(id) ON DELETE SET NULL,
    UNIQUE(collection_id, topic_key)
);

CREATE TABLE IF NOT EXISTS entry_topics (
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY(entry_id, topic_id)
);

CREATE TABLE IF NOT EXISTS relations (
    source_entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    target_entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN (
            'supersedes','depends_on','related_to','caused_by','contradicts'
        )
    ),
    PRIMARY KEY(source_entry_id, target_entry_id, relation_type)
);

CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(
    entry_id UNINDEXED,
    title,
    summary,
    body,
    topics,
    tokenize = 'unicode61 remove_diacritics 2'
);
