"""Tests for GET /health endpoint."""

import asyncio

import pytest
from starlette.testclient import TestClient

import web.db as db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())

    from web.server import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok_json(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok"}
