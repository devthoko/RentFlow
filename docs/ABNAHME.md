# Abnahmeprotokoll

Stand: 16.10.2026, Version 1.0.1. Alle hier aufgeführten ausführbaren Tests liefen direkt auf der gemeinsamen Ubuntu-26.04-LXC. Automatisierte Fachtests verwenden ausschließlich temporäre Datenbanken und Dateien.

## Fachregeln und Oberfläche

42 automatisierte Tests prüfen die 30 verlangten Pflichtfälle einschließlich:

- Kunden ohne Auftrag, neuer Auftrag, Fortsetzen und Eventvalidierung.
- Artikel, Pakete, freie Positionen, genaue Summen und eingefrorene Daten.
- Angebotsversionen, Pointer-Unterschrift im echten Chromium-Browser, PDF-Nachweise und erneute Unterschrift nach Änderung.
- Vertragsvorlagen, Rechnung, Teilzahlungen, Gegenbuchung und Storno.
- Zahlungssperre vor und nach Unterschrift, direkter API-Aufruf, Administrator und Mitarbeiter.
- Packliste bei offener Rechnung, parallele Rechnungs-/Zahlungsvorgänge und identische Protokollwiederholung.
- Tatsächliche Übergabemengen, Rücknahme ohne Signatur, Schäden/Fehlmengen und bestätigte Kosten.
- Getrennte Kaution, begründeter Einbehalt, tatsächliche Rückzahlung und Abschluss.
- Unveränderliche Datensätze, aktive PDF-Inhalte, Zugriffsrollen und CSRF.
- SMTP-Annahme, Anhänge, Fehler und unklarer Versand; wiederholte Versandaktionen.
- WebDAV-Ausfall, Existenzkonflikt, Prüfsummen und Schutz vor Überschreiben.
- Backup und Restore, zusätzliche Artikelbilder, Paketänderungen und Kleinunternehmer-Summen.

Chromium: Desktop 1440 px, Tablet 820 px und Mobilansicht 390 px; keine JavaScript-Ausnahmen oder horizontal überlaufende Seiten in den geprüften Ansichten. Helle und dunkle Oberfläche wurden als Screenshots geprüft.

Mehrseitige PDFs mit 40 Positionen und langem Vertragstext wurden erzeugt, per pypdf auf vollständigen Text geprüft und mit Poppler für die Sichtprüfung gerendert. Unterschriften bleiben auf ein konkretes Original mit Nummer, Version und SHA-256 bezogen.

## Betrieb und Installation

Isolierte Installation auf derselben LXC mit separatem Systembenutzer, Konfiguration, Diensten, Daten und Ports 18080/18081 erfolgreich. Update des Testarchivs von 0.1.0 auf 0.1.1 führte die echte Migration von 0002 auf 0003 aus. Bestehende Kundendaten blieben erhalten. Ein falscher Release-Hash wurde vor Ausführung abgewiesen. Backup und Restore über die ausgelieferten Shellskripte erfolgreich; die nach dem Backup erfassten Daten blieben im vorherigen Datenverzeichnis erhalten. Die DEV-Anwendung blieb erreichbar.

Die Python-Laufzeitabhängigkeiten wurden mit pip-audit geprüft: keine bekannten Schwachstellen zum Prüfzeitpunkt. Das ist keine umfassende Sicherheitszertifizierung. HTTP-Sicherheitsheader, lokale Ressourcen, verschlüsselte SMTP-/WebDAV-Passwörter und sichere Uploads werden ergänzend eingesetzt.

## Abnahme des veröffentlichten Installers

Der von GitHub heruntergeladene Bootstrap für 1.0.0-rc.2 wurde auf derselben LXC erneut mit separatem Benutzer, Diensten und Daten unter /opt/rentflow-final-test ausgeführt. Das durch das Manifest festgelegte Archiv des Commits 2fafe05de7f74078996049586d20c59fb1f521be wurde erfolgreich geprüft und installiert. Anschließend bestanden das simulierte Versionsupdate, der Restore sowie der Abruf eines per root erzeugten Backups durch den angemeldeten App-Administrator. Die DEV-Anwendung blieb unter Port 80 mit Version 1.0.0-rc.2 erreichbar. Sie enthält keine Testbenutzer oder Testaufträge.

## Freigabeumfang 1.0.0

Der Auftraggeber hat den zusätzlichen Deployment-Test ausdrücklich abgewählt. Die Freigabe stützt sich auf die Fach- und Browsertests sowie die bereits erfolgreichen isolierten Installations-, Update- und Wiederherstellungstests auf der vorhandenen LXC. Die folgenden historischen Versuche sind keine erfolgreiche Neuinstallationsabnahme.

Zusätzliche Absicherung: Bei parallelen Foto-Uploads bleibt das Übergabe-/Rücknahmeformular bis zum Ende aller laufenden Uploads gesperrt, auch gegen Absenden per Tastatur. Ein Chromium-Test prüft den Wettlauf, den Erhalt des ersten Fotos und die Freigabe mit Fehlermeldung nach einem fehlgeschlagenen zweiten Upload.


SMTP und WebDAV wurden mit kontrollierten Transportantworten und Fehlersimulation geprüft. Ein produktiver Mailserver und Nextcloud-Zugang wurden nicht angegeben; deren konkrete Erreichbarkeit/Anmeldung muss nach Konfiguration mit Testmail bzw. Synchronisierung geprüft werden.

## Versuch einer frischen Ubuntu-Umgebung am 16.10.2026

Nach Zustimmung wurde Ubuntu 26.04 per debootstrap aus dem offiziellen Ubuntu-Archiv in einer temporaeren Umgebung neu installiert. Der verschachtelte systemd-nspawn-Start scheiterte beim Mounten von /proc (Operation not permitted). Der vorgeschlagene Start ohne private Benutzerzuordnung wurde von der automatischen Freigabepruefung abgelehnt und nicht ausgefuehrt. Der veroeffentlichte RentFlow-Installer konnte deshalb in dieser Umgebung noch nicht gestartet werden; dies ist keine erfolgreiche Neuinstallationsabnahme.

Die temporaere Rootfs, die eigene NAT-Tabelle und das veth-Paar wurden entfernt. IPv4-Forwarding wurde auf den vorherigen Wert 0 zurueckgesetzt. Der bestehende Dienst meldete danach health=ok, Version 1.0.0-rc.2. Die stabile Freigabe bleibt offen.

Erneuter Versuch nach ausdruecklicher Zustimmung: Auch systemd-nspawn mit --private-users=no scheiterte mit Operation not permitted beim /proc-Mount. Ein vorgeschalteter separater PID-/Mount-Namensraum aenderte das Ergebnis nicht. Die aeussere LXC verwendet selbst eine Benutzerzuordnung (UID 0 auf Host-UID 100000). Die genaue Kernel-/LXC-Ursache ist nicht abschliessend bestimmt. Rootfs und Testnetz wurden erneut entfernt, Forwarding auf 0 zurueckgesetzt. Fuer die verbleibende Neuinstallationsabnahme wird eine separat bootfaehige Ubuntu-LXC oder VM benoetigt.

## Mobile Oberfläche 1.0.1

Navigation auf Handy und Tablet als aufklappbares Menü einschließlich Profil, Abmeldung und Farbschema. Touch-Flächen ab 44 Pixel, 16-Pixel-Formularschrift, einspaltige Formulare auf Handys, innerhalb der Tabelle scrollbare breite Inhalte, größere Unterschriftsfläche und automatisch sichtbarer aktiver Auftragsschritt. Ohne JavaScript bleibt die Navigation sichtbar.

Chromium prüft neun Ansichten bei 320, 390, 768, 820 und 1024 Pixeln ohne horizontalen Seitenüberlauf, Menübedienung, Escape und den Wechsel zurück zur Desktop-Navigation. Eine über native Chromium-Touch-Ereignisse gezeichnete Unterschrift wird gespeichert. Handy- und Tablet-Screenshots wurden visuell geprüft. Dies ist eine Browser-Emulation, kein Test auf physischen iOS-/Android-Geräten.
