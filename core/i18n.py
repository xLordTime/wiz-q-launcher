"""Small runtime translation helper for the launcher UI."""

LANGUAGE_OPTIONS = ["English", "Deutsch"]
_LANGUAGE_CODES = {"English": "en", "Deutsch": "de"}

_TRANSLATIONS = {
    "de": {
        "Global Settings": "Allgemeine Einstellungen",
        "Find setting/key": "Einstellung/Schlüssel suchen",
        "Search": "Suchen",
        "Clear": "Löschen",
        "Search by label, config key, or UI key.": "Nach Bezeichnung, Konfigurations- oder UI-Schlüssel suchen.",
        "Login wait seconds": "Wartezeit vor dem Login (Sekunden)",
        "Window title template": "Fenstertitel-Vorlage",
        "Log level": "Log-Level",
        "UI": "Benutzeroberfläche",
        "Theme": "Theme",
        "Remember window position": "Fensterposition merken",
        "Language": "Sprache",
        "English": "Englisch",
        "Deutsch": "Deutsch",
        "Discord Rich Presence": "Discord Rich Presence",
        "Enable Discord Rich Presence": "Discord Rich Presence aktivieren",
        "RPC update interval (sec)": "RPC-Aktualisierungsintervall (Sek.)",
        "Discord Webhook Notifications": "Discord-Webhook-Benachrichtigungen",
        "Webhook URL": "Webhook-URL",
        "Enable webhook notifications": "Webhook-Benachrichtigungen aktivieren",
        "Test": "Testen",
        "Session start": "Sitzungsbeginn",
        "Session end": "Sitzungsende",
        "Errors": "Fehler",
        "Update Checker": "Update-Prüfung",
        "Check for Updates": "Nach Updates suchen",
        "Automatically check for updates on startup": "Beim Start automatisch nach Updates suchen",
        "Storage Migration": "Speichermigration",
        "Migration Dry-Run": "Migration testen",
        "Tab Visibility": "Sichtbarkeit der Tabs",
        "Show Tools tab": "Werkzeuge-Tab anzeigen",
        "Show Extensions tab": "Erweiterungen-Tab anzeigen",
        "Show Performance tab": "Performance-Tab anzeigen",
        "Show Wizwall extension": "Wizwall-Erweiterung anzeigen",
        "Show Clip & Record extension": "Clip-&-Aufnahme-Erweiterung anzeigen",
        "Issue Reporter": "Fehler melden",
        "Title": "Titel",
        "Context": "Kontext",
        "Report Problem": "Problem melden",
        "Region Visibility": "Sichtbarkeit der Regionen",
        "United States (US)": "Vereinigte Staaten (US)",
        "Save settings": "Einstellungen speichern",
        "Playtime Tracking": "Spielzeit-Tracking",
        "Track playtime automatically": "Spielzeit automatisch erfassen",
        "Track even without auto-login": "Auch ohne Auto-Login erfassen",
        "Launch Options": "Startoptionen",
        "Extra launch arguments": "Zusätzliche Startargumente",
        "Backup & Restore": "Sichern & Wiederherstellen",
        "Backup content": "Sicherungsinhalt",
        "Create Backup": "Sicherung erstellen",
        "Open Backup Folder": "Sicherungsordner öffnen",
        "Restore file": "Datei wiederherstellen",
        "Browse": "Durchsuchen",
        "Restore Backup": "Sicherung wiederherstellen",
        "Restore scope": "Wiederherstellungsumfang",
        "Security": "Sicherheit",
        "Temporary Unlock": "Temporäre Entsperrung",
        "Remember unlock for": "Entsperrung merken für",
        "day(s)": "Tag(e)",
        "Suspend Password": "Passwort aussetzen",
        "Lock Now": "Jetzt sperren",
        "Password Management": "Passwortverwaltung",
        "Change Master Password": "Master-Passwort ändern",
        "Performance Monitor": "Performance-Monitor",
        "Enable Performance Monitoring": "Performance-Überwachung aktivieren",
        "Refresh Metrics": "Metriken aktualisieren",
        "Launch": "Start",
        "Accounts": "Konten",
        "Regions": "Regionen",
        "Stats": "Statistik",
        "Settings": "Einstellungen",
        "Logs": "Protokolle",
        "Extensions": "Erweiterungen",
        "Tools": "Werkzeuge",
        "Performance": "Performance",
        "Ready": "Bereit",
        "Switch Region:": "Region wechseln:",
        "Apply Region": "Region anwenden",
        "Select accounts to launch (Ctrl+Click for multiple):": "Konten zum Starten auswählen (Strg+Klick für mehrere):",
        "Bring window to front": "Fenster in den Vordergrund holen",
        "Set window title": "Fenstertitel setzen",
        "Install path:": "Installationspfad:",
        "Login Server:": "Login-Server:",
        "Port:": "Port:",
        "Add": "Hinzufügen",
        "Edit": "Bearbeiten",
        "Delete": "Löschen",
        "Check for updates": "Nach Updates suchen",
        "⬇ Download Update": "⬇ Update herunterladen",
        "No tools configured right now.": "Derzeit sind keine Werkzeuge konfiguriert.",
        "The previous Damage Calculator has been removed.": "Der vorherige Schadensrechner wurde entfernt.",
        "We can build the new tool here next.": "Hier kann als Nächstes ein neues Werkzeug entstehen.",
        "CPU Usage:": "CPU-Auslastung:",
        "RAM Usage:": "RAM-Auslastung:",
        "Wizard Memory:": "Wizard-Speicher:",
        "Refresh Metrics": "Metriken aktualisieren",
        "Clear History": "Verlauf löschen",
        "Live Log Viewer": "Live-Protokollanzeige",
        "Filter by level:": "Nach Level filtern:",
        "Copy": "Kopieren",
        "Open log folder": "Protokollordner öffnen",
        "Refresh Logs": "Protokolle aktualisieren",
        "Export Log": "Protokoll exportieren",
        "Playtime Statistics": "Spielzeitstatistik",
        "Refresh": "Aktualisieren",
        "Export Stats": "Statistik exportieren",
        "Reset Selected": "Ausgewählte zurücksetzen",
        "Reset All Stats": "Alle Statistiken zurücksetzen",
    }
}


def language_code(value: str) -> str:
    """Return a supported language code, defaulting to English."""
    value = str(value or "en").strip().lower()
    if value in ("de", "deutsch", "german"):
        return "de"
    return "en"


def language_label(code: str) -> str:
    """Return the display label for a language code."""
    return "Deutsch" if language_code(code) == "de" else "English"


def t(text: str, language: str = "en") -> str:
    """Translate a UI string; English remains the source-language fallback."""
    return _TRANSLATIONS.get(language_code(language), {}).get(text, text)


def selected_language_code(label: str) -> str:
    """Convert a Settings combo label into its persisted language code."""
    return _LANGUAGE_CODES.get(str(label), "en")
