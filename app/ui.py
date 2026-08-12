"""UI components and theme management."""

from typing import List, Optional
from pathlib import Path
import logging
import re
import sys
import tkinter as _tk

import PySimpleGUI as sg

from core.config import APP_NAME, APP_VERSION, REGION_META
from core.i18n import LANGUAGE_OPTIONS, language_label, t
from security.crypto import Account, account_display
from services.playtime_tracker import PlaytimeTracker
from services.log_viewer import LogViewer

_WIZWALL_LAYOUTS = ["1x1", "2x1", "1x2", "2x2", "3x2", "3x3", "4x2", "4x3"]

# All selectable UI themes (displayed in Settings → UI Theme combo).
_AVAILABLE_THEMES = [
    "WizDark",      # Deep charcoal · teal accent  (default)
    "WizLight",     # Clean white · blue accent
    "Midnight",     # Navy · electric-blue accent
    "Nord",         # Slate-blue · muted-blue accent
    "Dracula",      # Deep purple-gray · lavender accent
    "Catppuccin",   # Dark mauve · pastel-blue accent
    "Monokai",      # Warm dark · vibrant-green accent
    "Emerald",      # Forest dark · bright-green accent
    "Steve-Green",  # Dark mode · neon green · apple green
    "Slate",        # Dark indigo · violet accent
    "Sunset",       # Dark maroon · warm-red accent
    "Pink",         # Bold magenta · neon pink accent
]

_THEME_COLOR_KEYS = (
    "BACKGROUND", "TEXT", "INPUT", "TEXT_INPUT", "SCROLL",
    "BUTTON_TEXT", "BUTTON_BACKGROUND", "ACCENT",
)
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_UI_TOOLTIPS_ENABLED = False


def _tip(text: str) -> Optional[str]:
    """Return a tooltip only when the user enabled tooltips."""
    return text if _UI_TOOLTIPS_ENABLED else None

# Flat PyQt6-style theme definitions shared across all themes.
# BORDER=0 + SLIDER_DEPTH=0 + PROGRESS_DEPTH=0 remove all tkinter 3-D effects.
_THEME_DEFS: dict = {
    "WizDark": {
        "BACKGROUND": "#0D1117",
        "TEXT": "#E6EDF3",
        "INPUT": "#161B22",
        "TEXT_INPUT": "#E6EDF3",
        "SCROLL": "#30363D",
        "BUTTON": ("#FFFFFF", "#238636"),   # GitHub green
        "PROGRESS": ("#238636", "#0D1117"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "WizLight": {
        "BACKGROUND": "#FFFFFF",
        "TEXT": "#24292F",
        "INPUT": "#F6F8FA",
        "TEXT_INPUT": "#24292F",
        "SCROLL": "#D0D7DE",
        "BUTTON": ("#FFFFFF", "#0969DA"),   # GitHub blue
        "PROGRESS": ("#0969DA", "#F6F8FA"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Midnight": {
        "BACKGROUND": "#0A0E1A",
        "TEXT": "#A9B1D6",
        "INPUT": "#13182A",
        "TEXT_INPUT": "#C0CAF5",
        "SCROLL": "#24283B",
        "BUTTON": ("#1A1B26", "#7AA2F7"),   # Tokyo Night blue
        "PROGRESS": ("#7AA2F7", "#0A0E1A"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Nord": {
        "BACKGROUND": "#2E3440",
        "TEXT": "#ECEFF4",
        "INPUT": "#3B4252",
        "TEXT_INPUT": "#ECEFF4",
        "SCROLL": "#434C5E",
        "BUTTON": ("#ECEFF4", "#5E81AC"),   # Nord blue
        "PROGRESS": ("#88C0D0", "#2E3440"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Dracula": {
        "BACKGROUND": "#282A36",
        "TEXT": "#F8F8F2",
        "INPUT": "#44475A",
        "TEXT_INPUT": "#F8F8F2",
        "SCROLL": "#6272A4",
        "BUTTON": ("#F8F8F2", "#BD93F9"),   # Dracula purple
        "PROGRESS": ("#BD93F9", "#282A36"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Catppuccin": {
        "BACKGROUND": "#1E1E2E",
        "TEXT": "#CDD6F4",
        "INPUT": "#313244",
        "TEXT_INPUT": "#CDD6F4",
        "SCROLL": "#45475A",
        "BUTTON": ("#1E1E2E", "#89B4FA"),   # Catppuccin blue
        "PROGRESS": ("#89B4FA", "#1E1E2E"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Monokai": {
        "BACKGROUND": "#272822",
        "TEXT": "#F8F8F2",
        "INPUT": "#3E3D32",
        "TEXT_INPUT": "#F8F8F2",
        "SCROLL": "#49483E",
        "BUTTON": ("#272822", "#A6E22E"),   # Monokai green
        "PROGRESS": ("#A6E22E", "#272822"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Emerald": {
        "BACKGROUND": "#0D1A13",
        "TEXT": "#B6F5C8",
        "INPUT": "#152A1E",
        "TEXT_INPUT": "#B6F5C8",
        "SCROLL": "#1E3A28",
        "BUTTON": ("#0D1A13", "#27AE60"),   # Forest green
        "PROGRESS": ("#27AE60", "#0D1A13"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Steve-Green": {
        "BACKGROUND": "#071A0B",
        "TEXT": "#D7FF6A",
        "INPUT": "#0D2A12",
        "TEXT_INPUT": "#E8FFD0",
        "SCROLL": "#285C20",
        "BUTTON": ("#071A0B", "#8DB600"),
        "PROGRESS": ("#39FF14", "#071A0B"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Slate": {
        "BACKGROUND": "#1A1A2E",
        "TEXT": "#E0E0FF",
        "INPUT": "#16213E",
        "TEXT_INPUT": "#E0E0FF",
        "SCROLL": "#0F3460",
        "BUTTON": ("#E0E0FF", "#533483"),   # Deep violet
        "PROGRESS": ("#533483", "#1A1A2E"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Sunset": {
        "BACKGROUND": "#1A0A0A",
        "TEXT": "#F5D0C0",
        "INPUT": "#2A1010",
        "TEXT_INPUT": "#F5D0C0",
        "SCROLL": "#3A1818",
        "BUTTON": ("#F5D0C0", "#C0392B"),   # Warm red
        "PROGRESS": ("#C0392B", "#1A0A0A"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
    "Pink": {
        "BACKGROUND": "#140813",
        "TEXT": "#FFD6F1",
        "INPUT": "#281026",
        "TEXT_INPUT": "#FFF0FA",
        "SCROLL": "#4A1744",
        "BUTTON": ("#FFFFFF", "#E91E9B"),   # Bright pink
        "PROGRESS": ("#FF4DB8", "#140813"),
        "BORDER": 0, "SLIDER_DEPTH": 0, "PROGRESS_DEPTH": 0,
    },
}


def apply_theme(config: dict) -> None:
    """
    Register all custom themes and apply the one selected in *config*.

    All themes use BORDER=0 / SLIDER_DEPTH=0 for a flat, PyQt6-style look.
    Falls back to WizDark when an unknown theme name is stored in config.
    """
    for name, definition in _THEME_DEFS.items():
        sg.theme_add_new(name, definition)

    valid_custom_names = []
    for name, definition in config.get("custom_themes", {}).items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            continue
        if all(_HEX_COLOR.fullmatch(str(definition.get(key, ""))) for key in _THEME_COLOR_KEYS):
            custom_definition = {
                "BACKGROUND": definition["BACKGROUND"],
                "TEXT": definition["TEXT"],
                "INPUT": definition["INPUT"],
                "TEXT_INPUT": definition["TEXT_INPUT"],
                "SCROLL": definition["SCROLL"],
                "BUTTON": (definition["BUTTON_TEXT"], definition["BUTTON_BACKGROUND"]),
                "PROGRESS": (definition["ACCENT"], definition["BACKGROUND"]),
                "BORDER": 0,
                "SLIDER_DEPTH": 0,
                "PROGRESS_DEPTH": 0,
            }
            sg.theme_add_new(name, custom_definition)
            valid_custom_names.append(name)

    selected = config.get("ui_theme", "WizDark")
    if selected not in _THEME_DEFS and selected not in valid_custom_names:
        selected = "WizDark"
    sg.theme(selected)


def _available_themes(config: dict) -> List[str]:
    """Return built-in themes followed by valid custom theme names."""
    custom = config.get("custom_themes", {})
    names = [name for name in custom if isinstance(name, str) and name.strip()]
    return _AVAILABLE_THEMES + [name for name in names if name not in _AVAILABLE_THEMES]


def build_theme_creator_tab(config: dict) -> List:
    """Build the Theme-Creator extension for user-defined launcher themes."""
    custom_themes = config.get("custom_themes", {})
    selected = config.get("ui_theme", "WizDark")
    selected_definition = custom_themes.get(selected, {}) if isinstance(custom_themes, dict) else {}

    def color(key: str, fallback: str) -> str:
        value = selected_definition.get(key, fallback)
        return str(value) if _HEX_COLOR.fullmatch(str(value)) else fallback

    return [
        [sg.Text("Theme-Creator", font=("Segoe UI", 12, "bold"))],
        [sg.Text("Create and save your own launcher theme. Use six-digit HEX colors.", font=("Segoe UI", 9, "italic"))],
        [sg.Text("Theme name"), sg.Input(selected if selected not in _AVAILABLE_THEMES else "", key="-TC-NAME-", size=(24, 1))],
        [sg.Text("Background", size=(18, 1)), sg.Input(color("BACKGROUND", "#0D1117"), key="-TC-BACKGROUND-", size=(12, 1))],
        [sg.Text("Text", size=(18, 1)), sg.Input(color("TEXT", "#E6EDF3"), key="-TC-TEXT-", size=(12, 1))],
        [sg.Text("Input background", size=(18, 1)), sg.Input(color("INPUT", "#161B22"), key="-TC-INPUT-", size=(12, 1))],
        [sg.Text("Input text", size=(18, 1)), sg.Input(color("TEXT_INPUT", "#E6EDF3"), key="-TC-TEXT-INPUT-", size=(12, 1))],
        [sg.Text("Scroll", size=(18, 1)), sg.Input(color("SCROLL", "#30363D"), key="-TC-SCROLL-", size=(12, 1))],
        [sg.Text("Button text", size=(18, 1)), sg.Input(color("BUTTON_TEXT", "#FFFFFF"), key="-TC-BUTTON-TEXT-", size=(12, 1))],
        [sg.Text("Button background", size=(18, 1)), sg.Input(color("BUTTON_BACKGROUND", "#238636"), key="-TC-BUTTON-BG-", size=(12, 1))],
        [sg.Text("Accent", size=(18, 1)), sg.Input(color("ACCENT", "#238636"), key="-TC-ACCENT-", size=(12, 1))],
        [sg.Button("Save Theme", key="-TC-SAVE-"), sg.Button("Apply Theme", key="-TC-APPLY-"), sg.Button("Delete Theme", key="-TC-DELETE-")],
        [sg.Text("Saved custom themes:"), sg.Combo(_available_themes(config), default_value=selected, key="-TC-SELECT-", readonly=True, enable_events=True, size=(24, 1))],
        [sg.Text("Built-in themes are not changed or deleted.", font=("Segoe UI", 9, "italic"), text_color="#9AA5B1")],
    ]


def _get_screen_height() -> int:
    """Return the primary monitor's height in pixels (no visible window created)."""
    try:
        root = _tk.Tk()
        root.withdraw()
        h = root.winfo_screenheight()
        root.destroy()
        return h
    except Exception:
        return 768  # safe fallback


def bind_mousewheel_scroll(window: sg.Window) -> None:
    """
    Enable mousewheel scrolling for every scrollable Column in *window*.

    Walks up the tkinter widget tree from the cursor position to find the
    nearest Canvas (which backs every scrollable Column) and scrolls it.
    Must be called *after* ``window.finalize()`` / ``window.read()``.
    """
    try:
        def _on_wheel(event: _tk.Event) -> None:
            widget = event.widget
            while widget is not None:
                try:
                    cls = widget.winfo_class()
                except Exception:
                    break
                if cls == "Canvas":
                    try:
                        widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    except Exception:
                        pass
                    return
                widget = getattr(widget, "master", None)

        window.TKroot.bind_all("<MouseWheel>", _on_wheel)
    except Exception:
        pass


def _find_asset(filename: str) -> Optional[Path]:
    """Find a bundled asset by filename, checking frozen and dev paths."""
    candidates = []
    # PyInstaller frozen: extracted files live in sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / filename)
        # Also check next to the .exe itself
        candidates.append(Path(sys.executable).parent / filename)
    # Dev mode: walk up from this file to find the project root
    for parent in Path(__file__).parents:
        candidates.append(parent / filename)
    for p in candidates:
        if p.exists():
            return p
    return None


def resolve_icon_path(config: dict) -> Optional[str]:
    """
    Resolve an icon path for the main window.
    Supports .ico directly, or .png with optional Pillow conversion.
    Always falls back to icon.ico from the bundled assets.
    """
    icon_path = str(config.get("app_icon_path", "")).strip()

    # Try the config-specified path first
    if icon_path:
        path = Path(icon_path)
        if not path.is_absolute():
            # Check in bundled asset locations before falling back to CWD
            asset = _find_asset(path.name)
            path = asset if asset is not None else path.resolve()
        if path.exists():
            if path.suffix.lower() == ".ico":
                return str(path)
            if path.suffix.lower() == ".png":
                return _convert_png_to_ico(path)
            logging.getLogger("ui").warning("Unsupported icon format: %s", path)

    # Fallback: always try icon.ico from bundled assets
    fallback = _find_asset("icon.ico")
    if fallback:
        return str(fallback)

    logging.getLogger("ui").warning("icon.ico not found")
    return None


def _convert_png_to_ico(path: Path) -> Optional[str]:
    """Convert a PNG to .ico using Pillow; returns the .ico path or the PNG path as fallback."""
    ico_path = path.with_suffix(".ico")
    if ico_path.exists():
        return str(ico_path)
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.save(ico_path)
        return str(ico_path)
    except Exception as exc:
        logging.getLogger("ui").warning("Failed to convert PNG icon to ICO: %s", exc)
        return str(path)


def build_launch_tab(config: dict, account_list: List[str]) -> List:
    """Build Launch tab layout."""
    current_region = config.get("current_region", "de")
    region_name = REGION_META.get(current_region, {}).get("name", current_region.upper())
    tr = lambda text: t(text, config.get("language", "en"))
    
    # Build available regions list for dropdown
    available_regions = []
    for region_code in REGION_META:
        if config.get(f"show_region_{region_code}", False):
            region_display = f"{region_code.upper()} - {REGION_META[region_code]['name']}"
            available_regions.append((region_display, region_code))
    
    # Get default value for dropdown
    default_region = f"{current_region.upper()} - {region_name}"
    
    return [
        [sg.Text(f"🌍 Current Region: {region_name.upper()}", font=("Segoe UI", 12, "bold"), text_color="#2C6E73")],
        [
            sg.Text(tr("Switch Region:")),
            sg.Combo(
                values=[r[0] for r in available_regions],
                default_value=default_region,
                key="-REGION-SELECT-",
                readonly=True,
                enable_events=True,
                size=(35, 1),
                expand_x=True,
            ),
            sg.Button(tr("Apply Region"), key="-APPLY-REGION-", tooltip=_tip("Switch the active Wizard101 region")),
        ],
        [
            sg.Button("🚀 Quicklaunch (1 Instance)", key="Quicklaunch", tooltip=_tip("Start one Wizard101 instance without logging in")),
            sg.Button("🎮 Start Selected Instances", key="Start Instances", tooltip=_tip("Start one instance for every selected account")),
            sg.Button("🔐 Start Selected + Auto Login", key="Start + Auto Login", tooltip=_tip("Start selected instances and log in automatically")),
        ],
        [
            sg.Text(tr("Select accounts to launch (Ctrl+Click for multiple):")),
            sg.Text("0 selected", key="-SELECTED-COUNT-", font=("Segoe UI", 9, "bold"), text_color="#2C6E73")
        ],
        [
            sg.Input("", key="-ACCOUNT-SEARCH-", expand_x=True, enable_events=True,
                     tooltip=_tip("Filter accounts by name or username")),
            sg.Button("Select All", key="-SELECT-ALL-", tooltip=_tip("Select all accounts currently shown")),
            sg.Button("Clear Selection", key="-CLEAR-SELECTION-", tooltip=_tip("Clear the current account selection")),
        ],
        [
            sg.Listbox(
                values=account_list,
                select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE,
                key="-AUTO-ACCOUNTS-",
                size=(55, 10),
                enable_events=True,  # Enable events to update counter
                expand_x=True,
                expand_y=True,
            )
        ],
        [
            sg.Checkbox(
                tr("Bring window to front"),
                default=config.get("foreground_on_login", True),
                key="-FOREGROUND-",
            ),
            sg.Checkbox(
                tr("Set window title"),
                default=config.get("set_window_title", True),
                key="-SETTITLE-",
            ),
        ],
    ]


def build_region_tab(config: dict, region_code: str) -> List:
    """Build per-region settings tab."""
    region_info = REGION_META.get(region_code, {})
    region_name = region_info.get("name", region_code.upper())
    
    return [
        [sg.Text(f"Settings for {region_name}", font=("Segoe UI", 11, "bold"))],
        [
            sg.Text("Install path:"),
            sg.Input(
                config.get(f"region_install_{region_code}", ""),
                key=f"-INSTALL-{region_code.upper()}-",
                size=(40, 1)
            ),
            sg.FolderBrowse(key=f"-BROWSE-{region_code.upper()}-"),
            sg.Button("🔍 Auto-Detect", key=f"-AUTO-DETECT-{region_code.upper()}-",
                      tooltip=_tip("Scan common install directories and registry for Wizard101")),
        ],
        [
            sg.Text("Login Server:"),
            sg.Input(
                config.get(f"region_server_{region_code}", region_info.get("server", "")),
                key=f"-SERVER-{region_code.upper()}-",
                size=(40, 1)
            ),
        ],
        [
            sg.Text("Port:"),
            sg.Input(
                str(config.get(f"region_port_{region_code}", 12000)),
                key=f"-PORT-{region_code.upper()}-",
                size=(10, 1)
            ),
        ],
        [sg.Button(f"🎮 Set as Current ({region_name})", key=f"-SET-REGION-{region_code.upper()}-")],
        [sg.Button(f"↺ Reset {region_name} to Default", key=f"-RESET-{region_code.upper()}-", button_color=("#E6E6E6", "#8B0000"))],
    ]


def build_accounts_tab(account_list: List[str]) -> List:
    """Build Accounts tab layout."""
    return [
        [sg.Text("Account Manager", font=("Segoe UI", 13, "bold"))],
        [sg.Text(
            f"{len(account_list)} account(s) in the current region. Select an account to edit, reorder, or remove it.",
            font=("Segoe UI", 9),
            text_color="#87909A",
        )],
        [
            sg.Listbox(
                values=account_list,
                key="-ACCOUNTS-",
                size=(62, 14),
                enable_events=True,
                expand_x=True,
                expand_y=True,
            )
        ],
        [
            sg.Button("Add Account", key="Add", button_color=("white", "#238636"), tooltip=_tip("Create a new encrypted account entry")),
            sg.Button("Edit Account", key="Edit", tooltip=_tip("Edit the selected account")),
            sg.Button("Delete Account", key="Delete", button_color=("white", "#8B0000"), tooltip=_tip("Delete the selected account")),
            sg.Push(),
             sg.Button("↑", key="-ACCT-UP-", tooltip=_tip("Move selected account up")),
             sg.Button("↓", key="-ACCT-DOWN-", tooltip=_tip("Move selected account down")),
        ],
    ]


def build_settings_tab(config: dict) -> List:
    """
    Build Settings tab with global configuration options.
    Includes logging, themes, and region visibility settings.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List layout for settings tab
    """
    backup_scope = str(config.get("backup_scope", "full"))
    if backup_scope not in ("config", "config_data", "full"):
        backup_scope = "full"
    restore_scope = str(config.get("backup_restore_scope", "full"))
    if restore_scope not in ("config", "config_data", "full"):
        restore_scope = "full"

    backup_scope_options = [
        "config",
        "config_data",
        "full",
    ]
    language = config.get("language", "en")
    tr = lambda text: t(text, language)

    return [
        [sg.Text(tr("Global Settings"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(tr("Find setting/key")),
            sg.Input("", key="-SETTINGS-SEARCH-", size=(28, 1)),
            sg.Button(tr("Search"), key="-SETTINGS-SEARCH-BTN-", tooltip=_tip("Search settings by label, config key, or UI key")),
            sg.Button(tr("Clear"), key="-SETTINGS-SEARCH-CLEAR-", tooltip=_tip("Clear the settings search")),
        ],
        [
            sg.Text(
                tr("Search by label, config key, or UI key."),
                key="-SETTINGS-SEARCH-STATUS-",
                font=("Segoe UI", 9),
                text_color="#9AA5B1",
            )
        ],
        [
            sg.Text(tr("Login wait seconds")),
            sg.Input(str(config.get("login_wait_seconds", 5)), key="-WAIT-", size=(10, 1)),
        ],
        [
            sg.Text(tr("Window title template")),
            sg.Input(
                config.get("window_title_template", "{name} ({username})"),
                key="-TITLE-",
                expand_x=True,
            ),
        ],
        [
            sg.Text(tr("Log level")),
            sg.Combo(
                ["DEBUG", "INFO", "WARNING", "ERROR"],
                default_value=config.get("log_level", "INFO"),
                key="-LOGLEVEL-",
                readonly=True,
            ),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("UI"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(tr("Theme")),
            sg.Combo(
                _available_themes(config),
                default_value=config.get("ui_theme", "WizDark"),
                key="-THEME-",
                readonly=True,
                enable_events=True,
                size=(16, 1),
            ),
            sg.Checkbox(
                tr("Remember window position"),
                default=config.get("save_window_state", False),
                key="-SAVE-WINDOW-STATE-",
            ),
            sg.Checkbox(
                "Enable tooltips",
                default=config.get("tooltips_enabled", False),
                key="-TOOLTIPS-",
                tooltip=_tip("Show explanations when hovering over buttons and controls"),
            ),
        ],
        [
            sg.Text(tr("Language")),
            sg.Combo(
                LANGUAGE_OPTIONS,
                default_value=language_label(language),
                key="-LANGUAGE-",
                readonly=True,
                enable_events=True,
                size=(16, 1),
            ),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Discord Rich Presence"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Checkbox(
                tr("Enable Discord Rich Presence"),
                default=config.get("discord_rich_presence", True),
                key="-DISCORD-RPC-",
            ),
        ],
        [
            sg.Text(tr("RPC update interval (sec)")),
            sg.Input(
                str(config.get("discord_rpc_update_interval", 15)),
                key="-DISCORD-RPC-INTERVAL-",
                size=(10, 1),
            ),
        ],
        [
            sg.Checkbox(
                "Yield presence to game (let Discord show 'Playing Wizard101' while game is running)",
                default=config.get("discord_rpc_yield_to_game", True),
                key="-DISCORD-RPC-YIELD-",
            ),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Discord Webhook Notifications"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(tr("Webhook URL")),
            sg.Input(
                config.get("discord_webhook_url", ""),
                key="-DISCORD-WEBHOOK-URL-",
                size=(44, 1),
                password_char="",
                tooltip=_tip("Paste your Discord webhook URL here"),
                expand_x=True,
            ),
        ],
        [
            sg.Checkbox(
                tr("Enable webhook notifications"),
                default=config.get("discord_notifications", False),
                key="-DISCORD-NOTIFY-",
            ),
            sg.Button(tr("Test"), key="-DISCORD-WEBHOOK-TEST-", size=(6, 1)),
        ],
        [
            sg.Checkbox(
                tr("Session start"),
                default=config.get("discord_session_start", True),
                key="-DISCORD-NOTIFY-START-",
            ),
            sg.Checkbox(
                tr("Session end"),
                default=config.get("discord_session_end", True),
                key="-DISCORD-NOTIFY-END-",
            ),
            sg.Checkbox(
                tr("Errors"),
                default=config.get("discord_errors", False),
                key="-DISCORD-NOTIFY-ERRORS-",
            ),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Update Checker"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Button(tr("Check for Updates"), key="-CHECK-UPDATES-", tooltip=_tip("Check GitHub for a newer launcher version")),
            sg.Button(tr("⬇ Download Update"), key="-DOWNLOAD-UPDATE-", disabled=True, tooltip=_tip("Download the available launcher update")),
        ],
        [
            sg.Text(
                "No update check run yet.",
                key="-UPDATE-STATUS-",
                size=(70, 2),
                text_color="#87CEEB",
            )
        ],
        [
            sg.Checkbox(
                "Automatically check for updates on startup",
                default=config.get("check_for_updates", True),
                key="-CHECK-FOR-UPDATES-",
            ),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Storage Migration"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(
                "Migration status: checking...",
                key="-MIGRATION-STATUS-",
                size=(70, 1),
                text_color="#87CEEB",
            )
        ],
        [
            sg.Text(
                str(config.get("migration_last_detail", "No migration check run yet.")),
                key="-MIGRATION-DETAIL-",
                size=(70, 2),
                text_color="#9AA5B1",
            )
        ],
        [
            sg.Button(tr("Migration Dry-Run"), key="-MIGRATION-DRYRUN-", tooltip=_tip("Preview legacy profile files that would be migrated")),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Tab Visibility"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Checkbox(tr("Show Tools tab"), default=config.get("show_tools_tab", False), key="-SHOW-TOOLS-TAB-"),
            sg.Checkbox(tr("Show Extensions tab"), default=config.get("show_extensions_tab", False), key="-SHOW-EXTENSIONS-TAB-"),
            sg.Checkbox(tr("Show Performance tab"), default=config.get("show_performance_tab", False), key="-SHOW-PERFORMANCE-TAB-"),
        ],
        [
            sg.Checkbox(tr("Show Wizwall extension"), default=config.get("show_extension_wizwall", True), key="-SHOW-EXT-WIZWALL-"),
            sg.Checkbox(tr("Show Clip & Record extension"), default=config.get("show_extension_capture", True), key="-SHOW-EXT-CAPTURE-"),
            sg.Checkbox("Show Theme-Creator extension", default=config.get("show_extension_theme_creator", True), key="-SHOW-EXT-THEME-CREATOR-"),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Issue Reporter"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(tr("Title")),
            sg.Input("", key="-ISSUE-TITLE-", size=(48, 1)),
        ],
        [
            sg.Text(tr("Context")),
            sg.Multiline(default_text="", key="-ISSUE-CONTEXT-", size=(58, 5)),
        ],
        [sg.Button(tr("Report Problem"), key="-REPORT-ISSUE-")],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Region Visibility"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Checkbox("Deutschland (DE)", default=config.get("show_region_de", True), key="-SHOW-DE-", enable_events=True),
            sg.Checkbox(tr("United States (US)"), default=config.get("show_region_us", True), key="-SHOW-US-", enable_events=True),
        ],
        [
            sg.Checkbox("France (FR)", default=config.get("show_region_fr", False), key="-SHOW-FR-", enable_events=True),
            sg.Checkbox("Italia (IT)", default=config.get("show_region_it", False), key="-SHOW-IT-", enable_events=True),
        ],
        [
            sg.Checkbox("United Kingdom (GB)", default=config.get("show_region_gb", False), key="-SHOW-GB-", enable_events=True),
            sg.Checkbox("Polska (PL)", default=config.get("show_region_pl", False), key="-SHOW-PL-", enable_events=True),
        ],
        [
            sg.Checkbox("Espana (ES)", default=config.get("show_region_es", False), key="-SHOW-ES-", enable_events=True),
            sg.Checkbox("Ellada (GR)", default=config.get("show_region_gr", False), key="-SHOW-GR-", enable_events=True),
        ],
        [sg.Button(tr("Save settings"), key="Save settings", tooltip=_tip("Save all settings changes"))],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Playtime Tracking"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Checkbox(tr("Track playtime automatically"), default=config.get("auto_playtime_tracking", True), key="-AUTO-PLAYTIME-"),
            sg.Checkbox(tr("Track even without auto-login"), default=config.get("track_without_autologin", False), key="-TRACK-WITHOUT-LOGIN-"),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text(tr("Launch Options"), font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(tr("Extra launch arguments")),
            sg.Input(
                " ".join(str(a) for a in config.get("extra_args", [])),
                key="-EXTRA-ARGS-",
                size=(36, 1),
                tooltip=_tip("Space-separated, e.g. -nosound -window"),
            ),
        ],
        [sg.HorizontalSeparator()],
        [sg.Text("Backup & Restore", font=("Segoe UI", 11, "bold"))],
        [
            sg.Text("Backup content", size=(16, 1)),
            sg.Combo(
                backup_scope_options,
                default_value=backup_scope,
                key="-BACKUP-SCOPE-",
                readonly=True,
                size=(16, 1),
            ),
            sg.Button("Create Backup", key="-BACKUP-CREATE-", tooltip=_tip("Create a backup of the selected profile data")),
            sg.Button("Open Backup Folder", key="-BACKUP-OPEN-FOLDER-", tooltip=_tip("Open the folder containing profile backups")),
        ],
        [
            sg.Text("Restore file", size=(12, 1)),
            sg.Input("", key="-BACKUP-RESTORE-FILE-", size=(42, 1)),
            sg.FileBrowse(
                "Browse",
                target="-BACKUP-RESTORE-FILE-",
                file_types=(("WizQ Backups", "*.wizqbackup.zip"), ("ZIP", "*.zip"), ("All Files", "*.*")),
            ),
            sg.Button("Restore Backup", key="-BACKUP-RESTORE-", tooltip=_tip("Restore profile data from the selected backup file")),
        ],
        [
            sg.Text("Restore scope", size=(16, 1)),
            sg.Combo(
                backup_scope_options,
                default_value=restore_scope,
                key="-BACKUP-RESTORE-SCOPE-",
                readonly=True,
                size=(16, 1),
            ),
        ],
        [
            sg.Text(
                "Modes: config | config_data | full (includes logs).",
                font=("Segoe UI", 9),
                text_color="#9AA5B1",
            )
        ],
        [sg.HorizontalSeparator()],
        [sg.Text("Security", font=("Segoe UI", 11, "bold"))],
        [
            sg.Text(
                "Control how account unlock works at startup.",
                font=("Segoe UI", 9, "italic"),
                text_color="#9AA5B1",
            )
        ],
        [
            sg.Checkbox(
                "Require master password on startup",
                default=config.get("master_password_enabled", True),
                key="-MASTER-PW-ENABLED-",
            ),
        ],
        [
            sg.Text(
                "Status: checking...",
                key="-MASTER-PW-STATUS-",
                font=("Segoe UI", 9, "bold"),
                text_color="#87CEEB",
            )
        ],
        [sg.HorizontalSeparator()],
        [sg.Text("Temporary Unlock", font=("Segoe UI", 10, "bold"))],
        [
            sg.Text("Remember unlock for", size=(16, 1)),
            sg.Input(
                str(config.get("master_password_suspend_days", 7)),
                key="-MASTER-PW-DAYS-",
                size=(6, 1),
            ),
            sg.Text("day(s)", size=(8, 1)),
            sg.Button("Suspend Password", key="-MASTER-PW-SUSPEND-"),
            sg.Button("Lock Now", key="-MASTER-PW-LOCK-NOW-"),
        ],
        [
            sg.Text(
                "Uses Windows local protection and expires automatically.",
                font=("Segoe UI", 9),
                text_color="#9AA5B1",
            )
        ],
        [sg.HorizontalSeparator()],
        [sg.Text("Password Management", font=("Segoe UI", 10, "bold"))],
        [
            sg.Button(
                "Change Master Password",
                key="-CHANGE-PASSWORD-",
                button_color=("white", "#8B0000"),
            )
        ],
    ]


def build_performance_tab(enable_perf: bool = True) -> List:
    """Build Performance tab with live system metrics."""
    return [
        [sg.Text("Performance Monitor", font=("Segoe UI", 12, "bold"))],
        [
            sg.Checkbox(
                "Enable Performance Monitoring",
                default=enable_perf,
                key="-ENABLE-PERF-MONITOR-",
                enable_events=True,
                tooltip=_tip("Toggle live CPU/RAM/Wizard memory polling on or off"),
            )
        ],
        [sg.Text("Live metrics refresh automatically while app is running.", font=("Segoe UI", 9, "italic"))],
        [sg.HorizontalSeparator()],
        [sg.HorizontalSeparator()],
        [
            sg.Text("CPU Usage:"),
            sg.Text("0.0%", key="-PERF-CPU-", size=(10, 1), text_color="#E6E6E6"),
            sg.Text("RAM Usage:"),
            sg.Text("0.0%", key="-PERF-RAM-", size=(10, 1), text_color="#E6E6E6"),
            sg.Text("Wizard Memory:"),
            sg.Text("0.0 MB", key="-PERF-WIZMEM-", size=(12, 1), text_color="#E6E6E6"),
        ],
        [
            sg.Text("Avg CPU (last 10):"),
            sg.Text("0.0%", key="-PERF-AVG-CPU-", size=(10, 1), text_color="#87CEEB"),
            sg.Text("Peak CPU:"),
            sg.Text("0.0%", key="-PERF-PEAK-CPU-", size=(10, 1), text_color="#87CEEB"),
            sg.Text("Peak Wizard Mem:"),
            sg.Text("0.0 MB", key="-PERF-PEAK-WIZMEM-", size=(12, 1), text_color="#87CEEB"),
        ],
        [
            sg.Button("Refresh Metrics", key="-PERF-REFRESH-"),
            sg.Button("Clear History", key="-PERF-CLEAR-HISTORY-"),
        ],
        [
            sg.Multiline(
                default_text="No snapshots yet.",
                key="-PERF-HISTORY-",
                size=(75, 14),
                disabled=True,
                background_color="#1A1F20",
                text_color="#E6E6E6",
                font=("Courier", 9),
            )
        ],
    ]



def build_regions_tab(config: dict) -> List:
    """Build Regions tab with sub-tabs for each active region."""
    region_subtabs = []
    
    for region_code in REGION_META:
        if config.get(f"show_region_{region_code}", False):
            region_subtabs.append(
                sg.Tab(
                    f"{region_code.upper()} - {REGION_META[region_code]['name']}",
                    build_region_tab(config, region_code),
                    key=f"-TAB-REGION-{region_code.upper()}-"
                )
            )
    
    # If no regions are enabled, show a message
    if not region_subtabs:
        return [
            [sg.Text("No regions enabled.", font=("Segoe UI", 11, "bold"))],
            [sg.Text("Go to Settings tab to enable regions.")],
        ]
    
    return [
        [
            sg.TabGroup(
                [region_subtabs],
                key="-REGIONS-TABGROUP-"
            )
        ]
    ]


def build_logs_tab(log_viewer: Optional[LogViewer] = None) -> List:
    """
    Build Logs tab with live log viewer.
    
    Args:
        log_viewer: LogViewer instance for reading log files
        
    Returns:
        List layout for logs tab
    """
    if log_viewer:
        # Live log viewer with search and filtering
        return [
            [sg.Text("Live Log Viewer", font=("Segoe UI", 11, "bold"))],
            [
                sg.Text("Search:"),
                sg.Input(key="-LOG-SEARCH-", size=(30, 1)),
                sg.Button("Search", key="-LOG-SEARCH-BTN-"),
                sg.Button("Clear", key="-LOG-CLEAR-BTN-"),
            ],
            [
                sg.Text("Filter by level:"),
                sg.Combo(["All", "DEBUG", "INFO", "WARNING", "ERROR"],
                        default_value="All",
                        key="-LOG-LEVEL-",
                        readonly=True,
                        enable_events=True,
                        size=(15, 1)),
                sg.Button("Last 15 min", key="-LOG-LAST15-"),
                sg.Button("Copy", key="-LOG-COPY-"),
            ],
            [
                sg.Multiline(
                    size=(75, 20),
                    key="-LOG-OUTPUT-",
                    disabled=True,
                    background_color="#1A1F20",
                    text_color="#E6E6E6",
                    font=("Courier", 9),
                    no_scrollbar=False,
                )
            ],
            [
                sg.Text(f"Log file: logs/launcher.log", font=("Segoe UI", 9)),
                sg.Button("Open log folder"),
                sg.Button("Refresh Logs", key="-LOG-REFRESH-"),
                sg.Button("Export Log", key="-LOG-EXPORT-"),
            ],
        ]
    else:
        # Fallback if LogViewer not available
        return [
            [sg.Text("Log file")],
            [sg.Text("logs/launcher.log")],
            [sg.Button("Open log folder")],
        ]


def build_wizwall_tab(config: dict) -> List:
    """
    Build the Wizwall sub-tab layout.

    Uses wizwalker.utils.get_all_wizard_handles() for window discovery — no
    game hooks are activated.  Layout / padding / borderless settings are
    persisted in *config*.
    """
    default_layout    = config.get("wizwall_layout", "2x2")
    default_padding   = config.get("wizwall_padding", 4)
    default_borderless = config.get("wizwall_borderless", True)

    return [
        [sg.Text("Wizwall — Window Tiling", font=("Segoe UI", 11, "bold"))],
        [sg.Text(
            "Arranges running Wizard101 windows in a grid on your primary monitor.\n"
            "Window discovery uses wizwalker.utils — no game hooks are activated.",
            font=("Segoe UI", 8, "italic"),
            text_color="#AAAAAA",
        )],
        [sg.HorizontalSeparator()],

        # ── Layout settings ──────────────────────────────────────────────────
        [
            sg.Text("Grid Layout:", size=(12, 1)),
            sg.Combo(
                _WIZWALL_LAYOUTS,
                default_value=default_layout,
                key="-WW-LAYOUT-",
                readonly=True,
                size=(8, 1),
                enable_events=True,
            ),
            sg.Text("  Padding (px):", size=(12, 1)),
            sg.Input(str(default_padding), key="-WW-PADDING-", size=(5, 1)),
            sg.Checkbox(
                "Borderless",
                default=default_borderless,
                key="-WW-BORDERLESS-",
                tooltip=_tip("Remove title-bar and borders for seamless tiling"),
            ),
        ],

        [sg.HorizontalSeparator()],

        # ── Action buttons ───────────────────────────────────────────────────
        [
            sg.Button("Scan Windows",    key="-WW-SCAN-",    size=(14, 1), tooltip=_tip("Find all currently open Wizard101 windows")),
            sg.Button("Arrange Grid",    key="-WW-ARRANGE-", size=(14, 1), button_color=("white", "#1A6B2E"), tooltip=_tip("Arrange scanned windows using the selected grid")),
            sg.Button("Save Positions",  key="-WW-SAVE-",    size=(14, 1), tooltip=_tip("Save the current window positions")),
            sg.Button("Restore",         key="-WW-RESTORE-", size=(14, 1), tooltip=_tip("Restore the last saved window positions")),
        ],

        [sg.HorizontalSeparator()],

        # ── Window list ──────────────────────────────────────────────────────
        [sg.Text("Active Wizard101 Windows", font=("Segoe UI", 9, "bold"))],
        [
            sg.Multiline(
                "",
                key="-WW-WINDOWS-",
                size=(70, 6),
                disabled=True,
                background_color="#1A1F20",
                text_color="#E6E6E6",
                font=("Courier New", 9),
                no_scrollbar=False,
            )
        ],

        # ── Output log ───────────────────────────────────────────────────────
        [sg.Text("Output", font=("Segoe UI", 9, "bold"))],
        [
            sg.Multiline(
                "",
                key="-WW-OUTPUT-",
                size=(70, 5),
                disabled=True,
                background_color="#111518",
                text_color="#B8FFB8",
                font=("Courier New", 9),
                no_scrollbar=False,
            )
        ],

        [sg.HorizontalSeparator()],
        [sg.Text(
            "Tip: click 'Scan' first, then 'Arrange Grid'.  "
            "'Save Positions' snapshots current geometry; 'Restore' brings windows back.",
            font=("Segoe UI", 8, "italic"),
            text_color="#888888",
        )],
    ]


def build_extensions_tab(config: dict) -> List:
    """Build Extensions tab containing extension sub-tabs."""
    extension_tabs = []
    if config.get("show_extension_wizwall", True):
        extension_tabs.append(sg.Tab("Wizwall", build_wizwall_tab(config), key="-TAB-WIZWALL-"))
    if config.get("show_extension_capture", True):
        extension_tabs.append(sg.Tab("Clip & Record", build_capture_tab(config), key="-TAB-CAPTURE-"))
    if config.get("show_extension_theme_creator", True):
        extension_tabs.append(sg.Tab("Theme-Creator", build_theme_creator_tab(config), key="-TAB-THEME-CREATOR-"))

    if not extension_tabs:
        return [
            [sg.Text("No extensions enabled.", font=("Segoe UI", 11, "bold"))],
            [sg.Text("Enable at least one extension in Settings to show this tab.")],
        ]

    return [
        [
            sg.TabGroup(
                [extension_tabs],
                key="-EXTENSIONS-TABGROUP-",
            )
        ]
    ]


def build_capture_tab(config: dict) -> List:
    """Build the Clip & Record extension tab layout."""
    from extensions import window_capture as _wc
    cv2_status = "✅ opencv-python installed — MP4 output enabled" if _wc.CV2_AVAILABLE else (
        "⚠ opencv-python not found — PNG frame sequence fallback\n"
        "  Install with:  pip install opencv-python"
    )
    pil_status = "✅ Pillow installed" if _wc.PIL_AVAILABLE else (
        "❌ Pillow not found — capture disabled  (pip install Pillow)"
    )

    return [
        [sg.Text("Clip & Record", font=("Segoe UI", 12, "bold"))],
        [sg.Text(f"{pil_status}    {cv2_status}", font=("Segoe UI", 8), text_color="#888888")],
        [sg.HorizontalSeparator()],

        # Window list
        [sg.Text("Active Wizard101 Windows:", font=("Segoe UI", 10, "bold"))],
        [
            sg.Listbox(
                values=[],
                key="-CAP-WINDOWS-",
                size=(50, 5),
                select_mode=sg.SELECT_MODE_SINGLE,
                enable_events=True,
            ),
            sg.Column([
                [sg.Button("🔍 Scan Windows", key="-CAP-SCAN-", size=(16, 1), tooltip=_tip("Find available Wizard101 windows for capture"))],
                [sg.Button("📸 Screenshot All", key="-CAP-SCREENSHOT-ALL-", size=(16, 1), tooltip=_tip("Capture a screenshot from every scanned window"))],
                [sg.Button("📸 Screenshot", key="-CAP-SCREENSHOT-", size=(16, 1), tooltip=_tip("Capture the selected Wizard101 window"))],
            ]),
        ],

        [sg.HorizontalSeparator()],

        # Recording controls
        [sg.Text("Recording:", font=("Segoe UI", 10, "bold"))],
        [
            sg.Button("⏺ Start Recording", key="-CAP-REC-START-", size=(18, 1), tooltip=_tip("Start recording the selected window")),
            sg.Button("⏹ Stop Recording", key="-CAP-REC-STOP-", size=(18, 1), disabled=True, tooltip=_tip("Stop the current recording and save it")),
            sg.Button("💾 Save Clip", key="-CAP-CLIP-SAVE-", size=(14, 1),
                      tooltip=_tip(f"Save last {config.get('clip_buffer_seconds', 30)}s from buffer")),
        ],
        [sg.Text("", key="-CAP-REC-STATUS-", size=(60, 1), font=("Segoe UI", 9))],

        [sg.HorizontalSeparator()],

        # Settings
        [sg.Text("Settings:", font=("Segoe UI", 10, "bold"))],
        [
            sg.Text("Output folder:", size=(14, 1)),
            sg.Input(
                config.get("capture_output_dir", "recordings"),
                key="-CAP-OUTPUT-DIR-",
                size=(30, 1),
            ),
            sg.FolderBrowse("Browse", target="-CAP-OUTPUT-DIR-"),
        ],
        [
            sg.Text("FPS:", size=(14, 1)),
            sg.Spin(
                values=[10, 15, 20, 24, 30],
                initial_value=config.get("capture_fps", 20),
                key="-CAP-FPS-",
                size=(5, 1),
            ),
            sg.Text("Clip buffer (s):", size=(14, 1)),
            sg.Spin(
                values=list(range(10, 121, 10)),
                initial_value=config.get("clip_buffer_seconds", 30),
                key="-CAP-CLIP-SECS-",
                size=(5, 1),
            ),
        ],
        [sg.Button("💾 Save Settings", key="-CAP-SAVE-SETTINGS-", size=(16, 1))],

        [sg.HorizontalSeparator()],
        [sg.Text("Output:", font=("Segoe UI", 9, "bold"))],
        [sg.Multiline(
            "",
            key="-CAP-OUTPUT-",
            size=(68, 5),
            disabled=True,
            autoscroll=True,
            font=("Consolas", 8),
        )],
    ]


def build_stats_tab(stats_list: List[dict]) -> List:
    """Build Playtime Statistics tab layout."""
    headers = ["Account", "Total Playtime", "Sessions", "Avg Session"]
    rows = []
    
    for stat in stats_list:
        rows.append([
            stat["name"],
            stat["total_playtime"],
            str(stat["sessions"]),
            stat["avg_session"],
        ])
    
    return [
        [sg.Text("Playtime Statistics", font=("Segoe UI", 12, "bold"))],
        [
            sg.Table(
                values=rows,
                headings=headers,
                max_col_width=20,
                auto_size_columns=False,
                col_widths=[20, 15, 10, 15],
                key="-STATS-TABLE-",
                size=(60, 12),
            )
        ],
        [
            sg.Button("Refresh"),
            sg.Button("Export Stats"),
            sg.Button("Reset Selected", key="-RESET-SELECTED-STATS-", tooltip=_tip("Reset playtime for the selected account")),
            sg.Button("Reset All Stats"),
        ],
    ]


def build_tools_tab() -> List:
    """Build Tools tab placeholder for future tools."""
    return [
        [sg.Text("Tools", font=("Segoe UI", 12, "bold"))],
        [sg.HorizontalSeparator()],
        [sg.Text("No tools configured right now.", font=("Segoe UI", 11, "bold"), text_color="#2C6E73")],
        [sg.Text("The previous Damage Calculator has been removed." )],
        [sg.Text("We can build the new tool here next.", font=("Segoe UI", 9, "italic"))],
    ]


def build_window(config: dict, accounts: List[Account], log_file_path: Optional[str] = None) -> sg.Window:
    """
    Build and return the main application window.
    
    Constructs the complete UI with all tabs:
    - Launch: Start instances with various methods
    - Accounts: Manage wizard accounts
    - Regions: Configure region-specific settings
    - Stats: View playtime statistics
    - Settings: Global configuration
    - Logs: Live log viewer
    
    Args:
        config: Application configuration dictionary
        accounts: List of Account objects to display
        log_file_path: Path to log file for live viewer
        
    Returns:
        PySimpleGUI Window object
    """
    global _UI_TOOLTIPS_ENABLED
    _UI_TOOLTIPS_ENABLED = bool(config.get("tooltips_enabled", False))

    current_region = config.get("current_region", "de")
    region_name = REGION_META.get(current_region, {}).get("name", current_region.upper())
    tr = lambda text: t(text, config.get("language", "en"))
    
    # Filter accounts by current region
    region_accounts = [acc for acc in accounts if acc.region == current_region]
    account_list = [account_display(acc) for acc in region_accounts]

    # Generate playtime statistics (lightweight – no I/O)
    tracker = PlaytimeTracker()
    stats_list = tracker.get_accounts_stats_sorted(region_accounts, sort_by="playtime")
    
    # Initialize log viewer if log file provided
    log_viewer = None
    if log_file_path:
        try:
            from pathlib import Path
            log_viewer = LogViewer(Path(log_file_path))
        except Exception as e:
            logging.getLogger("ui").warning(f"Could not initialize log viewer: {e}")

    # ── Adaptive sizing ────────────────────────────────────────────────────
    screen_h = _get_screen_height()
    # Leave room for taskbar (~40px), title bar (~30px), tab bar (~30px), status bar (~25px)
    tab_h = max(380, screen_h - 170)
    win_h = max(480, min(720, screen_h - 80))

    def _scroll_col(tab_layout: list, key: str) -> list:
        """Wrap a tab layout in a vertically-scrollable, horizontally-expanding column."""
        return [[
            sg.Column(
                tab_layout,
                scrollable=True,
                vertical_scroll_only=True,
                expand_x=True,
                expand_y=True,
                size=(870, tab_h),
                key=key,
            )
        ]]

    def _tab_visible(key: str, default: bool = True) -> bool:
        return bool(config.get(key, default))

    # Build main window layout
    show_extensions_tab = _tab_visible("show_extensions_tab", config.get("enable_extensions", False))
    show_tools_tab = _tab_visible("show_tools_tab", False)
    show_performance_tab = _tab_visible("show_performance_tab", config.get("enable_performance_monitor", True))

    tabs = [
        sg.Tab(tr("Launch"),      _scroll_col(build_launch_tab(config, account_list),    "-SCROLL-LAUNCH-"),      key="-TAB-LAUNCH-"),
        sg.Tab(tr("Accounts"),    _scroll_col(build_accounts_tab(account_list),           "-SCROLL-ACCOUNTS-"),    key="-TAB-ACCOUNTS-"),
        sg.Tab(tr("Regions"),     _scroll_col(build_regions_tab(config),                  "-SCROLL-REGIONS-"),     key="-TAB-REGIONS-"),
        sg.Tab(tr("Stats"),       _scroll_col(build_stats_tab(stats_list),                "-SCROLL-STATS-"),       key="-TAB-STATS-"),
        sg.Tab(tr("Settings"),    _scroll_col(build_settings_tab(config),                 "-SCROLL-SETTINGS-"),    key="-TAB-SETTINGS-"),
        sg.Tab(tr("Logs"),        _scroll_col(build_logs_tab(log_viewer),                 "-SCROLL-LOGS-"),        key="-TAB-LOGS-"),
    ]

    if show_extensions_tab:
        tabs.insert(2, sg.Tab(tr("Extensions"), _scroll_col(build_extensions_tab(config), "-SCROLL-EXTENSIONS-"), key="-TAB-EXTENSIONS-"))

    if show_tools_tab:
        tools_index = 4 if show_extensions_tab else 3
        tabs.insert(tools_index, sg.Tab(tr("Tools"), _scroll_col(build_tools_tab(), "-SCROLL-TOOLS-"), key="-TAB-TOOLS-"))

    if show_performance_tab:
        performance_index = 4 if (show_extensions_tab or show_tools_tab) else 3
        tabs.insert(performance_index, sg.Tab(tr("Performance"), _scroll_col(build_performance_tab(config.get("enable_performance_monitor", True)), "-SCROLL-PERF-"), key="-TAB-PERFORMANCE-"))

    layout = [
        # Title bar with app name, version, and active region
        [sg.Text(f"{APP_NAME} {APP_VERSION} | 🎮 Active: {region_name.upper()}", font=("Segoe UI", 14, "bold"))],

        # Update banner — hidden initially, shown when an update is found
        [
            sg.Text(
                "",
                key="-UPDATE-BANNER-",
                text_color="#000000",
                background_color="#FFD700",
                font=("Segoe UI", 10, "bold"),
                size=(80, 1),
                justification="center",
                visible=False,
                enable_events=True,
            ),
        ],

        # Main tab group
        [
            sg.TabGroup(
                [
                    tabs
                ],
                expand_x=True,
                expand_y=True,
            )
        ],
        
        # Status bar at bottom
        [sg.StatusBar(tr("Ready"), key="-STATUS-")],
    ]

    icon_path = resolve_icon_path(config)
    _win_kwargs: dict = {
        "finalize": True,
        "icon": icon_path,
        "resizable": True,
        "size": (900, win_h),
    }
    if config.get("save_window_state", False):
        wx = config.get("window_x")
        wy = config.get("window_y")
        if wx is not None and wy is not None:
            _win_kwargs["location"] = (int(wx), int(wy))
    window = sg.Window(APP_NAME, layout, **_win_kwargs)
    
    # ── Expand the TabGroup so it fills all space when resized ──────────
    window["-SCROLL-LAUNCH-"].expand(True, True, True)

    # ================== KEYBOARD SHORTCUTS ==================
    window.bind('<F1>', 'F1')
    window.bind('<F2>', 'F2')
    window.bind('<F3>', 'F3')
    window.bind('<F4>', 'F4')
    window.bind('<Control-e>', 'Ctrl+E')
    window.bind('<Control-s>', 'Ctrl+S')

    return window



