# Path Editing Redesign

## Purpose

This document defines the desired user experience for a redesigned path editing interface in BLine. The redesign should make path construction feel closer to a modern video editing workflow while preserving the strengths of the current canvas-based field editor.

This document intentionally focuses on what the user should be able to do and how the interface should feel. It does not describe implementation, class structure, widget choices, or technical migration steps.

## Product Goal

Users should be able to build, inspect, and refine robot paths with the same confidence and speed that video editors use to shape a timeline. The redesigned interface should make sequence, timing, ranges, and cause-and-effect relationships obvious at a glance.

The result should feel:

- visual rather than form-heavy
- structured without being rigid
- friendly to first-time users
- efficient for expert users doing rapid iteration
- safe for experimentation, with low fear of making mistakes

## Primary UX Shift

The field canvas remains the main spatial editor.

The right sidebar remains the only property editing surface.

The bottom of the window becomes a dedicated, zoomable timeline workspace where users can understand and manipulate the order, span, and overlap of:

- path elements
- rotation targets
- waypoints
- event triggers
- ranged constraints

The timeline should become the main temporal and sequence-editing surface, while the canvas remains the main geometric editing surface.

## Core User Outcomes

Users should be able to:

- understand the full path structure without opening multiple dialogs
- see where each element occurs in the path sequence
- see which constraints apply over which sections of the path
- stack multiple constraints without visual confusion
- place and move event triggers in a precise, timeline-like way
- select anything from the canvas or timeline and edit it from the same sidebar
- zoom out for overall structure and zoom in for fine control
- make edits without losing context of the full path
- compare path geometry on the field with sequencing and timing at the same time

## Design Principles

### 1. One object, one source of truth

Every editable item should have a clear identity in the UI. If a user selects an item on the field, the same item should become obvious on the timeline and in the sidebar. If a user selects an item on the timeline, the same item should become obvious on the field and in the sidebar.

### 2. Sequence should be visible by default

The user should not need to infer order from a list or remember how constraints map onto path elements. The interface should make ordering and ranges obvious without extra clicks.

### 3. Dense information, low cognitive load

The redesign should show more information than the current sidebar-driven editing flow, but it should still feel calm and legible. Visual hierarchy, grouping, and progressive disclosure should keep the interface understandable.

### 4. Direct manipulation first

The user should be able to move, resize, reorder, split, and inspect timeline items directly from the timeline whenever that is the natural interaction. The sidebar should refine a selection, not replace direct editing.

### 5. Fast to learn, faster to master

Basic operations should be obvious to a first-time user. Advanced control should emerge naturally through zooming, keyboard shortcuts, precision handles, snapping, and multi-selection.

### 6. Geometry and timing should cooperate

The field canvas and the timeline should feel like two views of the same path, not two separate tools. Users should be able to understand both where something happens and when or over what span it happens.

## Target Users

### New users

New users need a UI that explains path structure visually. They should be able to create a basic path, inspect constraints, and place triggers without first learning internal data model concepts.

### Experienced path authors

Experienced users need speed, precision, and fewer modal steps. They should be able to adjust structure, constraints, and triggers quickly while continuously watching the field and simulation context.

### Reviewers and collaborators

Users reviewing an existing path should be able to open a project and immediately understand the path’s major beats, special regions, and trigger points from the timeline alone.

## High-Level Layout

The redesigned editor should have three persistent work areas:

### 1. Main field canvas

The canvas remains the dominant spatial workspace for:

- placing and moving translation targets
- shaping path geometry
- adjusting headings and waypoint positions
- viewing simulation overlays and robot motion context

### 2. Bottom timeline workspace

The bottom workspace becomes a full timeline editor for path structure. It should feel substantial, not like a thin accessory strip. It should be large enough to support focused editing sessions on its own.

### 3. Right property sidebar

The sidebar remains the single place for detailed property editing, numeric entry, naming, configuration, and advanced per-item controls.

No second inspector should appear elsewhere.

## Timeline Mental Model

The timeline should represent path progress in a left-to-right sequence. Users should feel that moving right means moving later through the path.

The timeline does not need to imply literal clock time unless the app has enough information to show it meaningfully. It should, at minimum, communicate sequence and span clearly. If timing is shown, it should help the user without making the timeline dependent on perfect simulation data.

The timeline should support multiple useful readings of the same path:

- structural order
- relative position along the path
- active ranges for constraints
- discrete trigger points
- selected context around the current edit

## Timeline Content Model

The timeline should present information in layered tracks similar to editing software.

### Path structure track

Users should be able to see the ordered path backbone in a compact, readable way. This track should communicate:

- start and end
- translation anchors
- waypoints
- rotation targets
- gaps or transitions between major path elements

This track should make the skeleton of the path understandable even before users inspect the canvas.

### Event trigger tracks

Event triggers should appear as discrete, movable timeline items. Users should be able to:

- see all triggers at once
- stack triggers if multiple happen near the same location
- distinguish triggers clearly from constraints
- select a trigger from the timeline without hunting on the canvas
- understand which segment or path region a trigger belongs to

### Constraint tracks

Ranged constraints should appear as span-based clips or bars on stackable tracks. Users should be able to:

- see where a constraint begins and ends
- understand overlapping constraints without ambiguity
- compare multiple constraint types in the same region
- visually identify the currently active constraint for a selected part of the path
- add, extend, shorten, split, and remove ranges directly from the timeline

Constraint tracks should feel organized and intentional, not like a compressed data grid.

### Optional grouping behavior

Constraint tracks should be visually grouped by type so users can scan them quickly. Event trigger tracks should remain visually distinct from constraint tracks.

Users should be able to collapse groups when they want a simpler overview and expand them when they need precision.

## Zoom and Navigation

The timeline should be zoomable and scrollable in a way that feels natural to anyone familiar with editing software.

Users should be able to:

- zoom out to see the whole path structure
- zoom in for fine placement and range editing
- pan horizontally without losing their place
- keep selection visible while zooming
- quickly return to a “fit all” view
- focus on a selected region or selected item

Zoom should increase editing confidence, not just magnify the same clutter.

## Selection and Focus

Selection behavior should be consistent across canvas, timeline, and sidebar.

Users should be able to:

- click an item on the field and see it highlighted on the timeline
- click an item on the timeline and see it highlighted on the field
- use the sidebar to edit whichever item is currently selected
- move between nearby items without losing track of what is active
- tell the difference between hovered, selected, and indirectly related items

Related items should be visually linked when helpful. For example, selecting a constraint range should clearly show the affected path region; selecting a trigger should clarify where it occurs on the path.

## Editing Behavior

The redesign should support direct manipulation of timeline items.

Users should be able to:

- drag items left or right to reposition them in sequence
- drag range edges to adjust where a constraint starts and ends
- create new constraints by dragging across a region
- duplicate or repeat applicable items quickly
- split a range into smaller ranges
- merge adjacent ranges when appropriate
- snap edits to meaningful boundaries when precision is needed
- make fine adjustments without fighting the interface

Edits should feel forgiving. The UI should reduce accidental changes and make recovery obvious.

## Relationship Between Canvas and Timeline

The canvas and timeline should reinforce each other continuously.

Users should be able to:

- see where a timeline selection lives on the field
- see which timeline region corresponds to a selected path segment on the field
- preview affected path areas when hovering a timeline item
- scrub attention through the path and understand both shape and sequencing

The user should never have to mentally translate between three disconnected representations.

## Sidebar Responsibilities

The sidebar remains the only detailed editor. It should adapt to the current selection and present the right controls without forcing the user into a separate mode.

Users should be able to use the sidebar to:

- view and edit the selected item’s properties
- rename or label items where applicable
- inspect exact values after rough timeline manipulation
- make precise numeric edits
- understand the role of the selected item in the path

The sidebar should not need to carry the burden of showing full path structure. The timeline should do that.

## Workflow Goals

### Creating a new path

Users should be able to:

- place the first path elements on the field
- immediately see them appear in the timeline in the correct order
- add headings, waypoints, triggers, and constraints without switching to separate management dialogs
- understand the path structure as it grows

### Editing an existing path

Users should be able to:

- open a project and understand its shape quickly
- identify dense or problematic regions from the timeline
- isolate a region, zoom in, and refine it
- inspect and update constraints and triggers in context

### Tuning motion behavior

Users should be able to:

- see where movement limits change
- understand overlaps and transitions between constraint ranges
- focus on a problematic segment and refine only that region
- compare multiple active motion-related constraints in one timeline view

### Trigger authoring

Users should be able to:

- place event triggers at meaningful positions along the path
- move them precisely
- stack them if several occur in the same region
- inspect trigger order when triggers are close together

### Review and debugging

Users should be able to:

- scan the path timeline to identify unusual structure
- detect missing constraints or suspicious trigger placement
- understand why a section behaves differently from its neighbors
- communicate about a region of the path using visible landmarks in the UI

## Visual Hierarchy Expectations

The interface should have a clear visual reading order:

1. field geometry
2. path sequence timeline
3. selected item details

Within the timeline, hierarchy should be obvious:

- the main path structure should be easy to locate
- constraints should read as spans
- triggers should read as points or short blocks
- active selection should dominate related context
- less important reference information should stay quiet

The redesign should avoid making the bottom workspace look like a spreadsheet, a property table, or a generic list view.

## Discoverability

The UI should teach itself through layout and interaction cues.

Users should be able to discover:

- that the timeline is zoomable
- that ranges can be dragged and resized
- that triggers can be moved directly
- that collapsed track groups can be expanded
- that the sidebar edits the current selection

Common actions should be visible enough to find without reading documentation, while advanced actions can rely on tooltips, context menus, or shortcut hints.

## Friendly Interaction Requirements

The redesign should feel smooth and non-threatening.

That means users should:

- receive immediate visual confirmation after actions
- understand what changed and why
- be protected from accidental destructive edits
- have obvious undo/redo confidence
- avoid situations where the UI feels stuck, over-modal, or fragile

The interface should prefer continuity over interruption. Most editing should happen inline without opening separate popouts for routine work.

## Precision Requirements

The interface should support both rough sketching and exact editing.

Users should be able to:

- make broad edits quickly while zoomed out
- switch to precise control while zoomed in
- use snapping when it helps and avoid it when it gets in the way
- rely on the sidebar for exact values after direct manipulation

## Density and Scalability

The redesign should stay usable for:

- very small paths
- medium paths with several triggers and constraints
- dense competition paths with many layered edits

As projects become more complex, users should still be able to:

- find the active item quickly
- collapse less relevant detail
- zoom to the region that matters
- understand overlap without visual breakdown

## Empty, Sparse, and Dense States

The bottom workspace should remain helpful in all project states.

### Empty state

When no path exists, the timeline area should explain what kinds of items will appear there and how the user can begin.

### Early path state

When only a few path elements exist, the timeline should still feel purposeful rather than oversized or empty.

### Dense state

When many constraints and triggers exist, the timeline should preserve readability through grouping, spacing, stacking, and clear selection focus.

## Terminology Expectations

The UI should use consistent, user-facing language. Terms should be intuitive and avoid exposing internal structure unless that structure is genuinely useful to users.

If the interface uses terms like track, clip, marker, range, span, or lane, those terms should stay consistent across tooltips, menus, and sidebar labels.

## Error Prevention

The redesign should reduce mistakes by making relationships visible before users commit changes.

Users should be protected from:

- unintentionally editing the wrong item
- losing track of overlapping ranges
- confusing discrete triggers with continuous constraints
- creating visually ambiguous placements
- making precise edits while zoomed too far out without clear feedback

## Accessibility and Comfort

The redesign should remain readable and comfortable over long editing sessions.

Users should be able to:

- distinguish tracks, ranges, and selections without relying on color alone
- read labels at practical zoom levels
- operate key timeline actions with keyboard support
- maintain orientation during zooming and panning

## Success Criteria

The redesign is successful if users can do the following with less friction than the current interface:

- understand the structure of a path at a glance
- edit constraints without opening separate management flows
- place and tune event triggers in context
- move between field editing and sequence editing naturally
- use the sidebar as a precise inspector rather than as the main structural navigator

## Non-Goals for This Phase

This document does not yet define:

- implementation architecture
- specific widget or component choices
- data model changes
- rendering strategy
- migration sequencing
- performance tactics
- exact visual styling tokens

Those belong in later planning once the product behavior and interaction model are agreed upon.
