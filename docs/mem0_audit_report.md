# Mem0 OSS Audit and Automated Screen-Ingestion Design (with Gemini)

## Executive summary

- Mem0 is a long‑term memory layer for AI agents. It extracts facts from interactions, deduplicates/conflicts them against existing memories, stores them in a vector DB (optionally with a graph store), and retrieves relevant context fast.
- Ingestion options today: Python/TS SDKs (OSS), a lightweight REST server (`server/`), the hosted Platform client (`mem0.client`), and the OpenMemory project (self‑hosted API + MCP server + UI) that bridges memories to MCP clients.
- Gemini support exists for both LLM and embeddings. Vision is supported in Mem0’s pipeline when LLM implementations support multimodal inputs; for Gemini specifically, rely on OCR for screenshots initially.
- Your goal (automated screen extraction → dedupe/summarize → Mem0 → MCP across profiles) fits best with OpenMemory’s MCP server and per‑client “profiles”. Implement a lightweight Windows capture + OCR service that feeds OpenMemory or Mem0 directly using `user_id` plus per‑profile `client_name` (or `agent_id`).

---

### What the memory system does now

## 1) Core capabilities

- Fact extraction (LLM‑driven): Given messages, Mem0 prompts an LLM to extract “facts” worth remembering, then prompts again to decide per‑fact whether to ADD/UPDATE/DELETE/NONE.
- Storage: Facts are embedded and written to a pluggable vector store (Qdrant default; many supported). Each memory payload includes `data` (original text), `hash`, timestamps, and any passed metadata. Optional graph memory builds relationships for richer retrieval.
- Retrieval: Semantic search (by embedding), plus filtering by `user_id`, `agent_id`, `run_id` to scope memory. Graph search is optional.
- History: Every mutation logs a row in a local SQLite history DB (OSS) to audit memory evolution.

## 2) Key modules (Python OSS)

- `mem0/memory/main.py` (core)
  - `Memory.add(...)`: validates identifiers, optionally parses multimodal messages, runs the extraction/update prompts, and calls `ADD/UPDATE/DELETE` handlers.
  - `_create_memory/_update_memory/_delete_memory`: writes to vector store and appends to local history.
  - `search/get/get_all/history/reset`: standard operations with scoping via `user_id | agent_id | run_id`.
- Providers
  - LLMs: `mem0/llms/*` with a factory in `mem0/utils/factory.py` (providers include openai, anthropic, gemini, groq, aws_bedrock, azure_openai, litellm, etc.).
  - Embeddings: `mem0/embeddings/*` (includes Google GenAI embeddings for Gemini).
  - Vector stores: `mem0/vector_stores/*` (qdrant, chroma, pgvector, pinecone, weaviate, redis, faiss, elasticsearch, milvus, opensearch, supabase, vertex ai, etc.).
- Prompts
  - `FACT_RETRIEVAL_PROMPT`: extracts “facts”.
  - `DEFAULT_UPDATE_MEMORY_PROMPT`: resolves dedupe/conflict via ADD/UPDATE/DELETE/NONE.
- Vision support
  - `parse_vision_messages(...)` routes image messages to `llm.generate_response` for descriptions before fact extraction.
  - Note: current Gemini LLM implementation handles text well; for screenshots prefer OCR → text for reliable ingestion.

## 3) TypeScript OSS SDK (`mem0-ts`)

- Mirrors core Memory flow: `add/search/get/getAll/update/delete`, provider factories (LLM/Embedder/Vector), and optional graph memory. Useful if you prefer a Node capture service.

## 4) REST API (OSS server)

- `server/` (FastAPI) exposes endpoints for `configure`, `memories` (add/get/get by id/update/history), and `search`. Good for lightweight, local microservice ingestion without embedding SDK code in your capture app.

## 5) OpenMemory (self‑hosted API + UI + MCP)

- `openmemory/` runs a FastAPI backend and Next.js UI, plus an MCP server (`/mcp/.../sse/...`).
- The MCP server defines tools to `add`, `search`, `list`, and `delete_all`. Each SSE connection sets `user_id` and `client_name`; created memories are recorded both in the vector store and in OpenMemory’s SQL DB and are filtered by “app/client” permissions.
- This is the most turnkey way to expose your personal memory profiles to MCP clients (Cursor, Claude, Windsurf, etc.).

---

### How ingestion works today

- Python OSS SDK
  - Call `Memory.add(messages=[...], user_id=..., agent_id=..., run_id=..., metadata=..., infer=True)`.
  - With `infer=True` (default), LLM extraction + dedupe/updates occur automatically.
  - With `infer=False`, raw messages are stored as memories (no LLM extraction).

- TypeScript OSS SDK
  - `new Memory(config).add(messages, { userId, agentId, runId, metadata, infer })` with similar semantics.

- REST server (OSS)
  - POST `/memories` with `messages` + at least one of `user_id|agent_id|run_id`.
  - GET `/memories` (scoped), GET `/memories/{id}`, POST `/search`, PUT `/memories/{id}`.

- Hosted Platform client (`mem0.client.MemoryClient`)
  - For managed API. Not needed if you self‑host.

- OpenMemory API + MCP
  - API route `POST /memories/` (OpenMemory) calls Mem0 to add, then persists the memory id + app/user in SQL so MCP tools can scope/filter.
  - MCP route `GET /mcp/{client_name}/sse/{user_id}` hosts tools for add/search/list/delete scoped to that app/client.

---

### Provider abstraction and Gemini support

- LLM providers are pluggable via factories. Gemini is supported (text); embeddings via `google-genai` are also supported.
- Recommended for screenshots: use Gemini for the prompts but extract text with OCR first (see design below). If you want LLM‑vision descriptions, use OpenAI multimodal in Mem0 for that step while keeping Gemini for other prompts.
- Minimal Python config (Gemini for LLM and embeddings):

```python
import os
from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.vector_stores.configs import VectorStoreConfig
from mem0.llms.configs import LlmConfig
from mem0.embeddings.configs import EmbedderConfig

config = MemoryConfig(
    vector_store=VectorStoreConfig(
        provider="qdrant",
        config={"host": "localhost", "port": 6333, "collection_name": "mem0_screens"},
    ),
    llm=LlmConfig(
        provider="gemini",
        config={"api_key": os.getenv("GOOGLE_API_KEY"), "model": "gemini-2.0-flash"},
    ),
    embedder=EmbedderConfig(
        provider="gemini",
        config={"api_key": os.getenv("GOOGLE_API_KEY"), "model": "models/text-embedding-004", "embedding_dims": 768},
    ),
    version="v1.1",
)

mem = Memory(config)
mem.add(
    messages=[{"role": "user", "content": "Detected calendar: meeting Tue 2pm with Alex."}],
    user_id="james",
    metadata={"source": "screen-ocr", "window": "outlook"},
)
```

---

### Designing your automated screen‑extraction ingestion pipeline (Windows)

Goal: lightweight app that watches screens/monitors, extracts text, dedupes/summarizes if necessary, then feeds Mem0; expose profiles via MCP.

## Capture strategy

- Trigger: hotkey, clipboard change, window focus change, or periodic sampling (e.g., every N seconds while foreground app is whitelisted).
- Tools (Windows):
  - Python: `mss` (fast screenshots), `pywin32`/`pygetwindow` for active window titles/handles.
  - Node: `screenshot-desktop`, `robotjs` (or `@nut-tree/nut-js`), `active-win`.
- Multi‑monitor: tag captures with `monitor_id` and `window_title` in metadata.

## 2) OCR and normalization

- OCR: Tesseract (`pytesseract`) locally, or cloud OCR if needed (Azure Computer Vision, Google Cloud Vision). Start with Tesseract for privacy and speed.
- Normalize: strip timestamps, transient counters, hex hashes, >N repeated lines, and compress whitespace. Keep a rolling cache of recent OCR outputs (per window) and skip if near‑duplicate by:
  - Exact hash (MD5) of normalized text.
  - Cosine similarity of embeddings over 0.95 threshold.

## 3) Chunking and summarization (optional)

- For large captures, chunk by paragraph or layout region; optionally summarize to a short “fact” list using your Gemini LLM before passing to Mem0. However, Mem0 can perform extraction/dedupe internally (`infer=True`). Prefer feeding raw clean text and let Mem0’s extraction prompts decide.

## 4) Submission to the memory system

- Option A: OpenMemory API (recommended for MCP integration)
  - POST `http://localhost:8765/memories/` with body: `{ user_id, text, metadata, app }` where `app` is your profile name (e.g., `work`, `personal`, `monitor-1`). OpenMemory writes both the vector store and its SQL DB for per‑app scoping.
- Option B: Mem0 OSS REST server
  - POST `http://localhost:8000/memories` with `{ messages: [...], user_id, agent_id?, run_id?, metadata?, infer? }`.
- Option C: Direct SDK
  - Call `Memory.add(...)` from your app with appropriate identifiers and metadata.

## 5) Identifiers and profiles

- Use `user_id="james"` for scoping across devices.
- Use profiles via OpenMemory MCP path `.../mcp/<client_name>/sse/<user_id>` where `<client_name>` is your profile key (e.g., `work`, `personal`, `monitor-2`).
- Alternatively use `agent_id`/`run_id` in raw Mem0 to segregate memories by app/task/session.

## 6) Metadata recommendations

- Include `source`, `window_title`, `process_name`, `monitor_id`, `url` (if browser), `selection_bbox`, and your dedupe hashes.
- These become part of each memory’s payload and are retrievable with search results.

## 7) Rate limiting and privacy

- Apply cooldowns per window (e.g., no more than 1 capture/15s unless hotkeyed).
- Redact obvious PII patterns before submission if desired.

Example ingestion loop (Python, OCR → OpenMemory):

```python
import os, time, hashlib
import mss
import pytesseract
from PIL import Image
import httpx

OPENMEM_URL = "http://localhost:8765"
USER_ID = "james"
PROFILE = "work"  # maps to OpenMemory app/client

seen = set()

def ocr_image(img_path: str) -> str:
    return pytesseract.image_to_string(Image.open(img_path))

with mss.mss() as sct:
    while True:
        filename = sct.shot(output="_screen.png")
        text = ocr_image(filename).strip()
        norm = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        digest = hashlib.md5(norm.encode()).hexdigest()
        if len(norm) > 40 and digest not in seen:  # basic filter
            seen.add(digest)
            payload = {
                "user_id": USER_ID,
                "text": norm,
                "metadata": {"source": "screen-ocr"},
                "app": PROFILE,
                "infer": True,
            }
            try:
                httpx.post(f"{OPENMEM_URL}/memories/", json=payload, timeout=10).raise_for_status()
            except Exception as e:
                print("ingest error:", e)
        time.sleep(10)
```

This relies on OpenMemory’s API to write to Mem0 and its SQL DB, enabling MCP scoping per `app`.

---

### Making outputs available via MCP

## Run OpenMemory

- `make build && make up` in `openmemory/` (or use the provided `run.sh`). Ensure `OPENAI_API_KEY` or your provider keys are set; if you want Gemini for Mem0, update the stored config in the OpenMemory settings UI or DB to `provider: gemini` with `env:GOOGLE_API_KEY`.

## 2) Connect your client(s)

- Install MCP endpoint for a profile:
  - `npx @openmemory/install local http://localhost:8765/mcp/work/sse/james --client work`
  - Repeat for `personal`, `monitor-1`, etc.

## 3) Use tools in the MCP client

- Tools exposed: add_memories(text), search_memory(query), list_memories(), delete_all_memories(). They are scoped by the `{client_name}` (your profile) and `{user_id}`.

## 4) Optionally extend

- If you need agent/run segregation beyond profiles, add `agent_id`/`run_id` to the Mem0 calls in OpenMemory’s MCP server or API router and thread them through as filters.

---

### Configuration tips

- Vector store
  - Start with Qdrant (default). For local dev use Docker `qdrant/qdrant`. Set `collection_name` per use case (`mem0_screens`, etc.).
- Gemini
  - Set `GOOGLE_API_KEY`. Use `gemini-2.0-flash` for extraction/update prompts. Use `models/text-embedding-004` at 768 dims for embeddings (match vector store dims).
- Vision
  - For screenshots, prefer OCR→text with Gemini LLM. If you need LLM‑vision, use OpenAI multimodal in Mem0 for `parse_vision_messages` while keeping Gemini for other prompts, or implement Gemini image parts handling in `mem0/llms/gemini.py`.
- IDs and quotas
  - Always provide at least one of `user_id|agent_id|run_id` to `add/get_all/search`. OpenMemory MCP enforces app‑level filtering on top.

---

### End‑to‑end options recap

- Fastest path to your goal (recommended):
  1) Run OpenMemory (API + MCP + UI).
  2) Build the Windows screen‑OCR feeder (Python example above).
  3) POST to `openmemory /memories/` with `user_id` and `app` per profile.
  4) Connect MCP clients per profile via `.../mcp/{client}/sse/{user}`.

- Alternative: Use the Mem0 OSS REST server or SDK directly, then separately wire a custom MCP server—more work for the same outcome.

---

### Risks, gaps, and recommendations

- Gemini multimodal: current Gemini LLM adapter focuses on text; prefer OCR→text for screenshots, or extend `mem0/llms/gemini.py` to map image parts to `google.genai`’s content parts.
- Dedupe: Mem0’s LLM “update” pass resolves conflicts and avoids bloat; add a pre‑ingest hash/similarity skip to cut noisy duplicates from OCR.
- PII: add simple regex redaction for obvious secrets and IDs before ingestion.
- Performance: aim for ≤1 submission/15s per window unless manually triggered.
- Observability: log accepted/skipped captures; inspect Mem0 histories and OpenMemory UI to validate memory evolution.

---

### Minimal test plan

## 1) Local run

- Start OpenMemory and Qdrant. Confirm `http://localhost:8765/docs` and UI on `:3000`.
- Configure Mem0 in OpenMemory for Gemini or your chosen provider.

## 2) OCR feeder

- Run the Python feeder; trigger a few captures with distinct text; verify OpenMemory UI shows memories for the `work` app.

## 3) MCP

- Install MCP endpoint for `work` and query via your editor/assistant: use `search_memory("meeting")` → ensure expected results.

## 4) Profiles

- Add `personal` endpoint; ingest different content; verify separation between profiles in list/search tools.

---

### Appendix: useful references in the codebase

- Memory add/search core (Python): `mem0/memory/main.py`
- Gemini LLM and embeddings: `mem0/llms/gemini.py`, `mem0/embeddings/gemini.py`
- Provider factories: `mem0/utils/factory.py`, `mem0/llms/configs.py`, `mem0/vector_stores/configs.py`
- REST server (OSS): `server/main.py`
- OpenMemory MCP server: `openmemory/api/app/mcp_server.py`
- OpenMemory API router for memories: `openmemory/api/app/routers/memories.py`
- TypeScript SDK core: `mem0-ts/src/oss/src/memory/index.ts`

---
