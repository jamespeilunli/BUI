from __future__ import annotations

from pathlib import Path

from models.path_model import (
    EventTrigger,
    Path as PathModel,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from utils.project_io import deserialize_path, serialize_path


def test_serialize_deserialize_round_trip(tmp_path: Path):
    path = PathModel()
    path.path_elements.append(TranslationTarget(x_meters=0.0, y_meters=0.0))
    path.path_elements.append(RotationTarget(rotation_radians=0.5, t_ratio=0.5))
    path.path_elements.append(TranslationTarget(x_meters=2.0, y_meters=1.0))

    data = serialize_path(path)
    restored = deserialize_path(
        data, lambda key: 0.1 if key == "intermediate_handoff_radius_meters" else None
    )

    assert len(restored.path_elements) == len(path.path_elements)
    serialized_again = serialize_path(restored)
    assert serialized_again["path_elements"][0]["type"] == "translation"


def test_deserialize_rotation_ranged_constraint_counts_event_triggers():
    data = {
        "path_elements": [
            {"type": "translation", "x_meters": 0.0, "y_meters": 0.0},
            {"type": "event_trigger", "t_ratio": 0.25, "lib_key": "A"},
            {"type": "rotation", "rotation_radians": 0.5, "t_ratio": 0.5},
            {"type": "translation", "x_meters": 1.0, "y_meters": 1.0},
        ],
        "constraints": {
            "max_velocity_deg_per_sec": [
                {"value": 90.0, "start_ordinal": 1, "end_ordinal": 1},
            ]
        },
    }

    restored = deserialize_path(data)

    assert isinstance(restored.path_elements[1], EventTrigger)
    assert isinstance(restored.path_elements[2], RotationTarget)
    assert restored.ranged_constraints == [
        RangedConstraint(
            key="max_velocity_deg_per_sec",
            value=90.0,
            start_ordinal=2,
            end_ordinal=2,
        )
    ]


def test_serialize_mixed_path_preserves_flat_and_ranged_constraints():
    path = PathModel(
        path_elements=[
            TranslationTarget(0.0, 0.0, intermediate_handoff_radius_meters=0.2),
            Waypoint(
                translation_target=TranslationTarget(1.0, 0.5),
                rotation_target=RotationTarget(rotation_radians=0.25, profiled_rotation=False),
            ),
            EventTrigger(t_ratio=0.3, lib_key="shoot"),
            RotationTarget(rotation_radians=0.75, t_ratio=0.8),
            TranslationTarget(2.0, 1.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.5,
                start_ordinal=1,
                end_ordinal=2,
            )
        ],
    )
    path.constraints.max_velocity_meters_per_sec = 9.0
    path.constraints.end_translation_tolerance_meters = 0.05
    path.constraints.end_rotation_tolerance_deg = 2.0

    data = serialize_path(path)

    assert [item["type"] for item in data["path_elements"]] == [
        "translation",
        "waypoint",
        "event_trigger",
        "rotation",
        "translation",
    ]
    assert data["constraints"]["max_velocity_meters_per_sec"] == [
        {"value": 2.5, "start_ordinal": 0, "end_ordinal": 1}
    ]
    assert data["constraints"]["default_max_velocity_meters_per_sec"] == 9.0
    assert data["constraints"]["end_translation_tolerance_meters"] == 0.05
    assert data["constraints"]["end_rotation_tolerance_deg"] == 2.0


def test_deserialize_flat_constraints_and_legacy_default_keys():
    restored = deserialize_path(
        {
            "constraints": {
                "default_max_velocity_meters_per_sec": "3.5",
                "end_translation_tolerance_meters": "0.04",
                "end_rotation_tolerance_deg": 1,
            },
            "path_elements": [],
        }
    )

    assert restored.constraints.max_velocity_meters_per_sec == 3.5
    assert restored.constraints.end_translation_tolerance_meters == 0.04
    assert restored.constraints.end_rotation_tolerance_deg == 1.0


def test_deserialize_same_key_flat_default_and_ranged_constraints():
    restored = deserialize_path(
        {
            "constraints": {
                "default_max_velocity_meters_per_sec": 2.0,
                "max_velocity_meters_per_sec": [
                    {"value": 1.5, "start_ordinal": 0, "end_ordinal": 0},
                ],
            },
            "path_elements": [
                {"type": "translation", "x_meters": 0.0, "y_meters": 0.0},
                {"type": "translation", "x_meters": 1.0, "y_meters": 0.0},
            ],
        }
    )

    assert restored.constraints.max_velocity_meters_per_sec == 2.0
    assert restored.ranged_constraints == [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=1.5,
            start_ordinal=1,
            end_ordinal=1,
        )
    ]


def test_deserialize_repairs_overlapping_translation_ranges_from_older_files():
    restored = deserialize_path(
        {
            "path_elements": [
                {"type": "translation", "x_meters": 0.0, "y_meters": 0.0},
                {"type": "translation", "x_meters": 1.0, "y_meters": 0.0},
                {"type": "translation", "x_meters": 2.0, "y_meters": 0.0},
            ],
            "constraints": {
                "max_velocity_meters_per_sec": [
                    {"value": 2.0, "start_ordinal": 0, "end_ordinal": 0},
                    {"value": 2.0, "start_ordinal": 0, "end_ordinal": 1},
                    {"value": 4.0, "start_ordinal": 2, "end_ordinal": 2},
                ]
            },
        }
    )

    assert restored.ranged_constraints == [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=1,
        ),
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=2,
            end_ordinal=2,
        ),
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=4.0,
            start_ordinal=3,
            end_ordinal=3,
        ),
    ]


def test_deserialize_drops_fully_covered_overlapping_range_from_older_files():
    restored = deserialize_path(
        {
            "path_elements": [
                {"type": "translation", "x_meters": 0.0, "y_meters": 0.0},
                {"type": "translation", "x_meters": 1.0, "y_meters": 0.0},
            ],
            "constraints": {
                "max_velocity_meters_per_sec": [
                    {"value": 2.0, "start_ordinal": 0, "end_ordinal": 1},
                    {"value": 3.0, "start_ordinal": 0, "end_ordinal": 0},
                ]
            },
        }
    )

    assert restored.ranged_constraints == [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=2,
        )
    ]


def test_deserialize_legacy_rotation_position_converts_to_segment_ratio():
    restored = deserialize_path(
        {
            "path_elements": [
                {"type": "translation", "x_meters": 0.0, "y_meters": 0.0},
                {
                    "type": "rotation",
                    "rotation_radians": 1.0,
                    "x_meters": 3.0,
                    "y_meters": 0.0,
                },
                {"type": "translation", "x_meters": 6.0, "y_meters": 0.0},
            ]
        }
    )

    rotation = restored.path_elements[1]
    assert isinstance(rotation, RotationTarget)
    assert rotation.t_ratio == 0.5
    assert rotation.legacy_position is None
    assert rotation.legacy_converted is True


def test_deserialize_malformed_items_and_constraints_skips_bad_entries():
    restored = deserialize_path(
        {
            "path_elements": [
                {"type": "translation", "x_meters": "bad", "y_meters": 0.0},
                {"type": "event_trigger", "t_ratio": "bad", "lib_key": "ignored"},
                {"type": "translation", "x_meters": 1.0, "y_meters": 2.0},
            ],
            "constraints": {
                "max_velocity_meters_per_sec": [
                    {"value": "bad", "start_ordinal": 0, "end_ordinal": 0},
                    {"value": 2.0, "start_ordinal": 0, "end_ordinal": 0},
                ],
                "unknown": [{"value": 1.0, "start_ordinal": 0, "end_ordinal": 0}],
            },
        }
    )

    assert len(restored.path_elements) == 1
    assert isinstance(restored.path_elements[0], TranslationTarget)
    assert restored.ranged_constraints == [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=1,
        )
    ]
