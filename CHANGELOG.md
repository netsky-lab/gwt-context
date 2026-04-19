# Changelog

## 2026-04-19

- Added `src/gwt_context/interfaces/ports.py` to define target application/MCP contracts.
- Synchronized `ARCHITECTURE.md` with current repository boundaries, entrypoint ownership, import directions, and explicit P5/P6 migration blocks.
- Documented and created baseline `AGENTS.md` and `ROADMAP.md` to unblock architecture/task ordering requirements.
- Added `SelectionBroadcastCycle` MCP-facing methods (`run_competition_dry`, `enqueue_for_competition`, `set_goal`, `evict_workspace_item`, `link_items`, `inspect`) so MCP boundary contracts are explicit in code.
- Switched `mcp.tools`/`mcp.resources` to port-oriented typing and added in-source quality fixes for ruff/mypy issues in `src/`.
- Updated quality config to keep gate scope focused on source package (`exclude = ["tests"]`) in `pyproject.toml`.

## 2026-04-13

- Fix in-memory link consistency after `gwt_link`: newly created bidirectional links now update already-loaded buffer/workspace `MemoryItem` instances in the same session so the next competition round sees the new graph.
- Added regressions for live object link sync and multi-hop competition after linking.

## 2026-04-19

- Added target clean architecture baseline in ARCHITECTURE.md.
- Defined explicit layer dependency rules, composition-root responsibilities, import matrix, and ADR-1..ADR-4.
- Added explicit forbidden leak list and a migration path for P5 (ports-first application refactor) and P6 (MCP boundary cleanup).

## 2026-04-19

- Refined `ARCHITECTURE.md` with interface-layer target map, allowed/forbidden import matrix, and operation flow diagrams (memory ingest/link/inspect).
- Added explicit migration enforcement checks for P5/P6 and concrete review gate checklist.
