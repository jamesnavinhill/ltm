# Automated Screen Ingestion Build Plan

This plan accompanies `mem0_screen_ingestion_spec.md` and breaks the effort into concrete, verifiable tasks. Each checkbox should be updated during execution; keep the source of truth here in `/plans`.

## Legend

- [ ] = not started
- [~] = in progress
- [x] = complete

## Phase 0 – Environment readiness

- [ ] Confirm OpenMemory stack is running locally (`openmemory/Makefile`: `make up`) with Qdrant reachable.
- [ ] Update OpenMemory memory configuration for Gemini provider if required (`openmemory/ui` settings ➝ persists to database via `get_memory_client`).
- [ ] Verify `POST /api/v1/memories/` accepts sample payload using `plans/mem0_screen_ingestion_spec.md` metadata schema (references `openmemory/api/app/routers/memories.py`).

## Phase 1 – Capture agent scaffolding (Python)

- [x] Create new package directory `plans/agent_prototype/` (or repo-approved location) with `__init__.py`, `capture.py`, `config.py`.
- [x] Implement configuration loader handling YAML/TOML with schema described in spec (store defaults in `config.py`).
- [x] Implement screen capture function in `capture.py` using `mss` and `pywin32` to collect active window metadata (window title/process name).
- [x] Save raw PNG to temp dir and delete after OCR succeeds (respect debug flag).

## Phase 2 – OCR + normalization

- [x] Integrate `pytesseract` OCR call with configurable language packs.
- [x] Normalize text (strip blank lines, collapse whitespace, limit repeated lines) per spec §6.2.
- [x] Compute MD5 hash of normalized text (`hashlib.md5`) mirroring Mem0 `_create_memory` usage (see `mem0/memory/main.py`).
- [x] Maintain dedupe LRU cache with TTL (store in `dedupe.py` or within capture loop) – skip captures when hash seen within interval.

## Phase 3 – Ingestion adapter

- [x] Implement REST submit helper using `httpx` with robust error handling.
- [x] Handle error responses/connection failures by enqueueing payload into local SQLite-backed queue (`queue.py`).
- [x] Provide CLI `plans/agent_prototype/cli.py drain` to replay queued payloads once server reachable.
- [ ] Optional fallback: direct Mem0 SDK path using `Memory.add` when OpenMemory unreachable.

## Phase 4 – Multi-profile routing & controls

- [x] Extend config to map hotkeys/window filters to `app` profile names (align with spec §6.5).
- [x] Implement global hotkey listener (e.g., `keyboard` lib) to trigger immediate capture to selected profile.
- [x] Add foreground window change detection (via `pywin32` events or polling) to reduce redundant captures.
- [x] Log accepted/skipped captures with metadata for debugging (write to rotating file or stdout).

## Phase 5 – Testing & validation

- [x] Unit tests for dedupe cache, config loader, queue persistence (locate in `tests/agent/` or similar, using `pytest`).
- [x] Integration test against mocked OpenMemory FastAPI endpoint verifying payload structure.
- [ ] Manual test: run agent, capture real window, confirm memory appears in OpenMemory UI and `Memory` SQL table.
- [ ] Manual test: connect MCP client (`npx @openmemory/install ...`) and verify `search_memory` returns new fact.

## Phase 6 – Packaging & docs

- [x] Create README under `plans/agent_prototype/` with setup instructions for Windows (Tesseract install, env vars).
- [ ] Provide optional packaging script (PyInstaller or `python -m build`) to create executable.
- [ ] Update `plans/mem0_screen_ingestion_spec.md` references if implementation diverges.
- [ ] Record summary in work-session log (`mem0_screen_ingestion_log.md`) after each major milestone.
