# Path Editing UI Spec

## Scope

This document turns the redesign goals in [design.md](design.md) into a concrete product spec for the new path editing interface.

This is still a UX specification, not an implementation plan. It defines screen regions, behaviors, states, and interaction expectations so the redesign can be built coherently.

## Product Summary

The path editor should feel like a hybrid of:

- a field-based spatial editor
- a non-linear video editing timeline
- a single-inspector authoring tool

The user edits geometry on the field, edits sequence and ranges on the timeline, and edits exact properties in the right sidebar.

## Primary Layout

The main window should be organized into three persistent regions:

### 1. Field Stage

Location:

- upper-left primary workspace

Purpose:

- spatial editing
- path shape review
- simulation review
- direct manipulation of translation and rotation geometry

Content:

- field image/background
- path lines and direction indicators
- translation targets
- waypoints
- rotation handles
- simulation trail and robot preview
- selection overlays
- hover previews linked from the timeline

### 2. Timeline Dock

Location:

- full-width bottom dock under the field stage and extending beneath the sidebar edge only if visually useful

Purpose:

- sequence editing
- event and constraint authoring
- path structure overview
- zoomed region inspection

Content:

- timeline toolbar
- left track header rail
- main scrollable timeline body
- top ruler
- playhead/scrubber
- path structure track
- event trigger tracks
- one combined constraints row
- overview/minimap strip if needed

### 3. Property Sidebar

Location:

- right side, vertically full height

Purpose:

- detailed property editing for the current selection
- exact numeric edits
- contextual help for the selected item

Content:

- selection header
- editable fields for the selected object
- grouped controls relevant to that object type
- inline explanations where needed

No additional inspector panel should appear elsewhere.

## Layout Proportions

Default proportions should support real work without immediate resizing.

Expected behavior:

- the field stage should remain visually dominant
- the timeline dock should be large enough to edit comfortably without feeling cramped
- the sidebar should be wide enough for readable forms but narrower than the field stage

Default visual balance:

- field stage: approximately 55 to 65 percent of available width
- sidebar: approximately 20 to 28 percent of available width
- timeline dock: approximately 28 to 38 percent of available window height

Resizable dividers should let users:

- grow the timeline for detailed sequence work
- shrink the timeline for field-focused work
- slightly widen the sidebar for dense property editing

## Overall Interaction Model

The editor should support three modes of attention without explicit mode switches:

- spatial attention on the field
- sequence attention in the timeline
- precision attention in the sidebar

Users should be able to move fluidly between them. Selection should persist across regions and should never feel like changing tools.

## Object Types in the New UI

The following user-facing items should be first-class citizens in the interface:

- translation target
- waypoint
- rotation target
- event trigger
- ranged constraint
- path segment
- path start
- path end

Each should have:

- a visible representation in at least one major region
- a clear selection state
- a predictable sidebar detail view

## Timeline Model

## Horizontal Axis

The timeline’s horizontal axis should represent estimated elapsed time through the path from start to finish.

At minimum the axis must support:

- sequence order
- estimated time
- relative position along the path as supporting context

Optionally the axis may also expose:

- distance along path
- relative progress

If multiple interpretations are available, the default should remain estimated time because it matches playback, scrubbing, and a video-editor mental model.

For the first release, the default horizontal scale is estimated time derived from the current simulation/projection data.

This choice should drive item placement, ruler math, snapping, zoom, playback, scrubbing, and fit-to-view behavior. When simulation output is unavailable or incomplete, fallback timing may be derived from path distance and configured/default velocity, but the displayed axis should still read as time.

Distance or relative-progress views are alternate/future modes, not the default first-release timeline.

## Vertical Axis

The vertical axis should organize information by track and track group.

Track order should be stable so users build muscle memory.

Recommended top-to-bottom order:

1. ruler and playhead zone
2. path structure track
3. event trigger group
4. combined constraints row

Within each group, visible stacking should prevent overlaps from becoming unreadable.

## Timeline Regions

### Track Header Rail

The left side of the timeline should contain a fixed header rail.

Users should be able to see:

- track names
- track group labels
- expand/collapse affordances
- add buttons where appropriate
- visibility and mute-style toggles if those concepts are introduced

The header rail should stay visible while horizontal scrolling happens.

### Ruler

The top ruler should provide orientation and precision.

Users should be able to:

- understand where they are in the path
- judge relative spacing between items
- place and move items more precisely when zoomed in

The ruler should adapt label density to zoom level.

### Playhead / Scrubber

The timeline should include a single clear playhead.

Users should be able to:

- scrub across the path
- see corresponding context on the field
- use the playhead as a temporary focus tool during inspection

The playhead is not required to drive full playback behavior in this phase, but it should provide a strong sense of “current location.”

### Main Scroll Body

This is the main interaction zone for editing tracks.

Users should be able to:

- select items
- drag items
- resize ranges
- marquee a region when appropriate
- right-click for contextual actions
- hover for previews and details

## Path Structure Track

The path structure track is the backbone track and should always be visible.

Purpose:

- show the ordered path skeleton
- provide a quick mental model of the path
- anchor all other track content

Users should be able to see:

- start marker
- end marker
- anchor positions
- waypoint positions
- rotation target positions
- path segmentation cues

The path structure track should read as the main editorial sequence line.

### Structure Track Item Rules

Translation targets:

- should appear as major anchor items
- should feel foundational and easy to distinguish

Waypoints:

- should appear as anchor-like items but visually secondary to primary translations

Rotation targets:

- should appear as directional or orientation-focused markers
- should be distinct from event triggers

Event triggers:

- should not be embedded into the structure track by default
- should remain in their own dedicated tracks for clarity

### Structure Track Interactions

Users should be able to:

- click an item to select it
- hover an item to highlight it on the field
- drag supported items horizontally when reordering or repositioning is valid
- jump the viewport to the selected item

The structure track should support reading and selection even when the user is zoomed far out.

## Event Trigger Group

The event trigger area should resemble marker lanes in an editing tool.

Purpose:

- show all triggers without clutter
- make trigger placement feel precise and editable
- allow dense paths to remain understandable

### Event Trigger Representation

Triggers should appear as compact blocks or markers with:

- a short visible label
- a distinct visual identity from constraints
- a precise anchor point on the timeline

When triggers are close or overlapping:

- they should stack into multiple lanes
- ordering should remain legible
- labels should degrade gracefully instead of becoming noise

### Event Trigger Interactions

Users should be able to:

- create a trigger at the current playhead or clicked location
- drag a trigger left or right
- select one of many nearby triggers reliably
- delete a trigger without affecting adjacent items
- inspect trigger details in the sidebar

### Event Trigger Grouping

For the first release, all event triggers should live in one shared trigger group with automatic lane stacking.

The UI should not imply semantic trigger categories or separate trigger families yet because the current model does not provide a stable category system beyond each trigger's configured key.

If the project contains many triggers, users should be able to:

- collapse the trigger group to a single compact summary row
- expand it back into lanes for precise editing

Collapsed state should still show:

- trigger density
- selected trigger context
- approximate trigger positions

## Combined Constraints Row

Constraints should be organized as stacked clip-style spans in one combined constraints row.

The combined row includes these ranged constraint types:

- translation speed
- translation acceleration
- rotation speed
- rotation acceleration

Users should be able to compare different constraint types in one place without scanning multiple separated groups.

For the first release, the header rail should show a single constraints row with one add-range affordance. The active add type may be selected from the sidebar inspector or another compact control, but the timeline should not show four separate constraint groups.

This keeps the timeline visually simple and avoids turning the bottom workspace into a stacked settings panel.

## Constraint Track Structure

The combined constraints row should have:

- a single row header
- one or more automatic lanes
- an add-range affordance

Each lane should support multiple non-overlapping spans when needed.

If spans overlap visually, the UI must place them on separate lanes automatically to avoid ambiguity. Different constraint types may overlap in time and should still be visually distinguishable.

## Constraint Span Representation

A ranged constraint should appear as a timeline clip or bar with:

- clear left and right boundaries
- a readable label
- a visible selected state
- resize handles or obvious edge affordances when selected or hovered

The user should be able to distinguish:

- constraint type
- span extent
- active selection
- overlaps
- disabled or indirect context if such states exist

## Constraint Group Interactions

Users should be able to:

- create a new constraint by dragging across empty space in the combined constraints row
- select an existing span
- drag a span left or right when valid
- resize the start edge
- resize the end edge
- delete a span
- edit exact values in the sidebar

### Constraint Lane Rules

Users should not have to manually manage lanes in routine cases.

The interface should:

- automatically stack spans to avoid collisions
- preserve a stable layout so tracks do not jump unnecessarily
- keep the selected span visible and prominent

## Selection Rules

The entire UI should use a shared selection model.

Single selection should be the default behavior.

The first release should implement single selection only across canvas, timeline, and sidebar.

The UI should not show marquee selection, additive selection affordances, or batch edit controls until multi-selection is intentionally designed and shipped.

Selection actions:

- clicking a field item selects the corresponding timeline item if one exists
- clicking a timeline item selects the corresponding field item if one exists
- selecting a range on the timeline also highlights its affected field region
- selecting a trigger highlights its path location and linked segment context

Selection states should include:

- idle
- hover
- selected
- selected plus related context
- temporarily previewed

These states should be visually distinct.

## Hover and Preview Behavior

Hover should be useful but lightweight.

Hovering a timeline item should:

- highlight the corresponding object on the field
- softly reveal related regions or path segments
- show a compact tooltip or detail hint if helpful

Hovering should not create noisy flashing or large layout shifts.

## Sidebar Detail States

The sidebar content should depend entirely on current selection.

### No selection

The sidebar should show:

- a quiet overview or helper panel
- brief guidance for common actions
- context-aware empty messaging

### Translation target selected

The sidebar should show:

- position and identity fields
- any anchor-specific controls
- any relevant path context

### Waypoint selected

The sidebar should show:

- translation-related fields
- rotation-related fields
- waypoint-specific context

### Rotation target selected

The sidebar should show:

- orientation controls
- placement context along the path
- any special rotation behavior settings

### Event trigger selected

The sidebar should show:

- trigger name or label
- trigger key or configured action
- exact placement information
- any trigger-specific metadata

### Constraint selected

The sidebar should show:

- constraint type
- exact value
- exact start and end extent
- context about the affected region

The sidebar should not be responsible for browsing among all constraints. That is the timeline’s job.

## Navigation and Zoom Spec

### Timeline Zoom

Users should be able to zoom the timeline with standard editing-software expectations.

Supported user goals:

- inspect the whole path at once
- zoom toward the cursor or selection
- make precise local edits
- return to fit-all quickly

Zoomed-out state should prioritize structure.

Zoomed-in state should prioritize editability and labels.

### Timeline Scrolling

Users should be able to:

- scroll horizontally through long paths
- scroll vertically through expanded track groups when needed
- keep track headers pinned
- keep the ruler pinned

### Focus Commands

The interface should expose easy ways to:

- fit the full timeline
- center on selection
- frame the active region
- jump to start
- jump to end

## Editing Flows

## Flow 1: Add a New Constraint

The user should be able to:

1. find the combined constraints row
2. choose the constraint type to add
3. click or drag in empty space in the combined constraints row to create a new span
4. see the new span appear immediately
5. have the new span selected automatically
6. refine the exact value in the sidebar

The flow should avoid popout dialogs.

## Flow 2: Adjust an Existing Constraint Range

The user should be able to:

1. click the span
2. see its affected region on the field
3. drag the left or right edge
4. see immediate visual feedback during adjustment
5. release and keep the span selected for exact sidebar edits if needed

## Flow 3: Add or Move an Event Trigger

The user should be able to:

1. create the trigger from the event group or current context
2. drag it to the desired location
3. see where it belongs on the field
4. edit its precise settings in the sidebar

## Flow 4: Inspect a Dense Region

The user should be able to:

1. zoom into a busy section of the timeline
2. expand the relevant groups
3. scrub or hover through nearby items
4. isolate the specific trigger or range they want
5. edit without opening secondary windows

## Flow 5: Edit from the Field First

The user should be able to:

1. select a path element on the field
2. immediately see the corresponding timeline location
3. use the timeline to understand nearby triggers and constraints
4. use the sidebar for exact property edits

## Drag and Drop Behavior

Drag behavior should feel stable and forgiving.

While dragging timeline items, users should receive:

- continuous highlight of the edited item
- clear indication of valid placement
- subtle snap feedback where applicable
- a readable preview of the resulting position or extent

Drag interactions should avoid:

- accidental track switching
- ambiguous drop targets
- excessive jitter
- hidden side effects

## Snapping Rules

The UI should support snapping where it genuinely improves confidence.

Useful snap targets may include:

- nearby anchors
- segment boundaries
- item edges
- the playhead
- relevant ordinal positions

Snapping should be:

- visible when it occurs
- easy to override for fine control if needed
- stronger when zoomed in and weaker when zoomed out if that improves usability

## Context Menus

Timeline items should offer concise, predictable context actions.

Examples:

- rename
- delete
- zoom to item
- reveal on field

Context menus should reinforce discoverability for advanced actions.

## Multi-Selection

Multi-selection is deferred out of the first implementation wave.

Later support may allow users to:

- select multiple compatible timeline items
- move them together when valid
- delete them together

Until then, the UI should not visually imply that it exists.

## Visual Language

The redesigned editor should feel more like a creative tool than a settings panel.

The visual system should communicate:

- tracks as purposeful editorial lanes
- spans as editable clips
- markers as precise events
- selection as confident and unmistakable

The bottom timeline should not look like a table, form, or debug panel.

## Motion and Feedback

UI motion should be used sparingly but intentionally.

Helpful motion examples:

- smooth scroll and zoom anchoring
- subtle selection transitions
- clean lane expansion and collapse
- restrained hover emphasis

Motion should help orientation, not decorate the interface.

## Empty States

### Empty Project

The timeline should explain:

- that path structure will appear here
- that triggers and constraints will stack below
- the first meaningful action to get started

### No Constraints Yet

The combined constraints row should make it obvious that:

- no ranges exist yet
- the user can create one directly in the lane

### No Triggers Yet

The event section should make it obvious that:

- triggers can be added here
- they will align to path progress

## Responsive Behavior

The layout should remain usable at smaller desktop window sizes.

When space is constrained:

- the timeline may show fewer lanes before vertical scrolling
- labels may simplify
- the sidebar may prioritize the most important controls first

The redesign should still assume desktop-class use, not phone-scale adaptation.

## Accessibility Requirements

Users should be able to understand track content without relying only on color.

Required cues include combinations of:

- color
- shape
- iconography
- border treatment
- label text

Keyboard expectations:

- tabbing into timeline controls should be possible
- selected items should have clear focus indication
- key actions like delete and zoom-to-selection should have keyboard equivalents

## Acceptance Criteria

The UI spec is satisfied when the redesign supports the following behaviors clearly and directly:

- users can understand path order from the timeline without opening dialogs
- users can add and edit ranged constraints from the timeline itself
- users can place and move event triggers from the timeline itself
- users can always use the right sidebar as the sole detailed property editor
- users can move between field, timeline, and sidebar without losing selection context
- dense paths remain readable through zoom, grouping, and stacking
- the bottom workspace feels like a real editing surface, not a compact utility widget

## First Release Scope Boundary

The first release includes:

- the three-region layout with a substantial bottom timeline dock
- estimated-time-based timeline projection
- path structure visibility
- one shared event trigger group with stacked lanes
- one combined constraints row with direct ranged-constraint editing
- zoom, scroll, fit-all, and center-on-selection behavior
- single-selection synchronization across canvas, timeline, and sidebar
- direct event trigger placement and repositioning from the timeline
- basic event trigger stacking
- the right sidebar as the sole detailed property editor

The first release explicitly excludes:

- distance/progress as the primary timeline axis
- semantic trigger categories or multiple trigger group families
- multi-selection and batch timeline edits
- minimap or overview-strip requirements
- rich animation polish beyond lightweight orientation feedback
- multi-item or bulk structure reordering behaviors whose model semantics are not already safe and clear

These exclusions are deliberate so the implementation can ship the core editing workflow first without expanding into a second wave of interaction design.

## Deferred Enhancements

Future design passes may still evaluate:

- alternate distance/progress readouts layered on top of the default time axis
- semantic trigger grouping if the model gains stable trigger categories
- a minimap or overview strip for very dense projects
- multi-selection once single-item interactions are proven stable
