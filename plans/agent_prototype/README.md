# Windows Screen Ingestion Agent (Prototype)

This prototype captures the foreground screen, runs OCR, deduplicates, and submits memories to OpenMemory.

## Prerequisites

- Python 3.11+ on Windows
- Tesseract OCR installed:
  - Download installer and add to PATH or set `tesseract_path` in `agent.config.yaml`
- Install Python dependencies:
  - `pip install mss pytesseract pywin32 psutil httpx pyyaml keyboard`
- OpenMemory stack running locally (recommended):
  - See `openmemory/README.md` for instructions (e.g., `make up`)

## Configuration

See `agent.config.yaml` for defaults:
- `openmemory_url`, `user_id`
- `profiles`: hotkeys and whitelists mapping to `app` (profile name)
- `capture_interval_sec`, `dedupe_ttl_sec`
- `log_path`, `log_level`, `foreground_change_only`

## Usage

Run once:

```bash
python -m plans.agent_prototype.cli once --config plans/agent_prototype/agent.config.yaml --profile work
```

Run foreground-change loop:

```bash
python -m plans.agent_prototype.cli loop --config plans/agent_prototype/agent.config.yaml
```

Run global hotkeys listener:

```bash
python -m plans.agent_prototype.cli hotkeys --config plans/agent_prototype/agent.config.yaml
```

Drain queued payloads:

```bash
python -m plans.agent_prototype.cli drain --config plans/agent_prototype/agent.config.yaml
```

## Notes

- PNGs are deleted after OCR unless `debug_keep_png` is true.
- Logs go to stdout unless `log_path` is set.
- The agent can run without the OpenMemory server; failed submissions are queued locally for later drain.
