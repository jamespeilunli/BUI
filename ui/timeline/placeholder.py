# mypy: ignore-errors
"""Timeline dock for the redesign rollout."""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QRectF, QSize, Signal, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFontDatabase,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
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
from ui.sidebar.utils import (
    RANGED_CONSTRAINT_KEYS,
    ROTATION_CONSTRAINT_KEYS,
    SPINNER_METADATA,
    SPINNER_UNITS,
    TRANSLATION_CONSTRAINT_KEYS,
)
from ui.sidebar.utils.ranged_constraint_ui import get_constraint_domain_elements


HEADER_WIDTH = 216
TRACK_PADDING_X = 12
TIMELINE_RIGHT_OVERSCROLL_PX = 600
TOP_PADDING = 8
BOTTOM_PADDING = 8
RULER_HEIGHT = 22
ROW_HEIGHT = 34
ROW_GAP = 4
MIN_ROW_HEIGHT = 22
MIN_SPAN_ROW_HEIGHT = 18
MIN_LANE_HEIGHT = 5
MIN_LANE_GAP = 2
MIN_ZOOM_PX_PER_M = 25
MAX_ZOOM_PX_PER_M = 1200
DEFAULT_ZOOM_PX_PER_M = 72
ZOOM_SLIDER_MIN = 0
ZOOM_SLIDER_MAX = 100
PLAYBACK_STEP_S = SIMULATION_UPDATE_INTERVAL_MS / 1000.0
TIMELINE_MARKER_SIZE = 11.0
TIMELINE_MARKER_SELECTION_SIZE = 19.0
TIMELINE_MARKER_HIT_WIDTH = 20.0
TIMELINE_MARKER_HIT_HEIGHT = 24.0
TIMELINE_MARKER_LINE_INSET = 1.5
TIMELINE_STRUCTURE_TRANSLATION_COLOR = "#3aa3ff"
TIMELINE_STRUCTURE_WAYPOINT_COLOR = "#ff7f3a"
TIMELINE_STRUCTURE_ROTATION_COLOR = "#50c878"
TIMELINE_TRIGGER_COLOR = "#ffd54d"
STRUCTURE_ADD_TYPES = ("translation", "waypoint", "rotation")
STRUCTURE_ADD_LABELS = {
    "translation": "Translation",
    "waypoint": "Waypoint",
    "rotation": "Rotation",
}
TRANSLATION_CONSTRAINT_ROW_TITLE = "Translation Constraints"
ROTATION_CONSTRAINT_ROW_TITLE = "Rotation Constraints"


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
    constraint_index: int | None = None
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
    constraint_keys: list[str] = field(default_factory=list)
    constraint_positions_by_key: dict[str, list[float]] = field(default_factory=dict)
    constraint_display_ranges_by_key: dict[str, list[tuple[float, float]]] = field(
        default_factory=dict
    )


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
    constraint_index: int | None = None
    constraint_key: str | None = None
    start_ordinal: int | None = None
    end_ordinal: int | None = None


@dataclass
class _SimTimeIndex:
    sample_s: list[float]
    sample_t: list[float]
    sample_x: list[float]
    sample_y: list[float]


@dataclass
class TriggerPlacement:
    insert_index: int
    t_ratio: float


@dataclass
class StructurePlacement:
    insert_index: int
    x_m: float | None = None
    y_m: float | None = None
    t_ratio: float | None = None


def _row_height_for(row: TimelineRow) -> int:
    if not row.spans:
        return ROW_HEIGHT
    lanes = max(1, int(row.lane_count))
    # Keep single-lane rows compact, but expand for stacked overlaps.
    return max(ROW_HEIGHT, 10 + lanes * 16 + max(0, lanes - 1) * 3)


def _rows_total_height(rows: list[TimelineRow]) -> int:
    if not rows:
        return ROW_HEIGHT
    return sum(_row_height_for(row) for row in rows) + max(0, len(rows) - 1) * ROW_GAP


def _row_min_height_for(row: TimelineRow) -> int:
    if not row.spans:
        return MIN_ROW_HEIGHT
    lanes = max(1, int(row.lane_count))
    return max(MIN_SPAN_ROW_HEIGHT, 6 + lanes * MIN_LANE_HEIGHT + max(0, lanes - 1) * MIN_LANE_GAP)


def _constraint_row_keys(row: TimelineRow) -> list[str]:
    keys = [str(key) for key in getattr(row, "constraint_keys", []) if str(key)]
    if keys:
        return keys
    if row.constraint_key:
        return [str(row.constraint_key)]
    return []


def _is_constraint_row(row: TimelineRow | None) -> bool:
    return bool(row is not None and _constraint_row_keys(row))


def _constraint_domain_label_for_key(key: str) -> str:
    if str(key) in TRANSLATION_CONSTRAINT_KEYS:
        return "translation"
    return "rotation"


def _distribute_integer_heights(values: list[float], target_total: int) -> list[int]:
    if not values:
        return []
    floored = [int(math.floor(value)) for value in values]
    remainder = int(target_total - sum(floored))
    if remainder > 0:
        order = sorted(
            range(len(values)),
            key=lambda idx: (values[idx] - floored[idx]),
            reverse=True,
        )
        for idx in order[:remainder]:
            floored[idx] += 1
    elif remainder < 0:
        order = sorted(
            range(len(values)),
            key=lambda idx: (values[idx] - floored[idx]),
        )
        for idx in order[: abs(remainder)]:
            floored[idx] -= 1
    return floored


def _row_layout(rows: list[TimelineRow], canvas_height: int) -> list[tuple[int, int]]:
    if not rows:
        return []

    start_y = TOP_PADDING + RULER_HEIGHT
    available_rows_h = max(0, int(canvas_height) - start_y - BOTTOM_PADDING)
    gap_count = max(0, len(rows) - 1)

    natural_heights = [_row_height_for(row) for row in rows]
    min_heights = [_row_min_height_for(row) for row in rows]
    absolute_min_heights = [1 for _ in rows]
    natural_rows_h = sum(natural_heights)
    min_rows_h = sum(min_heights)
    absolute_min_rows_h = sum(absolute_min_heights)
    if gap_count > 0:
        max_gap = max(0.0, (available_rows_h - absolute_min_rows_h) / gap_count)
        row_gap = max(0, int(math.floor(min(float(ROW_GAP), max_gap))))
    else:
        row_gap = 0
    target_rows_h = max(absolute_min_rows_h, available_rows_h - gap_count * row_gap)

    if natural_rows_h <= target_rows_h:
        heights = list(natural_heights)
    elif min_rows_h <= target_rows_h:
        flex_total = sum(
            max(0, natural_height - min_height)
            for natural_height, min_height in zip(natural_heights, min_heights)
        )
        if flex_total <= 1e-9:
            heights = list(min_heights)
        else:
            ratio = max(0.0, min(1.0, (target_rows_h - min_rows_h) / flex_total))
            heights = [
                min_height + (natural_height - min_height) * ratio
                for natural_height, min_height in zip(natural_heights, min_heights)
            ]
    else:
        flex_total = sum(
            max(0, min_height - absolute_min_height)
            for min_height, absolute_min_height in zip(min_heights, absolute_min_heights)
        )
        if flex_total <= 1e-9:
            heights = list(absolute_min_heights)
        else:
            ratio = max(
                0.0,
                min(1.0, (target_rows_h - absolute_min_rows_h) / flex_total),
            )
            heights = [
                absolute_min_height + (min_height - absolute_min_height) * ratio
                for min_height, absolute_min_height in zip(min_heights, absolute_min_heights)
            ]

    heights_int = _distribute_integer_heights(heights, target_rows_h)
    layout: list[tuple[int, int]] = []
    y = start_y
    for height in heights_int:
        layout.append((y, max(1, int(height))))
        y += int(height) + row_gap
    return layout


class _TimelineCanvasBase(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._projection = TimelineProjection(0.0, 6.0, "", [])
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(180)

    def set_projection(self, projection: TimelineProjection) -> None:
        self._projection = projection
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        height = TOP_PADDING + RULER_HEIGHT + _rows_total_height(self._projection.rows)
        height += BOTTOM_PADDING
        return QSize(HEADER_WIDTH, height)

    def _row_layout(self) -> list[tuple[int, int]]:
        return _row_layout(self._projection.rows, self.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            self._paint_background(painter)

            if not self._projection.rows:
                return

            self._draw_ruler(painter)
            for index, (row, (row_top, row_h)) in enumerate(
                zip(self._projection.rows, self._row_layout())
            ):
                self._draw_row(painter, row, row_top, row_h, index)
        finally:
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
    structureAddClicked = Signal()
    triggerAddClicked = Signal()
    constraintAddClicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)
        self._structure_add_armed = False
        self._trigger_add_armed = False
        self._constraint_add_armed = False
        self._constraint_create_key = str(RANGED_CONSTRAINT_KEYS[0])

    def set_structure_add_armed(self, armed: bool) -> None:
        self._structure_add_armed = bool(armed)
        self.update()

    def set_trigger_add_armed(self, armed: bool) -> None:
        self._trigger_add_armed = bool(armed)
        self.update()

    def set_constraint_add_armed(self, armed: bool) -> None:
        self._constraint_add_armed = bool(armed)
        self.update()

    def set_constraint_create_key(self, key: str) -> None:
        if key in RANGED_CONSTRAINT_KEYS:
            self._constraint_create_key = str(key)
        self.update()

    def _draw_ruler(self, painter: QPainter) -> None:
        top = TOP_PADDING
        painter.fillRect(QRectF(0, top, HEADER_WIDTH, RULER_HEIGHT), QColor("#171717"))

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
        if row.title == "Structure":
            self._draw_add_button(painter, y, row_height, self._structure_add_armed)
        elif row.title == "Triggers":
            self._draw_add_button(painter, y, row_height, self._trigger_add_armed)
        elif _is_constraint_row(row):
            armed = bool(
                self._constraint_add_armed
                and self._constraint_create_key in _constraint_row_keys(row)
            )
            self._draw_add_button(painter, y, row_height, armed)

    def _draw_add_button(self, painter: QPainter, y: int, row_height: int, armed: bool) -> None:
        rect = self._add_button_rect(y, row_height)
        fill = QColor("#2f6f52") if armed else QColor("#23272c")
        border = QColor("#6bd39a") if armed else QColor("#3a4047")
        text = QColor("#eef4f8") if armed else QColor("#d7dde4")
        painter.save()
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 4.0, 4.0)
        painter.setPen(text)
        fm = painter.fontMetrics()
        plus = "+"
        text_x = rect.center().x() - (fm.horizontalAdvance(plus) / 2.0)
        text_y = rect.center().y() + ((fm.ascent() - fm.descent()) / 2.0)
        painter.drawText(int(text_x), int(text_y), plus)
        painter.restore()

    def _add_button_rect(self, y: int, row_height: int) -> QRectF:
        button_size = min(18.0, max(14.0, float(row_height) - 10.0))
        x = HEADER_WIDTH - button_size - 10.0
        y_pos = y + max(2.0, (float(row_height) - button_size) / 2.0)
        return QRectF(x, y_pos, button_size, button_size)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            for row, (row_top, row_h) in zip(self._projection.rows, self._row_layout()):
                if row.title not in {"Structure", "Triggers"} and not _is_constraint_row(row):
                    continue
                if self._add_button_rect(row_top, row_h).contains(event.position()):
                    if row.title == "Structure":
                        self.structureAddClicked.emit()
                    elif row.title == "Triggers":
                        self.triggerAddClicked.emit()
                    else:
                        keys = _constraint_row_keys(row)
                        domain = _constraint_domain_label_for_key(keys[0]) if keys else ""
                        self.constraintAddClicked.emit(domain)
                    event.accept()
                    return
        super().mousePressEvent(event)


class _TimelineTrackCanvas(_TimelineCanvasBase):
    scrubRequested = Signal(float)
    playPauseToggleRequested = Signal()
    zoomInRequested = Signal()
    zoomOutRequested = Signal()
    pathItemClicked = Signal(int)
    constraintSpanClicked = Signal(str, int, int)
    constraintSpanClickedWithIndex = Signal(int, str, int, int)
    emptyAreaClicked = Signal()
    structureItemCreateRequested = Signal(str, float)
    eventTriggerCreateRequested = Signal(float)
    eventTriggerMoveRequested = Signal(int, float)
    constraintRangeCreateRequested = Signal(str, int, int)
    constraintRangeUpdateRequested = Signal(int, str, int, int, int, int, str)
    constraintRangeDeleteRequested = Signal(int, str, int, int)
    deleteSelectionRequested = Signal()
    addModeCancelRequested = Signal()

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
        self._empty_press_scrubbed = False
        self._pressed_event_marker: TimelineMarker | None = None
        self._pressed_event_marker_origin_s_m = 0.0
        self._pressed_event_marker_drag_s_m = 0.0
        self._pressed_event_marker_drag_active = False
        self._pressed_event_marker_press_pos: tuple[float, float] | None = None
        self._structure_add_armed = False
        self._structure_add_type = "translation"
        self._structure_add_hover_s_m: float | None = None
        self._structure_add_hover_valid = True
        self._structure_add_press_consumed = False
        self._trigger_add_armed = False
        self._trigger_add_press_consumed = False
        self._constraint_add_armed = False
        self._constraint_create_key = str(RANGED_CONSTRAINT_KEYS[0])
        self._constraint_add_press_consumed = False
        self._pressed_constraint_span: TimelineSpan | None = None
        self._pressed_constraint_action: str | None = None
        self._pressed_constraint_origin: tuple[int, int] | None = None
        self._pressed_constraint_preview: tuple[int, int] | None = None
        self._pressed_constraint_preview_valid = True
        self._pressed_constraint_press_pos: tuple[float, float] | None = None
        self._pressed_constraint_drag_active = False
        self._pressed_constraint_drag_offset = 0
        self._pressed_constraint_move_press_s_m: float | None = None
        self._pressed_constraint_move_origin_bounds: tuple[float, float] | None = None
        self._creating_constraint_key: str | None = None
        self._creating_constraint_start: int | None = None
        self._creating_constraint_anchor_s_m: float | None = None
        self._creating_constraint_preview: tuple[int, int] | None = None
        self._creating_constraint_preview_valid = True
        self._hover_hit: tuple[str, object] | None = None
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._path_context: Path | None = None
        self._config_context: dict[str, object] = {}

    def set_path_context(self, path: Path | None, config: dict[str, object] | None) -> None:
        self._path_context = path
        self._config_context = dict(config or {})

    def set_structure_add_armed(self, armed: bool, element_type: str | None = None) -> None:
        self._structure_add_armed = bool(armed)
        if element_type in STRUCTURE_ADD_TYPES:
            self._structure_add_type = str(element_type)
        if not self._structure_add_armed:
            self._structure_add_hover_s_m = None
            self._structure_add_hover_valid = True
        self._update_structure_add_cursor()
        self.update()

    def set_trigger_add_armed(self, armed: bool) -> None:
        self._trigger_add_armed = bool(armed)
        self._update_trigger_add_cursor()
        self.update()

    def set_constraint_add_armed(self, armed: bool) -> None:
        self._constraint_add_armed = bool(armed)
        self._update_constraint_add_cursor()
        self.update()

    def set_constraint_create_key(self, key: str) -> None:
        if key in RANGED_CONSTRAINT_KEYS:
            self._constraint_create_key = str(key)

    def set_projection(self, projection: TimelineProjection) -> None:
        self._hover_hit = None
        self._structure_add_hover_s_m = None
        self._structure_add_hover_valid = True
        super().set_projection(projection)

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
        timeline_width = TRACK_PADDING_X * 2 + max(1, track_width) + TIMELINE_RIGHT_OVERSCROLL_PX
        return QSize(timeline_width, base.height())

    def _track_left(self) -> float:
        return float(TRACK_PADDING_X)

    def _track_right(self) -> float:
        return float(self.width() - TRACK_PADDING_X)

    def _track_width(self) -> float:
        return max(1.0, self._track_right() - self._track_left())

    def _x_for_s(self, s_m: float) -> float:
        s_m = max(0.0, min(float(s_m), self._projection.display_s_m))
        return self._track_left() + s_m * self._zoom_px_per_m

    def _x_for_time(self, s_m: float) -> float:
        s_m = max(0.0, float(s_m))
        return self._track_left() + s_m * self._zoom_px_per_m

    def _ruler_end_s(self) -> float:
        visible_s = self._track_width() / max(1.0, float(self._zoom_px_per_m))
        return max(float(self._projection.display_s_m), visible_s)

    def _track_rect_for_row(self, row_top: int, row_height: int) -> QRectF:
        vertical_padding = max(0.5, min(5.0, float(row_height) * 0.12))
        return QRectF(
            self._track_left(),
            row_top + vertical_padding,
            self._track_width(),
            max(1.0, row_height - (vertical_padding * 2.0)),
        )

    def _lane_metrics(self, row: TimelineRow, track_rect: QRectF) -> tuple[int, float, float, float]:
        lane_count = max(1, int(row.lane_count), self._preview_lane_count_for_row(row))
        available_h = max(1.0, track_rect.height())
        lane_gap = 3.0
        if lane_count > 1:
            max_gap = (available_h - lane_count) / max(1, lane_count - 1)
            lane_gap = max(0.0, min(lane_gap, max_gap))
        total_lane_gap = lane_gap * max(0, lane_count - 1)
        lane_h = max(1.0, (available_h - total_lane_gap) / lane_count)
        lanes_block_h = lane_count * lane_h + total_lane_gap
        lanes_top = track_rect.top() + max(0.0, (available_h - lanes_block_h) / 2.0)
        return lane_count, lane_gap, lane_h, lanes_top

    def _preview_lane_count_for_row(self, row: TimelineRow) -> int:
        lane = self._active_constraint_preview_lane(row)
        if lane is None:
            return 1
        return max(1, int(lane) + 1)

    def _active_constraint_preview_lane(self, row: TimelineRow) -> int | None:
        if not _is_constraint_row(row):
            return None
        if (
            self._creating_constraint_key
            and self._creating_constraint_preview is not None
            and self._creating_constraint_key in row.constraint_positions_by_key
        ):
            start_ord, end_ord = self._creating_constraint_preview
            return self._constraint_preview_lane(
                row,
                self._creating_constraint_key,
                int(start_ord),
                int(end_ord),
            )
        return None

    def _constraint_preview_lane(
        self,
        row: TimelineRow,
        key: str,
        start_ordinal: int,
        end_ordinal: int,
        *,
        ignore_index: int | None = None,
    ) -> int | None:
        positions = row.constraint_positions_by_key.get(str(key), [])
        if not positions:
            return None
        start_s, end_s = _constraint_display_range_from_positions(
            list(positions),
            int(start_ordinal),
            int(end_ordinal),
        )
        spans: list[TimelineSpan] = []
        preview_span = TimelineSpan(
            start_s_m=float(start_s),
            end_s_m=float(end_s),
            label="",
            color=_constraint_color(str(key)),
            constraint_key=str(key),
            start_ordinal=int(start_ordinal),
            end_ordinal=int(end_ordinal),
        )
        for span in row.spans:
            if ignore_index is not None and span.constraint_index == ignore_index:
                continue
            spans.append(
                TimelineSpan(
                    start_s_m=float(span.start_s_m),
                    end_s_m=float(span.end_s_m),
                    label=str(span.label),
                    color=str(span.color),
                    constraint_index=span.constraint_index,
                    constraint_key=span.constraint_key,
                    start_ordinal=span.start_ordinal,
                    end_ordinal=span.end_ordinal,
                )
            )
        spans.append(preview_span)
        spans.sort(key=lambda span: (span.start_s_m, span.end_s_m, span.label))
        _assign_span_lanes(spans)
        return int(preview_span.lane)

    def _span_lane_for_display(self, span: TimelineSpan, row: TimelineRow) -> int:
        return max(0, int(getattr(span, "lane", 0)))

    def _draw_ruler(self, painter: QPainter) -> None:
        top = TOP_PADDING
        bottom = TOP_PADDING + RULER_HEIGHT
        painter.fillRect(QRectF(0, top, self.width(), RULER_HEIGHT), QColor("#181818"))

        base_y = bottom - 1
        painter.setPen(QPen(QColor("#59636e"), 1))
        painter.drawLine(int(self._track_left()), base_y, int(self._track_right()), base_y)

        step_m = _nice_ruler_step(self._zoom_px_per_m)
        minor_step_m = _minor_ruler_step(step_m)
        ruler_end_s = self._ruler_end_s()
        metrics = painter.fontMetrics()
        label_y = top + 14
        minor_tick_top = bottom - 5
        tick_top = bottom - 9
        tick_bottom = bottom - 1

        if minor_step_m > 1e-9 and minor_step_m < step_m:
            minor_tick = 0.0
            while minor_tick <= ruler_end_s + 1e-9:
                major_index = round(minor_tick / step_m)
                if abs(minor_tick - major_index * step_m) > 1e-6:
                    x = self._x_for_time(minor_tick)
                    painter.setPen(QPen(QColor("#454d56"), 1))
                    painter.drawLine(int(x), minor_tick_top, int(x), tick_bottom)
                minor_tick += minor_step_m

        tick = 0.0
        while tick <= ruler_end_s + 1e-9:
            x = self._x_for_time(tick)
            painter.setPen(QPen(QColor("#68727d"), 1))
            painter.drawLine(int(x), tick_top, int(x), tick_bottom)
            label = _format_axis_label(tick, step_m, self._projection.axis_unit)
            label_width = metrics.horizontalAdvance(label)
            painter.setPen(QColor("#c1c9d1"))
            painter.drawText(int(x - label_width / 2), label_y, label)
            tick += step_m

    def _draw_row(
        self, painter: QPainter, row: TimelineRow, y: int, row_height: int, index: int
    ) -> None:
        row_rect = QRectF(0, y, self.width(), row_height)
        track_rect = self._track_rect_for_row(y, row_height)

        painter.fillRect(
            row_rect,
            QColor("#161a1d") if index % 2 == 0 else QColor("#13171a"),
        )

        painter.setPen(QColor("#30353b"))
        painter.drawLine(0, y + row_height - 1, self.width(), y + row_height - 1)

        if row.spans or self._has_constraint_create_preview(row):
            self._draw_spans(painter, row, track_rect)
            return
        if row.markers:
            self._draw_markers(painter, row, track_rect)
            if row.title == "Structure":
                self._draw_structure_add_preview(painter, row, track_rect)
            return

        painter.setPen(QColor("#6f7882"))
        painter.drawText(
            int(track_rect.left()),
            int(track_rect.center().y() + 5),
            row.empty_text,
        )
        if row.title == "Structure":
            center_y = track_rect.center().y()
            painter.setPen(QPen(QColor("#3b4148"), 1))
            painter.drawLine(
                _qpointf(track_rect.left(), center_y),
                _qpointf(track_rect.right(), center_y),
            )
            self._draw_structure_add_preview(painter, row, track_rect)

    def _has_constraint_create_preview(self, row: TimelineRow) -> bool:
        return bool(
            _is_constraint_row(row)
            and self._creating_constraint_key
            and self._creating_constraint_preview is not None
            and self._creating_constraint_key in row.constraint_positions_by_key
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
        painter.drawLine(_qpointf(track_rect.left(), center_y), _qpointf(track_rect.right(), center_y))

        last_label_right = -10_000.0
        metrics = painter.fontMetrics()
        indicator_inset = max(
            1.0,
            min(TIMELINE_MARKER_LINE_INSET, max(1.0, track_rect.height() * 0.08)),
        )
        indicator_top = track_rect.top() + indicator_inset
        indicator_bottom = track_rect.bottom() - indicator_inset

        for marker in row.markers:
            marker_s_m = self._marker_display_s(marker)
            x = self._x_for_s(marker_s_m)
            color = QColor(marker.color)
            painter.setPen(QPen(color, 1.4))
            painter.drawLine(_qpointf(x, indicator_top), _qpointf(x, indicator_bottom))
            if self._is_marker_selected(marker):
                painter.save()
                painter.setPen(QPen(QColor("#f5f7fa"), 1.4))
                painter.setBrush(Qt.NoBrush)
                selection_size = TIMELINE_MARKER_SELECTION_SIZE
                painter.drawEllipse(
                    QRectF(
                        x - (selection_size / 2.0),
                        center_y - (selection_size / 2.0),
                        selection_size,
                        selection_size,
                    )
                )
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
            painter.drawText(int(label_x), int(track_rect.top()) + 10, label)
            last_label_right = label_x + label_width

    def _draw_marker_shape(
        self, painter: QPainter, kind: str, x: float, center_y: float, color: QColor
    ) -> None:
        painter.save()
        outline_color = QColor(color.darker(118))
        fill_color = QColor(color)
        half_size = TIMELINE_MARKER_SIZE / 2.0
        if kind == "waypoint":
            painter.setPen(QPen(outline_color, 1.0))
            painter.setBrush(fill_color)
            diamond = QPolygonF(
                [
                    _qpointf(x, center_y - half_size),
                    _qpointf(x + half_size, center_y),
                    _qpointf(x, center_y + half_size),
                    _qpointf(x - half_size, center_y),
                ]
            )
            painter.drawPolygon(diamond)
        elif kind == "rotation":
            painter.setPen(QPen(outline_color, 1.0))
            painter.setBrush(fill_color)
            tip_offset = half_size * 1.1
            base_offset = tip_offset / 2.0
            tri = QPolygonF(
                [
                    _qpointf(x, center_y - tip_offset),
                    _qpointf(x + half_size, center_y + base_offset),
                    _qpointf(x - half_size, center_y + base_offset),
                ]
            )
            painter.drawPolygon(tri)
        else:
            painter.setPen(QPen(outline_color, 1.0))
            painter.setBrush(fill_color)
            painter.drawEllipse(
                QRectF(
                    x - half_size,
                    center_y - half_size,
                    TIMELINE_MARKER_SIZE,
                    TIMELINE_MARKER_SIZE,
                )
            )
        painter.restore()

    def _draw_structure_add_preview(
        self, painter: QPainter, row: TimelineRow, track_rect: QRectF
    ) -> None:
        if (
            not self._structure_add_armed
            or row.title != "Structure"
            or self._structure_add_hover_s_m is None
        ):
            return

        x = self._x_for_s(float(self._structure_add_hover_s_m))
        center_y = track_rect.center().y()
        valid = bool(self._structure_add_hover_valid)
        element_type = str(self._structure_add_type)
        color = QColor(
            {
                "translation": TIMELINE_STRUCTURE_TRANSLATION_COLOR,
                "waypoint": TIMELINE_STRUCTURE_WAYPOINT_COLOR,
                "rotation": TIMELINE_STRUCTURE_ROTATION_COLOR,
            }.get(element_type, TIMELINE_STRUCTURE_TRANSLATION_COLOR)
        )
        if not valid:
            color = QColor("#d06a6a")

        painter.save()
        painter.setOpacity(0.68 if valid else 0.56)
        guide_pen = QPen(color, 1.4, Qt.DashLine)
        painter.setPen(guide_pen)
        painter.drawLine(
            _qpointf(x, track_rect.top() + 1.0),
            _qpointf(x, track_rect.bottom() - 1.0),
        )
        self._draw_marker_shape(painter, element_type, x, center_y, color)
        painter.setOpacity(1.0)

        label = STRUCTURE_ADD_LABELS.get(element_type, "Structure")
        if not valid:
            label = f"{label} unavailable"
        metrics = painter.fontMetrics()
        label_x = min(
            max(track_rect.left(), x + 8.0),
            max(track_rect.left(), track_rect.right() - metrics.horizontalAdvance(label) - 4.0),
        )
        painter.setPen(QColor("#f0f4f8") if valid else QColor("#ffb7b7"))
        painter.drawText(int(label_x), int(track_rect.top()) + 10, label)
        painter.restore()

    def _draw_spans(self, painter: QPainter, row: TimelineRow, track_rect: QRectF) -> None:
        lane_count, lane_gap, lane_h, lanes_top = self._lane_metrics(row, track_rect)
        lanes_block_h = lane_count * lane_h + lane_gap * max(0, lane_count - 1)
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
            start_s_m, end_s_m = self._span_display_bounds(span, row)
            x0 = self._x_for_s(start_s_m)
            x1 = self._x_for_s(end_s_m)
            if x1 < x0:
                x0, x1 = x1, x0
            if abs(x1 - x0) < 1.0:
                center_x = (x0 + x1) / 2.0
                width = 8.0
                left_x = center_x - (width / 2.0)
            else:
                width = max(1.0, x1 - x0)
                left_x = x0
            lane_index = self._span_lane_for_display(span, row)
            bar_y = lanes_top + lane_index * (lane_h + lane_gap)
            rect = QRectF(left_x, bar_y, width, lane_h)
            color = QColor(span.color)
            fill = QColor(color)
            fill.setAlpha(220)
            if self._is_span_selected(span):
                fill = QColor(color.lighter(118))
                fill.setAlpha(245)
            elif self._is_span_hovered(span):
                fill = QColor(color.lighter(108))
                fill.setAlpha(238)
            if self._pressed_constraint_span is span and not self._pressed_constraint_preview_valid:
                fill = QColor("#8a3f46")
                fill.setAlpha(180)

            pen_color = color.lighter(120)
            pen_width = 1.1
            if self._is_span_selected(span):
                pen_color = QColor("#f4f7fa")
                pen_width = 1.5
            elif self._is_span_hovered(span):
                pen_color = QColor("#d9e2ec")
                pen_width = 1.35
            if self._pressed_constraint_span is span and not self._pressed_constraint_preview_valid:
                pen_color = QColor("#ff8c92")
                pen_width = 1.4
            painter.setPen(QPen(pen_color, pen_width))
            painter.setBrush(fill)
            painter.drawRect(rect)

            if (
                self._is_span_selected(span)
                or self._pressed_constraint_span is span
                or self._is_span_hovered(span)
            ):
                handle_w = min(6.0, max(3.0, rect.width() / 3.0))
                handle_color = QColor("#f4f7fa")
                if self._hover_span_edge(span, "start"):
                    handle_color = QColor("#ffffff")
                painter.fillRect(
                    QRectF(rect.left(), rect.top(), handle_w, rect.height()),
                    handle_color,
                )
                handle_color = QColor("#f4f7fa")
                if self._hover_span_edge(span, "end"):
                    handle_color = QColor("#ffffff")
                painter.fillRect(
                    QRectF(rect.right() - handle_w, rect.top(), handle_w, rect.height()),
                    handle_color,
                )

            text_rect = QRectF(rect.left() + 5, rect.top(), rect.width() - 10, rect.height())
            if span.label and text_rect.width() > 1.0:
                painter.save()
                painter.setClipRect(text_rect)
                painter.setPen(QColor("#f4f7fa"))
                painter.drawText(
                    text_rect,
                    Qt.AlignVCenter | Qt.AlignLeft,
                    span.label,
                )
                painter.restore()

        if (
            self._pressed_constraint_span is not None
            and self._pressed_constraint_preview is not None
            and self._pressed_constraint_span.constraint_key
        ):
            positions = row.constraint_positions_by_key.get(
                str(self._pressed_constraint_span.constraint_key),
                [],
            )
            if positions:
                start_ord, end_ord = self._pressed_constraint_preview
                start_s, end_s = _constraint_display_range_from_positions(
                    list(positions),
                    start_ord,
                    end_ord,
                )
                self._draw_constraint_guides(
                    painter,
                    start_s,
                    end_s,
                    lanes_top - 2.0,
                    lanes_top + lanes_block_h + 2.0,
                    self._pressed_constraint_preview_valid,
                )

        if (
            self._creating_constraint_key
            and self._creating_constraint_preview is not None
            and self._creating_constraint_key in row.constraint_positions_by_key
        ):
            start_ord, end_ord = self._creating_constraint_preview
            positions = row.constraint_positions_by_key.get(self._creating_constraint_key, [])
            if positions:
                start_s, end_s = _constraint_display_range_from_positions(
                    positions,
                    start_ord,
                    end_ord,
                )
                x0 = self._x_for_s(start_s)
                x1 = self._x_for_s(end_s)
                if x1 < x0:
                    x0, x1 = x1, x0
                if abs(x1 - x0) < 1.0:
                    center_x = (x0 + x1) / 2.0
                    x0 = center_x - 4.0
                    x1 = center_x + 4.0
                lane_index = self._constraint_preview_lane(
                    row,
                    self._creating_constraint_key,
                    int(start_ord),
                    int(end_ord),
                )
                lane_index = 0 if lane_index is None else int(lane_index)
                preview_y = lanes_top + lane_index * (lane_h + lane_gap)
                preview_rect = QRectF(x0, preview_y, max(1.0, x1 - x0), lane_h)
                if self._creating_constraint_preview_valid:
                    color = QColor(_constraint_color(self._creating_constraint_key))
                    color.setAlpha(120)
                    pen_color = QColor("#e8eef5")
                else:
                    color = QColor("#8a3f46")
                    color.setAlpha(110)
                    pen_color = QColor("#ff8c92")
                painter.setPen(QPen(pen_color, 1.2, Qt.DashLine))
                painter.setBrush(color)
                painter.drawRect(preview_rect)
                self._draw_constraint_guides(
                    painter,
                    start_s,
                    end_s,
                    lanes_top - 2.0,
                    lanes_top + lanes_block_h + 2.0,
                    self._creating_constraint_preview_valid,
                )

    def _draw_constraint_guides(
        self,
        painter: QPainter,
        start_s_m: float,
        end_s_m: float,
        top: float,
        bottom: float,
        valid: bool,
    ) -> None:
        painter.save()
        color = QColor("#e8eef5" if valid else "#ff8c92")
        color.setAlpha(210 if valid else 235)
        painter.setPen(QPen(color, 1.0, Qt.DashLine))
        for s_m in {float(start_s_m), float(end_s_m)}:
            x = self._x_for_s(s_m)
            painter.drawLine(_qpointf(x, top), _qpointf(x, bottom))
        painter.restore()

    def _span_display_bounds(self, span: TimelineSpan, row: TimelineRow) -> tuple[float, float]:
        if (
            self._pressed_constraint_span is span
            and self._pressed_constraint_preview is not None
            and span.constraint_key
        ):
            positions = row.constraint_positions_by_key.get(str(span.constraint_key), [])
            if positions:
                start_ord, end_ord = self._pressed_constraint_preview
                return _constraint_display_range_from_positions(positions, start_ord, end_ord)
        return float(span.start_s_m), float(span.end_s_m)

    def _ordinal_for_x(self, row: TimelineRow, key: str, x: float) -> int | None:
        positions = list(row.constraint_positions_by_key.get(str(key), []) or [])
        if not positions:
            return None
        total = len(positions)
        if total <= 1:
            return 1
        s_m = self._s_for_x(float(x))
        if s_m <= positions[0]:
            return 1
        if s_m >= positions[-1]:
            return total
        right_idx = bisect.bisect_left(positions, s_m)
        left_idx = max(0, right_idx - 1)
        right_idx = min(total - 1, right_idx)
        if abs(float(s_m) - float(positions[left_idx])) <= abs(float(positions[right_idx]) - float(s_m)):
            return left_idx + 1
        return right_idx + 1

    def _constraint_range_available(
        self,
        row: TimelineRow,
        key: str,
        start_ordinal: int,
        end_ordinal: int,
        *,
        ignore_index: int | None = None,
    ) -> bool:
        if str(key) not in row.constraint_positions_by_key:
            return False
        if not row.constraint_positions_by_key.get(str(key), []):
            return False
        start_ordinal = int(start_ordinal)
        end_ordinal = int(end_ordinal)
        if start_ordinal > end_ordinal:
            start_ordinal, end_ordinal = end_ordinal, start_ordinal
        return True

    def _constraint_row_for_key(self, key: str | None) -> TimelineRow | None:
        if not key:
            return None
        for row in self._projection.rows:
            if str(key) in _constraint_row_keys(row):
                return row
        return None

    def _update_constraint_drag_preview(self, x: float) -> None:
        span = self._pressed_constraint_span
        if span is None or not span.constraint_key:
            return
        row = self._constraint_row_for_key(str(span.constraint_key))
        if row is None:
            return
        origin = self._pressed_constraint_origin
        if origin is None:
            return
        start_ord, end_ord = origin
        action = self._pressed_constraint_action or "move"
        if action == "resize_start":
            positions = row.constraint_positions_by_key.get(str(span.constraint_key), [])
            target_start = _constraint_start_ordinal_for_s(
                list(positions),
                int(end_ord),
                self._s_for_x(float(x)),
            )
            if target_start is None:
                return
            new_start = max(1, min(int(target_start), end_ord))
            new_end = end_ord
        elif action == "resize_end":
            target_ordinal = self._ordinal_for_x(row, str(span.constraint_key), float(x))
            if target_ordinal is None:
                return
            new_start = start_ord
            new_end = max(start_ord, int(target_ordinal))
        else:
            positions = row.constraint_positions_by_key.get(str(span.constraint_key), [])
            current_s_m = self._s_for_x(float(x))
            if (
                self._pressed_constraint_move_press_s_m is not None
                and self._pressed_constraint_move_origin_bounds is not None
            ):
                origin_start_s_m, _origin_end_s_m = self._pressed_constraint_move_origin_bounds
                target_start_s_m = origin_start_s_m + (
                    current_s_m - float(self._pressed_constraint_move_press_s_m)
                )
                move_range = _constraint_move_range_for_display_start(
                    list(positions),
                    int(start_ord),
                    int(end_ord),
                    target_start_s_m,
                )
            else:
                move_range = _constraint_move_range_for_s(
                    list(positions),
                    int(start_ord),
                    int(end_ord),
                    current_s_m,
                )
            if move_range is None:
                return
            new_start, new_end = move_range
        self._pressed_constraint_preview = (int(new_start), int(new_end))
        self._pressed_constraint_preview_valid = self._constraint_range_available(
            row,
            str(span.constraint_key),
            int(new_start),
            int(new_end),
            ignore_index=span.constraint_index,
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
        self._pressed_event_marker = None
        self._pressed_event_marker_press_pos = None
        self._pressed_event_marker_drag_active = False
        self._empty_press_scrubbed = False
        self._scrub_moved = False
        self._structure_add_press_consumed = False
        self._trigger_add_press_consumed = False
        self._constraint_add_press_consumed = False
        self._pressed_constraint_span = None
        self._pressed_constraint_action = None
        self._pressed_constraint_origin = None
        self._pressed_constraint_preview = None
        self._pressed_constraint_preview_valid = True
        self._pressed_constraint_press_pos = None
        self._pressed_constraint_drag_active = False
        self._pressed_constraint_move_press_s_m = None
        self._pressed_constraint_move_origin_bounds = None
        self._creating_constraint_key = None
        self._creating_constraint_start = None
        self._creating_constraint_anchor_s_m = None
        self._creating_constraint_preview = None
        self._creating_constraint_preview_valid = True
        self._pressed_on_playhead = self._is_playhead_click(event)
        pressed_row = self._row_at_y(float(event.position().y()))
        if self._structure_add_armed:
            if pressed_row is not None and pressed_row.title == "Structure":
                target_s = self._s_for_x(float(event.position().x()))
                if self._structure_add_is_valid(target_s):
                    self.structureItemCreateRequested.emit(
                        str(self._structure_add_type),
                        float(target_s),
                    )
                self._structure_add_press_consumed = True
            event.accept()
            return
        if self._trigger_add_armed and pressed_row is not None and pressed_row.title == "Triggers":
            self.eventTriggerCreateRequested.emit(self._s_for_x(float(event.position().x())))
            self._trigger_add_press_consumed = True
            event.accept()
            return
        if (
            self._constraint_add_armed
            and pressed_row is not None
            and _is_constraint_row(pressed_row)
            and self._constraint_create_key in _constraint_row_keys(pressed_row)
            and self._pressed_hit is None
        ):
            positions = pressed_row.constraint_positions_by_key.get(self._constraint_create_key, [])
            anchor_s_m = self._s_for_x(float(event.position().x()))
            preview = _constraint_creation_range_for_s(
                list(positions),
                anchor_s_m,
                anchor_s_m,
            )
            if preview is not None:
                self._creating_constraint_key = self._constraint_create_key
                self._creating_constraint_start = int(preview[0])
                self._creating_constraint_anchor_s_m = float(anchor_s_m)
                self._constraint_add_press_consumed = True
                self._creating_constraint_preview = (int(preview[0]), int(preview[1]))
                self._creating_constraint_preview_valid = self._constraint_range_available(
                    pressed_row,
                    self._constraint_create_key,
                    int(preview[0]),
                    int(preview[1]),
                )
                self.update()
                event.accept()
                return
        if self._pressed_hit is not None:
            hit_kind, payload = self._pressed_hit
            if hit_kind in {"span", "span_edge"}:
                if hit_kind == "span_edge":
                    span, side = payload
                    action = "resize_start" if side == "start" else "resize_end"
                else:
                    span = payload
                    action = "move"
                if isinstance(span, TimelineSpan):
                    self._pressed_constraint_span = span
                    self._pressed_constraint_action = action
                    self._hover_hit = None
                    start_ord = int(span.start_ordinal or 1)
                    end_ord = int(span.end_ordinal or start_ord)
                    self._pressed_constraint_origin = (start_ord, end_ord)
                    self._pressed_constraint_preview = (start_ord, end_ord)
                    self._pressed_constraint_preview_valid = True
                    self._pressed_constraint_press_pos = (
                        float(event.position().x()),
                        float(event.position().y()),
                    )
                    row = self._constraint_row_for_key(str(span.constraint_key))
                    if row is not None and span.constraint_key:
                        positions = row.constraint_positions_by_key.get(
                            str(span.constraint_key),
                            [],
                        )
                        if positions:
                            self._pressed_constraint_move_press_s_m = self._s_for_x(
                                float(event.position().x())
                            )
                            self._pressed_constraint_move_origin_bounds = (
                                _constraint_display_range_from_positions(
                                    list(positions),
                                    start_ord,
                                    end_ord,
                                )
                            )
                        click_ord = self._ordinal_for_x(
                            row,
                            str(span.constraint_key),
                            float(event.position().x()),
                        )
                        if click_ord is not None:
                            self._pressed_constraint_drag_offset = int(click_ord) - start_ord
                    self._apply_constraint_drag_cursor()
                    event.accept()
                    return
            if (
                hit_kind == "marker"
                and isinstance(payload, TimelineMarker)
                and payload.kind == "event"
                and payload.path_index is not None
            ):
                self._pressed_event_marker = payload
                self._pressed_event_marker_origin_s_m = float(payload.s_m)
                self._pressed_event_marker_drag_s_m = float(payload.s_m)
                self._pressed_event_marker_press_pos = (
                    float(event.position().x()),
                    float(event.position().y()),
                )
                event.accept()
                return
        self._scrub_active = bool(self._pressed_on_playhead and self._pressed_hit is None)
        if self._pressed_hit is None and not self._pressed_on_playhead:
            self.emptyAreaClicked.emit()
            self._emit_scrub_for_event(event)
            self._empty_press_scrubbed = True
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._update_structure_add_cursor(float(event.position().y()), float(event.position().x()))
        self._update_trigger_add_cursor(float(event.position().y()))
        self._update_constraint_add_cursor(float(event.position().y()))
        if not (
            self._structure_add_armed
            or self._trigger_add_armed
            or self._constraint_add_armed
            or self._pressed_constraint_span is not None
            or self._pressed_event_marker is not None
            or self._scrub_active
        ):
            self._update_hover_feedback(float(event.position().x()), float(event.position().y()))
        if self._trigger_add_press_consumed:
            event.accept()
            return
        if self._constraint_add_press_consumed:
            row = self._constraint_row_for_key(self._creating_constraint_key)
            if (
                row is not None
                and self._creating_constraint_key
                and self._creating_constraint_anchor_s_m is not None
            ):
                positions = row.constraint_positions_by_key.get(self._creating_constraint_key, [])
                preview = _constraint_creation_range_for_s(
                    list(positions),
                    float(self._creating_constraint_anchor_s_m),
                    self._s_for_x(float(event.position().x())),
                )
                if preview is not None:
                    start, end = preview
                    self._creating_constraint_preview = (int(start), int(end))
                    self._creating_constraint_preview_valid = self._constraint_range_available(
                        row,
                        self._creating_constraint_key,
                        start,
                        end,
                    )
                    self.update()
            event.accept()
            return
        if self._pressed_constraint_span is not None:
            press_pos = self._pressed_constraint_press_pos
            if press_pos is not None and not self._pressed_constraint_drag_active:
                dx = float(event.position().x()) - float(press_pos[0])
                dy = float(event.position().y()) - float(press_pos[1])
                if (dx * dx) + (dy * dy) >= 9.0:
                    self._pressed_constraint_drag_active = True
            if self._pressed_constraint_drag_active:
                self._apply_constraint_drag_cursor()
                self._update_constraint_drag_preview(float(event.position().x()))
                self.update()
            event.accept()
            return
        if self._pressed_event_marker is not None:
            press_pos = self._pressed_event_marker_press_pos
            if press_pos is not None and not self._pressed_event_marker_drag_active:
                dx = float(event.position().x()) - float(press_pos[0])
                dy = float(event.position().y()) - float(press_pos[1])
                if (dx * dx) + (dy * dy) >= 9.0:
                    self._pressed_event_marker_drag_active = True
            if self._pressed_event_marker_drag_active:
                self._pressed_event_marker_drag_s_m = self._s_for_x(float(event.position().x()))
                self.update()
            event.accept()
            return
        if self._scrub_active:
            self._scrub_moved = True
            self._emit_scrub_for_event(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._structure_add_press_consumed:
            self._structure_add_press_consumed = False
            self._pressed_hit = None
            self._pressed_on_playhead = False
            self._empty_press_scrubbed = False
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._trigger_add_press_consumed:
            self._trigger_add_press_consumed = False
            self._pressed_hit = None
            self._pressed_on_playhead = False
            self._empty_press_scrubbed = False
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._constraint_add_press_consumed:
            try:
                if (
                    self._creating_constraint_key
                    and self._creating_constraint_preview is not None
                    and self._creating_constraint_preview_valid
                ):
                    start_ord, end_ord = self._creating_constraint_preview
                    self.constraintRangeCreateRequested.emit(
                        str(self._creating_constraint_key),
                        int(start_ord),
                        int(end_ord),
                    )
            finally:
                self._constraint_add_press_consumed = False
                self._creating_constraint_key = None
                self._creating_constraint_start = None
                self._creating_constraint_anchor_s_m = None
                self._creating_constraint_preview = None
                self._creating_constraint_preview_valid = True
                self._pressed_hit = None
                self._pressed_on_playhead = False
                self._empty_press_scrubbed = False
                if self._constraint_add_armed:
                    self._update_constraint_add_cursor(float(event.position().y()))
                else:
                    self._update_hover_feedback(float(event.position().x()), float(event.position().y()))
                self.update()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._pressed_constraint_span is not None:
            try:
                span = self._pressed_constraint_span
                if (
                    self._pressed_constraint_drag_active
                    and self._pressed_constraint_preview is not None
                    and self._pressed_constraint_preview_valid
                ):
                    old_start, old_end = self._pressed_constraint_origin or (
                        int(span.start_ordinal or 1),
                        int(span.end_ordinal or span.start_ordinal or 1),
                    )
                    new_start, new_end = self._pressed_constraint_preview
                    if (
                        span.constraint_index is not None
                        and span.constraint_key
                        and (int(new_start), int(new_end)) != (int(old_start), int(old_end))
                    ):
                        self.constraintRangeUpdateRequested.emit(
                            int(span.constraint_index),
                            str(span.constraint_key),
                            int(old_start),
                            int(old_end),
                            int(new_start),
                            int(new_end),
                            str(self._pressed_constraint_action or "move"),
                        )
                elif (
                    span.constraint_key
                    and span.start_ordinal is not None
                    and span.end_ordinal is not None
                ):
                    if span.constraint_index is not None:
                        self.constraintSpanClickedWithIndex.emit(
                            int(span.constraint_index),
                            str(span.constraint_key),
                            int(span.start_ordinal),
                            int(span.end_ordinal),
                        )
                    else:
                        self.constraintSpanClicked.emit(
                            str(span.constraint_key),
                            int(span.start_ordinal),
                            int(span.end_ordinal),
                        )
            finally:
                self._pressed_constraint_span = None
                self._pressed_constraint_action = None
                self._pressed_constraint_origin = None
                self._pressed_constraint_preview = None
                self._pressed_constraint_preview_valid = True
                self._pressed_constraint_press_pos = None
                self._pressed_constraint_drag_active = False
                self._pressed_constraint_drag_offset = 0
                self._pressed_constraint_move_press_s_m = None
                self._pressed_constraint_move_origin_bounds = None
                self._update_hover_feedback(float(event.position().x()), float(event.position().y()))
                self.update()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._pressed_event_marker is not None:
            try:
                if self._pressed_event_marker.path_index is not None:
                    if self._pressed_event_marker_drag_active:
                        target_s_m = self._s_for_x(float(event.position().x()))
                        self.eventTriggerMoveRequested.emit(
                            int(self._pressed_event_marker.path_index),
                            float(target_s_m),
                        )
                    else:
                        self.pathItemClicked.emit(int(self._pressed_event_marker.path_index))
            finally:
                self._pressed_event_marker = None
                self._pressed_event_marker_press_pos = None
                self._pressed_event_marker_drag_active = False
                self._pressed_event_marker_drag_s_m = 0.0
                self.update()
            event.accept()
            return
        if not self._scrub_active or event.button() != Qt.LeftButton:
            if event.button() == Qt.LeftButton and not self._scrub_moved:
                if not self._empty_press_scrubbed:
                    self._activate_click_hit(event)
                self._pressed_hit = None
                self._pressed_on_playhead = False
                self._empty_press_scrubbed = False
                event.accept()
                return
            self._pressed_hit = None
            self._pressed_on_playhead = False
            self._empty_press_scrubbed = False
            return super().mouseReleaseEvent(event)

        if self._scrub_moved or not self._pressed_on_playhead:
            self._emit_scrub_for_event(event)
        should_toggle = self._pressed_on_playhead and self._is_playhead_click(event) and not self._scrub_moved
        self._scrub_active = False
        self._scrub_moved = False
        self._pressed_on_playhead = False
        self._pressed_hit = None
        self._empty_press_scrubbed = False
        if should_toggle:
            self.playPauseToggleRequested.emit()
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._update_structure_add_cursor()
        self._update_trigger_add_cursor()
        self._update_constraint_add_cursor()
        self._hover_hit = None
        self.unsetCursor()
        self.setToolTip("")
        self.update()
        super().leaveEvent(event)

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

    def _marker_display_s(self, marker: TimelineMarker) -> float:
        if (
            self._pressed_event_marker is not None
            and self._pressed_event_marker_drag_active
            and marker.path_index is not None
            and self._pressed_event_marker.path_index is not None
            and int(marker.path_index) == int(self._pressed_event_marker.path_index)
        ):
            return float(self._pressed_event_marker_drag_s_m)
        return float(marker.s_m)

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
                if span.constraint_index is not None:
                    self.constraintSpanClickedWithIndex.emit(
                        int(span.constraint_index),
                        str(span.constraint_key),
                        int(span.start_ordinal),
                        int(span.end_ordinal),
                    )
                else:
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
        for row, (row_top, row_h) in zip(self._projection.rows, self._row_layout()):
            if row_top <= y <= row_top + row_h:
                track_rect = self._track_rect_for_row(row_top, row_h)
                if row.spans:
                    for span, rect in self._iter_span_rects(row, track_rect):
                        if rect.adjusted(-4.0, -2.0, 4.0, 2.0).contains(x, y):
                            edge_hit_width = min(6.0, max(2.0, rect.width() / 3.0))
                            if abs(float(x) - rect.left()) <= edge_hit_width:
                                return ("span_edge", (span, "start"))
                            if abs(float(x) - rect.right()) <= edge_hit_width:
                                return ("span_edge", (span, "end"))
                        if rect.adjusted(-3.0, -2.0, 3.0, 2.0).contains(x, y):
                            return ("span", span)
                if row.markers:
                    center_y = track_rect.center().y()
                    for marker in row.markers:
                        marker_rect = QRectF(
                            self._x_for_s(self._marker_display_s(marker))
                            - (TIMELINE_MARKER_HIT_WIDTH / 2.0),
                            center_y - (TIMELINE_MARKER_HIT_HEIGHT / 2.0),
                            TIMELINE_MARKER_HIT_WIDTH,
                            TIMELINE_MARKER_HIT_HEIGHT,
                        )
                        if marker_rect.contains(x, y):
                            return ("marker", marker)
                return None
        return None

    def _row_at_y(self, y: float) -> TimelineRow | None:
        if self._y_in_ruler(y):
            return None
        for row, (row_top, row_h) in zip(self._projection.rows, self._row_layout()):
            if row_top <= y <= row_top + row_h:
                return row
        return None

    def _structure_add_is_valid(self, s_m: float) -> bool:
        if self._structure_add_type != "rotation":
            return True
        return (
            resolve_structure_placement_for_time(
                self._path_context or Path(),
                self._config_context,
                float(s_m),
                self._structure_add_type,
            )
            is not None
        )

    def _update_structure_add_cursor(
        self,
        y: float | None = None,
        x: float | None = None,
    ) -> None:
        try:
            if not self._structure_add_armed:
                if not self._trigger_add_armed and not self._constraint_add_armed:
                    self.unsetCursor()
                self._structure_add_hover_s_m = None
                self._structure_add_hover_valid = True
                return

            row = self._row_at_y(float(y)) if y is not None else None
            if row is not None and row.title == "Structure":
                hover_s = self._s_for_x(float(x)) if x is not None else self._structure_add_hover_s_m
                if hover_s is not None:
                    self._structure_add_hover_s_m = float(hover_s)
                    self._structure_add_hover_valid = self._structure_add_is_valid(float(hover_s))
                self.setCursor(Qt.CrossCursor if self._structure_add_hover_valid else Qt.ForbiddenCursor)
                label = STRUCTURE_ADD_LABELS.get(self._structure_add_type, "Structure")
                self.setToolTip(
                    f"Click to add {label}"
                    if self._structure_add_hover_valid
                    else f"{label} needs a valid segment between anchors"
                )
            else:
                self._structure_add_hover_s_m = None
                self._structure_add_hover_valid = True
                self.setCursor(Qt.ArrowCursor)
                self.setToolTip("")
            self.update()
        except Exception:
            pass

    def _update_trigger_add_cursor(self, y: float | None = None) -> None:
        try:
            if not self._trigger_add_armed:
                if not self._structure_add_armed and not self._constraint_add_armed:
                    self.unsetCursor()
                return
            row = self._row_at_y(float(y)) if y is not None else None
            if row is not None and row.title == "Triggers":
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        except Exception:
            pass

    def _update_constraint_add_cursor(self, y: float | None = None) -> None:
        try:
            if not self._constraint_add_armed:
                if not self._structure_add_armed and not self._trigger_add_armed:
                    self.unsetCursor()
                return
            row = self._row_at_y(float(y)) if y is not None else None
            if (
                row is not None
                and _is_constraint_row(row)
                and self._constraint_create_key in _constraint_row_keys(row)
            ):
                self.setCursor(Qt.CrossCursor)
                self.setToolTip(
                    f"Drag to create {_constraint_key_label(self._constraint_create_key)}"
                )
            else:
                self.setCursor(Qt.ArrowCursor)
                self.setToolTip("")
        except Exception:
            pass

    def _apply_constraint_drag_cursor(self) -> None:
        action = self._pressed_constraint_action or "move"
        if action in {"resize_start", "resize_end"}:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.ClosedHandCursor)

    def _update_hover_feedback(self, x: float, y: float) -> None:
        hit = self._hit_test(float(x), float(y))
        if hit is not None and hit[0] not in {"span", "span_edge"}:
            hit = None
        changed = not self._same_hit(self._hover_hit, hit)
        self._hover_hit = hit

        if hit is None:
            self.unsetCursor()
            self.setToolTip("")
        else:
            kind, payload = hit
            if kind == "span_edge":
                span, side = payload
                self.setCursor(Qt.SizeHorCursor)
                verb = "Resize start" if side == "start" else "Resize end"
                self.setToolTip(f"{verb} - {self._constraint_span_tooltip(span)}")
            elif kind == "span":
                self.setCursor(Qt.OpenHandCursor)
                self.setToolTip(f"Move - {self._constraint_span_tooltip(payload)}")
            else:
                self.unsetCursor()
                self.setToolTip("")

        if changed:
            self.update()

    def _same_hit(
        self,
        left: tuple[str, object] | None,
        right: tuple[str, object] | None,
    ) -> bool:
        if left is None or right is None:
            return left is right
        if left[0] != right[0]:
            return False
        if left[0] == "span_edge":
            left_span, left_side = left[1]
            right_span, right_side = right[1]
            return left_span is right_span and left_side == right_side
        return left[1] is right[1]

    def _constraint_span_tooltip(self, span: TimelineSpan) -> str:
        key = str(span.constraint_key or "")
        label = _constraint_key_label(key)
        value = str(span.label or "").strip()
        start = int(span.start_ordinal or 1)
        end = int(span.end_ordinal or start)
        range_text = f"{start}" if start == end else f"{start}-{end}"
        if value:
            return f"{label} {value}, range {range_text}"
        return f"{label}, range {range_text}"

    def _iter_span_rects(self, row: TimelineRow, track_rect: QRectF):
        _, lane_gap, lane_h, lanes_top = self._lane_metrics(row, track_rect)
        for span in row.spans:
            start_s_m, end_s_m = self._span_display_bounds(span, row)
            x0 = self._x_for_s(start_s_m)
            x1 = self._x_for_s(end_s_m)
            if x1 < x0:
                x0, x1 = x1, x0
            if abs(x1 - x0) < 1.0:
                center_x = (x0 + x1) / 2.0
                width = 8.0
                left_x = center_x - (width / 2.0)
            else:
                width = max(1.0, x1 - x0)
                left_x = x0
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
        if not self._selection or self._selection.kind != "constraint":
            return False
        if self._selection.constraint_index is not None:
            return bool(
                span.constraint_index is not None
                and int(span.constraint_index) == int(self._selection.constraint_index)
            )
        return bool(
            span.constraint_key == self._selection.constraint_key
            and span.start_ordinal == self._selection.start_ordinal
            and span.end_ordinal == self._selection.end_ordinal
        )

    def _is_span_hovered(self, span: TimelineSpan) -> bool:
        hit = self._hover_hit
        if hit is None:
            return False
        if hit[0] == "span":
            return hit[1] is span
        if hit[0] == "span_edge":
            hovered_span, _side = hit[1]
            return hovered_span is span
        return False

    def _hover_span_edge(self, span: TimelineSpan, side: str) -> bool:
        hit = self._hover_hit
        if hit is None or hit[0] != "span_edge":
            return False
        hovered_span, hovered_side = hit[1]
        return hovered_span is span and str(hovered_side) == str(side)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Escape and (
            self._structure_add_armed or self._trigger_add_armed or self._constraint_add_armed
        ):
            self.addModeCancelRequested.emit()
            event.accept()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.deleteSelectionRequested.emit()
            event.accept()
            return
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
    constraintRangeSelectedByIndex = Signal(int, str, int, int)
    selectionCleared = Signal()
    pathItemDeleteRequested = Signal(int)
    structureItemCreateRequested = Signal(str, float)
    eventTriggerCreateRequested = Signal(float)
    eventTriggerMoveRequested = Signal(int, float)
    constraintRangeCreateRequested = Signal(str, int, int)
    constraintRangeUpdateRequested = Signal(int, str, int, int, int, int, str)
    constraintRangeDeleteRequested = Signal(int, str, int, int)

    def __init__(self, path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._config: dict[str, object] = {}
        self._projection = TimelineProjection(0.0, 6.0, "", [])
        self._selection: TimelineSelection | None = None
        self._current_time_s = 0.0
        self._total_time_s = 0.0
        self._is_playing = False
        self._minimum_zoom_px_per_m = MIN_ZOOM_PX_PER_M
        self._structure_add_armed = False
        self._structure_add_type = "translation"
        self._trigger_add_armed = False
        self._constraint_add_armed = False
        self._constraint_create_key = str(RANGED_CONSTRAINT_KEYS[0])
        self._play_pause_btn: QPushButton
        self._time_current_label: QLabel
        self._time_total_label: QLabel
        self._zoom_label: QLabel
        self._zoom_slider: QSlider
        self._rail_scroll: QScrollArea
        self._track_scroll: QScrollArea
        self._rail_canvas: _TimelineRailCanvas
        self._track_canvas: _TimelineTrackCanvas
        self._setup_ui()
        self.set_path(path or Path(), {})

    def _zoom_value_from_slider(self, slider_value: int) -> int:
        clamped = max(ZOOM_SLIDER_MIN, min(ZOOM_SLIDER_MAX, int(slider_value)))
        alpha = (clamped - ZOOM_SLIDER_MIN) / max(1, ZOOM_SLIDER_MAX - ZOOM_SLIDER_MIN)
        min_zoom = float(MIN_ZOOM_PX_PER_M)
        max_zoom = float(MAX_ZOOM_PX_PER_M)
        if max_zoom <= min_zoom:
            return int(round(min_zoom))
        zoom = min_zoom * ((max_zoom / min_zoom) ** alpha)
        return max(int(round(min_zoom)), min(MAX_ZOOM_PX_PER_M, int(round(zoom))))

    def _slider_value_from_zoom(self, zoom_value: float) -> int:
        min_zoom = float(MIN_ZOOM_PX_PER_M)
        max_zoom = float(MAX_ZOOM_PX_PER_M)
        zoom = max(min_zoom, min(max_zoom, float(zoom_value)))
        if max_zoom <= min_zoom:
            return ZOOM_SLIDER_MIN
        alpha = math.log(zoom / min_zoom) / math.log(max_zoom / min_zoom)
        slider_span = max(1, ZOOM_SLIDER_MAX - ZOOM_SLIDER_MIN)
        return int(round(ZOOM_SLIDER_MIN + alpha * slider_span))

    def _setup_ui(self) -> None:
        self.setObjectName("timelineDock")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(180)
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
            QPushButton[timelineControl='true'] {
                background: #272727;
                color: #e9eef3;
                border: 1px solid #393939;
                border-radius: 4px;
                padding: 2px 8px;
            }
            QPushButton[timelineControl='true']:hover {
                background: #313131;
            }
            QPushButton[timelineTransport='true'] {
                background: transparent;
                border: none;
                border-radius: 0;
                padding: 0;
            }
            QPushButton[timelineTransport='true']:hover {
                background: #24282d;
            }
            QPushButton[timelineTransport='true']:disabled {
                background: transparent;
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
            QLabel#timelineTimeValue,
            QLabel#timelineTimeSeparator {
                color: #bcc4cc;
                font-size: 11px;
            }
            QLabel#timelineTimeValue {
                color: #d3d9df;
                font-size: 12px;
            }
            QLabel#timelineTimeSeparator {
                color: #7f8892;
                font-size: 12px;
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
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        toolbar_layout.setSpacing(8)

        side_panel_width = 260
        left_panel = QWidget()
        left_panel.setFixedWidth(side_panel_width)
        left_layout = QHBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        fixed_font.setPointSize(11)

        self._time_current_label = QLabel(_format_time_value(0.0))
        self._time_current_label.setObjectName("timelineTimeValue")
        self._time_current_label.setWordWrap(False)
        self._time_current_label.setFont(fixed_font)
        time_value_width = self._time_current_label.fontMetrics().horizontalAdvance("9999.99")
        self._time_current_label.setFixedWidth(time_value_width + 2)
        self._time_current_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        left_layout.addWidget(self._time_current_label)

        time_separator_label = QLabel(" / ")
        time_separator_label.setObjectName("timelineTimeSeparator")
        time_separator_label.setFont(fixed_font)
        left_layout.addWidget(time_separator_label)

        self._time_total_label = QLabel(f"{_format_time_value(0.0)} s")
        self._time_total_label.setObjectName("timelineTimeValue")
        self._time_total_label.setWordWrap(False)
        self._time_total_label.setFont(fixed_font)
        total_width = self._time_total_label.fontMetrics().horizontalAdvance("9999.99 s")
        self._time_total_label.setFixedWidth(total_width + 2)
        self._time_total_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        left_layout.addWidget(self._time_total_label)
        left_layout.addStretch(1)
        toolbar_layout.addWidget(left_panel)

        toolbar_layout.addStretch(1)

        self._play_pause_btn = QPushButton("")
        self._play_pause_btn.setProperty("timelineTransport", "true")
        self._play_pause_btn.setFixedSize(32, 32)
        self._play_pause_btn.setIconSize(QSize(28, 28))
        self._play_pause_btn.setEnabled(False)
        self._play_pause_btn.clicked.connect(self._on_play_pause_toggled)
        toolbar_layout.addWidget(self._play_pause_btn, 0, Qt.AlignCenter)

        toolbar_layout.addStretch(1)

        right_panel = QWidget()
        right_panel.setFixedWidth(side_panel_width)
        right_layout = QHBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addStretch(1)

        fit_btn = QPushButton("Fit")
        fit_btn.setProperty("timelineControl", "true")
        fit_btn.clicked.connect(self.fit_to_all)
        right_layout.addWidget(fit_btn)

        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(ZOOM_SLIDER_MIN, ZOOM_SLIDER_MAX)
        self._zoom_slider.setValue(self._slider_value_from_zoom(DEFAULT_ZOOM_PX_PER_M))
        self._zoom_slider.setFixedWidth(124)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        right_layout.addWidget(self._zoom_slider)

        self._zoom_label = QLabel("")
        self._zoom_label.setObjectName("timelineZoomLabel")
        self._zoom_label.setMinimumWidth(54)
        right_layout.addWidget(self._zoom_label)
        toolbar_layout.addWidget(right_panel)

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
        self._rail_canvas.structureAddClicked.connect(self._show_structure_add_menu)
        self._rail_canvas.triggerAddClicked.connect(self._toggle_trigger_add_armed)
        self._rail_canvas.constraintAddClicked.connect(self._show_constraint_add_menu)
        self._rail_scroll.setWidget(self._rail_canvas)
        body_layout.addWidget(self._rail_scroll)

        self._track_scroll = QScrollArea()
        self._track_scroll.setWidgetResizable(False)
        self._track_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._track_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._track_scroll.viewport().installEventFilter(self)

        self._track_canvas = _TimelineTrackCanvas()
        self._track_canvas.scrubRequested.connect(self._on_scrub_requested)
        self._track_canvas.playPauseToggleRequested.connect(self._on_play_pause_toggled)
        self._track_canvas.zoomInRequested.connect(lambda: self._adjust_zoom(10))
        self._track_canvas.zoomOutRequested.connect(lambda: self._adjust_zoom(-10))
        self._track_canvas.pathItemClicked.connect(self.select_path_index)
        self._track_canvas.pathItemClicked.connect(self.pathItemSelected)
        self._track_canvas.constraintSpanClickedWithIndex.connect(
            self.select_constraint_range_by_index
        )
        self._track_canvas.constraintSpanClickedWithIndex.connect(
            self.constraintRangeSelectedByIndex
        )
        self._track_canvas.constraintSpanClicked.connect(self.select_constraint_range)
        self._track_canvas.constraintSpanClicked.connect(self.constraintRangeSelected)
        self._track_canvas.emptyAreaClicked.connect(self._on_empty_area_clicked)
        self._track_canvas.structureItemCreateRequested.connect(
            self._on_structure_item_create_requested
        )
        self._track_canvas.eventTriggerCreateRequested.connect(
            self._on_event_trigger_create_requested
        )
        self._track_canvas.eventTriggerMoveRequested.connect(self.eventTriggerMoveRequested)
        self._track_canvas.constraintRangeCreateRequested.connect(
            self._on_constraint_range_create_requested
        )
        self._track_canvas.constraintRangeUpdateRequested.connect(
            self.constraintRangeUpdateRequested
        )
        self._track_canvas.deleteSelectionRequested.connect(self._on_delete_selection_requested)
        self._track_canvas.addModeCancelRequested.connect(self._clear_add_modes)
        self._track_scroll.setWidget(self._track_canvas)
        self._track_scroll.setFocusProxy(self._track_canvas)
        body_layout.addWidget(self._track_scroll, 1)
        outer.addWidget(body, 1)

        self._track_scroll.verticalScrollBar().valueChanged.connect(
            self._rail_scroll.verticalScrollBar().setValue
        )

        self._on_zoom_changed(self._zoom_slider.value())
        self._update_play_pause_icon()
        self._apply_structure_add_armed(False)
        self._apply_trigger_add_armed(False)
        self._apply_constraint_add_armed(False)

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Wheel and watched in {
            self._track_scroll.viewport(),
            self._rail_scroll.viewport(),
        }:
            delta_x, delta_y = self._wheel_delta_components(event)
            abs_x = abs(delta_x)
            abs_y = abs(delta_y)
            if abs_x > abs_y:
                if watched is self._track_scroll.viewport():
                    self._pan_horizontally_from_wheel(delta_x)
                event.accept()
                return True
            if abs_y > abs_x:
                self._zoom_from_wheel(int(round(delta_y)), event.position().x(), watched)
                event.accept()
                return True
            if abs_x > 1e-6 or abs_y > 1e-6:
                event.accept()
                return True
        if event.type() == QEvent.Resize and watched in {
            self._track_scroll.viewport(),
            self._rail_scroll.viewport(),
        }:
            self._sync_canvas_size()
            self._update_minimum_zoom(enforce_current=True)
        return super().eventFilter(watched, event)

    def set_path(self, path: Path | None, config: dict[str, object] | None = None) -> None:
        had_meaningful_projection = float(getattr(self._projection, "total_s_m", 0.0)) > 1e-9
        preserved_hbar = int(self._track_scroll.horizontalScrollBar().value())
        preserved_vbar = int(self._track_scroll.verticalScrollBar().value())
        self._path = path or Path()
        self._config = dict(config or {})
        self._projection = _build_projection(self._path, self._config, use_sim_time=True)
        self._rail_canvas.set_projection(self._projection)
        self._track_canvas.set_path_context(self._path, self._config)
        self._track_canvas.set_projection(self._projection)
        self._restore_selection()
        self._track_canvas.set_playhead(self._current_time_s, self._is_playing)
        self._sync_canvas_size()
        self._update_minimum_zoom(enforce_current=False)
        if not had_meaningful_projection and self._projection.total_s_m > 1e-9:
            QTimer.singleShot(0, self.fit_to_all)
        else:
            self._restore_scroll_state(preserved_hbar, preserved_vbar)

    def fit_to_all(self) -> None:
        self._set_zoom_px_per_m(self._fit_zoom_px_per_m())

    def _adjust_zoom(self, delta: int) -> None:
        self._zoom_slider.setValue(self._zoom_slider.value() + int(delta))

    def _wheel_delta_components(self, event) -> tuple[float, float]:
        pixel_delta = event.pixelDelta()
        pixel_x = float(pixel_delta.x()) if pixel_delta else 0.0
        pixel_y = float(pixel_delta.y()) if pixel_delta else 0.0
        if abs(pixel_x) > 1e-6 or abs(pixel_y) > 1e-6:
            return pixel_x, pixel_y

        angle_delta = event.angleDelta()
        angle_x = float(angle_delta.x()) if angle_delta else 0.0
        angle_y = float(angle_delta.y()) if angle_delta else 0.0
        return angle_x, angle_y

    def _pan_horizontally_from_wheel(self, delta_x: float) -> None:
        hbar = self._track_scroll.horizontalScrollBar()
        scroll_px = int(round(delta_x))
        if scroll_px == 0 and abs(delta_x) > 1e-6:
            scroll_px = 1 if delta_x > 0.0 else -1
        hbar.setValue(hbar.value() - scroll_px)

    def _zoom_from_wheel(self, delta_y: int, viewport_x: float, watched: QWidget) -> None:
        if delta_y == 0:
            return
        current_zoom = int(self._track_canvas._zoom_px_per_m)
        zoom_steps = float(delta_y) / 120.0
        zoom_ratio = 1.12 ** zoom_steps
        target_zoom = int(round(current_zoom * zoom_ratio))
        if target_zoom == current_zoom:
            target_zoom = current_zoom + (1 if delta_y > 0 else -1)
        anchor_viewport_x = float(viewport_x)
        anchor_s_m: float | None = None
        if watched is self._track_scroll.viewport():
            hbar = self._track_scroll.horizontalScrollBar()
            content_x = float(hbar.value()) + anchor_viewport_x
            anchor_s_m = max(0.0, (content_x - TRACK_PADDING_X) / max(1.0, float(current_zoom)))
        self._set_zoom_px_per_m(
            target_zoom,
            anchor_viewport_x=anchor_viewport_x,
            anchor_s_m=anchor_s_m,
        )

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
        self._play_pause_btn.setEnabled(bool(enabled and self._total_time_s > 1e-9))
        self._update_play_pause_icon()
        self._time_current_label.setText(_format_time_value(self._current_time_s))
        self._time_total_label.setText(f"{_format_time_value(self._total_time_s)} s")
        if self._is_playing:
            self._ensure_playhead_visible()

    def _update_play_pause_icon(self) -> None:
        self._play_pause_btn.setIcon(_transport_icon(self._is_playing))
        self._play_pause_btn.setToolTip("Pause" if self._is_playing else "Play")

    def _on_zoom_changed(self, value: int) -> None:
        zoom_px_per_m = self._zoom_value_from_slider(value)
        self._apply_zoom_px_per_m(zoom_px_per_m)

    def _apply_zoom_px_per_m(
        self,
        zoom_px_per_m: int,
        *,
        anchor_viewport_x: float | None = None,
        anchor_s_m: float | None = None,
    ) -> None:
        zoom_px_per_m = max(MIN_ZOOM_PX_PER_M, min(MAX_ZOOM_PX_PER_M, int(round(zoom_px_per_m))))
        hbar = self._track_scroll.horizontalScrollBar()
        if anchor_viewport_x is not None and anchor_s_m is not None:
            preserved_viewport_x = float(anchor_viewport_x)
            preserved_content_s_m = max(0.0, float(anchor_s_m))
        else:
            playhead_x_before = TRACK_PADDING_X + self._current_time_s * float(
                self._track_canvas._zoom_px_per_m
            )
            preserved_viewport_x = playhead_x_before - float(hbar.value())
            preserved_content_s_m = float(self._current_time_s)

        self._zoom_label.setText(f"{int(zoom_px_per_m)} px/s")
        self._track_canvas.set_zoom_px_per_m(zoom_px_per_m)
        self._sync_canvas_size()

        anchor_x_after = TRACK_PADDING_X + preserved_content_s_m * float(zoom_px_per_m)
        hbar.setValue(int(round(anchor_x_after - preserved_viewport_x)))

    def _set_zoom_px_per_m(
        self,
        zoom_px_per_m: int,
        *,
        anchor_viewport_x: float | None = None,
        anchor_s_m: float | None = None,
    ) -> None:
        clamped_zoom = max(
            MIN_ZOOM_PX_PER_M,
            min(MAX_ZOOM_PX_PER_M, int(round(zoom_px_per_m))),
        )
        slider_value = self._slider_value_from_zoom(clamped_zoom)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(slider_value)
        self._zoom_slider.blockSignals(False)
        self._apply_zoom_px_per_m(
            clamped_zoom,
            anchor_viewport_x=anchor_viewport_x,
            anchor_s_m=anchor_s_m,
        )

    def _fit_zoom_px_per_m(self) -> int:
        display_s_m = max(self._projection.display_s_m, 0.0)
        if display_s_m <= 0.0:
            return MIN_ZOOM_PX_PER_M
        viewport_width = max(1, self._track_scroll.viewport().width() - TRACK_PADDING_X * 2)
        zoom = int(round(viewport_width / display_s_m))
        return max(MIN_ZOOM_PX_PER_M, min(MAX_ZOOM_PX_PER_M, zoom))

    def _update_minimum_zoom(self, *, enforce_current: bool) -> None:
        self._minimum_zoom_px_per_m = MIN_ZOOM_PX_PER_M
        current_zoom = max(MIN_ZOOM_PX_PER_M, int(self._track_canvas._zoom_px_per_m))
        slider_value = self._slider_value_from_zoom(current_zoom)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(slider_value)
        self._zoom_slider.blockSignals(False)

    def _sync_canvas_size(self) -> None:
        rail_hint = self._rail_canvas.sizeHint()
        track_hint = self._track_canvas.sizeHint()
        track_viewport_width = max(0, self._track_scroll.viewport().width())
        viewport_height = max(0, self._track_scroll.viewport().height())
        rail_height = max(1, viewport_height)
        path_width = int(
            round(max(self._projection.display_s_m, 0.0) * self._track_canvas._zoom_px_per_m)
        )
        right_overscroll_width = max(
            TIMELINE_RIGHT_OVERSCROLL_PX,
            track_viewport_width * 2,
        )
        track_width = max(
            track_hint.width(),
            track_viewport_width,
            TRACK_PADDING_X * 2 + path_width + right_overscroll_width,
        )
        track_height = max(1, viewport_height)

        self._rail_canvas.resize(HEADER_WIDTH, rail_height)
        self._rail_canvas.setMinimumSize(HEADER_WIDTH, 1)
        self._track_canvas.resize(track_width, track_height)
        self._track_canvas.setMinimumSize(track_width, 1)
        self._rail_scroll.verticalScrollBar().setPageStep(
            self._track_scroll.verticalScrollBar().pageStep()
        )
        self._rail_scroll.verticalScrollBar().setRange(
            self._track_scroll.verticalScrollBar().minimum(),
            self._track_scroll.verticalScrollBar().maximum(),
        )
        self._rail_scroll.verticalScrollBar().setValue(self._track_scroll.verticalScrollBar().value())

    def _restore_scroll_state(self, hbar_value: int, vbar_value: int) -> None:
        hbar = self._track_scroll.horizontalScrollBar()
        vbar = self._track_scroll.verticalScrollBar()
        hbar.setValue(max(hbar.minimum(), min(hbar.maximum(), int(hbar_value))))
        vbar.setValue(max(vbar.minimum(), min(vbar.maximum(), int(vbar_value))))

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

    def select_constraint_range_by_index(
        self,
        constraint_index: int | None,
        key: str | None,
        start_ordinal: int | None,
        end_ordinal: int | None,
    ) -> None:
        if constraint_index is None or not key or start_ordinal is None or end_ordinal is None:
            self.select_constraint_range(key, start_ordinal, end_ordinal)
            return
        selection = TimelineSelection(
            kind="constraint",
            constraint_index=int(constraint_index),
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
            index = self._selection.constraint_index
            key = self._selection.constraint_key
            start = self._selection.start_ordinal
            end = self._selection.end_ordinal
            found = False
            constraints = list(getattr(self._path, "ranged_constraints", []) or [])
            if index is not None and 0 <= int(index) < len(constraints):
                rc = constraints[int(index)]
                if (
                    getattr(rc, "key", None) == key
                    and int(getattr(rc, "start_ordinal", -1)) == int(start)
                    and int(getattr(rc, "end_ordinal", -1)) == int(end)
                ):
                    found = True
            if not found:
                for idx, rc in enumerate(constraints):
                    if (
                        getattr(rc, "key", None) == key
                        and int(getattr(rc, "start_ordinal", -1)) == int(start)
                        and int(getattr(rc, "end_ordinal", -1)) == int(end)
                    ):
                        self._selection.constraint_index = int(idx)
                        found = True
                        break
            if not found:
                self._selection = None
        self._track_canvas.set_selection(self._selection)

    def _on_empty_area_clicked(self) -> None:
        self.clear_selection()
        self.selectionCleared.emit()

    def _show_structure_add_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self._timeline_menu_stylesheet())
        for element_type in STRUCTURE_ADD_TYPES:
            action = menu.addAction(STRUCTURE_ADD_LABELS[element_type])
            action.triggered.connect(
                lambda checked=False, item_type=element_type: self._apply_structure_add_armed(
                    True,
                    item_type,
                )
        )
        menu.exec(QCursor.pos())

    def _show_constraint_add_menu(self, domain: str) -> None:
        domain = str(domain)
        if domain == "translation":
            keys = [key for key in RANGED_CONSTRAINT_KEYS if key in TRANSLATION_CONSTRAINT_KEYS]
        elif domain == "rotation":
            keys = [key for key in RANGED_CONSTRAINT_KEYS if key in ROTATION_CONSTRAINT_KEYS]
        else:
            return

        menu = QMenu(self)
        menu.setStyleSheet(self._timeline_menu_stylesheet())
        for key in keys:
            action = menu.addAction(_constraint_key_label(str(key)))
            action.triggered.connect(
                lambda checked=False, item_key=str(key): self._apply_constraint_add_armed(
                    True,
                    item_key,
                )
            )
        menu.exec(QCursor.pos())

    def _timeline_menu_stylesheet(self) -> str:
        return """
            QMenu {
                background: #202326;
                color: #eef2f6;
                border: 1px solid #3b424a;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 18px 5px 10px;
            }
            QMenu::item:selected {
                background: #304155;
            }
            """

    def _clear_add_modes(self) -> None:
        self._apply_structure_add_armed(False)
        self._apply_trigger_add_armed(False)
        self._apply_constraint_add_armed(False)

    def _apply_structure_add_armed(
        self,
        armed: bool,
        element_type: str | None = None,
    ) -> None:
        self._structure_add_armed = bool(armed)
        if element_type in STRUCTURE_ADD_TYPES:
            self._structure_add_type = str(element_type)
        self._rail_canvas.set_structure_add_armed(self._structure_add_armed)
        self._track_canvas.set_structure_add_armed(
            self._structure_add_armed,
            self._structure_add_type,
        )
        if self._structure_add_armed:
            self._apply_trigger_add_armed(False)
            self._apply_constraint_add_armed(False)

    def _on_structure_item_create_requested(self, element_type: str, time_s: float) -> None:
        self._apply_structure_add_armed(False)
        self.structureItemCreateRequested.emit(str(element_type), float(time_s))

    def _toggle_trigger_add_armed(self) -> None:
        self._apply_trigger_add_armed(not self._trigger_add_armed)

    def _apply_trigger_add_armed(self, armed: bool) -> None:
        self._trigger_add_armed = bool(armed)
        self._rail_canvas.set_trigger_add_armed(self._trigger_add_armed)
        self._track_canvas.set_trigger_add_armed(self._trigger_add_armed)
        if self._trigger_add_armed:
            self._apply_structure_add_armed(False)
            self._apply_constraint_add_armed(False)

    def set_constraint_create_key(self, key: str) -> None:
        if key not in RANGED_CONSTRAINT_KEYS:
            return
        self._constraint_create_key = str(key)
        self._rail_canvas.set_constraint_create_key(str(key))
        self._track_canvas.set_constraint_create_key(str(key))

    def _apply_constraint_add_armed(self, armed: bool, key: str | None = None) -> None:
        self._constraint_add_armed = bool(armed)
        if key in RANGED_CONSTRAINT_KEYS:
            self._constraint_create_key = str(key)
        self._rail_canvas.set_constraint_add_armed(self._constraint_add_armed)
        self._rail_canvas.set_constraint_create_key(self._constraint_create_key)
        self._track_canvas.set_constraint_add_armed(self._constraint_add_armed)
        self._track_canvas.set_constraint_create_key(self._constraint_create_key)
        if self._constraint_add_armed:
            self._apply_structure_add_armed(False)
            self._apply_trigger_add_armed(False)

    def _on_event_trigger_create_requested(self, time_s: float) -> None:
        self._apply_trigger_add_armed(False)
        self.eventTriggerCreateRequested.emit(float(time_s))

    def _on_constraint_range_create_requested(
        self,
        key: str,
        start_ordinal: int,
        end_ordinal: int,
    ) -> None:
        self._apply_constraint_add_armed(False)
        self.constraintRangeCreateRequested.emit(
            str(key),
            int(start_ordinal),
            int(end_ordinal),
        )

    def _on_delete_selection_requested(self) -> None:
        if self._selection is None:
            return
        if self._selection.kind == "path":
            index = self._selection.path_index
            if index is None or self._path is None:
                return
            if index < 0 or index >= len(getattr(self._path, "path_elements", []) or []):
                return
            self.pathItemDeleteRequested.emit(int(index))
            return
        if self._selection.kind == "constraint":
            for row in self._projection.rows:
                for span in row.spans:
                    if not self._track_canvas._is_span_selected(span):
                        continue
                    if span.constraint_index is None or not span.constraint_key:
                        return
                    self.constraintRangeDeleteRequested.emit(
                        int(span.constraint_index),
                        str(span.constraint_key),
                        int(span.start_ordinal or 1),
                        int(span.end_ordinal or span.start_ordinal or 1),
                    )
                    return

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Escape and (
            self._structure_add_armed or self._trigger_add_armed or self._constraint_add_armed
        ):
            self._clear_add_modes()
            event.accept()
            return
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
    rotation_count = 0
    event_count = 0
    translation_count = 0
    waypoint_count = 0

    for index, element in enumerate(path_elements):
        s_m = _element_global_s(index, element, path_elements, anchor_s_by_path_index)
        if isinstance(element, TranslationTarget):
            translation_count += 1
            structure_markers.append(
                TimelineMarker(
                    s_m,
                    f"T{translation_count}",
                    "translation",
                    TIMELINE_STRUCTURE_TRANSLATION_COLOR,
                    path_index=index,
                    source_x_m=_element_x(element),
                    source_y_m=_element_y(element),
                )
            )
        elif isinstance(element, Waypoint):
            waypoint_count += 1
            structure_markers.append(
                TimelineMarker(
                    s_m,
                    f"W{waypoint_count}",
                    "waypoint",
                    TIMELINE_STRUCTURE_WAYPOINT_COLOR,
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
                    TIMELINE_STRUCTURE_ROTATION_COLOR,
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
                    TIMELINE_TRIGGER_COLOR,
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

    translation_constraint_keys = [
        key for key in RANGED_CONSTRAINT_KEYS if key in TRANSLATION_CONSTRAINT_KEYS
    ]
    rotation_constraint_keys = [
        key for key in RANGED_CONSTRAINT_KEYS if key in ROTATION_CONSTRAINT_KEYS
    ]
    translation_constraint_spans = _build_combined_constraint_spans(
        path,
        translation_constraint_keys,
        path_elements,
        anchor_s_by_path_index,
    )
    rotation_constraint_spans = _build_combined_constraint_spans(
        path,
        rotation_constraint_keys,
        path_elements,
        anchor_s_by_path_index,
    )
    translation_constraint_positions_by_key = {
        key: _build_constraint_positions(path, key, path_elements, anchor_s_by_path_index)
        for key in translation_constraint_keys
    }
    rotation_constraint_positions_by_key = {
        key: _build_constraint_positions(path, key, path_elements, anchor_s_by_path_index)
        for key in rotation_constraint_keys
    }
    translation_constraint_display_ranges_by_key = {
        key: _build_constraint_display_ranges(translation_constraint_positions_by_key[key])
        for key in translation_constraint_keys
    }
    rotation_constraint_display_ranges_by_key = {
        key: _build_constraint_display_ranges(rotation_constraint_positions_by_key[key])
        for key in rotation_constraint_keys
    }
    rows.append(
        TimelineRow(
            title=TRANSLATION_CONSTRAINT_ROW_TITLE,
            empty_text="No translation ranges yet.",
            spans=translation_constraint_spans,
            lane_count=_lane_count_for_spans(translation_constraint_spans),
            constraint_keys=translation_constraint_keys,
            constraint_positions_by_key=translation_constraint_positions_by_key,
            constraint_display_ranges_by_key=translation_constraint_display_ranges_by_key,
        )
    )
    rows.append(
        TimelineRow(
            title=ROTATION_CONSTRAINT_ROW_TITLE,
            empty_text="No rotation ranges yet.",
            spans=rotation_constraint_spans,
            lane_count=_lane_count_for_spans(rotation_constraint_spans),
            constraint_keys=rotation_constraint_keys,
            constraint_positions_by_key=rotation_constraint_positions_by_key,
            constraint_display_ranges_by_key=rotation_constraint_display_ranges_by_key,
        )
    )

    display_s_m = max(total_s_m, 1.0 if structure_markers else 6.0)
    projection = TimelineProjection(
        total_s_m=total_s_m,
        display_s_m=display_s_m,
        summary_text="",
        rows=rows,
        axis_label="",
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
    spans: list[TimelineSpan] = []
    for rc_index, rc in enumerate(getattr(path, "ranged_constraints", []) or []):
        if getattr(rc, "key", "") != key:
            continue
        total = len(domain_positions)
        if total <= 0:
            continue
        start_ord = max(1, min(int(getattr(rc, "start_ordinal", 1)), total))
        end_ord = max(start_ord, min(int(getattr(rc, "end_ordinal", start_ord)), total))
        start_s, end_s = _constraint_display_range_from_positions(
            domain_positions,
            start_ord,
            end_ord,
        )
        unit = str(SPINNER_UNITS.get(key, "") or "")
        label = f"{float(getattr(rc, 'value', 0.0)):g}{unit}"
        spans.append(
            TimelineSpan(
                start_s_m=float(start_s),
                end_s_m=float(end_s),
                label=label,
                color=_constraint_color(key),
                constraint_index=rc_index,
                constraint_key=key,
                start_ordinal=start_ord,
                end_ordinal=end_ord,
            )
        )

    spans.sort(key=lambda span: (span.start_s_m, span.end_s_m))
    _assign_span_lanes(spans)
    return spans


def _build_constraint_positions(
    path: Path,
    key: str,
    path_elements: list[object],
    anchor_s_by_path_index: dict[int, float],
) -> list[float]:
    domain_elements = list(get_constraint_domain_elements(path, key))
    if not domain_elements:
        return []

    element_index_by_identity = {id(element): index for index, element in enumerate(path_elements)}
    domain_positions: list[float] = []
    for element in domain_elements:
        element_index = element_index_by_identity.get(id(element))
        if element_index is None:
            domain_positions.append(0.0)
            continue
        domain_positions.append(
            _element_global_s(element_index, element, path_elements, anchor_s_by_path_index)
        )
    return domain_positions


def _constraint_display_range_from_positions(
    positions: list[float],
    start_ordinal: int,
    end_ordinal: int,
) -> tuple[float, float]:
    """Return the effective applied span for a ranged constraint.

    Ranged constraints are selected by ordinal domain elements, but the path
    segment they affect starts at the previous domain position when one exists.
    This mirrors CanvasView.show_constraint_range_overlay().
    """
    if not positions:
        return 0.0, 0.0
    total = len(positions)
    start = max(1, min(int(start_ordinal), total))
    end = max(start, min(int(end_ordinal), total))
    start_index = max(0, start - 2 if start > 1 else start - 1)
    end_index = max(0, min(end - 1, total - 1))
    return float(positions[start_index]), float(positions[end_index])


def _constraint_display_indices_for_ordinals(
    positions: list[float],
    start_ordinal: int,
    end_ordinal: int,
) -> tuple[int, int] | None:
    if not positions:
        return None
    total = len(positions)
    start = max(1, min(int(start_ordinal), total))
    end = max(start, min(int(end_ordinal), total))
    start_index = max(0, start - 2 if start > 1 else start - 1)
    end_index = max(0, min(end - 1, total - 1))
    return int(start_index), int(end_index)


def _constraint_ordinals_for_display_indices(
    positions: list[float],
    start_index: int,
    end_index: int,
    *,
    preferred_start_ordinal: int,
) -> tuple[int, int] | None:
    if not positions:
        return None
    total = len(positions)
    display_start = max(0, min(int(start_index), total - 1))
    display_end = max(display_start, min(int(end_index), total - 1))

    end_ordinal = max(1, min(total, display_end + 1))
    if display_start == 0:
        if display_end == 0:
            start_ordinal = 1
        elif int(preferred_start_ordinal) == 1:
            start_ordinal = 1
        else:
            start_ordinal = 2
    else:
        start_ordinal = display_start + 2

    start_ordinal = max(1, min(int(start_ordinal), end_ordinal))
    return int(start_ordinal), int(end_ordinal)


def _constraint_move_range_for_display_start(
    positions: list[float],
    start_ordinal: int,
    end_ordinal: int,
    display_start_s_m: float,
) -> tuple[int, int] | None:
    """Move a ranged constraint by its visual left edge, preserving applied width.

    Ranged constraints use inclusive ordinals, but their visible span is the
    applied segment range. The first visible segment is ambiguous because both
    ordinal starts 1 and 2 can draw from the far-left edge; body moves should
    preserve the displayed clip width instead of falling into the shorter
    ordinal candidate at that boundary.
    """
    display_indices = _constraint_display_indices_for_ordinals(
        positions,
        start_ordinal,
        end_ordinal,
    )
    if display_indices is None:
        return None
    total = len(positions)
    origin_start_index, origin_end_index = display_indices
    display_width = max(0, int(origin_end_index) - int(origin_start_index))
    if display_width <= 0:
        return _constraint_move_range_for_s(
            positions,
            start_ordinal,
            end_ordinal,
            display_start_s_m,
        )

    max_start_index = max(0, total - 1 - display_width)
    target = float(display_start_s_m)
    candidate_start_index = min(
        range(max_start_index + 1),
        key=lambda index: (
            abs(target - float(positions[index])),
            abs(index - origin_start_index),
            index,
        ),
    )
    candidate_end_index = candidate_start_index + display_width
    return _constraint_ordinals_for_display_indices(
        positions,
        candidate_start_index,
        candidate_end_index,
        preferred_start_ordinal=int(start_ordinal),
    )


def _constraint_move_range_for_s(
    positions: list[float],
    start_ordinal: int,
    end_ordinal: int,
    s_m: float,
) -> tuple[int, int] | None:
    """Return the move target whose applied range contains or is nearest ``s_m``."""
    if not positions:
        return None
    total = len(positions)
    start = max(1, min(int(start_ordinal), total))
    end = max(start, min(int(end_ordinal), total))
    ordinal_width = max(0, end - start)
    max_start = max(1, total - ordinal_width)
    target_s = float(s_m)
    candidates: list[tuple[int, int, float, float]] = []
    for candidate_start in range(1, max_start + 1):
        candidate_end = min(total, candidate_start + ordinal_width)
        display_start, display_end = _constraint_display_range_from_positions(
            positions,
            candidate_start,
            candidate_end,
        )
        lo = min(display_start, display_end)
        hi = max(display_start, display_end)
        candidates.append((candidate_start, candidate_end, lo, hi))
    if not candidates:
        return None

    epsilon = 1e-9
    containing = [
        candidate
        for candidate in candidates
        if candidate[2] - epsilon <= target_s <= candidate[3] + epsilon
    ]
    if containing:
        best = min(
            containing,
            key=lambda candidate: (
                candidate[3] - candidate[2],
                abs(((candidate[2] + candidate[3]) / 2.0) - target_s),
                candidate[0],
            ),
        )
        return int(best[0]), int(best[1])

    best = min(
        candidates,
        key=lambda candidate: (
            min(abs(target_s - candidate[2]), abs(target_s - candidate[3])),
            abs(((candidate[2] + candidate[3]) / 2.0) - target_s),
            candidate[0],
        ),
    )
    return int(best[0]), int(best[1])


def _constraint_start_ordinal_for_s(
    positions: list[float],
    end_ordinal: int,
    s_m: float,
) -> int | None:
    """Return the start ordinal whose displayed left edge is nearest ``s_m``."""
    if not positions:
        return None
    total = len(positions)
    end = max(1, min(int(end_ordinal), total))
    target_s = float(s_m)
    candidates: list[tuple[int, float]] = []
    for candidate_start in range(1, end + 1):
        display_start, _ = _constraint_display_range_from_positions(
            positions,
            candidate_start,
            end,
        )
        candidates.append((candidate_start, float(display_start)))
    if not candidates:
        return None

    best = min(
        candidates,
        key=lambda candidate: (
            abs(target_s - candidate[1]),
            -candidate[0],
        ),
    )
    return int(best[0])


def _constraint_end_ordinal_for_s(positions: list[float], s_m: float) -> int | None:
    """Return the end ordinal whose displayed right edge is nearest ``s_m``."""
    if not positions:
        return None
    total = len(positions)
    if total <= 1:
        return 1
    target_s = float(s_m)
    best_index = min(
        range(total),
        key=lambda index: (
            abs(target_s - float(positions[index])),
            index,
        ),
    )
    return int(best_index + 1)


def _constraint_creation_range_for_s(
    positions: list[float],
    anchor_s_m: float,
    current_s_m: float,
) -> tuple[int, int] | None:
    """Convert a visual drag interval into ranged-constraint ordinals."""
    if not positions:
        return None
    if len(positions) <= 1:
        return 1, 1

    anchor = float(anchor_s_m)
    current = float(current_s_m)
    if math.isclose(anchor, current, abs_tol=1e-9):
        ordinal = _constraint_area_ordinal_for_s(positions, anchor, bias="right")
        if ordinal is None:
            return None
        return int(ordinal), int(ordinal)

    if current >= anchor:
        start_ordinal = _constraint_area_ordinal_for_s(positions, anchor, bias="right")
        end_ordinal = _constraint_area_ordinal_for_s(positions, current, bias="left")
    else:
        start_ordinal = _constraint_area_ordinal_for_s(positions, current, bias="right")
        end_ordinal = _constraint_area_ordinal_for_s(positions, anchor, bias="left")

    if start_ordinal is None or end_ordinal is None:
        return None
    if start_ordinal > end_ordinal:
        start_ordinal, end_ordinal = end_ordinal, start_ordinal
    return int(start_ordinal), int(end_ordinal)


def _constraint_area_ordinal_for_s(
    positions: list[float],
    s_m: float,
    *,
    bias: str,
) -> int | None:
    """Return the constraint ordinal for the potential segment area at ``s_m``."""
    if not positions:
        return None
    total = len(positions)
    if total <= 1:
        return 1

    target = float(s_m)
    first = float(positions[0])
    last = float(positions[-1])
    if target <= first:
        return 2
    if target >= last:
        return total

    right_index = bisect.bisect_left(positions, target)
    if right_index < total and math.isclose(target, float(positions[right_index]), abs_tol=1e-9):
        if bias == "right":
            return min(total, right_index + 2)
        return max(2, right_index + 1)

    return max(2, min(total, right_index + 1))


def _build_constraint_display_ranges(positions: list[float]) -> list[tuple[float, float]]:
    return [
        _constraint_display_range_from_positions(positions, ordinal, ordinal)
        for ordinal in range(1, len(positions) + 1)
    ]


def _build_combined_constraint_spans(
    path: Path,
    keys: list[str],
    path_elements: list[object],
    anchor_s_by_path_index: dict[int, float],
) -> list[TimelineSpan]:
    spans: list[TimelineSpan] = []
    for key in keys:
        spans.extend(_build_constraint_spans(path, key, path_elements, anchor_s_by_path_index))
    spans.sort(key=lambda span: (span.start_s_m, span.end_s_m, span.label))
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
    for rc_index, rc in enumerate(getattr(path, "ranged_constraints", []) or []):
        if getattr(rc, "key", "") != key:
            continue
        total = len(domain_positions)
        if total <= 0:
            continue
        start_ord = max(1, min(int(getattr(rc, "start_ordinal", 1)), total))
        end_ord = max(start_ord, min(int(getattr(rc, "end_ordinal", start_ord)), total))
        start_s, end_s = _constraint_display_range_from_positions(
            domain_positions,
            start_ord,
            end_ord,
        )
        unit = str(SPINNER_UNITS.get(key, "") or "")
        label = f"{float(getattr(rc, 'value', 0.0)):g}{unit}"
        spans.append(
            TimelineSpan(
                start_s_m=float(start_s),
                end_s_m=float(end_s),
                label=label,
                color=_constraint_color(key),
                constraint_index=rc_index,
                constraint_key=key,
                start_ordinal=start_ord,
                end_ordinal=end_ord,
            )
        )

    spans.sort(key=lambda span: (span.start_s_m, span.end_s_m))
    _assign_span_lanes(spans)
    return spans


def _build_combined_constraint_spans_for_axis(
    path: Path,
    keys: list[str],
    path_elements: list[object],
    *,
    mapper,
    sim_index: _SimTimeIndex | None,
) -> list[TimelineSpan]:
    spans: list[TimelineSpan] = []
    for key in keys:
        spans.extend(
            _build_constraint_spans_for_axis(
                path,
                key,
                path_elements,
                mapper=mapper,
                sim_index=sim_index,
            )
        )
    spans.sort(key=lambda span: (span.start_s_m, span.end_s_m, span.label))
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


def _constraint_color(key: str) -> str:
    return {
        "max_velocity_meters_per_sec": "#4ca5ff",
        "max_acceleration_meters_per_sec2": "#4fd1c5",
        "max_velocity_deg_per_sec": "#f59e7f",
        "max_acceleration_deg_per_sec2": "#d184ff",
    }.get(key, "#6f94b7")


def _constraint_key_label(key: str) -> str:
    meta = SPINNER_METADATA.get(str(key), {})
    label = _plain_label(str(meta.get("label", key)))
    return label or str(key)


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


def _format_time_value(time_s: float) -> str:
    return f"{max(0.0, float(time_s)):.2f}"


def _format_timecode(current_time_s: float, total_time_s: float) -> str:
    return f"{_format_time_value(current_time_s)} / {_format_time_value(total_time_s)} s"


def _transport_icon(is_playing: bool) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        if is_playing:
            painter.drawRoundedRect(QRectF(8.0, 6.0, 5.0, 20.0), 1.2, 1.2)
            painter.drawRoundedRect(QRectF(19.0, 6.0, 5.0, 20.0), 1.2, 1.2)
        else:
            triangle = QPolygonF(
                [
                    _qpointf(10.0, 6.0),
                    _qpointf(10.0, 26.0),
                    _qpointf(25.0, 16.0),
                ]
            )
            painter.drawPolygon(triangle)
    finally:
        painter.end()
    return QIcon(pixmap)


def _nice_ruler_step(px_per_m: float) -> float:
    target_px = 88.0
    for step in (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0):
        if step * float(px_per_m) >= target_px:
            return step
    return 100.0


def _minor_ruler_step(major_step: float) -> float:
    major = max(0.0, float(major_step))
    if major <= 0.0:
        return 0.0
    normalized = major
    while normalized >= 10.0:
        normalized /= 10.0
    while normalized < 1.0:
        normalized *= 10.0
    if math.isclose(normalized, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        return major / 5.0
    return major / 4.0


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
        constraint_keys = _constraint_row_keys(row)
        if constraint_keys:
            row.constraint_positions_by_key = {}
            row.constraint_display_ranges_by_key = {}
            path_elements = list(getattr(path, "path_elements", []) or [])
            for key in constraint_keys:
                positions = _constraint_domain_axis_positions(
                    path,
                    key,
                    path_elements,
                    mapper=mapper,
                    sim_index=sim_index,
                )
                row.constraint_positions_by_key[str(key)] = positions
                row.constraint_display_ranges_by_key[str(key)] = _build_constraint_display_ranges(
                    positions
                )
            row.spans = _build_combined_constraint_spans_for_axis(
                path,
                constraint_keys,
                path_elements,
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


def _resolve_path_axis_position_for_time(
    path: Path,
    config: dict[str, object] | None,
    time_s: float,
    *,
    use_sim_time: bool = True,
) -> tuple[dict[str, object], float, float, float, float]:
    path = path or Path()
    path_elements = list(getattr(path, "path_elements", []) or [])
    anchor_data = _build_anchor_distances(path_elements)
    total_path_s = max(0.0, float(anchor_data.get("total_s_m", 0.0)))
    display_s = max(total_path_s, 1.0)
    projection = TimelineProjection(
        total_s_m=total_path_s,
        display_s_m=display_s,
        summary_text="",
        rows=[],
    )
    mapper, total_t, sim_index = _build_time_mapper(
        path=path,
        projection=projection,
        config=dict(config or {}),
        use_sim_time=use_sim_time,
    )

    requested_time_s = float(time_s)
    target_time_s = max(0.0, min(requested_time_s, float(max(total_t, 0.0))))
    if sim_index is not None and len(sim_index.sample_t) >= 2:
        sample_t = sim_index.sample_t
        sample_s = sim_index.sample_s
        idx = bisect.bisect_left(sample_t, target_time_s)
        if idx <= 0:
            target_s = float(sample_s[0])
        elif idx >= len(sample_t):
            target_s = float(sample_s[-1])
        else:
            t0 = float(sample_t[idx - 1])
            t1 = float(sample_t[idx])
            s0 = float(sample_s[idx - 1])
            s1 = float(sample_s[idx])
            if t1 <= t0 + 1e-9:
                target_s = s0
            else:
                alpha = (target_time_s - t0) / (t1 - t0)
                target_s = s0 + alpha * (s1 - s0)
    else:
        default_v = _safe_positive(
            dict(config or {}).get("default_max_velocity_meters_per_sec", 4.5),
            fallback=4.5,
        )
        target_s = target_time_s * default_v
        if total_path_s > 1e-9:
            target_s = max(0.0, min(float(target_s), float(total_path_s)))
        else:
            target_s = float(mapper(0.0))

    return anchor_data, float(target_s), float(total_path_s), float(total_t), requested_time_s


def _anchor_position(
    path_elements: list[object],
    index: int,
) -> tuple[float, float] | None:
    if index < 0 or index >= len(path_elements):
        return None
    element = path_elements[index]
    if isinstance(element, TranslationTarget):
        return float(element.x_meters), float(element.y_meters)
    if isinstance(element, Waypoint):
        return (
            float(element.translation_target.x_meters),
            float(element.translation_target.y_meters),
        )
    return None


def resolve_structure_placement_for_time(
    path: Path,
    config: dict[str, object] | None,
    time_s: float,
    element_type: str,
    *,
    use_sim_time: bool = True,
) -> StructurePlacement | None:
    element_type = str(element_type)
    if element_type not in STRUCTURE_ADD_TYPES:
        return None

    path = path or Path()
    path_elements = list(getattr(path, "path_elements", []) or [])
    anchor_data, target_s, total_path_s, total_t, requested_time_s = (
        _resolve_path_axis_position_for_time(
            path,
            config,
            time_s,
            use_sim_time=use_sim_time,
        )
    )
    anchor_indices = [int(index) for index in list(anchor_data.get("anchor_indices", []) or [])]
    anchor_s_by_path_index = dict(anchor_data.get("anchor_s_by_path_index", {}) or {})

    if element_type in {"translation", "waypoint"}:
        if not anchor_indices:
            return StructurePlacement(insert_index=0)
        if len(anchor_indices) == 1:
            anchor_pos = _anchor_position(path_elements, anchor_indices[0])
            insert_index = 0 if requested_time_s <= 0.0 else anchor_indices[0] + 1
            return StructurePlacement(
                insert_index=int(insert_index),
                x_m=None if anchor_pos is None else float(anchor_pos[0]),
                y_m=None if anchor_pos is None else float(anchor_pos[1]),
            )

        first_anchor = anchor_indices[0]
        last_anchor = anchor_indices[-1]
        first_s = float(anchor_s_by_path_index.get(first_anchor, 0.0))
        last_s = float(anchor_s_by_path_index.get(last_anchor, total_path_s))
        if target_s <= first_s + 1e-9:
            anchor_pos = _anchor_position(path_elements, first_anchor)
            return StructurePlacement(
                insert_index=int(first_anchor),
                x_m=None if anchor_pos is None else float(anchor_pos[0]),
                y_m=None if anchor_pos is None else float(anchor_pos[1]),
            )
        if target_s >= last_s - 1e-9:
            anchor_pos = _anchor_position(path_elements, last_anchor)
            return StructurePlacement(
                insert_index=int(last_anchor) + 1,
                x_m=None if anchor_pos is None else float(anchor_pos[0]),
                y_m=None if anchor_pos is None else float(anchor_pos[1]),
            )

    if len(anchor_indices) < 2:
        return None
    if element_type == "rotation" and requested_time_s > max(0.0, total_t) + 1e-9:
        return None

    anchor_s_by_path_index = dict(anchor_data.get("anchor_s_by_path_index", {}) or {})
    segment_start_index = anchor_indices[0]
    segment_end_index = anchor_indices[1]
    segment_start_s = float(anchor_s_by_path_index.get(segment_start_index, 0.0))
    segment_end_s = float(anchor_s_by_path_index.get(segment_end_index, segment_start_s))

    for anchor_idx in range(len(anchor_indices) - 1):
        start_idx = int(anchor_indices[anchor_idx])
        end_idx = int(anchor_indices[anchor_idx + 1])
        start_s = float(anchor_s_by_path_index.get(start_idx, 0.0))
        end_s = float(anchor_s_by_path_index.get(end_idx, start_s))
        segment_start_index = start_idx
        segment_end_index = end_idx
        segment_start_s = start_s
        segment_end_s = end_s
        if target_s <= end_s + 1e-9 or anchor_idx == len(anchor_indices) - 2:
            break

    seg_len = max(0.0, segment_end_s - segment_start_s)
    if seg_len <= 1e-9:
        t_ratio = 0.0
    else:
        t_ratio = (float(target_s) - segment_start_s) / seg_len
    t_ratio = max(0.0, min(1.0, float(t_ratio)))

    if element_type == "rotation":
        return StructurePlacement(insert_index=int(segment_end_index), t_ratio=t_ratio)

    start_pos = _anchor_position(path_elements, int(segment_start_index))
    end_pos = _anchor_position(path_elements, int(segment_end_index))
    if start_pos is None or end_pos is None:
        return StructurePlacement(insert_index=int(segment_end_index))
    x_m = float(start_pos[0]) + (float(end_pos[0]) - float(start_pos[0])) * t_ratio
    y_m = float(start_pos[1]) + (float(end_pos[1]) - float(start_pos[1])) * t_ratio
    return StructurePlacement(insert_index=int(segment_end_index), x_m=x_m, y_m=y_m)


def resolve_trigger_placement_for_time(
    path: Path,
    config: dict[str, object] | None,
    time_s: float,
    *,
    use_sim_time: bool = True,
) -> TriggerPlacement | None:
    path = path or Path()
    path_elements = list(getattr(path, "path_elements", []) or [])
    anchor_data, target_s, _total_path_s, _total_t, _requested_time_s = (
        _resolve_path_axis_position_for_time(
            path,
            config,
            time_s,
            use_sim_time=use_sim_time,
        )
    )
    anchor_indices = list(anchor_data.get("anchor_indices", []) or [])
    if len(anchor_indices) < 2:
        return None
    anchor_s_by_path_index = dict(anchor_data.get("anchor_s_by_path_index", {}) or {})
    segment_start_index = anchor_indices[0]
    segment_end_index = anchor_indices[1]
    segment_start_s = float(anchor_s_by_path_index.get(segment_start_index, 0.0))
    segment_end_s = float(anchor_s_by_path_index.get(segment_end_index, segment_start_s))

    for anchor_idx in range(len(anchor_indices) - 1):
        start_idx = int(anchor_indices[anchor_idx])
        end_idx = int(anchor_indices[anchor_idx + 1])
        start_s = float(anchor_s_by_path_index.get(start_idx, 0.0))
        end_s = float(anchor_s_by_path_index.get(end_idx, start_s))
        segment_start_index = start_idx
        segment_end_index = end_idx
        segment_start_s = start_s
        segment_end_s = end_s
        if target_s <= end_s + 1e-9 or anchor_idx == len(anchor_indices) - 2:
            break

    seg_len = max(0.0, segment_end_s - segment_start_s)
    if seg_len <= 1e-9:
        t_ratio = 0.0
    else:
        t_ratio = (float(target_s) - segment_start_s) / seg_len
    t_ratio = max(0.0, min(1.0, float(t_ratio)))

    return TriggerPlacement(insert_index=int(segment_end_index), t_ratio=t_ratio)


def _safe_positive(value, *, fallback: float) -> float:
    try:
        parsed = float(value)
        if parsed > 1e-9:
            return parsed
    except Exception:
        pass
    return float(fallback)
