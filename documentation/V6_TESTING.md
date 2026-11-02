# Wiz Q Launcher 6.0.0-beta.6 testen

Diese Version enthält die neue native Explorer-Oberfläche. Die Windows-EXE enthält Python, Qt und den nativen Launcher-Adapter; eine separate Python-/Rust-Installation ist nicht nötig.

## Download und Start

1. Auf GitHub unter **Actions → Version 6 Windows Build** den erfolgreichen Lauf für **Version-6.0** öffnen.
2. Das Artefakt **WizQLauncher-6.0-Windows-Beta** herunterladen und die ZIP-Datei entpacken.
3. Den bisherigen Launcher über **Beenden** vollständig schließen. Das X kann ihn lediglich in den Tray verschieben.
4. **WizQLauncher-v6.0.0-beta.6.exe** starten. Die Datei kann im Unterordner `release` der entpackten ZIP liegen.
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
| Datei → Leere Instanz | Quicklaunch mit Region, Spielsprache und Instanzanzahl |
| Sprache über der Accountliste | Sprache für alle Accounts dieses Starts; Serverprofil übernimmt die jeweilige Regionseinstellung |
| Einstellungen → Darstellung | Aero Explorer, Graphit Werkbank oder Arkaner Explorer wählen; alle 20 bisherigen Themes bleiben vorhanden |
| Trennleisten | Baumansicht und Instanzbereich vergrößern/verkleinern; Aufteilung wird beim Beenden gespeichert |

**Startauswahl:** Die Zeilenmarkierung zeigt den Account für die Detailansicht. Der Haken und der Text **Ausgewählt** bestimmen die Startauswahl. Der Startknopf nennt die Anzahl. Beim Filtern bleiben Checkboxen gemerkt. Gestartet werden ausschließlich die **sichtbaren, angekreuzten** Accounts. Ein Startprofil lässt sich unten über **Startprofil** speichern und laden.

## Sinnvolle erste Testrunde

1. Accountanzahl und bisherige Spielzeitsummen mit der alten Version vergleichen.
2. Über den Pfeil bei **Alle Accounts** eine Gruppe öffnen, dann über die Pfadleiste zum übergeordneten Bereich wechseln. Zurück/Vorwärts und die Baumansicht ausprobieren.
3. Einen Account ankreuzen, die Gruppe wechseln und zurückkehren. Die Markierung muss erhalten bleiben. Ein ausgeblendeter Account darf beim Start einer anderen Gruppe nicht mitstarten.
4. Account hinzufügen/bearbeiten; unter **Accounts verwalten** Accounts per Drag & Drop sortieren und Gruppen wechseln.
5. Einen DE- und einen US-Client separat starten. Autologin, Accountzuordnung, Fenstertitel und Spielzeiterfassung prüfen. Anschließend einen gemeinsamen Start testen.
6. Unter **Einstellungen → Launcher & Regionen → DE · Spielsprache** zunächst **English (US)** wählen: DE muss ohne `-A` starten. Anschließend **Deutsch** wählen: derselbe Server muss mit `-A de` starten. Andere Regionen/Sprachen entsprechend testen. Die Startauswahl und Quicklaunch erlauben eine einmalige abweichende Sprache; der gespeicherte Profilwert bleibt erhalten.
7. Quicklaunch mit der ausdrücklich gewählten Region und Spielsprache testen. Im Instanzbereich Fokussieren, Anordnen und Zuordnen ausprobieren.
8. Die drei Desktop-Stile durchschalten, die Fensteraufteilung ändern, beenden und erneut starten. Daten, Theme und Aufteilung müssen erhalten bleiben.
9. F1 öffnen und nach einer Einstellung suchen. Sicherung über Datei → Profil sichern oder Strg+S erstellen.

Die automatischen Tests prüfen Datenhaltung, Navigation und den gepackten Windows-Start einschließlich EXE-Austausch. Eine erfolgreiche Anmeldung an den aktuell installierten DE-/US-Spielclients kann nur mit diesen Clients geprüft werden. Nach Spielupdates können sich Loginmuster ändern.

## Fensterverwaltung in Beta 5

1. **Launch → Laufende Instanzen → Anordnen …** öffnen, die betroffenen Fenster ankreuzen und ihre Reihenfolge per Drag & Drop bestimmen. Der erste Client wird zum Hauptfenster.
2. Einen Zielmonitor oder **Alle Monitore** wählen. Raster, Hauptfenster links/rechts/oben, Kaskade und Monitor füllen ausprobieren. Abstand, Bildschirmrand, Taskleistenfläche und Hauptfensteranteil prüfen.
3. In der Vorschau ein Fenster ziehen oder unten rechts skalieren. Alternativ unter **Eigene Position und Größe** X/Y und Maße eingeben. Negative Koordinaten sind bei Monitoren links/oberhalb korrekt. Bis **Anwenden** muss das echte Spielfenster unverändert bleiben.
4. **Rahmenlos**, **Mit Rahmen** und **Immer im Vordergrund** prüfen. **Spielbereich** soll die gewünschte Windows-Clientfläche ohne Rahmen liefern; das Außenmaß enthält den Rahmen. Über **Zielmonitor rahmenlos füllen** lässt sich ein rahmenloses Vollbild vorbereiten; Taskleistenfreigabe entsprechend wählen.
5. **Letzte Änderung rückgängig** und **Originalzustand wiederherstellen** testen, auch nach einem Launcher-Neustart bei weiterlaufendem Spiel. Nach dem Beenden eines Clients darf eine wiederverwendete Prozess-/Fenster-ID nicht verändert werden.
6. Ein Fensterprofil speichern und neu laden. Fehlende Accounts müssen ausgelassen werden. Account-Startvorgaben speichern und den betreffenden Client neu starten; Position, Größe, Rahmen und Vordergrund müssen übernommen werden. Eine Startvorgabe lässt sich schon vor dem Start über **Fenster …** beim Account bearbeiten.
7. Per Rechtsklick in **Laufende Instanzen** minimieren, maximieren, wiederherstellen und Rahmen wechseln. Auf mehreren Monitoren verschiedene Windows-Skalierungen sowie eine geänderte Monitoranordnung testen.

Wizard101 im **Fenstermodus** verwenden. Die interne Renderauflösung und die Kamera werden von dieser Funktion nicht erzwungen. Bei gestrecktem Bild oder versetzten Klicks eine zur Fenstergröße passende Auflösung im Spiel wählen. Im F1-Hilfebereich **Spielfenster anordnen** stehen Erklärungen und Beispiele.

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

## Wenn Autologin fehlschlägt

Die Meldung enthält einen festen Fehlercode, aber keine Zugangsdaten. `permission` bedeutet fehlenden Prozesszugriff: Spiel und Launcher mit denselben Windows-Berechtigungen starten. `initializing`/`module` kann auf langsamen PCs eine längere **Autologin: Initialisierung abwarten**-Zeit benötigen. `login_missing` oder `hook_missing` nach Ablauf der Wartezeit deutet auf ein inkompatibles Clientmuster hin. Mehrdeutige Treffer werden als `login_ambiguous`/`hook_ambiguous` getrennt gemeldet und führen zu keinem Login. `hook_timeout` wird nicht automatisch wiederholt, damit derselbe Login nicht mehrfach gesendet wird.

Bei einem Fehler bleiben die manuellen Eingaben im Client verfügbar. Zum Eingrenzen reichen Fehlercode, Serverregion und Spielsprache; Zugangsdaten gehören nicht in einen Fehlerbericht.
