import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QSpinBox, QStyleOptionViewItem

from wizq.app import Window
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
