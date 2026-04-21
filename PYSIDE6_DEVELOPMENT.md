# PySide6 Development Guide for BLine-GUI

This document is the working guide for making effective UI changes in this codebase.
It combines PySide6 fundamentals with the repo-specific patterns that actually matter in
`BLine-GUI`.

The short version:

- This is a Qt Widgets application, not a web app and not a QML app.
- The UI is organized around a custom `QGraphicsView` editor on the left and a
  widget-based sidebar on the right.
- The source of truth is the Python path model in `models/`, not the canvas items.
- Undo/redo is snapshot-based and depends on specific signal sequencing.
- Deferred UI work with `QTimer.singleShot(...)` is used heavily to avoid re-entrancy,
  stale references, and Qt layout/selection churn.

If you are making UI changes here, you need to understand both general Qt Widgets
mechanics and the local contracts described below.

## 1. What PySide6 Means in This Repo

PySide6 is Qt for Python. In this repo it is used in the classic desktop style:

- `QApplication` owns the app lifecycle.
- `QMainWindow` owns the shell, menu bar, status bar, and central layout.
- `QWidget` subclasses provide forms, lists, dialogs, and custom controls.
- `QGraphicsView` + `QGraphicsScene` + custom `QGraphicsItem` subclasses implement the
  interactive path editor.
- Signals and slots are the primary integration mechanism between UI layers.

There is no DOM, no CSS cascade in the web sense, and no retained React-like state tree.
Qt has its own object model, event loop, ownership rules, and repaint/layout behavior.

## 2. High-Level Architecture

The app boot path is:

1. `main.py` creates or reuses `QApplication`.
2. `ui.resources.ensure_assets_loaded()` imports `assets_rc.py` so `:/assets/...` paths work.
3. `set_dark_theme()` applies the global Fusion palette and top-level stylesheet.
4. `ui.main_window.MainWindow` creates the shell.
5. `MainWindow` wires `CanvasView`, `Sidebar`, menus, autosave, and undo/redo together.

Core modules:

- `main.py`: app startup, theme, shortcut creation, entrypoint
- `ui/main_window/window.py`: shell, wiring, undo coordination, project actions
- `ui/main_window/menus.py`: menu construction and menu styling
- `ui/main_window/events.py`: event-filter and window-state stabilization behavior
- `ui/canvas/view.py`: custom `QGraphicsView` editor and simulation playback
- `ui/canvas/items/elements.py`: custom `QGraphicsItem` subclasses for path elements
- `ui/sidebar/sidebar.py`: right-hand editing surface
- `ui/sidebar/components/property_editor.py`: element property controls
- `ui/sidebar/components/constraint_manager.py`: constraint widgets, segment bars, popout
- `ui/config_dialog.py`: config editor dialog
- `utils/project_manager.py`: project persistence and `QSettings`
- `utils/undo_system.py`: command-based snapshot undo/redo

Conceptually, the app is closest to:

- a widget shell
- around a graphics editor
- backed by a mutable Python model
- with snapshot undo
- and explicit signal-based synchronization

## 3. Mental Model: Source of Truth and Data Flow

The single most important rule is:

The Python model is the source of truth. UI objects are projections of that model.

That means:

- `self.path` in `MainWindow` and `Sidebar` is the authoritative path state.
- Canvas items are visual handles for editing that state.
- Sidebar controls read and write model values.
- `refresh_from_model()` and `_rebuild_items()` re-project model state into the canvas.
- Undo/redo works by replacing model state snapshots, then refreshing the UI.

Do not treat a `QGraphicsItem` or a widget's current value as durable application state.
They are views over the model.

Typical mutation flow from the sidebar:

1. Sidebar emits `aboutToChange`.
2. `MainWindow` deep-copies the current model for undo.
3. Sidebar or a component mutates the model.
4. Sidebar emits `modelChanged` or `modelStructureChanged`.
5. Canvas refreshes and simulation rebuild is requested.
6. Sidebar emits `userActionOccurred`.
7. `MainWindow` records a `PathCommand` using the old and new snapshots.

Typical mutation flow from the canvas:

1. A `QGraphicsItem` moves or rotates.
2. `CanvasView` emits `elementMoved` or `elementRotated`.
3. `MainWindow` mutates the model directly.
4. Sidebar updates visible values.
5. On drag finish or rotation finish, `MainWindow` records the grouped undo action.

This separation is deliberate. Preserve it.

## 4. Why the Code Uses Qt Widgets, Not Designer/QML

Everything here is hand-authored Python UI code. That is a good fit for this app because:

- the editor is interaction-heavy
- the layout is custom and stateful
- the canvas behavior is tied directly to Python model logic
- dynamic widget creation is common, especially in the sidebar

There are no `.ui` files and no QML layer. If you add new UI, follow the existing Python
construction patterns unless there is a compelling reason not to.

## 5. Repo-Specific PySide6 Patterns

### 5.1 `ui.qt_compat` exists for typing friction

Qt enums and flags are awkward under PySide6 stubs and mypy. This repo centralizes a set of
`cast(Any, ...)` shims in `ui/qt_compat.py`.

If you hit enum/flag typing issues, prefer using the existing compat exports:

- `Qt`
- `QGraphicsItem`
- `QDialogButtonBox`
- `QSizePolicy`
- `QFormLayoutRoles`
- `QMessageBox`
- `QKeySequence`
- `QPainter`

This codebase also uses `# mypy: ignore-errors` in most UI files. That is not ideal, but it is
the current local convention. Do not waste time fighting PySide6 stub edge cases in UI modules
unless there is a real bug.

### 5.2 `QTimer.singleShot(...)` is a core tool, not a workaround of last resort

This repo uses deferred work constantly. Common reasons:

- let Qt finish selection/layout updates first
- avoid re-entrancy during widget rebuilds
- preserve scroll position after the framework auto-scrolls
- create undo commands after the mutation is already applied
- resync references after undo replaces deep-copied objects
- postpone centering, fitting, or overlay positioning until geometry is ready

Patterns used here:

- `QTimer.singleShot(0, ...)` for next-event-loop deferral
- short delays like `20`, `50`, `100`, `150`, `1000` ms for stubborn Qt behaviors

When you see a timer in this repo, assume there is a real sequencing issue behind it. Do not
remove or collapse those deferrals casually.

### 5.3 Signal wiring is explicit and dense

`MainWindow.__init__()` is the integration hub. It wires:

- sidebar selection to canvas selection
- canvas selection to sidebar selection
- sidebar model changes to canvas refresh
- sidebar structure changes to canvas item rebuild
- constraint preview signals to canvas overlays
- popout signals to canvas highlight state
- delete/undo/redo flows
- autosave triggers

Before changing cross-component behavior, inspect the existing signal graph in
`ui/main_window/window.py`. Problems here usually come from signal ordering, duplicate emission,
or feedback loops.

### 5.4 Selection churn is a real issue

The code has explicit guard logic to avoid redundant select-clear-select cycles. Examples:

- `CanvasView.select_index()` exits early if the requested item is already selected.
- `Sidebar` suppresses one-shot propagation when selection came from the canvas.
- Both canvas and sidebar preserve scroll positions during programmatic selection.

If you change selection behavior, assume visual flicker and scroll jumps will appear unless you
preserve these guards.

## 6. Main Window Responsibilities

`MainWindow` is not just a container. It owns several important coordination concerns:

- creating the central horizontal layout
- instantiating `CanvasView` and `Sidebar`
- creating menus and status bar
- project open/save/load actions
- startup load behavior
- undo/redo integration
- config dialog lifecycle
- autosave controller lifecycle
- event filtering for global preview clearing

Important local conventions:

- `build_menu_bar(self)` is called before central layout setup.
- `QTimer.singleShot(0, self._startup_load)` defers initial project/path loading.
- `WindowEventMixin.changeEvent()` suspends sidebar work during fullscreen/window-state churn.
- `_record_path_change()` and `_record_config_change()` create commands on the next event-loop turn.

Do not move state mutation into random widget code when it should remain centralized in
`MainWindow`.

## 7. Sidebar Architecture

The sidebar is a widget-based editor composed from smaller managers:

- `Sidebar`: orchestration and top-level layout
- `ElementManager`: add/remove/reorder/type-switch behavior
- `PropertyEditor`: element property widgets
- `ConstraintManager`: constraint widgets, ranged-segment bars, popout synchronization

Key facts:

- The sidebar is fixed-width (`300` px).
- It dynamically rebuilds list rows and form controls based on current selection.
- It installs an event filter to clear constraint previews when clicks happen outside
  range-related controls.
- It preserves scroll positions aggressively.

Important practical rule:

When changing sidebar UI, assume that rebuilds happen often and current widget references may
become invalid after refreshes, path swaps, or undo/redo.

That means:

- do not stash stale child widget references outside the owning component
- prefer rebuilding and re-selecting cleanly over trying to mutate every sub-widget in place
- be careful about connecting the same signal multiple times after rebuilds

`ConstraintManager` explicitly disconnects and reconnects some signals during rebuilds to avoid
duplicate handlers. Follow that pattern if you add more dynamic controls.

## 8. Canvas Architecture: This Is a Graphics View App

The most specialized PySide6 knowledge you need for this repo is the Graphics View framework.

`CanvasView` is a custom `QGraphicsView` with:

- a `QGraphicsScene`
- a field background pixmap
- custom scene items for translations, rotations, waypoints, and event triggers
- connecting lines between path elements
- selection pulse visuals
- handoff radius overlays
- constraint preview overlays
- a simulated robot and trail
- a transport overlay for playback

Custom item types live in `ui/canvas/items/elements.py`:

- `CircleElementItem`
- `RectElementItem`
- `EventTriggerItem`
- `RotationHandle`
- `HandoffRadiusVisualizer`

Simulation visuals live in `ui/canvas/items/sim.py`.

### 8.1 Coordinate systems

There are two coordinate spaces:

- model coordinates: robot/path coordinates in meters
- scene coordinates: Qt scene positions, including field-image offset and inverted Y

Use:

- `_scene_from_model(x_m, y_m)`
- `_model_from_scene(x_s, y_s)`

Do not mix raw scene positions into model code or vice versa.

For the 2026 field, the view applies `FIELD_OFFSET_M`, and Y is inverted relative to normal
screen coordinates. If a visual looks mirrored or shifted, check the conversion path first.

### 8.2 Interactive items are constrained in `itemChange()`

Canvas items use `QGraphicsItem.ItemPositionChange` and `ItemPositionHasChanged` to:

- clamp anchor positions to the field and robot perimeter
- project rotation targets and event triggers onto the line segment between neighbor anchors
- emit live-move callbacks back to `CanvasView`

That means geometric rules are partly enforced at the `QGraphicsItem` layer, not only in
`MainWindow`.

If you add a new draggable canvas item, decide:

- where its authoritative geometry lives in the model
- how it converts to/from scene coordinates
- what constraints should run in `itemChange()`
- what signals it should trigger during live interaction and on release

### 8.3 Selection and paint are custom

Selected items are not left to default Qt visuals. The canvas provides:

- custom selection pulse animation via a timer
- custom `paint()` logic in item classes
- explicit z-ordering changes when selected

If you change selection visuals, inspect:

- `_set_selection_pulse_active()`
- `_on_selection_pulse_tick()`
- `_apply_selection_layering()`
- custom `paint()` methods in the item classes

### 8.4 Panning and zooming are custom too

`CanvasView` overrides:

- `wheelEvent()` for zoom
- `mousePressEvent()` / `mouseMoveEvent()` / `mouseReleaseEvent()` for panning
- `scrollContentsBy()` to keep the transport overlay anchored
- `resizeEvent()` / `showEvent()` to fit the scene and reposition overlay controls

If a change affects viewport behavior, test:

- zoom limits
- panning on background vs interactive items
- overlay positioning during scroll/zoom/resize

## 9. Undo/Redo Contract

Undo/redo is snapshot-based, not diff-based.

That has several consequences:

- deep copies are expected
- object identity can change after undo/redo
- components holding references into lists of model objects must resync after command execution

This is why `ConstraintManager` has deferred resync logic after undo. The old `RangedConstraint`
objects are replaced by deep-copied clones, so cached references become stale.

Rules for safe changes:

1. Before a user-driven mutation that should be undoable, capture old state.
2. Apply the mutation.
3. Record the command after the mutation, usually via deferred `QTimer.singleShot(0, ...)`.
4. If your UI caches references to mutable model objects, resync after undo/redo.

Do not build new features that depend on object identity surviving undo.

## 10. Autosave and Persistence

Persistence is split between:

- `QSettings` for app-level "last project" and recent-project state
- JSON files for project config and path data

`utils/project_manager.py` owns both project structure and `QSettings`.

Important points:

- Selecting an FRC repo root auto-resolves to `src/main/deploy/autos`
- config defaults influence UI defaults and simulation behavior
- autosave is debounced and driven by sidebar changes and canvas drag finish
- `AutosaveController` updates the status bar UI directly

If you add UI that changes persistent data, decide whether it belongs in:

- `QSettings` as application preference
- `config.json` as project configuration
- path JSON as model content

Do not blur those layers.

## 11. Styling in This Repo

There are two styling layers:

1. global palette + app stylesheet in `main.py`
2. local widget stylesheets in individual widgets/dialogs/components

The codebase mostly uses:

- Fusion application style
- dark palette
- targeted `setStyleSheet()` blocks on containers and controls

Practical conventions:

- top-level app chrome uses the global palette and stylesheet
- component-specific visuals are set locally in Python
- spacing, margins, and minimum/maximum sizes are used heavily to force alignment

Qt stylesheet caveats matter here:

- styling a parent can affect descendants unexpectedly
- object-name selectors like `QWidget#titleBar` are safer than broad widget selectors
- style changes can alter size hints
- custom painting is sometimes a better fit than more stylesheet complexity

If you are trying to make a widget look right and it keeps fighting layout/painting,
inspect size policies and custom paint logic before adding more stylesheet overrides.

## 12. Resources and Assets

Qt resources are compiled into `assets_rc.py` and loaded once through `ui/resources/__init__.py`.

Use resource paths like:

- `:/assets/field26.png`
- `:/assets/remove_icon.png`
- `:/assets/add_icon.png`

Important rules:

- if you add or rename an asset, update `assets.qrc`
- regenerate `assets_rc.py` as needed
- call `ensure_assets_loaded()` before relying on resource paths

Do not replace working `:/assets/...` usage with raw filesystem paths inside the app UI.

## 13. Common Implementation Recipes

### 13.1 Add a new property to an element

Typical steps:

1. Extend the model in `models/path_model.py`.
2. Update serialization in `utils/project_io.py`.
3. Add spinner or control metadata in `ui/sidebar/utils/constants.py`.
4. Ensure `PropertyEditor` creates the right control.
5. Update sidebar selection refresh to read/write the field.
6. Update canvas rendering if the property has visual impact.
7. Update simulation if behavior changes.
8. Verify undo/redo and autosave.

### 13.2 Add a new sidebar-only control

Typical steps:

1. Decide whether the control edits model state, config state, or pure UI state.
2. Create the widget in the owning component, usually `Sidebar`, `PropertyEditor`, or
   `ConstraintManager`.
3. Connect the signal once, carefully, especially if the control may be rebuilt.
4. If it mutates the model, preserve the `aboutToChange` -> mutate -> `userActionOccurred`
   flow.
5. If it should survive rebuilds, make sure refresh code restores its state.

### 13.3 Add a new canvas item type

Typical steps:

1. Extend the model and serialization first.
2. Add item construction in `CanvasView._rebuild_items()`.
3. Define coordinate conversion and placement rules.
4. Implement a `QGraphicsItem` subclass or reuse an existing one.
5. Emit selection and live-edit signals consistent with other item types.
6. Update selection visuals, overlays, and connection lines if needed.
7. Update sidebar editing support.
8. Test drag, rotate, selection, undo, redo, autosave, and simulation rebuilds.

### 13.4 Add a new dialog

Use the `ConfigDialog` pattern:

- subclass `QDialog`
- create layout in Python
- set modal behavior intentionally
- style locally if needed
- separate value extraction from widget construction
- if live updates are needed, pass a callback instead of letting the dialog reach deeply into
  unrelated objects

## 14. Common Pitfalls in This Codebase

### 14.1 Re-entrancy during rebuilds

Symptoms:

- duplicate signal handling
- flicker
- selection bouncing
- crashes from stale widgets

Mitigations used here:

- `_suspended` and `_ready` guards
- one-shot suppression flags
- deferred selection and refresh
- explicit disconnect/reconnect in rebuild paths

### 14.2 Stale object references after undo

If you cache model objects across undo, expect bugs. Cache keys or indexes when possible, and
rebuild references after command execution.

### 14.3 Scroll position loss

Qt will happily auto-scroll list widgets and scroll areas during selection or relayout.
This repo works around that with explicit scroll capture and restore. Preserve those patterns.

### 14.4 Duplicate signal connections

Dynamic rebuilds make it easy to connect the same slot repeatedly. If a widget is reused across
rebuilds, disconnect old handlers before reconnecting.

### 14.5 Mixing model mutation into paint or selection code

Painting should paint. Selection handlers should select. Keep model mutation in explicit edit
paths, not in passive rendering code.

### 14.6 Assuming Qt layout timing is synchronous

Many layout-dependent operations need to happen later:

- `fitInView`
- restoring scrollbars
- centering selected items
- positioning overlay widgets

When geometry-dependent code acts flaky, test a deferred invocation before redesigning the logic.

## 15. Verification Checklist for UI Changes

Any non-trivial UI change should be checked against this list:

- App still starts cleanly.
- New assets load through Qt resources.
- Selection sync between sidebar and canvas still works.
- No extra scroll jumps in the sidebar.
- Undo and redo still produce the expected UI state.
- Autosave still triggers when it should.
- Config changes apply live if intended.
- Simulation rebuild still occurs for behavior-affecting edits.
- Panning, zooming, and overlays still behave correctly.
- No duplicate signal side effects after repeated rebuilds.
- Window resize/fullscreen transitions do not cause churn or broken selection.

For canvas changes specifically:

- drag anchors
- drag projected items
- rotate handles
- clear selection by clicking background
- zoom with wheel
- pan on empty space
- run simulation playback
- test with longer paths and multiple constraints

## 16. Recommended External PySide6 Topics

For engineers already comfortable with desktop UI work, the most relevant Qt/PySide6 topics for
this repo are:

- Qt Widgets application structure
- signals and slots
- `QMainWindow`
- layouts and size policies
- event filters
- `QTimer`
- `QSettings`
- Graphics View framework
- `QGraphicsView`, `QGraphicsScene`, and `QGraphicsItem`
- Qt resource system (`.qrc`)
- Qt stylesheets

The official Qt for Python docs are the right reference source. For this repo, prioritize
Widgets and Graphics View over QML.

## 17. Practical Guidance for Future Contributors

If you are new to this repo and need to make UI changes quickly, follow this order:

1. Read `main.py`, `ui/main_window/window.py`, and `ui/main_window/events.py`.
2. Read `ui/sidebar/sidebar.py`, `ui/sidebar/components/property_editor.py`, and
   `ui/sidebar/components/constraint_manager.py`.
3. Read `ui/canvas/view.py` and `ui/canvas/items/elements.py`.
4. Read `utils/project_manager.py` and `utils/undo_system.py`.
5. Make the smallest change that preserves the existing signal and mutation contracts.
6. Test the behavior manually in the running GUI.

The fastest way to break this app is to:

- bypass the model as source of truth
- ignore undo sequencing
- remove deferred Qt timers without understanding why they exist
- introduce signal loops
- treat the canvas like a passive drawing surface instead of an interactive graphics editor

The fastest way to succeed is to:

- keep state in the model
- keep wiring explicit
- rebuild views from model state when in doubt
- respect the existing deferred-update patterns
- test interactions, not just appearance

