# Changelog

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
