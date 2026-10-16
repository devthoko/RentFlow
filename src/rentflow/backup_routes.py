from pathlib import Path
import re
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from .main import require_user, render, redirect, csrf
from .db import transaction
from . import maintenance, domain as d


def register(app):
    @app.get("/admin/backups")
    def backups(request: Request):
        with Session(app.state.engine) as db:
            require_user(request, db, True)
        folder = app.state.config.data / "backups"
        entries = [
            {"name": p.name, "size": round(p.stat().st_size / 1024, 1)}
            for p in sorted(folder.glob("rentflow-*.tar.gz"), reverse=True)
            if p.is_file()
        ]
        return render(request, "backups.html", backups=entries)

    @app.post("/admin/backup")
    async def create_backup(request: Request):
        data = dict(await request.form())
        csrf(request, data)
        with Session(app.state.engine) as db:
            actor = require_user(request, db, True)
        path = await run_in_threadpool(
            maintenance.backup, app.state.engine, app.state.config
        )
        with transaction(app.state.engine) as db:
            d.audit(db, actor, "backup.created", {"filename": path.name})
        return redirect(request, "/admin/backups", "Vollständiges Backup erstellt.")

    @app.get("/admin/backups/{filename}")
    def download_backup(request: Request, filename: str):
        with Session(app.state.engine) as db:
            require_user(request, db, True)
        if not re.fullmatch(r"rentflow-\d{8}T\d{12}Z\.tar\.gz", filename):
            raise HTTPException(404, "Backup nicht gefunden.")
        path = app.state.config.data / "backups" / filename
        if not path.is_file():
            raise HTTPException(404, "Backup nicht gefunden.")
        return FileResponse(
            path,
            media_type="application/gzip",
            filename=filename,
            headers={"Cache-Control": "no-store"},
        )
