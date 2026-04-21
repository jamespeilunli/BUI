# Path Editing Redesign Implementation Plan

## Goal

Ship the redesign in the smallest useful slices:

- keep the field canvas as the spatial editor
- keep the right sidebar as the only detailed property editor
- add a bottom timeline for structure, event triggers, and ranged constraints
- avoid building advanced timeline features until the core editing loop is solid

Deferred and optional enhancements live in [nice-to-haves.md](/home/jamesli/git_repos/BLine-GUI/nice-to-haves.md).

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

- default horizontal axis is relative path progress derived from path distance
- event triggers use one shared track group with automatic lane stacking
- all four constraint groups stay visible; non-empty groups start expanded, empty groups start compact
- first release is single-selection only
- first release excludes playback-driven timeline behavior, semantic trigger categories, minimap, and multi-selection

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
- [x] Render four constraint rows from real project data
- [x] Add a ruler, horizontal scrolling, and fit-all zoom
- [x] Show sensible empty states for no path, no triggers, and no constraints

Exit criteria:

- opening a project shows a readable timeline with real data

## Phase 3: Selection Sync

Objective:

- make canvas, timeline, and sidebar behave like one tool

Tasks:

- [ ] Clicking a timeline item selects the matching canvas/sidebar item
- [ ] Canvas selection highlights the matching timeline item
- [ ] Constraint selection highlights the affected field region
- [ ] Clear selection stays stable across all three regions
- [ ] Prevent signal loops and selection churn

Exit criteria:

- single-item selection stays synchronized reliably

## Phase 4: Minimal Event Editing

Objective:

- support the smallest complete trigger workflow in the timeline

Tasks:

- [ ] Create a trigger from a clicked timeline location
- [ ] Drag a trigger horizontally to reposition it
- [ ] Delete a trigger from the timeline
- [ ] Keep exact trigger property editing in the existing sidebar
- [ ] Preserve undo/redo for create, move, and delete

Exit criteria:

- users can place and adjust triggers from the timeline without extra dialogs

## Phase 5: Minimal Constraint Editing

Objective:

- support the smallest complete ranged-constraint workflow in the timeline

Tasks:

- [ ] Render ranged constraints as editable spans
- [ ] Create a span by dragging in empty space
- [ ] Resize span start and end
- [ ] Move a span when valid
- [ ] Delete a span
- [ ] Keep exact value editing in the existing sidebar
- [ ] Preserve undo/redo for create, move, resize, and delete

Notes:

- reuse existing ranged-constraint helpers where practical
- defer split, merge, and duplicate unless they fall out naturally from the implementation

Exit criteria:

- routine constraint editing no longer depends on the popout

## Phase 6: Cleanup and Hardening

Objective:

- remove redundant UI and stabilize the simple workflow

Tasks:

- [ ] Reduce or remove old compact constraint editing once the timeline replacement is stable
- [ ] Keep the sidebar focused on the selected item’s exact properties
- [ ] Add tests for timeline projection, selection sync, trigger edits, constraint edits, and undo/redo
- [ ] Manually verify dense paths, resize behavior, and save/load compatibility
- [ ] Remove dead code only after the replacement path is proven

Exit criteria:

- the timeline is the default workflow for structure inspection, triggers, and ranged constraints

## Cross-Cutting Requirements

- [ ] The app remains runnable after every phase
- [ ] Existing project files remain loadable
- [ ] Undo/redo remains trustworthy
- [ ] Autosave continues to save valid project state
- [ ] Timeline edits refresh the canvas and simulation correctly
- [ ] Selection never desynchronizes across regions

## Definition of Done

- users can understand path structure from the bottom timeline
- users can create and edit event triggers from the timeline
- users can create and edit ranged constraints from the timeline
- the right sidebar remains the sole detailed property editor
- the old popout-driven constraint flow is no longer needed for routine work
