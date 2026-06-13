from __future__ import annotations

import math

from models.path_model import EventTrigger, Path, RangedConstraint, RotationTarget, TranslationTarget
from models.simulation import (
    ChassisSpeeds,
    limit_acceleration,
    shortest_angular_distance,
    simulate_path,
    wrap_angle_radians,
)


def test_simulate_path_generates_trail():
    path = Path()
    path.path_elements.append(TranslationTarget(x_meters=0.0, y_meters=0.0))
    path.path_elements.append(TranslationTarget(x_meters=3.0, y_meters=1.0))

    config = {
        "default_max_velocity_meters_per_sec": 2.0,
        "default_max_acceleration_meters_per_sec2": 4.0,
        "default_max_velocity_deg_per_sec": 90.0,
        "default_max_acceleration_deg_per_sec2": 180.0,
    }

    result = simulate_path(path, config, dt_s=0.01)

    assert result.total_time_s > 0.0
    assert result.trail_points
    assert 0.0 in result.poses_by_time


def test_angle_helpers_wrap_and_choose_shortest_direction():
    assert math.isclose(wrap_angle_radians(3 * math.pi), math.pi)
    assert math.isclose(wrap_angle_radians(-3 * math.pi), -math.pi)
    assert math.isclose(shortest_angular_distance(math.pi, -math.pi + 0.1), -0.1)


def test_limit_acceleration_clamps_delta_magnitude():
    limited = limit_acceleration(
        ChassisSpeeds(vx_mps=10.0, vy_mps=0.0, omega_radps=5.0),
        ChassisSpeeds(vx_mps=0.0, vy_mps=0.0, omega_radps=0.0),
        0.5,
        2.0,
        4.0,
    )
    assert math.isclose(limited.vx_mps, 1.0)
    assert math.isclose(limited.vy_mps, 0.0)
    assert math.isclose(limited.omega_radps, 2.0)

    unchanged = limit_acceleration(
        ChassisSpeeds(vx_mps=10.0, vy_mps=0.0, omega_radps=5.0),
        ChassisSpeeds(vx_mps=1.0, vy_mps=2.0, omega_radps=3.0),
        0.0,
        2.0,
        4.0,
    )
    assert unchanged == ChassisSpeeds(vx_mps=1.0, vy_mps=2.0, omega_radps=3.0)


def test_simulation_applies_translation_and_rotation_ranged_constraints():
    fast = {
        "default_max_velocity_meters_per_sec": 4.0,
        "default_max_acceleration_meters_per_sec2": 20.0,
        "default_max_velocity_deg_per_sec": 360.0,
        "default_max_acceleration_deg_per_sec2": 720.0,
    }
    constrained = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            RotationTarget(rotation_radians=math.pi, t_ratio=0.5),
            EventTrigger(t_ratio=0.75, lib_key="event"),
            TranslationTarget(4.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=1.0,
                start_ordinal=1,
                end_ordinal=2,
            ),
            RangedConstraint(
                key="max_velocity_deg_per_sec",
                value=45.0,
                start_ordinal=1,
                end_ordinal=2,
            ),
        ],
    )
    unconstrained = Path(path_elements=constrained.path_elements.copy())

    constrained_result = simulate_path(constrained, fast, dt_s=0.02)
    unconstrained_result = simulate_path(unconstrained, fast, dt_s=0.02)

    assert constrained_result.total_time_s > unconstrained_result.total_time_s
    assert constrained_result.progress_by_time
