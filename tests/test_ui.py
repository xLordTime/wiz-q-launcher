import pytest
from PySide6.QtWidgets import QApplication

from wizq.addon_pages import ThemeEditor
from wizq.app import Window
from wizq.themes import BUILTINS, validate_theme


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_all_pages_themes_and_help_render(app, profile, tmp_path, monkeypatch):
    paths, store, vault = profile
    store.set("check_for_updates", False)
    store.set("discord_rich_presence", False)
    store.set("performance", "eco")
    store.save_account(vault, "Merlin", "synthetic", "synthetic-password", "de")
    window = Window(paths, store, vault)
    window.heartbeat.stop()
    window.maintenance.stop()
    window.show()
    try:
        for i in range(6):
            window.navigate(i)
            app.processEvents()
            assert window.stack.currentIndex() == i
            assert not window.grab().isNull()
        assert len(BUILTINS) == 20 and len({t.id for t in BUILTINS}) == 20
        for theme in BUILTINS:
            store.set("theme", theme.id)
            window.apply_theme()
            app.processEvents()
            assert not window.grab().isNull()
        window.navigate(3)
        for i in (1, 2, 3, 0):
            window.addons_page.navigation.setCurrentRow(i)
            app.processEvents()
            assert not window.grab().isNull()
        editor = ThemeEditor(window, BUILTINS[10])
        editor.show()
        app.processEvents()
        assert not editor.grab().isNull()
        editor.reject()
        window.help_page.open_topic("Passwort")
        assert window.help_page.topics.count() > 0
        window.navigate(0)
        window.grab().save(str(tmp_path / "launch-qa.png"))
    finally:
        window.shutdown()
        window.force_quit = True
        window.close()
        app.processEvents()


def test_malformed_theme_cannot_inject_styles():
    from dataclasses import asdict

    data = asdict(BUILTINS[0])
    data["accent"] = "#ffffff; arbitrary-style"
    with pytest.raises(ValueError):
        validate_theme(data)
