#!/usr/bin/env python3
"""MCP server exposing newsletter data to Claude Desktop."""

import os
import sqlite3
import sys

# Add project root to path so db imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from db.schema import init_db
from db import operations as ops

mcp = FastMCP("my-newsletter")

DB_PATH = os.environ.get("DB_PATH", "newsletter.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def get_newsletter_info() -> dict:
    """Get newsletter metadata: name, description, author, total articles, date range, and engagement summary."""
    conn = _get_conn()
    try:
        result = ops.get_newsletter_info(conn)
        if not result:
            return {"error": "No newsletter data found. Run ingest_runner.py first."}
        return result
    finally:
        conn.close()


@mcp.tool()
def search_articles(
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    audience: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Search articles by keyword in title, date range, and audience type.

    Returns article summaries (no full text). Use get_article for full content.

    Args:
        keyword: Search term to match in title or subtitle
        date_from: Start date (ISO format, e.g. "2024-01-01")
        date_to: End date (ISO format, e.g. "2024-12-31")
        audience: Filter by "everyone" (free) or "only_paid"
        limit: Max results to return (default 20)
        offset: Skip this many results for pagination
    """
    conn = _get_conn()
    try:
        return ops.search_articles(conn, keyword, date_from, date_to, audience, limit, offset)
    finally:
        conn.close()


@mcp.tool()
def full_text_search(query: str, limit: int = 10) -> list[dict]:
    """Full-text search across all article content using FTS5.

    Returns titles and matching text snippets. Use get_article for full content.

    Args:
        query: Search query (supports FTS5 syntax: AND, OR, NOT, "exact phrase")
        limit: Max results to return (default 10)
    """
    conn = _get_conn()
    try:
        return ops.fts_search(conn, query, limit)
    finally:
        conn.close()


@mcp.tool()
def get_article(id: int) -> dict:
    """Get the full text and all metadata for a single article by its ID.

    Args:
        id: Article ID (from search results)
    """
    conn = _get_conn()
    try:
        result = ops.get_article_by_id(conn, id)
        if not result:
            return {"error": f"Article with id {id} not found."}
        return result
    finally:
        conn.close()


@mcp.tool()
def get_articles_batch(ids: list[int]) -> list[dict]:
    """Get full text and metadata for multiple articles at once (max 5).

    Args:
        ids: List of article IDs (max 5)
    """
    conn = _get_conn()
    try:
        return ops.get_articles_batch(conn, ids)
    finally:
        conn.close()


@mcp.tool()
def get_stats() -> dict:
    """Get aggregate statistics: total articles, date distribution, engagement averages, free vs paid breakdown."""
    conn = _get_conn()
    try:
        return ops.get_stats(conn)
    finally:
        conn.close()


@mcp.tool()
def get_top_articles(metric: str = "reaction_count", limit: int = 10) -> list[dict]:
    """Get top articles ranked by an engagement metric.

    Args:
        metric: Ranking metric - "reaction_count", "comment_count", or "word_count"
        limit: Number of articles to return (default 10)
    """
    conn = _get_conn()
    try:
        return ops.get_top_articles(conn, metric, limit)
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
