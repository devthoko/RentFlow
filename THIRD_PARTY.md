# Eingebundene Komponenten

RentFlow liefert die folgenden Frontend-Ressourcen lokal aus. Es werden keine externen Schrift- oder Skriptserver aufgerufen.

| Komponente | Version | Lizenz | Quelle |
|---|---|---|---|
| HTMX | 2.0.4 | Zero-Clause BSD | https://github.com/bigskysoftware/htmx |
| Alpine.js CSP | 3.14.9 | MIT | https://github.com/alpinejs/alpine |
| Lucide | 0.468.0 | ISC, teilweise MIT | https://github.com/lucide-icons/lucide |
| Inter Variable | 4.1 | SIL Open Font License 1.1 | https://github.com/rsms/inter |

Die vollständigen Hinweise stehen in licenses/. scripts/vendor_licenses.py lädt sie aus den jeweiligen Versionen.

Python-Abhängigkeiten sind in requirements.lock festgelegt und werden durch pip samt ihren Lizenzmetadaten installiert. Die eigene SQLite-Laufzeit 3.54.0 wird aus dem offiziellen Quellarchiv erstellt; SQLite ist Public Domain: https://sqlite.org/copyright.html. Systempakete bleiben unter ihren jeweiligen Lizenzen.
