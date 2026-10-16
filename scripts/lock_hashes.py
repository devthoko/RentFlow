"""Add PyPI archive hashes to the existing exact runtime pins; never update versions."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
lock = root / "requirements.lock"
pins = [
    line.strip().split(" \\")[0]
    for line in lock.read_text().splitlines()
    if "==" in line and not line.lstrip().startswith("--")
]
if not any(line.startswith("setuptools==") for line in pins):
    pins.append("setuptools==80.9.0")


def expand(pin):
    name, version = pin.split("==")
    with urlopen(
        "https://pypi.org/pypi/" + name + "/" + version + "/json", timeout=30
    ) as response:
        info = json.load(response)
    hashes = sorted({file["digests"]["sha256"] for file in info["urls"]})
    if not hashes:
        raise ValueError("Keine Archive für " + pin)
    return (
        pin + " \\\n" + " \\\n".join("    --hash=sha256:" + digest for digest in hashes)
    )


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=8) as pool:
        lines = list(pool.map(expand, sorted(pins, key=str.lower)))
    lock.write_text("\n".join(lines) + "\n")
    print("Geprüfte Hashes für", len(pins), "festgelegte Pakete gespeichert.")
