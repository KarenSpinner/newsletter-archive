# Substack Newsletter Archive + Claude Desktop MCP

## Project Spec

### Overview

A single-user desktop tool that ingests **your own Substack newsletter articles** (long-form posts only, not Notes) into a local SQLite database — including full article content, metadata, and available engagement metrics — then exposes the data to Claude Desktop via a custom MCP server for conversational analysis of your writing.

### Scope

- **In scope:** Articles (long-form newsletter posts delivered via email to subscribers)
- **Out of scope:** Substack Notes (short-form social posts — different API, requires auth, lower analytical value)

---

## 1. Data Sources

### Primary: `substack-api` Python Library (unofficial)

- **Archive access:** Full paginated history of your publication via `/api/v1/archive`
- **Content:** Full HTML for all your posts (you're the author, so no paywall issue)
- **Engagement metrics:** `reaction_count`, `comment_count`, `reactions` (emoji breakdown), restacks
- **Metadata:** title, subtitle, publish date, URL, categories, audience type (free/paid)
- **Risk:** Unofficial API — could break if Substack changes internal endpoints

### Fallback: RSS Feed

- **URL pattern:** `https://{your-slug}.substack.com/feed` (or `{custom-domain}/feed`)
- **Content:** Full HTML in `<content:encoded>`
- **Limitations:** No engagement metrics, no pagination (~10-25 most recent posts only)
- **Use case:** Reliability fallback if `substack-api` breaks

---

## 2. Database Schema (SQLite)

### `newsletter` Table (single row — your publication metadata)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Always 1 |
| name | TEXT NOT NULL | Your newsletter name |
| slug | TEXT NOT NULL | URL slug (e.g., "yournewsletter") |
| url | TEXT NOT NULL | Full URL |
| description | TEXT | Newsletter description |
| author | TEXT | Your name |
| last_fetched | TIMESTAMP | Last successful fetch time |

### `articles` Table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| title | TEXT NOT NULL | Article title |
| subtitle | TEXT | Article subtitle |
| url | TEXT UNIQUE NOT NULL | Canonical URL |
| published_date | TIMESTAMP | Publication date |
| content_html | TEXT | Original HTML content |
| content_text | TEXT | Cleaned plain text (for search + analysis) |
| word_count | INTEGER | Computed from content_text |
| audience | TEXT | "everyone" or "only_paid" |
| reaction_count | INTEGER DEFAULT 0 | Total likes/reactions |
| comment_count | INTEGER DEFAULT 0 | Number of comments |
| reactions_json | TEXT | JSON of reaction breakdown (e.g., `{"heart": 4}`) |
| categories | TEXT | JSON array of tags/categories |
| featured_image_url | TEXT | Hero image URL |
| fetched_at | TIMESTAMP | When we ingested this article |

### `articles_fts` Virtual Table (FTS5)

Full-text search index over `title`, `subtitle`, and `content_text`. Enables fast keyword search without embeddings.

---

## 3. Ingestion Pipeline

### Configuration

```python
# config.py
NEWSLETTER_SLUG = "yournewsletter"  # User sets this once
```

### Fetch Flow

1. Validate slug by fetching newsletter metadata
2. Fetch full post archive via `substack-api` (paginated)
3. For each post not already in DB (dedupe by URL):
   - Fetch full content + engagement metrics
   - Clean HTML → plain text (via BeautifulSoup)
   - Compute word count
   - Insert into `articles` table
   - Update FTS5 index
4. Rate limit: 1 request/second between API calls
5. Log progress: articles fetched, skipped (already exists), failed

### Incremental Updates

- Track `last_fetched` on the newsletter record
- On subsequent runs, only fetch posts published after `last_fetched`
- Can be run manually or via cron/launchd

### CLI Usage

```bash
# First run — full archive fetch
python ingest_runner.py

# Subsequent runs — only new posts
python ingest_runner.py

# Force re-fetch everything
python ingest_runner.py --full
```

### CLI Output

All CLI scripts must print progress updates — never hang silently. Example output:

```
Connecting to Substack: yournewsletter... OK
Fetching article archive... found 39 articles
[  1/39] "Why AI Won't Replace Writers" (2024-03-15)... saved
[  2/39] "The Pricing Paradox" (2024-03-22)... saved
[  3/39] "On Building in Public" (2024-04-01)... already exists, skipped
...
[ 39/39] "What I Learned This Year" (2025-01-10)... saved

Done: 36 saved, 3 skipped, 0 failed
```

Requirements:
- Show connection/validation status immediately
- Print total article count before processing starts
- Show per-article progress with index, title, date, and outcome (saved/skipped/failed)
- Print summary line at completion with counts
- Print errors inline (don't swallow them) with enough detail to debug

---

## 4. MCP Server

### Technology

- Python with `FastMCP` (from `mcp` SDK)
- Communicates with Claude Desktop via stdio
- Read-only access to the SQLite database

### Tools Exposed

| Tool | Description | Returns |
|------|-------------|---------|
| `get_newsletter_info` | Newsletter metadata: name, description, total articles, date range, overall engagement stats | Single metadata object |
| `search_articles` | Filter by date range, keyword in title, audience type. Returns metadata only (no full text) | List of article summaries (title, date, word count, engagement) |
| `full_text_search` | FTS5 keyword search across all article content. Returns titles + matching snippets | Search results with context snippets |
| `get_article` | Retrieve full text of a single article by ID | Full article content + all metadata |
| `get_articles_batch` | Retrieve full text for up to 5 articles by IDs | Multiple full articles |
| `get_stats` | Aggregate statistics: total articles, articles over time, engagement trends, avg word count, free vs paid breakdown | Summary statistics |
| `get_top_articles` | Top N articles ranked by engagement (reactions, comments) | Ranked article list with metrics |

### Design Principles

- **Tiered retrieval:** Metadata/search first, full text on demand. Keeps token usage low.
- **No tool returns more than ~10K tokens.** Pagination via `limit`/`offset` parameters where applicable.
- **Read-only:** No write operations exposed through MCP.

### Claude Desktop Configuration

Added to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-newsletter": {
      "command": "/Users/karenspinner/Documents/Newsletter_RAG/.venv/bin/python",
      "args": ["/Users/karenspinner/Documents/Newsletter_RAG/mcp_server/server.py"],
      "env": {
        "DB_PATH": "/Users/karenspinner/Documents/Newsletter_RAG/newsletter.db"
      }
    }
  }
}
```

Restart Claude Desktop after adding this configuration.

---

## 5. Project Structure

```
Newsletter_RAG/
├── docs/
│   └── spec.md              # This document
├── ingest/
│   ├── __init__.py
│   ├── fetcher.py           # Substack API + RSS fetching logic
│   └── parser.py            # HTML → clean text extraction
├── db/
│   ├── __init__.py
│   ├── schema.py            # Table creation + FTS5 setup
│   └── operations.py        # Insert, query, dedupe operations
├── mcp_server/
│   └── server.py            # FastMCP server with all tools
├── config.py                # Newsletter slug + settings
├── ingest_runner.py         # CLI entry point for ingestion
├── newsletter.db            # SQLite database (generated)
└── requirements.txt
```

---

## 6. Dependencies

```
substack-api>=1.0        # Substack data fetching (unofficial API)
feedparser>=6.0          # RSS feed parsing (fallback)
beautifulsoup4>=4.12     # HTML → plain text conversion
mcp[cli]>=1.0            # MCP server SDK (includes FastMCP)
```

No embeddings, no vector DB, no API keys required.

---

## 7. Scale Considerations

| Scenario | Articles | Est. Tokens | Approach |
|----------|----------|-------------|----------|
| Current | 39 | ~50K | Fits comfortably in context; MCP adds structure |
| Growing | 100-200 | ~135-270K | Tiered retrieval keeps queries efficient |
| Prolific | 500+ | ~675K+ | Same architecture scales; add embeddings at 1000+ |

### Why No Embeddings

- SQLite FTS5 covers keyword/phrase search
- MCP filtering covers metadata queries (date, audience, engagement)
- Claude reasons well over retrieved text without semantic pre-filtering
- Avoids API dependencies and embedding pipeline complexity
- Can be added later if semantic search becomes needed

---

## 8. Example Interactions with Claude Desktop

Once configured, conversations like:

- "Which of my posts got the most engagement?"
- "Show me my writing about AI from the last 6 months"
- "What topics have I covered most frequently?"
- "How has my average word count changed over time?"
- "Find posts where I discussed pricing strategy"
- "Summarize the key themes across my last 10 articles"
- "Which of my free posts outperformed my paid posts in engagement?"

Claude will use the MCP tools to search, filter, and retrieve relevant articles, then analyze them in context.

---

## 9. Implementation Order

1. **Database schema** — Create SQLite DB with tables + FTS5
2. **Ingestion pipeline** — Fetcher + parser + CLI runner
3. **MCP server** — FastMCP with all 7 tools
4. **Claude Desktop config** — Wire up and test
5. **Incremental updates** — Add `last_fetched` logic for re-runs

---

## 10. Known Limitations

- `substack-api` is unofficial and could break without notice
- No real-time updates — must re-run ingestion to pick up new articles
- Engagement metrics are point-in-time snapshots (not live-updating)
- RSS fallback loses engagement metrics and is limited to ~25 recent posts
