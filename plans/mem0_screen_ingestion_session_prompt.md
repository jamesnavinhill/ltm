# Mem0 Screen Ingestion Session Kickoff Prompt

This drop-in prompt is designed for any contributor spinning up a fresh agent session on the Mem0 screen ingestion initiative. Share or paste the block below to get aligned instantly.

````markdown
You are joining the Mem0 screen ingestion effort. Follow this workflow end-to-end before wrapping the session:

1. Read these three documents to ground yourself:
   - `plans/mem0_screen_ingestion_spec.md` (overview, architecture, requirements)
   - `plans/mem0_screen_ingestion_build_plan.md` (phase checklist with tasks)
   - `plans/mem0_screen_ingestion_log.md` (latest summaries and decisions)
2. Identify the next unchecked item(s) in the build plan and complete the entire phase or task you select. Avoid scattershot progress.
3. While working, keep everything rooted in the referenced files and existing code (e.g., `mem0/memory/main.py`, `openmemory/api/app/routers/memories.py`, `openmemory/api/app/mcp_server.py`).
4. When you finish the chosen work:
   - Update the checkbox status directly in `mem0_screen_ingestion_build_plan.md`.
   - Append a new entry to `mem0_screen_ingestion_log.md` capturing what changed, artifacts touched, decisions, blockers, next steps grounded in the build plan.
5. If new TODOs emerge, add them under the appropriate phase in the build plan before leaving.
6. Leave the workspace ready for the next agent (clean working tree, documented follow-ups, passing checks if code was executed).

Report back with a concise summary of actions, verification steps taken, and any unresolved items.
````

## Usage notes

- Keep this document alongside the spec, build plan, and log in `/plans` so every session starts from the same source of truth.
- If workflow expectations change, update this prompt first, then reflect those changes in the other planning documents.
- Encourage agents to cite specific files or functions when describing their work to maintain auditability.
