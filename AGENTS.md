# AGENTS.md

## Repository Conventions

- Language: Python 3.11+, type hints required (`[tool.mypy]` uses strict mode).
- Entrypoint: `src/gwt_context/__main__.py` calls `gwt_context.server:main`.
- Composition root: `src/gwt_context/server.py` only; business logic belongs in `application/` or `domain/`.
- MCP entry layer (`src/gwt_context/mcp/`) must delegate to application services and avoid reading private state directly.
- Task order for architectural work:
  1. Stabilize contract/documentation
  2. P5: move application dependencies behind `interfaces/` ports
  3. P6: remove MCP dependence on concrete domain/infrastructure internals
  4. P7/P8 benchmark and run workflows

## Quality Gates

- Run `pytest` for behavior.
- Run `ruff check .` before merge.
- Run `mypy .` before merge.

