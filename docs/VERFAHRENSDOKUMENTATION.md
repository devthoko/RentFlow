# Vorlage für die betriebliche Verfahrensdokumentation

Stand: 16.10.2026. Diese Vorlage beschreibt technische Maßnahmen; sie ersetzt keine firmenspezifische Freigabe oder steuerliche und rechtliche Prüfung.

## Geltungsbereich und Verantwortung

RentFlow unterstützt den Mietprozess mit Privatkunden. Firmenleitung benennt Verantwortliche für Benutzerrechte, Rechnungen, Zahlungskontrolle, Backups, Datenschutz und Wiederherstellung. Änderungen am Verfahren und an der Software werden mit Datum und Freigabe dokumentiert. Auftragsdaten und Systemprotokolle sind regelmäßig auf Vollständigkeit zu prüfen.

Bei Rechnungen an private Endverbraucher greift die hier relevante obligatorische B2B-E-Rechnung nicht. RentFlow erzeugt PDF-Rechnungen; vor elektronischem Rechnungsversand ist die notwendige Zustimmung des Empfängers betrieblich sicherzustellen. Das Programm enthält keinen B2B-/XRechnungsprozess. Quellen: [BMF – E-Rechnung](https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html), [§ 14 UStG](https://www.gesetze-im-internet.de/ustg_1980/__14.html).

## Erfassung und Kontrolle

Kunden- und Eventdaten prüfen. Preise werden intern netto mit Dezimalrechnung geführt; Gesamtbetrag und Steuerbeträge werden ausgewiesen. Die eingestellte Besteuerungsart und Steuersätze muss die Firma fachlich bestätigen. Mietvertragstext und Verbraucherinformationen sind vor Nutzung anzupassen. Zusätzliche gesetzliche Informations- oder Widerrufspflichten hängen vom konkreten Geschäftsmodell ab und werden nicht automatisch erzeugt.

Angebote, Verträge und Rechnungen speichern die zum Ausstellungszeitpunkt gültigen Daten. Nummern werden unter einer Datenbanksperre fortlaufend pro Jahr und Dokumentart vergeben. Das Original einer Rechnung bleibt erhalten. Eine Korrektur erzeugt einen eigenen Stornobeleg; Buchungen werden mit Gegenbuchungen korrigiert. Archivierte Datensätze sind durch Datenbanktrigger gegen normale Updates und Löschungen geschützt.

Digitale Unterschriften sind einfache elektronische Unterschriften. Dokument-ID, Version, Originalprüfsumme, Person, Zeitpunkt, erfassender Benutzer und Nachweis werden gespeichert. Ein hochgeladenes PDF ist ein dokumentierter Nachweis, keine Echtheitsprüfung.

## Archiv und Prüfpfad

PDFs und Bilder erhalten SHA-256-Prüfsummen und eindeutige Dateinamen. Dateischreibvorgänge erfolgen atomar; Abruf und Backup prüfen die Prüfsummen. Wesentliche Aktionen bilden eine fortgeschriebene Hashkette im Audit-Log. Dokumente, Zahlungen, Kautionen, Unterschriftsnachweise und Audit-Einträge lassen sich über die Anwendung nicht löschen oder nachträglich überschreiben.

Diese Maßnahmen sind keine externe Zertifizierung und kein manipulationssicherer Speicher gegen Administratoren mit Betriebssystemzugriff. Root-/Hostzugriffe restriktiv vergeben und protokollieren. Ergänzende externe, gegen Veränderung geschützte Sicherungen und regelmäßige Kontrollen sind erforderlich. [GoBD, amtliche Fassung](https://amtliche-handbuecher.bundesfinanzministerium.de/ao/2025/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/anhang-33.html).

Für Prüfungen stehen PDFs, ihre Historie, Audit-Daten und der vollständige SQLite-Datenbestand im Backup zur Verfügung. Export bzw. Datenzugriff mit der steuerlichen Beratung und Prüfungsstelle abstimmen; RentFlow behauptet keinen zertifizierten DATEV-/Prüferexport.

## Aufbewahrung und Datenschutz

Rechnungsdoppel sind nach § 14b UStG grundsätzlich acht Jahre aufzubewahren, gerechnet vom Schluss des Ausstellungsjahres; Verlängerungen und andere Unterlagenarten müssen gesondert beurteilt werden. RentFlow löscht das Archiv nicht automatisch. [§ 14b UStG](https://www.gesetze-im-internet.de/ustg_1980/__14b.html).

Die Firma dokumentiert Rechtsgrundlagen, Datenschutzhinweise, Berechtigungen, Auftragsverarbeitung mit Mail-/WebDAV-/Hosting-Anbietern und ein Lösch-/Sperrkonzept. Auskunfts- und Löschersuchen fachlich prüfen; gesetzlich aufzubewahrende Unterlagen nicht pauschal entfernen. Nicht mehr erforderliche Kontakte oder Bemerkungen können bearbeitet werden, während notwendige historische Belege erhalten bleiben. Ein automatischer DSGVO-Auskunfts- oder Löschworkflow ist nicht Bestandteil dieser Version.

## Sicherung und Wiederanlauf

Tägliche Sicherungen prüfen, eine geschützte externe Kopie aufbewahren und regelmäßig eine Testwiederherstellung durchführen. Verantwortliche, Zeitpunkte, Ergebnis und Abweichungen dokumentieren. Vor Updates erfolgt eine Sicherung. Bei Restore bleibt der vorherige Datenstand erhalten; eventuell danach entstandene Geschäftsvorgänge werden ausdrücklich abgeglichen.

Nach Wiederherstellung Zahlungsstände, Rechnungsnummern, PDFs und den tatsächlichen Mailversand kontrollieren. Systemzeit, Speicherplatz, Dienststatus und Fehlermeldungen regelmäßig überwachen. Benutzer schulen: Nur tatsächliche Geldflüsse buchen; eine Kaution bezahlt keine Rechnung.
