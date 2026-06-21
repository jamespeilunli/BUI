from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from models.path_model import Path
from ui.qt_compat import Qt, QSizePolicy, QDialogButtonBox
from ui.sidebar.utils import SPINNER_METADATA, constraint_default_value
from ui.sidebar.widgets.no_wheel_spinbox import NoWheelDoubleSpinBox


KINEMATIC_CONSTRAINT_KEYS = (
    "max_velocity_meters_per_sec",
    "max_acceleration_meters_per_sec2",
    "max_velocity_deg_per_sec",
    "max_acceleration_deg_per_sec2",
)
TERMINAL_CONSTRAINT_KEYS = (
    "end_translation_tolerance_meters",
    "end_rotation_tolerance_deg",
)
PATH_SETTINGS_CONSTRAINT_KEYS = KINEMATIC_CONSTRAINT_KEYS + TERMINAL_CONSTRAINT_KEYS

CONSTRAINT_LABELS = {
    "max_velocity_meters_per_sec": "Max Velocity (m/s)",
    "max_acceleration_meters_per_sec2": "Max Acceleration (m/s^2)",
    "max_velocity_deg_per_sec": "Max Rotation Velocity (deg/s)",
    "max_acceleration_deg_per_sec2": "Max Rotation Acceleration (deg/s^2)",
    "end_translation_tolerance_meters": "End Translation Tolerance (m)",
    "end_rotation_tolerance_deg": "End Rotation Tolerance (deg)",
}


class PathSettingsDialog(QDialog):
    """Modal editor for flat path-level constraints."""

    def __init__(
        self,
        parent=None,
        path: Optional[Path] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Path Settings")
        self.setModal(True)
        self._path = path or Path()
        self._config = dict(config or {})
        self._enabled: Dict[str, QCheckBox] = {}
        self._spins: Dict[str, NoWheelDoubleSpinBox] = {}
        self._warnings: Dict[str, QLabel] = {}

        try:
            self.setObjectName("pathSettingsDialog")
            self.setMinimumWidth(520)
            self.setStyleSheet(
                """
                QDialog#pathSettingsDialog { background-color: #151515; }
                QLabel { color: #f0f0f0; }
                QGroupBox {
                    background-color: #202020;
                    border: 1px solid #444444;
                    border-radius: 6px;
                    color: #f0f0f0;
                    margin-top: 8px;
                    padding-top: 8px;
                }
                QWidget[settingsRow='true'] {
                    background: #2d2d2d;
                    border: 1px solid #454545;
                    border-radius: 6px;
                    margin: 4px 0;
                }
                """
            )
        except Exception:
            pass

        root = QVBoxLayout(self)
        try:
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)
        except Exception:
            pass

        self._build_title(root)
        self._build_section(root, "Whole-Path Limits", KINEMATIC_CONSTRAINT_KEYS)
        self._build_section(root, "Terminal Tolerances", TERMINAL_CONSTRAINT_KEYS)
        self._build_buttons(root)
        self._refresh_warnings()

    def get_values(self) -> Dict[str, Optional[float]]:
        values: Dict[str, Optional[float]] = {}
        for key in PATH_SETTINGS_CONSTRAINT_KEYS:
            enabled = self._enabled[key].isChecked()
            values[key] = float(self._spins[key].value()) if enabled else None
        return values

    def warning_text_for_key(self, key: str) -> str:
        label = self._warnings.get(key)
        if label is None or not bool(label.property("activeWarning")):
            return ""
        return label.text()

    def _build_title(self, root: QVBoxLayout) -> None:
        title_bar = QWidget()
        title_bar.setObjectName("pathSettingsTitleBar")
        try:
            title_bar.setStyleSheet(
                """
                QWidget#pathSettingsTitleBar {
                    background-color: #2a2a2a;
                    border: 1px solid #5a5a5a;
                    border-radius: 6px;
                }
                """
            )
        except Exception:
            pass
        layout = QVBoxLayout(title_bar)
        try:
            layout.setContentsMargins(10, 6, 10, 6)
            layout.setSpacing(2)
        except Exception:
            pass
        title = QLabel("Path Settings")
        subtitle = QLabel(
            "Whole-path limits apply to the full path. Ranged timeline spans can only "
            "make a region more restrictive."
        )
        try:
            title.setStyleSheet("font-size: 14px; font-weight: bold; color: #eeeeee;")
            subtitle.setStyleSheet("color: #b8b8b8;")
            subtitle.setWordWrap(True)
        except Exception:
            pass
        layout.addWidget(title)
        layout.addWidget(subtitle)
        root.addWidget(title_bar)

    def _build_section(
        self,
        root: QVBoxLayout,
        title: str,
        keys: tuple[str, ...],
    ) -> None:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        try:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)
        except Exception:
            pass
        for key in keys:
            self._add_constraint_row(layout, key)
        root.addWidget(group)

    def _add_constraint_row(self, group_layout: QVBoxLayout, key: str) -> None:
        row = QWidget()
        row.setProperty("settingsRow", "true")
        row_layout = QVBoxLayout(row)
        try:
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(4)
        except Exception:
            pass

        top = QWidget()
        top_layout = QHBoxLayout(top)
        try:
            top_layout.setContentsMargins(0, 0, 0, 0)
            top_layout.setSpacing(8)
        except Exception:
            pass

        check = QCheckBox("Use", self)
        label = QLabel(CONSTRAINT_LABELS.get(key, key))
        spin = self._make_spinbox(key)
        existing_value = self._current_constraint_value(key)
        check.setChecked(existing_value is not None)
        spin.setValue(
            float(existing_value if existing_value is not None else self._default_value(key))
        )
        spin.setEnabled(existing_value is not None)
        try:
            label.setMinimumWidth(250)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            spin.setMinimumWidth(110)
            spin.setMaximumWidth(130)
        except Exception:
            pass

        top_layout.addWidget(check)
        top_layout.addWidget(label)
        top_layout.addStretch()
        top_layout.addWidget(spin)

        warning = QLabel("")
        warning.setProperty("activeWarning", False)
        warning.setVisible(False)
        try:
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #f0c36a; padding-left: 28px;")
        except Exception:
            pass

        check.toggled.connect(lambda checked, k=key: self._on_row_enabled(k, checked))
        spin.valueChanged.connect(lambda _value, k=key: self._refresh_warning_for_key(k))

        self._enabled[key] = check
        self._spins[key] = spin
        self._warnings[key] = warning

        row_layout.addWidget(top)
        row_layout.addWidget(warning)
        group_layout.addWidget(row)

    def _make_spinbox(self, key: str) -> NoWheelDoubleSpinBox:
        meta = SPINNER_METADATA.get(key, {})
        spin = NoWheelDoubleSpinBox(self)
        spin.setDecimals(4)
        try:
            step = float(meta.get("step", 0.1))
        except Exception:
            step = 0.1
        spin.setSingleStep(step)
        rng = meta.get("range", (0.0, 99999.0))
        try:
            low, high = float(rng[0]), float(rng[1])
        except Exception:
            low, high = 0.0, 99999.0
        spin.setRange(low, high)
        return spin

    def _build_buttons(self, root: QVBoxLayout) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            orientation=Qt.Horizontal,
            parent=self,
        )
        try:
            buttons.setStyleSheet(
                """
                QDialogButtonBox QPushButton {
                    background-color: #303030;
                    color: #eeeeee;
                    border: 1px solid #5a5a5a;
                    border-radius: 4px;
                    padding: 4px 10px;
                }
                QDialogButtonBox QPushButton:hover { background: #575757; }
                QDialogButtonBox QPushButton:pressed { background: #6a6a6a; }
                """
            )
        except Exception:
            pass
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_row_enabled(self, key: str, checked: bool) -> None:
        spin = self._spins[key]
        if checked and self._current_constraint_value(key) is None:
            spin.setValue(float(self._default_value(key)))
        spin.setEnabled(bool(checked))
        self._refresh_warning_for_key(key)

    def _refresh_warnings(self) -> None:
        for key in KINEMATIC_CONSTRAINT_KEYS:
            self._refresh_warning_for_key(key)
        for key in TERMINAL_CONSTRAINT_KEYS:
            label = self._warnings.get(key)
            if label is not None:
                label.setText("")
                label.setProperty("activeWarning", False)
                label.setVisible(False)

    def _refresh_warning_for_key(self, key: str) -> None:
        label = self._warnings.get(key)
        if label is None:
            return
        if key not in KINEMATIC_CONSTRAINT_KEYS or not self._enabled[key].isChecked():
            label.setText("")
            label.setProperty("activeWarning", False)
            label.setVisible(False)
            return

        flat_value = float(self._spins[key].value())
        clamped_count = 0
        for rc in getattr(self._path, "ranged_constraints", []) or []:
            try:
                if (
                    getattr(rc, "key", None) == key
                    and float(getattr(rc, "value", 0.0)) > flat_value
                ):
                    clamped_count += 1
            except Exception:
                continue

        if clamped_count:
            noun = "span" if clamped_count == 1 else "spans"
            label.setText(
                f"{clamped_count} ranged {noun} above this value will be constrained "
                "by the whole-path limit."
            )
            label.setProperty("activeWarning", True)
            label.setVisible(True)
        else:
            label.setText("")
            label.setProperty("activeWarning", False)
            label.setVisible(False)

    def _current_constraint_value(self, key: str) -> Optional[float]:
        constraints = getattr(self._path, "constraints", None)
        if constraints is None:
            return None
        try:
            value = getattr(constraints, key, None)
            return float(value) if value is not None else None
        except Exception:
            return None

    def _default_value(self, key: str) -> float:
        default_key = f"default_{key}"
        value = self._config.get(default_key)
        if value is None:
            value = self._config.get(key)
        try:
            if value is not None:
                return float(value)
        except Exception:
            pass
        return constraint_default_value(key)
