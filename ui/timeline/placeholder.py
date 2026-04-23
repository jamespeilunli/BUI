# mypy: ignore-errors
"""Timeline dock for the redesign rollout."""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QRectF, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from models.path_model import (
    EventTrigger,
    Path,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from models.simulation import simulate_path
from ui.canvas.constants import SIMULATION_UPDATE_INTERVAL_MS
from ui.qt_compat import Qt, QSizePolicy
from ui.sidebar.utils import RANGED_CONSTRAINT_KEYS, SPINNER_METADATA, SPINNER_UNITS
from ui.sidebar.utils.ranged_constraint_ui import get_constraint_domain_elements


HEADER_WIDTH = 156
TRACK_PADDING_X = 16
TOP_PADDING = 14
BOTTOM_PADDING = 16
RULER_HEIGHT = 28
ROW_HEIGHT = 42
ROW_GAP = 8
MIN_ZOOM_PX_PER_M = 24
MAX_ZOOM_PX_PER_M = 240
DEFAULT_ZOOM_PX_PER_M = 72
PLAYBACK_STEP_S = SIMULATION_UPDATE_INTERVAL_MS / 1000.0


@dataclass
class TimelineMarker:
    s_m: float
    label: str
    kind: str
    color: str
    path_index: int | None = None
    source_x_m: float | None = None
    source_y_m: float | None = None


@dataclass
class TimelineSpan:
    start_s_m: float
    end_s_m: float
    label: str
    color: str
    lane: int = 0
    constraint_key: str | None = None
    start_ordinal: int | None = None
    end_ordinal: int | None = None


@dataclass
class TimelineRow:
    title: str
    empty_text: str
    markers: list[TimelineMarker] = field(default_factory=list)
    spans: list[TimelineSpan] = field(default_factory=list)
    lane_count: int = 1
    constraint_key: str | None = None


@dataclass
class TimelineProjection:
    total_s_m: float
    display_s_m: float
    summary_text: str
    rows: list[TimelineRow]
    axis_label: str = "Path Progress"
    axis_unit: str = "m"


@dataclass
class TimelineSelection:
    kind: str
    path_index: int | None = None
    constraint_key: str | None = None
    start_ordinal: int | None = None
    end_ordinal: int | None = None


@dataclass
class _SimTimeIndex:
    sample_s: list[float]
    sample_t: list[float]
    sample_x: list[float]
    sample_y: list[float]


def _row_height_for(row: TimelineRow) -> int:
    if not row.spans:
        return ROW_HEIGHT
    lanes = max(1, int(row.lane_count))
    # Keep single-lane rows compact, but expand for stacked overlaps.
    return max(ROW_HEIGHT, 14 + lanes * 18 + max(0, lanes - 1) * 4)


def _rows_total_height(rows: list[TimelineRow]) -> int:
    if not rows:
        return ROW_HEIGHT
    return sum(_row_height_for(row) for row in rows) + max(0, len(rows) - 1) * ROW_GAP


class _TimelineCanvasBase(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._projection = TimelineProjection(0.0, 6.0, "", [])
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(220)

    def set_projection(self, projection: TimelineProjection) -> None:
        self._projection = projection
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        height = TOP_PADDING + RULER_HEIGHT + _rows_total_height(self._projection.rows)
        height += BOTTOM_PADDING
        return QSize(HEADER_WIDTH, height)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_background(painter)

        if not self._projection.rows:
            painter.end()
            return

        self._draw_ruler(painter)
        row_top = TOP_PADDING + RULER_HEIGHT
        for index, row in enumerate(self._projection.rows):
            row_h = _row_height_for(row)
            self._draw_row(painter, row, row_top, row_h, index)
            row_top += row_h + ROW_GAP

        painter.end()

    def _paint_background(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor("#141414"))

    def _draw_ruler(self, painter: QPainter) -> None:
        raise NotImplementedError

    def _draw_row(
        self, painter: QPainter, row: TimelineRow, y: int, row_height: int, index: int
    ) -> None:
        raise NotImplementedError


class _TimelineRailCanvas(_TimelineCanvasBase):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)

    def _draw_ruler(self, painter: QPainter) -> None:
        top = TOP_PADDING
        painter.fillRect(QRectF(0, top, HEADER_WIDTH, RULER_HEIGHT), QColor("#171717"))

        painter.setPen(QColor("#6d737c"))
        painter.drawText(14, top + 18, self._projection.axis_label)

    def _draw_row(
        self, painter: QPainter, row: TimelineRow, y: int, row_height: int, index: int
    ) -> None:
        rail_rect = QRectF(0, y, HEADER_WIDTH, row_height)
        painter.fillRect(rail_rect, QColor("#171717"))

        painter.setPen(QColor("#30353b"))
        painter.drawLine(HEADER_WIDTH - 1, y, HEADER_WIDTH - 1, y + row_height)
        painter.drawLine(0, y + row_height - 1, HEADER_WIDTH, y + row_height - 1)

        painter.setPen(QColor("#dce1e6"))
        fm = painter.fontMetrics()
        text_y = int(y + (row_height + fm.ascent() - fm.descent()) / 2.0)
        painter.drawText(14, text_y, row.title)


class _TimelineTrackCanvas(_TimelineCanvasBase):
    scrubRequested = Signal(float)
    playPauseToggleRequested = Signal()
    zoomInRequested = Signal()
    zoomOutRequested = Signal()
    pathItemClicked = Signal(int)
    constraintSpanClicked = Signal(str, int, int)
    emptyAreaClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._zoom_px_per_m = DEFAULT_ZOOM_PX_PER_M
        self._playhead_s_m = 0.0
        self._is_playing = False
        self._selection: TimelineSelection | None = None
        self._scrub_active = False
        self._scrub_moved = False
        self._pressed_on_playhead = False
        self._pressed_hit: tuple[str, object] | None = None
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_zoom_px_per_m(self, zoom_px_per_m: int) -> None:
        self._zoom_px_per_m = max(MIN_ZOOM_PX_PER_M, min(MAX_ZOOM_PX_PER_M, int(zoom_px_per_m)))
        self.updateGeometry()
        self.update()

    def set_playhead(self, s_m: float, playing: bool) -> None:
        max_s = max(0.0, float(self._projection.display_s_m))
        self._playhead_s_m = max(0.0, min(float(s_m), max_s))
        self._is_playing = bool(playing)
        self.update()

    def set_selection(self, selection: TimelineSelection | None) -> None:
        self._selection = selection
        self.update()

    def sizeHint(self) -> QSize:
        track_width = int(round(max(self._projection.display_s_m, 0.0) * self._zoom_px_per_m))
        base = super().sizeHint()
        return QSize(TRACK_PADDING_X * 2 + max(1, track_width), base.height())

    def _track_left(self) -> float:
        return float(TRACK_PADDING_X)

    def _track_right(self) -> float:
        return float(self.width() - TRACK_PADDING_X)

    def _track_width(self) -> float:
        return max(1.0, self._track_right() - self._track_left())

    def _x_for_s(self, s_m: float) -> float:
        s_m = max(0.0, min(float(s_m), self._projection.display_s_m))
        return self._track_left() + s_m * self._zoom_px_per_m

    def _draw_ruler(self, painter: QPainter) -> None:
        top = TOP_PADDING
        bottom = TOP_PADDING + RULER_HEIGHT
        painter.fillRect(QRectF(0, top, self.width(), RULER_HEIGHT), QColor("#181818"))

        base_y = bottom - 1
        painter.setPen(QPen(QColor("#3b4148"), 1))
        painter.drawLine(int(self._track_left()), base_y, int(self._track_right()), base_y)

        step_m = _nice_ruler_step(self._zoom_px_per_m)
        metrics = painter.fontMetrics()
        label_y = top + 17
        tick_top = bottom - 10
        tick_bottom = bottom - 1

        tick = 0.0
        while tick <= self._projection.display_s_m + 1e-9:
            x = self._x_for_s(tick)
            painter.drawLine(int(x), tick_top, int(x), tick_bottom)
            label = _format_axis_label(tick, step_m, self._projection.axis_unit)
            label_width = metrics.horizontalAdvance(label)
            painter.setPen(QColor("#9aa3ad"))
            painter.drawText(int(x - label_width / 2), label_y, label)
            painter.setPen(QPen(QColor("#3b4148"), 1))
            tick += step_m

    def _draw_row(
        self, painter: QPainter, row: TimelineRow, y: int, row_height: int, index: int
    ) -> None:
        row_rect = QRectF(0, y, self.width(), row_height)
        track_rect = QRectF(self._track_left(), y + 7, self._track_width(), max(10.0, row_height - 14))

        painter.fillRect(
            row_rect,
            QColor("#161a1d") if index % 2 == 0 else QColor("#13171a"),
        )

        painter.setPen(QColor("#30353b"))
        painter.drawLine(0, y + row_height - 1, self.width(), y + row_height - 1)

        if row.spans:
            self._draw_spans(painter, row, track_rect)
            return
        if row.markers:
            self._draw_markers(painter, row, track_rect)
            return

        painter.setPen(QColor("#6f7882"))
        painter.drawText(
            int(track_rect.left()),
            int(track_rect.center().y() + 5),
            row.empty_text,
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._projection.rows:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_playhead(painter)
        painter.end()

    def _draw_markers(self, painter: QPainter, row: TimelineRow, track_rect: QRectF) -> None:
        center_y = track_rect.center().y()
        painter.setPen(QPen(QColor("#3b4148"), 1))
        painter.drawLine(int(track_rect.left()), int(center_y), int(track_rect.right()), int(center_y))

        last_label_right = -10_000.0
        metrics = painter.fontMetrics()

        for marker in row.markers:
            x = self._x_for_s(marker.s_m)
            color = QColor(marker.color)
            painter.setPen(QPen(color, 1.4))
            painter.drawLine(int(x), int(track_rect.top()), int(x), int(track_rect.bottom()))
            if self._is_marker_selected(marker):
                painter.save()
                painter.setPen(QPen(QColor("#f5f7fa"), 1.4))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QRectF(x - 9.0, center_y - 9.0, 18.0, 18.0))
                painter.restore()
            self._draw_marker_shape(painter, marker.kind, x, center_y, color)

            label = marker.label.strip()
            if not label:
                continue
            label_width = metrics.horizontalAdvance(label)
            label_x = x + 6
            if label_x <= last_label_right + 8:
                continue
            painter.setPen(QColor("#cfd6de"))
            painter.drawText(int(label_x), int(track_rect.top()) + 11, label)
            last_label_right = label_x + label_width

    def _draw_marker_shape(
        self, painter: QPainter, kind: str, x: float, center_y: float, color: QColor
    ) -> None:
        painter.save()
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(color)
        if kind == "waypoint":
            diamond = QPolygonF(
                [
                    _qpointf(x, center_y - 6),
                    _qpointf(x + 6, center_y),
                    _qpointf(x, center_y + 6),
                    _qpointf(x - 6, center_y),
                ]
            )
            painter.drawPolygon(diamond)
        elif kind == "rotation":
            tri = QPolygonF(
                [
                    _qpointf(x, center_y - 7),
                    _qpointf(x + 6, center_y + 5),
                    _qpointf(x - 6, center_y + 5),
                ]
            )
            painter.drawPolygon(tri)
        elif kind == "end":
            painter.drawRect(QRectF(x - 4, center_y - 4, 8, 8))
        else:
            painter.drawEllipse(QRectF(x - 4.5, center_y - 4.5, 9, 9))
        painter.restore()

    def _draw_spans(self, painter: QPainter, row: TimelineRow, track_rect: QRectF) -> None:
        lane_count = max(1, int(row.lane_count))
        lane_gap = 4.0
        total_lane_gap = lane_gap * max(0, lane_count - 1)
        available_h = max(10.0, track_rect.height())
        lane_h = max(10.0, (available_h - total_lane_gap) / lane_count)
        lanes_block_h = lane_count * lane_h + total_lane_gap
        lanes_top = track_rect.top() + (available_h - lanes_block_h) / 2.0
        metrics = painter.fontMetrics()

        painter.setPen(QPen(QColor("#2f3740"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(
            QRectF(
                track_rect.left(),
                lanes_top - 2.0,
                track_rect.width(),
                lanes_block_h + 4.0,
            )
        )

        for span in row.spans:
            x0 = self._x_for_s(span.start_s_m)
            x1 = self._x_for_s(span.end_s_m)
            if x1 < x0:
                x0, x1 = x1, x0
            center_x = (x0 + x1) / 2.0
            width = max(8.0, x1 - x0)
            left_x = center_x - (width / 2.0)
            lane_index = max(0, int(getattr(span, "lane", 0)))
            bar_y = lanes_top + lane_index * (lane_h + lane_gap)
            rect = QRectF(left_x, bar_y, width, lane_h)
            color = QColor(span.color)
            fill = QColor(color)
            fill.setAlpha(220)
            if self._is_span_selected(span):
                fill = QColor(color.lighter(118))
                fill.setAlpha(245)

            pen_color = color.lighter(120)
            pen_width = 1.1
            if self._is_span_selected(span):
                pen_color = QColor("#f4f7fa")
                pen_width = 1.5
            painter.setPen(QPen(pen_color, pen_width))
            painter.setBrush(fill)
            painter.drawRect(rect)

            text = metrics.elidedText(span.label, Qt.ElideRight, int(max(0.0, width - 10.0)))
            if text:
                painter.setPen(QColor("#f4f7fa"))
                painter.drawText(
                    QRectF(rect.left() + 5, rect.top(), rect.width() - 10, rect.height()),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    text,
                )

    def _draw_playhead(self, painter: QPainter) -> None:
        x = self._x_for_s(self._playhead_s_m)
        line_color = QColor("#55d38a") if self._is_playing else QColor("#e6edf5")
        line_pen = QPen(line_color, 2)
        painter.setPen(line_pen)
        painter.drawLine(
            int(round(x)),
            TOP_PADDING,
            int(round(x)),
            self.height() - BOTTOM_PADDING,
        )

        head_y = TOP_PADDING + 3
        triangle = QPolygonF(
            [
                _qpointf(x - 7, head_y),
                _qpointf(x + 7, head_y),
                _qpointf(x, head_y + 10),
            ]
        )
        painter.setPen(QPen(line_color, 1.2))
        painter.setBrush(line_color)
        painter.drawPolygon(triangle)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(Qt.MouseFocusReason)
        self._pressed_hit = self._hit_test(event.position().x(), event.position().y())
        self._scrub_active = bool(
            self._pressed_hit is None and self._y_in_ruler(float(event.position().y()))
        )
        self._scrub_moved = False
        self._pressed_on_playhead = self._is_playhead_click(event)
        if self._scrub_active and not self._pressed_on_playhead:
            self._emit_scrub_for_event(event)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._scrub_active:
            self._scrub_moved = True
            self._emit_scrub_for_event(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._scrub_active or event.button() != Qt.LeftButton:
            if event.button() == Qt.LeftButton and not self._scrub_moved:
                self._activate_click_hit(event)
                event.accept()
                return
            return super().mouseReleaseEvent(event)

        if self._scrub_moved or not self._pressed_on_playhead:
            self._emit_scrub_for_event(event)
        should_toggle = self._pressed_on_playhead and self._is_playhead_click(event) and not self._scrub_moved
        self._scrub_active = False
        self._scrub_moved = False
        self._pressed_on_playhead = False
        self._pressed_hit = None
        if should_toggle:
            self.playPauseToggleRequested.emit()
        event.accept()

    def _emit_scrub_for_event(self, event: QMouseEvent) -> None:
        self.scrubRequested.emit(self._s_for_x(float(event.position().x())))

    def _s_for_x(self, x: float) -> float:
        return max(
            0.0,
            min(
                (float(x) - self._track_left()) / max(1.0, float(self._zoom_px_per_m)),
                float(self._projection.display_s_m),
            ),
        )

    def _is_playhead_click(self, event: QMouseEvent) -> bool:
        x = float(event.position().x())
        y = float(event.position().y())
        playhead_x = self._x_for_s(self._playhead_s_m)
        return abs(x - playhead_x) <= 8.0 and y <= (TOP_PADDING + RULER_HEIGHT)

    def _activate_click_hit(self, event: QMouseEvent) -> None:
        hit = self._hit_test(event.position().x(), event.position().y())
        pressed_hit = self._pressed_hit
        self._pressed_hit = None
        self._scrub_moved = False
        self._pressed_on_playhead = False
        if hit is None or hit != pressed_hit:
            self.emptyAreaClicked.emit()
            return
        hit_kind, payload = hit
        if hit_kind == "marker":
            marker = payload
            if marker.path_index is not None:
                self.pathItemClicked.emit(int(marker.path_index))
            return
        if hit_kind == "span":
            span = payload
            if (
                span.constraint_key
                and span.start_ordinal is not None
                and span.end_ordinal is not None
            ):
                self.constraintSpanClicked.emit(
                    str(span.constraint_key),
                    int(span.start_ordinal),
                    int(span.end_ordinal),
                )
                return
        self.emptyAreaClicked.emit()

    def _hit_test(self, x: float, y: float) -> tuple[str, object] | None:
        if self._y_in_ruler(y):
            return None
        row_top = TOP_PADDING + RULER_HEIGHT
        for row in self._projection.rows:
            row_h = _row_height_for(row)
            if row_top <= y <= row_top + row_h:
                track_rect = QRectF(
                    self._track_left(),
                    row_top + 7,
                    self._track_width(),
                    max(10.0, row_h - 14),
                )
                if row.spans:
                    for span, rect in self._iter_span_rects(row, track_rect):
                        if rect.adjusted(-3.0, -2.0, 3.0, 2.0).contains(x, y):
                            return ("span", span)
                if row.markers:
                    center_y = track_rect.center().y()
                    for marker in row.markers:
                        marker_rect = QRectF(
                            self._x_for_s(marker.s_m) - 9.0,
                            center_y - 11.0,
                            18.0,
                            22.0,
                        )
                        if marker_rect.contains(x, y):
                            return ("marker", marker)
                return None
            row_top += row_h + ROW_GAP
        return None

    def _iter_span_rects(self, row: TimelineRow, track_rect: QRectF):
        lane_count = max(1, int(row.lane_count))
        lane_gap = 4.0
        total_lane_gap = lane_gap * max(0, lane_count - 1)
        available_h = max(10.0, track_rect.height())
        lane_h = max(10.0, (available_h - total_lane_gap) / lane_count)
        lanes_block_h = lane_count * lane_h + total_lane_gap
        lanes_top = track_rect.top() + (available_h - lanes_block_h) / 2.0
        for span in row.spans:
            x0 = self._x_for_s(span.start_s_m)
            x1 = self._x_for_s(span.end_s_m)
            if x1 < x0:
                x0, x1 = x1, x0
            center_x = (x0 + x1) / 2.0
            width = max(8.0, x1 - x0)
            left_x = center_x - (width / 2.0)
            lane_index = max(0, int(getattr(span, "lane", 0)))
            bar_y = lanes_top + lane_index * (lane_h + lane_gap)
            yield span, QRectF(left_x, bar_y, width, lane_h)

    def _y_in_ruler(self, y: float) -> bool:
        return TOP_PADDING <= y <= (TOP_PADDING + RULER_HEIGHT)

    def _is_marker_selected(self, marker: TimelineMarker) -> bool:
        return bool(
            self._selection
            and self._selection.kind == "path"
            and marker.path_index is not None
            and int(marker.path_index) == int(self._selection.path_index)
        )

    def _is_span_selected(self, span: TimelineSpan) -> bool:
        return bool(
            self._selection
            and self._selection.kind == "constraint"
            and span.constraint_key == self._selection.constraint_key
            and span.start_ordinal == self._selection.start_ordinal
            and span.end_ordinal == self._selection.end_ordinal
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            if key in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoomInRequested.emit()
                event.accept()
                return
            if key == Qt.Key_Minus:
                self.zoomOutRequested.emit()
                event.accept()
                return
        if key == Qt.Key_Space:
            self.playPauseToggleRequested.emit()
            event.accept()
            return
        if key == Qt.Key_Left:
            self.scrubRequested.emit(max(0.0, self._playhead_s_m - PLAYBACK_STEP_S))
            event.accept()
            return
        if key == Qt.Key_Right:
            self.scrubRequested.emit(
                min(float(self._projection.display_s_m), self._playhead_s_m + PLAYBACK_STEP_S)
            )
            event.accept()
            return
        super().keyPressEvent(event)


class TimelineDock(QFrame):
    """Timeline dock with editor-style playhead transport."""

    scrubRequested = Signal(float)
    playPauseToggled = Signal()
    pathItemSelected = Signal(int)
    constraintRangeSelected = Signal(str, int, int)
    selectionCleared = Signal()

    def __init__(self, path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._config: dict[str, object] = {}
        self._projection = TimelineProjection(0.0, 6.0, "", [])
        self._selection: TimelineSelection | None = None
        self._current_time_s = 0.0
        self._total_time_s = 0.0
        self._is_playing = False
        self._play_pause_btn: QPushButton
        self._playback_label: QLabel
        self._summary_label: QLabel
        self._zoom_label: QLabel
        self._zoom_slider: QSlider
        self._rail_scroll: QScrollArea
        self._track_scroll: QScrollArea
        self._rail_canvas: _TimelineRailCanvas
        self._track_canvas: _TimelineTrackCanvas
        self._setup_ui()
        self.set_path(path or Path(), {})

    def _setup_ui(self) -> None:
        self.setObjectName("timelineDock")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(220)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(
            """
            QFrame#timelineDock {
                background: #141414;
                border-top: 1px solid #2d2d2d;
            }
            QWidget#timelineToolbar {
                background: #191919;
                border-bottom: 1px solid #2b2b2b;
            }
            QLabel#timelineToolbarTitle {
                color: #f0f0f0;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#timelineToolbarMeta {
                color: #97a0aa;
                font-size: 11px;
            }
            QPushButton[timelineControl='true'] {
                background: #272727;
                color: #e9eef3;
                border: 1px solid #393939;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton[timelineControl='true']:hover {
                background: #313131;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #2a2a2a;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                margin: -5px 0;
                border-radius: 6px;
                background: #d8dee6;
            }
            QLabel#timelineZoomLabel,
            QLabel#timelinePlaybackLabel {
                color: #bcc4cc;
                font-size: 11px;
            }
            QScrollArea {
                border: none;
                background: #141414;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("timelineToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 10, 14, 10)
        toolbar_layout.setSpacing(10)

        title = QLabel("Timeline")
        title.setObjectName("timelineToolbarTitle")
        toolbar_layout.addWidget(title)

        self._summary_label = QLabel("")
        self._summary_label.setObjectName("timelineToolbarMeta")
        self._summary_label.setWordWrap(False)
        toolbar_layout.addWidget(self._summary_label, 1)

        self._playback_label = QLabel("Paused at 0.00 / 0.00 s")
        self._playback_label.setObjectName("timelinePlaybackLabel")
        toolbar_layout.addWidget(self._playback_label)

        self._play_pause_btn = QPushButton("Play")
        self._play_pause_btn.setProperty("timelineControl", "true")
        self._play_pause_btn.setEnabled(False)
        self._play_pause_btn.clicked.connect(self._on_play_pause_toggled)
        toolbar_layout.addWidget(self._play_pause_btn)

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setProperty("timelineControl", "true")
        zoom_out_btn.clicked.connect(lambda: self._adjust_zoom(-10))
        toolbar_layout.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setProperty("timelineControl", "true")
        zoom_in_btn.clicked.connect(lambda: self._adjust_zoom(10))
        toolbar_layout.addWidget(zoom_in_btn)

        fit_btn = QPushButton("Fit")
        fit_btn.setProperty("timelineControl", "true")
        fit_btn.clicked.connect(self.fit_to_all)
        toolbar_layout.addWidget(fit_btn)

        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(MIN_ZOOM_PX_PER_M, MAX_ZOOM_PX_PER_M)
        self._zoom_slider.setValue(DEFAULT_ZOOM_PX_PER_M)
        self._zoom_slider.setFixedWidth(140)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar_layout.addWidget(self._zoom_slider)

        self._zoom_label = QLabel("")
        self._zoom_label.setObjectName("timelineZoomLabel")
        toolbar_layout.addWidget(self._zoom_label)

        outer.addWidget(toolbar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._rail_scroll = QScrollArea()
        self._rail_scroll.setWidgetResizable(False)
        self._rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rail_scroll.setFixedWidth(HEADER_WIDTH)
        self._rail_scroll.viewport().installEventFilter(self)

        self._rail_canvas = _TimelineRailCanvas()
        self._rail_scroll.setWidget(self._rail_canvas)
        body_layout.addWidget(self._rail_scroll)

        self._track_scroll = QScrollArea()
        self._track_scroll.setWidgetResizable(False)
        self._track_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._track_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._track_scroll.viewport().installEventFilter(self)

        self._track_canvas = _TimelineTrackCanvas()
        self._track_canvas.scrubRequested.connect(self._on_scrub_requested)
        self._track_canvas.playPauseToggleRequested.connect(self._on_play_pause_toggled)
        self._track_canvas.zoomInRequested.connect(lambda: self._adjust_zoom(10))
        self._track_canvas.zoomOutRequested.connect(lambda: self._adjust_zoom(-10))
        self._track_canvas.pathItemClicked.connect(self.select_path_index)
        self._track_canvas.pathItemClicked.connect(self.pathItemSelected)
        self._track_canvas.constraintSpanClicked.connect(self.select_constraint_range)
        self._track_canvas.constraintSpanClicked.connect(self.constraintRangeSelected)
        self._track_canvas.emptyAreaClicked.connect(self._on_empty_area_clicked)
        self._track_scroll.setWidget(self._track_canvas)
        self._track_scroll.setFocusProxy(self._track_canvas)
        body_layout.addWidget(self._track_scroll, 1)
        outer.addWidget(body, 1)

        self._track_scroll.verticalScrollBar().valueChanged.connect(
            self._rail_scroll.verticalScrollBar().setValue
        )

        self._on_zoom_changed(self._zoom_slider.value())

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Resize and watched in {
            self._track_scroll.viewport(),
            self._rail_scroll.viewport(),
        }:
            self._sync_canvas_size()
        if watched is self._rail_scroll.viewport() and event.type() == QEvent.Wheel:
            self._forward_vertical_wheel(event)
            return True
        return super().eventFilter(watched, event)

    def set_path(self, path: Path | None, config: dict[str, object] | None = None) -> None:
        had_meaningful_projection = float(getattr(self._projection, "total_s_m", 0.0)) > 1e-9
        self._path = path or Path()
        self._config = dict(config or {})
        self._projection = _build_projection(self._path, self._config, use_sim_time=True)
        self._summary_label.setText(self._projection.summary_text)
        self._rail_canvas.set_projection(self._projection)
        self._track_canvas.set_projection(self._projection)
        self._restore_selection()
        self._track_canvas.set_playhead(self._current_time_s, self._is_playing)
        self._sync_canvas_size()
        if not had_meaningful_projection and self._projection.total_s_m > 1e-9:
            QTimer.singleShot(0, self.fit_to_all)
        else:
            self._ensure_playhead_visible()

    def fit_to_all(self) -> None:
        display_s_m = max(self._projection.display_s_m, 0.0)
        if display_s_m <= 0.0:
            return
        viewport_width = max(1, self._track_scroll.viewport().width() - TRACK_PADDING_X * 2)
        zoom = int(round(viewport_width / display_s_m))
        zoom = max(MIN_ZOOM_PX_PER_M, min(MAX_ZOOM_PX_PER_M, zoom))
        self._zoom_slider.setValue(zoom)

    def _adjust_zoom(self, delta: int) -> None:
        self._zoom_slider.setValue(self._zoom_slider.value() + int(delta))

    def set_playback_state(
        self,
        current_time_s: float,
        total_time_s: float,
        is_playing: bool,
        enabled: bool,
    ) -> None:
        self._current_time_s = max(0.0, float(current_time_s))
        self._total_time_s = max(0.0, float(total_time_s))
        self._is_playing = bool(is_playing and enabled)
        self._track_canvas.set_playhead(self._current_time_s, self._is_playing)
        state_text = "Playing" if self._is_playing else "Paused"
        if not enabled or self._total_time_s <= 1e-9:
            state_text = "No simulation"
        self._play_pause_btn.setEnabled(bool(enabled and self._total_time_s > 1e-9))
        self._play_pause_btn.setText("Pause" if self._is_playing else "Play")
        self._playback_label.setText(
            f"{state_text} at {self._current_time_s:.2f} / {self._total_time_s:.2f} s"
        )
        self._ensure_playhead_visible()

    def _on_zoom_changed(self, value: int) -> None:
        hbar = self._track_scroll.horizontalScrollBar()
        playhead_x_before = TRACK_PADDING_X + self._current_time_s * float(
            self._track_canvas._zoom_px_per_m
        )
        playhead_offset_in_view = playhead_x_before - float(hbar.value())

        self._zoom_label.setText(f"{int(value)} px/m")
        self._track_canvas.set_zoom_px_per_m(value)
        self._sync_canvas_size()

        playhead_x_after = TRACK_PADDING_X + self._current_time_s * float(value)
        hbar.setValue(int(round(playhead_x_after - playhead_offset_in_view)))

    def _sync_canvas_size(self) -> None:
        rail_hint = self._rail_canvas.sizeHint()
        track_hint = self._track_canvas.sizeHint()
        track_viewport_width = max(0, self._track_scroll.viewport().width())
        viewport_height = max(0, self._track_scroll.viewport().height())
        rail_height = max(rail_hint.height(), viewport_height)
        track_width = max(track_hint.width(), track_viewport_width)
        track_height = max(track_hint.height(), viewport_height)

        self._rail_canvas.resize(HEADER_WIDTH, rail_height)
        self._rail_canvas.setMinimumSize(HEADER_WIDTH, rail_hint.height())
        self._track_canvas.resize(track_width, track_height)
        self._track_canvas.setMinimumSize(track_width, track_hint.height())
        self._rail_scroll.verticalScrollBar().setPageStep(
            self._track_scroll.verticalScrollBar().pageStep()
        )
        self._rail_scroll.verticalScrollBar().setRange(
            self._track_scroll.verticalScrollBar().minimum(),
            self._track_scroll.verticalScrollBar().maximum(),
        )
        self._rail_scroll.verticalScrollBar().setValue(self._track_scroll.verticalScrollBar().value())

    def _on_scrub_requested(self, time_s: float) -> None:
        self.scrubRequested.emit(float(time_s))

    def _on_play_pause_toggled(self) -> None:
        self.playPauseToggled.emit()

    def select_path_index(self, index: int | None) -> None:
        if index is None:
            self.clear_selection()
            return
        selection = TimelineSelection(kind="path", path_index=int(index))
        if self._selection == selection:
            return
        self._selection = selection
        self._track_canvas.set_selection(self._selection)

    def select_constraint_range(
        self,
        key: str | None,
        start_ordinal: int | None,
        end_ordinal: int | None,
    ) -> None:
        if not key or start_ordinal is None or end_ordinal is None:
            self.clear_selection()
            return
        selection = TimelineSelection(
            kind="constraint",
            constraint_key=str(key),
            start_ordinal=int(start_ordinal),
            end_ordinal=int(end_ordinal),
        )
        if self._selection == selection:
            return
        self._selection = selection
        self._track_canvas.set_selection(self._selection)

    def clear_selection(self) -> None:
        if self._selection is None:
            return
        self._selection = None
        self._track_canvas.set_selection(None)

    def clear_constraint_selection(self) -> None:
        if self._selection is None or self._selection.kind != "constraint":
            return
        self.clear_selection()

    def _restore_selection(self) -> None:
        if self._selection is None:
            self._track_canvas.set_selection(None)
            return
        if self._selection.kind == "path":
            index = self._selection.path_index
            if index is None or index < 0 or index >= len(getattr(self._path, "path_elements", []) or []):
                self._selection = None
        elif self._selection.kind == "constraint":
            key = self._selection.constraint_key
            start = self._selection.start_ordinal
            end = self._selection.end_ordinal
            found = False
            for rc in getattr(self._path, "ranged_constraints", []) or []:
                if (
                    getattr(rc, "key", None) == key
                    and int(getattr(rc, "start_ordinal", -1)) == int(start)
                    and int(getattr(rc, "end_ordinal", -1)) == int(end)
                ):
                    found = True
                    break
            if not found:
                self._selection = None
        self._track_canvas.set_selection(self._selection)

    def _on_empty_area_clicked(self) -> None:
        self.clear_selection()
        self.selectionCleared.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            if key in (Qt.Key_Plus, Qt.Key_Equal):
                self._adjust_zoom(10)
                event.accept()
                return
            if key == Qt.Key_Minus:
                self._adjust_zoom(-10)
                event.accept()
                return
        if key == Qt.Key_Space:
            self._on_play_pause_toggled()
            event.accept()
            return
        if key == Qt.Key_Left:
            self._step_playhead(-1)
            event.accept()
            return
        if key == Qt.Key_Right:
            self._step_playhead(1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _step_playhead(self, direction: int) -> None:
        if self._total_time_s <= 1e-9:
            return
        target_time_s = self._current_time_s + (PLAYBACK_STEP_S * int(direction))
        target_time_s = max(0.0, min(float(target_time_s), self._total_time_s))
        self.scrubRequested.emit(target_time_s)

    def _ensure_playhead_visible(self) -> None:
        hbar = self._track_scroll.horizontalScrollBar()
        viewport_width = max(1, self._track_scroll.viewport().width())
        playhead_x = TRACK_PADDING_X + self._current_time_s * float(self._track_canvas._zoom_px_per_m)
        visible_left = float(hbar.value())
        visible_right = visible_left + float(viewport_width)
        margin = min(96.0, viewport_width * 0.25)

        if playhead_x < visible_left + margin:
            hbar.setValue(int(round(playhead_x - margin)))
        elif playhead_x > visible_right - margin:
            hbar.setValue(int(round(playhead_x - viewport_width + margin)))

    def _forward_vertical_wheel(self, event) -> None:
        scrollbar = self._track_scroll.verticalScrollBar()
        delta_y = 0
        try:
            delta_y = int(event.angleDelta().y())
        except Exception:
            delta_y = 0
        if delta_y == 0:
            return
        step = scrollbar.singleStep() or 20
        direction = -1 if delta_y > 0 else 1
        scrollbar.setValue(scrollbar.value() + direction * step * 3)


TimelinePlaceholder = TimelineDock


def _build_projection(
    path: Path,
    config: dict[str, object] | None = None,
    *,
    use_sim_time: bool = False,
) -> TimelineProjection:
    path = path or Path()
    path_elements = list(getattr(path, "path_elements", []) or [])

    anchor_data = _build_anchor_distances(path_elements)
    anchor_s_by_path_index = anchor_data["anchor_s_by_path_index"]
    total_s_m = float(anchor_data["total_s_m"])

    structure_markers: list[TimelineMarker] = []
    trigger_markers: list[TimelineMarker] = []
    structure_count = 0
    rotation_count = 0
    event_count = 0
    translation_count = 0
    waypoint_count = 0

    if anchor_data["anchor_indices"]:
        first_anchor = path_elements[anchor_data["anchor_indices"][0]]
        structure_markers.append(
            TimelineMarker(
                0.0,
                "Start",
                "start",
                "#5ac878",
                path_index=anchor_data["anchor_indices"][0],
                source_x_m=_element_x(first_anchor),
                source_y_m=_element_y(first_anchor),
            )
        )
        if len(anchor_data["anchor_indices"]) > 1 and total_s_m > 0.0:
            last_anchor = path_elements[anchor_data["anchor_indices"][-1]]
            structure_markers.append(
                TimelineMarker(
                    total_s_m,
                    "End",
                    "end",
                    "#d96a6a",
                    path_index=anchor_data["anchor_indices"][-1],
                    source_x_m=_element_x(last_anchor),
                    source_y_m=_element_y(last_anchor),
                )
            )

    for index, element in enumerate(path_elements):
        s_m = _element_global_s(index, element, path_elements, anchor_s_by_path_index)
        if isinstance(element, TranslationTarget):
            translation_count += 1
            structure_count += 1
            structure_markers.append(
                TimelineMarker(
                    s_m,
                    f"T{translation_count}",
                    "translation",
                    "#60b7ff",
                    path_index=index,
                    source_x_m=_element_x(element),
                    source_y_m=_element_y(element),
                )
            )
        elif isinstance(element, Waypoint):
            waypoint_count += 1
            structure_count += 1
            structure_markers.append(
                TimelineMarker(
                    s_m,
                    f"W{waypoint_count}",
                    "waypoint",
                    "#9c8cff",
                    path_index=index,
                    source_x_m=_element_x(element),
                    source_y_m=_element_y(element),
                )
            )
        elif isinstance(element, RotationTarget):
            rotation_count += 1
            structure_markers.append(
                TimelineMarker(
                    s_m,
                    f"R{rotation_count}",
                    "rotation",
                    "#ff9c5a",
                    path_index=index,
                )
            )
        elif isinstance(element, EventTrigger):
            event_count += 1
            lib_key = str(getattr(element, "lib_key", "") or "").strip()
            trigger_markers.append(
                TimelineMarker(
                    s_m,
                    lib_key or f"E{event_count}",
                    "event",
                    "#ffd166",
                    path_index=index,
                )
            )

    rows = [
        TimelineRow(
            title="Structure",
            empty_text="Add translation targets or waypoints to build the path.",
            markers=structure_markers,
        ),
        TimelineRow(
            title="Triggers",
            empty_text="No triggers yet.",
            markers=trigger_markers,
        ),
    ]

    for key in RANGED_CONSTRAINT_KEYS:
        spans = _build_constraint_spans(path, key, path_elements, anchor_s_by_path_index)
        lane_count = _lane_count_for_spans(spans)
        rows.append(
            TimelineRow(
                title=_plain_label(str(SPINNER_METADATA.get(key, {}).get("label", key))),
                empty_text="No ranges yet.",
                spans=spans,
                lane_count=lane_count,
                constraint_key=key,
            )
        )

    display_s_m = max(total_s_m, 1.0 if structure_markers else 6.0)
    summary_text = (
        f"{structure_count} structure items, "
        f"{rotation_count} rotation targets, "
        f"{event_count} triggers, "
        f"{len(getattr(path, 'ranged_constraints', []) or [])} ranged constraints"
    )
    projection = TimelineProjection(
        total_s_m=total_s_m,
        display_s_m=display_s_m,
        summary_text=summary_text,
        rows=rows,
        axis_label="Estimated Time",
        axis_unit="s",
    )
    _map_projection_distance_to_time(
        projection,
        path=path,
        config=config or {},
        use_sim_time=use_sim_time,
    )
    return projection


def _build_anchor_distances(path_elements: list[object]) -> dict[str, object]:
    anchors: list[tuple[int, float, float]] = []
    for index, element in enumerate(path_elements):
        if isinstance(element, TranslationTarget):
            anchors.append((index, float(element.x_meters), float(element.y_meters)))
        elif isinstance(element, Waypoint):
            anchors.append(
                (
                    index,
                    float(element.translation_target.x_meters),
                    float(element.translation_target.y_meters),
                )
            )

    if not anchors:
        return {"anchor_indices": [], "anchor_s_by_path_index": {}, "total_s_m": 0.0}

    if len(anchors) == 1:
        return {
            "anchor_indices": [anchors[0][0]],
            "anchor_s_by_path_index": {anchors[0][0]: 0.0},
            "total_s_m": 0.0,
        }

    anchor_s_by_path_index: dict[int, float] = {anchors[0][0]: 0.0}
    cumulative = 0.0

    for i in range(len(anchors) - 1):
        idx_a, ax, ay = anchors[i]
        idx_b, bx, by = anchors[i + 1]
        cumulative += math.hypot(bx - ax, by - ay)
        anchor_s_by_path_index[idx_a] = anchor_s_by_path_index.get(idx_a, 0.0)
        anchor_s_by_path_index[idx_b] = cumulative

    return {
        "anchor_indices": [anchor[0] for anchor in anchors],
        "anchor_s_by_path_index": anchor_s_by_path_index,
        "total_s_m": cumulative,
    }


def _element_global_s(
    index: int,
    element: object,
    path_elements: list[object],
    anchor_s_by_path_index: dict[int, float],
) -> float:
    if isinstance(element, (TranslationTarget, Waypoint)):
        return float(anchor_s_by_path_index.get(index, 0.0))

    if isinstance(element, (RotationTarget, EventTrigger)):
        prev_anchor_index = None
        next_anchor_index = None
        for i in range(index - 1, -1, -1):
            if isinstance(path_elements[i], (TranslationTarget, Waypoint)):
                prev_anchor_index = i
                break
        for i in range(index + 1, len(path_elements)):
            if isinstance(path_elements[i], (TranslationTarget, Waypoint)):
                next_anchor_index = i
                break

        if prev_anchor_index is None and next_anchor_index is None:
            return 0.0
        if prev_anchor_index is None:
            return float(anchor_s_by_path_index.get(next_anchor_index, 0.0))
        if next_anchor_index is None:
            return float(anchor_s_by_path_index.get(prev_anchor_index, 0.0))

        s0 = float(anchor_s_by_path_index.get(prev_anchor_index, 0.0))
        s1 = float(anchor_s_by_path_index.get(next_anchor_index, s0))
        try:
            t_ratio = float(getattr(element, "t_ratio", 0.0))
        except Exception:
            t_ratio = 0.0
        t_ratio = max(0.0, min(1.0, t_ratio))
        return s0 + t_ratio * max(0.0, s1 - s0)

    return 0.0


def _build_constraint_spans(
    path: Path,
    key: str,
    path_elements: list[object],
    anchor_s_by_path_index: dict[int, float],
) -> list[TimelineSpan]:
    domain_elements = list(get_constraint_domain_elements(path, key))
    if not domain_elements:
        return []

    domain_positions: list[float] = []
    element_index_by_identity = {id(element): index for index, element in enumerate(path_elements)}
    for element in domain_elements:
        element_index = element_index_by_identity.get(id(element))
        if element_index is None:
            domain_positions.append(0.0)
            continue
        domain_positions.append(_element_global_s(element_index, element, path_elements, anchor_s_by_path_index))
    domain_boundaries = _build_domain_boundaries(domain_positions)

    spans: list[TimelineSpan] = []
    for rc in getattr(path, "ranged_constraints", []) or []:
        if getattr(rc, "key", "") != key:
            continue
        total = len(domain_positions)
        if total <= 0:
            continue
        start_ord = max(1, min(int(getattr(rc, "start_ordinal", 1)), total))
        end_ord = max(start_ord, min(int(getattr(rc, "end_ordinal", start_ord)), total))
        # Render spans as ordinal intervals (old SegmentBar-style), not point-to-point marks.
        # This ensures even single-ordinal ranges have visible extent in timeline space.
        start_s = domain_boundaries[start_ord - 1]
        end_s = domain_boundaries[end_ord]
        unit = str(SPINNER_UNITS.get(key, "") or "")
        label = f"{float(getattr(rc, 'value', 0.0)):g}{unit}"
        spans.append(
            TimelineSpan(
                start_s_m=float(start_s),
                end_s_m=float(end_s),
                label=label,
                color=_constraint_color(key),
                constraint_key=key,
                start_ordinal=start_ord,
                end_ordinal=end_ord,
            )
        )

    spans.sort(key=lambda span: (span.start_s_m, span.end_s_m))
    _assign_span_lanes(spans)
    return spans


def _build_constraint_spans_for_axis(
    path: Path,
    key: str,
    path_elements: list[object],
    *,
    mapper,
    sim_index: _SimTimeIndex | None,
) -> list[TimelineSpan]:
    domain_positions = _constraint_domain_axis_positions(
        path,
        key,
        path_elements,
        mapper=mapper,
        sim_index=sim_index,
    )
    return _build_constraint_spans_from_positions(path, key, domain_positions)


def _constraint_domain_axis_positions(
    path: Path,
    key: str,
    path_elements: list[object],
    *,
    mapper,
    sim_index: _SimTimeIndex | None,
) -> list[float]:
    domain_elements = list(get_constraint_domain_elements(path, key))
    if not domain_elements:
        return []

    anchor_data = _build_anchor_distances(path_elements)
    anchor_s_by_path_index = anchor_data["anchor_s_by_path_index"]
    element_index_by_identity = {id(element): index for index, element in enumerate(path_elements)}
    positions: list[float] = []

    for element in domain_elements:
        element_index = element_index_by_identity.get(id(element))
        source_s = 0.0
        if element_index is not None:
            source_s = _element_global_s(
                element_index,
                element,
                path_elements,
                anchor_s_by_path_index,
            )

        mapped = None
        if sim_index is not None:
            source_x = _element_x(element)
            source_y = _element_y(element)
            if source_x is not None and source_y is not None:
                mapped = _closest_time_for_point(
                    sim_index,
                    float(source_x),
                    float(source_y),
                    expected_s=source_s,
                )
        positions.append(float(mapped if mapped is not None else mapper(source_s)))

    return positions


def _build_constraint_spans_from_positions(
    path: Path,
    key: str,
    domain_positions: list[float],
) -> list[TimelineSpan]:
    if not domain_positions:
        return []

    spans: list[TimelineSpan] = []
    for rc in getattr(path, "ranged_constraints", []) or []:
        if getattr(rc, "key", "") != key:
            continue
        total = len(domain_positions)
        if total <= 0:
            continue
        start_ord = max(1, min(int(getattr(rc, "start_ordinal", 1)), total))
        end_ord = max(start_ord, min(int(getattr(rc, "end_ordinal", start_ord)), total))
        start_index = start_ord - 1
        end_index = end_ord - 1
        if start_index > 0:
            start_s = float(domain_positions[start_index - 1])
        else:
            start_s = float(domain_positions[start_index])
        end_s = float(domain_positions[end_index])
        unit = str(SPINNER_UNITS.get(key, "") or "")
        label = f"{float(getattr(rc, 'value', 0.0)):g}{unit}"
        spans.append(
            TimelineSpan(
                start_s_m=float(start_s),
                end_s_m=float(end_s),
                label=label,
                color=_constraint_color(key),
                constraint_key=key,
                start_ordinal=start_ord,
                end_ordinal=end_ord,
            )
        )

    spans.sort(key=lambda span: (span.start_s_m, span.end_s_m))
    _assign_span_lanes(spans)
    return spans


def _assign_span_lanes(spans: list[TimelineSpan]) -> None:
    lane_end_s: list[float] = []
    eps = 1e-9
    for span in spans:
        placed = False
        for lane_index, lane_end in enumerate(lane_end_s):
            # Touching edges can share a lane; true overlap stacks.
            if span.start_s_m >= lane_end - eps:
                span.lane = lane_index
                lane_end_s[lane_index] = max(lane_end, span.end_s_m)
                placed = True
                break
        if not placed:
            span.lane = len(lane_end_s)
            lane_end_s.append(span.end_s_m)


def _lane_count_for_spans(spans: list[TimelineSpan]) -> int:
    if not spans:
        return 1
    return max(1, max(int(getattr(span, "lane", 0)) for span in spans) + 1)


def _build_domain_boundaries(domain_positions: list[float]) -> list[float]:
    """Build ordinal interval boundaries from ordinal center positions.

    For N ordinals (center positions), returns N+1 boundaries:
    - boundary[0] at first center
    - boundary[N] at last center
    - interior boundaries as midpoints between adjacent centers
    """
    if not domain_positions:
        return [0.0]
    if len(domain_positions) == 1:
        pos = float(domain_positions[0])
        return [pos, pos]

    boundaries: list[float] = [float(domain_positions[0])]
    for i in range(1, len(domain_positions)):
        left = float(domain_positions[i - 1])
        right = float(domain_positions[i])
        boundaries.append((left + right) / 2.0)
    boundaries.append(float(domain_positions[-1]))
    return boundaries


def _constraint_color(key: str) -> str:
    return {
        "max_velocity_meters_per_sec": "#4ca5ff",
        "max_acceleration_meters_per_sec2": "#4fd1c5",
        "max_velocity_deg_per_sec": "#f59e7f",
        "max_acceleration_deg_per_sec2": "#d184ff",
    }.get(key, "#6f94b7")


def _plain_label(label: str) -> str:
    label = str(label or "")
    label = label.replace("<br/>", " ").replace("<br>", " ")
    label = re.sub(r"\s+", " ", label).strip()
    return label


def _element_x(element: object) -> float | None:
    if isinstance(element, TranslationTarget):
        return float(element.x_meters)
    if isinstance(element, Waypoint):
        return float(element.translation_target.x_meters)
    return None


def _element_y(element: object) -> float | None:
    if isinstance(element, TranslationTarget):
        return float(element.y_meters)
    if isinstance(element, Waypoint):
        return float(element.translation_target.y_meters)
    return None


def _format_axis_label(value: float, step: float, unit: str) -> str:
    suffix = f" {unit}" if unit else ""
    if step < 1.0:
        return f"{value:.1f}{suffix}"
    return f"{value:.0f}{suffix}"


def _nice_ruler_step(px_per_m: float) -> float:
    target_px = 88.0
    for step in (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0):
        if step * float(px_per_m) >= target_px:
            return step
    return 100.0


def _qpointf(x: float, y: float):
    from PySide6.QtCore import QPointF

    return QPointF(float(x), float(y))


def _map_projection_distance_to_time(
    projection: TimelineProjection,
    *,
    path: Path,
    config: dict[str, object],
    use_sim_time: bool,
) -> None:
    total_s = max(0.0, float(projection.display_s_m))
    if total_s <= 1e-9:
        projection.display_s_m = 1.0
        projection.total_s_m = 0.0
        return

    mapper, total_t, sim_index = _build_time_mapper(
        path=path,
        projection=projection,
        config=config,
        use_sim_time=use_sim_time,
    )

    for row in projection.rows:
        for marker in row.markers:
            if marker.kind == "start":
                marker.s_m = 0.0
                continue
            if marker.kind == "end":
                # The end marker represents path completion, not first arrival at
                # the final XY position. If the robot reaches the last point and
                # then spends additional time rotating in place, nearest-point
                # matching can incorrectly snap the end marker to that earlier
                # arrival time. Pin it to the true simulation duration instead.
                marker.s_m = float(total_t)
                continue
            source_s = marker.s_m
            mapped = None
            if (
                sim_index is not None
                and marker.source_x_m is not None
                and marker.source_y_m is not None
            ):
                mapped = _closest_time_for_point(
                    sim_index,
                    float(marker.source_x_m),
                    float(marker.source_y_m),
                    expected_s=source_s,
                )
            marker.s_m = float(mapped if mapped is not None else mapper(source_s))
        if row.constraint_key:
            row.spans = _build_constraint_spans_for_axis(
                path,
                row.constraint_key,
                list(getattr(path, "path_elements", []) or []),
                mapper=mapper,
                sim_index=sim_index,
            )
            row.lane_count = _lane_count_for_spans(row.spans)
        else:
            for span in row.spans:
                span.start_s_m = mapper(span.start_s_m)
                span.end_s_m = mapper(span.end_s_m)

    projection.total_s_m = total_t
    projection.display_s_m = max(1.0, total_t)


def _build_time_mapper(
    *,
    path: Path,
    projection: TimelineProjection,
    config: dict[str, object],
    use_sim_time: bool,
):
    total_s = max(1e-9, float(projection.display_s_m))
    default_v = _safe_positive(
        config.get("default_max_velocity_meters_per_sec", 4.5),
        fallback=4.5,
    )

    if not use_sim_time:
        total_t = total_s / default_v
        return (lambda s: max(0.0, min(float(s), total_s)) / default_v), total_t, None

    try:
        sim_index, total_t = _build_sim_time_index(path, config, total_s)

        def map_s_to_t(s_value: float) -> float:
            s = max(0.0, min(float(s_value), total_s))
            idx = bisect.bisect_left(sim_index.sample_s, s)
            if idx <= 0:
                return sim_index.sample_t[0]
            if idx >= len(sim_index.sample_s):
                return sim_index.sample_t[-1]
            s0 = sim_index.sample_s[idx - 1]
            s1 = sim_index.sample_s[idx]
            t0 = sim_index.sample_t[idx - 1]
            t1 = sim_index.sample_t[idx]
            if s1 <= s0 + 1e-9:
                return t0
            alpha = (s - s0) / (s1 - s0)
            return t0 + alpha * (t1 - t0)

        return map_s_to_t, max(total_t, 1e-6), sim_index
    except Exception:
        total_t = total_s / default_v
        return (lambda s: max(0.0, min(float(s), total_s)) / default_v), total_t, None


def _build_sim_time_index(
    path: Path,
    config: dict[str, object],
    total_s: float,
) -> tuple[_SimTimeIndex, float]:
    sim = simulate_path(path, config, dt_s=0.02)
    times = list(getattr(sim, "times_sorted", []) or [])
    poses = dict(getattr(sim, "poses_by_time", {}) or {})
    progress = dict(getattr(sim, "progress_by_time", {}) or {})
    if len(times) < 2 or not poses:
        raise ValueError("not enough simulation samples")

    sample_s: list[float] = []
    sample_t: list[float] = []
    sample_x: list[float] = []
    sample_y: list[float] = []
    last_s = 0.0

    segments: list[tuple[float, float, float, float, float, float, float]] = []
    total_len = 0.0
    if not progress:
        segments, total_len = _build_anchor_progress_geometry(
            list(getattr(path, "path_elements", []) or [])
        )
        if not segments or total_len <= 1e-9:
            raise ValueError("insufficient anchor geometry")

    for t in times:
        pose = poses.get(t)
        if pose is None:
            continue
        x, y, _ = pose
        if progress and t in progress:
            s_val = max(last_s, min(float(total_s), float(progress[t])))
        else:
            s_val = _project_point_to_global_s(float(x), float(y), segments, fallback_s=last_s)
            s_val = min(float(total_len), max(last_s, s_val))
        sample_s.append(s_val)
        sample_t.append(float(t))
        sample_x.append(float(x))
        sample_y.append(float(y))
        last_s = s_val

    if len(sample_s) < 2:
        raise ValueError("not enough projected samples")

    return (
        _SimTimeIndex(
            sample_s=sample_s,
            sample_t=sample_t,
            sample_x=sample_x,
            sample_y=sample_y,
        ),
        float(sample_t[-1]),
    )


def _build_anchor_progress_geometry(
    path_elements: list[object],
) -> tuple[list[tuple[float, float, float, float, float, float, float]], float]:
    anchors: list[tuple[float, float]] = []
    for element in path_elements:
        if isinstance(element, TranslationTarget):
            anchors.append((float(element.x_meters), float(element.y_meters)))
        elif isinstance(element, Waypoint):
            anchors.append(
                (
                    float(element.translation_target.x_meters),
                    float(element.translation_target.y_meters),
                )
            )

    if len(anchors) < 2:
        return [], 0.0

    segments: list[tuple[float, float, float, float, float, float, float]] = []
    cumulative = 0.0
    for i in range(len(anchors) - 1):
        ax, ay = anchors[i]
        bx, by = anchors[i + 1]
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        seg_len = math.hypot(dx, dy)
        start_s = cumulative
        cumulative += seg_len
        segments.append((ax, ay, dx, dy, denom, start_s, seg_len))

    return segments, cumulative


def _project_point_to_global_s(
    x_m: float,
    y_m: float,
    segments: list[tuple[float, float, float, float, float, float, float]],
    fallback_s: float,
) -> float:
    if not segments:
        return float(fallback_s)

    best_s = float(fallback_s)
    best_dist2: float | None = None
    for ax, ay, dx, dy, denom, start_s, seg_len in segments:
        t = 0.0
        if denom > 1e-12:
            t = ((x_m - ax) * dx + (y_m - ay) * dy) / denom
            t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        dist2 = (x_m - proj_x) ** 2 + (y_m - proj_y) ** 2
        s_val = start_s + (seg_len * t)
        if best_dist2 is None or dist2 < best_dist2:
            best_dist2 = dist2
            best_s = s_val
    return float(best_s)


def _closest_time_for_point(
    sim_index: _SimTimeIndex,
    x_m: float,
    y_m: float,
    *,
    expected_s: float,
    max_s_delta: float | None = 1.5,
) -> float | None:
    if not sim_index.sample_t:
        return None

    if max_s_delta is None:
        candidate_indices = range(len(sim_index.sample_t))
    else:
        min_s = max(0.0, float(expected_s) - float(max_s_delta))
        max_s = float(expected_s) + float(max_s_delta)
        start_idx = bisect.bisect_left(sim_index.sample_s, min_s)
        end_idx = bisect.bisect_right(sim_index.sample_s, max_s)
        if start_idx >= end_idx:
            return None
        candidate_indices = range(start_idx, end_idx)

    best_idx: int | None = None
    best_score: float | None = None
    for idx in candidate_indices:
        sx = sim_index.sample_x[idx]
        sy = sim_index.sample_y[idx]
        ss = sim_index.sample_s[idx]
        dist2 = (float(sx) - x_m) ** 2 + (float(sy) - y_m) ** 2
        s_bias = 0.25 * abs(float(ss) - float(expected_s))
        score = dist2 + s_bias * s_bias
        if best_score is None or score < best_score:
            best_score = score
            best_idx = idx

    if best_idx is None:
        return None
    return float(sim_index.sample_t[best_idx])


def _safe_positive(value, *, fallback: float) -> float:
    try:
        parsed = float(value)
        if parsed > 1e-9:
            return parsed
    except Exception:
        pass
    return float(fallback)
