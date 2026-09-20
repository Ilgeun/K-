import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import security


def _app(monkeypatch, password="s3cret", user=None, env=None):
    for k in ("APP_PASSWORD", "APP_USER", "MARINE_ENV", "MARINE_ALLOW_OPEN"):
        monkeypatch.delenv(k, raising=False)
    if password:
        monkeypatch.setenv("APP_PASSWORD", password)
    if user:
        monkeypatch.setenv("APP_USER", user)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    app = FastAPI()
    security.install(app)

    @app.get("/api/x")
    def x():
        return {"ok": 1}

    @app.get("/healthz")
    def h():
        return {"ok": True}

    return TestClient(app)


def _basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def test_requests_without_credentials_are_rejected(monkeypatch):
    c = _app(monkeypatch)
    r = c.get("/api/x")
    assert r.status_code == 401 and "Basic" in r.headers["www-authenticate"]


def test_wrong_password_and_wrong_user_are_rejected(monkeypatch):
    c = _app(monkeypatch)
    assert c.get("/api/x", headers=_basic("team", "nope")).status_code == 401
    assert c.get("/api/x", headers=_basic("other", "s3cret")).status_code == 401


def test_correct_credentials_pass_and_custom_user_works(monkeypatch):
    assert _app(monkeypatch).get("/api/x", headers=_basic("team", "s3cret")).status_code == 200
    assert _app(monkeypatch, user="jaehwi").get("/api/x", headers=_basic("jaehwi", "s3cret")).status_code == 200


def test_malformed_authorization_header_is_rejected_not_crashing(monkeypatch):
    c = _app(monkeypatch)
    assert c.get("/api/x", headers={"Authorization": "Basic !!!not-base64"}).status_code == 401
    assert c.get("/api/x", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_health_check_is_public(monkeypatch):
    assert _app(monkeypatch).get("/healthz").status_code == 200


def test_production_without_password_refuses_to_start(monkeypatch):
    with pytest.raises(RuntimeError, match="APP_PASSWORD"):
        _app(monkeypatch, password="", env={"MARINE_ENV": "production"})


def test_production_can_be_opened_only_explicitly(monkeypatch):
    c = _app(monkeypatch, password="", env={"MARINE_ENV": "production", "MARINE_ALLOW_OPEN": "1"})
    assert c.get("/api/x").status_code == 200


def test_development_without_password_stays_open(monkeypatch):
    assert _app(monkeypatch, password="").get("/api/x").status_code == 200
