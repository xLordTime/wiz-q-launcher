# Wiz Q Launcher 6.0.0-beta.3 testen

Diese Version enthält die neue native Explorer-Oberfläche. Die Windows-EXE enthält Python, Qt und den nativen Launcher-Adapter; eine separate Python-/Rust-Installation ist nicht nötig.

## Download und Start

1. Auf GitHub unter **Actions → Version 6 Windows Build** den erfolgreichen Lauf für **Version-6.0** öffnen.
2. Das Artefakt **WizQLauncher-6.0-Windows-Beta** herunterladen und die ZIP-Datei entpacken.
3. Den bisherigen Launcher über **Beenden** vollständig schließen. Das X kann ihn lediglich in den Tray verschieben.
4. **WizQLauncher-v6.0.0-beta.3.exe** starten. Die Datei kann im Unterordner `release` der entpackten ZIP liegen.
5. Beim ersten 6.0-Start den Tresorschutz wählen und ein gefundenes 5.x-Profil übernehmen. Für ein vorhandenes 6.0-Profil werden die bisherigen Daten und der bisherige Schutzmodus verwendet.
6. Unter **Einstellungen → Launcher & Regionen** die Spielordner prüfen. Ein Spielordner enthält `Bin/WizardGraphicalClient.exe`.

Das Profil liegt unter `%LOCALAPPDATA%\WizQLauncher`. Das Importieren verändert die alten Quelldateien nicht. Ein Launcher-Profil kann jeweils nur von einer laufenden Launcher-Instanz geöffnet werden.

## Neue Bedienung

| Bedienelement | Funktion |
| --- | --- |
| Mein Launcher in der Pfadleiste | Alle Accounts öffnen, Such- und Regionsfilter zurücksetzen |
| Pfadsegment | Den entsprechenden Bereich oder die Gruppe öffnen |
| Kleiner Pfeil am Pfadsegment | Bereiche, Gruppen bzw. Unterseiten auswählen |
| Baumansicht links | Dieselben Ziele direkt öffnen |
| Zurück / Vorwärts | Vorige bzw. nächste Ansicht im Navigationsverlauf |
| Eine Ebene höher | Übergeordneten Bereich öffnen |
| Rechtsklick auf Pfadleiste | Lesbaren Pfad kopieren |
| Checkbox am Account | Account für den Start vormerken; Haken, Startauswahl-Text und fette Schrift bestätigen die Auswahl |
| Accountname / Doppelklick | Details anzeigen / Eigenschaften bearbeiten |
| Datei → Leere Instanz | Quicklaunch mit Region und Instanzanzahl |
| Einstellungen → Darstellung | Aero Explorer, Graphit Werkbank oder Arkaner Explorer wählen; alle 20 bisherigen Themes bleiben vorhanden |
| Trennleisten | Baumansicht und Instanzbereich vergrößern/verkleinern; Aufteilung wird beim Beenden gespeichert |

**Startauswahl:** Die Zeilenmarkierung zeigt den Account für die Detailansicht. Der Haken und der Text **Ausgewählt** bestimmen die Startauswahl. Der Startknopf nennt die Anzahl. Beim Filtern bleiben Checkboxen gemerkt. Gestartet werden ausschließlich die **sichtbaren, angekreuzten** Accounts. Ein Startprofil lässt sich unten über **Startprofil** speichern und laden.

## Sinnvolle erste Testrunde

1. Accountanzahl und bisherige Spielzeitsummen mit der alten Version vergleichen.
2. Über den Pfeil bei **Alle Accounts** eine Gruppe öffnen, dann über die Pfadleiste zum übergeordneten Bereich wechseln. Zurück/Vorwärts und die Baumansicht ausprobieren.
3. Einen Account ankreuzen, die Gruppe wechseln und zurückkehren. Die Markierung muss erhalten bleiben. Ein ausgeblendeter Account darf beim Start einer anderen Gruppe nicht mitstarten.
4. Account hinzufügen/bearbeiten; unter **Accounts verwalten** Accounts per Drag & Drop sortieren und Gruppen wechseln.
5. Einen DE- und einen US-Client separat starten. Autologin, Accountzuordnung, Fenstertitel und Spielzeiterfassung prüfen. Anschließend einen gemeinsamen Start testen.
6. Quicklaunch mit der ausdrücklich gewählten Region testen. Im Instanzbereich Fokussieren, Anordnen und Zuordnen ausprobieren.
7. Die drei Desktop-Stile durchschalten, die Fensteraufteilung ändern, beenden und erneut starten. Daten, Theme und Aufteilung müssen erhalten bleiben.
8. F1 öffnen und nach einer Einstellung suchen. Sicherung über Datei → Profil sichern oder Strg+S erstellen.

Die automatischen Tests prüfen Datenhaltung, Navigation und den gepackten Windows-Start einschließlich EXE-Austausch. Eine erfolgreiche Anmeldung an den aktuell installierten DE-/US-Spielclients kann nur mit diesen Clients geprüft werden. Nach Spielupdates können sich Loginmuster ändern.

## Tastatur

- **Alt+Links / Alt+Rechts:** Zurück / Vorwärts
- **Alt+Oben:** Eine Ebene höher
- **Alt+Pos1:** Startansicht
- **F5:** Sichtbare Startauswahl starten
- **Strg+N:** Account hinzufügen
- **Strg+Umschalt+N:** Quicklaunch
- **Strg+S:** Profil sichern
- **Strg+1 … Strg+6:** Hauptbereiche
- **Strg+L:** Tresor sperren
- **Strg+Q:** Vollständig beenden
- **F1:** Hilfe

Clips/Aufnahmen benötigen weiterhin einen vorhandenen FFmpeg-Encoder. Aufnahme startet ausschließlich nach deiner Aktion.
