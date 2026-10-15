from sqlalchemy import select, text
from sqlalchemy.orm import Session
from rentflow.models import User
from conftest import token

def test_health_and_setup_gate(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "Einrichtungsschlüssel" in client.get("/").text

def test_setup_csrf_and_token(client):
    assert client.post("/setup", data={}).status_code == 403
    csrf = token(client)
    assert client.post("/setup", data={"csrf": csrf, "token": "wrong"}).status_code == 403

def test_setup_is_single_use_and_password_hashed(admin, app):
    assert admin.post("/setup", data={"csrf": token(admin, "/")}).status_code == 409
    with Session(app.state.engine) as db:
        user = db.scalar(select(User))
        assert user.role == "admin"
        assert user.password.startswith("$argon2")
        assert db.scalar(text("PRAGMA journal_mode")) == "wal"
        assert db.scalar(text("PRAGMA foreign_keys")) == 1

def test_login_logout(admin):
    assert admin.post("/logout", data={"csrf": token(admin, "/")}).status_code == 200
    assert "Melde dich an" in admin.get("/").text
    csrf = token(admin, "/login")
    assert admin.post("/login", data={"csrf": csrf, "email": "admin@example.com", "password": "wrong"}).status_code == 400
    assert admin.post("/login", data={"csrf": csrf, "email": "admin@example.com", "password": "Testpassword123!"}).status_code == 200
