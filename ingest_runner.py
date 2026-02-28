#!/usr/bin/env python3
"""CLI entry point for newsletter ingestion."""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from db.schema import init_db
from db.operations import upsert_newsletter, upsert_article, get_article_urls, update_last_fetched
from ingest.fetcher import resolve_base_url, fetch_archive, extract_newsletter_metadata, fetch_post_content, parse_post_metadata
from ingest.parser import html_to_text


def main():
    parser = argparse.ArgumentParser(description="Ingest Substack newsletter articles")
    parser.add_argument("--full", action="store_true", help="Re-fetch all articles (ignore existing)")
    args = parser.parse_args()

    base_url = resolve_base_url(config.NEWSLETTER_SLUG)
    db_path = config.DB_PATH

    # Initialize database
    conn = init_db(db_path)

    # Phase 1: Fetch archive metadata
    print(f"Connecting to Substack: {base_url}... ", end="", flush=True)
    try:
        posts = fetch_archive(base_url)
    except Exception as e:
        print(f"FAILED\n  Error: {e}")
        sys.exit(1)

    if not posts:
        print("OK\nNo articles found.")
        return

    print("OK")

    # Extract and save newsletter metadata
    nl_meta = extract_newsletter_metadata(base_url, posts)
    nl_meta["last_fetched"] = datetime.now(timezone.utc).isoformat()
    upsert_newsletter(conn, nl_meta)

    # Get existing URLs for dedup
    existing_urls = get_article_urls(conn) if not args.full else set()

    print(f"Fetching article archive... found {len(posts)} articles")

    saved = 0
    skipped = 0
    failed = 0

    for i, post in enumerate(posts, 1):
        meta = parse_post_metadata(post, base_url)
        title = meta["title"]
        pub_date = (meta["published_date"] or "unknown")[:10]

        print(f"[{i:3d}/{len(posts)}] \"{title}\" ({pub_date})... ", end="", flush=True)

        # Check if already in DB
        if meta["url"] in existing_urls:
            print("already exists, skipped")
            skipped += 1
            continue

        # Phase 2: Fetch full content
        html_content = fetch_post_content(base_url, meta["post_slug"])
        if html_content is None:
            print("FAILED (could not fetch content)")
            failed += 1
            continue

        # Parse content
        text_content = html_to_text(html_content)
        word_count = len(text_content.split()) if text_content else (meta["word_count_from_api"] or 0)

        # Build article record
        article = {
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "url": meta["url"],
            "published_date": meta["published_date"],
            "content_html": html_content,
            "content_text": text_content,
            "word_count": word_count,
            "audience": meta["audience"],
            "reaction_count": meta["reaction_count"],
            "comment_count": meta["comment_count"],
            "reactions_json": meta["reactions_json"],
            "categories": meta["categories"],
            "featured_image_url": meta["featured_image_url"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        if upsert_article(conn, article):
            print("saved")
            saved += 1
        else:
            print("already exists, skipped")
            skipped += 1

        # Rate limit between content fetches
        time.sleep(1)

    update_last_fetched(conn)
    conn.close()

    print(f"\nDone: {saved} saved, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
