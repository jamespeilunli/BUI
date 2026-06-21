You’re continuing work on BUI, a fork of BLine-GUI that redesigns the UI to be based on a timeline. The app now uses a three-region layout: field canvas on the upper left, property sidebar on the upper right, and the timeline on the bottom. The timeline is meant to be the main sequence/timing surface, while the canvas remains the geometric editor and the sidebar remains the only detailed inspector. The user wants this to feel like a simple, intuitive video editing workflow. The timeline is already in place and mostly functioning as the main temporal UI. It has a pinned left header rail, horizontally scrollable tracks, viewport-centered zoom, fit-to-view behavior, a time-based axis, and stacked bar-style constraint rows. Playback/scrubbing was moved into the timeline so the timeline acts as the transport UI.

During development, you must maintain 100% compatibility with BLine-Lib, the backend library that follows the paths that this program edits. This means the schema of the path and config files cannot change.

Notes

- The user is very sensitive to visual correctness and alignment. They specifically care that positions, bars, playback, and navigation feel exact and intuitive. Small offsets and rough behavior are likely to be noticed and called out. UI/UX should be the number one priority.
- Carefully read and respect the following docs before beginning development: docs/PYSIDE6_DEVELOPMENT.md, docs/design.md, docs/ui-spec.md, and docs/tasks.md.
- Validate every distinct function or feature with unit tests. Run tests using `uv run pytest`
- There is no `python`, there is `python3`
- For original BLine-GUI upstream sync context, read and update `docs/UPSTREAM_SYNC.md` every time upstream changes are reviewed or ported.
