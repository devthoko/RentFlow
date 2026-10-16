"""Refresh license notices for the bundled frontend versions."""

from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sources = {
    "HTMX-LICENSE.txt": "https://raw.githubusercontent.com/bigskysoftware/htmx/v2.0.4/LICENSE",
    "ALPINE-LICENSE.txt": "https://raw.githubusercontent.com/alpinejs/alpine/v3.14.9/LICENSE.md",
    "LUCIDE-LICENSE.txt": "https://raw.githubusercontent.com/lucide-icons/lucide/0.468.0/LICENSE",
    "INTER-LICENSE.txt": "https://raw.githubusercontent.com/rsms/inter/v4.1/LICENSE.txt",
}
if __name__ == "__main__":
    (ROOT / "licenses").mkdir(exist_ok=True)
    for name, url in sources.items():
        with urlopen(url, timeout=30) as response:
            raw = response.read()
        if len(raw) < 500:
            raise ValueError("Unvollständiger Lizenztext: " + name)
        (ROOT / "licenses" / name).write_bytes(raw)
        print(name)
