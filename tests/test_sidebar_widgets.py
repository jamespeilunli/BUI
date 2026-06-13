from __future__ import annotations

from PySide6.QtGui import QColor

from ui.sidebar.widgets.range_slider import RangeSlider
from ui.sidebar.widgets.segment_bar import SegmentBar, SegmentData


def test_range_slider_clamps_values_and_enforces_minimum_separation(qt_app):
    slider = RangeSlider(1, 5)
    try:
        changes: list[tuple[int, int]] = []
        slider.rangeChanged.connect(lambda low, high: changes.append((low, high)))

        slider.setMinimumSeparation(2)
        slider.setValues(5, 1)

        assert slider.values() == (1, 5)

        slider.setValues(4, 4)
        assert slider.values() == (3, 5)
        assert changes[-1] == (3, 5)

        slider.setRange(2, 3)
        assert slider.values() == (2, 3)
    finally:
        slider.close()


def test_range_slider_pixel_mapping_round_trips_inside_bounds(qt_app):
    slider = RangeSlider(0, 10)
    try:
        slider.resize(220, 48)

        for value in (0, 5, 10):
            x = slider._value_to_pos(value)
            assert abs(slider._pos_to_value(x) - value) <= 1

        assert slider._pos_to_value(-100) == 0
        assert slider._pos_to_value(10_000) == 10
    finally:
        slider.close()


def test_segment_bar_gap_and_hit_helpers_respect_scroll_offset(qt_app):
    bar = SegmentBar()
    try:
        bar.resize(160, 48)
        bar.set_domain_size(4)
        bar.set_segments(
            [
                SegmentData(1, 1, 2.0, QColor("#ff0000")),
                SegmentData(3, 3, 3.0, QColor("#00ff00")),
            ]
        )

        assert bar._covered_ordinals() == {1, 3}
        assert bar._find_gap_at_ordinal(2) == (2, 2)
        assert bar._find_gap_at_ordinal(4) == (4, 4)
        assert bar._find_gap_at_ordinal(1) is None

        assert bar._hit_test_segment(int(bar._ordinal_to_x(1) + 4)) == 0
        assert bar._hit_test_segment(int(bar._ordinal_to_x(3) + 4)) == 1
        assert bar._hit_test_gap(int(bar._ordinal_to_x(2) + 4)) == (2, 2)

        bar._scroll_offset = 20
        assert bar._x_to_ordinal(int(bar._ordinal_to_x(3) + 4)) == 3
    finally:
        bar.close()


def test_segment_bar_selection_emits_only_on_change(qt_app):
    bar = SegmentBar()
    try:
        selections: list[int] = []
        bar.segmentSelected.connect(selections.append)

        bar.set_selected_index(0)
        bar.set_selected_index(0)
        bar.set_selected_index(-1)

        assert selections == [0, -1]
        assert bar.selected_index() == -1
    finally:
        bar.close()
