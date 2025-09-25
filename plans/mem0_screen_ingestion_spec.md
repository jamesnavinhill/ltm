# Automated Screen Ingestion → Mem0/OpenMemory Specification

## 1. Purpose and scope

- Deliver an automated Windows capture service that converts foreground screen content into structured long-term memories using the existing Mem0/OpenMemory stack.
- Enable multi-profile routing so that each MCP client (e.g., work vs. personal) receives scoped recall via OpenMemory’s SSE MCP server (`openmemory/api/app/mcp_server.py`).
- Ground the design in current OSS behavior: Mem0’s `Memory.add` workflow (`mem0/memory/main.py`) and OpenMemory’s REST + SQL persistence (`openmemory/api/app/routers/memories.py`).

### In-scope

1. Capturing screen text via OCR and preparing payloads with deduplication metadata.
2. Submitting memories through OpenMemory’s REST API (`POST /api/v1/memories/`) or MCP tool (`add_memories`).
3. Managing identifiers (`user_id`, `app`, `agent_id`) to keep profiles isolated.
4. Operating against Qdrant (default vector store) and SQLite history as configured in Mem0.

### Out-of-scope

- Building a brand-new MCP server (reuse OpenMemory).
- Replacing Mem0’s LLM prompts or vector store providers beyond configuration surface already exposed in `MemoryConfig`.
- Automating hosted Platform flows (self-hosted only for now).

## 2. Stakeholders and success criteria

- **Primary user**: James, who wants cross-editor MCP recall from personal/work profiles.
- **Secondary**: Contributors enhancing Mem0/OpenMemory ingestion tooling.
- **Success metrics**:
  - OCR agent posts at least one memory per distinct capture, visible in OpenMemory UI and retrievable through MCP `search_memory`.
  - Duplicate captures skipped ≥ 90% of the time (compare normalized hash cache vs. Mem0’s update step).
  - End-to-end latency (capture → memory accessible through MCP) under 15 seconds in local environment.

## 3. Background recap (ground-truth references)

- **Mem0 core** (`mem0/memory/main.py`):
  - `Memory.add` enforces at least one of `user_id | agent_id | run_id` via `_build_filters_and_metadata`.
  - With `infer=True`, Mem0 extracts facts, generates embeddings via configured embedder (e.g., Gemini) and writes to vector store with metadata including `hash`, timestamps, `user_id`, etc.
  - Object storage uses the configured vector provider (default Qdrant) and appends history rows to SQLite via `SQLiteManager`.
- **OpenMemory API** (`openmemory/api/app/routers/memories.py`):
  - `POST /api/v1/memories/` takes `user_id`, `text`, `metadata`, `infer`, `app` (profile name).
  - Handler fetches/creates the SQL `App`, calls `get_memory_client().add(...)`, persists `Memory` rows sharing the Mem0-generated UUID.
- **OpenMemory MCP server** (`openmemory/api/app/mcp_server.py`):
  - SSE route `/mcp/{client_name}/sse/{user_id}` channels tools `add_memories`, `search_memory`, `list_memories`, `delete_all_memories`.
  - Tools resolve the same Mem0 client, enforce per-app permissions, and log access via `MemoryAccessLog`.

## 4. User stories

1. *As a user*, I can press a hotkey to capture the active window, and within seconds, have the factual summary appear in my `work` profile memories.
2. *As a user*, I can run periodic background capture with dedupe so repeating meetings or static screens don’t spam the memory store.
3. *As a user*, I can query from an MCP-enabled IDE (Cursor, Claude, Windsurf) and get context-limited recall per profile.

## 5. High-level architecture

1. **Capture Service (Windows Agent)**
   - Language: Python (reuse `pytesseract`, `mss`, `pywin32`) or Node (alternative). Initial implementation targets Python.
   - Responsibilities: capture screens triggered by hotkey/timer, gather metadata (window title, process name), persist temporary PNG.
2. **OCR + Normalization Module**
   - Use `pytesseract.image_to_string` (local Tesseract). Normalize text (strip noise, join lines, lower-case optional, remove duplicates).
   - Deduplicate using rolling cache keyed by MD5 hash of normalized text (`hashlib.md5` mirrored from Mem0’s `_create_memory`).
3. **Ingestion Adapter**
   - POST to OpenMemory: `http://localhost:8765/api/v1/memories/` with JSON body.
   - Fallback direct Mem0 SDK using `Memory.add` when OpenMemory unreachable, but still supply metadata enabling future re-sync.
4. **Storage & Recall**
   - Mem0 handles fact extraction, vector insertion, history log; OpenMemory mirrors the vector UUID into SQL for UI and MCP scoping.
5. **MCP Integration**
   - For each profile, install SSE endpoint `.../mcp/<profile>/sse/<user_id>`.
   - MCP tool search uses Mem0 `vector_store.search` with filters containing `user_id` from context.

## 6. Detailed design

### 6.1 Capture triggers

- **Hotkey**: system-level listener (e.g., `keyboard` Python library) to request immediate capture.
- **Interval mode**: configurable (default 15s) but only captures when active window changes or last hash differs.
- **Whitelist**: JSON config enumerating allowed process names or window title substrings.

### 6.2 Metadata schema

```json
{
  "user_id": "james",
  "app": "work",
  "metadata": {
    "source": "screen-ocr",
    "window_title": "Visual Studio Code",
    "process": "Code.exe",
    "monitor_id": 1,
    "capture_mode": "interval",
    "ocr_hash": "...",
    "screenshot_path": "optional for debugging"
  },
  "infer": true,
  "text": "Captured plain text..."
}
```

- `app` is required for OpenMemory to map to an `App` row; aligns with `request.app` in `create_memory` router.
- `user_id` must match the SSE path user for MCP compatibility (e.g., `work` MCP uses same `james`).

### 6.3 Deduplication

- Pre-ingest dedupe: maintain an LRU cache keyed by `ocr_hash`; skip if hash seen in past N minutes.
- Secondary dedupe: rely on Mem0’s `Memory.add` update logic—existing vector search uses `filters` containing `user_id` and `agent_id/run_id` if provided.

### 6.4 Error handling

- If OpenMemory returns `{ "error": ... }`, log and queue payload for retry (e.g., SQLite queue).
- When Mem0 client unavailable (`get_memory_client_safe` returns None), degrade gracefully and persist to local queue.
- Provide manual reprocess command that drains queue once OpenMemory reachable.

### 6.5 Configuration management

- YAML or TOML file co-located with capture agent specifying:
  - `openmemory_url`, `user_id`, `profiles` (map of hotkeys/whitelist to `app` names), `capture_interval`, dedupe thresholds.
  - `tesseract_path` if not in PATH.
  - Optional `mem0_config_path` to ensure the OpenMemory backend is already configured for Gemini (see `openmemory/ui` settings).

### 6.6 Deployment assumptions

- OpenMemory stack running locally via `openmemory/Makefile` (`make up`). Qdrant accessible on configured port.
- Capture agent runs on Windows (system tray app eventually; MVP CLI script).
- For packaging, consider PyInstaller once script stable; not required for prototype.

## 7. External integration details

### 7.1 OpenMemory REST contract

- Endpoint: `POST http://localhost:8765/api/v1/memories/`
- Body fields validated by `CreateMemoryRequest` Pydantic model (`user_id: str`, `text: str`, `metadata: dict`, `infer: bool`, `app: str`).
- Success returns persisted `Memory` row with `id` matching Mem0 vector ID (UUID).
- Errors include: `403` if app paused, `404` if user missing, JSON error when Mem0 client missing.

### 7.2 Mem0 client behavior

- `memory_client.add` expects `messages` parameter; OpenMemory passes plain string leading to `Memory.add` converting to `[{"role": "user"...}]`.
- When `infer=True`, Mem0 calls provider-specific LLM via `self.llm.generate_response`; ensure Gemini config present in `MemoryConfig` persisted by OpenMemory.
- Embedding dims must match vector store (Gemini `text-embedding-004` = 768, Qdrant collection should match via `MemoryConfig.vector_store.config.embedding_model_dims`).

### 7.3 MCP consumption

- Tools in `mcp_server.py` rely on contextvars `user_id` and `client_name`. SSE installer command `npx @openmemory/install local http://localhost:8765/mcp/work/sse/james --client work` ensures `client_name` = profile.
- `search_memory` manually embeds query via `memory_client.embedding_model.embed` and filters accessible `Memory` IDs from SQL permission checks.

## 8. Data retention and privacy

- Screenshots stored transiently (delete PNG after OCR unless debug flag set).
- Provide optional regex scrubber for PII (emails, credit card patterns) before submission.
- Maintain local queue encrypted at rest if storing raw text (consider Windows DPAPI or simple AES with key in config for later iteration).

## 9. Operational concerns

- **Monitoring**: log accepted/skipped captures; optionally send metrics to local Prometheus (future work).
- **Telemetry**: Mem0 already logs events via `capture_event` (see `mem0/memory/main.py`), no additional instrumentation required but can hook into logs for debugging.
- **Resource usage**: Tesseract CPU spikes; throttle captures to avoid >50% utilization.

## 10. Testing strategy

1. **Unit tests** (Python capture agent)
   - Hash dedupe logic.
   - Window whitelist evaluation.
   - Retry queue serialization/deserialization.
2. **Integration tests**
   - Mock OpenMemory endpoint (FastAPI TestClient) verifying payload structure.
   - Local end-to-end against real OpenMemory + Qdrant container.
3. **Manual validation**
   - Launch OpenMemory UI, confirm memory created with metadata and `App.name` = profile.
   - Connect MCP client and run `search_memory("text snippet")`.

## 11. Risks & mitigations

- **OCR accuracy**: mitigate by toggling language packs and optional summarization (Gemini) before ingestion.
- **Duplicate noise**: combination of local hash cache and Mem0 conflict resolution should prevent buildup; monitor `mem0/memory/main.py` history table for churn.
- **Service availability**: queue unsent payloads if OpenMemory offline; expose CLI to reprocess.
- **Gemini quota limits**: allow fallback to OpenAI provider by updating OpenMemory config or providing local `infer=False` mode to store raw text when key exhausted.

## 12. Milestones

1. Prototype capture → OCR → OpenMemory POST (single profile, manual run).
2. Add dedupe cache and metadata enrichment.
3. Introduce config-driven multi-profile routing + MCP install script wrappers.
4. Package agent (virtualenv + Windows service or tray icon).
5. Harden with tests, logging, and documentation updates.

---

## References

- `plans/mem0_audit_report.md`
- `mem0/memory/main.py`
- `openmemory/api/app/routers/memories.py`
- `openmemory/api/app/mcp_server.py`
- `mem0/llms/gemini.py`, `mem0/embeddings/gemini.py`
