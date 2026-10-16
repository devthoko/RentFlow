# Abnahmeprotokoll

Stand: 16.10.2026, Kandidat 1.0.0-rc.1. Alle hier aufgeführten ausführbaren Tests liefen direkt auf der gemeinsamen Ubuntu-26.04-LXC. Automatisierte Fachtests verwenden ausschließlich temporäre Datenbanken und Dateien.

## Fachregeln und Oberfläche

40 automatisierte Tests prüfen die 30 verlangten Pflichtfälle einschließlich:

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

## Noch offene Freigabe

Der Entwicklungsauftrag verlangt vor Version 1.0.0 zusätzlich eine echte Neuinstallation auf einem frischen Ubuntu-Server. Diese wurde noch nicht durchgeführt. Für eine zusätzliche kurzlebige Testumgebung ist laut Auftrag vorherige Erlaubnis einzuholen. Bis dahin wird ausschließlich ein Release Candidate veröffentlicht.

SMTP und WebDAV wurden mit kontrollierten Transportantworten und Fehlersimulation geprüft. Ein produktiver Mailserver und Nextcloud-Zugang wurden nicht angegeben; deren konkrete Erreichbarkeit/Anmeldung muss nach Konfiguration mit Testmail bzw. Synchronisierung geprüft werden.
