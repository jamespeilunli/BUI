# Design Principles

## Role

This is BUI's stable product and UI/UX contract. Read it before changing the interface.

This document is not a task list. It captures principles that should remain true as features
evolve. If implementation details change, preserve these user-facing behaviors unless the user
explicitly decides otherwise.

## Product Shape

BUI is a timeline-based fork of BLine-GUI for editing BLine autonomous paths.

The app has three persistent work areas:

- Field canvas: the spatial and geometric editor.
- Timeline: the main sequence, timing, playback, event, and ranged-constraint surface.
- Property sidebar: the only detailed inspector and exact-value editor.

The interface should feel like a simple, precise video-editing workflow adapted to robot paths.
Users should be able to see path order, timing, ranges, and cause/effect relationships without
opening secondary management flows.

## Core Experience

- Sequence should be visible by default. Users should not infer order from a hidden list.
- Timing should feel exact. Playback, scrub position, ruler labels, bars, markers, and zoom should
  agree visually and mathematically.
- Geometry and timing should reinforce each other. Selecting or hovering an object in one region
  should clarify the same object or region in the other regions.
- Direct manipulation comes first when it is natural. Timeline-native operations such as moving
  triggers or resizing ranged constraints should happen in the timeline.
- Exact values belong in the sidebar. Do not create a second inspector or duplicate detailed
  property editor elsewhere.
- Dense paths should stay calm and legible. Use hierarchy, grouping, lanes, labels, and restrained
  selection emphasis rather than turning the UI into a table or debug panel.

## Region Responsibilities

### Field Canvas

The canvas is for spatial understanding and geometric edits:

- translation target placement
- waypoint placement
- rotation handle adjustment
- field context
- simulated robot and path overlays
- selected or hovered region context from the timeline

Do not make the canvas the primary timing or sequence editor.

### Timeline

The timeline is the primary temporal UI:

- path structure appears left to right
- playback and scrubbing live here
- zooming, scrolling, and fit-to-view preserve orientation
- event triggers are point-like timeline objects
- ranged constraints are span-like timeline objects
- overlapping ranges stack into lanes instead of becoming ambiguous

The timeline should never feel like a secondary debug panel, spreadsheet, or compact utility strip.
It should be substantial enough to support focused sequence editing.

### Sidebar

The sidebar is the only detailed inspector:

- exact coordinates, rotations, values, keys, and settings live here
- selected timeline and canvas objects edit through the same sidebar
- rough edits can happen directly, precise edits happen here

Do not add another detailed inspector in the timeline, canvas, or a persistent extra panel.

## Selection And State

Selection must feel like one shared object across canvas, timeline, and sidebar.

- Selecting an object on the canvas should reveal and select it in the timeline when applicable.
- Selecting an object on the timeline should select or highlight the matching canvas context.
- Selecting a ranged constraint should show the affected path region.
- Clearing selection should clear all three regions predictably.
- Hover and preview states should help orientation without noisy flashing or layout shifts.

Selection bugs are product bugs. Flicker, scroll jumps, stale highlights, or mismatched selected
objects break the core workflow.

## Undo/Redo And Experimentation

Undo and redo must work for user-visible edits. This is part of the product experience, not just
an engineering convenience.

- Path structure edits should be undoable and redoable.
- Timeline edits to triggers and ranged constraints should be undoable and redoable.
- Sidebar edits to selected item properties and exact values should be undoable and redoable.
- Config or path settings changes that affect project data should preserve undo/redo expectations.
- Undo/redo should restore visual context as predictably as practical.

The app should feel safe for rapid iteration. Broken undo/redo undermines user confidence and
should be treated as a core UX regression.

## Visual Quality Bar

The user is very sensitive to visual correctness. Treat the following as high-priority UI bugs:

- timeline markers or bars offset from their true time/progress position
- playback playhead drift
- zooming that loses the cursor or selected context
- fit-to-view that clips or misframes path start/end
- row/header/body misalignment
- labels that collide, overflow, or obscure controls
- selection states that are too subtle or inconsistent

Favor stable dimensions, clear alignment, and predictable behavior over decorative complexity.

## Feature Design Defaults

When adding a UI feature:

- Put the control where the user naturally looks for that task.
- Keep frequent actions direct and visible.
- Keep rare or exact edits in the sidebar.
- Preserve empty, sparse, and dense states.
- Use shape, placement, label, border, and motion in addition to color.
- Avoid modal or popout workflows for routine timeline tasks.
- Prefer continuity over interruption.

New features should make the path easier to understand at a glance. If a feature adds visible
complexity, it should pay for that complexity with clearer structure, safer editing, or faster
inspection.
