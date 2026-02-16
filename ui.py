"""UI components and theme management."""

from typing import List, Optional
from pathlib import Path
import logging

import PySimpleGUI as sg

from config import APP_NAME, APP_VERSION, REGION_META
from crypto import Account, account_display
from playtime_tracker import PlaytimeTracker
from log_viewer import LogViewer


def apply_theme(config: dict) -> None:
    """
    Apply custom theme based on configuration.
    Supports automatic WizDark (dark) theme.
    
    Args:
        config: Configuration dictionary with 'ui_theme' key
    """
    # Define WizDark (dark) theme
    sg.theme_add_new(
        "WizDark",
        {
            "BACKGROUND": "#101415",      # Very dark gray (almost black)
            "TEXT": "#E6E6E6",            # Light gray text
            "INPUT": "#1A1F20",           # Dark input boxes
            "TEXT_INPUT": "#E6E6E6",      # Light text in inputs
            "SCROLL": "#3A3F41",          # Darker scroll bars
            "BUTTON": ("#E6E6E6", "#2C6E73"),  # Teal buttons
            "PROGRESS": ("#2C6E73", "#101415"), # Progress bar
            "BORDER": 1,
            "SLIDER_DEPTH": 0,
            "PROGRESS_DEPTH": 0,
        },
    )
    
    # Define Light theme as alternative
    sg.theme_add_new(
        "WizLight",
        {
            "BACKGROUND": "#F5F5F5",      # Light gray background
            "TEXT": "#000000",            # Black text
            "INPUT": "#FFFFFF",           # White input boxes
            "TEXT_INPUT": "#000000",      # Black text in inputs
            "SCROLL": "#CCCCCC",          # Light scroll bars
            "BUTTON": ("#000000", "#87CEEB"),  # Light blue buttons
            "PROGRESS": ("#87CEEB", "#F5F5F5"),
            "BORDER": 1,
            "SLIDER_DEPTH": 0,
            "PROGRESS_DEPTH": 0,
        },
    )
    
    # Apply selected theme
    selected_theme = config.get("ui_theme", "WizDark")
    sg.theme(selected_theme)


def resolve_icon_path(config: dict) -> Optional[str]:
    """
    Resolve an icon path for the main window.
    Supports .ico directly, or .png with optional Pillow conversion.
    """
    icon_path = str(config.get("app_icon_path", "")).strip()
    if not icon_path:
        return None

    path = Path(icon_path)
    if not path.is_absolute():
        path = path.resolve()

    if not path.exists():
        logging.getLogger("ui").warning("Icon path not found: %s", path)
        return None

    if path.suffix.lower() == ".ico":
        return str(path)

    if path.suffix.lower() == ".png":
        ico_path = path.with_suffix(".ico")
        if ico_path.exists():
            return str(ico_path)
        try:
            from PIL import Image

            with Image.open(path) as img:
                img.save(ico_path)
            return str(ico_path)
        except Exception as exc:
            logging.getLogger("ui").warning(
                "Failed to convert PNG icon to ICO: %s", exc
            )
            return str(path)

    logging.getLogger("ui").warning("Unsupported icon format: %s", path)
    return None


def build_launch_tab(config: dict, account_list: List[str]) -> List:
    """Build Launch tab layout (window management moved to Extensions tab)."""
    current_region = config.get("current_region", "de")
    region_name = REGION_META.get(current_region, {}).get("name", current_region.upper())
    
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
            sg.Text("Switch Region:"),
            sg.Combo(
                values=[r[0] for r in available_regions],
                default_value=default_region,
                key="-REGION-SELECT-",
                readonly=True,
                enable_events=True,
                size=(35, 1)
            ),
            sg.Button("Apply Region", key="-APPLY-REGION-"),
        ],
        [
            sg.Button("🚀 Quicklaunch (1 Instance)", key="Quicklaunch"),
            sg.Button("🎮 Start Selected Instances", key="Start Instances"),
            sg.Button("🔐 Start Selected + Auto Login", key="Start + Auto Login"),
        ],
        [
            sg.Text("Select accounts to launch (Ctrl+Click for multiple):"),
            sg.Text("0 selected", key="-SELECTED-COUNT-", font=("Segoe UI", 9, "bold"), text_color="#2C6E73")
        ],
        [
            sg.Listbox(
                values=account_list,
                select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE,
                key="-AUTO-ACCOUNTS-",
                size=(55, 6),
                enable_events=True,  # Enable events to update counter
            )
        ],
        [
            sg.Checkbox(
                "Bring window to front",
                default=config.get("foreground_on_login", True),
                key="-FOREGROUND-",
            ),
            sg.Checkbox(
                "Set window title",
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
        [
            sg.Listbox(
                values=account_list,
                key="-ACCOUNTS-",
                size=(55, 12),
                enable_events=True,
            )
        ],
        [sg.Button("Add"), sg.Button("Edit"), sg.Button("Delete")],
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
    return [
        [sg.Text("Global Settings", font=("Segoe UI", 11, "bold"))],
        [
            sg.Text("Login wait seconds"),
            sg.Input(str(config.get("login_wait_seconds", 5)), key="-WAIT-", size=(10, 1))
        ],
        [
            sg.Text("Window title template"),
            sg.Input(config.get("window_title_template", "{name} ({username})"), key="-TITLE-")
        ],
        [
            sg.Text("Log level"),
            sg.Combo(
                ["DEBUG", "INFO", "WARNING", "ERROR"],
                default_value=config.get("log_level", "INFO"),
                key="-LOGLEVEL-",
                readonly=True,
            ),
        ],
        [
            sg.Text("UI Theme"),
            sg.Combo(
                ["WizDark", "WizLight"],
                default_value=config.get("ui_theme", "WizDark"),
                key="-THEME-",
                readonly=True,
                enable_events=True,
            ),
        ],
        [sg.Text("Region Visibility", font=("Segoe UI", 11, "bold"))],
        [
            sg.Checkbox(
                "Deutschland (DE)",
                default=config.get("show_region_de", True),
                key="-SHOW-DE-",
                enable_events=True
            ),
            sg.Checkbox(
                "United States (US)",
                default=config.get("show_region_us", True),
                key="-SHOW-US-",
                enable_events=True
            ),
        ],
        [
            sg.Checkbox(
                "France (FR)",
                default=config.get("show_region_fr", False),
                key="-SHOW-FR-",
                enable_events=True
            ),
            sg.Checkbox(
                "Italia (IT)",
                default=config.get("show_region_it", False),
                key="-SHOW-IT-",
                enable_events=True
            ),
        ],
        [
            sg.Checkbox(
                "United Kingdom (GB)",
                default=config.get("show_region_gb", False),
                key="-SHOW-GB-",
                enable_events=True
            ),
            sg.Checkbox(
                "Polska (PL)",
                default=config.get("show_region_pl", False),
                key="-SHOW-PL-",
                enable_events=True
            ),
        ],
        [
            sg.Checkbox(
                "España (ES)",
                default=config.get("show_region_es", False),
                key="-SHOW-ES-",
                enable_events=True
            ),
            sg.Checkbox(
                "Ελλάδα (GR)",
                default=config.get("show_region_gr", False),
                key="-SHOW-GR-",
                enable_events=True
            ),
        ],
        [sg.Button("Save settings")],
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



def build_wizwall_subtab(config: dict) -> List:
    """
    Build Wizwall sub-tab for multi-window management.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List layout for wizwall sub-tab
    """
    wizwall_enabled = config.get("wizwall_enabled", True)
    default_layout = config.get("wizwall_default_layout", "2x2")
    auto_set_resolution = config.get("wizwall_auto_set_resolution", True)
    
    return [
        [sg.Text("Wizwalker Multi-Window Management", font=("Segoe UI", 11, "bold"))],
        [
            sg.Checkbox(
                "Enable Wizwall Extension",
                default=wizwall_enabled,
                key="-WIZWALL-ENABLED-",
                enable_events=True,
            )
        ],
        [sg.HorizontalSeparator()],
        
        # Grid Layout Configuration
        [sg.Text("Grid Layout Configuration", font=("Segoe UI", 10, "bold"))],
        [
            sg.Text("Default Layout:"),
            sg.Combo(
                ["1x1", "2x1", "1x2", "2x2", "3x2", "3x3", "4x2", "4x3"],
                default_value=default_layout,
                key="-WIZWALL-LAYOUT-",
                readonly=True,
                size=(10, 1),
                disabled=not wizwall_enabled,
            ),
            sg.Text("(Columns x Rows)")
        ],
        [
            sg.Checkbox(
                "Auto-set game resolution for layout",
                default=auto_set_resolution,
                key="-WIZWALL-AUTO-RESOLUTION-",
                tooltip="Automatically configure preferences.xml before starting clients",
                disabled=not wizwall_enabled,
            )
        ],
        
        # Resolution Info
        [sg.Text("Optimal Resolutions (for 1920x1080)", font=("Segoe UI", 9, "italic"))],
        [
            sg.Text(
                "2x1: 952x1070 | 2x2: 952x532 | 3x2: 633x532 | 3x3: 633x353",
                font=("Courier", 8),
                text_color="#888888"
            )
        ],
        
        [sg.HorizontalSeparator()],
        
        # Window Management Actions
        [sg.Text("Window Management", font=("Segoe UI", 10, "bold"))],
        [
            sg.Button("📐 Arrange Windows", key="-ARRANGE-WINDOWS-", disabled=not wizwall_enabled),
            sg.Button("🔄 Refresh Window List", key="-REFRESH-WINDOWS-", disabled=not wizwall_enabled),
        ],
        [
            sg.Button("💾 Save Current Layout", key="-SAVE-LAYOUT-", disabled=not wizwall_enabled),
            sg.Button("📂 Restore Saved Layout", key="-RESTORE-LAYOUT-", disabled=not wizwall_enabled),
        ],
        [
            sg.Button("🎯 Set Resolution for Layout", key="-SET-RESOLUTION-", disabled=not wizwall_enabled),
            sg.Text("(Apply before starting clients)", font=("Segoe UI", 8, "italic"))
        ],
        
        [sg.HorizontalSeparator()],
        
        # Active Windows List
        [sg.Text("Active Wizard101 Windows", font=("Segoe UI", 10, "bold"))],
        [
            sg.Multiline(
                size=(70, 8),
                key="-WIZWALL-WINDOWS-",
                disabled=True,
                background_color="#1A1F20",
                text_color="#E6E6E6",
                font=("Courier", 9),
            )
        ],
        
        [sg.HorizontalSeparator()],
        
        # Status and Tips
        [sg.Text("💡 Tips:", font=("Segoe UI", 9, "bold"))],
        [sg.Text("• Set resolution BEFORE starting clients for pixel-perfect mouse coordination", font=("Segoe UI", 8))],
        [sg.Text("• Use 'Arrange Windows' after all clients are on login screen", font=("Segoe UI", 8))],
        [sg.Text("• Borderless windows are created automatically for seamless tiling", font=("Segoe UI", 8))],
    ]


def build_extensions_tab(config: dict) -> List:
    """
    Build Extensions tab with sub-tabs for different extensions.
    
    Currently includes:
    - Wizwall: Multi-window grid layout management
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List layout for extensions tab with sub-tabs
    """
    extensions_enabled = config.get("enable_extensions", True)
    
    # Build extension sub-tabs
    extension_subtabs = [
        sg.Tab("Wizwall", build_wizwall_subtab(config), key="-TAB-WIZWALL-"),
        # Future extensions can be added here:
        # sg.Tab("Combat Helper", build_combat_helper_subtab(config), key="-TAB-COMBAT-"),
        # sg.Tab("Quest Tracker", build_quest_tracker_subtab(config), key="-TAB-QUEST-"),
    ]
    
    if not extensions_enabled:
        return [
            [sg.Text("Extensions Disabled", font=("Segoe UI", 11, "bold"))],
            [sg.Text("Extensions are currently disabled.")],
            [sg.Text("Enable them in the configuration to access advanced features.")],
        ]
    
    return [
        [
            sg.TabGroup(
                [extension_subtabs],
                key="-EXTENSIONS-TABGROUP-"
            )
        ]
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
            sg.Button("Reset All Stats"),
        ],
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
    current_region = config.get("current_region", "de")
    region_name = REGION_META.get(current_region, {}).get("name", current_region.upper())
    
    # Filter accounts by current region
    region_accounts = [acc for acc in accounts if acc.region == current_region]
    account_list = [account_display(acc) for acc in region_accounts]

    # Generate playtime statistics (for all accounts, will show region-filtered in UI)
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

    # Build main window layout
    layout = [
        # Title bar with app name, version, and active region
        [sg.Text(f"{APP_NAME} {APP_VERSION} | 🎮 Active: {region_name.upper()}", font=("Segoe UI", 14, "bold"))],
        
        # Main tab group
        [
            sg.TabGroup(
                [
                    [
                        sg.Tab("Launch", build_launch_tab(config, account_list), key="-TAB-LAUNCH-"),
                        sg.Tab("Accounts", build_accounts_tab(account_list), key="-TAB-ACCOUNTS-"),
                        sg.Tab("Extensions", build_extensions_tab(config), key="-TAB-EXTENSIONS-"),
                        sg.Tab("Regions", build_regions_tab(config), key="-TAB-REGIONS-"),
                        sg.Tab("Stats", build_stats_tab(stats_list), key="-TAB-STATS-"),
                        sg.Tab("Settings", build_settings_tab(config), key="-TAB-SETTINGS-"),
                        sg.Tab("Logs", build_logs_tab(log_viewer), key="-TAB-LOGS-"),
                    ]
                ]
            )
        ],
        
        # Status bar at bottom
        [sg.StatusBar("Ready", key="-STATUS-")],
    ]

    icon_path = resolve_icon_path(config)
    window = sg.Window(APP_NAME, layout, finalize=True, icon=icon_path)
    
    # ================== KEYBOARD SHORTCUTS ==================
    # Bind keyboard shortcuts to the window
    window.bind('<F1>', 'F1')      # Quicklaunch
    window.bind('<F2>', 'F2')      # Multi-Instance
    window.bind('<F3>', 'F3')      # Auto-Login
    window.bind('<F4>', 'F4')      # Minimize to tray
    window.bind('<Control-e>', 'Ctrl+E')   # Export Stats
    window.bind('<Control-s>', 'Ctrl+S')   # Save Settings

    return window


