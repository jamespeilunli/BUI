# Path Editing Redesign Implementation Plan

## Goal

Ship the redesign in the smallest useful slices:

- keep the field canvas as the spatial editor
- keep the right sidebar as the only detailed property editor
- add a bottom timeline for structure, event triggers, and ranged constraints
- avoid building advanced timeline features until the core editing loop is solid

Deferred and optional enhancements live in [nice-to-haves.md](nice-to-haves.md).

## Simplicity Rules

- Reuse the existing path model, undo/redo flow, autosave flow, and canvas/sidebar wiring where possible.
- Prefer one simple timeline implementation over a deep hierarchy of timeline abstractions.
- Start read-only, then add the minimum direct-editing behaviors needed for real use.
- Keep old flows alive until the replacement works, then remove them.
- Defer features that add complexity without unlocking the core workflow.

## Phase 0: Decision Lock

Status:

- [x] Done

Locked decisions:

- default horizontal axis is estimated time derived from simulation/projection data
- event triggers use one shared track group with automatic lane stacking
- all ranged constraint types share one combined constraints row with automatic lane stacking
- first release is single-selection only
- first release excludes semantic trigger categories, minimap, and multi-selection

## Phase 1: Layout Shell

Objective:

- add the new three-region layout without changing editing behavior yet

Tasks:

- [x] Refactor the main window so the left side is a vertical split: field on top, timeline on bottom
- [x] Keep the current right sidebar in place
- [x] Add user-resizable splitters for field/timeline and left/sidebar
- [x] Add a simple timeline placeholder widget so the app opens in the new shape
- [ ] Verify project load, menus, autosave, canvas, and sidebar still work

Exit criteria:

- the app opens with the new layout and no editing regressions

## Phase 2: Read-Only Timeline

Objective:

- make the timeline useful for inspection before adding direct manipulation

Tasks:

- [x] Render a simple structure row for path items
- [x] Render one trigger group from real project data
- [x] Render one combined constraints row from real project data
- [x] Add a ruler, horizontal scrolling, and fit-all zoom
- [x] Show sensible empty states for no path, no triggers, and no constraints

Exit criteria:

- opening a project shows a readable timeline with real data

## Phase 3: Selection Sync

Objective:

- make canvas, timeline, and sidebar behave like one tool

Tasks:

- [x] Clicking a timeline item selects the matching canvas item
- [x] Canvas selection highlights the matching timeline item
- [x] Constraint selection highlights the affected field region
- [x] Clear selection stays stable across all three regions
- [x] Prevent signal loops and selection churn

Exit criteria:

- single-item selection stays synchronized reliably

## Phase 4: Minimal Event Editing

Objective:

- support the smallest complete trigger workflow in the timeline

Tasks:

- [x] Create a trigger from a clicked timeline location
- [x] Drag a trigger horizontally to reposition it
- [x] Delete a trigger from the timeline
- [x] Keep exact trigger property editing in the existing sidebar
- [x] Preserve undo/redo for create, move, and delete

Exit criteria:

- users can place and adjust triggers from the timeline without extra dialogs

## Phase 5: Minimal Constraint Editing

Objective:

- support the smallest complete ranged-constraint workflow in the timeline

Tasks:

- [x] Render ranged constraints as editable spans
- [x] Create a span by dragging in empty space
- [x] Resize span start and end
- [x] Move a span when valid
- [x] Delete a span
- [x] Keep exact value editing in the existing sidebar
- [x] Preserve undo/redo for create, move, resize, and delete

Notes:

- reuse existing ranged-constraint helpers where practical
- split, merge, and duplicate are explicitly out of scope for the current rewrite wave

Exit criteria:

- routine constraint editing no longer depends on the popout

## Phase 6: Restore Path Structure Authoring

Objective:

- restore first-class creation workflows for path structure items without bringing back the old sidebar list as the main navigator

Tasks:

- [x] Provide a clear way to add Translation, Waypoint, Rotation, and Event Trigger items from the redesigned timeline/canvas workflow
- [x] Ensure new Translation and Waypoint items appear immediately in the structure track and on the field
- [x] Ensure new Rotation and Event Trigger items are inserted between valid neighboring anchors and cannot be placed at invalid path ends
- [x] Preserve the existing behavior where new items use sensible default positions and project/config defaults
- [x] Select the newly created item across timeline, canvas, and sidebar
- [x] Preserve undo/redo and autosave for each add operation

Exit criteria:

- users can build a path from the redesigned UI without relying on the removed Path Elements sidebar list

## Phase 7: Restore Per-Path Constraint Settings

Objective:

- restore editing for path-level constraints through a dedicated per-path settings surface
- keep non-timeline constraints out of the timeline so ranged spans remain visually distinct

Tasks:

- [ ] Add a `Settings` item under the `Path` dropdown
- [ ] Open a per-path settings dialog or compact settings surface from `Path > Settings`
- [ ] Support add, edit, and remove for per-path max velocity (`max_velocity_meters_per_sec`)
- [ ] Support add, edit, and remove for per-path max acceleration (`max_acceleration_meters_per_sec2`)
- [ ] Support add, edit, and remove for per-path max rotation velocity (`max_velocity_deg_per_sec`)
- [ ] Support add, edit, and remove for per-path max rotation acceleration (`max_acceleration_deg_per_sec2`)
- [ ] Support add, edit, and remove for end translation tolerance (`end_translation_tolerance_meters`)
- [ ] Support add, edit, and remove for end rotation tolerance (`end_rotation_tolerance_deg`)
- [ ] Make it visually clear that flat constraints affect the whole path or terminal condition, not a timeline span
- [ ] Preserve undo/redo, autosave, and save/load compatibility

Exit criteria:

- users can inspect and edit every persisted per-path constraint supported by the original codebase from `Path > Settings`

## Phase 8: Timeline Delete Parity

Objective:

- make timeline deletion behavior match user expectations for selected path items

Tasks:

- [x] Delete selected Event Trigger items from the timeline
- [x] Delete selected Rotation items from the timeline when valid
- [x] Delete selected Translation and Waypoint items from the timeline with the same safeguards used elsewhere in the app
- [x] Remap ranged constraints after deleting structure items
- [x] Clear or restore selection predictably after deletion
- [x] Preserve undo/redo and autosave for timeline deletion

Exit criteria:

- pressing Delete/Backspace on a selected timeline item performs the same safe deletion users expect from the rest of the editor

## Phase 9: Final Cleanup and Hardening

Objective:

- remove redundant UI/code and stabilize the complete parity-restored workflow

Tasks:

- [ ] Remove or hide old compact ranged-constraint browsing once the timeline replacement is stable
- [ ] Keep the sidebar focused on the selected item’s exact properties
- [ ] Add tests for timeline projection, selection sync, trigger edits, constraint edits, path structure authoring, flat constraints, delete parity, and undo/redo
- [ ] Manually verify dense paths, resize behavior, save/load compatibility, autosave, and undo/redo
- [ ] Remove dead code only after Phases 6 through 8 are complete and manually verified

Exit criteria:

- the timeline is the default workflow for structure inspection, path authoring, triggers, and ranged constraints
- every known parity gap from the timeline rewrite has either been closed or explicitly deferred

## Current Wontfix For This Rewrite Wave

- split ranged-constraint spans
- merge adjacent compatible ranged-constraint spans
- duplicate ranged-constraint spans
- duplicate event triggers
- manual path structure reordering

These remain possible later enhancements, but they should not block parity work in Phases 6 through 8.

## Cross-Cutting Requirements

- [ ] The app remains runnable after every phase
- [ ] Existing project files remain loadable
- [ ] Undo/redo remains trustworthy
- [ ] Autosave continues to save valid project state
- [ ] Timeline edits refresh the canvas and simulation correctly
- [ ] Selection never desynchronizes across regions

## Definition of Done

- users can understand path structure from the bottom timeline
- users can create path structure from the redesigned UI
- users can create and edit event triggers from the timeline
- users can create and edit ranged constraints from the timeline
- users can edit flat path constraints that are not timeline spans
- the right sidebar remains the sole detailed property editor
- the old popout-driven constraint flow is no longer needed for routine work
