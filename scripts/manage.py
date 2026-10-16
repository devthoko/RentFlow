#!/usr/bin/env python3
"""Host installation and maintenance. All paths are derived from a validated prefix."""

import argparse, fcntl, tomllib, json, os, pwd, re, secrets, shutil, socket, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path


def run(*args, **kw):
    return subprocess.run(
        [str(a) for a in args], check=True, stdin=subprocess.DEVNULL, **kw
    )


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def env_read(path):
    env = os.environ.copy()
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key.startswith("RF_"):
                env[key] = value
    return env


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def config_for(prefix, isolated):
    if isolated:
        if prefix.name == "rentflow":
            raise ValueError("Isolierte Installation benötigt einen anderen Namen.")
        return dict(
            service=prefix.name,
            user=prefix.name,
            data="/var/lib/" + prefix.name,
            config="/etc/" + prefix.name + "/environment",
            app_port=18080,
            web_port=18081,
            isolated=True,
        )
    if prefix != Path("/opt/rentflow"):
        raise ValueError("Standardinstallation verwendet /opt/rentflow.")
    return dict(
        service="rentflow",
        user="rentflow",
        data="/var/lib/rentflow",
        config="/etc/rentflow/environment",
        app_port=8000,
        web_port=80,
        isolated=False,
    )


def host_check():
    if os.geteuid() != 0:
        raise ValueError("Dieser Vorgang benötigt root.")
    values = dict(
        line.split("=", 1)
        for line in Path("/etc/os-release").read_text().splitlines()
        if "=" in line
    )
    if values.get("ID", "").strip('"') != "ubuntu" or values.get(
        "VERSION_ID", ""
    ).strip('"') not in ["24.04", "26.04"]:
        raise ValueError("Unterstützt werden Ubuntu LTS 24.04 und 26.04.")
    if not Path("/run/systemd/system").is_dir():
        raise ValueError("systemd muss aktiv sein.")


def packages():
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    run("apt-get", "update", env=env)
    run(
        "apt-get",
        "install",
        "-y",
        "python3",
        "python3-venv",
        "python3-dev",
        "nginx",
        "curl",
        "ca-certificates",
        "build-essential",
        "libffi-dev",
        "libpango-1.0-0",
        "libpangoft2-1.0-0",
        "libharfbuzz-subset0",
        "libjpeg-dev",
        "zlib1g-dev",
        "fonts-dejavu-core",
        env=env,
    )


def prepare(source, target):
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "runtime",
            "tools",
            "__pycache__",
            ".pytest_cache",
            "artifacts",
        ),
    )
    run("python3", "-m", "venv", target / ".venv")
    py = target / ".venv/bin/python"
    run(
        py,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        target / "requirements.lock",
    )
    run(py, "-m", "pip", "install", "--no-deps", "--no-build-isolation", target)
    run("bash", target / "scripts/runtime.sh", target)


def runtime_env(prefix, cfg):
    env = env_read(Path(cfg["config"]))
    env["LD_LIBRARY_PATH"] = str(prefix / "runtime/lib")
    return env


def permissions(prefix, cfg):
    account = pwd.getpwnam(cfg["user"])
    for p in [Path(cfg["data"])] + list(Path(cfg["data"]).rglob("*")):
        if p.is_symlink():
            raise ValueError("Unerwarteter Link im Datenverzeichnis.")
        os.chown(p, account.pw_uid, account.pw_gid)
        p.chmod(0o700 if p.is_dir() else 0o400 if p.parent.name == "objects" else 0o600)
    for p in [prefix] + list(prefix.rglob("*")):
        if not p.is_symlink():
            os.chown(p, 0, account.pw_gid)
            p.chmod(
                p.stat().st_mode | 0o050 if p.is_dir() else p.stat().st_mode | 0o040
            )
    for script in prefix.glob("*.sh"):
        script.chmod(0o750)


def migrate(prefix, cfg):
    run(
        prefix / ".venv/bin/python",
        "-m",
        "alembic",
        "upgrade",
        "head",
        cwd=prefix,
        env=runtime_env(prefix, cfg),
    )


def units(prefix, cfg):
    name = cfg["service"]
    data = cfg["data"]
    user = cfg["user"]
    common = f"""User={user}
Group={user}
WorkingDirectory={prefix}
EnvironmentFile={cfg["config"]}
Environment=LD_LIBRARY_PATH={prefix}/runtime/lib
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={data}
"""
    write(
        Path("/etc/systemd/system") / (name + ".service"),
        f"""[Unit]
Description=RentFlow
After=network.target
[Service]
{common}ExecStart={prefix}/.venv/bin/python -m uvicorn rentflow.main:create_app --factory --host 127.0.0.1 --port {cfg["app_port"]} --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
""",
    )
    for task, command, calendar in [
        ("worker", "rentflow.integrations", "*:*:0/30"),
        ("backup", "rentflow.maintenance backup", "*-*-* 03:15:00"),
    ]:
        write(
            Path("/etc/systemd/system") / (name + "-" + task + ".service"),
            f"""[Unit]
Description=RentFlow {task}
After={name}.service
[Service]
Type=oneshot
{common}ExecStart={prefix}/.venv/bin/python -m {command}
TimeoutStartSec=15min
""",
        )
        write(
            Path("/etc/systemd/system") / (name + "-" + task + ".timer"),
            f"""[Unit]
Description=RentFlow {task} schedule
[Timer]
OnCalendar={calendar}
Persistent=true
RandomizedDelaySec=5
[Install]
WantedBy=timers.target
""",
        )
    site = Path("/etc/nginx/sites-available") / name
    write(
        site,
        f"""server {{
    listen {cfg["web_port"]};
    server_name _;
    client_max_body_size 12m;
    location / {{
        proxy_pass http://127.0.0.1:{cfg["app_port"]};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }}
}}
""",
    )
    link = Path("/etc/nginx/sites-enabled") / name
    if not link.exists():
        link.symlink_to(site)
    default = Path("/etc/nginx/sites-enabled/default")
    if not cfg["isolated"] and default.is_symlink():
        default.unlink()
    run("nginx", "-t")
    run("systemctl", "daemon-reload")
    run(
        "systemctl",
        "enable",
        name + ".service",
        name + "-worker.timer",
        name + "-backup.timer",
    )
    run("systemctl", "restart", name + ".service")
    run("systemctl", "start", name + "-worker.timer", name + "-backup.timer")
    run("systemctl", "enable", "--now", "nginx")
    run("systemctl", "reload", "nginx")


def healthy(cfg):
    url = "http://127.0.0.1:" + str(cfg["web_port"]) + "/health"
    for attempt in range(30):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                result = json.load(r)
                if result["status"] == "ok":
                    return result
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Healthcheck fehlgeschlagen: " + url)


def stop(cfg):
    name = cfg["service"]
    run("systemctl", "stop", name + "-worker.timer", name + "-backup.timer")
    run(
        "systemctl",
        "stop",
        name + "-worker.service",
        name + "-backup.service",
        name + ".service",
    )


def start(cfg):
    name = cfg["service"]
    run(
        "systemctl",
        "start",
        name + ".service",
        name + "-worker.timer",
        name + "-backup.timer",
    )


def backup(prefix, cfg, output=None):
    command = [prefix / ".venv/bin/python", "-m", "rentflow.maintenance", "backup"]
    if output:
        command += ["--output", output]
    result = run(
        *command,
        cwd=prefix,
        env=runtime_env(prefix, cfg),
        capture_output=True,
        text=True,
    )
    archive = Path(result.stdout.strip().splitlines()[-1])
    print("Backup:", archive, flush=True)
    return archive


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["install", "upgrade", "backup", "restore"])
    p.add_argument("--prefix", default="/opt/rentflow")
    p.add_argument("--source")
    p.add_argument("--isolated", action="store_true")
    p.add_argument("--base-url", default="")
    p.add_argument("--archive")
    p.add_argument("--confirm-replace", action="store_true")
    a = p.parse_args()
    host_check()
    prefix = Path(a.prefix).resolve()
    if prefix.parent != Path("/opt") or not re.fullmatch(
        "rentflow(?:-[a-z0-9-]+)?", prefix.name
    ):
        raise ValueError(
            "Installationsziel muss /opt/rentflow oder /opt/rentflow-<testname> sein."
        )
    lock = Path("/run/lock") / (prefix.name + "-maintenance.lock")
    with lock.open("w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if a.action == "install":
            cfg = config_for(prefix, a.isolated)
            for path in [
                prefix,
                Path(cfg["data"]),
                Path(cfg["config"]),
                Path("/etc/systemd/system") / (cfg["service"] + ".service"),
            ]:
                if path.exists():
                    raise ValueError("Ziel existiert bereits: " + str(path))
            for port in [cfg["app_port"], cfg["web_port"]]:
                with socket.socket() as sock:
                    try:
                        sock.bind(("0.0.0.0", port))
                    except OSError:
                        raise ValueError("Port ist belegt: " + str(port))
            if not a.isolated:
                packages()
            try:
                pwd.getpwnam(cfg["user"])
            except KeyError:
                run(
                    "useradd",
                    "--system",
                    "--home-dir",
                    cfg["data"],
                    "--shell",
                    "/usr/sbin/nologin",
                    cfg["user"],
                )
            data = Path(cfg["data"])
            data.mkdir(mode=0o700, parents=True)
            base = a.base_url or "http://" + socket.gethostname() + (
                ":" + str(cfg["web_port"]) if cfg["web_port"] != 80 else ""
            )
            if not re.fullmatch(r"https?://[A-Za-z0-9.:\[\]-]+", base):
                raise ValueError("Ungültige Basis-URL.")
            token = secrets.token_urlsafe(24)
            write(
                Path(cfg["config"]),
                f"RF_DATA={data}\nRF_SECRET={secrets.token_urlsafe(48)}\nRF_SETUP_TOKEN={token}\nRF_BASE_URL={base}\nRF_SECURE_COOKIE={'1' if base.startswith('https:') else '0'}\n",
                0o600,
            )
            prepare(Path(a.source), prefix)
            write(prefix / "installation.json", json.dumps(cfg, indent=2), 0o640)
            migrate(prefix, cfg)
            permissions(prefix, cfg)
            units(prefix, cfg)
            result = healthy(cfg)
            print("RentFlow " + result["version"] + " bereit: " + base + "/setup")
            print("Einrichtungsschlüssel: " + token)
        else:
            cfg = json.loads((prefix / "installation.json").read_text())
            if a.action == "backup":
                backup(prefix, cfg)
                return
            if a.action == "upgrade":
                if not a.source:
                    raise ValueError("Geprüftes Release-Archiv fehlt.")

                def version(path):
                    value = tomllib.loads((path / "pyproject.toml").read_text())[
                        "project"
                    ]["version"]
                    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?", value)
                    if not match:
                        raise ValueError("Ungültige Release-Version.")
                    return (
                        *map(int, match.groups()[:3]),
                        int(match.group(4)) if match.group(4) else 1000000,
                    )

                if version(Path(a.source)) <= version(prefix):
                    raise ValueError(
                        "Updates benötigen eine neuere Version. Downgrades sind gesperrt."
                    )
                staged = prefix.with_name(prefix.name + "-staged-" + stamp())
                prepare(Path(a.source), staged)
                write(staged / "installation.json", json.dumps(cfg, indent=2), 0o640)
                permissions(staged, cfg)
                stop(cfg)
                try:
                    archive = backup(prefix, cfg)
                except Exception:
                    start(cfg)
                    raise
                previous = prefix.with_name(prefix.name + "-before-upgrade-" + stamp())
                prefix.rename(previous)
                staged.rename(prefix)
                try:
                    migrate(prefix, cfg)
                    permissions(prefix, cfg)
                    units(prefix, cfg)
                    healthy(cfg)
                except Exception:
                    print(
                        "Update angehalten. Kein automatischer Daten-Rollback. Vorheriger Programmstand:",
                        previous,
                        "Backup:",
                        archive,
                        file=sys.stderr,
                    )
                    raise
                print("Update geprüft; vorheriger Programmstand:", previous)
            else:
                if not a.confirm_replace:
                    raise ValueError("Wiederherstellung benötigt --confirm-replace.")
                archive = Path(a.archive).resolve()
                env = runtime_env(prefix, cfg)
                py = prefix / ".venv/bin/python"
                run(
                    py,
                    "-m",
                    "rentflow.maintenance",
                    "verify",
                    "--archive",
                    archive,
                    env=env,
                )
                stop(cfg)
                try:
                    backup(
                        prefix,
                        cfg,
                        Path(cfg["data"]).parent / (cfg["service"] + "-safety-backups"),
                    )
                    run(
                        py,
                        "-m",
                        "rentflow.maintenance",
                        "restore",
                        "--archive",
                        archive,
                        "--target",
                        cfg["data"],
                        "--replace",
                        "--config-output",
                        cfg["config"],
                        env=env,
                    )
                    migrate(prefix, cfg)
                    permissions(prefix, cfg)
                    start(cfg)
                    healthy(cfg)
                except Exception:
                    print(
                        "Wiederherstellung angehalten; bisherige Daten und Sicherheitsbackup bleiben erhalten.",
                        file=sys.stderr,
                    )
                    raise
                print("Wiederherstellung erfolgreich geprüft.")


if __name__ == "__main__":
    main()
