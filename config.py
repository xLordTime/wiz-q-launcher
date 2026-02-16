"""Configuration module for Wizard101 launcher."""

import json
import logging
from pathlib import Path
from typing import Dict, Any

APP_NAME = "Wiz Q Launcher"
APP_VERSION = "0.3.0"

# Region metadata
REGION_META = {
    "de": {"name": "Deutschland", "server": "login-de.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(DE)"},
    "us": {"name": "USA", "server": "login.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101"},
    "fr": {"name": "France", "server": "login-fr.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(FR)"},
    "it": {"name": "Italia", "server": "login-it.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(IT)"},
    "gb": {"name": "United Kingdom", "server": "login-gb.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(GB)"},
    "pl": {"name": "Polska", "server": "login-pl.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(PL)"},
    "es": {"name": "España", "server": "login-es.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(ES)"},
    "gr": {"name": "Ελλάδα", "server": "login-gr.eu.wizard101.com", "port": 12000, "install": r"C:\ProgramData\KingsIsle Entertainment\Wizard101(GR)"},
}

DEFAULT_CONFIG = {
    # Legacy config keys (kept for backward compatibility)
    "default_install": r"C:\\ProgramData\\KingsIsle Entertainment\\Wizard101(DE)",
    "default_install_us": r"C:\\ProgramData\\KingsIsle Entertainment\\Wizard101",
    "current_region": "de",
    "region": "de",
    "extra_args": [],
    
    # Launch settings
    "login_wait_seconds": 5,
    "foreground_on_login": True,
    "set_window_title": True,
    "window_title_template": "{name} ({username})",
    
    # Logging
    "log_level": "INFO",
    "log_max_bytes": 1048576,
    "log_backup_count": 5,
    "debug_mode": False,
    
    # UI Theme
    "ui_theme": "WizDark",
    "ui_dark_theme": "WizDark",
    "ui_light_theme": "Light",
    
    # Window State
    "window_width": 900,
    "window_height": 700,
    "window_x": None,
    "window_y": None,
    "save_window_state": True,
    
    # Region visibility toggles
    "show_region_de": True,
    "show_region_us": True,
    "show_region_fr": False,
    "show_region_it": False,
    "show_region_gb": False,
    "show_region_pl": False,
    "show_region_es": False,
    "show_region_gr": False,
    
    # Per-region install paths
    "region_install_de": "",
    "region_install_us": "",
    "region_install_fr": "",
    "region_install_it": "",
    "region_install_gb": "",
    "region_install_pl": "",
    "region_install_es": "",
    "region_install_gr": "",
    
    # Per-region servers
    "region_server_de": "login-de.eu.wizard101.com",
    "region_server_us": "login.wizard101.com",
    "region_server_fr": "login-fr.eu.wizard101.com",
    "region_server_it": "login-it.eu.wizard101.com",
    "region_server_gb": "login-gb.eu.wizard101.com",
    "region_server_pl": "login-pl.eu.wizard101.com",
    "region_server_es": "login-es.eu.wizard101.com",
    "region_server_gr": "login-gr.eu.wizard101.com",
    
    # Per-region ports
    "region_port_de": 12000,
    "region_port_us": 12000,
    "region_port_fr": 12000,
    "region_port_it": 12000,
    "region_port_gb": 12000,
    "region_port_pl": 12000,
    "region_port_es": 12000,
    "region_port_gr": 12000,
    
    # Auto-Region-Switching
    "auto_region_switch": False,
    "account_region_map": {},  # {account_name: region_code}
    
    # Playtime Tracking
    "auto_playtime_tracking": True,
    "track_without_autologin": True,  # Track by process detection
    
    # Performance Monitoring
    "enable_performance_monitor": True,
    "performance_poll_interval": 5,  # seconds
    
    # Discord Integration
    "discord_webhook_url": "",
    "discord_notifications": False,
    "discord_session_start": True,
    "discord_session_end": True,
    "discord_errors": True,
    
    # Update Checking
    "check_for_updates": True,
    "update_check_interval": 86400,  # 24 hours in seconds
    "last_update_check": 0,
    
    # Error Reporting
    "enable_error_reporting": True,
    "github_repo": "oliwi/q-launcher",

    # App icon (optional)
    "app_icon_path": "icon.ico",
    
    # Extensions
    "enable_extensions": True,
    "wizwall_enabled": True,
    "wizwall_default_layout": "2x2",
    "wizwall_auto_set_resolution": True,
}


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize config to ensure all required keys exist."""
    normalized = DEFAULT_CONFIG.copy()
    normalized.update(config)
    # Ensure all region toggles exist
    for region_code in REGION_META:
        normalized.setdefault(f"show_region_{region_code}", DEFAULT_CONFIG.get(f"show_region_{region_code}", False))
        normalized.setdefault(f"region_install_{region_code}", DEFAULT_CONFIG.get(f"region_install_{region_code}", ""))
        normalized.setdefault(f"region_server_{region_code}", DEFAULT_CONFIG.get(f"region_server_{region_code}", ""))
        normalized.setdefault(f"region_port_{region_code}", DEFAULT_CONFIG.get(f"region_port_{region_code}", 12000))
    return normalized


REGISTRY_KEY = (
    r"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
    r"{A9E27FF5-6294-46A8-B8FD-77B1DECA3021}"
)


def merge_config(defaults: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override config into defaults."""
    merged = defaults.copy()
    for key, value in override.items():
        merged[key] = value
    return merged


def load_config(config_file: Path) -> Dict[str, Any]:
    """Load configuration from file or create default."""
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as handle:
            user_config = json.load(handle)
        return normalize_config(user_config)

    save_config(config_file, DEFAULT_CONFIG)
    return normalize_config(DEFAULT_CONFIG.copy())


def save_config(config_file: Path, config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    with config_file.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
