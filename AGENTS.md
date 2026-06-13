You’re continuing work on the BLine GUI timeline redesign. The app now uses a three-region layout: field canvas on the upper left, timeline on the lower left, and the existing property sidebar on the right. The timeline is meant to be the main sequence/timing surface, while the canvas remains the geometric editor and the sidebar remains the only detailed inspector. The user wants this to feel like a simple, intuitive video editing workflow, not a secondary debug panel. The timeline is already in place and mostly functioning as the main temporal UI. It has a pinned left header rail, horizontally scrollable tracks, viewport-centered zoom, fit-to-view behavior, a time-based axis, and stacked bar-style constraint rows. Playback/scrubbing was moved into the timeline so the timeline acts as the transport UI. The existing old canvas play button/transport path is no longer the primary interaction surface.

Notes

- The user is very sensitive to visual correctness and alignment. They specifically care that timeline positions, bars, and playback feel exact and intuitive. Small offsets are likely to be noticed and called out. UI/UX should be the number one priority.
- Carefully read and respect the following docs before beginning development: PYSIDE6_DEVELOPMENT.md, design.md, ui-spec.md, and tasks.md.
- Validate every distinct function or feature with unit tests. Run tests using `uv run python3 -m pytest`
- There is no `python`, there is `python3`
