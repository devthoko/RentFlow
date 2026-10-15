import re
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from rentflow.config import Config
from rentflow.main import create_app

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RF_DATA", str(tmp_path))
    monkeypatch.setenv("RF_SECRET", "test-secret-" * 8)
    monkeypatch.setenv("RF_SETUP_TOKEN", "test-setup-token")
    command.upgrade(AlembicConfig("alembic.ini"), "head")
    app = create_app(Config.environment())
    yield app
    app.state.engine.dispose()

def token(client, path="/setup"):
    response = client.get(path)
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)

@pytest.fixture
def client(app):
    with TestClient(app) as c: yield c

@pytest.fixture
def admin(client):
    csrf = token(client)
    response = client.post("/setup", data={"csrf": csrf, "token": "test-setup-token",
        "name": "Test Admin", "company": "Testverleih", "address": "Teststraße 1, 12345 Teststadt",
        "email": "admin@example.com", "password": "Testpassword123!", "tax_id": "DE123456789",
        "iban": "DE89370400440532013000"})
    assert response.status_code == 200, response.text
    return client
