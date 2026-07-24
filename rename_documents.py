#!/usr/bin/env python3
import argparse
import logging
import os
import re
import time
from typing import Optional

import httpx
import yaml

PROMPT_TEMPLATE = """You are a document title extractor. Given OCR text from a scanned document, produce a concise descriptive title.

Format: [Organization] [Document Type] [Year only if annual]
Examples: HSBC Mortgage Statement 2024, HMRC Tax Return 2023-24, Vodafone Invoice, City Dental Receipt

Rules:
- Return ONLY the title, no explanation, no quotes, no punctuation at the end
- Maximum 60 characters
- The organisation name is the primary business name shown at the top of the document; ignore names found in email addresses, URLs, or postal addresses
- Omit branch locations from the organisation name
- Use brief document type labels: Receipt not "Receipt of Payment", Invoice not "Tax Invoice"
- Only include the year for explicitly annual documents like yearly statements or tax returns; omit it for receipts, invoices, and letters
- NEVER include the recipient's name
- If you cannot determine enough detail, return: UNKNOWN

OCR text:
{content}"""


def load_config(path: str) -> dict:
    with open(path) as f:
        config = yaml.safe_load(f)

    if os.environ.get("PAPERLESS_TOKEN"):
        config["paperless"]["token"] = os.environ["PAPERLESS_TOKEN"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        config.setdefault("llm", {}).setdefault("anthropic", {})["api_key"] = os.environ["ANTHROPIC_API_KEY"]

    return config


def setup_logging(config: dict) -> None:
    level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper(), logging.INFO)
    log_file = config.get("logging", {}).get("file", "")
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def paperless_headers(config: dict) -> dict:
    return {"Authorization": f"Token {config['paperless']['token']}"}


def get_pending_documents(config: dict) -> list[dict]:
    base_url = config["paperless"]["url"].rstrip("/")
    pattern = re.compile(config.get("scanner_pattern", r"^BRW\d+"))
    headers = paperless_headers(config)
    docs = []
    url = f"{base_url}/api/documents/?title__istartswith=BRW&page_size=100"

    while url:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for doc in data.get("results", []):
            if pattern.match(doc["title"]):
                docs.append(doc)
        url = data.get("next")

    logging.info(f"Found {len(docs)} document(s) pending rename")
    return docs


def get_document_content(doc_id: int, config: dict) -> str:
    base_url = config["paperless"]["url"].rstrip("/")
    resp = httpx.get(
        f"{base_url}/api/documents/{doc_id}/",
        headers=paperless_headers(config),
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json().get("content", "")
    max_chars = config.get("llm", {}).get("max_content_chars", 3000)
    return content[:max_chars]


def update_document_title(doc_id: int, title: str, config: dict) -> None:
    base_url = config["paperless"]["url"].rstrip("/")
    resp = httpx.patch(
        f"{base_url}/api/documents/{doc_id}/",
        headers=paperless_headers(config),
        json={"title": title},
        timeout=30,
    )
    resp.raise_for_status()


def infer_title_ollama(content: str, config: dict) -> Optional[str]:
    ollama_cfg = config["llm"]["ollama"]
    url = ollama_cfg["url"].rstrip("/")
    payload = {
        "model": ollama_cfg["model"],
        "prompt": PROMPT_TEMPLATE.format(content=content),
        "stream": False,
    }
    resp = httpx.post(f"{url}/api/generate", json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["response"].strip()


def infer_title_anthropic(content: str, config: dict) -> Optional[str]:
    import anthropic

    anthropic_cfg = config["llm"]["anthropic"]
    api_key = anthropic_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=anthropic_cfg["model"],
        max_tokens=100,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(content=content)}],
    )
    return message.content[0].text.strip()


def infer_title(content: str, config: dict) -> Optional[str]:
    provider = config.get("llm", {}).get("provider", "ollama")
    try:
        if provider == "ollama":
            return infer_title_ollama(content, config)
        elif provider == "anthropic":
            return infer_title_anthropic(content, config)
        else:
            logging.error(f"Unknown LLM provider: {provider}")
            return None
    except Exception as e:
        logging.error(f"LLM inference failed: {e}")
        return None


def is_valid_title(title: Optional[str], scanner_pattern: str) -> bool:
    if not title or title.strip().upper() == "UNKNOWN":
        return False
    if len(title) > 80:
        return False
    if "\n" in title:
        return False
    if re.match(scanner_pattern, title):
        return False
    return True


def process_document(doc_id: int, doc_title: str, config: dict) -> None:
    dry_run = config.get("dry_run", False)
    scanner_pattern = config.get("scanner_pattern", r"^BRW\d+")

    logging.info(f"Processing doc {doc_id}: {doc_title}")

    try:
        content = get_document_content(doc_id, config)
    except Exception as e:
        logging.error(f"  Failed to get content for doc {doc_id}: {e}")
        return

    if not content.strip():
        logging.warning(f"  Doc {doc_id} has no OCR content, skipping")
        return

    title = infer_title(content, config)

    if not is_valid_title(title, scanner_pattern):
        logging.warning(f"  Doc {doc_id}: LLM returned unusable title {title!r}, skipping")
        return

    if dry_run:
        logging.info(f"  [DRY RUN] Would rename to: {title}")
    else:
        try:
            update_document_title(doc_id, title, config)
            logging.info(f"  Renamed to: {title}")
        except Exception as e:
            logging.error(f"  Failed to update doc {doc_id}: {e}")


def process_all_pending(config: dict) -> None:
    try:
        docs = get_pending_documents(config)
    except Exception as e:
        logging.error(f"Failed to fetch documents from Paperless: {e}")
        return

    for doc in docs:
        process_document(doc["id"], doc["title"], config)
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rename Paperless-NGX scanner documents using LLM title inference")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Preview titles without applying changes")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one pass and exit")
    mode.add_argument("--daemon", action="store_true", help="Poll on a schedule")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.dry_run:
        config["dry_run"] = True

    setup_logging(config)

    if args.daemon or config.get("mode") == "daemon":
        interval = config.get("scheduling", {}).get("interval_minutes", 30) * 60
        logging.info(f"Running in daemon mode, interval {interval // 60} minutes")
        while True:
            process_all_pending(config)
            logging.info(f"Sleeping {interval // 60} minutes until next run")
            time.sleep(interval)
    else:
        process_all_pending(config)


if __name__ == "__main__":
    main()
