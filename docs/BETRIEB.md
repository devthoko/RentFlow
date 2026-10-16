# RentFlow betreiben

RentFlow verwaltet einen Verleih mit Privatkunden. Jede Installation gehört einer Firma. B2B, XRechnung, Lagerbestände und Verfügbarkeitsplanung sind nicht Bestandteil dieser Version.

## Einrichtung und tägliche Arbeit

Nach der Installation /setup aufrufen und den vom Installer ausgegebenen Einrichtungsschlüssel verwenden. Er steht ebenfalls in /etc/rentflow/environment (nur root lesbar). Administrator, Firmenanschrift, Steuerdaten, Besteuerungsart und optionales Logo anlegen. Es gibt keine Standardpasswörter, Kunden oder Demoaufträge.

Unter Einstellungen den eigenen, fachlich geprüften Mietvertragstext hinterlegen, Mitarbeiter einrichten und optional SMTP/WebDAV verbinden. Die Vertragsvorlage ist absichtlich leer. Jeder Mitarbeiter erhält ein persönliches Konto; deaktivierte Konten und geänderte Passwörter verlieren ihre bisherigen Sitzungen.

Ein Auftrag führt durch Kunde, Event, Angebot, Mietvertrag, Rechnung, Packliste, Übergabe, Rücknahme sowie Kaution/Abschluss. Ein bestätigtes Dokument bleibt auch nach Änderungen an Stammdaten unverändert. Angebotsänderungen vor der Rechnung erfordern neue Unterschriften. Nach Rechnungsausstellung zuerst eine begründete Stornierung durchführen; erfasste Zahlungen vorher nachvollziehbar ausgleichen. Stornierung nach abgeschlossener Übergabe ist nicht vorgesehen; solche Sonderfälle müssen außerhalb dieses einfachen Mietablaufs fachlich geklärt werden.

Zahlungen nur nach tatsächlichem Eingang buchen. Teilzahlungen werden addiert; Kautionen zählen nicht zur Rechnung. Niemand kann die Zahlungssperre umgehen. Packlisten sind bereits vor Zahlung möglich. Die Übergabe benötigt eine Unterschrift; die Rücknahme benötigt keine. Einbehaltungen begründen und Rückzahlungen erst nach Geldfluss buchen.

## Server und Dienste

- Programm: /opt/rentflow, Systembenutzer rentflow
- Datenbank und Archivdateien: /var/lib/rentflow
- Konfiguration: /etc/rentflow/environment
- Dienste: rentflow.service, rentflow-worker.timer (alle 30 Sekunden), rentflow-backup.timer (täglich 03:15 Serverzeit)
- nginx: /etc/nginx/sites-available/rentflow; Uvicorn nur an 127.0.0.1:8000
- Diagnose: systemctl status rentflow; journalctl -u rentflow -u rentflow-worker
- Healthcheck: curl -fsS http://127.0.0.1/health

Die SQLite-Laufzeit liegt im Programmverzeichnis und wird über LD_LIBRARY_PATH geladen. Sie ersetzt keine Betriebssystembibliothek. Für manuelle Python-Wartung diesen Pfad ebenso setzen. Die Wartungsskripte übernehmen das.

HTTP ist für die abgeschottete DEV-/TEST-LXC vorgesehen. Vor Einsatz mit echten Daten außerhalb eines geschützten Netzes TLS am Reverse Proxy einrichten, RF_BASE_URL=https://... und RF_SECURE_COOKIE=1 setzen und den Dienst neu starten. nginx leitet nur von ihm gesetzte Proxy-Header weiter. Eine Domain und Zertifikate werden nicht vom Installer erfunden.

## E-Mail und WebDAV

SMTP benötigt STARTTLS oder TLS. Passwörter sind in der Datenbank mit einem aus RF_SECRET abgeleiteten Schlüssel verschlüsselt. Diesen Schlüssel separat sichern; nach Verlust lassen sich Zugangsdaten nicht wiederherstellen. Passwortfelder zeigen gespeicherte Geheimnisse nie an. Ein leeres Passwortfeld lässt den bisherigen Wert unverändert.

Versand erfolgt über eine lokale Warteschlange. Der Dokumentverlauf zeigt Empfänger, Version, Zeitpunkt und Status. „Erfolgreich“ bedeutet Annahme durch den SMTP-Server, keine garantierte Zustellung. Bei einem Verbindungsabbruch während der Übermittlung bleibt die Annahme unklar; vor einer manuellen Wiederholung Postausgang/Empfänger prüfen. Ein solcher Versand wird nicht automatisch wiederholt. Andere Fehler werden mit wachsendem Abstand bis zu fünfmal versucht.

WebDAV benötigt eine HTTPS-Adresse und Schreib-/Leserechte für einen Unterordner RentFlow. Zuerst wird immer lokal gespeichert. Archivdateien haben eindeutige Namen, werden mit If-None-Match: * übertragen und anschließend per SHA-256 verglichen. Bereits vorhandene abweichende Dateien werden nicht überschrieben. Bei Ausfällen bleibt das lokale Archiv vollständig benutzbar. Nach Einrichtung unter Einstellungen „Ausstehende Dateien synchronisieren“ ausführen.

## Backup

Befehl: sudo /opt/rentflow/backup.sh

Alternativ unter Einstellungen → Datensicherung. Sicherungen enthalten einen konsistenten SQLite-Snapshot, alle referenzierten Dokumente/Bilder, Prüfsummen und die benötigten Geheimnisse. Dateien liegen in /var/lib/rentflow/backups, mit restriktiven Zugriffsrechten. Die Datenbank wird über die SQLite-Backup-API kopiert; nicht einfach die laufende .sqlite3 ohne WAL-Datei kopieren.

Tägliche automatische Backups bleiben lokal erhalten. Es gibt bewusst keine automatische Löschung. Speicherplatz regelmäßig prüfen, Sicherungen verschlüsselt außerhalb des Servers ablegen und eine dokumentierte Aufbewahrungsstrategie umsetzen. WebDAV ersetzt kein vollständiges Backup.

## Wiederherstellung

1. Wartungsfenster ankündigen und das gewünschte Backup auswählen.
2. Befehl: sudo /opt/rentflow/restore.sh /absoluter/pfad/backup.tar.gz --confirm-replace
3. Das Skript prüft Archivpfade, Prüfsummen, referenzierte Dateien und Datenbankintegrität, stoppt Anwendung/Hintergrundjobs und erstellt eine aktuelle Sicherheitssicherung.
4. Der vorherige Datenbestand bleibt als /var/lib/rentflow.before-restore-<Zeitstempel> erhalten. Ein altes Backup überschreibt neuere Geschäftsvorgänge damit nicht unbemerkt.
5. Nach Wiederherstellung werden unterstützte Migrationen ausgeführt, Berechtigungen gesetzt und Dienste samt Healthcheck gestartet.
6. Zusätzlich Anmeldung, letzte Rechnungsnummern, Beispiel-PDF, Zahlungen und Versandwarteschlange fachlich prüfen. Im alten Datenbestand vorhandene neuere Vorgänge bewusst abgleichen. Nach Restore könnten früher bereits versandte Nachrichten im alten Stand noch als ausstehend erscheinen.

Das Backup enthält Geheimnisse, ist aber nicht selbst verschlüsselt. Nur berechtigten Administratoren zugänglich machen. Wiederherstellung mit einer passenden, mindestens gleich neuen Programmversion durchführen. Bei Fehlern hält das Skript an; es führt keinen automatischen Daten-Rollback aus.

## Updates

Befehl: sudo /opt/rentflow/upgrade.sh --version <veröffentlichte-neuere-Version>

Release-Hash prüfen, neue virtuelle Umgebung vorbereiten, Dienste stoppen, Backup erstellen, Programmstand wechseln, Migrationen ausführen und Healthcheck durchführen. Vorheriger Programmstand bleibt in /opt/rentflow-before-upgrade-<Zeitstempel>. Downgrades sind gesperrt. Ein fehlgeschlagenes Update verlangt eine bewusste Entscheidung zwischen Reparatur und geprüftem Restore; dadurch werden zwischenzeitliche Geschäftsdaten nicht automatisch zurückgesetzt.

Backups und alte Programmstände erst nach abgeschlossener Prüfung und nach der betrieblichen Aufbewahrungsregel entfernen. Die systemd-/nginx-Dateien sind vom Installer verwaltet; eigene TLS-Erweiterungen und Reverse-Proxy-Konfigurationen vor Updates separat sichern.
