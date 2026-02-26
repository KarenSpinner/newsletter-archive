import json
import time

import requests
from substack_api.post import Post


def fetch_archive(slug: str) -> list[dict]:
    """Fetch all post metadata from the Substack archive API.

    Returns a list of raw post dicts for newsletter articles only (no restacks).
    Uses a small page size because the Substack API returns inconsistent counts
    with larger limits, and always fetches until a truly empty page.
    """
    base_url = f"https://{slug}.substack.com"
    all_posts = []
    offset = 0
    limit = 12  # Small pages — API returns inconsistent counts with limit=25+

    while True:
        resp = requests.get(
            f"{base_url}/api/v1/archive",
            params={"sort": "new", "offset": offset, "limit": limit},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        posts = resp.json()

        if not posts:
            break

        all_posts.extend(posts)
        offset += len(posts)
        time.sleep(2)  # Rate limit

    # Filter to newsletter articles only (exclude restacks, etc.)
    all_posts = [p for p in all_posts if p.get("type") == "newsletter"]

    return all_posts


def extract_newsletter_metadata(slug: str, posts: list[dict]) -> dict:
    """Extract newsletter-level metadata from archive posts."""
    # Try to get author name from publishedBylines
    author = None
    for post in posts:
        bylines = post.get("publishedBylines") or []
        if bylines:
            author = bylines[0].get("name")
            break

    # Newsletter name is often in the first post's publication info
    pub_name = slug  # fallback
    for post in posts:
        pub = post.get("publication") or {}
        if pub.get("name"):
            pub_name = pub["name"]
            break

    pub_description = None
    for post in posts:
        pub = post.get("publication") or {}
        if pub.get("hero_text"):
            pub_description = pub["hero_text"]
            break

    return {
        "name": pub_name,
        "slug": slug,
        "url": f"https://{slug}.substack.com",
        "description": pub_description,
        "author": author,
        "last_fetched": None,
    }


def fetch_post_content(slug: str, post_slug: str) -> str | None:
    """Fetch the full HTML content for a single post."""
    try:
        url = f"https://{slug}.substack.com/p/{post_slug}"
        post = Post(url)
        return post.get_content()
    except Exception as e:
        print(f"    Error fetching content: {e}")
        return None


def parse_post_metadata(post: dict, slug: str) -> dict:
    """Convert a raw archive API post dict into our article schema."""
    # Tags/categories
    tags = post.get("postTags") or []
    tag_names = [t.get("name", "") for t in tags if isinstance(t, dict)]

    # Reactions breakdown
    reactions = post.get("reactions") or {}

    canonical_url = post.get("canonical_url") or f"https://{slug}.substack.com/p/{post.get('slug', '')}"

    return {
        "title": post.get("title", "Untitled"),
        "subtitle": post.get("subtitle"),
        "url": canonical_url,
        "published_date": post.get("post_date"),
        "audience": post.get("audience", "everyone"),
        "reaction_count": post.get("reaction_count", 0) or 0,
        "comment_count": post.get("comment_count", 0) or 0,
        "reactions_json": json.dumps(reactions) if reactions else None,
        "categories": json.dumps(tag_names) if tag_names else None,
        "featured_image_url": post.get("cover_image"),
        "word_count_from_api": post.get("wordcount"),  # May use as fallback
        "post_slug": post.get("slug"),
    }
