from __future__ import annotations

from models.path_model import EventTrigger, Path, RotationTarget, TranslationTarget, Waypoint
from ui.sidebar.utils.ranged_constraint_ui import (
    get_constraint_domain_elements,
    get_constraint_domain_info,
    get_constraint_domain_labels,
)


def test_rotation_domain_excludes_event_triggers_and_translations():
    path = Path(
        path_elements=[
            TranslationTarget(),
            EventTrigger(),
            RotationTarget(),
            Waypoint(),
            TranslationTarget(),
        ]
    )

    elements = get_constraint_domain_elements(path, "max_velocity_deg_per_sec")

    assert [type(element).__name__ for element in elements] == [
        "RotationTarget",
        "Waypoint",
    ]


def test_translation_domain_excludes_rotations_and_event_triggers():
    path = Path(
        path_elements=[
            TranslationTarget(),
            Waypoint(),
            RotationTarget(),
            TranslationTarget(),
            EventTrigger(),
        ]
    )

    domain, count = get_constraint_domain_info(path, "max_velocity_meters_per_sec")

    assert (domain, count) == ("translation", 3)
    assert get_constraint_domain_labels(path, "max_velocity_meters_per_sec") == [
        "T1",
        "W1",
        "T2",
    ]
