# Development Context

## Role

This is BUI's living engineering context and PySide6 development guide. Read it before
implementation-heavy work.

This document is allowed to be detailed. Its job is to save future agents from rediscovering local
Qt, model, persistence, undo, autosave, timeline, and testing conventions. Update it when durable
architecture, data-flow, persistence, testing, or implementation patterns change. Do not use it for
task lists, speculative features, or one-off notes.

## Non-Negotiable Compatibility

BUI must remain 100% compatible with BLine-Lib path and config files.

- Do not change the persisted path or config schema without explicit user approval.
- Preserve path JSON semantics for translations, waypoints, rotations, event triggers, flat
  constraints, and ranged constraints.
- Preserve `config.json` semantics for robot/project defaults.
- Event trigger `lib_key` values are external library keys. The GUI should store and pass them
  through without inventing robot-side meaning.
- BUI can add editor-only state only when it belongs outside path/config files, usually in
  app-local `QSettings`.
- Legacy path repair/conversion behavior in deserialization is compatibility behavior. Treat it as
  part of the supported data surface.

## PySide6 Mental Model In This Repo

BUI is a Qt Widgets application.

- It is not a web app, not React, not QML, and not Qt Designer.
- `QApplication` owns process-level app state and the event loop.
- `QMainWindow` owns the shell, menus, status bar, central layout, and top-level coordination.
- `QWidget` subclasses provide forms, panels, controls, dialogs, and custom timeline surfaces.
- `QGraphicsView`, `QGraphicsScene`, and custom `QGraphicsItem` subclasses implement the field
  canvas.
- Signals and slots are the integration mechanism between regions.

There is no DOM, no web-style CSS cascade, and no retained React-like state tree. Qt has its own
object ownership, event dispatch, repaint, and layout timing. Many visual or selection operations
that look synchronous in code do not settle until the event loop runs.

The UI is hand-authored Python. There are no `.ui` files. Follow the existing construction pattern
unless there is a strong reason to introduce a new one.

## Application Boot And Module Map

Startup flow:

1. `main.py` creates or reuses `QApplication`.
2. `configure_application_identity()` sets BUI app identity before QSettings-backed components are
   created.
3. `ui.resources.ensure_assets_loaded()` imports `assets_rc.py` so `:/assets/...` paths work.
4. `set_dark_theme()` applies the global Fusion palette and top-level stylesheet.
5. `ui.main_window.MainWindow` creates the shell and wires the app.

Core areas:

- `main.py`: startup, BUI identity, global theme, shortcut creation, entrypoint.
- `ui/main_window/window.py`: three-region shell, signal wiring, undo/autosave coordination,
  project actions, timeline edit handlers.
- `ui/main_window/menus.py`: menu construction and menu styling.
- `ui/main_window/events.py`: event filtering and window-state stabilization.
- `ui/main_window/autosave.py`: autosave timer and status bar state.
- `ui/canvas/view.py`: field canvas, graphics scene, geometry editing, simulation preview.
- `ui/canvas/items/elements.py`: custom path-element graphics items.
- `ui/canvas/items/sim.py`: simulated robot/path visuals.
- `ui/timeline/placeholder.py`: timeline dock, projection, transport, zoom/scroll, editing.
- `ui/sidebar/sidebar.py`: property sidebar and exact-value editing orchestration.
- `ui/sidebar/components/property_editor.py`: element property controls.
- `ui/sidebar/components/constraint_manager.py`: constraint controls, ranged bars, popout sync.
- `models/path_model.py`: path data model.
- `models/ordinal_remap.py`: ranged-constraint remapping after structure changes.
- `models/simulation.py`: editor simulation/projection support.
- `utils/project_io.py`: path serialization/deserialization.
- `utils/project_manager.py`: project/config/settings persistence.
- `utils/undo_system.py`: snapshot undo/redo commands.

Conceptually, the app is a widget shell around a graphics editor, timeline editor, and property
sidebar, backed by a mutable Python model with snapshot undo and explicit signal synchronization.

## Source Of Truth And Data Flow

The Python path model is the source of truth.

- `MainWindow.path` and `Sidebar.path` reference the authoritative path state.
- Canvas items are visual handles over model objects.
- Timeline markers and spans are projections of model objects.
- Sidebar widgets read and write model/config values.
- Undo/redo replaces live model state from snapshots.

Do not treat widget values, `QGraphicsItem` positions, or timeline projection objects as durable
application state. Rebuild UI projections from the model when in doubt.

Typical sidebar mutation flow:

1. Sidebar emits `aboutToChange`.
2. `MainWindow` deep-copies current model state for undo.
3. Sidebar or a component mutates the model.
4. Sidebar emits `modelChanged` or `modelStructureChanged`.
5. Canvas refreshes and simulation rebuild is requested.
6. Timeline receives a fresh projection from the model.
7. Sidebar emits `userActionOccurred`.
8. `MainWindow` records a `PathCommand` from old to new snapshots.

Typical canvas mutation flow:

1. A `QGraphicsItem` moves or rotates.
2. `CanvasView` emits `elementMoved` or `elementRotated`.
3. `MainWindow` mutates the model directly.
4. Sidebar and timeline refresh visible values/projections.
5. On drag finish or rotation finish, `MainWindow` records the grouped undo action.

Timeline mutations should follow the same model-first pattern: resolve placement/update intent in
the timeline, mutate the path in `MainWindow`, refresh all projections, record undo, and autosave.

## Persistence Boundaries

There are three persistence layers. Decide which one a change belongs to before adding state.

### App-Local QSettings

Use `QSettings` for machine-local user preferences and launch continuity. These values are not part
of a robot path, should not be committed to project files, and must not affect BLine-Lib
compatibility.

Examples:

- last selected project directory
- last opened path filename
- recent project list
- simulated path display mode

`ProjectManager` should own QSettings keys when practical. Avoid scattering raw settings keys
through UI classes.

### Project config.json

Use `config.json` for shared project defaults and robot/editor settings that influence simulation,
authoring defaults, or path interpretation.

Examples:

- robot dimensions
- protrusion settings and event-key mappings
- default kinematic constraints
- default handoff radius and end tolerances

Changing config is a project data change. It should preserve config save/load behavior, undo/redo,
refresh, and autosave expectations where applicable.

### Path JSON Files

Use path JSON files only for BLine path semantics consumed by BLine-Lib.

Examples:

- translation targets, waypoints, rotation targets, and event triggers
- flat path constraints
- ranged constraints

Autosave writes the current path through this layer. Undo/redo is in-memory snapshot state and is
not persisted across app restarts.

Rule of thumb: view state belongs in `QSettings`; robot/project defaults belong in `config.json`;
path semantics belong in path JSON.

## Timeline And Constraint Model

The timeline uses estimated elapsed time as the primary user-facing axis, with path progress as
supporting projection data.

Important contracts:

- Structure markers represent path elements in sequence.
- Event triggers are point-like timeline objects positioned by `t_ratio` between neighboring
  anchors.
- Ranged constraints are span-like timeline objects.
- Translation ranged constraints use the translation domain: `TranslationTarget` and `Waypoint`.
- Rotation ranged constraints use the rotation domain: `RotationTarget` and `Waypoint`.
- Event triggers are not in either ranged-constraint ordinal domain.
- Ranged-constraint ordinals are 1-based in the model/UI layer and serialized as zero-based values
  for the BLine-compatible JSON shape.

When path structure changes, remap ranged constraints using `models.ordinal_remap`. Do not
hand-roll ordinal updates in feature code.

The timeline is not display-only. It owns transport controls, scrubbing, zoom, fit-to-view,
selection, add modes, and direct editing requests. Model mutation should still happen through
`MainWindow` so canvas, sidebar, timeline, undo, and autosave stay coordinated.

## Undo/Redo Contract

Undo/redo must always work for user-visible path and config edits.

Undo/redo is snapshot-based, not diff-based:

- Deep copies are expected.
- Object identity can change after undo/redo.
- Components holding references into model lists must resync after command execution.
- Do not build features that depend on object identity surviving undo.

Safe mutation pattern:

1. Capture old state before the user-driven mutation.
2. Apply the mutation.
3. Refresh projections from the model.
4. Record the command after mutation, usually via deferred `QTimer.singleShot(0, ...)`.
5. If UI caches references to mutable model objects, resync after undo/redo.

Undo/redo should coordinate canvas, timeline, sidebar, autosave, and simulation refresh. Broken
undo/redo is both a technical bug and a product trust failure.

## Autosave And Project Persistence

Autosave is debounced and status-aware.

- `AutosaveController` owns timers and status bar UI.
- Sidebar changes and canvas drag finish currently drive autosave triggers.
- Project load/save behavior goes through `ProjectManager`.
- Selecting an FRC repo root can resolve to `src/main/deploy/autos`.
- Autosave should only write valid project state.

If a new UI action changes persistent project/path/config data, ensure it schedules autosave and
records undo consistently with existing flows.

## Qt Timing And Deferred Work

`QTimer.singleShot(...)` is a core local tool, not a last-resort workaround.

Common reasons it appears:

- letting Qt finish selection or layout updates first
- avoiding re-entrancy during widget rebuilds
- preserving scroll position after Qt auto-scrolls
- creating undo commands after mutation has been applied
- resyncing references after undo replaces deep-copied objects
- postponing centering, fitting, or overlay positioning until geometry is ready

Common patterns:

- `QTimer.singleShot(0, ...)` for next-event-loop deferral
- short delays such as `20`, `50`, `100`, `150`, or `1000` ms for stubborn Qt behaviors

When you see a timer in this repo, assume there is a sequencing issue behind it. Do not remove or
collapse deferrals unless targeted tests and manual checks prove the behavior remains stable.

## Signals, Selection, And MainWindow Wiring

`MainWindow.__init__()` is intentionally dense. It is the signal graph for the app.

It wires:

- sidebar selection to canvas and timeline selection
- canvas selection to sidebar and timeline selection
- timeline selection to sidebar and canvas highlight/selection
- sidebar model changes to canvas refresh, simulation rebuild, and timeline projection refresh
- constraint preview signals to canvas overlays and timeline selection
- timeline edit requests to model mutations
- delete, undo, redo, and autosave flows

Before changing cross-region behavior, inspect the existing signal graph in
`ui/main_window/window.py`. Bugs here usually come from signal ordering, duplicate emission, or
feedback loops.

Selection churn is a real issue:

- `CanvasView.select_index()` exits early when possible.
- `Sidebar` has propagation guards.
- Canvas, sidebar, and timeline preserve or restore scroll/selection state in programmatic flows.

If you change selection behavior, expect flicker, scroll jumps, stale highlights, or recursive
signals unless you preserve these guards.

## ui.qt_compat And Typing

Qt enums and flags are awkward under PySide6 stubs and mypy. This repo centralizes casts and
compatibility exports in `ui/qt_compat.py`.

Prefer existing exports when you hit enum/flag typing friction:

- `Qt`
- `QGraphicsItem`
- `QDialogButtonBox`
- `QSizePolicy`
- `QFormLayoutRoles`
- `QMessageBox`
- `QKeySequence`
- `QPainter`

Most UI modules use `# mypy: ignore-errors`. That is not ideal, but it is the current convention.
Do not spend time fighting PySide6 stub edge cases in UI modules unless there is a real bug or the
user explicitly asks for type cleanup.

## Sidebar Architecture

The sidebar is a widget-based editor composed from smaller managers:

- `Sidebar`: orchestration and top-level layout
- `ElementManager`: add/remove/reorder/type-switch behavior
- `PropertyEditor`: element property widgets
- `ConstraintManager`: constraint widgets, ranged segment bars, popout synchronization

Important facts:

- The sidebar dynamically rebuilds rows and form controls based on current selection.
- It installs an event filter to clear constraint previews when clicks happen outside range-related
  controls.
- It preserves scroll positions aggressively.
- Constraint manager maintains references to ranged constraints and must resync after undo.

When changing sidebar UI:

- assume rebuilds happen often
- avoid stashing stale child widget references outside the owning component
- prefer rebuilding and reselecting cleanly over mutating every sub-widget in place
- disconnect old signal handlers before reconnecting reused widgets
- preserve `aboutToChange -> mutate -> userActionOccurred` for model mutations

## Canvas / Graphics View Architecture

`CanvasView` is a custom `QGraphicsView` with:

- a `QGraphicsScene`
- field background pixmap
- custom scene items for translations, rotations, waypoints, and event triggers
- connecting lines between path elements
- selection pulse visuals
- handoff radius overlays
- constraint preview overlays
- simulated robot and trail

Custom item types live in `ui/canvas/items/elements.py`. Simulation visuals live in
`ui/canvas/items/sim.py`.

### Coordinate Systems

There are two coordinate spaces:

- model coordinates: robot/path coordinates in meters
- scene coordinates: Qt scene positions, including field-image offset and inverted Y

Use the existing conversion helpers:

- `_scene_from_model(x_m, y_m)`
- `_model_from_scene(x_s, y_s)`

Do not mix raw scene positions into model code or raw model coordinates into item painting. For the
current field, the view applies `FIELD_OFFSET_M`, and Y is inverted relative to screen coordinates.
If a visual looks mirrored or shifted, check conversion first.

### Item Constraints

Canvas items use `QGraphicsItem.ItemPositionChange` and `ItemPositionHasChanged` to:

- clamp anchor positions to the field and robot perimeter
- project rotation targets and event triggers onto segments between neighboring anchors
- emit live-move callbacks back to `CanvasView`

Geometric rules are partly enforced at the graphics item layer, not only in `MainWindow`.

When adding a draggable canvas item, decide:

- where authoritative geometry lives in the model
- how it converts to/from scene coordinates
- what constraints should run in `itemChange()`
- which signals should fire during live interaction and on release

### Selection, Paint, Pan, And Zoom

Canvas selection visuals are custom. Inspect selection pulse and layering helpers before changing
selected-state visuals.

Canvas panning and zooming are also custom. `CanvasView` overrides wheel, mouse, scroll, resize,
and show events to preserve field framing and overlay positioning. Any change in this area should
be checked manually with zooming, panning, dragging, rotation handles, and simulation overlays.

## Timeline Architecture

`TimelineDock` owns:

- transport controls and time labels
- playhead/scrubbing
- projection from path model to timeline rows
- left header rail and scrollable track canvas
- zoom slider and wheel zoom
- fit-to-view behavior
- add modes for structure, triggers, and constraints
- selection restoration or clearing after projection refresh

Header rail and track canvas alignment are visually critical. Fit-to-view and cursor-centered zoom
are also sensitive. Treat small offsets as real regressions.

Timeline edit requests should emit intent signals and let `MainWindow` mutate the model. This keeps
undo, autosave, sidebar, canvas, and simulation in sync.

## Styling And Resources

Styling has two layers:

1. Global Fusion palette and app stylesheet in `main.py`.
2. Local widget stylesheets in widgets, dialogs, and components.

Practical rules:

- Use object-name selectors for targeted local styling when possible.
- Broad parent styles can affect descendants unexpectedly.
- Stylesheet changes can alter size hints.
- If a widget fights layout or painting, inspect size policies, fixed/min/max sizes, and custom
  paint logic before adding more stylesheet rules.
- Stable dimensions matter for timeline rows, labels, buttons, and scroll/zoom behavior.

Qt resources are compiled into `assets_rc.py` and loaded through `ui/resources/__init__.py`.

Use resource paths such as:

- `:/assets/field26.png`
- `:/assets/remove_icon.png`
- `:/assets/add_icon.png`

If you add or rename an asset, update `assets.qrc`, regenerate `assets_rc.py`, and keep app UI on
resource paths instead of raw filesystem paths.

## Implementation Recipes

### Add A Model Property

1. Extend `models/path_model.py`.
2. Update `utils/project_io.py` serialization/deserialization.
3. Add control metadata in `ui/sidebar/utils/constants.py` if needed.
4. Update `PropertyEditor` or relevant sidebar component.
5. Update canvas rendering if the property has visual impact.
6. Update timeline projection if it affects sequence, timing, labels, or spans.
7. Update simulation if behavior changes.
8. Test serialization, undo/redo, autosave, and affected UI projection.

### Add A Sidebar-Only Control

1. Decide whether the control edits model state, config state, or app-local UI state.
2. Create the widget in `Sidebar`, `PropertyEditor`, `ConstraintManager`, or a local component.
3. Connect signals once; disconnect before reconnecting reused dynamic widgets.
4. If it mutates the model, preserve `aboutToChange -> mutate -> userActionOccurred`.
5. If it mutates config, preserve config undo/save/refresh expectations.
6. Ensure rebuild/refresh code restores visible state.

### Add A Canvas Item

1. Extend the model and serialization first if persistent.
2. Add item construction in `CanvasView._rebuild_items()`.
3. Define model/scene coordinate conversion.
4. Implement or reuse a `QGraphicsItem`.
5. Enforce placement constraints in the right layer.
6. Emit selection and live-edit signals consistent with existing items.
7. Update selection visuals, z-ordering, overlays, and connecting lines if needed.
8. Test drag, selection, undo, redo, autosave, simulation rebuild, and timeline sync.

### Add A Timeline Action Or Edit

1. Add projection data only if existing projection structures cannot represent the behavior.
2. Emit an intent signal from timeline UI.
3. Handle model mutation in `MainWindow`.
4. Refresh timeline projection, canvas, and sidebar from the model.
5. Record undo and schedule autosave.
6. Test placement math, selection, undo/redo, projection refresh, and visual edge cases.

### Add A Dialog

Use the existing dialog patterns:

- subclass `QDialog`
- build layout in Python
- style locally
- separate value extraction from widget construction
- pass callbacks or return values instead of reaching deeply into unrelated components
- preserve undo/config save behavior if values mutate project data

## Common Pitfalls

- Changing persisted JSON shape and breaking BLine-Lib compatibility.
- Bypassing the model as source of truth.
- Mutating model state in paint, hover, or passive selection code.
- Removing `QTimer.singleShot` deferrals without understanding sequencing.
- Caching model object references across undo/redo.
- Creating duplicate signal connections during dynamic rebuilds.
- Losing scroll position during sidebar or timeline selection.
- Treating event triggers as ranged-constraint domain elements.
- Hand-rolling ranged-constraint ordinal updates instead of using remap helpers.
- Adding a second inspector outside the sidebar.
- Making the timeline look or behave like a debug table rather than an editing surface.

## Verification Guidance

Use:

```bash
uv run pytest
```

Add focused tests for every distinct behavior. Choose coverage based on risk:

- Serialization/compatibility: round trips, legacy inputs, malformed inputs.
- Timeline projection/editing: placement math, zoom/scroll behavior, selection, undo, constraint
  spans, fit-to-view.
- Canvas/sidebar/main-window wiring: selection sync, model refresh, signal loops.
- Persistence/config changes: save/load, defaults, autosave, undo interactions.
- Visual alignment-sensitive logic: geometry calculations where practical.

Manual checks for non-trivial UI changes:

- app starts cleanly
- selection syncs across canvas, timeline, and sidebar
- undo/redo returns expected model and UI state
- autosave triggers when project data changes
- simulation rebuilds for behavior-affecting edits
- timeline zoom, pan, fit-to-view, and playhead stay aligned
- dense paths with multiple triggers/constraints remain readable
- window resize/fullscreen transitions do not break selection or layout

Docs-only changes do not require app tests.

