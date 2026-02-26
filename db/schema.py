import sqlite3


def init_db(db_path: str) -> sqlite3.Connection:
    """Create tables if they don't exist and return a connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS newsletter (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT,
            author TEXT,
            last_fetched TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subtitle TEXT,
            url TEXT UNIQUE NOT NULL,
            published_date TIMESTAMP,
            content_html TEXT,
            content_text TEXT,
            word_count INTEGER,
            audience TEXT,
            reaction_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            reactions_json TEXT,
            categories TEXT,
            featured_image_url TEXT,
            fetched_at TIMESTAMP
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title,
            subtitle,
            content_text,
            content='articles',
            content_rowid='id'
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, title, subtitle, content_text)
            VALUES (new.id, new.title, new.subtitle, new.content_text);
        END;

        CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, title, subtitle, content_text)
            VALUES ('delete', old.id, old.title, old.subtitle, old.content_text);
        END;

        CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, title, subtitle, content_text)
            VALUES ('delete', old.id, old.title, old.subtitle, old.content_text);
            INSERT INTO articles_fts(rowid, title, subtitle, content_text)
            VALUES (new.id, new.title, new.subtitle, new.content_text);
        END;
    """)

    conn.commit()
    return conn
