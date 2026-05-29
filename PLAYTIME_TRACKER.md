## 🎮 Playtime Tracker v5.2.0 - Neue Features

Ihr Launcher verfügt jetzt über einen umfassenden **Playtime Tracking System**!

### **Was wird getrackt?**

#### **Pro Account:**
- ⏱️ **Total Playtime**: Gesamte Spielzeit in Stunden:Minuten
- 📊 **Sessions Count**: Anzahl der aktuellen Spielsessions
- ⌚ **Average Session**: Durchschnittliche Sessson-Dauer
- 🕐 **Last Session Start**: Zeitstempel des letzten Sessson-Starts

#### **Account-Erweiterung:**
```python
Account(
    name, username, password,
    total_playtime: float,        # Sekunden
    sessions_count: int,          # Anzahl
    last_session_start: float,    # Zeitstempel
    last_used: float              # zuletzt verwendet
)
```

---

### **🎯 Neue UI Features**

#### **Stats Tab** (Neue Tab in der Anwendung)
Zeigt eine **Tabelle aller Accounts** mit:

| Column | Inhalt |
|--------|--------|
| Account | Kontoname |
| Total Playtime | z.B. "1h 30m" |
| Sessions | Anzahl der Sessions |
| Avg Session | Durchschnittliche Sessson-Länge |

**Buttons im Stats-Tab:**
- 🔄 **Refresh** - Aktualisiert die Statistiken
- 💾 **Export Stats** - Speichert Statistiken als `playtime_stats.txt`
- 🗑️ **Reset All Stats** - Löscht alle Playtime-Daten (mit Bestätigung)

---

### **⚙️ Wie funktioniert Tracking?**

#### **Automatisches Tracking:**
1. Klick auf **"Start + Auto Login"** startet Tracking
2. Playtime-Tracking beginnt automatisch für jedes Account
3. Wenn Instanz schließt → **Sessionsdauer wird gemessen und gespeichert**
4. Account wird aktualsiert: `total_playtime += session_duration`

#### **Tracking-Logik:**
- `tracker.start_session(handle, username)` - Session startet
- `tracker.track_session_end(handle, account)` - Session endet, Daten werden gespeichert
- Alle 1 Sekunde: Check für geschlossene Instances → Sessions automatisch beenden
- Beim App-Close: Alle aktiven Sessions werden beendet und Account-Daten gespeichert

---

### **📂 Neue/Geänderte Dateien**

| Datei | Änderungen |
|-------|-----------|
| `playtime_tracker.py` | 🆕 Neue Modul |
| `crypto.py` | ✏️ Account-Klasse erweitert um Playtime-Felder |
| `ui.py` | ✏️ Stats-Tab hinzugefügt, PlaytimeTracker-Import |
| `launcher.py` | ✏️ Helper-Funktionen für Session-Tracking |
| `main.py` | ✏️ Event-Handler für Stats, Session-Polling, Cleanup |

---

### **🎮 Workflow Beispiel**

```
1. App öffnet → Tracker initialisiert
2. Klick "Start + Auto Login" mit 2 Accounts ausgewählt
   ├─ Accounts starten
   ├─ Tracking aktiv: Handle 1234 = "Account1"
   ├─ Tracking aktiv: Handle 5678 = "Account2"
3. Spieler spielen...
4. Nach 1 Stunde: Spieler beenden App → App erkennt geschlossene Handles
5. Handle 1234 → Session 3600 Sekunden (1 Stunde)
   ├─ Account1.total_playtime += 3600
   ├─ Account1.sessions_count += 1
6. Handle 5678 → Session 2700 Sekunden (45 Minuten)
   └─ Account2.total_playtime += 2700
   └─ Account2.sessions_count += 1
7. App speichert aktualisierte Accounts in accounts.enc.json
8. Nächster App-Start → Stats werden korrekt angezeigt
```

---

### **📊 Daten-Persistenz**

Playtime-Daten werden in **accounts.enc.json** gespeichert:
```json
{
  "name": "MyAccount",
  "username": "player1",
  "password": "...",
  "total_playtime": 3661.5,     ← Neu!
  "sessions_count": 5,          ← Neu!
  "last_session_start": 1707930000.0,  ← Neu!
  "last_used": 1707930000.0
}
```

Zahlen sind **verschlüsselt** wie alle anderen Account-Daten.

---

### **⏲️ Timing-Details**

- **Poll-Interval**: Alle 1 Sekunde wird überprüft ob Instanzen noch aktiv sind
- **Export**: Sichert Stats ins Textformat (lesbare Statistiken)
- **Reset**: Mit Bestätigung um Datenverlust zu vermeiden
- **Auto-Save**: Beim App-Close werden alle Sessions beendet und gespeichert

---

### **🧪 Test**

Playtime-Tracker wurde mit Test-Accounts verifiziert:
```
✓ Playtime Tracker Works!
  Test2: 2h 2m (10 sessions)
  Test1: 1h 1m (5 sessions)
```

---

**Status**: Playtime Tracker vollständig implementiert und getestet ✅

