from __future__ import annotations

from ui.canvas.view import CanvasView


def _visible_lines(canvas: CanvasView) -> list[bool]:
    return [line.isVisible() for line in canvas._trail_lines]


def _install_sim_samples(canvas: CanvasView) -> None:
    canvas._sim_times_sorted = [0.0, 1.0, 2.0, 3.0]
    canvas._sim_total_time_s = 3.0
    canvas._sim_poses_by_time = {
        0.0: (0.0, 0.0, 0.0),
        1.0: (1.0, 0.0, 0.0),
        2.0: (2.0, 0.0, 0.0),
        3.0: (3.0, 0.0, 0.0),
    }


def test_simulated_path_hidden_hides_all_trail_lines(qt_app):
    canvas = CanvasView()
    try:
        canvas.set_simulated_path_display_mode("hidden")
        canvas._setup_trail([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])

        assert canvas.simulated_path_display_mode() == "hidden"
        assert _visible_lines(canvas) == [False, False]
    finally:
        canvas.close()


def test_simulated_path_to_current_time_tracks_playback_time(qt_app):
    canvas = CanvasView()
    try:
        _install_sim_samples(canvas)
        canvas._setup_trail([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])

        assert canvas.simulated_path_display_mode() == "to_current_time"
        assert _visible_lines(canvas) == [False, False, False]

        canvas.set_playback_time(2.1)

        assert _visible_lines(canvas) == [True, True, False]
    finally:
        canvas.close()


def test_simulated_path_complete_stays_visible_after_scrub_and_rebuild(qt_app):
    canvas = CanvasView()
    try:
        _install_sim_samples(canvas)
        canvas.set_simulated_path_display_mode("complete")
        canvas._setup_trail([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])

        assert _visible_lines(canvas) == [True, True, True]

        canvas.set_playback_time(1.0)

        assert _visible_lines(canvas) == [True, True, True]

        canvas._setup_trail([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])

        assert _visible_lines(canvas) == [True, True]
    finally:
        canvas.close()
