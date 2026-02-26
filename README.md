# Substack Newsletter Archive + Claude Desktop MCP

Turn your Substack newsletter into a personal knowledge base that Claude Desktop can search, analyze, and visualize — all through natural conversation.

## What this does

1. **Ingests** every article from your Substack newsletter into a local SQLite database (full text, metadata, engagement metrics)
2. **Exposes** 7 read-only tools to Claude Desktop via MCP (Model Context Protocol)
3. **Claude Desktop becomes your front end** — search your archive, analyze trends, compare posts, generate visualizations, all in natural language

## Requirements

- Python 3.12+
- Node.js (for optional Mermaid diagram rendering)
- Claude Desktop
- A Substack newsletter (yours — you're the author)

## Setup

### 1. Create virtual environment and install dependencies

```bash
cd newsletter-archive
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Configure your newsletter slug

Edit `config.py` and set your Substack slug:

```python
NEWSLETTER_SLUG = "yournewsletter"  # from yournewsletter.substack.com
```

### 3. Ingest your articles

```bash
.venv/bin/python ingest_runner.py
```

You'll see progress for each article:

```
Connecting to Substack: yournewsletter... OK
Fetching article archive... found 39 articles
[  1/39] "Article Title" (2025-07-09)... saved
...
Done: 39 saved, 0 skipped, 0 failed
```

To re-fetch everything later: `.venv/bin/python ingest_runner.py --full`

### 4. Connect to Claude Desktop

Open your Claude Desktop config file:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

(On macOS: Finder → Go → Go to Folder → paste the path above)

Add this to the `"mcpServers"` section (update the paths to match where you put this project):

```json
{
  "mcpServers": {
    "my-newsletter": {
      "command": "/FULL/PATH/TO/newsletter-archive/.venv/bin/python",
      "args": ["/FULL/PATH/TO/newsletter-archive/mcp_server/server.py"],
      "env": {
        "DB_PATH": "/FULL/PATH/TO/newsletter-archive/newsletter.db"
      }
    }
  }
}
```

**Important:** Use full absolute paths, not `~` or relative paths.

If you already have other MCP servers configured, add `"my-newsletter"` alongside them (don't replace the existing ones).

### 5. Restart Claude Desktop

Fully quit Claude Desktop (Cmd+Q) and reopen it. The newsletter tools will appear automatically.

## What you can ask Claude

Once connected:

- "Which of my posts got the most engagement?"
- "Show me everything I've written about [topic]"
- "How has my average word count changed over time?"
- "Which free posts outperformed my paid posts?"
- "Summarize the key themes across my last 10 articles"
- "What topics have I covered most frequently?"

## Optional: Add Mermaid diagram rendering

To let Claude generate mind maps, flowcharts, and other visualizations inline:

Add this to your `claude_desktop_config.json` alongside the newsletter server:

```json
"mermaid": {
  "command": "npx",
  "args": ["-y", "@peng-shawn/mermaid-mcp-server"]
}
```

Requires Node.js. Then ask Claude things like "Create a mind map of my newsletter topics."

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `get_newsletter_info` | Newsletter name, author, total articles, date range, engagement summary |
| `search_articles` | Filter by keyword, date range, audience type — returns summaries |
| `full_text_search` | FTS5 search across all article content — returns snippets |
| `get_article` | Full text + metadata for one article by ID |
| `get_articles_batch` | Full text for up to 5 articles at once |
| `get_stats` | Totals, averages, free vs paid breakdown, articles by year |
| `get_top_articles` | Ranked by reactions, comments, or word count |

## Project structure

```
newsletter-archive/
├── config.py              # Your newsletter slug (edit this)
├── ingest_runner.py       # CLI: python ingest_runner.py [--full]
├── requirements.txt       # 4 dependencies
├── db/
│   ├── schema.py          # SQLite tables + FTS5 search index
│   └── operations.py      # All database queries
├── ingest/
│   ├── parser.py          # HTML → plain text conversion
│   └── fetcher.py         # Substack API fetching (two-phase)
├── mcp_server/
│   └── server.py          # MCP server with 7 tools
└── docs/
    └── spec.md            # Full project specification
```

## Updating your archive

Run the ingestion script again anytime to pick up new articles:

```bash
.venv/bin/python ingest_runner.py
```

It only fetches articles not already in the database (deduplicates by URL).

## Troubleshooting

**"No newsletter data found"** — You need to run `ingest_runner.py` before using the MCP tools.

**Claude Desktop doesn't show the tools** — Check that your paths in `claude_desktop_config.json` are correct absolute paths. Fully quit and reopen Claude Desktop.

**Ingestion finds fewer articles than expected** — The Substack API can be inconsistent with pagination. The fetcher uses small page sizes (12) to work around this. If articles are still missing, try `--full`.
