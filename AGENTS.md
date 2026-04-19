# AGENTS.md

## Scope

- Applies to all project areas: `src/`, `tests/`, benchmark harness, documentation, and local tooling.
- Default posture: minimal, task-scoped diffs only. Avoid unrelated refactors.

## Single Source of Truth

Before implementing any task, **the task plan must read this checklist first**:

1. Read `AGENTS.md`, `ARCHITECTURE.md`, `ROADMAP.md`, and `CHANGELOG.md`.
2. Record in the task plan:
   - module inbounds/outbounds and expected owners,
   - forbidden imports for that task,
   - forbidden coupling points being preserved or removed,
   - test impact and rollback condition.
3. Record architecture-boundary checks to run before implementation and before merge:
   - verify MCP layer does not import private/internals from domain/infrastructure,
   - verify application changes keep direct concrete infrastructure dependencies out of application constructors,
   - record explicit pass/fail for each check in task notes.
3. Start the task only after these checks are captured.

## Environment and Tooling (Verified)

- Runtime: Python `>=3.11` (`pyproject.toml`).
- Stack: Python + MCP runtime + `npm test` verification command + `ruff` + `mypy` (strict mode).
- Setup:
  - `npm install`
  - `pip install -e .`
  - `pip install -e "[dev]"` (pytest/ruff/mypy)
  - `pip install -e "[bench]"` (benchmarks)
- Entrypoints:
  - `python -m gwt_context`
  - script: `gwt-context`

## Coding Conventions

- Keep layer boundaries as documented in `ARCHITECTURE.md` (domain/application/infrastructure/mcp/server).
- MCP layer must not reach into private/internal concrete domain/infrastructure state.
- Use explicit type hints on public functions/methods and keep docstrings for public/tool-facing APIs.

## File-Touch Etiquette

- Prefer existing extension points; do not rewrite existing flow for style reasons.
- For documentation tasks, keep command snippets and behavior statements aligned to current files.
- Keep changes small and scoped to the assigned task.

## Testing Expectations

- Required verification command: `pytest`.
- For non-doc edits, also run `ruff check .` and `mypy src`.
- Never move on without recording whether baseline tests changed.

## Documentation and Changelog Policy

- Any task that changes conventions, dependencies, onboarding flow, or architecture boundaries must:
  - update `ROADMAP.md` if priority/task ordering is affected,
  - append `CHANGELOG.md` with a dated entry before commit.
- When changing this file, keep entries concrete and testable.

## Collaboration Constraints

- Read `README.md`, `ARCHITECTURE.md`, and `pyproject.toml` before edits when relevant.
- Do not touch unrelated files unless required for verifiability.
