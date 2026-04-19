# ROADMAP

## Current Focus

- P4: Define and lock down target clean architecture boundaries (done in this task).
- P5: Refactor application layer to depend on ports/ABCs from `src/gwt_context/interfaces/ports.py`.
- P6: Clean MCP boundary so tools/resources use only application ports and read-model DTOs.
- P7: Stabilize benchmark harness dependencies and reliability.
- P8: Execute benchmark matrix on RunPod Gemma endpoint.

## Task Onboarding Action Item (mandatory)

- Before any new task begins, include in the plan:
  - explicit read of `ARCHITECTURE.md`,
  - boundary checks for inbounds/outbounds,
  - forbidden imports list for the task,
  - forbidden coupling removals/preservations,
  - acceptance criteria and regression guard.
- Owner: all agents/task assignees.
- Acceptance:
  - every task plan documents these checks before implementation,
  - blocked or retry tasks that touch boundaries list an explicit verification step for each forbidden import rule.

## Constraint for Dependency Changes

- Do not move runtime behavior in this task; this roadmap expects documentation and interface intent first.
- Preserve `server.py` as composition root and avoid introducing concrete infrastructure dependencies in MCP and domain layers.
