"""Stream URL Adapter — sağlayıcıya özgü URL formatını üretir."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .models import Stream, Provider


@dataclass
class StreamUrlParts:
    """Üretilen URL parçaları."""
    url: str
    headers: dict = None  # bazı sağlayıcılar token/header ister


class StreamUrlAdapter(ABC):
    """Sağlayıcıya özgü URL adaptörü arayüzü."""

    @abstractmethod
    def build_live_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        pass

    @abstractmethod
    def build_vod_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        pass

    @abstractmethod
    def build_series_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        pass

    def get_name(self) -> str:
        return self.__class__.__name__


class StandardXtreamAdapter(StreamUrlAdapter):
    """Standart Xtream Codes formatı: /live/user/pass/id.ts"""
    
    def build_live_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        url = f"{base}/live/{provider.username}/{pwd}/{stream.provider_stream_id}.ts"
        return StreamUrlParts(url=url)

    def build_vod_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        ext = stream.extension or "mp4"
        url = f"{base}/movie/{provider.username}/{pwd}/{stream.provider_stream_id}.{ext}"
        return StreamUrlParts(url=url)

    def build_series_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        url = f"{base}/series/{provider.username}/{pwd}/{stream.provider_stream_id}"
        return StreamUrlParts(url=url)


class HlsM3U8Adapter(StreamUrlAdapter):
    """HLS/M3U8 formatı: /live/user/pass/id.m3u8"""
    
    def build_live_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        url = f"{base}/live/{provider.username}/{pwd}/{stream.provider_stream_id}.m3u8"
        return StreamUrlParts(url=url)

    def build_vod_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        url = f"{base}/movie/{provider.username}/{pwd}/{stream.provider_stream_id}.m3u8"
        return StreamUrlParts(url=url)

    def build_series_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        url = f"{base}/series/{provider.username}/{pwd}/{stream.provider_stream_id}.m3u8"
        return StreamUrlParts(url=url)


class DirectSourceAdapter(StreamUrlAdapter):
    """Sağlayıcı `direct_source` alanı doluysa onu kullanır."""
    
    def _build(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        if stream.stream_source and stream.stream_source != "xtream":
            return StreamUrlParts(url=stream.stream_source)
        # fallback standard
        return StandardXtreamAdapter().build_live_url(provider, stream)

    def build_live_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return self._build(provider, stream)

    def build_vod_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        if stream.stream_source and stream.stream_source != "xtream":
            return StreamUrlParts(url=stream.stream_source)
        return StandardXtreamAdapter().build_vod_url(provider, stream)

    def build_series_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return StandardXtreamAdapter().build_series_url(provider, stream)


class CustomPathAdapter(StreamUrlAdapter):
    """Özel path template'i: provider config'inden alınır."""
    
    def __init__(self, live_template: str = None, vod_template: str = None, series_template: str = None):
        self.live_template = live_template or "/live/{username}/{password}/{stream_id}.ts"
        self.vod_template = vod_template or "/movie/{username}/{password}/{stream_id}.{ext}"
        self.series_template = series_template or "/series/{username}/{password}/{stream_id}"

    def _render(self, provider: Provider, stream: Stream, template: str) -> str:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        return base + template.format(
            username=provider.username,
            password=pwd,
            stream_id=stream.provider_stream_id,
            ext=stream.extension or "mp4",
            name=stream.name,
            provider_id=provider.id
        )

    def build_live_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return StreamUrlParts(url=self._render(provider, stream, self.live_template))

    def build_vod_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return StreamUrlParts(url=self._render(provider, stream, self.vod_template))

    def build_series_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return StreamUrlParts(url=self._render(provider, stream, self.series_template))


class M3UPlaylistAdapter(StreamUrlAdapter):
    """M3U playlist'ten URL pattern öğrenip kullanır."""
    
    def __init__(self, sample_m3u_url: str = None):
        self.sample_m3u_url = sample_m3u_url
        self._pattern_cache = {}

    def _extract_pattern(self, provider: Provider) -> dict:
        """M3U'den URL pattern'ini çıkar."""
        cache_key = provider.id
        if cache_key in self._pattern_cache:
            return self._pattern_cache[cache_key]
        
        # Bu adaptör sync sırasında M3U indirip pattern öğrenir
        # Şimdilik standard fallback
        pattern = {"live": "/live/{username}/{password}/{stream_id}.ts"}
        self._pattern_cache[cache_key] = pattern
        return pattern

    def build_live_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        from . import crypto_util
        pwd = crypto_util.decrypt(provider.password_enc)
        base = provider.server_url.rstrip("/")
        pattern = self._extract_pattern(provider).get("live", "/live/{username}/{password}/{stream_id}.ts")
        url = base + pattern.format(username=provider.username, password=pwd, stream_id=stream.provider_stream_id)
        return StreamUrlParts(url=url)

    def build_vod_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return StandardXtreamAdapter().build_vod_url(provider, stream)

    def build_series_url(self, provider: Provider, stream: Stream) -> StreamUrlParts:
        return StandardXtreamAdapter().build_series_url(provider, stream)


# ==================== ADAPTER REGISTRY ====================

_ADAPTER_REGISTRY = {
    "standard": StandardXtreamAdapter,
    "hls": HlsM3U8Adapter,
    "direct_source": DirectSourceAdapter,
    "custom_path": CustomPathAdapter,
    "m3u_learned": M3UPlaylistAdapter,
}

_ADAPTER_INSTANCES = {}  # provider_id -> instance


def register_adapter(name: str, adapter_class: type):
    """Yeni adaptör kaydet."""
    _ADAPTER_REGISTRY[name] = adapter_class


def get_adapter_class(name: str) -> type:
    return _ADAPTER_REGISTRY.get(name, StandardXtreamAdapter)


def get_adapter_for_provider(provider: Provider) -> StreamUrlAdapter:
    """Sağlayıcı için doğru adaptörü döndür (cache'li)."""
    if provider.id in _ADAPTER_INSTANCES:
        return _ADAPTER_INSTANCES[provider.id]
    
    # Provider config'inden adapter_type oku (models.py'ye eklenecek)
    adapter_type = getattr(provider, "adapter_type", "standard")
    adapter_class = get_adapter_class(adapter_type)
    
    # Custom parametreleri varsa al
    adapter_config = getattr(provider, "adapter_config", {}) or {}
    
    if adapter_type == "custom_path":
        instance = adapter_class(
            live_template=adapter_config.get("live_template"),
            vod_template=adapter_config.get("vod_template"),
            series_template=adapter_config.get("series_template"),
        )
    elif adapter_type == "m3u_learned":
        instance = adapter_class(sample_m3u_url=adapter_config.get("sample_m3u_url"))
    else:
        instance = adapter_class()
    
    _ADAPTER_INSTANCES[provider.id] = instance
    return instance


def clear_adapter_cache(provider_id: int = None):
    if provider_id:
        _ADAPTER_INSTANCES.pop(provider_id, None)
    else:
        _ADAPTER_INSTANCES.clear()