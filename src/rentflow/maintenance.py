import hashlib, json, os, shutil, sqlite3, tarfile, tempfile
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from .models import Document, Asset
from .db import transaction


def backup(engine, config, destination=None):
    folder = Path(destination or config.data / "backups")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / ("rentflow-" + stamp + ".tar.gz")
    with tempfile.TemporaryDirectory(prefix="rentflow-backup-") as temp:
        root = Path(temp)
        manifest = {}
        with transaction(engine) as db:
            source = sqlite3.connect(config.data / "rentflow.sqlite3")
            output = sqlite3.connect(root / "database.sqlite3")
            try:
                source.backup(output)
            finally:
                source.close()
                output.close()
            objects = {
                obj.filename: obj.sha256
                for obj in list(db.scalars(select(Document)))
                + list(db.scalars(select(Asset)))
            }
            (root / "objects").mkdir()
            for name, digest in objects.items():
                path = config.data / "objects" / name
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError("Prüfsummenfehler vor Backup: " + name)
                (root / "objects" / name).write_bytes(raw)
                manifest["objects/" + name] = digest
            configdata = {
                "secret": config.secret,
                "setup_token": config.setup_token,
                "secure_cookie": config.secure_cookie,
                "base_url": config.base_url,
            }
            (root / "configuration.json").write_text(json.dumps(configdata))
            for name in ["database.sqlite3", "configuration.json"]:
                manifest[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
            (root / "manifest.json").write_text(
                json.dumps(
                    {"format": 1, "created_at": stamp, "files": manifest},
                    sort_keys=True,
                )
            )
            temporary = target.with_suffix(".tmp")
            with tarfile.open(temporary, "w:gz") as archive:
                for name in [
                    "database.sqlite3",
                    "configuration.json",
                    "manifest.json",
                    "objects",
                ]:
                    archive.add(root / name, arcname=name, recursive=True)
            temporary.chmod(0o600)
            os.replace(temporary, target)
    fd = os.open(target, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return target


def verify_archive(archive, staging):
    staging = Path(staging)
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        if sum(member.size for member in members) > 20 * 1024**3:
            raise ValueError("Backup überschreitet die zulässige Größe.")
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("Unsicherer Pfad im Backup.")
            if path.parts[0] not in [
                "objects",
                "database.sqlite3",
                "configuration.json",
                "manifest.json",
            ]:
                raise ValueError("Unbekannter Backup-Inhalt.")
        tf.extractall(staging, filter="data")
    manifest = json.loads((staging / "manifest.json").read_text())
    if manifest.get("format") != 1:
        raise ValueError("Unbekanntes Backup-Format.")
    if not {"database.sqlite3", "configuration.json"} <= set(manifest.get("files", {})):
        raise ValueError("Backup-Manifest ist unvollständig.")
    for name, digest in manifest["files"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsicherer Manifestpfad.")
        if hashlib.sha256((staging / path).read_bytes()).hexdigest() != digest:
            raise ValueError("Backup-Prüfsumme stimmt nicht: " + name)
    actual = {
        str(p.relative_to(staging))
        for p in staging.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if actual != set(manifest["files"]):
        raise ValueError("Backup enthält nicht geprüfte Dateien.")
    db = sqlite3.connect(staging / "database.sqlite3")
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Datenbankprüfung fehlgeschlagen.")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Datenbankbeziehungen sind beschädigt.")
        for name, digest in db.execute(
            "SELECT filename,sha256 FROM documents UNION SELECT filename,sha256 FROM assets"
        ):
            if manifest["files"].get("objects/" + name) != digest:
                raise ValueError(
                    "Archivdatei fehlt oder widerspricht der Datenbank: " + name
                )
        version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        db.close()
    config = json.loads((staging / "configuration.json").read_text())
    if len(config.get("secret", "")) < 32:
        raise ValueError("Konfiguration im Backup ist unvollständig.")
    return config, version


def restore(archive, target, replace=False):
    target = Path(target).resolve()
    if target == Path("/") or len(target.parts) < 3:
        raise ValueError("Unsicheres Wiederherstellungsziel.")
    if target.exists() and any(target.iterdir()) and not replace:
        raise ValueError("Das Ziel enthält Daten. Explizite Bestätigung erforderlich.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="rentflow-restore-", dir=target.parent
    ) as temp:
        stage = Path(temp)
        config, version = verify_archive(archive, stage)
        new = stage / "restored"
        new.mkdir()
        shutil.move(str(stage / "database.sqlite3"), str(new / "rentflow.sqlite3"))
        shutil.move(str(stage / "objects"), str(new / "objects"))
        previous = None
        if target.exists():
            previous = target.with_name(
                target.name
                + ".before-restore-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            )
            target.rename(previous)
        try:
            new.rename(target)
        except Exception:
            if previous and not target.exists():
                previous.rename(target)
            raise
    return config, version


if __name__ == "__main__":
    import argparse
    from .config import Config
    from .db import make_engine

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("--archive")
    parser.add_argument("--target")
    parser.add_argument("--output")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--config-output")
    args = parser.parse_args()
    if args.action == "backup":
        cfg = Config.environment()
        print(backup(make_engine(cfg.data), cfg, args.output))
    elif args.action == "verify":
        with tempfile.TemporaryDirectory() as temp:
            _, version = verify_archive(args.archive, temp)
            print("Backup geprüft; Datenbankversion " + version)
    else:
        cfg, version = restore(args.archive, args.target, args.replace)
        if args.config_output:
            path = Path(args.config_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "RF_DATA="
                + str(Path(args.target).resolve())
                + "\nRF_SECRET="
                + cfg["secret"]
                + "\nRF_SETUP_TOKEN="
                + cfg["setup_token"]
                + "\nRF_BASE_URL="
                + cfg["base_url"]
                + "\nRF_SECURE_COOKIE="
                + ("1" if cfg["secure_cookie"] else "0")
                + "\n"
            )
            path.write_text(content)
            path.chmod(0o600)
        print("Wiederhergestellt; Datenbankversion " + version)
