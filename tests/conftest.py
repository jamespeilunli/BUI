from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.path_model import (
    EventTrigger,
    Path as PathModel,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Ensure Qt widgets and core classes can initialize during tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def process_events(qt_app):
    """Flush queued Qt work used by selection, undo, and timeline refresh paths."""

    def _flush(iterations: int = 4) -> None:
        for _ in range(iterations):
            qt_app.processEvents()

    return _flush


@pytest.fixture
def mixed_path() -> PathModel:
    """A representative timeline path with structure, rotation, trigger, and constraints."""
    return PathModel(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            Waypoint(
                translation_target=TranslationTarget(1.0, 0.0),
                rotation_target=RotationTarget(rotation_radians=0.2, t_ratio=0.0),
            ),
            RotationTarget(rotation_radians=0.5, t_ratio=0.25),
            EventTrigger(t_ratio=0.75, lib_key="score"),
            TranslationTarget(3.0, 0.0),
        ],
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=2.0,
                start_ordinal=1,
                end_ordinal=2,
            ),
            RangedConstraint(
                key="max_velocity_deg_per_sec",
                value=90.0,
                start_ordinal=1,
                end_ordinal=2,
            ),
        ],
    )


@pytest.fixture
def install_main_window_path(process_events):
    """Install a path into MainWindow views without relying on startup project loading."""

    def _install(window, path: PathModel) -> None:
        window.path = path
        window.sidebar.set_path(window.path)
        window.canvas.set_path(window.path)
        window.timeline.set_path(window.path, window._timeline_config())
        process_events()

    return _install
