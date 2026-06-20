from __future__ import annotations

import json
from pathlib import Path

from models.path_model import Path as PathModel, TranslationTarget
from utils.project_manager import ProjectConfig, ProjectManager


class DummySettings:
    def __init__(self):
        self._store: dict[str, str] = {}

    def setValue(self, key: str, value):
        self._store[key] = value

    def value(self, key: str, type=None):
        return self._store.get(key)

    def remove(self, key: str):
        self._store.pop(key, None)


def test_project_config_updates():
    cfg = ProjectConfig()
    cfg.update_from_mapping({"robot_length_meters": 0.75})
    assert cfg.robot_length_meters == 0.75
    assert (
        cfg.get_default_optional_value("max_velocity_meters_per_sec")
        == cfg.default_max_velocity_meters_per_sec
    )


def test_project_config_migrates_legacy_protrusions():
    cfg = ProjectConfig.from_mapping(
        {
            "robot_length_meters": 0.7,
            "robot_width_meters": 0.6,
            "robot_protrusion_left_meters": 0.18,
            "robot_protrusion_front_meters": 0.08,
        }
    )

    assert cfg.protrusion_enabled is True
    assert cfg.protrusion_side == "left"
    assert cfg.protrusion_distance_meters == 0.18
    assert cfg.protrusion_default_state == "shown"

    structured = cfg.to_dict()
    assert "settings_version" not in structured
    assert structured["gui"]["robot"]["length_meters"] == 0.7
    assert structured["gui"]["protrusions"]["side"] == "left"
    assert structured["gui"]["protrusions"]["distance_meters"] == 0.18


def test_project_manager_uses_bui_settings_namespace(monkeypatch):
    calls: list[tuple[str, str]] = []

    class RecordingSettings(DummySettings):
        def __init__(self, organization: str, application: str):
            super().__init__()
            calls.append((organization, application))

    monkeypatch.setattr("utils.project_manager.QSettings", RecordingSettings)

    ProjectManager()

    assert ProjectManager.SETTINGS_ORG == "BUI"
    assert ProjectManager.SETTINGS_APP == "BUI"
    assert calls == [("BUI", "BUI")]


def test_project_manager_migrates_legacy_config_file(tmp_path: Path):
    pm = ProjectManager()
    pm.settings = DummySettings()
    pm.set_project_dir(str(tmp_path))

    legacy = {
        "robot_length_meters": 0.65,
        "robot_width_meters": 0.55,
        "robot_protrusion_back_meters": 0.12,
        "default_max_velocity_meters_per_sec": 3.0,
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = pm.load_config()
    assert loaded.protrusion_enabled is True
    assert loaded.protrusion_side == "back"
    assert loaded.protrusion_distance_meters == 0.12

    migrated = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "settings_version" not in migrated
    assert "gui" in migrated and "kinematic_constraints" in migrated
    assert migrated["gui"]["protrusions"]["side"] == "back"


def test_project_manager_saves_and_loads_paths(tmp_path: Path):
    pm = ProjectManager()
    pm.settings = DummySettings()
    pm.set_project_dir(str(tmp_path))

    path = PathModel()
    path.path_elements.append(TranslationTarget(x_meters=1.0, y_meters=2.0))
    saved_name = pm.save_path(path, "unit_test.json")
    assert saved_name == "unit_test.json"

    loaded = pm.load_path("unit_test.json")
    assert loaded is not None
    assert len(loaded.path_elements) == 1


def test_project_manager_persists_simulated_path_display_mode():
    pm = ProjectManager()
    pm.settings = DummySettings()

    assert pm.simulated_path_display_mode() == "to_current_time"

    pm.set_simulated_path_display_mode("complete")

    assert pm.simulated_path_display_mode() == "complete"
    assert (
        pm.settings.value(ProjectManager.KEY_SIMULATED_PATH_DISPLAY_MODE)
        == "complete"
    )

    pm.set_simulated_path_display_mode("unsupported")

    assert pm.simulated_path_display_mode() == "complete"

    pm.settings.setValue(ProjectManager.KEY_SIMULATED_PATH_DISPLAY_MODE, "unsupported")

    assert pm.simulated_path_display_mode() == "to_current_time"
