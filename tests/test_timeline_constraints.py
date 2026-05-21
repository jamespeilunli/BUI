from __future__ import annotations

import math

from models.path_model import Path, RangedConstraint, TranslationTarget
from ui.timeline.placeholder import (
    TimelineDock,
    _build_projection,
    _constraint_creation_range_for_s,
    _constraint_move_range_for_s,
    _constraint_start_ordinal_for_s,
)


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
