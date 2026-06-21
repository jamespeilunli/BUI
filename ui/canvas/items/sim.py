"""Simulation overlay graphics items for the canvas."""

from __future__ import annotations
import math
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsPolygonItem
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF

from ui.qt_compat import QGraphicsItem

if TYPE_CHECKING:
    from ui.canvas.view import CanvasView


class RobotSimItem(QGraphicsRectItem):
    def __init__(self, canvas_view: "CanvasView"):
        super().__init__()
        self.canvas_view = canvas_view
        robot_width_m = 0.5
        robot_length_m = 0.5
        protrusion_enabled = False
        protrusion_distance_m = 0.0
        protrusion_side = "none"
        protrusion_default_state = ""
        try:
            if hasattr(canvas_view, "_project_manager") and canvas_view._project_manager:
                if hasattr(canvas_view._project_manager, "config_as_dict"):
                    cfg = canvas_view._project_manager.config_as_dict()
                else:
                    cfg = dict(getattr(canvas_view._project_manager, "config", {}) or {})
                robot_width_m = float(cfg.get("robot_width_meters", robot_width_m))
                robot_length_m = float(cfg.get("robot_length_meters", robot_length_m))
                protrusion_enabled = bool(cfg.get("protrusion_enabled", False))
                protrusion_distance_m = max(
                    0.0, float(cfg.get("protrusion_distance_meters", protrusion_distance_m) or 0.0)
                )
                protrusion_side = (
                    str(cfg.get("protrusion_side", protrusion_side) or "none").strip().lower()
                )
                protrusion_default_state = (
                    str(cfg.get("protrusion_default_state", protrusion_default_state) or "")
                    .strip()
                    .lower()
                )
        except Exception:
            pass
        self.setBrush(QBrush(QColor(255, 165, 0, 120)))
        self.setPen(QPen(QColor("#000000"), 0.03))
        self.setZValue(15)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.triangle_item = QGraphicsPolygonItem(self)
        self.set_dimensions(
            robot_length_m,
            robot_width_m,
            protrusion_visible=bool(protrusion_enabled and protrusion_default_state == "shown"),
            protrusion_distance_m=protrusion_distance_m,
            protrusion_side=protrusion_side,
        )
        self._angle_radians = 0.0

    def set_dimensions(
        self,
        length_m: float,
        width_m: float,
        protrusion_visible: bool = False,
        protrusion_distance_m: float = 0.0,
        protrusion_side: str = "none",
    ):
        x_min = -(length_m / 2.0)
        x_max = length_m / 2.0
        y_min = -(width_m / 2.0)
        y_max = width_m / 2.0
        side = str(protrusion_side or "none").strip().lower()
        distance = max(0.0, float(protrusion_distance_m))
        if protrusion_visible and distance > 0.0:
            if side == "front":
                x_max += distance
            elif side == "back":
                x_min -= distance
            elif side == "left":
                # Robot-left maps to negative local Y for scene-rendered robot shapes.
                y_min -= distance
            elif side == "right":
                # Robot-right maps to positive local Y.
                y_max += distance
        self.setRect(x_min, y_min, x_max - x_min, y_max - y_min)
        self._build_triangle(float(self.rect().width()), float(self.rect().height()))

    def _build_triangle(self, robot_length_m: float, robot_width_m: float):
        if not self.triangle_item:
            return
        triangle_size = min(robot_length_m, robot_width_m) * 0.3
        triangle_offset = robot_length_m * 0.3
        points = [
            QPointF(triangle_offset + triangle_size, 0.0),
            QPointF(triangle_offset - triangle_size / 2, triangle_size / 2),
            QPointF(triangle_offset - triangle_size / 2, -triangle_size / 2),
        ]
        self.triangle_item.setPolygon(QPolygonF(points))
        self.triangle_item.setBrush(QBrush(QColor("#FFFFFF")))
        self.triangle_item.setPen(QPen(QColor("#000000"), 0.02))
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))
