# mypy: ignore-errors
"""Selection-driven sidebar inspector for path elements and constraints."""

from typing import Optional

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from models.ordinal_remap import remap_ranged_constraints
from models.path_model import (
    EventTrigger,
    Path,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)
from ui.qt_compat import Qt, QSizePolicy

from .components import ConstraintManager, ElementManager, PropertyEditor
from .utils import (
    ELEMENT_LABEL_TO_TYPE,
    ELEMENT_TYPE_LABELS,
    ElementType,
    RANGED_CONSTRAINT_KEYS,
    SPINNER_METADATA,
)
from .widgets import NoWheelDoubleSpinBox


class Sidebar(QWidget):
    """Right-hand inspector for the current selection."""

    elementSelected = Signal(int)
    modelChanged = Signal()
    modelStructureChanged = Signal()
    deleteSelectedRequested = Signal()
    aboutToChange = Signal(str)
    userActionOccurred = Signal(str)

    constraintRangePreviewRequested = Signal(str, int, int)
    constraintRangePreviewCleared = Signal()
    constraintTypeChanged = Signal(str)

    popoutOpened = Signal()
    popoutClosed = Signal()
    popoutSegmentSelected = Signal(str, int, int)
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, path=Path()):
        super().__init__()
        self.path = path
        self.project_manager = None

        self._suspended: bool = False
        self._ready: bool = False
        self._last_selected_index: Optional[int] = None
        self._selected_index: Optional[int] = None
        self._selected_element_identity: Optional[int] = None
        self._selected_constraint_ref: Optional[tuple[str, int, int]] = None
        self._active_constraint_key: str = str(RANGED_CONSTRAINT_KEYS[0])
        self._last_emitted_selected_index: Optional[int] = None
        self._suppress_element_selected_emit_once: bool = False

        # Compatibility placeholders for callers that still probe for these.
        self.points_list = None
        self.constraints_scroll = None

        self.element_manager = ElementManager(self)
        self.constraint_manager = ConstraintManager(self)
        self.property_editor = PropertyEditor(self)

        self._setup_ui()
        self._connect_component_signals()
        self.set_path(path)
        self.mark_ready()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        self.setMinimumWidth(280)
        self.resize(300, self.height())
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self._create_properties_section(main_layout)

        self.empty_state = QLabel("Select an element on the field or a constraint on the timeline.")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.empty_state.setStyleSheet(
            """
            color: #8f98a2;
            padding: 16px;
            border: 1px dashed #3b3f45;
            border-radius: 8px;
            background: #171717;
            """
        )
        self.empty_state.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.empty_state, 1)

        self.spinners = self.property_editor.create_property_controls(self.core_layout, None)

        self.installEventFilter(self)
        self._show_empty_state()

    def _create_properties_section(self, parent_layout) -> None:
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setStyleSheet(
            """
            QWidget#titleBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
            """
        )
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)
        title_layout.setSpacing(0)

        self.title_label = QLabel("Inspector")
        self.title_label.setStyleSheet(
            """
            font-size: 14px;
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
            """
        )
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        parent_layout.addWidget(self.title_bar)

        self.form_container = QGroupBox()
        self.form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.form_container.setStyleSheet(
            """
            QGroupBox {
                background-color: #242424;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
            }
            QLabel { color: #f0f0f0; }
            QWidget[constraintRow='true'] {
                background: #2a2a2a;
                border: 1px solid #3b3b3b;
                border-radius: 6px;
                margin: 4px 0;
            }
            """
        )

        box = QVBoxLayout(self.form_container)
        box.setContentsMargins(0, 6, 0, 6)
        box.setSpacing(4)

        self.type_row = QWidget()
        self.type_row.setProperty("constraintRow", "true")
        type_row_layout = QHBoxLayout(self.type_row)
        type_row_layout.setContentsMargins(8, 7, 8, 4)
        type_row_layout.setSpacing(6)
        self.type_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.type_label = QLabel("Type")
        self.type_combo = QComboBox()
        self.type_combo.currentTextChanged.connect(self.on_type_change)
        self.type_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        type_row_layout.addWidget(self.type_label)
        type_row_layout.addStretch()
        type_row_layout.addWidget(self.type_combo)
        box.addWidget(self.type_row)

        self.core_page = QWidget()
        self.core_layout = QFormLayout(self.core_page)
        self.core_layout.setLabelAlignment(Qt.AlignRight)
        self.core_layout.setVerticalSpacing(4)
        self.core_layout.setContentsMargins(8, 0, 8, 0)
        self.core_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        box.addWidget(self.core_page)

        self.constraint_page = QWidget()
        self.constraint_page.setContentsMargins(0, 0, 0, 0)
        constraint_layout = QFormLayout(self.constraint_page)
        constraint_layout.setLabelAlignment(Qt.AlignRight)
        constraint_layout.setVerticalSpacing(4)
        constraint_layout.setContentsMargins(8, 0, 8, 0)
        constraint_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.constraint_type_combo = QComboBox()
        self.constraint_type_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._constraint_type_key_by_label: dict[str, str] = {}
        for key in RANGED_CONSTRAINT_KEYS:
            label = self._constraint_label_for_key(str(key))
            self._constraint_type_key_by_label[label] = str(key)
            self.constraint_type_combo.addItem(label)
        self.constraint_type_combo.currentTextChanged.connect(self.on_constraint_type_change)
        constraint_layout.addRow("Type", self.constraint_type_combo)

        self.constraint_value_spin = NoWheelDoubleSpinBox()
        self.constraint_value_spin.setMinimumWidth(96)
        self.constraint_value_spin.setDecimals(3)
        self.constraint_value_spin.setKeyboardTracking(False)
        self.constraint_value_spin.valueChanged.connect(self.on_constraint_value_changed)
        constraint_layout.addRow("Value", self.constraint_value_spin)
        box.addWidget(self.constraint_page)

        parent_layout.addWidget(self.form_container, 1)

    def _connect_component_signals(self) -> None:
        self.element_manager.elementAdded.connect(lambda idx, elem: self.modelStructureChanged.emit())
        self.element_manager.elementRemoved.connect(
            lambda idx, elem: self.modelStructureChanged.emit()
        )
        self.element_manager.elementTypeChanged.connect(
            lambda idx, old, new: self.modelStructureChanged.emit()
        )
        self.element_manager.elementsReordered.connect(
            lambda order: self.modelStructureChanged.emit()
        )

        self.constraint_manager.constraintAdded.connect(lambda key, val: self.modelChanged.emit())
        self.constraint_manager.constraintRemoved.connect(lambda key: self.modelChanged.emit())
        self.constraint_manager.constraintValueChanged.connect(
            lambda key, val: self.modelChanged.emit()
        )
        self.constraint_manager.constraintRangeChanged.connect(
            lambda key, start, end: self.modelChanged.emit()
        )

        self.constraint_manager.aboutToChange.connect(self.aboutToChange)
        self.constraint_manager.userActionOccurred.connect(self.userActionOccurred)
        self.constraint_manager.constraintRangePreviewRequested.connect(
            self.constraintRangePreviewRequested
        )
        self.constraint_manager.constraintRangePreviewCleared.connect(
            self.constraintRangePreviewCleared
        )
        self.constraint_manager.popoutOpened.connect(self.popoutOpened)
        self.constraint_manager.popoutClosed.connect(self.popoutClosed)
        self.constraint_manager.popoutSegmentSelected.connect(self.popoutSegmentSelected)
        self.constraint_manager.undoRequested.connect(self.undoRequested)
        self.constraint_manager.redoRequested.connect(self.redoRequested)

        self.property_editor.propertyChanged.connect(self.on_attribute_change)
        self.property_editor.propertyRemoved.connect(self.on_attribute_removed)

    def set_suspended(self, suspended: bool) -> None:
        self._suspended = bool(suspended)

    def mark_ready(self) -> None:
        self._ready = True

    def get_selected_index(self) -> Optional[int]:
        if self.path is None or self._selected_index is None:
            return None
        if 0 <= int(self._selected_index) < len(self.path.path_elements):
            return int(self._selected_index)
        return None

    def _find_index_by_identity(self, identity: int) -> Optional[int]:
        if self.path is None:
            return None
        for index, element in enumerate(self.path.path_elements):
            if id(element) == int(identity):
                return index
        return None

    def _selected_constraint(self) -> Optional[RangedConstraint]:
        if self.path is None or self._selected_constraint_ref is None:
            return None
        key, start_ordinal, end_ordinal = self._selected_constraint_ref
        for rc in getattr(self.path, "ranged_constraints", []) or []:
            if (
                getattr(rc, "key", None) == key
                and int(getattr(rc, "start_ordinal", -1)) == int(start_ordinal)
                and int(getattr(rc, "end_ordinal", -1)) == int(end_ordinal)
            ):
                return rc
        return None

    def get_active_constraint_key(self) -> str:
        return str(self._active_constraint_key or RANGED_CONSTRAINT_KEYS[0])

    def _constraint_label_for_key(self, key: str) -> str:
        meta = SPINNER_METADATA.get(str(key), {})
        return str(meta.get("label", key)).replace("<br/>", " ")

    def _set_constraint_type_combo_key(self, key: str) -> None:
        label = self._constraint_label_for_key(str(key))
        try:
            self.constraint_type_combo.blockSignals(True)
            idx = self.constraint_type_combo.findText(label)
            if idx >= 0:
                self.constraint_type_combo.setCurrentIndex(idx)
        finally:
            self.constraint_type_combo.blockSignals(False)

    def _constraint_type_change_is_valid(
        self,
        constraint: RangedConstraint,
        new_key: str,
        new_start: int,
        new_end: int,
    ) -> bool:
        if self.path is None:
            return False
        for other in getattr(self.path, "ranged_constraints", []) or []:
            if other is constraint or getattr(other, "key", None) != new_key:
                continue
            other_start = int(getattr(other, "start_ordinal", 1))
            other_end = int(getattr(other, "end_ordinal", other_start))
            if new_start <= other_end and new_end >= other_start:
                return False
        return True

    def set_path(self, path: Path) -> None:
        self.path = path
        self.element_manager.set_path(path)
        self.constraint_manager.set_path(path)

        if self.project_manager is not None:
            self.element_manager.project_manager = self.project_manager
            self.constraint_manager.project_manager = self.project_manager
            self.property_editor.project_manager = self.project_manager

        self.refresh_current_selection()

    def select_index(self, index: int, propagate_to_canvas: bool = True, defer: bool = True) -> None:
        if self.path is None or index is None:
            return
        if index < 0 or index >= len(self.path.path_elements):
            return

        def _apply_selection() -> None:
            self.constraint_manager.clear_active_preview()
            self._selected_constraint_ref = None
            self._selected_index = int(index)
            self._last_selected_index = int(index)
            self._selected_element_identity = id(self.path.path_elements[index])
            if not propagate_to_canvas and self._selected_index != self._last_emitted_selected_index:
                self._suppress_element_selected_emit_once = True
            self.on_item_selected()

        if defer:
            QTimer.singleShot(0, _apply_selection)
        else:
            _apply_selection()

    def clear_selection(self) -> None:
        self._selected_index = None
        self._selected_constraint_ref = None
        self._selected_element_identity = None
        self._last_selected_index = None
        self._last_emitted_selected_index = None
        self._suppress_element_selected_emit_once = False
        self._show_empty_state()

    def refresh_current_selection(self) -> None:
        if self._selected_constraint_ref is not None:
            rc = self._selected_constraint()
            if rc is not None:
                self._show_constraint(rc)
                return
            self._selected_constraint_ref = None

        idx = self.get_selected_index()
        if idx is not None:
            self.on_item_selected()
            return

        if self._last_selected_index is not None and self.path is not None:
            if 0 <= int(self._last_selected_index) < len(self.path.path_elements):
                self._selected_index = int(self._last_selected_index)
                self.on_item_selected()
                return

        self._show_empty_state()

    def _show_empty_state(self) -> None:
        self.property_editor.hide_all_properties()
        self.title_bar.setVisible(False)
        self.form_container.setVisible(False)
        self.type_row.setVisible(False)
        self.core_page.setVisible(False)
        self.constraint_page.setVisible(False)
        self.empty_state.setVisible(True)

    def hide_spinners(self) -> None:
        self.property_editor.hide_all_properties()
        self.type_row.setVisible(False)
        self.core_page.setVisible(False)
        self.constraint_page.setVisible(False)
        self.form_container.setVisible(False)
        self.title_bar.setVisible(False)

    def _show_element(self, element) -> None:
        self.property_editor.hide_all_properties()
        self.constraint_page.setVisible(False)
        self.core_page.setVisible(True)
        self.type_row.setVisible(True)
        self.form_container.setVisible(True)
        self.title_bar.setVisible(True)
        self.empty_state.setVisible(False)

        self.property_editor.expose_element_properties(element)
        self.title_label.setText(self._get_entity_name(element))

        current_type = ElementType.WAYPOINT
        if isinstance(element, TranslationTarget):
            current_type = ElementType.TRANSLATION
        elif isinstance(element, RotationTarget):
            current_type = ElementType.ROTATION
        elif isinstance(element, EventTrigger):
            current_type = ElementType.EVENT_TRIGGER

        idx = self.get_selected_index()
        if idx is not None:
            self._rebuild_type_combo_for_index(idx, current_type)

    def _show_constraint(self, constraint: RangedConstraint) -> None:
        key = str(getattr(constraint, "key", ""))
        self._active_constraint_key = key or self.get_active_constraint_key()
        self._set_constraint_type_combo_key(self._active_constraint_key)

        self.property_editor.hide_all_properties()
        self.type_row.setVisible(False)
        self.core_page.setVisible(False)
        self.constraint_page.setVisible(True)
        self.form_container.setVisible(True)
        self.title_bar.setVisible(True)
        self.empty_state.setVisible(False)
        self.title_label.setText("Constraint")

        self._configure_constraint_spinbox(key)
        try:
            self.constraint_value_spin.blockSignals(True)
            self.constraint_value_spin.setValue(float(getattr(constraint, "value", 0.0)))
        finally:
            self.constraint_value_spin.blockSignals(False)

    def on_constraint_type_change(self, label: str) -> None:
        new_key = self._constraint_type_key_by_label.get(str(label))
        if not new_key:
            return

        old_active_key = self.get_active_constraint_key()
        self._active_constraint_key = str(new_key)
        self.constraintTypeChanged.emit(str(new_key))

        constraint = self._selected_constraint()
        if constraint is None:
            return

        old_key = str(getattr(constraint, "key", ""))
        if old_key == new_key:
            return

        _domain, count = self.constraint_manager.get_domain_info_for_key(str(new_key))
        total = max(1, int(count))
        new_start = max(1, min(int(getattr(constraint, "start_ordinal", 1)), total))
        new_end = max(new_start, min(int(getattr(constraint, "end_ordinal", new_start)), total))
        if not self._constraint_type_change_is_valid(constraint, str(new_key), new_start, new_end):
            self._active_constraint_key = old_active_key
            self._set_constraint_type_combo_key(old_key)
            self.constraintTypeChanged.emit(old_active_key)
            return

        desc = f"Change Constraint Type: {self._constraint_label_for_key(str(new_key))}"
        self.aboutToChange.emit(desc)
        constraint.key = str(new_key)
        constraint.start_ordinal = int(new_start)
        constraint.end_ordinal = int(new_end)
        self._selected_constraint_ref = (str(new_key), int(new_start), int(new_end))
        self._configure_constraint_spinbox(str(new_key))
        self.modelChanged.emit()
        self.constraintRangePreviewRequested.emit(str(new_key), int(new_start), int(new_end))
        self.userActionOccurred.emit(desc)

    def update_current_values_only(self) -> None:
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.property_editor.update_values_only(self.path.get_element(idx))
            return

        rc = self._selected_constraint()
        if rc is not None:
            try:
                self.constraint_value_spin.blockSignals(True)
                self.constraint_value_spin.setValue(float(getattr(rc, "value", 0.0)))
            finally:
                self.constraint_value_spin.blockSignals(False)

    def on_item_selected(self) -> None:
        if self._suspended or not self._ready:
            return

        idx = self.get_selected_index()
        if idx is None or self.path is None:
            self._show_empty_state()
            return

        try:
            element = self.path.get_element(idx)
        except Exception:
            self._show_empty_state()
            return

        self._selected_constraint_ref = None
        self._selected_element_identity = id(element)
        self._last_selected_index = idx
        self._show_element(element)

        if self._suppress_element_selected_emit_once:
            self._suppress_element_selected_emit_once = False
            self._last_emitted_selected_index = idx
        elif self._last_emitted_selected_index != idx:
            self.elementSelected.emit(idx)
            self._last_emitted_selected_index = idx

    def _rebuild_type_combo_for_index(self, idx: int, current_type: ElementType) -> None:
        if self.path is None:
            return
        is_end = idx == 0 or idx == len(self.path.path_elements) - 1
        allowed = [ELEMENT_TYPE_LABELS[e] for e in ElementType]
        if is_end and current_type not in (ElementType.ROTATION, ElementType.EVENT_TRIGGER):
            allowed = [
                ELEMENT_TYPE_LABELS[ElementType.TRANSLATION],
                ELEMENT_TYPE_LABELS[ElementType.WAYPOINT],
            ]
        try:
            self.type_combo.blockSignals(True)
            self.type_combo.clear()
            self.type_combo.addItems(allowed)
            self.type_combo.setCurrentText(ELEMENT_TYPE_LABELS[current_type])
        finally:
            self.type_combo.blockSignals(False)

    def on_type_change(self, value: str) -> None:
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return

        new_type = ELEMENT_LABEL_TO_TYPE.get(value) or ElementType(value)
        old_elements = self.path.path_elements[:]
        self.aboutToChange.emit(f"Change element type to {new_type.value}")

        if self.element_manager.change_element_type(idx, new_type):
            remap_ranged_constraints(self.path, old_elements)
            self._selected_index = idx
            self.refresh_current_selection()
            self.userActionOccurred.emit(f"Change element type to {new_type.value}")

    def on_attribute_change(self, key, value) -> None:
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return

        element = self.path.get_element(idx)
        label_text = str(SPINNER_METADATA.get(key, {}).get("label", key)).replace("<br/>", " ")
        desc = f"Edit {self._get_entity_name(element)} {label_text}"
        self.aboutToChange.emit(desc)
        self.property_editor.set_property_value(key, value, element)
        self.modelChanged.emit()
        self.userActionOccurred.emit(desc)

    def on_attribute_removed(self, key) -> None:
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return

        element = self.path.get_element(idx)
        label_text = str(SPINNER_METADATA.get(key, {}).get("label", key)).replace("<br/>", " ")
        desc = f"Remove {label_text}"
        self.aboutToChange.emit(desc)
        self.property_editor.set_property_value(key, None, element)
        self.refresh_current_selection()
        self.modelChanged.emit()
        self.userActionOccurred.emit(desc)

    def _configure_constraint_spinbox(self, key: str) -> None:
        meta = SPINNER_METADATA.get(key, {})
        step = float(meta.get("step", 0.1))
        min_val, max_val = meta.get("range", (0.0, 99999.0))
        suffix = ""
        label_text = str(meta.get("label", key)).replace("<br/>", " ")
        if "(" in label_text and label_text.endswith(")"):
            suffix = " " + label_text[label_text.rfind("(") + 1 : -1]
            if suffix.strip() in {"0-1", "0–1"}:
                suffix = ""

        decimals = 0
        if "." in str(step):
            decimals = len(str(step).rstrip("0").split(".")[-1])

        self.constraint_value_spin.setSingleStep(step)
        self.constraint_value_spin.setRange(float(min_val), float(max_val))
        self.constraint_value_spin.setDecimals(max(0, min(4, decimals if decimals else 3)))
        self.constraint_value_spin.setSuffix(suffix)

    def on_constraint_value_changed(self, value: float) -> None:
        constraint = self._selected_constraint()
        if constraint is None:
            return

        label_text = str(SPINNER_METADATA.get(constraint.key, {}).get("label", constraint.key))
        label_text = label_text.replace("<br/>", " ")
        desc = f"Edit Constraint Value: {label_text}"
        self.aboutToChange.emit(desc)
        constraint.value = float(value)
        self.modelChanged.emit()
        self.userActionOccurred.emit(desc)

    def _check_and_swap_rotation_targets(self) -> bool:
        try:
            return bool(self.element_manager.check_and_swap_rotation_targets())
        except Exception:
            return False

    def rebuild_points_list(self) -> None:
        self.refresh_current_selection()

    def _on_remove_element(self, idx_to_remove: int) -> None:
        if self.path is None:
            return
        if idx_to_remove < 0 or idx_to_remove >= len(self.path.path_elements):
            return

        old_elements = self.path.path_elements[:]
        self.element_manager.remove_element(idx_to_remove)
        remap_ranged_constraints(self.path, old_elements)
        self.clear_selection()

    def _get_entity_name(self, element) -> str:
        if isinstance(element, Waypoint):
            return "Waypoint"
        if isinstance(element, RotationTarget):
            return "Rotation"
        if isinstance(element, EventTrigger):
            return "Event Trigger"
        if isinstance(element, TranslationTarget):
            return "Translation"
        return "Element"

    def _delete_via_shortcut(self) -> None:
        self.deleteSelectedRequested.emit()

    def eventFilter(self, obj, event):
        try:
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
                target_widget = obj
                if obj is self:
                    try:
                        pt = event.position().toPoint()
                    except Exception:
                        pt = event.pos()
                    child = self.childAt(pt)
                    if child is not None:
                        target_widget = child

                if self.is_widget_range_related(target_widget):
                    return False

                self.constraint_manager.clear_active_preview()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def clear_active_preview(self) -> None:
        self.constraint_manager.clear_active_preview()

    def select_constraint_range(
        self,
        key: str,
        start_ordinal: int,
        end_ordinal: int,
        *,
        emit_preview: bool = True,
    ) -> bool:
        if self.path is None:
            return False

        self._selected_constraint_ref = (str(key), int(start_ordinal), int(end_ordinal))
        self._selected_index = None
        self._selected_element_identity = None
        self._last_emitted_selected_index = None
        self._suppress_element_selected_emit_once = False

        rc = self._selected_constraint()
        if rc is None:
            self._selected_constraint_ref = None
            self._show_empty_state()
            return False

        if emit_preview:
            self.constraintRangePreviewRequested.emit(str(key), int(start_ordinal), int(end_ordinal))
        self._show_constraint(rc)
        return True

    def is_widget_range_related(self, widget: QWidget) -> bool:
        if self.constraint_manager.is_widget_range_related(widget):
            return True
        if widget is None or self._selected_constraint_ref is None:
            return False
        try:
            if widget is self.constraint_page or self.constraint_page.isAncestorOf(widget):
                return True
            if widget is self.form_container or self.form_container.isAncestorOf(widget):
                return True
            if widget is self.title_bar or self.title_bar.isAncestorOf(widget):
                return True
        except Exception:
            return False
        return False
