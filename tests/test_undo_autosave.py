from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from models.path_model import Path, TranslationTarget
from ui.main_window.autosave import AutosaveController
from utils.project_manager import ProjectConfig
from utils.undo_system import CompoundCommand, ConfigCommand, PathCommand, UndoRedoManager


class _RecorderCommand:
    def __init__(self, name: str, calls: list[str]):
        self.name = name
        self.calls = calls

    def execute(self):
        self.calls.append(f"execute:{self.name}")

    def undo(self):
        self.calls.append(f"undo:{self.name}")

    def get_description(self):
        return self.name


def test_path_command_restores_elements_constraints_and_ranged_constraints():
    old = Path(path_elements=[TranslationTarget(0.0, 0.0)])
    new = Path(path_elements=[TranslationTarget(1.0, 2.0)])
    new.constraints.end_translation_tolerance_meters = 0.15
    new.ranged_constraints = []
    live = Path()
    callbacks: list[str] = []

    command = PathCommand(
        live,
        old,
        new,
        "Edit path",
        on_change_callback=lambda: callbacks.append("redo"),
        on_undo_callback=lambda: callbacks.append("undo"),
    )

    command.execute()
    assert live.path_elements == new.path_elements
    assert live.constraints.end_translation_tolerance_meters == 0.15
    assert callbacks == ["redo"]

    command.undo()
    assert live.path_elements == old.path_elements
    assert live.constraints == old.constraints
    assert callbacks == ["redo", "undo"]


def test_path_command_can_suppress_first_refresh_callback():
    live = Path()
    callbacks: list[None] = []
    command = PathCommand(
        live,
        Path(),
        Path(path_elements=[TranslationTarget(1.0, 0.0)]),
        "Add Translation",
        on_change_callback=lambda: callbacks.append(None),
        suppress_first_callback=True,
    )

    command.execute()
    command.execute()

    assert callbacks == [None]


def test_undo_redo_manager_limits_history_and_clears_redo():
    calls: list[str] = []
    manager = UndoRedoManager(max_history=2)
    state_changes: list[None] = []
    manager.add_callback(lambda: state_changes.append(None))

    manager.execute_command(_RecorderCommand("one", calls))
    manager.execute_command(_RecorderCommand("two", calls))
    manager.execute_command(_RecorderCommand("three", calls))

    assert manager.get_history_size() == (2, 0)
    assert manager.get_undo_description() == "three"
    assert calls == ["execute:one", "execute:two", "execute:three"]

    undone = manager.undo()
    assert undone.get_description() == "three"
    assert manager.get_redo_description() == "three"

    manager.execute_command(_RecorderCommand("four", calls))
    assert not manager.can_redo()
    assert state_changes


def test_compound_command_executes_forward_and_undos_reverse():
    calls: list[str] = []
    command = CompoundCommand(
        [_RecorderCommand("a", calls), _RecorderCommand("b", calls)],
        "compound",
    )

    command.execute()
    command.undo()

    assert calls == ["execute:a", "execute:b", "undo:b", "undo:a"]
    assert command.get_description() == "compound"


def test_config_command_saves_and_invokes_callback():
    class ProjectManagerStub:
        def __init__(self):
            self.config = ProjectConfig(robot_length_meters=0.7)
            self.saved: list[float] = []

        def save_config(self):
            self.saved.append(self.config.robot_length_meters)

    project_manager = ProjectManagerStub()
    callbacks: list[float] = []
    command = ConfigCommand(
        project_manager,
        ProjectConfig(robot_length_meters=0.7),
        ProjectConfig(robot_length_meters=0.9),
        "Edit config",
        on_change_callback=lambda: callbacks.append(project_manager.config.robot_length_meters),
    )

    command.execute()
    command.undo()

    assert project_manager.saved == [0.9, 0.7]
    assert callbacks == [0.9, 0.7]


def _autosave_window(qt_app):
    window = QMainWindow()
    window.statusBar = window.statusBar()
    window.path = Path(path_elements=[TranslationTarget(0.0, 0.0)])
    return window


def test_autosave_performs_save_for_valid_project(qt_app):
    class ProjectManagerStub:
        def __init__(self):
            self.saved_path = None

        def has_valid_project(self):
            return True

        def save_path(self, path):
            self.saved_path = path
            return "path.json"

    window = _autosave_window(qt_app)
    window.project_manager = ProjectManagerStub()
    controller = AutosaveController(window)
    try:
        controller._perform_autosave()

        assert window.project_manager.saved_path is window.path
        assert controller.status_label.text() == "\u2705 Saved"
    finally:
        window.close()


def test_autosave_reports_invalid_project_without_saving(qt_app):
    class ProjectManagerStub:
        def has_valid_project(self):
            return False

        def save_path(self, path):  # pragma: no cover - should not be reached
            raise AssertionError("save_path should not run")

    window = _autosave_window(qt_app)
    window.project_manager = ProjectManagerStub()
    controller = AutosaveController(window)
    try:
        controller._perform_autosave()

        assert controller.status_label.text() == "\u274c Error"
    finally:
        window.close()


def test_autosave_schedule_starts_timer_and_busy_indicator(qt_app):
    class ProjectManagerStub:
        def has_valid_project(self):
            return True

        def save_path(self, path):
            return "path.json"

    window = _autosave_window(qt_app)
    window.project_manager = ProjectManagerStub()
    controller = AutosaveController(window)
    try:
        controller.schedule()

        assert controller.timer.isActive()
        assert controller.status_label.text() == "\U0001f4be Saving..."
    finally:
        window.close()
