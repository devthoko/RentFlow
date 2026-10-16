"""Run only against /opt/rentflow-install-test on the shared DEV/TEST LXC."""

import hashlib, io, json, os, re, sqlite3, subprocess, tarfile, tempfile, time, tomllib
from pathlib import Path
import httpx

ROOT = Path("/opt/rentflow")
NAME = os.environ.get("RF_INSTALL_TEST_NAME", "rentflow-install-test")
if not re.fullmatch(r"rentflow-[a-z0-9-]+-test", NAME):
    raise ValueError("Ungültiger Testname.")
PREFIX = Path("/opt") / NAME
DATA = Path("/var/lib") / NAME
BASE = "http://127.0.0.1:18081"


def shell(*args, **kw):
    return subprocess.run(
        [str(a) for a in args], check=True, stdin=subprocess.DEVNULL, **kw
    )


def count():
    with sqlite3.connect(DATA / "rentflow.sqlite3") as db:
        return db.execute("SELECT count(*) FROM customers").fetchone()[0]


def csrf(client, path="/settings"):
    r = client.get(path)
    r.raise_for_status()
    return re.search(r'name="csrf" value="([^"]+)"', r.text)[1]


def customer(client, name):
    r = client.post(
        "/customers",
        data={
            "csrf": csrf(client, "/customers"),
            "name": name,
            "email": "install@example.com",
        },
    )
    r.raise_for_status()


def main():
    assert PREFIX.is_dir() and DATA.is_dir()
    source_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    base_version = tomllib.loads((PREFIX / "pyproject.toml").read_text())["project"][
        "version"
    ]
    major, minor, patch = map(int, base_version.split("-")[0].split("."))
    test_version = f"{major}.{minor}.{patch + 1}"
    with sqlite3.connect(DATA / "rentflow.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 0, (
            "Installationstest benötigt eine frische isolierte Installation."
        )
        assert db.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
    config = dict(
        line.split("=", 1)
        for line in (Path("/etc") / NAME / "environment").read_text().splitlines()
    )
    client = httpx.Client(base_url=BASE, follow_redirects=True, timeout=60)
    r = client.post(
        "/setup",
        data={
            "csrf": csrf(client, "/setup"),
            "token": config["RF_SETUP_TOKEN"],
            "name": "Installationstest",
            "company": "Isolierter Testbetrieb",
            "address": "Testanschrift 1",
            "email": "install@example.com",
            "password": "Installationstest!123",
            "tax_id": "Testkennung",
        },
    )
    r.raise_for_status()
    customer(client, "Vor dem Update")
    shell("bash", PREFIX / "backup.sh")
    archive = sorted((DATA / "backups").glob("*.tar.gz"))[-1]
    with tempfile.TemporaryDirectory(prefix="rentflow-update-test-") as temp:
        release = Path(temp) / "release.tar.gz"
        files = shell(
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.split("\0")
        with tarfile.open(release, "w:gz") as tf:
            for name in files:
                if not name or not (ROOT / name).is_file():
                    continue
                raw = (ROOT / name).read_bytes()
                if name in ["pyproject.toml", "src/rentflow/main.py"]:
                    raw = raw.replace(source_version.encode(), test_version.encode())
                info = tarfile.TarInfo("RentFlow-" + test_version + "/" + name)
                info.size = len(raw)
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(raw))
        digest = hashlib.sha256(release.read_bytes()).hexdigest()
        bad = subprocess.run(
            [
                "bash",
                str(ROOT / "install.sh"),
                "--version",
                test_version,
                "--archive",
                str(release),
                "--sha256",
                "0" * 64,
                "--upgrade",
                "--prefix",
                str(PREFIX),
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        assert bad.returncode != 0 and "Prüfsumme" in bad.stderr
        assert count() == 1
        shell(
            "bash",
            ROOT / "install.sh",
            "--version",
            test_version,
            "--archive",
            release,
            "--sha256",
            digest,
            "--upgrade",
            "--prefix",
            PREFIX,
        )
        assert httpx.get(BASE + "/health").json()["version"] == test_version
    assert count() == 1
    with sqlite3.connect(DATA / "rentflow.sqlite3") as db:
        assert (
            db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0003"
        )
    customer(client, "Nach dem Update")
    assert count() == 2
    shell("bash", PREFIX / "restore.sh", archive, "--confirm-replace")
    assert count() == 1
    previous = sorted(DATA.parent.glob(DATA.name + ".before-restore-*"))[-1]
    with sqlite3.connect(previous / "rentflow.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM customers").fetchone()[0] == 2
    assert httpx.get(BASE + "/health").json()["status"] == "ok"
    assert httpx.get("http://127.0.0.1/health").json()["status"] == "ok"
    print(
        "PASS: leere Neuinstallation, Prüfsummensperre, Update samt Migrationen, Datenübernahme, Backup, Restore, Erhalt neuerer Daten, DEV-Healthcheck."
    )


if __name__ == "__main__":
    main()
