# Update 3.1 - Logging

## Ziel

Das Logging soll früher im Startprozess aktiv sein, stabiler initialisiert werden und ungefangene Fehler zuverlässiger in `logs/launcher.log` schreiben.

## Umsetzung

1. Logging beim Start vor der automatischen Installations-Erkennung aktivieren.
2. Log-Verzeichnis bei Bedarf automatisch anlegen.
3. Doppelte Root-Handler verhindern, wenn Logging erneut initialisiert wird.
4. Uncaught Exceptions aus Hauptthread und Hintergrund-Threads ins Log schreiben.

## Aktueller Stand

- Logging-Härtung ist umgesetzt (frühe Initialisierung, Handler-Bereinigung, Exception-Hooks).
- Changelog ist auf dem aktuellen Gesamtstand der Unreleased-Änderungen erweitert.
- Folgearbeiten aus derselben Entwicklungsphase wurden ebenfalls umgesetzt:
	- Window-Tracking robuster (PID-gestützte Fallback-Erkennung).
	- UI-Modernisierung inkl. tabbasierter Sichtbarkeit und Pink-Theme.
	- Sicherheitslogik erweitert (optionales Masterpasswort, temporäre Entsperrung, Live-Status im Settings-Bereich).
	- Lokales Backup/Restore-System mit stabiler Archivstruktur.
	- Speicherung nach AppData verschoben inkl. Legacy-Migration und nachträglicher Migrationshärtung.
	- Prio-1 Stabilität/Sicherheit umgesetzt:
		- Migrationsstatus im Settings-Tab + Dry-Run mit Dateiliste.
		- Backup/Restore mit Integritätsprüfung (Manifest-Version + SHA-256 pro Datei).
		- Restore-Rollback auf Pre-Restore-Snapshot bei Fehlern.
		- Backup-/Restore-Scope (`config`, `config_data`, `full`) im UI auswählbar.
		- Temporäre Masterpasswort-Entsperrung zeigt Restdauer live im UI.
		- Lokale Secret-Invalidierung via "Lock Now" Button.

## Erwarteter Effekt

- Mehr Diagnose-Informationen direkt beim Start.
- Weniger verlorene Fehlermeldungen.
- Sauberere Log-Ausgabe bei mehreren Initialisierungen oder Entwicklungsstarts.

## Nächste Prüfungen

- Start der App und Kontrolle, ob `logs/launcher.log` sofort angelegt wird.
- Test eines absichtlichen Fehlers, um die Exception-Weiterleitung zu prüfen.
- Prüfen, ob der LogViewer unverändert mit dem neuen Log-Flow arbeitet.
- Einmaliger Upgrade-Test von alter Version auf neue Version, um AppData-Migration und Backup-Workflow gemeinsam zu validieren.