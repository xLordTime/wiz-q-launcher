import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QSpinBox, QStyleOptionViewItem

from wizq.app import Window
from wizq.cloud import new_code
from wizq.desktop import Location
from wizq.selection import contrast, mix, selection_colors
from wizq.themes import BUILTINS, DESKTOP_THEMES, catalog


@pytest.fixture
def desktop(profile, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths, store, vault = profile
    for key in ("check_for_updates", "discord_rich_presence", "animations"):
        store.set(key, False)
    store.set("performance", "eco")
    # No game, network or global keyboard hooks are needed for navigation tests.
    monkeypatch.setattr(Window, "poll", lambda self: None)
    monkeypatch.setattr("wizq.app.Hotkeys", lambda *args: type("Keys", (), {"close": lambda self: None})())
    de = store.add_group("Entdecker-Team")
    us = store.add_group("US-Accounts")
    ids = [
        store.save_account(vault, name, "synthetic-user", "synthetic-password", region, group)
        for name, region, group in (("Merlin", "de", de), ("Luna", "us", de), ("Orion", "us", us))
    ]
    window = Window(paths, store, vault)
    window.heartbeat.stop()
    window.maintenance.stop()
    window.show()
    app.processEvents()
    yield window, app, de, us, ids
    window.shutdown()
    window.force_quit = True
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def visible_ids(window):
    return [item.data(0, Qt.ItemDataRole.UserRole) for item in window.launch_page.items()]


def test_path_dropdown_tree_history_and_parent_are_synchronized(desktop):
    window, app, de, us, ids = desktop
    assert window.breadcrumb.path_text == "Mein Launcher > Alle Accounts"
    group_menu = window.breadcrumb.buttons[-1].menu()
    next(a for a in group_menu.actions() if a.data() == Location(0, de)).trigger()
    app.processEvents()
    assert visible_ids(window) == ids[:2]  # This group deliberately spans DE and US.
    assert window.breadcrumb.path_text.endswith("Alle Accounts > Entdecker-Team")
    assert window.navigation_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == Location(0, de)
    window.navigation_tree.setCurrentItem(window.route_items[Location(0, us)])
    assert visible_ids(window) == ids[2:]
    window.actions["back"].trigger()
    assert window.location == Location(0, de)
    window.actions["forward"].trigger()
    assert window.location == Location(0, us)
    window.actions["up"].trigger()
    assert visible_ids(window) == ids
    window.launch_page.search.setText("Orion")
    window.launch_page.region.setCurrentIndex(window.launch_page.region.findData("us"))
    window.breadcrumb.buttons[0].click()
    assert visible_ids(window) == ids
    assert not window.launch_page.search.text()
    assert window.launch_page.region.currentData() == "all"


def test_settings_and_addon_submenus_have_clickable_parents(desktop):
    window, app, *_ = desktop
    window.go(Location(4, section="Darstellung"))
    assert window.breadcrumb.path_text.endswith("Einstellungen > Darstellung")
    menu = window.breadcrumb.buttons[-1].menu()
    next(a for a in menu.actions() if a.text() == "Updates").trigger()
    assert window.settings_page.categories.currentItem().text() == "Updates"
    window.back()
    assert window.settings_page.categories.currentItem().text() == "Darstellung"
    window.breadcrumb.buttons[-2].click()
    assert window.location == Location(4)
    assert window.breadcrumb.path_text.endswith("Einstellungen")
    window.go(Location(3, section="Theme Creator"))
    assert window.addons_page.navigation.currentRow() == 3
    window.up()
    assert window.location == Location(3)
    assert window.addons_page.navigation.currentRow() == 0
    window.up()
    assert window.location == Location()
    window.go(Location(4))
    assert not window.actions["forward"].isEnabled()


def test_cloud_page_creates_a_profile_in_the_chosen_folder(desktop, tmp_path, monkeypatch):
    window, app, *_ = desktop
    page = window.addons_page.cloud
    folder = tmp_path / "Synced folder"
    folder.mkdir()
    codes = []
    loop = QEventLoop()
    monkeypatch.setattr(page, "pick_folder", lambda: str(folder))
    monkeypatch.setattr(page, "key_dialog", lambda code: (codes.append(code), loop.quit()))
    window.go(Location(3, section="Cloud-Synchronisierung"))
    assert window.addons_page.stack.currentWidget() is page
    assert page.create_button.isEnabled()
    page.create_button.click()
    QTimer.singleShot(5000, loop, loop.quit)
    loop.exec()
    assert codes == [page.service.code()]
    assert not page.busy
    assert page.sync_button.isEnabled()
    assert page.timer.isActive()
    page.disconnect_button.click()
    app.processEvents()
    assert page.service.config() is None
    assert page.create_button.isEnabled()
    assert not page.timer.isActive()


def test_cloud_page_shows_waiting_pairing_and_allows_retry(desktop, tmp_path, monkeypatch):
    window, app, *_ = desktop
    page = window.addons_page.cloud
    folder = tmp_path / "Cloud destination"
    folder.mkdir()
    code = new_code()
    loop = QEventLoop()
    complete = page.finished

    def finished():
        complete()
        loop.quit()

    monkeypatch.setattr(page, "finished", finished)
    monkeypatch.setattr(page, "pick_folder", lambda: str(folder))
    monkeypatch.setattr("wizq.cloud_page.QInputDialog.getText", lambda *args: (code, True))
    window.go(Location(3, section="Cloud-Synchronisierung"))
    page.join_button.click()
    QTimer.singleShot(5000, loop, loop.quit)
    loop.exec()
    assert "Verknüpfung gespeichert" in page.status.text()
    assert page.sync_button.isEnabled()
    assert page.move_button.isEnabled()
    assert page.timer.isActive()
    page.disconnect_button.click()
    app.processEvents()
    assert page.join_button.isEnabled()


def test_hidden_accounts_are_remembered_but_never_launched(desktop, monkeypatch):
    window, app, de, us, ids = desktop
    launched = []
    monkeypatch.setattr(
        window, "launch_accounts", lambda accounts, region=None: launched.append((accounts, region))
    )
    window.go(Location(0, de))
    window.launch_page.accounts.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    window.go(Location(0, us))
    window.launch_page.launch_selected()
    assert not launched
    window.launch_page.select_all()
    window.launch_page.launch_selected()
    assert [a["id"] for a in launched[-1][0]] == ids[2:]
    window.back()
    assert window.launch_page.selected_ids() == ids[:1]
    assert "synthetic-user" not in window.launch_page.detail_values.text()


def test_deleted_group_falls_back_without_stale_path(desktop):
    window, app, de, *_ = desktop
    window.go(Location(0, de))
    with window.store.transaction() as db:
        db.execute("DELETE FROM groups WHERE id=?", (de,))
    window.refresh_accounts()
    assert window.location == Location()
    assert "Entdecker-Team" not in window.breadcrumb.path_text
    assert len(visible_ids(window)) == 3


def test_quicklaunch_uses_the_chosen_region_and_count(desktop, monkeypatch):
    window, app, *_ = desktop
    launched = []
    monkeypatch.setattr(
        window, "launch_accounts", lambda accounts, region=None: launched.append((accounts, region))
    )

    def choose(dialog):
        region = dialog.findChild(QComboBox)
        region.setCurrentIndex(region.findData("us"))
        dialog.findChild(QSpinBox).setValue(2)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", choose)
    window.launch_page.empty_dialog()
    assert launched == [([None, None], "us")]


def test_language_override_applies_to_accounts_and_empty_quicklaunch(desktop, monkeypatch):
    window, app, *_ = desktop
    launched = []
    monkeypatch.setattr(window, "launch_accounts", lambda *args, **kwargs: launched.append((args, kwargs)))
    language = window.launch_page.game_language
    language.setCurrentIndex(language.findData("us"))
    window.launch_page.select_all()
    window.launch_page.launch_selected()
    assert len(launched[0][0][0]) == 3
    assert launched[0][1] == {"language": "us"}

    def choose(dialog):
        region, selected_language = dialog.findChildren(QComboBox)
        region.setCurrentIndex(region.findData("de"))
        assert selected_language.currentData() == "us"
        selected_language.setCurrentIndex(selected_language.findData("fr"))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", choose)
    window.launch_page.empty_dialog()
    assert launched[-1] == (([None], "de"), {"language": "fr"})
    # Overrides are for this start; the saved region language stays untouched.
    assert window.store.get("region_language_de") is None


def test_per_region_language_has_readable_settings_and_survives_navigation(desktop):
    window, app, *_ = desktop
    control = window.settings_page.controls["region_language_de"]
    control.setCurrentIndex(control.findData("us"))
    assert window.store.get("region_language_de") == "us"
    assert "English (US)" in control.currentText()
    window.go(Location(0))
    assert window.launch_page.game_language.currentData() is None
    assert window.store.get("region_language_de") == "us"


@pytest.fixture
def window_editor(desktop):
    from types import SimpleNamespace

    from wizq.window_dialog import WindowDialog
    from wizq.windowing import Monitor

    window, app, _, _, ids = desktop
    monitors = [
        Monitor("primary", (0, 0, 1920, 1080), (0, 0, 1920, 1040), True),
        Monitor("left", (-1280, 0, 1280, 1024), (-1280, 0, 1280, 984)),
    ]
    calls = []
    window.found = [{"pid": 100 + i, "created": float(i), "hwnd": 200 + i} for i in range(3)]
    api = SimpleNamespace(
        monitors=lambda: monitors,
        valid=lambda instance: instance in window.found,
        snapshot=lambda hwnd: {"rect": [30, 40, 800, 600], "style": 0x16C80000, "topmost": False},
        apply=lambda *args: calls.append(args),
        restore=lambda *args: calls.append(args),
    )
    window.window_manager._api = api
    for instance, account_id in zip(window.found, ids):
        window.window_manager.bind(instance, account_id)
    dialog = WindowDialog(window, monitors=monitors)
    dialog.show()
    app.processEvents()
    yield dialog, window, app, calls
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_window_preview_drag_and_custom_size_do_not_change_live_windows(window_editor):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    dialog, window, app, calls = window_editor
    assert len(dialog.plans) == 3
    assert dialog.canvas.active == 0
    dialog.monitor.setCurrentIndex(dialog.monitor.findData("all"))
    before = list(dialog.plans[0]["rect"])
    point = dialog.canvas.canvas_rect(before).center().toPoint()
    QTest.mousePress(dialog.canvas, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(dialog.canvas, point + QPoint(15, 10))
    QTest.mouseRelease(dialog.canvas, Qt.MouseButton.LeftButton, pos=point + QPoint(15, 10))
    assert dialog.layout_choice.currentData() == "custom"
    assert dialog.plans[0]["rect"] != before
    dialog.width_value.setValue(960)
    dialog.height_value.setValue(540)
    dialog.custom_mode.setCurrentIndex(dialog.custom_mode.findData("borderless"))
    assert dialog.plans[0]["rect"][2:] == [960, 540]
    assert dialog.plans[0]["mode"] == "borderless"
    assert not calls
    dialog.save_defaults()
    saved = window.store.get("window_placements")
    assert saved[window.store.accounts()[0]["id"]]["rect"][2:] == [960, 540]
    assert not calls


def test_window_profiles_match_accounts_and_never_assign_missing_account_to_another_window(
    window_editor, monkeypatch
):
    from PySide6.QtWidgets import QInputDialog

    dialog, window, app, calls = window_editor
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Zwei Monitore", True))
    dialog.monitor.setCurrentIndex(dialog.monitor.findData("all"))
    expected = [p["rect"] for p in dialog.plans]
    dialog.save_profile()
    profile = window.store.get("window_profiles")["Zwei Monitore"]
    assert [p["rect"] for p in profile["windows"]] == expected
    assert "instance" not in str(profile) and "synthetic-user" not in str(profile)
    missing_account = profile["windows"][0]["account_id"]
    window.store.set("window_profiles", {"Zwei Monitore": profile})
    first = dialog.windows.takeTopLevelItem(0)
    del first
    dialog.load_profile()
    assert len(dialog.plans) == 2
    assert all(p["entry"]["account_id"] != missing_account for p in dialog.plans)
    assert [p["rect"] for p in dialog.plans] == expected[1:]
    assert "1 aktuell nicht verfügbar" in dialog.status.text()
    assert not calls


def test_window_apply_runs_the_checked_batch_and_updates_saved_controls(window_editor):
    from PySide6.QtTest import QTest

    dialog, window, app, calls = window_editor
    dialog.mode.setCurrentIndex(dialog.mode.findData("borderless"))
    dialog.layout_choice.setCurrentIndex(dialog.layout_choice.findData("main-left"))
    dialog.gap.setValue(16)
    dialog.apply_button.click()
    for _ in range(300):
        app.processEvents()
        if not dialog.busy:
            break
        QTest.qWait(10)
    assert not dialog.busy
    assert len(calls) == 3
    assert all(call[2] == "borderless" for call in calls)
    assert len(window.store.get("window_originals")) == 3
    assert window.settings_page.controls["window_mode"].currentData() == "borderless"
    assert window.settings_page.controls["window_layout"].currentData() == "main-left"
    assert window.settings_page.controls["window_gap"].value() == 16
    assert "3 Spielfenster angeordnet" in dialog.status.text()


def test_account_window_template_can_be_edited_before_launch(desktop):
    from wizq.window_dialog import WindowDialog

    window, app, *_ = desktop
    dialog = WindowDialog(window, account=window.store.accounts()[0])
    try:
        assert dialog.current_entry()["instance"] is None
        assert not dialog.apply_button.isEnabled()
        dialog.width_value.setValue(960)
        dialog.height_value.setValue(540)
        dialog.save_defaults()
        assert len(window.store.get("window_placements")) == 1
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_desktop_presets_and_small_window_render(desktop):
    window, app, *_ = desktop
    assert len(catalog(window.paths.directory("themes"))) >= 23
    for theme in DESKTOP_THEMES:
        window.store.set("theme", theme.id)
        window.apply_theme()
        window.resize(1000, 700)
        app.processEvents()
        assert window.width() <= 1000
        assert window.height() <= 700
        assert not window.grab().isNull()
        assert window.breadcrumb.buttons[0].isVisible()


def test_selection_contrast_in_all_themes_and_low_contrast_custom_themes():
    from dataclasses import replace

    for theme in [*DESKTOP_THEMES, *BUILTINS]:
        for candidate in (theme, replace(theme, accent=theme.panel)):
            colors = selection_colors(candidate)
            assert contrast(colors.background, theme.panel) >= 3
            assert contrast(colors.background, mix(theme.panel, theme.background, 0.42)) >= 3
            assert contrast(colors.background, colors.foreground) >= 4.5
            assert contrast(colors.checked_background, colors.checked_foreground) >= 4.5


def test_checkbox_and_unfocused_selection_are_rendered_in_every_theme(desktop):
    window, app, *_ = desktop
    view = window.launch_page.accounts
    first, second = view.topLevelItem(0), view.topLevelItem(1)
    for theme in [*DESKTOP_THEMES, *BUILTINS]:
        window.store.set("theme", theme.id)
        window.apply_theme()
        colors = selection_colors(theme)
        view.setCurrentItem(second)
        first.setCheckState(0, Qt.CheckState.Unchecked)
        app.processEvents()
        index = view.indexFromItem(first, 0)
        option = QStyleOptionViewItem()
        option.initFrom(view)
        option.widget = view
        option.rect = view.visualRect(index)
        box = view.itemDelegateForColumn(0).indicator_rect(option, index)
        assert not box.isEmpty()
        before = view.viewport().grab().toImage()
        first.setCheckState(0, Qt.CheckState.Checked)
        app.processEvents()
        after = view.viewport().grab().toImage()
        scale = after.devicePixelRatio()
        inner = box.adjusted(3, 3, -3, -3)
        tick_pixels = sum(
            contrast(after.pixelColor(round(x * scale), round(y * scale)), colors.background) >= 4.5
            for x in range(inner.left(), inner.right() + 1)
            for y in range(inner.top(), inner.bottom() + 1)
        )
        assert tick_pixels >= 2, theme.id
        assert before != after
        assert first.text(1) == "Ausgewählt"
        assert first.font(0).bold()
        assert window.launch_page.launch_button.text() == "1 Account starten"
        view.setCurrentItem(first)
        window.launch_page.search.setFocus()
        app.processEvents()
        # The row must remain strongly highlighted after focus moves to the search box.
        cell = view.visualRect(view.indexFromItem(first, 4))
        image = view.viewport().grab().toImage()
        actual = image.pixelColor(round((cell.right() - 8) * scale), round(cell.center().y() * scale))
        assert actual.name() == colors.background, (theme.id, actual.name(), colors.background)
        assert "Für den Start ausgewählt" in window.launch_page.detail_start.text()
        first.setCheckState(0, Qt.CheckState.Unchecked)
        assert first.text(1) == "—"
        assert not window.launch_page.launch_button.isEnabled()
