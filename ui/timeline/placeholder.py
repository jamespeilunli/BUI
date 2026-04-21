# mypy: ignore-errors
"""Phase 1 timeline placeholder widget."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ui.qt_compat import Qt, QSizePolicy
from models.path_model import (
    EventTrigger,
    Path,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)


class TimelinePlaceholder(QFrame):
    """Minimal timeline dock placeholder used while the real timeline is built."""

    def __init__(self, path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._title_label: QLabel
        self._summary_label: QLabel
        self._hint_label: QLabel
        self._setup_ui()
        self.set_path(path or Path())

    def _setup_ui(self) -> None:
        self.setObjectName("timelinePlaceholder")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(180)
        self.setStyleSheet(
            """
            QFrame#timelinePlaceholder {
                background: #141414;
                border-top: 1px solid #2d2d2d;
            }
            QLabel#timelineTitle {
                color: #f0f0f0;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#timelineSummary {
                color: #b9c0c8;
                font-size: 12px;
            }
            QLabel#timelineHint {
                color: #7f8792;
                font-size: 11px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(6)

        self._title_label = QLabel("Timeline")
        self._title_label.setObjectName("timelineTitle")
        layout.addWidget(self._title_label)

        self._summary_label = QLabel()
        self._summary_label.setObjectName("timelineSummary")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        self._hint_label = QLabel(
            "Phase 1 placeholder: layout and splitter behavior first, timeline rendering next."
        )
        self._hint_label.setObjectName("timelineHint")
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        layout.addStretch(1)

    def set_path(self, path: Path | None) -> None:
        self._path = path
        self._summary_label.setText(self._build_summary(path))

    def _build_summary(self, path: Path | None) -> str:
        if path is None:
            return "No path loaded."

        structure_count = 0
        rotation_count = 0
        event_count = 0

        for element in path.path_elements:
            if isinstance(element, (TranslationTarget, Waypoint)):
                structure_count += 1
            elif isinstance(element, RotationTarget):
                rotation_count += 1
            elif isinstance(element, EventTrigger):
                event_count += 1

        constraint_count = len(getattr(path, "ranged_constraints", []) or [])

        return (
            f"{structure_count} anchors, "
            f"{rotation_count} rotation targets, "
            f"{event_count} triggers, "
            f"{constraint_count} ranged constraints."
        )
