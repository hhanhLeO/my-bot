import os
import json
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ARTICLES_DIR = Path("articles")
MANIFEST_FILE = ARTICLES_DIR / "manifest.json"
STORE_CONFIG_FILE = ARTICLES_DIR / ".store_config_openai.json"

VECTOR_STORE_NAME = "optisigns-support-docs"
def get_client() -> OpenAI:
    """Create and return an authenticated OpenAI client."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


def load_manifest() -> dict:
    """Load the local manifest file that tracks processed articles."""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
    return {}


def save_manifest(manifest: dict) -> None:
    """Save the local manifest file."""
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def load_store_config() -> dict:
    """Load Vector Store configuration."""
    if STORE_CONFIG_FILE.exists():
        return json.loads(STORE_CONFIG_FILE.read_text(encoding="utf-8-sig"))
    return {}


def save_store_config(config: dict) -> None:
    """Save Vector Store configuration."""
    STORE_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_or_create_store(client: OpenAI, store_id: str | None = None) -> str:
    """Retrieve an existing OpenAI Vector Store or create a new one."""
    config = load_store_config()

    # There is an existing Vector Store
    if store_id:
        log.info("Using provided vector store: %s", store_id)
        config["vector_store_id"] = store_id
        save_store_config(config)
        return store_id

    if "vector_store_id" in config:
        log.info("Reusing existing vector store: %s", config["vector_store_id"])
        return config["vector_store_id"]

    # Create a new Vector Store
    log.info("Creating new OpenAI vector store...")
    store = client.vector_stores.create(name=VECTOR_STORE_NAME)
    log.info("Vector store created: %s", store.id)
    config["vector_store_id"] = store.id
    save_store_config(config)
    return store.id


def upload_file(client: OpenAI, filepath: Path, store_id: str) -> str:
    """Upload one file to the vector store and wait for indexing. Returns the vector-store file id."""
    with open(filepath, "rb") as f:
        vsf = client.vector_stores.files.upload_and_poll(vector_store_id=store_id, file=f)
    if vsf.status != "completed":
        raise RuntimeError(f"indexing status={vsf.status} error={getattr(vsf, 'last_error', None)}")
    return vsf.id


def delete_file(client: OpenAI, store_id: str, file_id: str) -> None:
    """Best-effort removal of a previously uploaded file (used on updates to avoid stale duplicates)."""
    try:
        client.vector_stores.files.delete(vector_store_id=store_id, file_id=file_id)
    except Exception as exc:
        log.warning("Could not detach old file %s: %s", file_id, exc)
    try:
        client.files.delete(file_id)
    except Exception:
        pass


def upload(store_id: str | None = None) -> str:
    """Upload new/updated articles to the OpenAI vector store. Returns the store id."""
    client = get_client()
    manifest = load_manifest()

    if not manifest:
        log.error("No articles found in manifest. Run scraper.py first.")
        raise SystemExit(1)

    store = get_or_create_store(client, store_id)

    added = updated = skipped = errors = 0

    for article_id, meta in manifest.items():
        filepath = Path(meta["file"])
        current_hash = meta["hash"]

        if meta.get("openai_uploaded_hash") == current_hash:
            skipped += 1
            continue

        if not filepath.exists():
            log.warning("Missing file: %s — skipping", filepath)
            errors += 1
            continue

        is_update = "openai_file_id" in meta

        log.info("[uploading] %s", filepath.name)
        try:
            # On update, delete the stale copy first so the store has no duplicates.
            if is_update:
                delete_file(client, store, meta["openai_file_id"])

            file_id = upload_file(client, filepath, store)
            meta["openai_uploaded_hash"] = current_hash
            meta["openai_file_id"] = file_id

            if is_update:
                updated += 1
                log.info("[updated]   %s", filepath.name)
            else:
                added += 1
                log.info("[added]     %s", filepath.name)
        except Exception as exc:
            log.error("[error]     %s — %s", filepath.name, exc)
            errors += 1

    save_manifest(manifest)
    log.info("Upload complete. added=%d  updated=%d  skipped=%d  errors=%d", added, updated, skipped, errors)
    log.info("Vector store id: %s", store)
    return store


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload articles to an OpenAI vector store.")
    parser.add_argument(
        "--store",
        default=os.getenv("OPENAI_VECTOR_STORE_ID"),
        metavar="STORE_ID",
        help="Existing vector store id to reuse (default: auto-create or read from .store_config_openai.json)",
    )
    args = parser.parse_args()
    upload(store_id=args.store)


if __name__ == "__main__":
    main()
