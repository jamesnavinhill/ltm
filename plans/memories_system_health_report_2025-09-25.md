## Systems check — Memories testing report (2025-09-25)

### Executive summary
- Python (mem0 OSS): Core tests mostly pass, but graph-memory patching fails when optional graph deps aren’t installed. Result: 16 passed, 13 errors.
- TypeScript (mem0-ts): Test suites fail due to API signature/type drift (tests still use old call shapes). Result: 2 suites failed, 0 tests executed.
- The issues are primarily configuration and compatibility, not runtime service outages.

---

### What was run
- Python
  - Created venv and installed project with tests: see `pytest-output.txt` in repo root.
  - Focused run: `tests/test_main.py`, `tests/test_proxy.py`, `tests/test_memory.py`, `tests/test_telemetry.py`.

- TypeScript
  - In `mem0-ts`: `pnpm i` then `pnpm test`; output captured to `jest-output.txt` one level above `mem0-ts/`.

---

### Key failures and root causes

1) Python: Import/patch failure for graph memory
- Symptom (from `pytest-output.txt`): AttributeError: module `mem0.memory` has no attribute `graph_memory` while patching `mem0.memory.graph_memory.MemoryGraph`.

Code under test references the graph module:
```21:26:tests/test_main.py
        patch("mem0.utils.factory.EmbedderFactory") as mock_embedder,
        patch("mem0.memory.main.VectorStoreFactory") as mock_vector_store,
        patch("mem0.utils.factory.LlmFactory") as mock_llm,
        patch("mem0.memory.telemetry.capture_event"),
        patch("mem0.memory.graph_memory.MemoryGraph"),
        patch("mem0.memory.main.GraphStoreFactory") as mock_graph_store,
```

The graph backends hard-import optional deps. If they’re missing, import fails, breaking the patch site:
```5:13:mem0/memory/graph_memory.py
try:
    from langchain_neo4j import Neo4jGraph
except ImportError:
    raise ImportError("langchain_neo4j is not installed. Please install it using pip install langchain-neo4j")
```

```5:13:mem0/memory/kuzu_memory.py
try:
    import kuzu
except ImportError:
    raise ImportError("kuzu is not installed. Please install it using pip install kuzu")
```

Why this shows as AttributeError: The patch resolver attempts to import `mem0.memory.graph_memory`; the ImportError from optional deps causes the resolver to fall back to attribute lookup on the parent package, which then raises AttributeError.

2) TypeScript: API signature/type drift in tests
- Errors indicate the new API requires an options object rather than a bare `userId` string, and `Message.role` is a strict union type.

Current API surface for add:
```155:164:mem0-ts/src/oss/src/memory/index.ts
async add(
  messages: string | Message[],
  config: AddMemoryOptions,
): Promise<SearchResult> {
  // ... uses config.userId/agentId/runId
```

Representative failures (from `jest-output.txt`):
```text
error TS2559: Type 'string' has no properties in common with type 'AddMemoryOptions'.
  at tests calling: await memory.add(messages, userId)

error TS2345: Argument of type '{ role: string; content: string; }[]' is not assignable to parameter of type 'Message[]'.
  'role' must be '"user" | "assistant"'
```

---

### Remediation plan (prioritized)

1) Python: Make graph backends soft-optional (recommended)
- Change graph modules to degrade gracefully when optional deps are missing so the module still imports and tests can patch.
  - In `mem0/memory/graph_memory.py` and `kuzu_memory.py`, replace hard fail with minimal fallbacks (e.g., stub `Neo4jGraph` / `BM25Okapi` / `kuzu` usage) that only raise on use. This allows patching without requiring the deps.
- Alternatively, mark graph-dependent tests with `pytest.importorskip("langchain_neo4j")` or guard patches behind availability checks.
- If you prefer installing deps: install extras before running tests:
  - Windows PowerShell
    - `python -m venv .venv`
    - `.\.venv\Scripts\python -m pip install --upgrade pip`
    - `.\.venv\Scripts\pip install -e .[test,graph]`
    - `.\.venv\Scripts\pytest -q`

2) Python: Expose submodules in `mem0.memory`
- Optionally add exports in `mem0/memory/__init__.py` so `mem0.memory.graph_memory` resolves predictably (still requires soft-optional imports to avoid ImportError):
  - `from . import graph_memory, kuzu_memory  # noqa: F401`

3) TypeScript: Update tests to new API shapes
- Replace all calls like:
  - `await memory.add(messages, userId)` → `await memory.add(messages, { userId })`
  - `await memory.getAll(userId)` → `await memory.getAll({ userId })`
  - `await memory.search(query, userId)` → `await memory.search(query, { userId })`
- Ensure `Message[]` uses strict roles:
  - `{ role: "user" | "assistant", content: string }`
- In `memoryClient.test.ts`, update:
  - `client.add(messages, { user_id: userId })` to match the client’s expected `Message[]` type and options naming used by the current client.
  - `client.deleteUser(entity.id)` if the signature is now `deleteUser({ entity_id, entity_type })`.

4) CI/Dev ergonomics
- Document correct PowerShell invocations to avoid pipeline/pager issues:
  - Use `.\.venv\Scripts\pip.exe` and `.\.venv\Scripts\pytest.exe` on Windows.
  - Avoid piping to non-PowerShell commands like `| cat`; use `Tee-Object` for capture.

---

### Re-run checklist
- Python
  - Fresh env and install with extras: `.\.venv\Scripts\pip install -e .[test,graph]`
  - Run: `.\.venv\Scripts\pytest -q`

- TypeScript
  - `cd mem0-ts && corepack enable && pnpm i && pnpm test`

---

### Appendix — Evidence excerpts

Python error excerpt:
```text
ERROR ... patch("mem0.memory.graph_memory.MemoryGraph") ...
E   AttributeError: module 'mem0.memory' has no attribute 'graph_memory'
```

TypeScript error excerpts:
```text
TS2559: Type 'string' has no properties in common with type 'AddMemoryOptions'.
TS2345: Argument of type '{ role: string; content: string; }[]' is not assignable to parameter of type 'Message[]'.
  Type 'string' is not assignable to type '"user" | "assistant"'.
```

---

### Bottom line
- Systems are largely intact; issues are test-time configuration and API drift.
- Implement soft-optional graph imports (or install graph extras) and update TS tests to the current API to restore green test runs.


