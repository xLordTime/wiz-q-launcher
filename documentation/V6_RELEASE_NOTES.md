**Wiz Q Launcher 6.0.0-beta.5 – Fensterverwaltung**

- Neuer nativer Fensterdialog mit Monitorvorschau: Clients auswählen, sortieren, ziehen und skalieren. Erst **Anwenden** bewegt echte Fenster.
- Mehr Layouts: automatisches/eigenes Raster, 2×2, nebeneinander, untereinander, Hauptfenster links/rechts/oben, Kaskade und Monitor füllen. Monitorwahl, Verteilung über mehrere Monitore, Taskleistenbereich, Abstände, Ränder und Proportionen sind einstellbar.
- Eigene Positionen und Größen einschließlich negativer Bildschirmkoordinaten. Außenmaße und tatsächlicher Windows-Spielbereich sind getrennt; Größen-Presets bis 4K/Ultrawide, Zentrieren und rahmenloses Füllen.
- Vorhandenen Rahmen beibehalten, skalierbarer Rahmen oder rahmenlos. Optional immer im Vordergrund. Per Rechtsklick auf laufende Instanzen zusätzlich minimieren, maximieren, wiederherstellen und Rahmen wechseln.
- Benannte Fensterprofile und Account-Startvorgaben, die auch vor dem Spielstart bearbeitet werden können. Alte Positionen und Einstellungen bleiben lesbar. Nach einem Monitorwechsel werden unzugängliche Startpositionen zurückgeholt.
- Freigabe abgeschlossener Hintergrundaufträge korrigiert, um Abstürze beim Beenden zu vermeiden.
- Dauerhaft gesicherter Originalzustand und letzte Änderung zum Wiederherstellen. Prozessstartzeit sowie HWND/PID-Zuordnung schützen vor Zugriffen auf wiederverwendete Fenster. Fehlgeschlagene Anordnungen versuchen, vorherige Änderungen zurückzunehmen.

**Öffnen:** Launch → Laufende Instanzen → **Anordnen …** oder Extras → **Spielfenster anordnen**. Über **Fenster …** bei einem Account lässt sich seine Startvorgabe bearbeiten.

**Update:** Einstellungen → Updates → Kanal **beta** → Nach Updates suchen → Herunterladen → Neustarten & anwenden. Alternativ `WizQLauncher-v6.0.0-beta.5.exe` herunterladen und nach dem Beenden der alten Version starten. Das vorhandene lokale Profil wird weiterverwendet.

**Spielgrafik:** Die neuen Maße betreffen Windows-Fenster und Spielbereich. Interne Renderauflösung und Kamera-Aspekt-Hooks aus Deimos sind nicht enthalten; bei gestrecktem Bild oder versetzten Klicks eine passende Auflösung im Spiel wählen und den Fenstermodus verwenden. Rahmenlose Fenster werden über den Launcher-Editor skaliert.

Die Veröffentlichung erfolgt nach Python-/Qt-Tests, nativen Muster-Tests, realen Windows-Fensterprüfungen, EXE-Build und Start-/Updateprüfung mit Datenerhalt. DE-/US-Spielclients und gemischte Monitor-Skalierungen benötigen weiterhin Praxistests. Diese Version ist ein Prerelease.
