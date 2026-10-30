# Wiz Q Launcher 6.0 — Neuaufbau und Release-Plan

Stand: 30.10.2026. Arbeitsbranch: `Version-6.0`.
Status: Spezifikation und Architekturentwurf; die folgenden Funktionen sind noch nicht implementiert.
Anforderungen stammen aus der gemeinsamen 6.0-Planung. Technische Entscheidungen sind als Arbeitsgrundlage festgehalten und werden durch die unten genannten Prüfungen abgesichert.

## 1. Produktziel und verbindlicher Umfang

Vollständiger Neuaufbau mit Python und PySide6. Die Anwendung soll sich durchgängig modern, reaktionsschnell und verständlich bedienen lassen und auch auf älteren Windows-PCs mit reduzierten Effekten gut funktionieren.

6.0 bleibt ein Update desselben Produkts im selben Repository. Bestehende Nutzer behalten ihre Accounts und vorhandenen Statistiken; geeignete Einstellungen werden übernommen. Die Anwendung braucht weder eine neue Online-Registrierung noch eine Cloud für Zugangsdaten.

Pflichtumfang:
- Launch, Account Management, Playtime, Addons, Einstellungen und Help.
- Quicklaunch mit und ohne Autologin, mehrere Instanzen, Server-/Regionswahl.
- Accounts mit Nickname, Username und Password; Gruppen, Suche, Filter und Drag & Drop.
- PySide6-Widgets, konsistente Buttons, Dropdowns, Menüs und sanfte Übergänge.
- Überarbeitete Speicherung, Verschlüsselung, Wiederherstellung und Updates.
- Addon-System, Entwicklerdokumentation und drei mitgelieferte Addons: Stat Monitor, Clips and Record, Theme Creator.
- Genau 20 eigenständige mitgelieferte Themes, darunter schlichte und animierte Designs.
- Übernahme der bisherigen Discord Rich Presence einschließlich Yield-to-game und optionaler Webhook-Funktionen.
- Erststart-Tutorial und offline verfügbare, durchsuchbare Hilfe.

## 2. Kompatibilität: normales Update und vorhandene Daten

### Geprüfter Ausgangspunkt
Wiz Q Launcher: `bf3759d89bdd4682f09df9999792d8c930c5b7a7`, Version 5.5.1.
Deimos: `99194d7d053b011f2db36bcc2d2bf6635acb7d7e`.

5.5.1 verwendet bereits:
- `%LOCALAPPDATA%/WizQLauncher/config.json`
- `%LOCALAPPDATA%/WizQLauncher/data/accounts.enc.json`
- `%LOCALAPPDATA%/WizQLauncher/data/activity_24h.json`
- `logs/` und `backups/` im selben Profil.
Zusätzlich existiert eine Migration aus dem alten Ordner neben der EXE.

Der Release-Workflow erzeugt `WizQLauncher-v<VERSION>.exe`. Der alte Updater fragt GitHub Releases/latest ab und wählt die erste EXE im Release.

### Release-Vertrag
- Repository und Produktidentität beibehalten.
- 6.0 weiter als vollständige Windows-EXE im bisherigen Namensschema anbieten, inklusive aller zur Ausführung nötigen Komponenten. Kein separat zu installierendes Python oder Rust.
- Im Stable-Release darf die erste bzw. einzige oberste EXE kein isolierter Helper oder unvollständiger Installer sein.
- Der neue Updater wählt Assets explizit nach Produkt, Plattform und Paketformat, nicht nach Listenreihenfolge.
- Beta/RC als Prerelease; normale Altinstallationen erhalten keine ungeprüfte 6.0-Beta.
- Branch-Pushes veröffentlichen kein Stable-Release. Veröffentlichung erst nach den Freigabekriterien.
- Nutzerdaten bleiben getrennt von Programmdateien und werden durch den EXE-Austausch nicht entfernt.

### Wichtige Grenze beim Übergang
Der bereits ausgelieferte 5.5.1-Updater schreibt sein Batchskript mit ASCII, enthält darin aber einen Gedankenstrich. Das verhindert den automatischen Austausch. Eine neue 6.0-EXE kann diesen Fehler in einer bereits laufenden alten EXE nicht rückwirkend reparieren.

Für funktionierende ältere Updater bleibt der normale Download-/Neustartpfad erhalten. Für betroffene 5.5.1-Installationen wird das einmalige Starten der heruntergeladenen vollständigen 6.0-EXE dokumentiert und getestet. Ein vorgeschaltetes 5.5.x-Reparaturrelease ist möglich, kann aber denselben erstmaligen manuellen Start nicht grundsätzlich vermeiden. Es wird kein fehlerfreier vollautomatischer Direktwechsel aus jeder unveränderten Altversion versprochen.

### Migration
1. Alte Anwendung/Schreibzugriffe beenden; Profilsperre für den Wechsel setzen.
2. Vorhandenes Profil und ggf. altes EXE-Verzeichnis erkennen. Nie wahllos andere Benutzerordner durchsuchen.
3. Unveränderte Sicherung der Quelldateien samt vollständiger Dateiliste und Hashes anlegen. Geheimnisse bleiben verschlüsselt.
4. Alte Daten lesen und anhand bekannter Formate validieren. Veraltete Klartext-Listen nur als Migrationseingabe lesen, nie erneut im Klartext speichern.
5. Alten Tresor mit bisherigem Masterpasswort, vorhandenem DPAPI-Schlüssel oder dem erkannten alten Placeholder-Modus öffnen. Falsches Passwort bedeutet Abbruch/erneute Eingabe, kein Reset.
6. In eine neue, getrennte 6.0-Datenbank importieren und Zugangsdaten neu verschlüsseln.
7. Accountanzahl, Zuordnung und sämtliche vorhandenen Statistikwerte mit der Quelle vergleichen.
8. Migration und Aktivierungsmarker konsistent abschließen; bei Neustart idempotent fortsetzen, keine doppelten Summen.
9. Ergebnis anzeigen: übernommen, angepasst, nicht übertragbar und Grund. Quellen nicht löschen.

Ein gesperrter Tresor darf nicht als leere Accountliste übernommen werden. Bei Konflikten zwischen AppData und altem EXE-Verzeichnis nicht blind überschreiben; Herkunft und Konflikt sichtbar machen.

| Alter Wert | Verhalten in 6.0 |
| --- | --- |
| Accountname, Username, Passwort, Region | Übernahme in stabile Account-ID; Nicknames bleiben frei änderbar |
| total_playtime | Unveränderte historische Basissumme in Sekunden |
| sessions_count | Unveränderte historische Sitzungsanzahl |
| last_used, last_session_start | Erhalten, aber nicht als Beweis einer weiterhin laufenden Sitzung behandeln |
| activity_24h intervals | Gültige Intervalle übernehmen; verwaiste offene Intervalle nicht bis zum nächsten Start aufblähen |
| Region, Server, Port, Installationspfade | Validieren und übernehmen; nicht automatisch durch US-Standardwerte ersetzen |
| Sprache, Shortcuts, Fensterlayout | Übernehmen, soweit kompatibel; ungültige Monitorpositionen korrigieren |
| Discord-Einstellungen | Übernehmen; Webhook-URL im neuen Secret Store schützen |
| Altes Theme | Auf ein passendes 6.0-Theme abbilden; Originalwerte in Sicherung erhalten |
| Alte UI-Flags / nicht unterstützte Optionen | Protokolliert auslassen, ohne andere Daten zu verwerfen |

Historische Summen enthalten keine nachträglich rekonstruierbare Tageshistorie. Alte Summen und neue Einzelsitzungen werden getrennt gespeichert und nur einmal zusammengerechnet. Migrationstests brauchen echte Format-Fixtures der unterstützten Altversionen; 5.5.1 ist der erste bestätigte Ausgangspunkt.

## 3. Oberfläche und Navigation

Basis: PySide6 / Qt Widgets, Model/View für Accountlisten und Drag & Drop, eigener kleiner Satz wiederverwendbarer Controls, SVG-Icons. Qt-eigene Animationen statt zahlreicher UI-Frameworks. Kein Webbrowser-Renderer als Pflichtkomponente.

- Linke Navigation, auf kleinen Fenstern einklappbar.
- Oben Seitentitel und relevante Aktionen; unten unaufdringlicher Status für Speichern, Update und laufende Instanzen.
- Tastaturbedienung, deutliche Fokusrahmen, skalierbare Schrift, High-DPI und Screenreader-Namen.
- Einheitliche Suchfelder, Dialoge, Toasts, leere Zustände und Fehlerkarten mit konkreter Lösung.
- Dialoge erhalten sichtbare Lade-/Abbruchzustände; keine scheinbar eingefrorenen Buttons.
- Microanimations ca. 120–180 ms, Seitenwechsel ca. 180–240 ms, ohne Aktionen künstlich zu verzögern.
- Alle Animationen abschaltbar; reduzierte Windows-Bewegungseinstellungen beachten.
- UI-Arbeit nur im GUI-Thread; Launch, Datenzugriffe, Aufnahme und Netzverkehr über Worker mit Qt-Signalen.
- Deutsch und Englisch von Anfang an über gemeinsame Übersetzungsschlüssel.

### Launch
- Auswahl per Checkbox; Accounts nach Region und Gruppe filterbar.
- Favoriten, letzte Auswahl und gespeicherte Startprofile.
- Zwei klare Aktionen: ausgewählte Accounts mit Autologin starten; leere Instanz(en) ohne gespeicherte Zugangsdaten öffnen.
- Region/Serverprofil explizit auswählbar; Accountregion und Installation müssen zusammenpassen.
- Bei gemischten Regionen Startaufträge je Profil aufteilen.
- Startwarteschlange mit anpassbarer Parallelität und Verzögerung für ältere PCs.
- Zustände: geplant, Installation prüfen, starten, Fenster suchen, anmelden, gestartet bzw. fehlgeschlagen. „Angemeldet“ nur bei belastbarer Bestätigung.
- Pro Instanz: Nickname, Region, Laufzeit, Fenster fokussieren und vorhandene Fensterverwaltungsfunktionen.
- Spielpatch und Launcherupdate getrennt benennen. Bei veraltetem Client klarer Weg zum unterstützten Spielpatcher.

### Account Management
- Nickname, Username und Passwort sowie Region/Serverprofil.
- Stabile UUID als Identität; Nickname ist kein Primärschlüssel.
- Gruppen mit Reihenfolge/Farbe, Favoriten, Suche und Filter.
- Drag & Drop innerhalb und zwischen Gruppen; Reihenfolge transaktional speichern.
- Mehrfachauswahl für Gruppenzuweisung und Sortierung.
- Passwort standardmäßig maskiert, Sichtbarkeit zeitlich begrenzt und nur nach Entsperren.
- Passwörter nicht trimmen oder normalisieren. Gleichnamige Usernames in verschiedenen Regionen zulassen.
- Standardansicht zeigt Nicknames; Accountdaten in Fehlermeldungen und Screenshots minimieren.

### Playtime
- Identität einer Sitzung: Session-UUID + Prozess-ID + Prozesserstellzeit + Account-ID + Region. HWND nur als wechselnde Fensterreferenz.
- PID direkt vom Startprozess übernehmen und passende Fenster über PID zuordnen; nicht nach Reihenfolge neuer Fenster raten.
- Externe Instanzen als „nicht zugeordnet“ zeigen; Zuordnung auf Wunsch. Kein Raten anhand ähnlich lautender Fenster.
- Laufzeit ohne Änderung des Spiels erfassen; kein Hook als Voraussetzung für Zeitmessung.
- Laufende Zeit mit geeigneter monotoner Zeitbasis bestimmen; Neustart-/Sleep-/Resume-Grenzen explizit behandeln.
- Heartbeat ca. alle 10 Sekunden transaktional sichern; nach Absturz höchstens bis zum letzten bestätigten Heartbeat abrechnen, nicht die Offlinezeit bis zum nächsten Start.
- Standard: erkannte Client-Laufzeit; nicht behaupten, AFK- oder reine Charakterspielzeit zu erkennen.
- Sitzungen, Gesamtsummen, Region-/Accountfilter und neue Tages-/Wochen-/Monatsansichten.
- Überlappende Accounts: Accountstunden getrennt; persönliche reale Spielzeit als Vereinigungsmenge der Zeitintervalle. Beide Kennzahlen verständlich beschriften.
- Wiederaufnahme und Sitzungsabschluss dürfen keine Zeiten doppelt addieren. Mehrere Instanzen desselben Accounts gesondert behandeln.
- CSV-Export der Statistik; kein Export von Zugangsdaten.

### Einstellungen
Untermenüs: Allgemein, Launcher & Regionen, Accounts & Sicherheit, Fenster & Shortcuts, Darstellung & Animationen, Playtime, Discord, Updates, Speicher & Sicherungen, Erweitert.
Der bisherige Region-Tab geht vollständig in „Launcher & Regionen“ auf: Pfade, automatische Erkennung, Regionssichtbarkeit, Server/Port, Startargumente und Validierung.
Suche führt direkt zur passenden Einstellung. Jede Option besitzt Erklärung, Standardwert und eine Hilfereferenz.
Fehler bei Speichern klar anzeigen; „Gespeichert“ erst nach erfolgreichem Commit.

### Help
Offline verfügbare Suche, Schnellstart, Glossar, Screenshots/Beispiele, Einstellungsreferenz und Fehlercodes.
Themen: jede Seite und Einstellung, Autologin, Regionen/US/DE, Installation, Gruppen, Fenster, Playtime, Discord, Addons, Themes, Update, Migration, Backup und Wiederherstellung.
Kontext-Hilfe öffnet direkt den Artikel zur aktuellen Einstellung.
Diagnosepaket nur auf bewussten Export; ohne Passwörter, Schlüssel und Webhook-URLs. Log-/Pfadredaktion prüfen.
Tutorial wiederholen, Speicherordner öffnen und Problembericht vorbereiten.
Hilfe und Einstellungsschema teilen stabile IDs; beim Build fehlende Hilfetexte prüfen.

### Erststart
Neuinstallation: Willkommen → Spielinstallationen/Regionen → Speicherschutz erklären → optional erster Account → Theme/Leistungsprofil → Launch erklären.
Überspringbar und später wiederholbar; keine erzwungenen Beispieldaten oder Onlineanmeldung.
Nach Update: zuerst Migration/Entsperrung, anschließend kurze Tour zu Änderungen. Kein erneutes komplettes Setup für bestehende Nutzer.

## 4. Datenablage, Absturzfestigkeit und Wiederherstellung

Profilwurzel bleibt `%LOCALAPPDATA%/WizQLauncher`, üblicherweise `C:/Users/<Username>/AppData/Local/WizQLauncher`. Pfad über Windows-/Umgebungsauflösung ermitteln, kein hart codierter Benutzername.

Geplante Ablage:
- `data/launcher-v6.sqlite3`: Konfiguration, Accounts, Gruppen, Startprofile, Sessions, Migrationen und verschlüsselte Secrets.
- `backups/`: geprüfte rollierende Sicherungen und unveränderte Migrationssicherung.
- `logs/`: begrenzte, bereinigte Logs.
- `themes/`, `addons/`, `recordings/`, `cache/`, `updates/`.
- Programmdateien und mitgelieferte statische Ressourcen bleiben vom Benutzerprofil getrennt. Explizite Exporte dürfen an einen gewählten Ort geschrieben werden.

### Schutz gegen beschädigte Einstellungen
1. SQLite-Transaktionen statt komplettes Überschreiben zentraler JSON-Dateien.
2. `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`; wirksame Werte beim Öffnen kontrollieren. Relevante Verbindungseinstellungen für jede Verbindung setzen.
3. Ein serialisierter Schreibdienst; kein ungeprüftes Zurückschreiben veralteter kompletter Konfigurationskopien. Profilsperre gegen parallel schreibende Launcherprozesse.
4. Gruppenänderungen, Accountdaten und Schlüsselmetadaten gemeinsam in Transaktionen ändern.
5. Validierung vor Commit; Fehler/volle Platte/keine Rechte behalten den letzten gültigen Stand und zeigen den Fehler an.
6. Regelmäßige konsistente Snapshots über SQLite Backup API, nicht über simples Kopieren einer aktiven DB ohne WAL.
7. Sicherung zunächst temporär erstellen, Integrität prüfen, danach aktivieren; begrenzte Rotation. Nie die letzte gute Sicherung vor dem erfolgreichen Ersatz entfernen.
8. `quick_check` beim Start, vollständiger Integritätscheck vor Migration/Wiederherstellung und in Wartungsfällen.
9. Bei Defekt Original samt zugehöriger WAL-Dateien sichern/quarantänisieren, dann letzte geprüfte Sicherung anbieten bzw. wiederherstellen. Wiederhergestellten Zeitpunkt und mögliche verlorene letzte Änderungen anzeigen.
10. Kleine austauschbare JSON-Dateien wie Theme-Exports mit QSaveFile ohne direkten Schreibfallback atomar ersetzen.
11. Keine automatische Umwandlung von Parse-/Entschlüsselungsfehlern in ein frisches leeres Profil.
12. Backupimport prüft vollständige Dateimenge, Größenlimits, Pfade und Hashes; keine unmanifestierten Zusatzdateien oder Archiveinträge außerhalb des Zielordners.

Ziel: Ein normaler Programmabsturz oder Stromausfall soll weder halbe Einstellungen noch ein durch Defaults überschriebenes Profil hinterlassen. Die Haltbarkeit setzt korrekt arbeitendes Dateisystem/Hardware voraus. Gegen physisch defekte Datenträger oder Verlust aller lokalen Kopien gibt es keine absolute Garantie; dafür Export einer geschützten Sicherung anbieten. Ein jüngster noch nicht bestätigter Speichervorgang/Heartbeat kann fehlen.

## 5. Sicherheit neu aufbauen

- Keine festen Ersatzpasswörter und keine neuen Placeholder-Dateien.
- Accounts und Zugangsdaten über getrennte APIs behandeln; UI-Listen bekommen nur notwendige Metadaten.
- Zufälliger Profilschlüssel; Secret-Felder mit authentifizierter Verschlüsselung (AES-GCM), je Schreibvorgang eindeutigem Nonce und gebundener Account-ID/Formatversion.
- Standard ohne Masterpasswort: Profilschlüssel durch DPAPI im aktuellen Windows-Benutzerkontext schützen, nicht mit machine-weitem Flag. Verschlüsselte Daten bleiben im AppData-Profil.
- Optionaler echter Masterpasswortmodus: Schlüssel mit passwortabgeleitetem Schlüssel schützen, z. B. scrypt mit zufälligem Salt und versionierten, überprüften Parametern. Kein stiller zusätzlicher DPAPI-Entsperrweg, der das Passwort umgeht.
- Passwortwechsel ändert Schlüsselhüllen atomar; Entschlüsselung der neuen Hülle vor Commit prüfen.
- Automatische Sperre und Session-Unlock; keine ewige unbemerkte Passwortzwischenspeicherung.
- DPAPI-Profilkopien sind nicht automatisch auf anderen PCs nutzbar; für Umzug passwortgeschützten Export anbieten. Exportformat mit KDF-Parametern und Integritätsschutz dokumentieren.
- Secrets nicht in Logs, Crashpakete, CLI-Argumente, URLs, Zwischenablage oder Addon-Events schreiben.
- Masterpasswortverlust nicht durch einen vermeintlich datenrettenden Reset verschleiern. Originaltresor bleibt erhalten.
- Python kann vollständige Löschung aller Klartextkopien aus dem RAM nicht garantieren. Secrets nur kurz halten; native Login-Schnittstelle erhält nur den benötigten Account.
- DPAPI ist kein Schutz vor Schadsoftware mit bereits laufenden Rechten desselben Windows-Benutzers.
- Normale Nutzung ohne Administratorrechte; Sonderrechte nur für tatsächlich benötigte Funktionen.

## 6. Launcher-Backend, Deimos und wizwalker

Deimos enthält unter `libs/wizlaunch` eine Rust-/PyO3-Bibliothek. `launcher.rs` startet den Client mit konfigurierbarem Loginserver und liefert eine PID. `python.rs` stellt Start-/Loginfunktionen bereit; der Multi-Launch ordnet Fenster über PID zu. Der Standardserver dort ist US.

`login.rs` nutzt Pattern-Scanning und einen temporären Login-Hook mit Zugriff auf Spielspeicher. Das ist nicht bloß Tastatureingabe oder Fenstererkennung. Regionen und Client-Builds können unterschiedliche Muster besitzen. Vor einer Zusage regionenübergreifenden Autologins ist eine echte Windows-Prüfung nötig.

Arbeitsentscheidung:
- Eigene Backend-Schnittstelle für Erkennen, Starten, Fensterzuordnung, Anmelden und Status.
- Deimos `wizlaunch` als Basis des nativen Start-/Login-Adapters untersuchen und gezielt übernehmen/anpassen; commitgenau pinnen.
- UI und Datenmodell bleiben unabhängig vom Backend.
- Das mitgelieferte Deimos-Credential- und JSON-Metadatenmodell nicht unverändert übernehmen: es passt weder zur eigenen zentralen Datenhaltung noch automatisch zu den gewünschten eigenen Passwortdialogen.
- Native Schnittstelle für eigene Account-UUIDs und den eigenen Secret Store definieren; keine Nutzung des fremden Deimos-Credential-Namensraums.
- Kein installiertes Deimos nötig und keine Übernahme seiner kompletten Automationsoberfläche.
- `wizwalker` ist für Start, HWND/PID-Zuordnung, Zeitmessung, Stat Monitor, Themes und Discord technisch nicht zwingend. Ziel: keine Pflichtabhängigkeit für den Core. Ob ein begrenzter Fallback sinnvoll bleibt, entscheidet der Backend-Prototyp.
- DE/EU-spezifische Argumente/Verhalten anhand der vorhandenen Implementierung bewahren und prüfen.
- Regionsprofil enthält Installation, Server, Port, Clienttyp, Startargumente und verfügbaren Autologin-Adapter.
- Zunächst Bestandsregionen DE, US, FR, IT, GB, PL, ES, GR als Migrationskandidaten. Aktuelle offizielle Verfügbarkeit und funktionierender Login separat verifizieren; ein alter Konfigurationseintrag ist kein Funktionsnachweis.
- Kein stiller Wechsel auf irgendeine andere Installation bei fehlendem Regionspfad.
- Bei unbekanntem Client-Build/fehlendem Muster kontrolliert abbrechen und Start ohne Autologin anbieten; keine unkontrollierten Patchversuche.
- Steam und Standalone getrennt behandeln; vorhandene Deimos-Steam-Logik nur nach eigenem Test als unterstützt ausweisen.
- Backendfehlverhalten darf die Oberfläche oder Datenbank nicht mit herunterziehen.

Deimos deklariert GPL-3.0-only, auch `wizlaunch` trägt eine GPL-Lizenz. Bei Codeübernahme müssen Lizenzkompatibilität, passende Lizenzierung des abgeleiteten Codes, vollständige Hinweise und Quellcodebereitstellung vor Auslieferung geklärt werden. Bestehende MIT-Urheberhinweise erhalten. Nicht einfach fremden GPL-Code unter die bisherige MIT-Kennzeichnung kopieren. Dieser Plan ändert noch keine Lizenzdateien.

## 7. Update-System ab 6.0

Sichtbarer Ablauf: Update gefunden → Hinweise lesen → herunterladen → prüfen → beim Neustart anwenden → Ergebnis.
- Downloads/Staging im AppData-Profil, ausreichend freien Platz und Rechte vorab prüfen.
- Manifest mit Version, Plattform, Paketformat, Größe, Hash und signierter Metadatenprüfung. Vertrauensschlüssel in der Anwendung; Hash allein beweist keine Herkunft.
- Release-Schlüsselverwaltung und sichere CI-Signierung sind Freigabearbeit, keine bereits vorhandene Infrastruktur. Ohne gültige Prüfung nicht still auf ungeprüftes Auto-Apply zurückfallen.
- Eigenen kleinen Update-Helper verwenden; wartet auf die konkrete alte Prozessidentität und prüft das Ende.
- EXE am bisherigen Startpfad ersetzen; bei anderem Datenträger zuerst eine geprüfte temporäre Kopie im Zielverzeichnis erstellen.
- Alte EXE als Rückfallkopie behalten; Dateisperren, Virenscanner, schreibgeschützte Ordner, Sonderzeichen im Pfad und unterbrochene Austausche behandeln.
- Austauschzustände persistent protokollieren und nach Neustart fortsetzen.
- Neuer Prozess meldet erfolgreiches Starten erst nach Datenprüfung, Migration und UI-Start.
- Fehlender Erfolgsnachweis führt zu angebotener/geprüfter Rückkehr; kein endloser Neustart.
- Programmrollback und Datenrollback gemeinsam planen: Vor-Schema-Snapshot behalten. Alte EXE nie unkontrolliert auf ein inkompatibles 6.0-Schema schreiben lassen.
- Nach bereits erfolgten 6.0-Nutzeränderungen Datenrollback nicht still ausführen, da dies Änderungen verlieren könnte.
- 6.0-Writes und Legacy-5.x-Dateien getrennt halten; nicht beide Formate dauerhaft synchron schreiben.

## 8. Addons und SDK

Addons-Tab: installiert, aktiviert/deaktiviert, Version, Kompatibilität, Status, Einstellungen und Dokumentation. Drei First-Party-Addons werden mitgeliefert; schwere Komponenten werden erst bei Benutzung geladen.

### Architekturentwurf für API v1
- Manifest: schema_version, id, name, version, api_version, entrypoint, min_launcher_version, capabilities und help_entry.
- Lifecycle: discover → validate → load → start → stop → unload. Stop muss Timer, Prozesse und Aufnahmen freigeben.
- Stabile IDs und Semver-Kompatibilitätsprüfung.
- Events z. B. session.started, session.ended, theme.changed; nie Zugangsdaten.
- Host stellt registrierte Aktionen, bereinigte Sitzungsmetadaten, namespacegebundene Konfiguration und UI-Beschreibungen bereit.
- Eigener Datenbereich pro Addon unter AppData. Schreiben der Konfiguration über den transaktionalen Hostdienst.
- Worker für Aufnahme und aufwendige Messungen in separaten Prozessen, begrenzte IPC-Nachrichten und Timeouts.
- Externe Worker dürfen deklarative UI-Modelle liefern; direkte native Qt-Widgets nur für überprüfte integrierte Module.
- Drittanbieter-Code nicht automatisch ausführen oder bei Programmstart nachladen; Herkunft/Version anzeigen und bewusste Aktivierung.
- Ein Python-Plugin oder separater Prozess ist keine echte Sicherheitssandbox. Deklarierte Fähigkeiten beschränken die Host-API, aber nicht automatisch die Windows-Rechte fremden Codes. Keine anderslautende Sicherheitszusage.
- Fehlerhafte Addons deaktivieren; Start im Safe Mode ohne Addons und benutzerdefinierte Themes.
- Kein stilles pip install oder Download fremder EXEs während des normalen Starts.

### Dokumentationslieferumfang
Zum implementierten SDK gehören:
1. Schnellstart mit einer minimalen lauffähigen Beispiel-Erweiterung.
2. Manifest-/Schemaspezifikation.
3. Lifecycle, Worker-/GUI-Thread-Regeln und IPC-Protokoll.
4. Referenz der Host-API, Events und Fehlercodes.
5. Konfiguration, eigene Einstellungsseiten, Hilfeeinbindung und Migration.
6. Paketierung/Installation, Versionskompatibilität und Debugging.
7. Grenzen von Vertrauen/Isolation und Umgang mit personenbezogenen Daten.
8. Beispiele: Statistik-Kachel, Session-Event und eigenes Theme.
Diese Dokumente dürfen APIs erst dann als nutzbar beschreiben, wenn die Implementierung und Beispiele geprüft sind.

### Stat Monitor
CPU-Auslastung, RAM, Datenträger und verfügbare GPU-Metriken; optional je Spielprozess.
psutil als Basis, GPU-/Sensordaten über gesonderte geprüfte Adapter. Nicht verfügbare Temperaturen/Sensoren als „nicht verfügbar“, nicht als 0 anzeigen.
Kleine Kurven/Kacheln, anpassbares Abfrageintervall, begrenzter Verlauf; keine schnellen Sensorabfragen im Idle.
Keine verpflichtenden Hintergrunddienste oder Adminrechte nur für eine leere Temperaturanzeige.

### Clips and Record
Fensterwahl, Screenshot, Aufnahme, Replay-Clip, Hotkeys, Zielqualität, FPS, Dauer und Speicherlimit.
Fensteraufnahme mit kontrolliertem Encoder-Worker; Hardwareencoding nur bei Verfügbarkeit, Softwarefallback mit niedrigeren Profilen.
Begrenzter komprimierter Ringpuffer bzw. kurze kodierte Segmente auf Disk statt unbeschränkter unkomprimierter Frame-Liste im RAM.
Clipgrenzen an Keyframes/Segmenten sauber behandeln; Teildateien nach Absturz erkennbar/reparierbar halten.
Speicherplatzkontrolle, Quoten und klare Fehlermeldung bei vollem Datenträger.
Stop/Disable gibt Puffer und Worker frei. Audioquelle explizit wählbar, Mikrofon standardmäßig aus.
Aufnahme ist optional und startet nie unbemerkt. Encoderpakete, Lizenzen und Bezugsquelle prüfen/pinnen.

### Theme Creator
Live-Vorschau für echte Beispiel-Controls, Farben, Typografie, Radien, Abstände, Hintergründe, Icons und Bewegung.
Theme-Datei als validiertes Datenformat, ohne ausführbaren Python-/JavaScript-Code.
Kontrastwarnungen, Restore/Undo, Duplizieren, Import und Export; beschädigtes Theme fällt auf sicheres Standardtheme zurück.
Animationen nur aus erlaubten, ressourcenbegrenzten Presets. Eigene Assets mit Größenlimits und sicheren Pfaden.
Theme Creator bearbeitet dieselben Tokens wie die mitgelieferten Themes; keine zweite inkompatible Engine.

## 9. Genau 20 mitgelieferte Themes

Eigene Komposition, Typografie, Oberflächenstruktur und Akzentbehandlung je Theme; keine bloßen Farbkopien. Einheitliche Bedienlogik und Layout-Mindestmaße bleiben erhalten.

| Nr. | Theme | Charakter | Bewegung |
| --- | --- | --- | --- |
| 1 | Obsidian | Tiefschwarz, klare Flächen, violetter Fokus | Nur Control-Übergänge |
| 2 | Porcelain | Helles Weiß, feine Linien, königsblauer Akzent | Nur Control-Übergänge |
| 3 | Graphite Pro | Kompakte anthrazitfarbene Werkzeugoberfläche, Orange | Nur Control-Übergänge |
| 4 | Midnight Blue | Dunkles Marineblau, kühle abgesetzte Karten | Nur Control-Übergänge |
| 5 | Sandstone | Warme Papierflächen, Terrakotta, weiche Ecken | Nur Control-Übergänge |
| 6 | Forest Desk | Dunkles Waldgrün, Creme und dezentes Kupfer | Nur Control-Übergänge |
| 7 | Nordic Frost | Eisweiß, graublau, großzügige Abstände | Nur Control-Übergänge |
| 8 | Rose Quartz | Helles Rosé, Pflaume, sanfte abgerundete Panels | Nur Control-Übergänge |
| 9 | Solar Contrast | Sehr klare dunkle Flächen, Gelb, kräftige Fokusrahmen | Statisch, keine dekorative Bewegung |
| 10 | E-Ink | Graustufen, typografisch, ohne Schatten/Transparenz | Vollständig statisch |
| 11 | Mythic Explorers | Midnight Blue, Deep Violet, Antique Gold, Kompass und Runen | Langsamer Nebel und vereinzelte Runenimpulse |
| 12 | Arcane Observatory | Dunkles Pergament, Messing, Sternwarte | Behutsam rotierende Astrolabiumringe |
| 13 | Aurora Drift | Polarnacht mit Teal-/Violett-Lichtbändern | Begrenzte langsame Farbbandbewegung |
| 14 | Emberforge | Kohle, Bronze, glühende Linien | Wenige Funken in Randbereichen |
| 15 | Ocean Depths | Tiefseeblau, leuchtende Konturen, organische Formen | Dezente Lichtwellen |
| 16 | Neon Circuit | Dunkles Raster, Cyan/Magenta, technische Typografie | Seltene wandernde Leiterbahnimpulse |
| 17 | Clockwork Brass | Messing, dunkles Braun, gravierte Instrumente | Langsame dekorative Zahnräder |
| 18 | Sakura Breeze | Creme, Tintenlinien, Kirschblütenrosa | Vereinzelte Blütenblätter |
| 19 | Desert Mirage | Dunkles Indigo, Sandgold, geometrische Bögen | Langsame Hintergrundverläufe |
| 20 | Celestial Atlas | Sternkarten, Silber, tiefes kosmisches Blau | Sehr sparsame Sternkarten-Parallaxe |

Jedes animierte Theme erhält eine gestaltete statische Variante. Kontrast und Lesbarkeit haben Vorrang vor Effekten. Keine blinkenden Vollflächen oder Bewegung hinter Texteingaben.

## 10. Alte und neue PCs

Zielplattform zunächst Windows 10/11 x64, endgültige Mindestversion abhängig von der fest gepinnten Python-/PySide6-/Backend-Kombination und Windows-Buildtests. „Alle Geräte“ bedeutet im Projektumfang ältere und neue kompatible Windows-PCs, keine pauschale Zusage für Windows 7, 32 Bit, Mac, Linux oder ARM.

Drei Profile:
- Sparsam: statische Hintergründe, keine Transparenz-/Blur-Effekte, niedrige Abfrageraten, wenig parallele Starts.
- Ausgewogen: kurze Übergänge und begrenzte Themeneffekte.
- Effekte: animierte Designs mit begrenztem Effektbudget.

Minimiert/verdeckt dekorative Timer pausieren; deaktivierte Addons haben keine laufenden Poller. Core bleibt ohne GPU-Sensor- und Aufnahmebibliotheken startbar.
Listen effizient rendern; kein komplettes Neuzeichnen aller Accountkarten bei jedem Timer.
Ziele für den Prototyp, noch keine gemessenen Zusagen: Core-Idle auf dem Referenz-PC im Mittel unter 1 % CPU, ca. unter 200 MB RAM bei statischem Theme, sofortiges sichtbares Feedback auf Aktionen. Aufnahme/GPU-Addons separat messen.
Messmatrix: älterer 2-/4-Kern-PC, integrierte GPU, SSD/HDD, aktueller Gaming-PC; 1366×768, Full HD, 4K sowie 100/150/200-%-Skalierung.

## 11. Discord beibehalten

Vorhandene Module als Verhaltensreferenz:
- `integrations/discord_presence.py`
- `integrations/discord_integration.py`

Erhalten: optionales Rich Presence, Account-/Sitzungs-/Gesamtspielzeit, 24h-Aktivität, Updateintervall, Reconnect und Yield-to-game, damit Discord bei laufendem Wizard101 seine normale Spielerkennung zeigen kann.
Webhook-Funktionen bleiben optional mit ihren bisherigen Schaltern; automatisches Versenden ist deaktivierbar und im Erststart verständlich beschrieben.
Keine doppelten Benachrichtigungen bei Restart/Session-Recovery.
Nicknames/Statistik in Discord nur gemäß Nutzerwahl; niemals Passwort oder Token. Webhook-URLs im Secret Store.
Alte 24h-Fehlerbehandlung, die Offlinezeit nach einem Crash mitrechnet, nicht übernehmen.
Keine neue Discord-Anmeldung oder Bot-Hosting-Pflicht für lokale RPC.

## 12. Aufbau und Abhängigkeiten

Geplante Trennung:
- `src/app`: Start, Lifecycle, Dependency Wiring.
- `src/ui`: Shell, Seiten und wiederverwendbare Controls.
- `src/domain`: Accounts, Regionen, Sessions, Einstellungen, Events.
- `src/storage`: Datenbank, Migration, Backup und Recovery.
- `src/security`: Schlüsselverwaltung, Vault, Secret-Redaktion.
- `src/launcher`: Backend-Vertrag und native/windows-spezifische Adapter.
- `src/updates`: Releaseprüfung, Manifest, Staging, Apply/Recovery.
- `src/addons`: Host, API, IPC und Built-ins.
- `src/integrations`: Discord.
- `resources/themes`, `resources/help`, `examples/addons`.
- `tests/fixtures/legacy`: synthetische/sanitisierte Altprofile.

Basis: PySide6, sqlite3, cryptography, psutil, Windows-APIs und vorhandene Discord-Bibliothek.
PyQtGraph für Stat-Monitor-Kurven evaluieren; native Qt-Kurven reichen, falls die Zusatzlast nicht gerechtfertigt ist.
Keine Pflicht für PyQt6, Qt WebEngine oder mehrere parallele GUI-Frameworks.
Abhängigkeiten und Native-Quellen fest pinnen, Lockdatei und reproduzierbaren Windows-Build verwenden.
Lizenzinventar für Qt, Deimos, Icons, Encoder und alle eingebetteten Komponenten führen.

## 13. Reihenfolge und überprüfbare Ergebnisse

| Phase | Lieferung | Abnahme |
| --- | --- | --- |
| A — Kompatibilität | Legacy-Fixtures, Datenmodell, Migrations-/Release-Vertrag | Werteübernahme und Wiederholung ohne Duplikate nachgewiesen |
| B — Fundament | Speicher, Vault, Recovery, neues Updateprotokoll | Abbruch-/Fehlerfälle ohne leeres Überschreiben; alter Stand wiederherstellbar |
| C — Backend-Prototyp | Deimos-basierter Adapter, PID-Zuordnung, US/DE-Prüfmatrix | Tatsächlicher Start und geprüfter Login je freigegebenem Clientprofil |
| D — PySide6-Core | Launch, Accounts, Settings, Playtime, Fenster/Tray | Kompletter täglicher Ablauf samt Shortcuts ohne alte GUI |
| E — Bedienung | Tutorial, Help, Discord-Parität, Accessibility | Neu- und Updatepfad verständlich, Hilfelinks vollständig |
| F — Erweiterungen | Addon-API, drei Built-ins, 20 Themes, SDK-Beispiele | Stop/Fehler/Disable sauber, alle Themes lesbar und ressourcenbegrenzt |
| G — Beta und Release | Windows-EXE, Upgrade/Recovery-Matrix, Dokumentation | Alle Pflichtkriterien erfüllt, danach erst Stable 6.0 |

Alle genannten Features gehören zum 6.0-Zielumfang; die Phasen definieren die Entwicklungsreihenfolge, keine stillschweigende Streichung.

## 14. Freigabekriterien

- Upgrade mit Altprofil einschließlich echter Verschlüsselungsmodi; Wertevergleich der übernommenen Stats/Accounts.
- Migration nach erzwungenem Abbruch an jeder kritischen Stelle wiederholbar.
- Prozess während Speicherung, Passwortwechsel und Backup beenden: keine halben Datensätze, keine gelöschte letzte gute Kopie.
- Simulierte Dateisystemfehler: volle Platte, Rechteverlust, kaputte/abgeschnittene Dateien und fehlender Entschlüsselungsschlüssel.
- Unterschied zwischen Prozessabbruchtest und echtem VM-Hardreset/Power-Cut-Test dokumentieren; ersterer beweist keine vollständige Stromausfallfestigkeit.
- Aktive DB/WAL zusammen behandeln; Wiederherstellung aus geprüftem Backup testen.
- Updateabbruch vor/während Austausch, gesperrte EXE, Sonderzeichen im Pfad, ungültige Signatur/Hash und fehlgeschlagener Neustart.
- Programm- und Schema-Rollback einschließlich Grenzen bei späteren Nutzeränderungen.
- Mehrere gleichzeitige Starts ordnen Konten anhand der Prozessidentität korrekt zu.
- US/DE und jede weitere als unterstützt beworbene Region auf realem Windows/Client prüfen.
- Zeitmessung bei PID-/HWND-Wiederverwendung, Launcher-Neustart, Crash, Uhrzeitänderung, Suspend/Resume und parallelen Sitzungen.
- Alle 20 Themes bei kleiner/großer Skalierung; reduzierte Bewegung und Safe Mode.
- Addon-Crash, langsamer Worker, Stop/Disable, übergroße IPC-Nachricht und fehlerhafte Theme-/Addon-Pakete.
- Aufnahme unter Speicher-/CPU-Last und vollem Datenträger; Puffer nach Stop freigegeben.
- Keine Secrets in Logs, Diagnosen, Startargumenten oder Addon-Events.
- Windows-EXE aus sauberer Umgebung ohne Entwicklertools lauffähig.
- Keine Releasefreigabe allein auf Basis syntaktischer Python-Tests oder einer Linux-Vorschau.

## 15. Referenzen für die Umsetzung

- [Bestandsquelle 5.5.1](https://github.com/xLordTime/wiz-q-launcher/tree/bf3759d89bdd4682f09df9999792d8c930c5b7a7)
- [Deimos-Pin](https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/99194d7d053b011f2db36bcc2d2bf6635acb7d7e)
- [Deimos wizlaunch](https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/99194d7d053b011f2db36bcc2d2bf6635acb7d7e/libs/wizlaunch)
- [Qt QPropertyAnimation](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QPropertyAnimation.html)
- [Qt QSaveFile](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSaveFile.html)
- [SQLite synchronous](https://sqlite.org/pragma.html#pragma_synchronous)
- [SQLite WAL](https://sqlite.org/wal.html)
- [SQLite Online Backup](https://sqlite.org/backup.html)
- [Microsoft DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
