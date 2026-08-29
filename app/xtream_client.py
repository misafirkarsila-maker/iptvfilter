"""Xtream Codes provider istemcisi — sağlayıcıdan içerik çeker (proxy YAPMAZ)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=15.0)


class XtreamClient:
    def __init__(self, server_url: str, username: str, password: str):
        # Server URL sonunda / varsa temizle
        self.base = server_url.rstrip("/")
        self.username = username
        self.password = password

    # ---- yardımcılar ----
    def build_player_api_url(self) -> str:
        return f"{self.base}/player_api.php?username={self.username}&password={self.password}"

    def _stream_url(self, kind: str, *ids) -> str:
        """Sağlayıcının orijinal stream URL'sini üretir. (Direct URL — proxy YOK)"""
        id_str = "/".join(str(i) for i in ids)
        return (
            f"{self.base}/{kind}/{self.username}/{self.password}/{id_str}"
        )

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = path if path.startswith("http") else (
            f"{self.base}/{path}?username={self.username}&password={self.password}"
        )
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}" + "&".join(f"{k}={v}" for k, v in params.items())
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()

    # ---- Xtream Codes endpoints ----
    def get_auth(self) -> dict:
        return self._get("player_api.php")

    def get_live_categories(self) -> list[dict]:
        return self._get("player_api.php", {"action": "get_live_categories"})

    def get_live_streams(self) -> list[dict]:
        return self._get("player_api.php", {"action": "get_live_streams"})

    def get_vod_categories(self) -> list[dict]:
        return self._get("player_api.php", {"action": "get_vod_categories"})

    def get_vod_streams(self) -> list[dict]:
        return self._get("player_api.php", {"action": "get_vod_streams"})

    def get_series_categories(self) -> list[dict]:
        return self._get("player_api.php", {"action": "get_series_categories"})

    def get_series(self) -> list[dict]:
        return self._get("player_api.php", {"action": "get_series"})

    def get_epg(self, stream_ids: list[str], limit: int = 50000) -> list[dict]:
        """EPG bilgisi. stream_id CSV olarak gönderilir (chunked)."""
        all_programs: list[dict] = []
        # Tüm id'leri tek istekte topla (bazı sağlayıcılar kısıtlıyorsa chunk)
        ids_csv = ",".join(stream_ids)
        params = {
            "action": "get_short_epg",
            "stream_id": ids_csv,
            "limit": limit,
        }
        try:
            data = self._get("player_api.php", params)
            if isinstance(data, dict):
                data = data.get("epg_listings", [])
            if isinstance(data, list):
                all_programs.extend(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("EPG get_short_epg başarısız (%s), tekli deneme: %s", self.base, exc)
            # Tek tek deneyerek kısmi topla
            for sid in stream_ids[:200]:
                try:
                    p = self._get(
                        "player_api.php",
                        {"action": "get_short_epg", "stream_id": sid, "limit": limit},
                    )
                    if isinstance(p, dict):
                        p = p.get("epg_listings", [])
                    if isinstance(p, list):
                        all_programs.extend(p)
                except Exception:  # noqa: BLE001
                    continue
        return all_programs

    def build_live_url(self, stream_id) -> str:
        return self._stream_url("live", stream_id)

    def build_vod_url(self, stream_id, extension: str = "mp4") -> str:
        return self._stream_url("movie", stream_id, extension)

    def build_series_url(self, series_id, season, episode) -> str:
        return self._stream_url("series", series_id, season, episode)
