import json
import sqlite3
from datetime import datetime, timezone


def upsert_newsletter(conn: sqlite3.Connection, data: dict) -> None:
    """Insert or update the single newsletter row."""
    conn.execute(
        """INSERT INTO newsletter (id, name, slug, url, description, author, last_fetched)
           VALUES (1, :name, :slug, :url, :description, :author, :last_fetched)
           ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, slug=excluded.slug, url=excluded.url,
               description=excluded.description, author=excluded.author,
               last_fetched=excluded.last_fetched""",
        data,
    )
    conn.commit()


def upsert_article(conn: sqlite3.Connection, data: dict) -> bool:
    """Insert an article if it doesn't already exist (by URL). Returns True if inserted."""
    try:
        conn.execute(
            """INSERT INTO articles
               (title, subtitle, url, published_date, content_html, content_text,
                word_count, audience, reaction_count, comment_count, reactions_json,
                categories, featured_image_url, fetched_at)
               VALUES (:title, :subtitle, :url, :published_date, :content_html,
                       :content_text, :word_count, :audience, :reaction_count,
                       :comment_count, :reactions_json, :categories,
                       :featured_image_url, :fetched_at)""",
            data,
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_article_urls(conn: sqlite3.Connection) -> set[str]:
    """Return the set of all article URLs already in the database."""
    rows = conn.execute("SELECT url FROM articles").fetchall()
    return {row["url"] for row in rows}


def update_last_fetched(conn: sqlite3.Connection) -> None:
    """Update the newsletter's last_fetched timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE newsletter SET last_fetched = ? WHERE id = 1", (now,))
    conn.commit()


# --- Query helpers for MCP server ---


def get_newsletter_info(conn: sqlite3.Connection) -> dict | None:
    """Return newsletter metadata plus aggregate article stats."""
    nl = conn.execute("SELECT * FROM newsletter WHERE id = 1").fetchone()
    if not nl:
        return None

    stats = conn.execute(
        """SELECT
               COUNT(*) as total_articles,
               MIN(published_date) as earliest,
               MAX(published_date) as latest,
               COALESCE(SUM(reaction_count), 0) as total_reactions,
               COALESCE(SUM(comment_count), 0) as total_comments,
               COALESCE(ROUND(AVG(word_count)), 0) as avg_word_count
           FROM articles"""
    ).fetchone()

    return {
        "name": nl["name"],
        "slug": nl["slug"],
        "url": nl["url"],
        "description": nl["description"],
        "author": nl["author"],
        "last_fetched": nl["last_fetched"],
        "total_articles": stats["total_articles"],
        "date_range": {"earliest": stats["earliest"], "latest": stats["latest"]},
        "engagement": {
            "total_reactions": stats["total_reactions"],
            "total_comments": stats["total_comments"],
        },
        "avg_word_count": stats["avg_word_count"],
    }


def search_articles(
    conn: sqlite3.Connection,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    audience: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Filter articles by metadata. Returns summaries (no full text)."""
    conditions = []
    params: list = []

    if keyword:
        conditions.append("(title LIKE ? OR subtitle LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if date_from:
        conditions.append("published_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("published_date <= ?")
        params.append(date_to)
    if audience:
        conditions.append("audience = ?")
        params.append(audience)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    rows = conn.execute(
        f"""SELECT id, title, subtitle, url, published_date, word_count,
                   audience, reaction_count, comment_count
            FROM articles {where}
            ORDER BY published_date DESC
            LIMIT ? OFFSET ?""",
        params,
    ).fetchall()

    return [dict(row) for row in rows]


def fts_search(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """Full-text search. Returns titles and snippets."""
    rows = conn.execute(
        """SELECT a.id, a.title, a.published_date, a.url,
                  snippet(articles_fts, 2, '<b>', '</b>', '...', 40) as snippet
           FROM articles_fts f
           JOIN articles a ON a.id = f.rowid
           WHERE articles_fts MATCH ?
           ORDER BY rank
           LIMIT ?""",
        (query, limit),
    ).fetchall()

    return [dict(row) for row in rows]


def get_article_by_id(conn: sqlite3.Connection, article_id: int) -> dict | None:
    """Return full article content + metadata by ID."""
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    # Parse JSON fields for readability
    for field in ("reactions_json", "categories"):
        if result.get(field):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


def get_articles_batch(
    conn: sqlite3.Connection, ids: list[int]
) -> list[dict]:
    """Return full content for multiple articles (max 5)."""
    ids = ids[:5]
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM articles WHERE id IN ({placeholders})", ids
    ).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        for field in ("reactions_json", "categories"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        results.append(d)
    return results


def get_stats(conn: sqlite3.Connection) -> dict:
    """Aggregate statistics about the newsletter."""
    totals = conn.execute(
        """SELECT
               COUNT(*) as total_articles,
               COALESCE(SUM(reaction_count), 0) as total_reactions,
               COALESCE(SUM(comment_count), 0) as total_comments,
               COALESCE(ROUND(AVG(word_count)), 0) as avg_word_count,
               COALESCE(ROUND(AVG(reaction_count), 1), 0) as avg_reactions,
               COALESCE(ROUND(AVG(comment_count), 1), 0) as avg_comments,
               MIN(published_date) as earliest,
               MAX(published_date) as latest
           FROM articles"""
    ).fetchone()

    audience = conn.execute(
        """SELECT audience, COUNT(*) as count
           FROM articles GROUP BY audience"""
    ).fetchall()

    by_year = conn.execute(
        """SELECT strftime('%Y', published_date) as year, COUNT(*) as count
           FROM articles
           WHERE published_date IS NOT NULL
           GROUP BY year ORDER BY year"""
    ).fetchall()

    return {
        "total_articles": totals["total_articles"],
        "total_reactions": totals["total_reactions"],
        "total_comments": totals["total_comments"],
        "avg_word_count": totals["avg_word_count"],
        "avg_reactions_per_article": totals["avg_reactions"],
        "avg_comments_per_article": totals["avg_comments"],
        "date_range": {"earliest": totals["earliest"], "latest": totals["latest"]},
        "audience_breakdown": {row["audience"]: row["count"] for row in audience},
        "articles_by_year": {row["year"]: row["count"] for row in by_year},
    }


def get_top_articles(
    conn: sqlite3.Connection, metric: str = "reaction_count", limit: int = 10
) -> list[dict]:
    """Return top articles ranked by an engagement metric."""
    allowed_metrics = {"reaction_count", "comment_count", "word_count"}
    if metric not in allowed_metrics:
        metric = "reaction_count"

    rows = conn.execute(
        f"""SELECT id, title, url, published_date, word_count,
                   audience, reaction_count, comment_count
            FROM articles
            ORDER BY {metric} DESC
            LIMIT ?""",
        (limit,),
    ).fetchall()

    return [dict(row) for row in rows]
