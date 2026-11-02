import copy
import os
import subprocess
import sys

import pytest

from wizq.settings import get, set_value
from wizq.windowing import Monitor, WindowManager, arrange, identity, overlap, recover_rect, tile_rects

MONITORS = [
    Monitor("main", (0, 0, 1920, 1080), (0, 0, 1920, 1040), True),
    Monitor("left", (-1280, -120, 1280, 1024), (-1240, -120, 1240, 1024)),
]


@pytest.mark.parametrize(
    "layout", ["auto", "horizontal", "vertical", "2x2", "grid", "main-left", "main-right", "main-top"]
)
def test_layouts_keep_every_window_on_negative_origin_monitor_without_overlap(layout):
    bounds = MONITORS[1].work
    rects = tile_rects(bounds, 5, layout, gap=7, margin=13)
    assert len(rects) == 5
    for rect in rects:
        assert rect[0] >= bounds[0] + 13 and rect[1] >= bounds[1] + 13
        assert rect[0] + rect[2] <= bounds[0] + bounds[2] - 13
        assert rect[1] + rect[3] <= bounds[1] + bounds[3] - 13
        assert all(overlap(rect, other) == 0 for other in rects if other is not rect)


def test_grid_covers_odd_pixel_dimensions_and_expands_instead_of_dropping_clients():
    rects = tile_rects((0, 0, 1001, 703), 4, "grid", gap=3, margin=0, columns=2, rows=2)
    assert rects == [[0, 0, 499, 350], [502, 0, 499, 350], [0, 353, 499, 350], [502, 353, 499, 350]]
    assert len(tile_rects((0, 0, 1920, 1080), 7, "2x2")) == 7
    with pytest.raises(ValueError, match="Zu viele Fenster"):
        tile_rects((0, 0, 1280, 720), 32, "horizontal")


def test_multiple_monitor_distribution_preserves_profile_order_and_taskbar():
    entries = [{"name": str(i)} for i in range(5)]
    plans = arrange(MONITORS, entries, {"monitor": "all", "layout": "auto", "gap": 0, "margin": 0})
    assert [p["entry"] for p in plans] == entries
    assert [p["rect"][0] < 0 for p in plans] == [False, True, False, True, False]
    assert all(p["rect"][1] + p["rect"][3] <= 1040 for p in plans if p["rect"][0] >= 0)
    assert arrange(
        MONITORS, entries[:1], {"monitor": "missing", "layout": "fill", "work_area": False, "margin": 0}
    )[0]["rect"] == [0, 0, 1920, 1080]


def test_aspect_cascade_and_disconnected_monitor_recovery():
    for rect in tile_rects((0, 0, 1920, 1040), 3, "auto", aspect="16:9"):
        assert abs(rect[2] / rect[3] - 16 / 9) < 0.01
    assert len(tile_rects((0, 0, 1920, 1040), 32, "cascade")) == 32
    assert recover_rect([-1200, 0, 960, 540], MONITORS) == [-1200, 0, 960, 540]
    assert recover_rect([-1200, 0, 960, 540], MONITORS[:1]) == [0, 0, 960, 540]


class FakeWindows:
    def __init__(self):
        self.instances = [{"pid": i + 10, "created": float(i), "hwnd": i + 100} for i in range(3)]
        self.states = {
            i["hwnd"]: {"style": 0x16C80000, "exstyle": 0, "rect": [20, 40, 800, 600], "topmost": False}
            for i in self.instances
        }
        self.calls, self.fail = [], None
        self.before_apply = lambda: None

    def valid(self, instance):
        return instance in self.instances

    def monitors(self):
        return MONITORS

    def snapshot(self, hwnd):
        return copy.deepcopy(self.states[hwnd])

    def apply(self, hwnd, rect, mode, topmost, size_kind, original_style):
        self.before_apply()
        self.calls.append((hwnd, rect, mode, topmost, size_kind, original_style))
        self.states[hwnd]["rect"] = list(rect)
        if hwnd == self.fail:
            raise OSError("simulated SetWindowPos failure after style change")

    def restore(self, hwnd, state):
        self.states[hwnd] = copy.deepcopy(state)

    def show(self, hwnd, action):
        self.before_apply()
        self.states[hwnd]["show"] = action


@pytest.fixture
def windows(profile):
    _, store, _ = profile
    api = FakeWindows()
    return WindowManager(store, api), api, store


def plan(instance, rect=None):
    return {
        "entry": {"instance": instance},
        "rect": rect or [100, 100, 640, 360],
        "mode": "borderless",
        "topmost": None,
        "size_kind": "outer",
    }


def test_recovery_is_committed_before_changes_and_survives_manager_restart(windows):
    manager, api, store = windows
    original = api.snapshot(100)
    api.before_apply = lambda: (
        store.get("window_originals")[identity(api.instances[0])] or pytest.fail("missing recovery state")
    )
    assert manager.apply([plan(api.instances[0])]) == 1
    assert api.states[100]["rect"] == [100, 100, 640, 360]
    reopened = WindowManager(store, api)
    assert reopened.restore(undo=True) == 1
    assert api.states[100] == original
    manager.apply([plan(api.instances[0], [200, 200, 900, 500])])
    assert reopened.restore() == 1
    assert api.states[100] == original


def test_failed_batch_rolls_back_already_changed_and_partially_failed_windows(windows):
    manager, api, store = windows
    original = copy.deepcopy(api.states)
    api.fail = 101
    with pytest.raises(OSError):
        manager.apply([plan(i) for i in api.instances])
    assert api.states == original
    assert len(api.calls) == 2


def test_pid_and_handle_reuse_are_rejected_before_mutation_and_during_restore(windows):
    manager, api, store = windows
    original_instance = copy.deepcopy(api.instances[0])
    manager.apply([plan(original_instance)])
    api.instances[0]["created"] = 99
    assert manager.restore(undo=True) == 0
    with pytest.raises(ValueError, match="nicht mehr verfügbar"):
        manager.apply([plan(original_instance)])
    assert len(api.calls) == 1


def test_old_settings_and_position_lists_are_preserved_and_recovered(windows):
    manager, api, store = windows
    store.set("borderless", True)
    assert get(store, "window_mode") == "borderless"
    set_value(store, "borderless", False)
    assert get(store, "window_mode") == "windowed"
    instance = {**api.instances[0], "account_id": "account-one"}
    # API identity ignores extra launcher metadata, as the real native API does.
    api.valid = lambda i: all(i.get(k) == api.instances[0][k] for k in ("pid", "created", "hwnd"))
    store.set("window_placements", {"account-one": [-5000, 0, 960, 540]})
    assert manager.apply_saved(instance)
    assert api.calls[0][1] == [-1240, 0, 960, 540]
    assert manager.account_for(instance) == "account-one"
    assert store.get("window_placements")["account-one"] == [-5000, 0, 960, 540]


def test_invalid_plan_is_rejected_before_any_window_is_changed(windows):
    manager, api, _ = windows
    with pytest.raises(ValueError):
        manager.apply([plan(api.instances[0]), plan(api.instances[1], [True, 0, 960, 540])])
    assert not api.calls


def test_minimize_action_is_reversible_and_requires_current_identity(windows):
    manager, api, store = windows
    original = api.snapshot(100)
    api.before_apply = lambda: store.get("window_undo")[0] or pytest.fail("missing snapshot")
    manager.show(api.instances[0], "minimize")
    assert api.states[100]["show"] == "minimize"
    assert manager.restore(undo=True) == 1
    assert api.states[100] == original
    with pytest.raises(ValueError):
        manager.show({"hwnd": 100, "pid": 999, "created": 0}, "maximize")


def test_settings_page_values_override_previous_arrangement_defaults(windows):
    from wizq.windowing import preferences

    _, _, store = windows
    store.set("window_arrangement", {"layout": "main-left", "mode": "borderless", "monitor": "left"})
    set_value(store, "window_layout", "vertical")
    set_value(store, "window_mode", "windowed")
    assert preferences(store)["layout"] == "vertical"
    assert preferences(store)["mode"] == "windowed"
    assert preferences(store)["monitor"] == "left"


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 HWND, frame, client area and DPI")
def test_native_window_frames_client_size_and_restore_without_a_game():
    env = {**os.environ, "QT_QPA_PLATFORM": "windows"}
    subprocess.run([sys.executable, "-m", "scripts.check_window_api"], env=env, timeout=45, check=True)
