import os
import re
import json
import hashlib
import argparse
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv
from markdownify import markdownify as md

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ZENDESK_BASE = "https://support.optisigns.com/api/v2/help_center"
ARTICLES_DIR = Path("articles")
MANIFEST_FILE = ARTICLES_DIR / "manifest.json"


def slugify(text: str) -> str:
    """Convert the raw article title to file name."""
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", text.lower())).strip("-")


def fetch_articles(locale: str = "en-us", limit: int | None = None) -> list[dict]:
    """Fetch articles from Zendesk API, up to `limit` (None = all)."""
    url = f"{ZENDESK_BASE}/{locale}/articles.json?per_page=100&sort_by=updated_at&sort_order=desc"
    articles = []

    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        articles.extend(data["articles"])
        log.info("Fetched %d / %s articles so far...", len(articles), data.get("count", "?"))

        if limit and len(articles) >= limit:
            articles = articles[:limit]
            break

        url = data.get("next_page")

    return articles


def html_to_markdown(html: str, article_url: str) -> str:
    raw = md(html, heading_style="ATX", bullets="-", code_language="")
    # Collapse 3+ blank lines into 2
    cleaned = re.sub(r"\n{3,}", "\n\n", raw)
    return cleaned.strip()


def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def scrape(limit: int | None = None, locale: str = "en-us") -> None:
    ARTICLES_DIR.mkdir(exist_ok=True)
    manifest = load_manifest()

    articles = fetch_articles(locale=locale, limit=limit)
    log.info("Processing %d articles...", len(articles))

    added = updated = skipped = 0

    for article in articles:
        article_id = str(article["id"])
        title = article.get("title", "untitled")
        html_body = article.get("body") or ""
        url = article.get("html_url", "")
        updated_at = article.get("updated_at", "")

        body_md = html_to_markdown(html_body, url)
        full_md = f"# {title}\n\n**Article URL:** {url}\n\n{body_md}"
        h = content_hash(full_md)

        slug = slugify(title)[:80]  # keep filenames sane
        filepath = ARTICLES_DIR / f"{slug}.md"

        prev = manifest.get(article_id, {})
        if prev.get("hash") == h:
            skipped += 1
            continue

        filepath.write_text(full_md, encoding="utf-8")

        if article_id in manifest:
            updated += 1
            log.info("  [updated] %s", filepath.name)
        else:
            added += 1
            log.info("  [added]   %s", filepath.name)

        manifest[article_id] = {
            "slug": slug,
            "title": title,
            "url": url,
            "updated_at": updated_at,
            "hash": h,
            "file": str(filepath),
        }

    save_manifest(manifest)
    log.info("Done. added=%d  updated=%d  skipped=%d", added, updated, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape OptiSigns Help Center articles to Markdown.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max number of articles to scrape (default: all ~406). Use 30 for the minimum requirement.",
    )
    parser.add_argument(
        "--locale",
        default=os.getenv("ZENDESK_LOCALE", "en-us"),
        help="Zendesk locale (default: en-us)",
    )
    args = parser.parse_args()

    scrape(limit=args.limit, locale=args.locale)


if __name__ == "__main__":
    main()
