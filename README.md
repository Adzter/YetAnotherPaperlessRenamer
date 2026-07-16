# YAPR - Yet Another Paperless Renamer

Renames scanner-dumped documents in Paperless-NGX using an LLM to infer a title from OCR text.

`BRW008092DD78D4_073434` -> `HSBC Mortgage Statement Q1 2024`

Supports Ollama (local) or Anthropic (cloud).

## Setup

```bash
cp config.yaml my-config.yaml
# edit with your Paperless URL, token, and LLM settings
```

**Docker:**
```bash
docker compose up -d
docker logs -f paperless-rename
```

**Python:**
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python rename_documents.py --dry-run
.venv/bin/python rename_documents.py
```

## Config

```yaml
paperless:
  url: "http://192.168.0.10:8000"
  token: "your-token"           # Settings -> API in Paperless UI
                                # or set PAPERLESS_TOKEN env var

scanner_pattern: "^BRW\\d+"    # regex matching titles that need renaming

llm:
  provider: "ollama"            # "ollama" or "anthropic"

  ollama:
    url: "http://ollama-host:11434"
    model: "mistral:7b"             # recommended, pull with: ollama pull mistral:7b

  anthropic:
    api_key: ""                 # or set ANTHROPIC_API_KEY env var
    model: "claude-haiku-4-5"

  max_content_chars: 3000       # truncates to ~1 page

scheduling:
  interval_minutes: 30

logging:
  level: "INFO"
  file: ""                      # leave empty for stdout

dry_run: false
```

## Usage

```bash
python rename_documents.py --once        # one pass, good for cron
python rename_documents.py --daemon      # run continuously
python rename_documents.py --dry-run     # preview without changes
python rename_documents.py --config /path/to/config.yaml
```

**Cron:**
```cron
*/30 * * * * /path/to/.venv/bin/python /path/to/rename_documents.py --once
```
