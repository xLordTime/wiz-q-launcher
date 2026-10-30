from dataclasses import dataclass

REGIONS = {
    "de": "Deutschland",
    "us": "United States",
    "fr": "France",
    "it": "Italia",
    "gb": "United Kingdom",
    "pl": "Polska",
    "es": "España",
    "gr": "Ελλάδα",
}


@dataclass(frozen=True)
class Setting:
    key: str
    section: str
    title: str
    default: object
    help: str
    choices: tuple = ()
    low: int = 0
    high: int = 100000


SETTINGS = [
    Setting(
        "language",
        "Allgemein",
        "Sprache",
        "de",
        "Deutsch ist die Sprache der ersten 6.0-Beta. Bestehende Sprachwahl bleibt gespeichert; die vollständige englische UI folgt.",
        ("de", "en"),
    ),
    Setting(
        "close_to_tray",
        "Allgemein",
        "Beim Schließen im Tray weiterlaufen",
        True,
        "Damit wird Spielzeit weiter erfasst. Vollständig beenden über das Tray-Menü oder Strg+Q.",
    ),
    Setting(
        "theme",
        "Darstellung",
        "Theme",
        "aero-explorer",
        "Drei klassische Desktop-Stile, 20 weitere Themes und eigene Designs. Das Theme verändert die Gestaltung, nicht die Bedienlogik.",
    ),
    Setting(
        "performance",
        "Darstellung",
        "Leistungsprofil",
        "balanced",
        "Sparsam schaltet dekorative Bewegung aus. Ausgewogen und Effekte aktivieren begrenzte Animationen.",
        ("eco", "balanced", "effects"),
    ),
    Setting(
        "animations",
        "Darstellung",
        "Sanfte Übergänge",
        True,
        "Kurze Animationen für Seiten, Menüs und Fokus. Windows-Einstellungen für reduzierte Bewegung werden berücksichtigt.",
    ),
    Setting(
        "font_size",
        "Darstellung",
        "Schriftgröße",
        9,
        "Die Schrift wird zusätzlich zur Windows-DPI-Skalierung angepasst.",
        low=9,
        high=18,
    ),
    Setting(
        "current_region",
        "Launcher & Regionen",
        "Standardregion",
        "de",
        "DE und US sind getrennte Installationen/Startprofile. Ein fehlender Pfad wird nie durch eine andere Region ersetzt.",
        tuple(REGIONS),
    ),
    Setting(
        "parallel_launches",
        "Launcher & Regionen",
        "Parallele Startaufträge",
        1,
        "Ein Auftrag ist auf älteren PCs zuverlässiger. Mehrere Aufträge sind eindeutig über Prozess-IDs zugeordnet.",
        low=1,
        high=4,
    ),
    Setting(
        "launch_delay",
        "Launcher & Regionen",
        "Pause zwischen Starts (Sekunden)",
        2,
        "Entlastet CPU und Festplatte beim Öffnen mehrerer Clients.",
        low=0,
        high=30,
    ),
    Setting(
        "login_timeout",
        "Launcher & Regionen",
        "Fenster-Timeout (Sekunden)",
        45,
        "Wartezeit auf das Fenster der exakt gestarteten Prozess-ID.",
        low=10,
        high=180,
    ),
    Setting(
        "set_window_title",
        "Fenster & Shortcuts",
        "Nickname als Fenstertitel",
        True,
        "Verwendet nur den Nickname, niemals Username oder Passwort.",
    ),
    Setting(
        "window_layout",
        "Fenster & Shortcuts",
        "Fensteranordnung",
        "2x2",
        "Aktive Instanzen auf dem Hauptbildschirm anordnen. Fensterpositionen lassen sich zusätzlich speichern.",
        ("2x2", "horizontal", "vertical"),
    ),
    Setting(
        "borderless",
        "Fenster & Shortcuts",
        "Rahmenlose Fenster beim Anordnen",
        False,
        "Entfernt die Titelleiste bei der Anordnung. Normale Fensterrahmen lassen sich über dieselbe Einstellung wiederherstellen.",
    ),
    Setting(
        "auto_playtime_tracking",
        "Playtime",
        "Spielzeit erfassen",
        True,
        "Misst Client-Laufzeit, keine AFK-Erkennung. Regelmäßige Zwischenstände begrenzen Zeitverlust nach Abstürzen.",
    ),
    Setting(
        "track_without_autologin",
        "Playtime",
        "Nicht zugeordnete Instanzen anzeigen",
        True,
        "Extern gestartete Clients erscheinen ohne geratenen Accountnamen und können manuell zugeordnet werden.",
    ),
    Setting(
        "discord_rich_presence",
        "Discord",
        "Discord Rich Presence",
        True,
        "Zeigt auf Wunsch Nickname, Sitzung und Spielzeit in Discord. Keine Discord-Anmeldung im Launcher nötig.",
    ),
    Setting(
        "discord_rpc_yield_to_game",
        "Discord",
        "Normale Wizard101-Spielerkennung bevorzugen",
        True,
        "Während Clients laufen wird Launcher-RPC freigegeben, damit Discord Wizard101 wie bisher erkennen kann.",
    ),
    Setting(
        "discord_rpc_update_interval",
        "Discord",
        "Discord-Aktualisierung (Sekunden)",
        15,
        "Häufigere Abfragen sind für den Status nicht nötig.",
        low=5,
        high=120,
    ),
    Setting(
        "discord_show_nickname",
        "Discord",
        "Nickname im Status anzeigen",
        False,
        "Aktivieren, wenn der ausgewählte Accountname im öffentlichen Discord-Status sichtbar sein darf.",
    ),
    Setting(
        "discord_notifications",
        "Discord",
        "Webhook-Benachrichtigungen",
        False,
        "Sendet nur bei hinterlegter Webhook-URL und aktivierten Ereignissen. Die URL wird verschlüsselt gespeichert.",
    ),
    Setting(
        "discord_session_start",
        "Discord",
        "Webhook bei Sitzungsstart",
        True,
        "Versendet einen Hinweis bei einem neuen Launcher-Startauftrag, nicht bei einer Wiederherstellung.",
    ),
    Setting(
        "discord_session_end",
        "Discord",
        "Webhook bei Sitzungsende",
        True,
        "Versendet Nickname und erfasste Dauer. Kein Username oder Passwort.",
    ),
    Setting(
        "check_for_updates",
        "Updates",
        "Automatisch nach Updates suchen",
        True,
        "Prüft GitHub ohne Telemetrie. Download und Anwendung erfolgen erst auf deine Aktion.",
    ),
    Setting(
        "update_channel",
        "Updates",
        "Updatekanal",
        "stable",
        "Beta-Versionen sind nur im Beta-Kanal verfügbar.",
        ("stable", "beta"),
    ),
    Setting(
        "backup_interval",
        "Speicher & Sicherungen",
        "Sicherungsintervall (Minuten)",
        5,
        "Erstellt konsistente lokale Sicherungen über die SQLite Backup API.",
        low=1,
        high=60,
    ),
    Setting(
        "backup_keep",
        "Speicher & Sicherungen",
        "Anzahl rollierender Sicherungen",
        10,
        "Die letzte gute Sicherung wird erst nach einem geprüften Ersatz rotiert.",
        low=3,
        high=50,
    ),
    Setting(
        "lock_minutes",
        "Sicherheit",
        "Tresor nach Inaktivität sperren (Minuten, 0 = aus)",
        15,
        "Sperrt Zugangsdaten, ohne laufende Spiele zu schließen. Neue Starts und Accountbearbeitung benötigen erneutes Entsperren.",
        low=0,
        high=240,
    ),
    Setting(
        "capture_fps",
        "Clips and Record",
        "Aufnahme-FPS",
        20,
        "Niedrigere Werte entlasten ältere PCs. Aufnahme läuft als eigener Encoderprozess.",
        low=5,
        high=60,
    ),
    Setting(
        "clip_buffer_seconds",
        "Clips and Record",
        "Replay-Dauer (Sekunden)",
        30,
        "Komprimierte kurze Segmente auf der Festplatte; kein großer Rohbildpuffer im RAM.",
        low=10,
        high=120,
    ),
    Setting(
        "capture_quota_mb",
        "Clips and Record",
        "Replay-Speicherlimit (MiB)",
        512,
        "Begrenzt den Replay-Puffer. Fertige Aufnahmen werden nicht automatisch gelöscht.",
        low=64,
        high=4096,
    ),
    Setting(
        "ffmpeg_path",
        "Clips and Record",
        "FFmpeg-EXE (optional)",
        "",
        "Leer verwendet einen vorhandenen FFmpeg-Befehl. Es wird nichts ungefragt heruntergeladen. Ein eigener Build benötigt gdigrab und libx264.",
    ),
    Setting(
        "capture_audio_device",
        "Clips and Record",
        "Audio-Gerätename (optional)",
        "",
        "Leer bedeutet ohne Audio. Exakter DirectShow-Name eines Aufnahmegeräts; kein Mikrofon wird automatisch aktiviert.",
    ),
]
for code, title in REGIONS.items():
    SETTINGS.extend(
        [
            Setting(
                "region_install_" + code,
                "Launcher & Regionen",
                f"{code.upper()} · Spielordner",
                "",
                f"Installation für {title}; muss Bin/WizardGraphicalClient.exe enthalten. Über die Erkennung oder den Ordnerdialog auswählen.",
            ),
            Setting(
                "region_server_" + code,
                "Launcher & Regionen",
                f"{code.upper()} · Loginserver",
                "login.us.wizard101.com" if code == "us" else f"login-{code}.eu.wizard101.com",
                "Aus der bisherigen Version übernommenes Serverprofil. Verfügbarkeit und Autologin hängen vom aktuellen Spielclient ab.",
            ),
            Setting(
                "region_port_" + code,
                "Launcher & Regionen",
                f"{code.upper()} · Port",
                12000,
                "Loginport des Serverprofils.",
                low=1,
                high=65535,
            ),
        ]
    )

BY_KEY = {s.key: s for s in SETTINGS}


def get(store, key):
    spec = BY_KEY[key]
    return store.get(key, spec.default)


def set_value(store, key, value):
    spec = BY_KEY[key]
    if type(value) is not type(spec.default):
        raise ValueError("Ungültiger Einstellungstyp")
    if spec.choices and value not in spec.choices:
        raise ValueError("Ungültige Auswahl")
    if type(value) is int and not spec.low <= value <= spec.high:
        raise ValueError("Wert außerhalb des gültigen Bereichs")
    if key.startswith("region_server_") and (
        not value or any(c.isspace() for c in value) or ":" in value or "/" in value
    ):
        raise ValueError("Nur Serverhostname ohne Port oder Pfad eingeben")
    store.set(key, value)
