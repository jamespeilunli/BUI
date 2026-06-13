from __future__ import annotations

import pytest

from models.path_model import (
    EventTrigger,
    Path,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from ui.main_window.window import MainWindow


def _install_path(window: MainWindow, path: Path) -> None:
    window.path = path
    window.sidebar.set_path(window.path)
    window.canvas.set_path(window.path)
    window.timeline.set_path(window.path, window._timeline_config())


def _process_deferred_qt_work(qt_app, iterations: int = 4) -> None:
    for _ in range(iterations):
        qt_app.processEvents()


def test_shared_element_delete_leaves_no_replacement_selection(qt_app):
    window = MainWindow()
    window._record_path_change = lambda *args, **kwargs: None
    try:
        _install_path(
            window,
            Path(
                path_elements=[
                    TranslationTarget(0.0, 0.0),
                    TranslationTarget(1.0, 0.0),
                    TranslationTarget(2.0, 0.0),
                ]
            ),
        )

        window._select_path_index_across_views(1, center_canvas=False)
        assert window.sidebar.get_selected_index() == 1
        assert window.timeline._selection is not None

        window._delete_selected_element()

        assert len(window.path.path_elements) == 2
        assert window.sidebar.get_selected_index() is None
        assert window.timeline._selection is None
        assert window.canvas.graphics_scene.selectedItems() == []
    finally:
        window.close()


@pytest.mark.parametrize("delete_index", [0, 1, 2, 3, 4])
def test_timeline_selected_path_item_delete_removes_item_and_clears_selection(qt_app, delete_index):
    window = MainWindow()
    window._record_path_change = lambda *args, **kwargs: None
    try:
        _install_path(
            window,
            Path(
                path_elements=[
                    TranslationTarget(0.0, 0.0),
                    Waypoint(translation_target=TranslationTarget(1.0, 0.0)),
                    RotationTarget(rotation_radians=0.5, t_ratio=0.25),
                    EventTrigger(t_ratio=0.5, lib_key="score"),
                    TranslationTarget(2.0, 0.0),
                ]
            ),
        )
        removed_identity = id(window.path.path_elements[delete_index])

        window.timeline.select_path_index(delete_index)
        window._on_timeline_path_item_delete_requested(delete_index)

        assert len(window.path.path_elements) == 4
        assert all(id(element) != removed_identity for element in window.path.path_elements)
        assert not isinstance(window.path.path_elements[0], (RotationTarget, EventTrigger))
        assert not isinstance(window.path.path_elements[-1], (RotationTarget, EventTrigger))
        assert window.sidebar.get_selected_index() is None
        assert window.timeline._selection is None
        assert window.canvas.graphics_scene.selectedItems() == []
    finally:
        window.close()


def test_timeline_translation_delete_remaps_ranged_constraints(qt_app):
    window = MainWindow()
    window._record_path_change = lambda *args, **kwargs: None
    try:
        _install_path(
            window,
            Path(
                path_elements=[
                    TranslationTarget(0.0, 0.0),
                    TranslationTarget(1.0, 0.0),
                    TranslationTarget(2.0, 0.0),
                    TranslationTarget(3.0, 0.0),
                ],
                ranged_constraints=[
                    RangedConstraint(
                        key="max_velocity_meters_per_sec",
                        value=2.0,
                        start_ordinal=1,
                        end_ordinal=3,
                    ),
                ],
            ),
        )

        window.timeline.select_path_index(1)
        window._on_timeline_path_item_delete_requested(1)

        assert len(window.path.ranged_constraints) == 1
        constraint = window.path.ranged_constraints[0]
        assert (constraint.start_ordinal, constraint.end_ordinal) == (1, 2)
    finally:
        window.close()


def test_timeline_rotation_delete_remaps_rotation_ranged_constraints(qt_app):
    window = MainWindow()
    window._record_path_change = lambda *args, **kwargs: None
    try:
        _install_path(
            window,
            Path(
                path_elements=[
                    TranslationTarget(0.0, 0.0),
                    Waypoint(translation_target=TranslationTarget(1.0, 0.0)),
                    RotationTarget(rotation_radians=0.5, t_ratio=0.25),
                    EventTrigger(t_ratio=0.5, lib_key="score"),
                    TranslationTarget(2.0, 0.0),
                ],
                ranged_constraints=[
                    RangedConstraint(
                        key="max_velocity_deg_per_sec",
                        value=90.0,
                        start_ordinal=1,
                        end_ordinal=3,
                    ),
                ],
            ),
        )

        window.timeline.select_path_index(2)
        window._on_timeline_path_item_delete_requested(2)

        assert len(window.path.ranged_constraints) == 1
        constraint = window.path.ranged_constraints[0]
        assert (constraint.start_ordinal, constraint.end_ordinal) == (1, 2)
    finally:
        window.close()


def test_timeline_delete_records_undo_redo_and_autosave(qt_app):
    window = MainWindow()
    schedule_calls: list[None] = []
    window.project_manager.load_last_project = lambda: False
    window._action_open_project = lambda force_dialog=False: None
    window.autosave.schedule = lambda: schedule_calls.append(None)
    try:
        _install_path(
            window,
            Path(
                path_elements=[
                    TranslationTarget(0.0, 0.0),
                    EventTrigger(t_ratio=0.5, lib_key="score"),
                    TranslationTarget(2.0, 0.0),
                ]
            ),
        )

        window.timeline.select_path_index(1)
        window._on_timeline_path_item_delete_requested(1)
        _process_deferred_qt_work(qt_app)

        assert [type(element) for element in window.path.path_elements] == [
            TranslationTarget,
            TranslationTarget,
        ]
        assert window.undo_manager.can_undo()
        assert schedule_calls

        window.undo_manager.undo()
        assert [type(element) for element in window.path.path_elements] == [
            TranslationTarget,
            EventTrigger,
            TranslationTarget,
        ]

        window.undo_manager.redo()
        assert [type(element) for element in window.path.path_elements] == [
            TranslationTarget,
            TranslationTarget,
        ]
        assert len(schedule_calls) >= 3
    finally:
        window.close()
