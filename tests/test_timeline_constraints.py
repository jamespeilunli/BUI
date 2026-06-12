from __future__ import annotations

import math

import pytest

from models.path_model import (
    EventTrigger,
    Path,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from ui.timeline.placeholder import (
    TimelineDock,
    _build_projection,
    _constraint_creation_range_for_s,
    _constraint_move_range_for_display_start,
    _constraint_move_range_for_s,
    _constraint_start_ordinal_for_s,
    resolve_structure_placement_for_time,
)
from ui.qt_compat import Qt


def _path_with_constraints() -> Path:
    return Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(2.0, 0.0),
            TranslationTarget(4.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.0,
                start_ordinal=1,
                end_ordinal=1,
            ),
            RangedConstraint(
                key="max_acceleration_meters_per_sec2",
                value=3.0,
                start_ordinal=2,
                end_ordinal=3,
            ),
        ],
    )


def test_constraints_remain_on_single_combined_row():
    projection = _build_projection(_path_with_constraints(), {}, use_sim_time=False)

    constraint_rows = [row for row in projection.rows if row.title == "Constraints"]
    assert len(constraint_rows) == 1

    row = constraint_rows[0]
    assert len(row.spans) == 2
    assert {span.constraint_key for span in row.spans} == {
        "max_velocity_meters_per_sec",
        "max_acceleration_meters_per_sec2",
    }
    assert [span.constraint_index for span in row.spans] == [0, 1]
    assert "max_velocity_meters_per_sec" in row.constraint_positions_by_key
    assert all(
        math.isclose(actual, expected)
        for actual, expected in zip(
            row.constraint_positions_by_key["max_velocity_meters_per_sec"],
            [0.0, 2.0 / 4.5, 4.0 / 4.5],
        )
    )


def test_constraint_span_edges_align_to_domain_positions():
    projection = _build_projection(_path_with_constraints(), {}, use_sim_time=False)
    row = next(row for row in projection.rows if row.title == "Constraints")
    span = next(span for span in row.spans if span.constraint_key == "max_acceleration_meters_per_sec2")
    positions = row.constraint_positions_by_key["max_acceleration_meters_per_sec2"]

    # The displayed bar shows the effective path segment affected by the
    # ordinal range, so a range starting at T2 begins at the segment before T2.
    assert span.start_s_m == positions[span.start_ordinal - 2]
    assert span.end_s_m == positions[span.end_ordinal - 1]


def test_constraint_move_drop_zones_follow_applied_ranges():
    positions = [0.0, 1.0, 2.0, 3.0]

    assert _constraint_move_range_for_s(positions, 2, 2, 0.25) == (2, 2)
    assert _constraint_move_range_for_s(positions, 2, 2, 1.25) == (3, 3)
    assert _constraint_move_range_for_s(positions, 2, 2, 2.25) == (4, 4)

    assert _constraint_move_range_for_s(positions, 2, 3, 0.5) == (1, 2)
    assert _constraint_move_range_for_s(positions, 2, 3, 2.5) == (3, 4)


def test_constraint_body_move_preserves_visual_width_at_left_edge():
    positions = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]

    assert _constraint_move_range_for_display_start(positions, 3, 5, -10.0) == (2, 4)


def test_constraint_body_move_from_left_edge_preserves_visual_width_when_dragged_right():
    positions = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]

    assert _constraint_move_range_for_display_start(positions, 2, 4, 1.1) == (3, 5)


def test_constraint_body_drag_uses_press_offset_to_avoid_large_jump(qt_app):
    key = "max_velocity_meters_per_sec"
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(1.0, 0.0),
            TranslationTarget(2.0, 0.0),
            TranslationTarget(3.0, 0.0),
            TranslationTarget(4.0, 0.0),
            TranslationTarget(5.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(key=key, value=2.0, start_ordinal=3, end_ordinal=5),
        ],
    )
    dock = TimelineDock(path)
    canvas = dock._track_canvas
    row = next(row for row in dock._projection.rows if row.title == "Constraints")
    span = row.spans[0]
    display_start, display_end = span.start_s_m, span.end_s_m
    press_s = display_end - 0.1
    canvas._pressed_constraint_span = span
    canvas._pressed_constraint_action = "move"
    canvas._pressed_constraint_origin = (3, 5)
    canvas._pressed_constraint_preview = (3, 5)
    canvas._pressed_constraint_preview_valid = True
    canvas._pressed_constraint_move_press_s_m = press_s
    canvas._pressed_constraint_move_origin_bounds = (display_start, display_end)

    canvas._update_constraint_drag_preview(canvas._x_for_s(press_s + 0.02))

    assert canvas._pressed_constraint_preview == (3, 5)


def test_constraint_left_resize_snaps_to_displayed_start_edges():
    positions = [0.0, 1.0, 2.0, 3.0]

    assert _constraint_start_ordinal_for_s(positions, 4, 0.1) == 2
    assert _constraint_start_ordinal_for_s(positions, 4, 1.1) == 3
    assert _constraint_start_ordinal_for_s(positions, 4, 2.1) == 4


def test_constraint_creation_uses_visual_drag_interval():
    positions = [0.0, 1.0, 2.0, 3.0]

    assert _constraint_creation_range_for_s(positions, 1.0, 2.0) == (3, 3)
    assert _constraint_creation_range_for_s(positions, 2.0, 1.0) == (3, 3)
    assert _constraint_creation_range_for_s(positions, 1.0, 3.0) == (3, 4)
    assert _constraint_creation_range_for_s(positions, 0.0, 1.0) == (2, 2)
    assert _constraint_creation_range_for_s(positions, 1.5, 1.5) == (3, 3)
    assert _constraint_creation_range_for_s(positions, 1.0, 1.0) == (3, 3)


def test_same_key_overlap_is_rejected_but_other_keys_can_overlap(qt_app):
    dock = TimelineDock(_path_with_constraints())
    row = next(row for row in dock._projection.rows if row.title == "Constraints")

    assert not dock._track_canvas._constraint_range_available(
        row,
        "max_velocity_meters_per_sec",
        1,
        2,
    )
    assert dock._track_canvas._constraint_range_available(
        row,
        "max_velocity_meters_per_sec",
        2,
        3,
    )
    assert dock._track_canvas._constraint_range_available(
        row,
        "max_acceleration_meters_per_sec2",
        1,
        2,
        ignore_index=1,
    )


def test_constraint_hover_feedback_uses_move_and_resize_cursors(qt_app):
    dock = TimelineDock(_path_with_constraints())
    canvas = dock._track_canvas
    canvas.resize(520, 220)
    row = next(row for row in dock._projection.rows if row.title == "Constraints")
    row_top, row_h = next(
        layout
        for projection_row, layout in zip(dock._projection.rows, canvas._row_layout())
        if projection_row is row
    )
    track_rect = canvas._track_rect_for_row(row_top, row_h)
    span, rect = next(canvas._iter_span_rects(row, track_rect))

    canvas._update_hover_feedback(rect.center().x(), rect.center().y())
    assert canvas.cursor().shape() == Qt.OpenHandCursor
    assert canvas._is_span_hovered(span)
    assert canvas.toolTip().startswith("Move - ")

    canvas._update_hover_feedback(rect.left() + 1.0, rect.center().y())
    assert canvas.cursor().shape() == Qt.SizeHorCursor
    assert canvas._hover_span_edge(span, "start")
    assert canvas.toolTip().startswith("Resize start - ")


def test_invalid_constraint_drag_preview_is_kept_for_feedback(qt_app):
    key = "max_velocity_meters_per_sec"
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(2.0, 0.0),
            TranslationTarget(4.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(key=key, value=2.0, start_ordinal=1, end_ordinal=1),
            RangedConstraint(key=key, value=2.5, start_ordinal=3, end_ordinal=3),
        ],
    )
    dock = TimelineDock(path)
    canvas = dock._track_canvas
    row = next(row for row in dock._projection.rows if row.title == "Constraints")
    span = next(span for span in row.spans if span.constraint_key == key and span.start_ordinal == 1)
    positions = row.constraint_positions_by_key[key]

    canvas._pressed_constraint_span = span
    canvas._pressed_constraint_action = "move"
    canvas._pressed_constraint_origin = (1, 1)
    canvas._pressed_constraint_preview = (1, 1)
    canvas._pressed_constraint_preview_valid = True

    canvas._update_constraint_drag_preview(canvas._x_for_s(positions[2]))

    assert canvas._pressed_constraint_preview == (3, 3)
    assert not canvas._pressed_constraint_preview_valid


@pytest.mark.parametrize("path_index", [0, 1, 2, 3])
def test_timeline_path_selection_delete_emits_generic_path_delete(qt_app, path_index):
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            Waypoint(
                translation_target=TranslationTarget(2.0, 0.0),
                rotation_target=RotationTarget(rotation_radians=0.2, t_ratio=0.0),
            ),
            RotationTarget(rotation_radians=0.5, t_ratio=0.4),
            EventTrigger(t_ratio=0.6, lib_key="score"),
            TranslationTarget(4.0, 0.0),
        ],
    )
    dock = TimelineDock(path)
    path_deletes: list[int] = []
    dock.pathItemDeleteRequested.connect(path_deletes.append)

    dock.select_path_index(path_index)
    dock._on_delete_selection_requested()

    assert path_deletes == [path_index]


def test_timeline_constraint_selection_delete_keeps_range_delete_route(qt_app):
    dock = TimelineDock(_path_with_constraints())
    path_deletes: list[int] = []
    constraint_deletes: list[tuple[int, str, int, int]] = []
    dock.pathItemDeleteRequested.connect(path_deletes.append)
    dock.constraintRangeDeleteRequested.connect(
        lambda index, key, start, end: constraint_deletes.append((index, key, start, end))
    )

    dock.select_constraint_range("max_acceleration_meters_per_sec2", 2, 3)
    dock._on_delete_selection_requested()

    assert path_deletes == []
    assert constraint_deletes == [(1, "max_acceleration_meters_per_sec2", 2, 3)]


def test_structure_translation_placement_interpolates_between_anchors():
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(4.0, 2.0),
        ],
    )

    placement = resolve_structure_placement_for_time(
        path,
        {},
        (math.hypot(4.0, 2.0) / 2.0) / 4.5,
        "translation",
        use_sim_time=False,
    )

    assert placement is not None
    assert placement.insert_index == 1
    assert math.isclose(placement.x_m, 2.0)
    assert math.isclose(placement.y_m, 1.0)


def test_structure_waypoint_can_be_inserted_after_single_anchor():
    path = Path(path_elements=[TranslationTarget(1.0, 2.0)])

    placement = resolve_structure_placement_for_time(
        path,
        {},
        0.5,
        "waypoint",
        use_sim_time=False,
    )

    assert placement is not None
    assert placement.insert_index == 1
    assert math.isclose(placement.x_m, 1.0)
    assert math.isclose(placement.y_m, 2.0)


def test_structure_rotation_requires_two_anchors():
    path = Path(path_elements=[TranslationTarget(1.0, 2.0)])

    assert (
        resolve_structure_placement_for_time(
            path,
            {},
            0.0,
            "rotation",
            use_sim_time=False,
        )
        is None
    )


def test_structure_rotation_placement_uses_segment_ratio():
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(4.0, 0.0),
        ],
    )

    placement = resolve_structure_placement_for_time(
        path,
        {},
        1.0 / 4.5,
        "rotation",
        use_sim_time=False,
    )

    assert placement is not None
    assert placement.insert_index == 1
    assert math.isclose(placement.t_ratio, 0.25)


def test_structure_rotation_is_invalid_after_real_path_end():
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(1.0, 0.0),
        ],
    )

    assert (
        resolve_structure_placement_for_time(
            path,
            {},
            0.5,
            "rotation",
            use_sim_time=False,
        )
        is None
    )
