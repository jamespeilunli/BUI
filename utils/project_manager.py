from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from PySide6.QtCore import QByteArray, QSettings

from models.path_model import Path
from utils.project_io import create_example_paths, deserialize_path, serialize_path


@dataclass
class ProjectConfig:
    robot_length_meters: float = 0.5
    robot_width_meters: float = 0.5
    protrusion_enabled: bool = False
    protrusion_distance_meters: float = 0.0
    protrusion_side: str = "none"
    protrusion_default_state: str = ""
    protrusion_show_on_event_keys: List[str] = field(default_factory=list)
    protrusion_hide_on_event_keys: List[str] = field(default_factory=list)
    default_max_velocity_meters_per_sec: float = 4.5
    default_max_acceleration_meters_per_sec2: float = 7.0
    default_intermediate_handoff_radius_meters: float = 0.2
    default_max_velocity_deg_per_sec: float = 720.0
    default_max_acceleration_deg_per_sec2: float = 1500.0
    default_end_translation_tolerance_meters: float = 0.03
    default_end_rotation_tolerance_deg: float = 2.0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ProjectConfig":
        cfg = cls()
        if data:
            cfg.update_from_mapping(data)
        return cfg

    @staticmethod
    def _lookup_path(data: Mapping[str, Any], path: Tuple[str, ...]) -> Tuple[bool, Any]:
        current: Any = data
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                return False, None
            current = current.get(key)
        return True, current

    @classmethod
    def _lookup_any(cls, data: Mapping[str, Any], paths: List[Tuple[str, ...]]) -> Tuple[bool, Any]:
        for path in paths:
            found, value = cls._lookup_path(data, path)
            if found:
                return True, value
        return False, None

    @staticmethod
    def _coerce_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(fallback)

    @staticmethod
    def _coerce_bool(value: Any, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("1", "true", "yes", "on", "enabled"):
                return True
            if lowered in ("0", "false", "no", "off", "disabled"):
                return False
        return bool(fallback)

    @staticmethod
    def _normalize_protrusion_side(value: Any, fallback: str = "none") -> str:
        valid = {"none", "left", "right", "front", "back"}
        text = str(value).strip().lower()
        return text if text in valid else fallback

    @staticmethod
    def _normalize_protrusion_state(value: Any, fallback: str = "") -> str:
        text = str(value).strip().lower()
        if text in ("shown", "show", "visible", "on", "true", "1"):
            return "shown"
        if text in ("hidden", "hide", "invisible", "off", "false", "0"):
            return "hidden"
        if text in ("", "none"):
            return ""
        return fallback

    @staticmethod
    def _normalize_key_list(value: Any) -> List[str]:
        values: List[str] = []
        if value is None:
            return values
        if isinstance(value, str):
            raw_items = value.replace("\n", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_items = [str(v) for v in value]
        else:
            raw_items = [str(value)]

        seen: set[str] = set()
        for raw in raw_items:
            key = str(raw).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            values.append(key)
        return values

    @classmethod
    def _legacy_protrusion_conversion(cls, data: Mapping[str, Any]) -> Tuple[bool, float, str]:
        legacy_values = {
            "front": max(0.0, cls._coerce_float(data.get("robot_protrusion_front_meters"), 0.0)),
            "back": max(0.0, cls._coerce_float(data.get("robot_protrusion_back_meters"), 0.0)),
            "left": max(0.0, cls._coerce_float(data.get("robot_protrusion_left_meters"), 0.0)),
            "right": max(0.0, cls._coerce_float(data.get("robot_protrusion_right_meters"), 0.0)),
        }
        if not any(v > 0.0 for v in legacy_values.values()):
            return False, 0.0, "none"
        priority = ["front", "back", "left", "right"]
        best_side = max(priority, key=lambda k: (legacy_values[k], -priority.index(k)))
        return True, float(legacy_values[best_side]), best_side

    @classmethod
    def needs_migration(cls, data: Mapping[str, Any] | None) -> bool:
        if not isinstance(data, Mapping):
            return False
        gui = data.get("gui")
        if not isinstance(gui, Mapping):
            return True
        if not isinstance(gui.get("robot"), Mapping):
            return True
        if not isinstance(gui.get("protrusions"), Mapping):
            return True
        if not isinstance(data.get("kinematic_constraints"), Mapping):
            return True
        legacy_keys = (
            "robot_protrusion_front_meters",
            "robot_protrusion_back_meters",
            "robot_protrusion_left_meters",
            "robot_protrusion_right_meters",
        )
        return any(k in data for k in legacy_keys)

    def update_from_mapping(self, data: Mapping[str, Any]) -> None:
        # GUI: robot dimensions
        found, value = self._lookup_any(
            data,
            [("robot_length_meters",), ("gui", "robot", "length_meters")],
        )
        if found:
            self.robot_length_meters = max(0.0, self._coerce_float(value, self.robot_length_meters))

        found, value = self._lookup_any(
            data,
            [("robot_width_meters",), ("gui", "robot", "width_meters")],
        )
        if found:
            self.robot_width_meters = max(0.0, self._coerce_float(value, self.robot_width_meters))

        # GUI: protrusion options
        enabled_found, enabled_value = self._lookup_any(
            data,
            [("protrusion_enabled",), ("gui", "protrusions", "enabled")],
        )
        if enabled_found:
            self.protrusion_enabled = self._coerce_bool(enabled_value, self.protrusion_enabled)

        distance_found, distance_value = self._lookup_any(
            data,
            [("protrusion_distance_meters",), ("gui", "protrusions", "distance_meters")],
        )
        if distance_found:
            self.protrusion_distance_meters = max(
                0.0, self._coerce_float(distance_value, self.protrusion_distance_meters)
            )

        side_found, side_value = self._lookup_any(
            data,
            [("protrusion_side",), ("gui", "protrusions", "side")],
        )
        if side_found:
            self.protrusion_side = self._normalize_protrusion_side(side_value, self.protrusion_side)

        default_state_found, default_state_value = self._lookup_any(
            data,
            [("protrusion_default_state",), ("gui", "protrusions", "default_state")],
        )
        if default_state_found:
            self.protrusion_default_state = self._normalize_protrusion_state(
                default_state_value, self.protrusion_default_state
            )

        # Optional event mapping object: { "keyA": "shown", "keyB": "hidden" }
        state_map_found, state_map_value = self._lookup_any(
            data,
            [("gui", "protrusions", "event_state_overrides")],
        )
        if state_map_found and isinstance(state_map_value, Mapping):
            show_keys: List[str] = []
            hide_keys: List[str] = []
            for raw_key, raw_state in state_map_value.items():
                key = str(raw_key).strip()
                if not key:
                    continue
                state = self._normalize_protrusion_state(raw_state, "")
                if state == "shown":
                    show_keys.append(key)
                elif state == "hidden":
                    hide_keys.append(key)
            self.protrusion_show_on_event_keys = self._normalize_key_list(show_keys)
            self.protrusion_hide_on_event_keys = self._normalize_key_list(hide_keys)

        show_found, show_value = self._lookup_any(
            data,
            [("protrusion_show_on_event_keys",), ("gui", "protrusions", "show_on_event_keys")],
        )
        if show_found:
            self.protrusion_show_on_event_keys = self._normalize_key_list(show_value)

        hide_found, hide_value = self._lookup_any(
            data,
            [("protrusion_hide_on_event_keys",), ("gui", "protrusions", "hide_on_event_keys")],
        )
        if hide_found:
            self.protrusion_hide_on_event_keys = self._normalize_key_list(hide_value)

        # Legacy protrusion migration (flat directional values)
        legacy_keys = (
            "robot_protrusion_front_meters",
            "robot_protrusion_back_meters",
            "robot_protrusion_left_meters",
            "robot_protrusion_right_meters",
        )
        legacy_present = any(key in data for key in legacy_keys)
        new_protrusion_present = (
            any(
                (
                    enabled_found,
                    distance_found,
                    side_found,
                    default_state_found,
                    show_found,
                    hide_found,
                )
            )
            or self._lookup_path(data, ("gui", "protrusions"))[0]
        )
        if legacy_present and not new_protrusion_present:
            enabled, distance, side = self._legacy_protrusion_conversion(data)
            self.protrusion_enabled = enabled
            self.protrusion_distance_meters = distance
            self.protrusion_side = side
            self.protrusion_default_state = "shown" if enabled else ""
            self.protrusion_show_on_event_keys = []
            self.protrusion_hide_on_event_keys = []

        # Kinematic constraints defaults
        default_numeric_keys = (
            "default_max_velocity_meters_per_sec",
            "default_max_acceleration_meters_per_sec2",
            "default_intermediate_handoff_radius_meters",
            "default_max_velocity_deg_per_sec",
            "default_max_acceleration_deg_per_sec2",
            "default_end_translation_tolerance_meters",
            "default_end_rotation_tolerance_deg",
        )
        for key in default_numeric_keys:
            found, value = self._lookup_any(
                data,
                [(key,), ("kinematic_constraints", key)],
            )
            if not found:
                continue
            setattr(self, key, max(0.0, self._coerce_float(value, getattr(self, key))))

        self.protrusion_side = self._normalize_protrusion_side(self.protrusion_side, "none")
        if not bool(self.protrusion_enabled):
            self.protrusion_default_state = ""
        else:
            self.protrusion_default_state = self._normalize_protrusion_state(
                self.protrusion_default_state, ""
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gui": {
                "robot": {
                    "length_meters": float(self.robot_length_meters),
                    "width_meters": float(self.robot_width_meters),
                },
                "protrusions": {
                    "enabled": bool(self.protrusion_enabled),
                    "distance_meters": float(max(0.0, self.protrusion_distance_meters)),
                    "side": self._normalize_protrusion_side(self.protrusion_side, "none"),
                    "default_state": (
                        self._normalize_protrusion_state(self.protrusion_default_state, "")
                        if bool(self.protrusion_enabled)
                        else ""
                    ),
                    "show_on_event_keys": self._normalize_key_list(
                        self.protrusion_show_on_event_keys
                    ),
                    "hide_on_event_keys": self._normalize_key_list(
                        self.protrusion_hide_on_event_keys
                    ),
                },
            },
            "kinematic_constraints": {
                "default_max_velocity_meters_per_sec": float(
                    self.default_max_velocity_meters_per_sec
                ),
                "default_max_acceleration_meters_per_sec2": float(
                    self.default_max_acceleration_meters_per_sec2
                ),
                "default_intermediate_handoff_radius_meters": float(
                    self.default_intermediate_handoff_radius_meters
                ),
                "default_max_velocity_deg_per_sec": float(self.default_max_velocity_deg_per_sec),
                "default_max_acceleration_deg_per_sec2": float(
                    self.default_max_acceleration_deg_per_sec2
                ),
                "default_end_translation_tolerance_meters": float(
                    self.default_end_translation_tolerance_meters
                ),
                "default_end_rotation_tolerance_deg": float(
                    self.default_end_rotation_tolerance_deg
                ),
            },
        }

    def to_flat_dict(self) -> Dict[str, Any]:
        side = self._normalize_protrusion_side(self.protrusion_side, "none")
        distance = float(max(0.0, self.protrusion_distance_meters))
        enabled = bool(self.protrusion_enabled)
        default_state = (
            self._normalize_protrusion_state(self.protrusion_default_state, "") if enabled else ""
        )
        legacy_front = distance if enabled and side == "front" else 0.0
        legacy_back = distance if enabled and side == "back" else 0.0
        legacy_left = distance if enabled and side == "left" else 0.0
        legacy_right = distance if enabled and side == "right" else 0.0

        return {
            "robot_length_meters": float(self.robot_length_meters),
            "robot_width_meters": float(self.robot_width_meters),
            "protrusion_enabled": enabled,
            "protrusion_distance_meters": distance,
            "protrusion_side": side,
            "protrusion_default_state": default_state,
            "protrusion_show_on_event_keys": self._normalize_key_list(
                self.protrusion_show_on_event_keys
            ),
            "protrusion_hide_on_event_keys": self._normalize_key_list(
                self.protrusion_hide_on_event_keys
            ),
            # Legacy compatibility projection (directional distances)
            "robot_protrusion_front_meters": legacy_front,
            "robot_protrusion_back_meters": legacy_back,
            "robot_protrusion_left_meters": legacy_left,
            "robot_protrusion_right_meters": legacy_right,
            "default_max_velocity_meters_per_sec": float(self.default_max_velocity_meters_per_sec),
            "default_max_acceleration_meters_per_sec2": float(
                self.default_max_acceleration_meters_per_sec2
            ),
            "default_intermediate_handoff_radius_meters": float(
                self.default_intermediate_handoff_radius_meters
            ),
            "default_max_velocity_deg_per_sec": float(self.default_max_velocity_deg_per_sec),
            "default_max_acceleration_deg_per_sec2": float(
                self.default_max_acceleration_deg_per_sec2
            ),
            "default_end_translation_tolerance_meters": float(
                self.default_end_translation_tolerance_meters
            ),
            "default_end_rotation_tolerance_deg": float(self.default_end_rotation_tolerance_deg),
        }

    def get_default_optional_value(self, key: str) -> Optional[float]:
        # Prefer default_* keys but fall back to raw key to handle legacy lookups
        default_key = f"default_{key}"
        if hasattr(self, default_key):
            return float(getattr(self, default_key))
        if hasattr(self, key):
            return float(getattr(self, key))
        return None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class ProjectManager:
    """Handles project directory, config.json, and path JSON load/save.

    Persists last project dir and last opened path via QSettings.
    """

    SETTINGS_ORG = "BUI"
    SETTINGS_APP = "BUI"
    KEY_LAST_PROJECT_DIR = "project/last_project_dir"
    KEY_LAST_PATH_FILE = "project/last_path_file"
    KEY_RECENT_PROJECTS = "project/recent_projects"
    KEY_SIMULATED_PATH_DISPLAY_MODE = "view/simulated_path_display_mode"
    KEY_MAIN_WINDOW_GEOMETRY = "view/main_window_geometry"
    SIMULATED_PATH_DISPLAY_MODES = {"hidden", "to_current_time", "complete"}
    DEFAULT_SIMULATED_PATH_DISPLAY_MODE = "to_current_time"

    def __init__(self):
        self.settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
        self.project_dir: Optional[str] = None
        self.config = ProjectConfig()
        self.current_path_file: Optional[str] = None  # filename like "example.json"

    # --------------- Project directory ---------------
    def _is_frc_repo_root(self, directory: str) -> bool:
        """Check if the directory appears to be an FRC repository root (contains src/main/deploy/)."""
        deploy_path = os.path.join(directory, "src", "main", "deploy")
        return os.path.isdir(deploy_path)

    def _get_effective_project_dir(self, selected_dir: str) -> str:
        """Get the effective project directory, handling FRC repo structure automatically."""
        selected_dir = os.path.abspath(selected_dir)

        # If this is already an autos directory, use it directly
        if os.path.basename(selected_dir) == "autos":
            return selected_dir

        # Check if selected directory is an FRC repo root
        if self._is_frc_repo_root(selected_dir):
            autos_dir = os.path.join(selected_dir, "src", "main", "deploy", "autos")
            return autos_dir

        # For non-FRC directories, use as-is
        return selected_dir

    def set_project_dir(self, directory: str) -> None:
        directory = os.path.abspath(directory)
        effective_dir = self._get_effective_project_dir(directory)
        self.project_dir = effective_dir
        self.settings.setValue(
            self.KEY_LAST_PROJECT_DIR, directory
        )  # Store original selected dir for UI
        self.ensure_project_structure()
        # Track recents only after ensuring structure exists
        self._add_recent_project(effective_dir)
        self.load_config()

    def get_paths_dir(self) -> Optional[str]:
        if not self.project_dir:
            return None
        return os.path.join(self.project_dir, "paths")

    def ensure_project_structure(self) -> None:
        if not self.project_dir:
            return
        _ensure_dir(self.project_dir)
        paths_dir = os.path.join(self.project_dir, "paths")
        _ensure_dir(paths_dir)
        # Create default config if missing
        cfg_path = os.path.join(self.project_dir, "config.json")
        if not os.path.exists(cfg_path):
            self.save_config()
        # Create example files if paths folder empty
        try:
            if not os.listdir(paths_dir):
                create_example_paths(paths_dir)
        except Exception:
            pass

    def has_valid_project(self) -> bool:
        if not self.project_dir:
            return False
        cfg = os.path.join(self.project_dir, "config.json")
        paths = os.path.join(self.project_dir, "paths")
        return os.path.isdir(self.project_dir) and os.path.isfile(cfg) and os.path.isdir(paths)

    def load_last_project(self) -> bool:
        last_dir = self.settings.value(self.KEY_LAST_PROJECT_DIR, type=str)
        if not last_dir:
            return False

        # Get the effective project directory (handles FRC repo redirection)
        effective_dir = self._get_effective_project_dir(last_dir)

        # Validate without creating any files. Only accept if already valid.
        cfg = os.path.join(effective_dir, "config.json")
        paths = os.path.join(effective_dir, "paths")
        if os.path.isdir(effective_dir) and os.path.isfile(cfg) and os.path.isdir(paths):
            # Use the original last_dir to maintain the same behavior for set_project_dir
            self.set_project_dir(last_dir)
            return True
        return False

    # --------------- Recent Projects ---------------
    def recent_projects(self) -> List[str]:
        raw = self.settings.value(self.KEY_RECENT_PROJECTS)
        if not raw:
            return []
        # QSettings may return list or str
        if isinstance(raw, list):
            items = [str(x) for x in raw]
        else:
            try:
                items = json.loads(str(raw))
                if not isinstance(items, list):
                    items = []
            except Exception:
                items = []
        # Filter only existing dirs, and resolve FRC repo paths to their effective directories
        filtered_items = []
        for p in items:
            if isinstance(p, str) and os.path.isdir(p):
                effective_dir = self._get_effective_project_dir(p)
                if os.path.isdir(effective_dir):
                    filtered_items.append(effective_dir)
        # unique while preserving order
        seen = set()
        uniq = []
        for p in filtered_items:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return uniq[:10]

    def _add_recent_project(self, directory: str) -> None:
        if not directory:
            return
        items = self.recent_projects()
        # move to front
        items = [d for d in items if d != directory]
        items.insert(0, directory)
        items = items[:10]
        # Store as JSON string to be robust
        try:
            self.settings.setValue(self.KEY_RECENT_PROJECTS, json.dumps(items))
        except Exception:
            pass

    # --------------- Application view preferences ---------------
    def simulated_path_display_mode(self) -> str:
        raw = self.settings.value(self.KEY_SIMULATED_PATH_DISPLAY_MODE, type=str)
        mode = str(raw or "").strip().lower()
        if mode in self.SIMULATED_PATH_DISPLAY_MODES:
            return mode
        return self.DEFAULT_SIMULATED_PATH_DISPLAY_MODE

    def set_simulated_path_display_mode(self, mode: str) -> None:
        normalized = str(mode or "").strip().lower()
        if normalized not in self.SIMULATED_PATH_DISPLAY_MODES:
            return
        try:
            self.settings.setValue(self.KEY_SIMULATED_PATH_DISPLAY_MODE, normalized)
        except Exception:
            pass

    def main_window_geometry(self) -> Optional[QByteArray]:
        raw = self.settings.value(self.KEY_MAIN_WINDOW_GEOMETRY)
        if isinstance(raw, QByteArray):
            return raw if not raw.isEmpty() else None
        if isinstance(raw, (bytes, bytearray)):
            geometry = QByteArray(bytes(raw))
            return geometry if not geometry.isEmpty() else None
        return None

    def set_main_window_geometry(self, geometry: QByteArray | bytes | bytearray) -> None:
        try:
            value = geometry if isinstance(geometry, QByteArray) else QByteArray(bytes(geometry))
            if value.isEmpty():
                return
            self.settings.setValue(self.KEY_MAIN_WINDOW_GEOMETRY, value)
        except Exception:
            pass

    # --------------- Config ---------------
    def load_config(self) -> ProjectConfig:
        if not self.project_dir:
            return self.config
        cfg_path = os.path.join(self.project_dir, "config.json")
        try:
            migrated = False
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.config = ProjectConfig.from_mapping(data)
                    migrated = ProjectConfig.needs_migration(data)
            if migrated:
                self.save_config()
        except Exception:
            # Keep existing config on error
            pass
        return self.config

    def save_config(self, new_config: Optional[Mapping[str, Any]] = None) -> None:
        if new_config is not None:
            self.config.update_from_mapping(new_config)
        if not self.project_dir:
            return
        cfg_path = os.path.join(self.project_dir, "config.json")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=2)
        except Exception:
            pass

    def get_default_optional_value(self, key: str) -> Optional[float]:
        return self.config.get_default_optional_value(key)

    def config_as_dict(self) -> Dict[str, Any]:
        return self.config.to_flat_dict()

    # --------------- Paths listing ---------------
    def list_paths(self) -> List[str]:
        paths_dir = self.get_paths_dir()
        if not paths_dir or not os.path.isdir(paths_dir):
            return []
        files = [f for f in os.listdir(paths_dir) if f.lower().endswith(".json")]
        files.sort()
        return files

    # --------------- Path IO ---------------
    def load_path(self, filename: str) -> Optional[Path]:
        """Load a path from the paths directory by filename (e.g., 'my_path.json')."""
        paths_dir = self.get_paths_dir()
        if not self.project_dir or not paths_dir:
            return None
        filepath = os.path.join(paths_dir, filename)
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            path = deserialize_path(data, self.get_default_optional_value)
            self.current_path_file = filename
            # Remember in settings
            self.settings.setValue(self.KEY_LAST_PATH_FILE, filename)
            return path
        except Exception:
            return None

    def save_path(self, path: Path, filename: Optional[str] = None) -> Optional[str]:
        """Save path to filename in the paths dir. If filename is None, uses current_path_file
        or creates 'untitled.json'. Returns the filename used on success.
        """
        if filename is None:
            filename = self.current_path_file
        if filename is None:
            filename = "untitled.json"
        paths_dir = self.get_paths_dir()
        if not self.project_dir or not paths_dir:
            return None
        _ensure_dir(paths_dir)
        filepath = os.path.join(paths_dir, filename)
        try:
            serialized = serialize_path(path)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2)
            self.current_path_file = filename
            self.settings.setValue(self.KEY_LAST_PATH_FILE, filename)
            return filename
        except Exception:
            return None

    def delete_path(self, filename: str) -> bool:
        """Delete a path file from the paths directory. Returns True if successful."""
        paths_dir = self.get_paths_dir()
        if not self.project_dir or not paths_dir:
            return False
        filepath = os.path.join(paths_dir, filename)
        if not os.path.isfile(filepath):
            return False
        try:
            os.remove(filepath)
            # If this was the current path, clear it
            if self.current_path_file == filename:
                self.current_path_file = None
                self.settings.remove(self.KEY_LAST_PATH_FILE)
            return True
        except Exception:
            return False

    def load_last_or_first_or_create(self) -> Tuple[Path, str]:
        """Attempt to load last path (from settings). If unavailable, load first available
        path in directory. If none exist, create 'untitled.json' empty path and return it.
        Returns (Path, filename).
        """
        # Try last used
        last_file = self.settings.value(self.KEY_LAST_PATH_FILE, type=str)
        if last_file:
            p = self.load_path(last_file)
            if p is not None:
                return p, last_file
        # Try first available
        files = self.list_paths()
        if files:
            first = files[0]
            p = self.load_path(first)
            if p is not None:
                return p, first
        # Create a new empty path
        new_path = Path()
        used = self.save_path(new_path, "untitled.json")
        if used is None:
            used = "untitled.json"
        return new_path, used
