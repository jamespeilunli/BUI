from __future__ import annotations

from models.path_model import Path, TranslationTarget
from ui.main_window.window import MainWindow


def test_shared_element_delete_leaves_no_replacement_selection(qt_app):
    window = MainWindow()
    window._record_path_change = lambda *args, **kwargs: None
    window.path = Path(
        path_elements=[
            TranslationTarget(0.0, 0.0),
            TranslationTarget(1.0, 0.0),
            TranslationTarget(2.0, 0.0),
        ]
    )
    window.sidebar.set_path(window.path)
    window.canvas.set_path(window.path)
    window.timeline.set_path(window.path, window._timeline_config())

    window._select_path_index_across_views(1, center_canvas=False)
    assert window.sidebar.get_selected_index() == 1
    assert window.timeline._selection is not None

    window._delete_selected_element()

    assert len(window.path.path_elements) == 2
    assert window.sidebar.get_selected_index() is None
    assert window.timeline._selection is None
    assert window.canvas.graphics_scene.selectedItems() == []
    window.close()
