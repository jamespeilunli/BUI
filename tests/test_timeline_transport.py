from __future__ import annotations

from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import QEvent

from models.path_model import Path, RangedConstraint, TranslationTarget
from ui.qt_compat import Qt
from ui.timeline.placeholder import (
    MAX_ZOOM_PX_PER_M,
    MIN_ZOOM_PX_PER_M,
    PLAYBACK_STEP_S,
    TimelineDock,
    TimelineSelection,
)


def test_playback_state_updates_button_label_and_playhead(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock.set_playback_state(0.75, 2.0, is_playing=True, enabled=True)

        assert dock._play_pause_btn.isEnabled()
        assert dock._play_pause_btn.text() == "Pause"
        assert "Playing at 0.75 / 2.00 s" == dock._playback_label.text()
        assert dock._track_canvas._is_playing is True
        assert dock._track_canvas._playhead_s_m == 0.75

        dock.set_playback_state(9.0, 0.0, is_playing=True, enabled=False)

        assert not dock._play_pause_btn.isEnabled()
        assert dock._play_pause_btn.text() == "Play"
        assert dock._playback_label.text() == "No simulation at 9.00 / 0.00 s"
        assert dock._track_canvas._is_playing is False
    finally:
        dock.close()


def test_timeline_keyboard_shortcuts_emit_transport_requests(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    scrubbed: list[float] = []
    toggles: list[None] = []
    dock.scrubRequested.connect(scrubbed.append)
    dock.playPauseToggled.connect(lambda: toggles.append(None))
    try:
        dock.set_playback_state(1.0, 2.0, is_playing=False, enabled=True)

        dock.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
        dock.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
        dock.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))

        assert scrubbed == [1.0 + PLAYBACK_STEP_S, 1.0 - PLAYBACK_STEP_S]
        assert len(toggles) == 1
    finally:
        dock.close()


def test_zoom_slider_round_trip_respects_dynamic_minimum(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock._minimum_zoom_px_per_m = 40
        for zoom in (40, 80, 200, MAX_ZOOM_PX_PER_M):
            slider_value = dock._slider_value_from_zoom(zoom)
            round_trip = dock._zoom_value_from_slider(slider_value)
            assert round_trip >= 40
            assert abs(round_trip - zoom) <= max(3, int(zoom * 0.08))

        assert dock._zoom_value_from_slider(-999) >= 40
        assert dock._zoom_value_from_slider(999) <= MAX_ZOOM_PX_PER_M
    finally:
        dock.close()


def test_fit_to_all_uses_minimum_zoom_for_empty_or_tiny_paths(qt_app):
    dock = TimelineDock(Path())
    try:
        assert dock._fit_zoom_px_per_m() >= MIN_ZOOM_PX_PER_M
    finally:
        dock.close()


def test_zoom_from_wheel_keeps_content_under_cursor_stable(qt_app):
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(30.0, 0.0),
        ]
    )
    dock = TimelineDock(path)
    try:
        dock.resize(640, 240)
        dock.show()
        qt_app.processEvents()
        dock._sync_canvas_size()
        dock._set_zoom_px_per_m(180)
        qt_app.processEvents()

        hbar = dock._track_scroll.horizontalScrollBar()
        hbar.setValue(240)
        assert hbar.maximum() > 240
        viewport_x = 180.0
        before_zoom = float(dock._track_canvas._zoom_px_per_m)
        before_s = (hbar.value() + viewport_x - dock._track_canvas._track_left()) / before_zoom

        dock._zoom_from_wheel(120, viewport_x, dock._track_scroll.viewport())
        after_zoom = float(dock._track_canvas._zoom_px_per_m)
        after_s = (hbar.value() + viewport_x - dock._track_canvas._track_left()) / after_zoom

        assert after_zoom > before_zoom
        assert abs(after_s - before_s) < 0.05
    finally:
        dock.close()


def test_add_modes_are_mutually_exclusive_and_escape_clears_them(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock._apply_structure_add_armed(True, "waypoint")
        assert dock._structure_add_armed
        assert not dock._trigger_add_armed
        assert not dock._constraint_add_armed

        dock._apply_trigger_add_armed(True)
        assert dock._trigger_add_armed
        assert not dock._structure_add_armed
        assert not dock._constraint_add_armed

        dock._apply_constraint_add_armed(True)
        assert dock._constraint_add_armed
        assert not dock._structure_add_armed
        assert not dock._trigger_add_armed

        dock.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        assert not dock._structure_add_armed
        assert not dock._trigger_add_armed
        assert not dock._constraint_add_armed
    finally:
        dock.close()


def test_selection_is_restored_or_cleared_after_projection_refresh(qt_app):
    path = Path(
        path_elements=[TranslationTarget(0.0, 0.0), TranslationTarget(1.0, 0.0)],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.0,
                start_ordinal=1,
                end_ordinal=1,
            )
        ],
    )
    dock = TimelineDock(path)
    try:
        dock.select_path_index(1)
        dock.set_path(Path(path_elements=[TranslationTarget(0.0, 0.0)]), {})
        assert dock._selection is None

        dock.set_path(path, {})
        dock.select_constraint_range("max_velocity_meters_per_sec", 1, 1)
        path.ranged_constraints.clear()
        dock.set_path(path, {})
        assert dock._selection is None
    finally:
        dock.close()


def test_delete_request_ignores_stale_path_selection(qt_app):
    dock = TimelineDock(Path(path_elements=[TranslationTarget(0.0, 0.0)]))
    deletes: list[int] = []
    dock.pathItemDeleteRequested.connect(deletes.append)
    try:
        dock._selection = TimelineSelection(kind="path", path_index=5)

        dock._on_delete_selection_requested()

        assert deletes == []
    finally:
        dock.close()
