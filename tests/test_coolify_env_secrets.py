"""Coolify env-managed credentials must not be seeded or changed through SQLite."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import admin
from src.core.auth import AuthManager
from src.core.config import config
from src.core.database import Database
from src.services.proxy_manager import ProxyManager


@pytest.fixture
def env_secrets(monkeypatch):
    values = {
        "FLOW2API_SECRETS_FROM_ENV": "1",
        "FLOW2API_API_KEY": "new-api-key-strong-enough",
        "FLOW2API_ADMIN_PASSWORD": "new-admin-password-strong-enough",
        "FLOW2API_YESCAPTCHA_API_KEY": "new-captcha-key",
        "FLOW2API_PLUGIN_CONNECTION_TOKEN": "new-plugin-token",
        "FLOW2API_PROXY_URL": "http://user:secret@proxy.example:8080",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_env_mode_requires_unique_api_key_and_password(monkeypatch):
    monkeypatch.setenv("FLOW2API_SECRETS_FROM_ENV", "1")
    monkeypatch.delenv("FLOW2API_API_KEY", raising=False)
    monkeypatch.delenv("FLOW2API_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="FLOW2API_API_KEY"):
        config.validate_env_secrets()
    monkeypatch.setenv("FLOW2API_API_KEY", "han1234")
    with pytest.raises(RuntimeError, match="FLOW2API_API_KEY"):
        config.validate_env_secrets()
    monkeypatch.setenv("FLOW2API_API_KEY", "unique-key")
    with pytest.raises(RuntimeError, match="FLOW2API_ADMIN_PASSWORD"):
        config.validate_env_secrets()


def test_env_mode_scrubs_legacy_db_and_blocks_admin_secret_writes(temp_db_path, env_secrets):
    config.validate_env_secrets()

    async def prepare():
        database = Database(db_path=temp_db_path)
        await database.init_db()
        await database.init_config_from_toml(
            {"global": {"admin_username": "admin", "admin_password": "legacy-pass", "api_key": "legacy-key"},
             "captcha": {"captcha_method": "yescaptcha", "yescaptcha_api_key": "legacy-captcha"}},
            is_first_startup=True,
        )
        first_admin = await database.get_admin_config()
        assert first_admin.password == first_admin.api_key == ""
        await database.update_admin_config(password="old-stored-password", api_key="old-stored-api-key")
        await database.update_captcha_config(
            captcha_method="yescaptcha", yescaptcha_api_key="old-stored-captcha",
            browser_proxy_enabled=True, browser_proxy_url="http://user:secret@browser-proxy:8080",
        )
        await database.update_plugin_config(connection_token="old-stored-plugin")
        await database.update_proxy_config(enabled=True, proxy_url="http://old:secret@localhost:8001")
        await database.clear_env_managed_secrets()
        assert (await database.get_admin_config()).password == ""
        assert (await database.get_admin_config()).api_key == ""
        assert (await database.get_captcha_config()).yescaptcha_api_key == ""
        assert (await database.get_captcha_config()).browser_proxy_url is None
        assert (await database.get_plugin_config()).connection_token == ""
        assert (await database.get_proxy_config()).proxy_url is None
        return database

    database = asyncio.run(prepare())
    assert AuthManager.verify_admin("admin", env_secrets["FLOW2API_ADMIN_PASSWORD"])
    assert AuthManager.verify_api_key(env_secrets["FLOW2API_API_KEY"])
    assert not AuthManager.verify_api_key("old-stored-api-key")
    assert config.yescaptcha_api_key == env_secrets["FLOW2API_YESCAPTCHA_API_KEY"]

    app = FastAPI()
    app.include_router(admin.router)
    admin.set_dependencies(None, ProxyManager(database), database, None, None)
    session = "env-secret-test-admin"
    admin.active_admin_tokens.add(session)
    headers = {"Authorization": f"Bearer {session}"}
    try:
        with TestClient(app) as client:
            assert client.get("/api/admin/config", headers=headers).json()["api_key"] == ""
            assert client.get("/api/captcha/config", headers=headers).json()["yescaptcha_api_key"] == ""
            assert client.get("/api/plugin/config", headers=headers).json()["config"]["connection_token"] == ""
            assert client.get("/api/proxy/config", headers=headers).json()["proxy_url"] == ""
            assert client.post("/api/admin/apikey", headers=headers, json={"new_api_key": "override"}).status_code == 409
            assert client.post("/api/admin/password", headers=headers, json={"old_password": "old", "new_password": "new"}).status_code == 409
            assert client.post("/api/proxy/config", headers=headers, json={"proxy_enabled": True, "proxy_url": "http://x:1"}).status_code == 409
            assert client.post("/api/captcha/config", headers=headers, json={
                "captcha_method": "yescaptcha", "yescaptcha_api_key": "do-not-store",
            }).status_code == 200
            assert client.post("/api/plugin/config", headers=headers, json={
                "connection_token": "do-not-store", "auto_enable_on_update": False,
            }).json()["connection_token"] == ""
    finally:
        admin.active_admin_tokens.discard(session)
        admin.set_dependencies(None, None, None, None, None)

    async def verify():
        assert (await database.get_captcha_config()).yescaptcha_api_key == ""
        assert (await database.get_plugin_config()).connection_token == ""
        assert await ProxyManager(database).get_request_proxy_url() == env_secrets["FLOW2API_PROXY_URL"]

    asyncio.run(verify())
