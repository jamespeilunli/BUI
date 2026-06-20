from models.path_model import (
    Path,
    PathElement,
    RangedConstraint,
    TranslationTarget,
    Waypoint,
    RotationTarget,
)
from typing import List

def _translation_domain(elements: List[PathElement]) -> List[int]:
    """Return Python id()s of elements in the translation domain, in order."""
    return [id(e) for e in elements if isinstance(e, (TranslationTarget, Waypoint))]

def _rotation_domain(elements: List[PathElement]) -> List[int]:
    """Return Python id()s of elements in the rotation domain, in order."""
    return [id(e) for e in elements if isinstance(e, (Waypoint, RotationTarget))]

TRANSLATION_KEYS = {"max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2"}
ROTATION_KEYS = {"max_velocity_deg_per_sec", "max_acceleration_deg_per_sec2"}

def _domain_for_key(key: str, elements: List[PathElement]) -> List[int]:
    if key in TRANSLATION_KEYS:
        return _translation_domain(elements)
    else:
        return _rotation_domain(elements)


def _id_at_ordinal(domain: List[int], ordinal: int) -> int | None:
    index = int(ordinal) - 1
    if 0 <= index < len(domain):
        return domain[index]
    return None


def _display_left_id_for_range(
    domain: List[int],
    start_ordinal: int,
    end_ordinal: int,
) -> int | None:
    if not domain:
        return None
    start = int(start_ordinal)
    end = int(end_ordinal)
    if start > end:
        start, end = end, start
    total = len(domain)
    start = max(1, min(start, total))
    end = max(start, min(end, total))
    display_start_index = max(0, start - 2 if start > 1 else start - 1)
    return domain[display_start_index]


def remap_ranged_constraints(path: Path, old_elements: List[PathElement]) -> None:
    """Update all RangedConstraint ordinals on `path` to reflect the
    current `path.path_elements` relative to the snapshot `old_elements`.

    Must be called AFTER the mutation has been applied to path.path_elements,
    but AFTER the undo snapshot of the old state has already been taken.

    Modifies path.ranged_constraints in place. Removes constraints whose
    entire range has been eliminated.
    """
    new_elements = path.path_elements
    surviving: List[RangedConstraint] = []

    for rc in path.ranged_constraints:
        old_domain = _domain_for_key(rc.key, old_elements)
        new_domain = _domain_for_key(rc.key, new_elements)
        new_domain_size = len(new_domain)

        if new_domain_size == 0:
            continue

        old_start_id = _id_at_ordinal(old_domain, int(getattr(rc, "start_ordinal", 1)))
        old_end_id = _id_at_ordinal(old_domain, int(getattr(rc, "end_ordinal", 1)))
        old_display_left_id = _display_left_id_for_range(
            old_domain,
            int(getattr(rc, "start_ordinal", 1)),
            int(getattr(rc, "end_ordinal", 1)),
        )

        new_id_to_ordinal = {eid: i + 1 for i, eid in enumerate(new_domain)}

        new_start = new_id_to_ordinal.get(old_start_id) if old_start_id else None
        new_end = new_id_to_ordinal.get(old_end_id) if old_end_id else None
        new_display_left = (
            new_id_to_ordinal.get(old_display_left_id) if old_display_left_id else None
        )

        if (
            new_display_left is not None
            and new_end is not None
            and old_start_id is not None
            and old_end_id is not None
            and new_start is not None
        ):
            if int(getattr(rc, "start_ordinal", 1)) <= 1:
                remapped_start = int(new_start if new_start is not None else new_display_left)
            else:
                remapped_start = min(int(new_domain_size), int(new_display_left) + 1)
            remapped_end = int(new_end)
            if remapped_start > remapped_end:
                remapped_start, remapped_end = remapped_end, remapped_start
            rc.start_ordinal = remapped_start
            rc.end_ordinal = remapped_end
            surviving.append(rc)
        elif new_start is not None and new_end is not None:
            if new_start > new_end:
                new_start, new_end = new_end, new_start
            rc.start_ordinal = new_start
            rc.end_ordinal = new_end
            surviving.append(rc)
        elif new_start is not None:
            rc.start_ordinal = new_start
            rc.end_ordinal = new_domain_size
            surviving.append(rc)
        elif new_end is not None:
            rc.start_ordinal = 1
            rc.end_ordinal = new_end
            surviving.append(rc)
        else:
            old_range_ids = set()
            for ord_i in range(rc.start_ordinal, rc.end_ordinal + 1):
                if ord_i - 1 < len(old_domain):
                    old_range_ids.add(old_domain[ord_i - 1])
            surviving_ordinals = sorted(
                new_id_to_ordinal[eid]
                for eid in old_range_ids
                if eid in new_id_to_ordinal
            )
            if surviving_ordinals:
                rc.start_ordinal = surviving_ordinals[0]
                rc.end_ordinal = surviving_ordinals[-1]
                surviving.append(rc)

    path.ranged_constraints = surviving
