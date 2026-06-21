BUI is a timeline-based fork of BLine-GUI.

Before development, read and follow:

- `docs/DESIGN.md`
- `docs/DEVELOPMENT.md`

Maintain 100% compatibility with BLine-Lib path and config files. Do not change persisted schema without explicit user approval.

Use `uv run pytest` for tests. There is no `python`; use `python3` where a Python executable is needed. Do not run `uv run main.py`, the user will run it themselves.

For original BLine-GUI upstream sync context, read and update `docs/UPSTREAM_SYNC.md` every time upstream changes are reviewed, ported, or skipped.
