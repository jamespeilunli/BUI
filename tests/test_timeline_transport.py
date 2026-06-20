from __future__ import annotations

from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import QEvent, QPoint, QPointF

from models.path_model import Path, RangedConstraint, TranslationTarget
from ui.qt_compat import Qt
from ui.timeline.placeholder import (
    MAX_ZOOM_PX_PER_M,
    MIN_ZOOM_PX_PER_M,
    PLAYBACK_STEP_S,
    TimelineDock,
    TimelineSelection,
    _format_timecode,
)


class _WheelEventStub:
    def __init__(
        self,
        *,
        pixel_x: int = 0,
        pixel_y: int = 0,
        angle_x: int = 0,
        angle_y: int = 0,
        x: float = 120.0,
    ) -> None:
        self.accepted = False
        self._pixel_delta = QPoint(pixel_x, pixel_y)
        self._angle_delta = QPoint(angle_x, angle_y)
        self._position = QPointF(x, 20.0)

    def type(self):
        return QEvent.Wheel

    def pixelDelta(self):  # noqa: N802
        return self._pixel_delta

    def angleDelta(self):  # noqa: N802
        return self._angle_delta

    def position(self):
        return self._position

    def accept(self) -> None:
        self.accepted = True


def _show_zoomed_timeline(qt_app) -> TimelineDock:
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(30.0, 0.0),
        ]
    )
    dock = TimelineDock(path)
    dock.resize(640, 240)
    dock.show()
    qt_app.processEvents()
    dock._sync_canvas_size()
    dock._set_zoom_px_per_m(180)
    qt_app.processEvents()
    return dock


def test_playback_state_updates_icon_timecode_and_playhead(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock.set_playback_state(0.75, 2.0, is_playing=True, enabled=True)

        assert dock._play_pause_btn.isEnabled()
        assert dock._play_pause_btn.text() == ""
        assert not dock._play_pause_btn.icon().isNull()
        assert dock._play_pause_btn.toolTip() == "Pause"
        assert dock._time_current_label.text() == "0.75"
        assert dock._time_total_label.text() == "2.00 s"
        assert dock._track_canvas._is_playing is True
        assert dock._track_canvas._playhead_s_m == 0.75

        dock.set_playback_state(9.0, 0.0, is_playing=True, enabled=False)

        assert not dock._play_pause_btn.isEnabled()
        assert dock._play_pause_btn.text() == ""
        assert dock._play_pause_btn.toolTip() == "Play"
        assert dock._time_current_label.text() == "9.00"
        assert dock._time_total_label.text() == "0.00 s"
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


def test_zoom_slider_round_trip_uses_absolute_range(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock._minimum_zoom_px_per_m = 400
        for zoom in (MIN_ZOOM_PX_PER_M, 80, 200, MAX_ZOOM_PX_PER_M):
            slider_value = dock._slider_value_from_zoom(zoom)
            round_trip = dock._zoom_value_from_slider(slider_value)
            assert round_trip >= MIN_ZOOM_PX_PER_M
            assert abs(round_trip - zoom) <= max(3, int(zoom * 0.08))

        assert dock._zoom_value_from_slider(-999) == MIN_ZOOM_PX_PER_M
        assert dock._zoom_value_from_slider(999) <= MAX_ZOOM_PX_PER_M
    finally:
        dock.close()


def test_timecode_format_uses_no_leading_zero_padding():
    first = _format_timecode(7.23, 20.0)
    second = _format_timecode(12.23, 20.0)

    assert first == "7.23 / 20.00 s"
    assert second == "12.23 / 20.00 s"
    assert not first.startswith("0")


def test_timecode_labels_hold_stable_width_without_leading_zeroes(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        current_width = dock._time_current_label.width()
        total_width = dock._time_total_label.width()

        dock.set_playback_state(7.23, 20.0, is_playing=False, enabled=True)
        assert dock._time_current_label.text() == "7.23"
        assert dock._time_total_label.text() == "20.00 s"
        assert dock._time_current_label.width() == current_width
        assert dock._time_total_label.width() == total_width

        dock.set_playback_state(12.23, 20.0, is_playing=False, enabled=True)
        assert dock._time_current_label.text() == "12.23"
        assert dock._time_total_label.text() == "20.00 s"
        assert dock._time_current_label.width() == current_width
        assert dock._time_total_label.width() == total_width
    finally:
        dock.close()


def test_fit_to_all_uses_minimum_zoom_for_empty_or_tiny_paths(qt_app):
    dock = TimelineDock(Path())
    try:
        assert dock._fit_zoom_px_per_m() >= MIN_ZOOM_PX_PER_M
    finally:
        dock.close()


def test_zoom_from_wheel_keeps_content_under_cursor_stable(qt_app):
    dock = _show_zoomed_timeline(qt_app)
    try:
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


def test_zoom_from_wheel_anchors_empty_time_beyond_path_end(qt_app):
    dock = TimelineDock(
        Path(path_elements=[TranslationTarget(0.0, 0.0), TranslationTarget(2.0, 0.0)])
    )
    try:
        dock.resize(900, 240)
        dock.show()
        qt_app.processEvents()
        dock._sync_canvas_size()
        dock._set_zoom_px_per_m(MIN_ZOOM_PX_PER_M)
        qt_app.processEvents()

        hbar = dock._track_scroll.horizontalScrollBar()
        hbar.setValue(0)
        viewport_x = 650.0
        before_zoom = float(dock._track_canvas._zoom_px_per_m)
        before_s = (hbar.value() + viewport_x - dock._track_canvas._track_left()) / before_zoom
        assert before_s > dock._projection.display_s_m

        dock._zoom_from_wheel(120, viewport_x, dock._track_scroll.viewport())
        qt_app.processEvents()

        after_zoom = float(dock._track_canvas._zoom_px_per_m)
        after_s = (hbar.value() + viewport_x - dock._track_canvas._track_left()) / after_zoom
        assert after_zoom > before_zoom
        assert abs(after_s - before_s) < 0.2
    finally:
        dock.close()


def test_horizontal_wheel_pans_timeline_without_zooming(qt_app):
    dock = _show_zoomed_timeline(qt_app)
    try:
        hbar = dock._track_scroll.horizontalScrollBar()
        hbar.setValue(240)
        assert hbar.maximum() > 258
        before_scroll = hbar.value()
        before_zoom = dock._track_canvas._zoom_px_per_m

        event = _WheelEventStub(pixel_x=-18, pixel_y=0)

        handled = dock.eventFilter(dock._track_scroll.viewport(), event)

        assert handled
        assert event.accepted
        assert hbar.value() == before_scroll + 18
        assert dock._track_canvas._zoom_px_per_m == before_zoom
    finally:
        dock.close()


def test_slow_horizontal_wheel_with_vertical_noise_does_not_zoom(qt_app):
    dock = _show_zoomed_timeline(qt_app)
    try:
        hbar = dock._track_scroll.horizontalScrollBar()
        hbar.setValue(240)
        assert hbar.maximum() > 252
        before_scroll = hbar.value()
        before_zoom = dock._track_canvas._zoom_px_per_m

        event = _WheelEventStub(pixel_x=-12, pixel_y=3)

        handled = dock.eventFilter(dock._track_scroll.viewport(), event)

        assert handled
        assert event.accepted
        assert hbar.value() == before_scroll + 12
        assert dock._track_canvas._zoom_px_per_m == before_zoom
    finally:
        dock.close()


def test_vertical_wheel_with_horizontal_noise_still_zooms(qt_app):
    dock = _show_zoomed_timeline(qt_app)
    try:
        before_zoom = dock._track_canvas._zoom_px_per_m

        event = _WheelEventStub(pixel_x=3, pixel_y=24)

        handled = dock.eventFilter(dock._track_scroll.viewport(), event)

        assert handled
        assert event.accepted
        assert dock._track_canvas._zoom_px_per_m > before_zoom
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
