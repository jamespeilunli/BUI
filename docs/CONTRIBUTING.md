# Contributing

1. **Install tooling**
   ```bash
   uv sync
   uv run pre-commit install # optional but recommended
   ```

2. **Run checks locally**
   ```bash
   uv run ruff format
   uv run ruff check
   uv run mypy
   uv run pytest
   ```

3. **Working on the UI**
   - Launch the GUI with `uv run main.py` (or `./scripts/dev_env.sh`).
   - When adjusting Qt widgets, keep styles in the UI modules and avoid editing `assets_rc.py` directly—regenerate it via `pyside6-rcc` if needed.

4. **Pull requests**
   - Include unit tests for non-GUI changes.
   - Update `CHANGELOG.md` when the behavior or public API changes.
