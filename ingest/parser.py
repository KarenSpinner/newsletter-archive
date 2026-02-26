import re

from bs4 import BeautifulSoup


def html_to_text(html: str | None) -> str:
    """Convert HTML to clean plain text with paragraph breaks preserved."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    # Replace <br> tags with newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Replace block-level elements with double newlines
    for tag in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]):
        tag.insert_before("\n\n")
        tag.insert_after("\n\n")

    text = soup.get_text()

    # Normalize whitespace: collapse runs of spaces/tabs (but not newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
