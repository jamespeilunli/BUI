from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QHBoxLayout, QWidget

from models.path_model import Path, RangedConstraint, TranslationTarget
from ui.sidebar.components.constraint_manager import ConstraintManager
from ui.sidebar.widgets.segment_bar import SegmentBar


class _ProjectManagerStub:
    def __init__(self, defaults: dict[str, float]):
        self._defaults = defaults

    def get_default_optional_value(self, key: str):
        return self._defaults.get(key)


def _translation_path() -> Path:
    return Path(path_elements=[TranslationTarget(), TranslationTarget()])


def test_gap_double_click_uses_project_manager_default_value(qt_app):
    key = "max_velocity_meters_per_sec"
    expected = 4.25

    manager = ConstraintManager()
    manager.project_manager = _ProjectManagerStub({key: expected})
    path = _translation_path()
    manager.set_path(path)

    manager._on_gap_double_clicked(key, 1, 1)

    matching = [
        rc
        for rc in path.ranged_constraints
        if rc.key == key and rc.start_ordinal == 1 and rc.end_ordinal == 1
    ]

    assert matching
    assert matching[-1].value == expected


def test_rebuilding_segment_bar_replaces_dynamic_widgets_without_duplicates(qt_app):
    key = "max_velocity_meters_per_sec"
    path = Path(
        path_elements=[TranslationTarget(), TranslationTarget(), TranslationTarget()],
        ranged_constraints=[
            RangedConstraint(key=key, value=2.0, start_ordinal=1, end_ordinal=1),
            RangedConstraint(key=key, value=3.0, start_ordinal=2, end_ordinal=3),
        ],
    )
    manager = ConstraintManager()
    manager.set_path(path)

    parent = QWidget()
    layout = QFormLayout(parent)
    label = QLabel("Velocity")
    spin_row = QWidget()
    spin_row.setLayout(QHBoxLayout())
    control = QDoubleSpinBox()
    spin_row.layout().addWidget(control)
    layout.addRow(label, spin_row)
    parent.show()

    manager.create_segment_bar_for_key(key, control, spin_row, label, layout)
    qt_app.processEvents()
    assert len(parent.findChildren(SegmentBar)) == 1
    assert manager._segment_spinboxes[key].isVisible()

    manager.create_segment_bar_for_key(key, control, spin_row, label, layout)
    qt_app.processEvents()

    assert len(parent.findChildren(SegmentBar)) == 1
    assert manager._segment_spinboxes[key] is control
    assert control.isVisible()

    parent.close()
