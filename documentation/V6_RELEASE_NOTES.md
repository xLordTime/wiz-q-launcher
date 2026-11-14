## Wiz Q Launcher 6.0.2

**Hotfix für die Cloud-Synchronisierung.** Die Verknüpfung bleibt gespeichert, wenn der Cloud-Dienst den ersten Profilstand noch überträgt. Sobald ein gültiger Profilstand verfügbar ist, setzt der Launcher den Abgleich fort. Accounts, Spielzeit und Einstellungen werden auch übernommen, wenn einzelne Aufnahmen oder andere Dateien noch ausstehen.

1. Auf PC A unter **Addons → Cloud-Synchronisierung** beim bestehenden Profil **Jetzt abgleichen** wählen. **Cloud-Ordner öffnen** führt zu den verschlüsselten Dateien. Über **Ordner wechseln** lässt sich der Speicherort mit demselben Schlüssel ändern.
2. Den Ordner **WizQ Cloud** vom Cloud-Dienst übertragen lassen. Auf PC B unter **Gerät verbinden** entweder diesen Ordner oder seinen übergeordneten Ordner wählen und den bisherigen Cloud-Schlüssel eingeben.
3. Die Statusmeldung zeigt die Zahl der Accounts und ob der Launcher den Profilstand in den Ordner geschrieben hat. Den PC-übergreifenden Upload und Download übernimmt der Cloud-Dienst.

Bei entsperrtem Tresor und aktivierter Automatik prüft der Launcher alle 30 Sekunden erneut. Cloud-Profile und Schlüssel aus 6.0.1 bleiben verwendbar.

Das Update verwendet das vorhandene lokale 6.0-Profil. Unter **Einstellungen → Updates** im Kanal **stable** nach Updates suchen, herunterladen und **Neustarten & anwenden** wählen.

Windows-EXE, Testanleitung und SHA-256-Prüfsumme stehen unter Assets.
