from __future__ import annotations

from models.path_model import Path, RangedConstraint
from ui.path_settings_dialog import PathSettingsDialog


def test_path_settings_dialog_uses_config_default_when_enabling_unset_value(qt_app):
    path = Path()
    dialog = PathSettingsDialog(
        None,
        path,
        {"default_max_velocity_meters_per_sec": 4.25},
    )

    try:
        key = "max_velocity_meters_per_sec"
        assert not dialog._enabled[key].isChecked()
        assert not dialog._spins[key].isEnabled()
        assert dialog._spins[key].value() == 4.25

        dialog._enabled[key].setChecked(True)

        assert dialog._spins[key].isEnabled()
        assert dialog.get_values()[key] == 4.25
    finally:
        dialog.close()


def test_path_settings_dialog_removes_enabled_value(qt_app):
    path = Path()
    path.constraints.end_rotation_tolerance_deg = 2.0
    dialog = PathSettingsDialog(None, path, {})

    try:
        key = "end_rotation_tolerance_deg"
        assert dialog._enabled[key].isChecked()

        dialog._enabled[key].setChecked(False)

        assert dialog.get_values()[key] is None
    finally:
        dialog.close()


def test_path_settings_dialog_warns_when_range_is_above_whole_path_limit(qt_app):
    path = Path(
        ranged_constraints=[
            RangedConstraint(
                key="max_velocity_meters_per_sec",
                value=3.0,
                start_ordinal=1,
                end_ordinal=2,
            )
        ]
    )
    path.constraints.max_velocity_meters_per_sec = 2.0
    dialog = PathSettingsDialog(None, path, {})

    try:
        key = "max_velocity_meters_per_sec"
        assert "whole-path limit" in dialog.warning_text_for_key(key)

        dialog._spins[key].setValue(4.0)

        assert dialog.warning_text_for_key(key) == ""
    finally:
        dialog.close()
