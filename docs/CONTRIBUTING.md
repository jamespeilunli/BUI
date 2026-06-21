# Contributing

1. **Install tooling**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install pre-commit # optional but recommended
   ```

2. **Run checks locally**
   ```bash
   make fmt
   make lint
   make test
   ```

3. **Working on the UI**
   - Launch the GUI with `make run` (or `./scripts/dev_env.sh`).
   - When adjusting Qt widgets, keep styles in the UI modules and avoid editing `assets_rc.py` directly—regenerate it via `pyside6-rcc` if needed.

4. **Pull requests**
   - Include unit tests for non-GUI changes.
   - Update `CHANGELOG.md` when the behavior or public API changes.

