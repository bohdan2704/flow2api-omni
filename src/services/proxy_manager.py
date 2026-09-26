"""Proxy management module"""
from typing import Optional
import re
import os
from ..core.config import config as app_config
from ..core.database import Database
from ..core.models import ProxyConfig
from ..shared.proxy_parse import parse_proxy_line

class ProxyManager:
    """Proxy configuration manager"""

    def __init__(self, db: Database):
        self.db = db

    def _parse_proxy_line(self, line: str) -> Optional[str]:
        """委托 shared.proxy_parse。"""
        return parse_proxy_line(line)

    def normalize_proxy_url(self, proxy_url: Optional[str]) -> Optional[str]:
        """标准化代理地址，空值返回 None，非法格式抛 ValueError。"""
        if proxy_url is None:
            return None

        raw = proxy_url.strip()
        if not raw:
            return None

        parsed = self._parse_proxy_line(raw)
        if not parsed:
            raise ValueError(
                "代理地址格式错误，支持示例："
                "http://user:pass@host:port / "
                "socks5://user:pass@host:port / "
                "host:port:user:pass / st5 host:port:user:pass"
            )
        return parsed

    async def get_proxy_url(self) -> Optional[str]:
        """兼容旧调用：返回请求代理地址"""
        return await self.get_request_proxy_url()

    async def get_request_proxy_url(self) -> Optional[str]:
        """Get request proxy URL if enabled, otherwise return None"""
        if app_config.secrets_from_env:
            return self.normalize_proxy_url(os.environ.get("FLOW2API_PROXY_URL"))
        config = await self.db.get_proxy_config()
        if config and config.enabled and config.proxy_url:
            return config.proxy_url
        return None

    async def get_media_proxy_url(self) -> Optional[str]:
        """Get media upload/download proxy URL, fallback to request proxy"""
        if app_config.secrets_from_env:
            media_url = self.normalize_proxy_url(os.environ.get("FLOW2API_MEDIA_PROXY_URL"))
            return media_url or await self.get_request_proxy_url()
        config = await self.db.get_proxy_config()
        if config and config.media_proxy_enabled and config.media_proxy_url:
            return config.media_proxy_url
        return await self.get_request_proxy_url()

    async def update_proxy_config(
        self,
        enabled: bool,
        proxy_url: Optional[str],
        media_proxy_enabled: Optional[bool] = None,
        media_proxy_url: Optional[str] = None
    ):
        """Update proxy configuration"""
        normalized_proxy_url = self.normalize_proxy_url(proxy_url)
        normalized_media_proxy_url = self.normalize_proxy_url(media_proxy_url)

        await self.db.update_proxy_config(
            enabled=enabled,
            proxy_url=normalized_proxy_url,
            media_proxy_enabled=media_proxy_enabled,
            media_proxy_url=normalized_media_proxy_url
        )

    async def get_proxy_config(self) -> ProxyConfig:
        """Get proxy configuration"""
        if app_config.secrets_from_env:
            request_url = await self.get_request_proxy_url()
            media_url = self.normalize_proxy_url(os.environ.get("FLOW2API_MEDIA_PROXY_URL"))
            return ProxyConfig(enabled=bool(request_url), proxy_url=request_url,
                               media_proxy_enabled=bool(media_url), media_proxy_url=media_url)
        return await self.db.get_proxy_config()
