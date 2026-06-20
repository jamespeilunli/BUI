from __future__ import annotations

import math

from PySide6.QtWidgets import QDialog

from models.path_model import (
    EventTrigger,
    Path,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from ui.main_window.window import MainWindow
from ui.timeline.placeholder import StructurePlacement, TriggerPlacement


def _new_window() -> MainWindow:
    window = MainWindow()
    window.project_manager.load_last_project = lambda: False
    window._action_open_project = lambda force_dialog=False: None
    return window


def _simple_path() -> Path:
    return Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(4.0, 0.0),
        ]
    )


def test_timeline_path_selection_signal_updates_sidebar_and_canvas(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    try:
        install_main_window_path(window, _simple_path())

        window.timeline.pathItemSelected.emit(1)
        process_events()

        assert window.sidebar.get_selected_index() == 1
        assert window.timeline._selection is not None
        assert window.timeline._selection.path_index == 1
        assert len(window.canvas.graphics_scene.selectedItems()) == 1
    finally:
        window.close()


def test_timeline_empty_selection_signal_clears_all_regions(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    try:
        install_main_window_path(window, _simple_path())
        window._select_path_index_across_views(1, center_canvas=False)
        assert window.sidebar.get_selected_index() == 1

        window.timeline._on_empty_area_clicked()
        process_events()

        assert window.sidebar.get_selected_index() is None
        assert window.timeline._selection is None
        assert window.canvas.graphics_scene.selectedItems() == []
    finally:
        window.close()


def test_timeline_constraint_selection_signal_updates_sidebar_and_canvas_overlay(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    path = Path(
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
                end_ordinal=2,
            )
        ],
    )
    try:
        install_main_window_path(window, path)

        window.timeline.select_constraint_range("max_velocity_meters_per_sec", 1, 2)
        window.timeline.constraintRangeSelected.emit("max_velocity_meters_per_sec", 1, 2)
        process_events()

        assert window.sidebar.get_selected_index() is None
        assert window.sidebar._selected_constraint_ref == ("max_velocity_meters_per_sec", 1, 2)
        assert window.timeline._selection is not None
        assert window.timeline._selection.kind == "constraint"
        assert window.canvas._constraint_highlight_indices == [0, 1]
        assert window.canvas._range_overlay_lines
    finally:
        window.close()


def test_timeline_structure_create_adds_waypoint_selects_it_and_records_undo(
    qt_app,
    monkeypatch,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    schedule_calls: list[None] = []
    window.autosave.schedule = lambda: schedule_calls.append(None)
    monkeypatch.setattr(
        "ui.main_window.window.resolve_structure_placement_for_time",
        lambda path, config, time_s, element_type: StructurePlacement(
            insert_index=1,
            x_m=2.0,
            y_m=0.5,
        ),
    )
    try:
        install_main_window_path(window, _simple_path())

        window._on_timeline_structure_item_create_requested("waypoint", 0.5)
        process_events()

        assert len(window.path.path_elements) == 3
        assert isinstance(window.path.path_elements[1], Waypoint)
        assert math.isclose(window.path.path_elements[1].translation_target.x_meters, 2.0)
        assert window.sidebar.get_selected_index() == 1
        assert window.timeline._selection.path_index == 1
        assert window.undo_manager.can_undo()

        window.undo_manager.undo()
        assert [type(element) for element in window.path.path_elements] == [
            TranslationTarget,
            TranslationTarget,
        ]
        window.undo_manager.redo()
        assert isinstance(window.path.path_elements[1], Waypoint)
        assert schedule_calls
    finally:
        window.close()


def test_timeline_waypoint_insert_preserves_constraint_visual_endpoints(
    qt_app,
    monkeypatch,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    monkeypatch.setattr(
        "ui.main_window.window.resolve_structure_placement_for_time",
        lambda path, config, time_s, element_type: StructurePlacement(
            insert_index=1,
            x_m=2.0,
            y_m=0.0,
        ),
    )
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(4.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.0,
                start_ordinal=2,
                end_ordinal=2,
            )
        ],
    )
    try:
        install_main_window_path(window, path)

        window._on_timeline_structure_item_create_requested("waypoint", 0.5)
        process_events()

        assert isinstance(window.path.path_elements[1], Waypoint)
        assert (
            window.path.ranged_constraints[0].start_ordinal,
            window.path.ranged_constraints[0].end_ordinal,
        ) == (2, 3)
    finally:
        window.close()


def test_timeline_event_trigger_create_and_move_preserve_selection_and_undo(
    qt_app,
    monkeypatch,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    placements = [
        TriggerPlacement(insert_index=1, t_ratio=0.25),
        TriggerPlacement(insert_index=2, t_ratio=0.75),
    ]

    def fake_resolve(path, config, time_s):
        return placements.pop(0)

    monkeypatch.setattr("ui.main_window.window.resolve_trigger_placement_for_time", fake_resolve)
    try:
        install_main_window_path(window, _simple_path())

        window._on_timeline_event_trigger_create_requested(0.25)
        process_events()
        trigger = window.path.path_elements[1]
        assert isinstance(trigger, EventTrigger)
        assert math.isclose(trigger.t_ratio, 0.25)
        assert window.undo_manager.get_undo_description() == "Add EventTrigger"

        window._on_timeline_event_trigger_move_requested(1, 0.75)
        process_events()

        assert isinstance(window.path.path_elements[2], EventTrigger)
        assert math.isclose(window.path.path_elements[2].t_ratio, 0.75)
        assert window.sidebar.get_selected_index() == 2
        assert window.undo_manager.get_undo_description() == "Move EventTrigger"

        window.undo_manager.undo()
        assert window.path.path_elements[1] is not trigger
        assert isinstance(window.path.path_elements[1], EventTrigger)
    finally:
        window.close()


def test_timeline_constraint_create_update_delete_records_undo_and_autosave(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    schedule_calls: list[None] = []
    window.autosave.schedule = lambda: schedule_calls.append(None)
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(2.0, 0.0),
            TranslationTarget(4.0, 0.0),
        ],
    )
    path.constraints.max_velocity_meters_per_sec = 1.5
    try:
        install_main_window_path(window, path)

        window._on_timeline_constraint_range_create_requested(
            "max_velocity_meters_per_sec",
            1,
            1,
        )
        process_events()

        assert len(window.path.ranged_constraints) == 1
        assert window.path.constraints.max_velocity_meters_per_sec == 1.5
        assert window.path.ranged_constraints[0].start_ordinal == 1
        assert window.sidebar._selected_constraint_ref == ("max_velocity_meters_per_sec", 1, 1)
        assert window.undo_manager.get_undo_description() == "Add constraint range"

        window._on_timeline_constraint_range_update_requested(
            0,
            "max_velocity_meters_per_sec",
            1,
            1,
            2,
            2,
            "move",
        )
        process_events()

        assert (window.path.ranged_constraints[0].start_ordinal, window.path.ranged_constraints[0].end_ordinal) == (
            2,
            2,
        )
        assert window.undo_manager.get_undo_description() == "Move constraint range"

        window._on_timeline_constraint_range_delete_requested(
            0,
            "max_velocity_meters_per_sec",
            2,
            2,
        )
        process_events()

        assert window.path.ranged_constraints == []
        assert window.sidebar._selected_constraint_ref is None
        assert window.timeline._selection is None
        assert window.undo_manager.get_undo_description() == "Delete constraint range"
        assert schedule_calls

        window.undo_manager.undo()
        assert len(window.path.ranged_constraints) == 1
        assert window.sidebar._selected_constraint_ref == ("max_velocity_meters_per_sec", 2, 2)
    finally:
        window.close()


def test_timeline_constraint_create_allows_same_key_overlap(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    path = Path(
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
                end_ordinal=2,
            )
        ],
    )
    try:
        install_main_window_path(window, path)

        window._on_timeline_constraint_range_create_requested(
            "max_velocity_meters_per_sec",
            2,
            3,
        )
        process_events()

        assert len(window.path.ranged_constraints) == 2
        assert (
            window.path.ranged_constraints[1].key,
            window.path.ranged_constraints[1].start_ordinal,
            window.path.ranged_constraints[1].end_ordinal,
        ) == ("max_velocity_meters_per_sec", 2, 3)
        assert window.sidebar._selected_constraint_ref == ("max_velocity_meters_per_sec", 2, 3)
        assert window.sidebar._selected_constraint_index == 1
        assert window.timeline._selection.constraint_index == 1
        assert window.undo_manager.get_undo_description() == "Add constraint range"
    finally:
        window.close()


def test_timeline_duplicate_constraint_selection_edits_selected_index(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    key = "max_velocity_meters_per_sec"
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(2.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(key=key, value=2.0, start_ordinal=1, end_ordinal=2),
            RangedConstraint(key=key, value=1.5, start_ordinal=1, end_ordinal=2),
        ],
    )
    try:
        install_main_window_path(window, path)

        window.timeline.constraintRangeSelectedByIndex.emit(1, key, 1, 2)
        process_events()
        window.sidebar.on_constraint_value_changed(1.25)
        process_events()

        assert window.path.ranged_constraints[0].value == 2.0
        assert window.path.ranged_constraints[1].value == 1.25
        assert window.sidebar._selected_constraint_index == 1
        assert window.sidebar._selected_constraint_ref == (key, 1, 2)
    finally:
        window.close()


def test_sidebar_constraint_type_combo_stays_within_translation_domain(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(2.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.0,
                start_ordinal=1,
                end_ordinal=2,
            )
        ],
    )
    try:
        install_main_window_path(window, path)
        window.sidebar.select_constraint_range_by_index(0, "max_velocity_meters_per_sec", 1, 2)
        process_events()

        labels = [
            window.sidebar.constraint_type_combo.itemText(index)
            for index in range(window.sidebar.constraint_type_combo.count())
        ]

        assert labels == [
            window.sidebar._constraint_label_for_key("max_velocity_meters_per_sec"),
            window.sidebar._constraint_label_for_key("max_acceleration_meters_per_sec2"),
        ]
    finally:
        window.close()


def test_sidebar_constraint_type_combo_stays_within_rotation_domain(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            RotationTarget(rotation_radians=0.5, t_ratio=0.5),
            TranslationTarget(2.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_deg_per_sec",
                value=90.0,
                start_ordinal=1,
                end_ordinal=1,
            )
        ],
    )
    try:
        install_main_window_path(window, path)
        window.sidebar.select_constraint_range_by_index(0, "max_velocity_deg_per_sec", 1, 1)
        process_events()

        labels = [
            window.sidebar.constraint_type_combo.itemText(index)
            for index in range(window.sidebar.constraint_type_combo.count())
        ]

        assert labels == [
            window.sidebar._constraint_label_for_key("max_velocity_deg_per_sec"),
            window.sidebar._constraint_label_for_key("max_acceleration_deg_per_sec2"),
        ]
    finally:
        window.close()


def test_sidebar_rejects_programmatic_cross_domain_constraint_type_change(
    qt_app,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            RotationTarget(rotation_radians=0.5, t_ratio=0.5),
            TranslationTarget(2.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.0,
                start_ordinal=1,
                end_ordinal=2,
            )
        ],
    )
    try:
        install_main_window_path(window, path)
        window.sidebar.select_constraint_range_by_index(0, "max_velocity_meters_per_sec", 1, 2)
        process_events()

        window.sidebar._constraint_type_key_by_label["Rotation Velocity"] = "max_velocity_deg_per_sec"
        window.sidebar.on_constraint_type_change("Rotation Velocity")

        assert window.path.ranged_constraints[0].key == "max_velocity_meters_per_sec"
        assert (
            window.path.ranged_constraints[0].start_ordinal,
            window.path.ranged_constraints[0].end_ordinal,
        ) == (1, 2)
    finally:
        window.close()


def test_timeline_rotation_create_uses_segment_ratio(
    qt_app,
    monkeypatch,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    monkeypatch.setattr(
        "ui.main_window.window.resolve_structure_placement_for_time",
        lambda path, config, time_s, element_type: StructurePlacement(
            insert_index=1,
            t_ratio=0.4,
        ),
    )
    try:
        install_main_window_path(window, _simple_path())

        window._on_timeline_structure_item_create_requested("rotation", 0.4)
        process_events()

        assert isinstance(window.path.path_elements[1], RotationTarget)
        assert math.isclose(window.path.path_elements[1].t_ratio, 0.4)
        assert window.sidebar.get_selected_index() == 1
    finally:
        window.close()


def test_path_settings_action_updates_flat_constraints_and_preserves_ranges(
    qt_app,
    monkeypatch,
    install_main_window_path,
    process_events,
):
    window = _new_window()
    schedule_calls: list[None] = []
    window.autosave.schedule = lambda: schedule_calls.append(None)
    path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(2.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=3.0,
                start_ordinal=1,
                end_ordinal=2,
            )
        ],
    )

    values = {
        "max_velocity_meters_per_sec": 2.0,
        "max_acceleration_meters_per_sec2": 4.0,
        "max_velocity_deg_per_sec": 90.0,
        "max_acceleration_deg_per_sec2": 180.0,
        "end_translation_tolerance_meters": 0.05,
        "end_rotation_tolerance_deg": None,
    }

    class FakePathSettingsDialog:
        def __init__(self, parent, dialog_path, config):
            self.path = dialog_path

        def exec(self):
            return QDialog.Accepted

        def get_values(self):
            return dict(values)

    monkeypatch.setattr("ui.main_window.window.PathSettingsDialog", FakePathSettingsDialog)
    try:
        install_main_window_path(window, path)
        assert window.action_path_settings.text() == "Settings…"

        window._action_path_settings()
        process_events()

        assert window.path.constraints.max_velocity_meters_per_sec == 2.0
        assert window.path.constraints.max_acceleration_meters_per_sec2 == 4.0
        assert window.path.constraints.max_velocity_deg_per_sec == 90.0
        assert window.path.constraints.max_acceleration_deg_per_sec2 == 180.0
        assert window.path.constraints.end_translation_tolerance_meters == 0.05
        assert window.path.constraints.end_rotation_tolerance_deg is None
        assert len(window.path.ranged_constraints) == 1
        assert window.path.ranged_constraints[0].value == 3.0
        assert window.undo_manager.get_undo_description() == "Change Path Settings"

        window.undo_manager.undo()
        assert window.path.constraints.max_velocity_meters_per_sec is None
        assert len(window.path.ranged_constraints) == 1

        window.undo_manager.redo()
        assert window.path.constraints.max_velocity_meters_per_sec == 2.0
        assert schedule_calls
    finally:
        window.close()
