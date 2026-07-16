# YAPR - Yet Another Paperless Renamer

Renames scanner-dumped documents in Paperless-NGX using an LLM to infer a title from OCR text.

`BRW008092DD78D4_073434` -> `HSBC Mortgage Statement Q1 2024`

Supports Ollama (local) or Anthropic (cloud). Three run modes: one-shot, daemon, or event-driven via Paperless webhooks.

## Setup

```bash
cp config.yaml.template config.yaml
# edit config.yaml with your Paperless URL, token, and LLM settings
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

mode: "webhook"                 # "once", "daemon", or "webhook"

webhook:
  port: 8080                    # webhook mode only

scheduling:
  interval_minutes: 30          # daemon mode only

llm:
  provider: "ollama"            # "ollama" or "anthropic"

  ollama:
    url: "http://ollama-host:11434"
    model: "mistral:7b"         # recommended, pull with: ollama pull mistral:7b

  anthropic:
    api_key: ""                 # or set ANTHROPIC_API_KEY env var
    model: "claude-haiku-4-5"

  max_content_chars: 3000       # truncates to ~1 page

logging:
  level: "INFO"
  file: ""                      # leave empty for stdout

dry_run: false
```

## Modes

### Webhook (recommended)

YAPR listens for HTTP POST requests from Paperless and processes each document as it arrives.

**Configure in Paperless:**
1. Go to Settings -> Workflows -> Add Workflow
2. Trigger: Document Added
3. Action: Webhook -> `http://<yapr-host>:8080/webhook`

Set `mode: "webhook"` in config, then start YAPR. Documents are renamed as soon as Paperless finishes consuming them.

### Daemon

Polls Paperless on a schedule, processing any documents matching `scanner_pattern`.

Set `mode: "daemon"` and `scheduling.interval_minutes` in config.

### One-shot

Runs once and exits. Good for cron.

```cron
*/30 * * * * /path/to/.venv/bin/python /path/to/rename_documents.py --once
```

## CLI

```bash
python rename_documents.py --once        # one pass and exit
python rename_documents.py --daemon      # poll on schedule
python rename_documents.py --webhook     # listen for webhooks
python rename_documents.py --dry-run     # preview without changes
python rename_documents.py --config /path/to/config.yaml
```

CLI flags override `mode` in config.
