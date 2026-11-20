"""Versioned changes to the database layout.

Each migration runs once, in order. SQLite's built-in `user_version`
number remembers how many have run. To change the layout later, ADD a new
entry at the end; never edit one that has already shipped.
"""

from __future__ import annotations

import sqlite3

# UTC time as text, e.g. 2026-11-09T21:00:00Z
NOW = "(strftime('%Y-%m-%dT%H:%M:%SZ','now'))"

MIGRATIONS: list[str] = [
    # 1: the starting layout.
    f"""
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        platform TEXT NOT NULL,              -- tiktok, youtube, instagram, facebook
        url TEXT NOT NULL,
        external_id TEXT,                    -- the platform's own id, if known
        author TEXT,
        caption TEXT,
        title TEXT,
        description TEXT,
        thumbnail_url TEXT,
        thumbnail_path TEXT,                 -- local copy, for offline viewing
        duration_s REAL,
        saved_at TEXT,
        platform_collection TEXT,
        status TEXT NOT NULL DEFAULT 'imported',
        error TEXT,
        done INTEGER NOT NULL DEFAULT 0,
        safe_to_unsave INTEGER NOT NULL DEFAULT 0,
        unsaved INTEGER NOT NULL DEFAULT 0,  -- the user has unsaved it on the platform
        created_at TEXT NOT NULL DEFAULT {NOW},
        updated_at TEXT NOT NULL DEFAULT {NOW},
        UNIQUE (platform, url)
    );
    CREATE INDEX items_status ON items (status);

    CREATE TABLE transcripts (
        item_id INTEGER PRIMARY KEY REFERENCES items (id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        language TEXT,
        source TEXT,                         -- e.g. "whisper-small"
        created_at TEXT NOT NULL DEFAULT {NOW}
    );

    CREATE TABLE ai_results (
        item_id INTEGER PRIMARY KEY REFERENCES items (id) ON DELETE CASCADE,
        category TEXT,
        title TEXT,
        summary TEXT,
        steps_json TEXT NOT NULL DEFAULT '[]',
        tags TEXT NOT NULL DEFAULT '[]',     -- JSON list of strings
        provider TEXT,
        model TEXT,
        confidence REAL,
        created_at TEXT NOT NULL DEFAULT {NOW},
        updated_at TEXT NOT NULL DEFAULT {NOW}
    );

    CREATE TABLE collections (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT {NOW}
    );

    CREATE TABLE item_collections (
        item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
        collection_id INTEGER NOT NULL REFERENCES collections (id) ON DELETE CASCADE,
        PRIMARY KEY (item_id, collection_id)
    );

    CREATE TABLE embeddings (
        item_id INTEGER PRIMARY KEY REFERENCES items (id) ON DELETE CASCADE,
        model TEXT NOT NULL,
        dim INTEGER NOT NULL,
        vector BLOB NOT NULL,                -- float32 numbers
        text_hash TEXT,                      -- re-embed when the text changes
        created_at TEXT NOT NULL DEFAULT {NOW}
    );

    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL,                -- queued, running, paused, done, failed, cancelled, interrupted
        progress INTEGER NOT NULL DEFAULT 0,
        total INTEGER NOT NULL DEFAULT 0,
        message TEXT,
        error TEXT,
        params_json TEXT NOT NULL DEFAULT '{{}}',
        result_json TEXT,
        created_at TEXT NOT NULL DEFAULT {NOW},
        updated_at TEXT NOT NULL DEFAULT {NOW},
        finished_at TEXT
    );

    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL
    );
    """,
    # 2: enrichment. When the video was posted, when the app got its
    # details and transcript, and how long that took (seconds).
    """
    ALTER TABLE items ADD COLUMN posted_at TEXT;
    ALTER TABLE items ADD COLUMN enriched_at TEXT;
    ALTER TABLE items ADD COLUMN enrich_seconds REAL;
    CREATE INDEX items_saved_at ON items (saved_at);
    """,
    # 3: AI notes and sorting.
    # collections.origin: mine (the user's list), ai (made up by the AI),
    #   platform (copied from a TikTok/Instagram/... collection).
    # item_collections.source: who put the item there: user, rule, ai, platform.
    #   Re-sorting never touches the user's own choices.
    # items.needs_review: the AI wasn't sure, so it waits in the inbox.
    """
    ALTER TABLE collections ADD COLUMN origin TEXT NOT NULL DEFAULT 'mine';
    ALTER TABLE collections ADD COLUMN description TEXT;
    ALTER TABLE collections ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE item_collections ADD COLUMN source TEXT NOT NULL DEFAULT 'user';
    ALTER TABLE item_collections ADD COLUMN confidence REAL;
    CREATE INDEX item_collections_collection ON item_collections (collection_id);
    ALTER TABLE ai_results ADD COLUMN kind TEXT;
    ALTER TABLE ai_results ADD COLUMN facts_json TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE ai_results ADD COLUMN suggestions_json TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE ai_results ADD COLUMN new_collection TEXT;
    ALTER TABLE items ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE items ADD COLUMN review_reason TEXT;
    ALTER TABLE items ADD COLUMN processed_at TEXT;
    ALTER TABLE items ADD COLUMN sorted_at TEXT;
    CREATE INDEX items_needs_review ON items (needs_review);
    """,
    # 4: search. See _search_migration() below.
    "",  # filled in right after this list
]


def _json_words(column: str) -> str:
    """SQL that turns a JSON list (of strings, or of {"text": ...} steps)
    into plain words, so JSON punctuation never ends up in the index."""
    return (
        "coalesce((SELECT group_concat(CASE WHEN j.type = 'object' THEN json_extract(j.value, '$.text') "
        f"ELSE j.value END, ' ') FROM json_each(CASE WHEN json_valid({column}) THEN {column} ELSE '[]' END) j), '')"
    )


# The three columns of one item's index row (see _search_migration).
_SEARCH_ROW = f"""
        SELECT i.id,
               trim(coalesce(i.title, '') || ' ' || coalesce(i.caption, '') || ' ' ||
                    coalesce(i.description, '') || ' ' || coalesce(i.author, '')),
               coalesce(t.text, ''),
               trim(coalesce(a.title, '') || ' ' || coalesce(a.summary, '') || ' ' ||
                    {_json_words('a.facts_json')} || ' ' || {_json_words('a.steps_json')} || ' ' ||
                    {_json_words('a.tags')})
        FROM items i
        LEFT JOIN transcripts t ON t.item_id = i.id
        LEFT JOIN ai_results a ON a.item_id = i.id"""


def _search_migration() -> str:
    """Keyword index (SQLite FTS5) kept up to date by triggers, plus tables
    for the "similar meaning" search.

    search_fts has one row per item (rowid = item id) with three columns:
      about      - title, caption, description and creator
      transcript - what is said in the video
      notes      - the AI's title, summary, key details, steps and tags
    The porter tokenizer lets "cooking" match "cook" and "cooked".
    """
    triggers = [
        """CREATE TRIGGER search_items_ad AFTER DELETE ON items BEGIN
        DELETE FROM search_fts WHERE rowid = OLD.id;
    END;"""
    ]
    for name, table, event, ref in [
        ("items_ai", "items", "INSERT", "NEW.id"),
        ("items_au", "items", "UPDATE OF title, caption, description, author", "NEW.id"),
        ("transcripts_ai", "transcripts", "INSERT", "NEW.item_id"),
        ("transcripts_au", "transcripts", "UPDATE", "NEW.item_id"),
        ("transcripts_ad", "transcripts", "DELETE", "OLD.item_id"),
        ("ai_results_ai", "ai_results", "INSERT", "NEW.item_id"),
        ("ai_results_au", "ai_results", "UPDATE OF title, summary, facts_json, steps_json, tags", "NEW.item_id"),
        ("ai_results_ad", "ai_results", "DELETE", "OLD.item_id"),
    ]:
        triggers.append(
            f"CREATE TRIGGER search_{name} AFTER {event} ON {table} BEGIN\n"
            f"        DELETE FROM search_fts WHERE rowid = {ref};\n"
            f"        INSERT INTO search_fts (rowid, about, transcript, notes) {_SEARCH_ROW}\n"
            f"        WHERE i.id = {ref};\n    END;"
        )
    return "\n".join(
        [
            """
    CREATE VIRTUAL TABLE search_fts USING fts5(
        about, transcript, notes,
        tokenize = 'porter unicode61 remove_diacritics 2'
    );""",
            *triggers,
            # Fill the index for the items that are already there.
            f"INSERT INTO search_fts (rowid, about, transcript, notes) {_SEARCH_ROW};",
            """
    -- "Similar meaning" search: each item's text cut into short passages,
    -- each stored with its meaning as numbers (a float32 vector).
    CREATE TABLE search_passages (
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
        part TEXT NOT NULL,              -- about, transcript, notes
        start_char INTEGER NOT NULL,     -- where the passage starts in that part
        text TEXT NOT NULL,
        vector BLOB NOT NULL
    );
    CREATE INDEX search_passages_item ON search_passages (item_id);

    -- Which items have passages, made from which text (re-done when it changes).
    CREATE TABLE search_indexed (
        item_id INTEGER PRIMARY KEY REFERENCES items (id) ON DELETE CASCADE,
        model TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        indexed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
    );
    """,
        ]
    )


MIGRATIONS[3] = _search_migration()

# 5: when the user started an item's steps, finished it, and unsaved it on
# the platform (for the Plans view and the "Safe to unsave" checklist).
MIGRATIONS.append("""
    ALTER TABLE items ADD COLUMN started_at TEXT;
    ALTER TABLE items ADD COLUMN done_at TEXT;
    ALTER TABLE items ADD COLUMN unsaved_at TEXT;
""")


# The notes column of the search index from version 6 on: tags come from
# item_tags (the AI's, the user's and the rules'), not from ai_results.tags.
_SEARCH_ROW_V6 = _SEARCH_ROW.replace(
    _json_words("a.tags"),
    "coalesce((SELECT group_concat(tg.name, ' ') FROM item_tags it JOIN tags tg ON tg.id = it.tag_id "
    "WHERE it.item_id = i.id), '')",
)

_OLD_SEARCH_TRIGGERS = [
    "items_ai", "items_au", "transcripts_ai", "transcripts_au", "transcripts_ad",
    "ai_results_ai", "ai_results_au", "ai_results_ad",
]


def _folders_and_tags_migration() -> str:
    """6: folders, AI choices per collection, and tags of their own.

    collections.parent_id: a collection can sit inside another one (a folder),
      shown as a tree in the sidebar. NULL = at the top.
    collections.ai_allowed: 0 = the AI never files videos here (the user's
      own collection, filled by hand or by rules).
    collections.color / collapsed: how it looks in the sidebar.
    tags + item_tags: tags as real rows, so the user can add, rename, merge
      and filter by them. item_tags.source: user, ai, rule or auto (the
      "not in any collection" tag). The AI's old tags are copied over.
    """
    tag_list = "json_each(CASE WHEN json_valid(a.tags) THEN a.tags ELSE '[]' END)"
    refresh = (
        "        DELETE FROM search_fts WHERE rowid = {ref};\n"
        f"        INSERT INTO search_fts (rowid, about, transcript, notes) {_SEARCH_ROW_V6}\n"
        "        WHERE i.id = {ref};"
    )
    triggers = [f"DROP TRIGGER IF EXISTS search_{name};" for name in _OLD_SEARCH_TRIGGERS]
    for name, table, event, ref in [
        ("items_ai", "items", "INSERT", "NEW.id"),
        ("items_au", "items", "UPDATE OF title, caption, description, author", "NEW.id"),
        ("transcripts_ai", "transcripts", "INSERT", "NEW.item_id"),
        ("transcripts_au", "transcripts", "UPDATE", "NEW.item_id"),
        ("transcripts_ad", "transcripts", "DELETE", "OLD.item_id"),
        ("ai_results_ai", "ai_results", "INSERT", "NEW.item_id"),
        ("ai_results_au", "ai_results", "UPDATE OF title, summary, facts_json, steps_json", "NEW.item_id"),
        ("ai_results_ad", "ai_results", "DELETE", "OLD.item_id"),
        ("item_tags_ai", "item_tags", "INSERT", "NEW.item_id"),
        ("item_tags_ad", "item_tags", "DELETE", "OLD.item_id"),
    ]:
        triggers.append(
            f"CREATE TRIGGER search_{name} AFTER {event} ON {table} BEGIN\n{refresh.format(ref=ref)}\n    END;"
        )
    # Renaming a tag changes the index row of every item that has it.
    triggers.append(
        "CREATE TRIGGER search_tags_au AFTER UPDATE OF name ON tags BEGIN\n"
        "        DELETE FROM search_fts WHERE rowid IN (SELECT item_id FROM item_tags WHERE tag_id = NEW.id);\n"
        f"        INSERT INTO search_fts (rowid, about, transcript, notes) {_SEARCH_ROW_V6}\n"
        "        WHERE i.id IN (SELECT item_id FROM item_tags WHERE tag_id = NEW.id);\n    END;"
    )
    return "\n".join([
        f"""
    ALTER TABLE collections ADD COLUMN parent_id INTEGER REFERENCES collections (id) ON DELETE SET NULL;
    ALTER TABLE collections ADD COLUMN ai_allowed INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE collections ADD COLUMN color TEXT;
    ALTER TABLE collections ADD COLUMN collapsed INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX collections_parent ON collections (parent_id);

    CREATE TABLE tags (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        color TEXT,
        created_at TEXT NOT NULL DEFAULT {NOW}
    );
    CREATE TABLE item_tags (
        item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
        source TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL DEFAULT {NOW},
        PRIMARY KEY (item_id, tag_id)
    );
    CREATE INDEX item_tags_tag ON item_tags (tag_id);

    INSERT OR IGNORE INTO tags (name)
        SELECT DISTINCT lower(trim(j.value)) FROM ai_results a, {tag_list} j
        WHERE j.type = 'text' AND trim(j.value) <> '';
    INSERT OR IGNORE INTO item_tags (item_id, tag_id, source)
        SELECT a.item_id, t.id, 'ai' FROM ai_results a, {tag_list} j
        JOIN tags t ON t.name = lower(trim(j.value))
        WHERE j.type = 'text';
    """,
        *triggers,
        "DELETE FROM search_fts;",
        f"INSERT INTO search_fts (rowid, about, transcript, notes) {_SEARCH_ROW_V6};",
    ])


MIGRATIONS.append(_folders_and_tags_migration())

# 7: plans of their own, saved AI Assistant chats, and links from platform
# collections to the app's collections. Collections become one flat list
# (broad topics like Food or Travel); tags are the small, detailed words.
#
# plans + plan_items: a plan holds one or many saves, in order; each save
#   is ticked off on its own (plan_items.done), and the save's steps keep
#   their own ticks. Saves the user had started become one plan.
# chats + chat_messages: AI Assistant conversations. chats.tool is what kind
#   (ask, summary, plan, shopping, ...) and target_json what it is about
#   (a collection, tag or plan). sources_json: the saves an answer used.
# platform_links: "TikTok collection 'recipes' -> my Food". mode auto: new
#   and existing saves from it are filed by themselves; manual: only when the
#   user presses "Add now".
MIGRATIONS.append(
    f"""
    UPDATE collections SET parent_id = NULL;

    CREATE TABLE plans (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        note TEXT,
        color TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        done_at TEXT,
        created_at TEXT NOT NULL DEFAULT {NOW},
        updated_at TEXT NOT NULL DEFAULT {NOW}
    );
    CREATE TABLE plan_items (
        plan_id INTEGER NOT NULL REFERENCES plans (id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
        position INTEGER NOT NULL DEFAULT 0,
        done INTEGER NOT NULL DEFAULT 0,
        done_at TEXT,
        added_at TEXT NOT NULL DEFAULT {NOW},
        PRIMARY KEY (plan_id, item_id)
    );
    CREATE INDEX plan_items_item ON plan_items (item_id);

    INSERT INTO plans (name, position)
        SELECT 'Things I started', 1 WHERE EXISTS (SELECT 1 FROM items WHERE started_at IS NOT NULL OR done = 1);
    INSERT INTO plan_items (plan_id, item_id, position, done, done_at)
        SELECT (SELECT MAX(id) FROM plans), id, ROW_NUMBER() OVER (ORDER BY started_at, id), done, done_at
        FROM items WHERE started_at IS NOT NULL OR done = 1;

    CREATE TABLE chats (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL DEFAULT 'New chat',
        tool TEXT NOT NULL DEFAULT 'ask',
        target_json TEXT,
        created_at TEXT NOT NULL DEFAULT {NOW},
        updated_at TEXT NOT NULL DEFAULT {NOW}
    );
    CREATE TABLE chat_messages (
        id INTEGER PRIMARY KEY,
        chat_id INTEGER NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources_json TEXT,
        found INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT {NOW}
    );
    CREATE INDEX chat_messages_chat ON chat_messages (chat_id, id);

    CREATE TABLE platform_links (
        id INTEGER PRIMARY KEY,
        platform TEXT NOT NULL,
        name TEXT NOT NULL COLLATE NOCASE,
        collection_id INTEGER REFERENCES collections (id) ON DELETE SET NULL,
        mode TEXT NOT NULL DEFAULT 'auto',
        created_at TEXT NOT NULL DEFAULT {NOW},
        UNIQUE (platform, name)
    );
    """
)


# 8: spaces, and collections inside collections again.
#
# spaces: separate areas for collections ("My saves", "Work", ...), shown as
#   tabs at the top of the Collections page. Every collection is in one space
#   (collections.space_id); the first space is made here and holds everything
#   that existed. collections.parent_id (kept from migration 6) is used again:
#   a collection can sit inside another one in the same space.
MIGRATIONS.append(
    f"""
    CREATE TABLE spaces (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        color TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT {NOW}
    );
    INSERT INTO spaces (id, name, position) VALUES (1, 'My saves', 1);
    ALTER TABLE collections ADD COLUMN space_id INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX collections_space ON collections (space_id, parent_id, position);
    """
)


# 9: deleting saves.
#
# items.deleted_at: set when the user deletes a save. It then only shows in
#   the Archive, from where it can be put back or deleted for good.
# removed_links: the links of saves deleted for good, so importing the same
#   export again doesn't bring them back.
MIGRATIONS.append(
    f"""
    ALTER TABLE items ADD COLUMN deleted_at TEXT;
    CREATE INDEX items_deleted ON items (deleted_at);
    CREATE TABLE removed_links (
        platform TEXT NOT NULL,
        url TEXT NOT NULL,
        removed_at TEXT NOT NULL DEFAULT {NOW},
        PRIMARY KEY (platform, url)
    );
    """
)


# 10: plans in more depth.
#
# plans.due_on: the day it's for ("2026-12-24"), plans.pinned: kept at the top.
# plan_items.section: the part of the plan a save is in ("Day 1", "To buy");
#   plan_items.note: the user's own note on that save in this plan.
# plan_tasks: to-dos of the user's own in a plan ("Book the hotel"), ticked
#   off like the saves, optionally in a section.
MIGRATIONS.append(
    f"""
    ALTER TABLE plans ADD COLUMN due_on TEXT;
    ALTER TABLE plans ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE plan_items ADD COLUMN section TEXT;
    ALTER TABLE plan_items ADD COLUMN note TEXT;
    CREATE TABLE plan_tasks (
        id INTEGER PRIMARY KEY,
        plan_id INTEGER NOT NULL REFERENCES plans (id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        section TEXT,
        done INTEGER NOT NULL DEFAULT 0,
        done_at TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT {NOW}
    );
    CREATE INDEX plan_tasks_plan ON plan_tasks (plan_id, position);
    """
)

# 11: indexes that keep big libraries (tens of thousands of saves) quick.
# Only indexes: no data is changed.
MIGRATIONS.append(
    """
    -- The Library's usual order (newest saved first, deleted ones left out)
    -- straight from the index, so page 1 and page 300 are equally quick.
    DROP INDEX IF EXISTS items_deleted;
    CREATE INDEX items_live_saved ON items (deleted_at, saved_at DESC, id DESC);
    -- One platform picked in the top-left picker.
    CREATE INDEX items_platform ON items (platform, deleted_at);
    -- Counting saves per tag without reading every save.
    CREATE INDEX item_tags_count ON item_tags (tag_id, source, item_id);
    -- The Safe to unsave list.
    CREATE INDEX items_safe ON items (safe_to_unsave) WHERE safe_to_unsave = 1;
    -- Which plans a save is in.
    CREATE INDEX IF NOT EXISTS plan_items_item ON plan_items (item_id);
    """
)

# 12: a small picture on a collection's folder (a star, a plane, ...).
MIGRATIONS.append(
    """
    ALTER TABLE collections ADD COLUMN icon TEXT;
    """
)

# 13: saves that only missed their sound because TikTok refused the file
# (HTTP 403) were wrongly marked done, so "Try again" skipped them. Put them
# back in the queue; their details and pictures stay.
MIGRATIONS.append(
    """
    UPDATE items SET status = 'imported'
    WHERE status = 'enriched'
      AND error LIKE 'Got the details, but not the sound.%HTTP Error 403%'
      AND id NOT IN (SELECT item_id FROM transcripts);
    -- TikTok's "status 10204" was explained as a block; it means taken down.
    UPDATE items SET error = 'This video was deleted or isn''t available any more.'
    WHERE error LIKE 'TikTok won''t show this video here.%';
    """
)

# 14: undo and redo (app/db/undo.py). A step is one change the user made;
# its log lines are the SQL that puts the rows back.
MIGRATIONS.append(
    """
    CREATE TABLE undo_steps (
        id INTEGER PRIMARY KEY,
        label TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'done',     -- done (can be undone) or undone (can be redone)
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
    );
    CREATE TABLE undo_log (
        id INTEGER PRIMARY KEY,
        step INTEGER NOT NULL,
        sql TEXT NOT NULL
    );
    CREATE INDEX undo_log_step ON undo_log (step);
    -- What the AI did, or is waiting to do, for an answer (app/search/agent.py).
    ALTER TABLE chat_messages ADD COLUMN actions_json TEXT;
    """
)

# 15: simpler sorting.
# - Saves taken down on the platform move to the Archive ("Deleted TikToks")
#   by themselves: gone_at.
# - The AI's tags can wait as suggestions (tag_suggestions_json).
# - Notes where the AI said it was given nothing ("Please provide a video")
#   came from prompts cut short; they're dropped and the saves wait for
#   notes again (with the AI's tags and collection picks for them).
# - No more "unsorted" tag, "Needs review" or new-collection ideas: a save in
#   no collection is in Unsorted, with the AI's pick as a suggestion.
# - The AI doesn't file or tag by itself unless switched on (Sort page).
# - Deleted saves go on the Unsave list.
MIGRATIONS.append(
    """
    ALTER TABLE items ADD COLUMN gone_at TEXT;
    ALTER TABLE ai_results ADD COLUMN tag_suggestions_json TEXT NOT NULL DEFAULT '[]';

    UPDATE items SET gone_at = coalesce(enriched_at, updated_at)
    WHERE status = 'failed' AND error = 'This video was deleted or isn''t available any more.';
    CREATE INDEX items_gone ON items (gone_at) WHERE gone_at IS NOT NULL;

    CREATE TEMP TABLE empty_notes AS
        SELECT item_id FROM ai_results
        WHERE lower(title) LIKE 'please provide%video%' OR lower(summary) LIKE 'please provide%video%'
           OR lower(title) LIKE 'please provide%transcript%' OR lower(summary) LIKE 'please provide%transcript%'
           OR lower(title) LIKE 'no video%provided%' OR lower(summary) LIKE 'no video%provided%'
           OR lower(title) LIKE 'no video content%' OR lower(summary) LIKE 'no video content%';
    DELETE FROM item_collections WHERE source = 'ai' AND item_id IN (SELECT item_id FROM empty_notes);
    DELETE FROM item_tags WHERE source = 'ai' AND item_id IN (SELECT item_id FROM empty_notes);
    DELETE FROM ai_results WHERE item_id IN (SELECT item_id FROM empty_notes);
    UPDATE items SET status = 'enriched', processed_at = NULL, sorted_at = NULL,
                     safe_to_unsave = CASE WHEN unsaved = 1 OR deleted_at IS NOT NULL THEN safe_to_unsave ELSE 0 END
    WHERE status = 'processed' AND id IN (SELECT item_id FROM empty_notes);
    DROP TABLE empty_notes;

    CREATE TEMP TABLE auto_tags AS SELECT DISTINCT tag_id FROM item_tags WHERE source = 'auto';
    DELETE FROM item_tags WHERE source = 'auto';
    DELETE FROM tags WHERE id IN (SELECT tag_id FROM auto_tags)
                       AND NOT EXISTS (SELECT 1 FROM item_tags it WHERE it.tag_id = tags.id);
    DROP TABLE auto_tags;
    UPDATE items SET needs_review = 0, review_reason = NULL WHERE needs_review = 1 OR review_reason IS NOT NULL;
    UPDATE ai_results SET new_collection = NULL WHERE new_collection IS NOT NULL;

    UPDATE settings
    SET value_json = json_remove(
            json_set(value_json, '$.auto_sort', json('false'), '$.auto_tag', json('false'), '$.mode', 'my_list'),
            '$.no_collection_tag', '$.safe_to_unsave')
    WHERE key = 'sorting' AND json_valid(value_json);

    UPDATE items SET safe_to_unsave = 1 WHERE deleted_at IS NOT NULL;
    """
)


MIGRATIONS.append(
    """
    ALTER TABLE items ADD COLUMN platform_collections_json TEXT;
    CREATE TABLE platform_import_destinations (
        platform TEXT PRIMARY KEY,
        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE
    );
    """
)


MIGRATIONS.append("ALTER TABLE jobs ADD COLUMN notice_dismissed INTEGER NOT NULL DEFAULT 0;")


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Run every migration that hasn't run yet. Returns the new version."""
    version = schema_version(conn)
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
    return schema_version(conn)
