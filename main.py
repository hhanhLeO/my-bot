import os
import logging

from scraper import scrape
from uploader import upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SCRAPE_LIMIT = int(os.getenv("SCRAPE_LIMIT")) if os.getenv("SCRAPE_LIMIT") else 30

def main() -> None:
    """Daily job entrypoint: re-scrape all articles, then upload only the delta."""
    log.info("=== Daily job start ===")
    scrape(limit=SCRAPE_LIMIT)
    upload()
    log.info("=== Daily job complete ===")


if __name__ == "__main__":
    main()
