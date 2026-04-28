# Publishing

This project has two publishable artifacts: the Python package and the static
documentation site under `docs/`.

## Release Candidate

Before tagging a release candidate:

```bash
python scripts/release_gate.py
npm run memory:health -- --smoke --json
npm run qwen:sanity -- --run --max-tasks 2
```

Then inspect:

- `docs/release-readiness.md`
- `docs/release-thresholds.md`
- `docs/dogfood-report.md`
- `docs/honest-gwt-report.md`
- `docs/releases/v0.3.0.md`

Do not publish if any of these are true:

- tracked `.env`, `.benchmarks`, benchmark result JSON, `dist/`, supervisor
  folders, or real RunPod URLs appear in git,
- boundary checks fail,
- bus-on accuracy regresses below bus-off for the same slice,
- bus subscriber timeout/error count is nonzero in release evidence.

## GitHub Pages

The Pages workflow builds the Markdown files in `docs/` through Jekyll and
deploys them from GitHub Actions on pushes to `main`. GitHub repository settings
must allow Pages deployment from Actions.

The generated site is documentation-only. It does not host the MCP server, a
database, benchmark artifacts, or secrets.

## Package

The package build gate is:

```bash
python -m build
```

Publishing to PyPI or an internal registry should use a tagged commit that has
passed the release gate and has matching release notes under `docs/releases/`.

