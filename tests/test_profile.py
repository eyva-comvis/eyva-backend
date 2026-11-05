"""Tes profil pengguna: baca, ubah username/avatar, validasi, dan username bentrok."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from tests.conftest import SECRET, make_token

ANON = {"Authorization": ""}


class FakeRepo:
    enabled = True

    def __init__(self):
        self.rows: dict[str, dict] = {"u1": {"id": "u1", "username": "budi", "avatar_url": "https://lh3.google/pic.jpg"}}

    def get_profile(self, user_id):
        return self.rows.get(user_id)

    def update_profile(self, user_id, changes):
        if changes.get("username") == "taken":
            raise Exception('duplicate key value violates unique constraint "profiles_username_lower_key" (23505)')
        row = {**self.rows.get(user_id, {"id": user_id}), **changes}
        self.rows[user_id] = row
        return row


def h(sub):
    return {"Authorization": f"Bearer {make_token(sub)}"}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_jwt_secret", SECRET)
    repo = FakeRepo()
    with TestClient(app) as c:
        original = app.state.persister
        app.state.persister = SimpleNamespace(repo=repo, drain=original.drain)
        yield c, repo


def test_profile_requires_login(env):
    c, _ = env
    assert c.get("/profile", headers=ANON).status_code == 401


def test_get_profile_reports_whether_an_app_avatar_was_chosen(env):
    c, _ = env
    r = c.get("/profile", headers=h("u1")).json()
    assert r == {"user_id": "u1", "email": "u1@example.com", "username": "budi",
                 "avatar_url": "https://lh3.google/pic.jpg", "avatar_selected": False}


def test_profile_without_row_falls_back_to_email_username(env):
    c, _ = env
    r = c.get("/profile", headers=h("newbie")).json()
    assert r["username"] == "newbie" and r["avatar_url"] is None and r["avatar_selected"] is False


def test_update_avatar_and_username(env):
    c, repo = env
    r = c.patch("/profile", json={"avatar_url": "/images/FemaleAva.svg"}, headers=h("u1"))
    assert r.status_code == 200 and r.json()["avatar_selected"] is True
    r = c.patch("/profile", json={"username": "budi_2"}, headers=h("u1"))
    assert r.json()["username"] == "budi_2" and repo.rows["u1"]["avatar_url"] == "/images/FemaleAva.svg"


def test_update_validation_and_conflict(env):
    c, _ = env
    assert c.patch("/profile", json={"avatar_url": "https://evil/x.png"}, headers=h("u1")).status_code == 422
    assert c.patch("/profile", json={"username": "a b"}, headers=h("u1")).status_code == 422
    assert c.patch("/profile", json={}, headers=h("u1")).status_code == 422
    assert c.patch("/profile", json={"username": "taken"}, headers=h("u1")).status_code == 409
