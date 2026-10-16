# Installation einer festgelegten Version

Der aktuelle Abnahmestand ist 1.0.0-rc.1. Die vollständige Freigabe als 1.0.0 wartet noch auf den vorgeschriebenen Test auf einem wirklich frischen Ubuntu-Server. Die bestehende DEV-/TEST-LXC sowie isolierte Verzeichnisse auf ihr ersetzen diesen Test nicht.

Vorgesehen: Ubuntu LTS 24.04 oder 26.04, systemd, root, mindestens 2 CPU-Kerne, 2 GB RAM und 5 GB freien Speicher zuzüglich Archiv/Backups. Die bisherige Host-Abnahme lief auf Ubuntu 26.04. Dienste und Ports 80/8000 dürfen vor einer Standardinstallation nicht anderweitig belegt sein. Der Installer verweigert bestehende Zielverzeichnisse.

## Einzeiler

Als root ausführen (auf Systemen mit sudo kann dem äußeren bash-Befehl sudo vorangestellt werden):

~~~sh
bash -c 'set -euo pipefail; apt-get update; apt-get install -y curl ca-certificates; curl -fsSL https://raw.githubusercontent.com/devthoko/RentFlow/main/install.sh | bash -s -- --version 1.0.0-rc.1'
~~~

Der Bootstrap lädt releases/1.0.0-rc.1.json, anschließend das Archiv des darin festgelegten Git-Commits und vergleicht dessen SHA-256 vor der Ausführung. Python-Pakete sind ebenfalls mit Versionen und Archiv-Hashes festgelegt. SQLite wird aus einem separat geprüften Quellarchiv erstellt. Das Bootstrap-Skript und das Manifest werden über GitHubs HTTPS-Verbindung vertraut; wer sie zusätzlich prüfen möchte, lädt install.sh zuerst herunter, prüft den Inhalt und führt die gespeicherte Datei aus.

Der Installer richtet Systembenutzer, virtuelle Python-Umgebung, Datenverzeichnis, Migrationen, nginx, Anwendung, Versandtimer und täglichen Backup-Timer ein. Er endet mit Healthcheck, Adresse und einmaligem Einrichtungsschlüssel. Die Neuinstallation enthält keine Geschäftsdaten.

Eine feste externe Basis-URL kann über --base-url https://verleih.example.com angegeben werden. Das setzt sichere Sitzungscookies voraus; TLS muss am vorgeschalteten Reverse Proxy bereits eingerichtet sein. Ohne Domain startet die abgeschottete Testinstallation per HTTP. Für Internetbetrieb zuerst TLS konfigurieren; siehe BETRIEB.md.

## Privates Repository

Bei einem künftig privaten Repository einen ausschließlich lesenden GitHub-Token als GITHUB_TOKEN bereitstellen. Den Bootstrap mit einem Authorization-Header herunterladen und beim Start dessen Umgebung erhalten:

~~~sh
curl -fSL -H "Authorization: Bearer $GITHUB_TOKEN" https://raw.githubusercontent.com/devthoko/RentFlow/main/install.sh -o install.sh
sudo --preserve-env=GITHUB_TOKEN bash install.sh --version 1.0.0-rc.1
~~~

Der Installer verwendet den Token nur für GitHub-Downloads; er schreibt ihn nicht in die Anwendungskonfiguration. Auf root-Sitzungen ist sudo nicht nötig.

## Isolierte Abnahme auf der vorhandenen LXC

--isolated --prefix /opt/rentflow-install-test verwendet separate Daten unter /var/lib/rentflow-install-test, eigene Dienste/Konfiguration und Ports 18080/18081. Systempakete müssen dort bereits vorhanden sein. Kein Verzeichnis und keine bestehende Datenbank werden überschrieben. Es wird keine weitere dauerhafte LXC benötigt.

Für einen lokalen Archivtest sind --archive /pfad/release.tar.gz und --sha256 <Hash> nötig. scripts/test_installation.py prüft eine frische isolierte Installation mit synthetischen Daten, manipuliertes Archiv, Versionsupdate, Datenübernahme und Restore einschließlich Erhalt des neueren Datenstands. Es verweigert eine bereits eingerichtete Testinstallation.

## Wartung

- Backup: sudo /opt/rentflow/backup.sh
- Update: sudo /opt/rentflow/upgrade.sh --version <neuere-Version>
- Restore: sudo /opt/rentflow/restore.sh /pfad/backup.tar.gz --confirm-replace

Ablauf, Datenpfade, Schutzmaßnahmen und erforderliche Fachprüfungen stehen in BETRIEB.md.
