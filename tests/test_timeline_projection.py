from __future__ import annotations

import math
from types import SimpleNamespace

from models.path_model import (
    EventTrigger,
    Path,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from ui.timeline.placeholder import (
    HEADER_WIDTH,
    ROTATION_CONSTRAINT_ROW_TITLE,
    TIMELINE_MAX_TIME_S,
    TRACK_PADDING_X,
    TimelineDock,
    TRANSLATION_CONSTRAINT_ROW_TITLE,
    _assign_span_lanes,
    _build_projection,
    _closest_time_for_point,
    _format_axis_label,
    _minor_ruler_step,
    _nice_ruler_step,
    TimelineSpan,
)


def _constraint_row_for_key(projection, key: str):
    return next(row for row in projection.rows if str(key) in row.constraint_positions_by_key)


def _axis_path() -> Path:
    return Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            Waypoint(translation_target=TranslationTarget(2.0, 0.0)),
            RotationTarget(rotation_radians=0.5, t_ratio=0.5),
            EventTrigger(t_ratio=0.25, lib_key="intake"),
            TranslationTarget(6.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=3.0,
                start_ordinal=2,
                end_ordinal=3,
            )
        ],
    )


def test_projection_uses_configured_fallback_velocity_for_time_axis():
    projection = _build_projection(
        _axis_path(),
        {"default_max_velocity_meters_per_sec": 2.0},
        use_sim_time=False,
    )

    structure = next(row for row in projection.rows if row.title == "Structure")
    triggers = next(row for row in projection.rows if row.title == "Triggers")
    constraints = _constraint_row_for_key(projection, "max_velocity_meters_per_sec")

    assert projection.axis_label == ""
    assert projection.axis_unit == "s"
    assert math.isclose(projection.total_s_m, 3.0)
    assert math.isclose(projection.display_s_m, TIMELINE_MAX_TIME_S)
    assert [marker.label for marker in structure.markers] == ["T1", "W1", "R1", "T2"]
    assert [round(marker.s_m, 4) for marker in structure.markers] == [0.0, 1.0, 2.0, 3.0]
    assert triggers.markers[0].label == "intake"
    assert math.isclose(triggers.markers[0].s_m, 1.5)
    assert constraints.spans[0].start_s_m <= constraints.spans[0].end_s_m


def test_projection_uses_simulation_time_when_available(monkeypatch):
    def fake_simulate_path(path, config, dt_s):
        return SimpleNamespace(
            times_sorted=[0.0, 2.0, 10.0],
            poses_by_time={
                0.0: (0.0, 0.0, 0.0),
                2.0: (2.0, 0.0, 0.0),
                10.0: (6.0, 0.0, 0.0),
            },
            progress_by_time={0.0: 0.0, 2.0: 2.0, 10.0: 6.0},
        )

    monkeypatch.setattr("ui.timeline.placeholder.simulate_path", fake_simulate_path)

    projection = _build_projection(_axis_path(), {}, use_sim_time=True)
    structure = next(row for row in projection.rows if row.title == "Structure")
    constraints = _constraint_row_for_key(projection, "max_velocity_meters_per_sec")

    assert math.isclose(projection.total_s_m, 10.0)
    assert math.isclose(structure.markers[1].s_m, 2.0)
    assert math.isclose(structure.markers[-1].s_m, 10.0)
    assert constraints.constraint_positions_by_key["max_velocity_meters_per_sec"] == [
        0.0,
        2.0,
        10.0,
    ]


def test_projection_falls_back_when_simulation_samples_are_unusable(monkeypatch):
    monkeypatch.setattr(
        "ui.timeline.placeholder.simulate_path",
        lambda path, config, dt_s: SimpleNamespace(
            times_sorted=[0.0],
            poses_by_time={},
            progress_by_time={},
        ),
    )

    projection = _build_projection(
        _axis_path(),
        {"default_max_velocity_meters_per_sec": 3.0},
        use_sim_time=True,
    )

    assert math.isclose(projection.total_s_m, 2.0)
    assert math.isclose(projection.display_s_m, TIMELINE_MAX_TIME_S)


def test_closest_time_for_point_limits_candidates_by_expected_progress():
    sim_index = SimpleNamespace(
        sample_t=[0.0, 1.0, 2.0],
        sample_s=[0.0, 5.0, 10.0],
        sample_x=[0.0, 100.0, 0.0],
        sample_y=[0.0, 0.0, 0.0],
    )

    assert _closest_time_for_point(sim_index, 0.0, 0.0, expected_s=0.0) == 0.0
    assert _closest_time_for_point(sim_index, 0.0, 0.0, expected_s=10.0) == 2.0


def test_ruler_label_density_helpers_are_stable():
    assert _nice_ruler_step(1000.0) == 0.1
    assert _nice_ruler_step(44.0) == 2.0
    assert math.isclose(_minor_ruler_step(0.1), 0.02)
    assert math.isclose(_minor_ruler_step(2.0), 0.5)
    assert _format_axis_label(1.25, 0.5, "s") == "1.2 s"
    assert _format_axis_label(12.0, 2.0, "s") == "12 s"


def test_span_lanes_stack_only_true_overlaps():
    spans = [
        TimelineSpan(0.0, 1.0, "A", "#fff"),
        TimelineSpan(1.0, 2.0, "B", "#fff"),
        TimelineSpan(0.5, 1.5, "C", "#fff"),
    ]

    _assign_span_lanes(spans)

    assert spans[0].lane == 0
    assert spans[1].lane == 0
    assert spans[2].lane == 1


def test_timeline_canvas_geometry_keeps_header_and_track_alignment(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock.resize(720, 260)
        dock._sync_canvas_size()

        assert dock._rail_scroll.width() == HEADER_WIDTH
        assert dock._track_canvas._track_left() == float(TRACK_PADDING_X)
        assert dock._track_canvas._x_for_s(0.0) == float(TRACK_PADDING_X)
        assert math.isclose(dock._projection.display_s_m, TIMELINE_MAX_TIME_S)
        assert math.isclose(dock._track_canvas._ruler_end_s(), TIMELINE_MAX_TIME_S)

        rows = dock._projection.rows
        layout = dock._track_canvas._row_layout()
        assert len(layout) == len(rows)
        assert all(height > 0 for _top, height in layout)

        assert [row.title for row in rows[-2:]] == [
            TRANSLATION_CONSTRAINT_ROW_TITLE,
            ROTATION_CONSTRAINT_ROW_TITLE,
        ]
        constraints = _constraint_row_for_key(dock._projection, "max_velocity_meters_per_sec")
        row_top, row_height = next(
            row_layout
            for row, row_layout in zip(rows, layout)
            if row is constraints
        )
        track_rect = dock._track_canvas._track_rect_for_row(row_top, row_height)
        lane_count, _gap, lane_height, lanes_top = dock._track_canvas._lane_metrics(
            constraints,
            track_rect,
        )

        assert lane_count == constraints.lane_count
        assert lane_height > 0.0
        assert track_rect.top() <= lanes_top <= track_rect.bottom()
    finally:
        dock.close()


def test_timeline_rail_paints_domain_specific_constraint_add_state(qt_app, mixed_path):
    dock = TimelineDock(mixed_path)
    try:
        dock.resize(720, 260)
        dock._sync_canvas_size()
        dock._apply_constraint_add_armed(True, "max_velocity_deg_per_sec")

        pixmap = dock._rail_canvas.grab()

        assert not pixmap.isNull()
    finally:
        dock.close()
