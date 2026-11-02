**Wiz Q Launcher 6.0.0-beta.4 – Spielsprache und Autologin**

- Spielsprache und Loginserver sind unabhängig: zum Beispiel DE mit US-Englisch ohne `-A` oder DE mit Deutsch über `-A de`.
- Unter **Einstellungen → Launcher & Regionen → [Region] · Spielsprache** lässt sich die Sprache für jedes vorhandene Serverprofil speichern. Die Auswahl über der Accountliste und im Quicklaunch-Dialog kann sie für einen einzelnen Start überschreiben. Das gilt für Accounts, leere Instanzen, Startprofile und Shortcuts.
- Verfügbar: US-Englisch, Deutsch, Französisch, Italienisch, UK-Englisch, Polnisch, Spanisch und Griechisch. Die Spielinstallation muss die gewählten Sprachdateien enthalten. Bestehende Standardsprachen bleiben erhalten.
- Die Deimos-Start-/Loginlogik wurde erneut mit dem aktuellen Upstream verglichen. Die Mustersuche prüft jetzt die tatsächlichen Instruktionen und relative Ziele, erlaubt abweichende Stackpositionen und grenzt das bisher sehr breite Fenstermuster ein. Mehrdeutige Treffer werden weiterhin nicht verwendet.
- Der Login wartet auf die Clientinitialisierung; die Wartezeit ist für langsamere PCs einstellbar. Bereits gesendete Anmeldungen werden nicht wiederholt. Die Fenstereingabe wird auch bei Fehlern wieder freigegeben.
- Statt der bisherigen allgemeinen Meldung gibt es feste Fehlercodes für fehlende/mehrdeutige Muster, Berechtigungen, Initialisierung, Zeitüberschreitung und Hilfsprozessfehler. Zugangsdaten und rohe Fehlermeldungen werden nicht ausgegeben.
- Accountauswahl, Themes und vorhandene Profildaten bleiben erhalten.

**Update:** Im vorhandenen 6.0-Launcher unter **Einstellungen → Updates** den Kanal **beta** wählen, **Nach Updates suchen → Herunterladen → Neustarten & anwenden**. Alternativ `WizQLauncher-v6.0.0-beta.4.exe` herunterladen, den alten Launcher über **Beenden** schließen und die neue EXE starten. Python/Rust sind nicht separat nötig.

Der Windows-Workflow prüft Python/Qt, native Muster mit synthetischen Daten, EXE-Build und den echten EXE-Austausch mit Datenerhalt vor der Veröffentlichung. Eine echte Anmeldung an den aktuellen DE-/US-Spielclients ist hier nicht möglich; die neue Diagnose zeigt bei verbleibenden Problemen den konkreten Fehlercode. Diese Version bleibt ein Prerelease. Clips/Aufnahmen benötigen einen vorhandenen FFmpeg-Encoder.
