# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic
#
# Download chain:
#   1. Railway YT API  (RAILWAY_YT_API_URL / RAILWAY_YT_API_KEY)

import asyncio
import os
import re
import time as _time
from typing import Union

import aiohttp
from py_yt import Playlist, VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

from ishu import config, logger
from ishu.helpers import utils

# ── Config ────────────────────────────────────────────────────────────────────
RAILWAY_YT_API_URL  = getattr(config, "RAILWAY_YT_API_URL",  None)
RAILWAY_YT_API_KEY  = getattr(config, "RAILWAY_YT_API_KEY",  None)

DOWNLOAD_DIR        = "downloads"


# ── Link helpers ──────────────────────────────────────────────────────────────
def _normalize_youtube_link(
    link: str,
    base: str = "https://www.youtube.com/watch?v=",
) -> str:
    if not link:
        return ""
    cleaned = link.strip()
    if "youtube.com" not in cleaned and "youtu.be" not in cleaned:
        cleaned = base + cleaned
    cleaned = cleaned.split("&si=")[0].split("?si=")[0]
    if "&" in cleaned and "list=" not in cleaned:
        cleaned = cleaned.split("&")[0]
    return cleaned


def _extract_video_id(link: str) -> str | None:
    cleaned = _normalize_youtube_link(link)
    if not cleaned:
        return None
    if "v=" in cleaned:
        return cleaned.split("v=")[-1].split("&")[0]
    if "youtu.be/" in cleaned:
        return cleaned.split("youtu.be/")[-1].split("?")[0].split("&")[0]
    return cleaned if len(cleaned) == 11 else None


# ── Downloader: Railway YT API ────────────────────────────────────────────────
async def _railway_download(video_id: str, media_type: str) -> str | None:
    """
    Download via Railway self-hosted YouTube API.

    Auth: X-API-Key header (RAILWAY_YT_API_KEY) — optional if API is open.

    Audio flow:
      1. GET /play/audio?id=<id>  → proxied byte stream (200 = direct file)
      2. GET /audio?id=<id>       → JSON {"success": true, "audio": {"best_audio": {"url": "..."}}}
                                     then stream that URL

    Video flow:
      1. GET /play/video/hq?id=<id> → proxied byte stream
      2. GET /video/hq?id=<id>      → JSON {"success": true, "stream": {"url": "..."}}
                                       then stream that URL

    Returns local file path on success, None on failure.
    """
    if not RAILWAY_YT_API_URL:
        logger.error("Railway YT API not configured: RAILWAY_YT_API_URL is missing")
        return None

    ext        = "mp4" if media_type == "video" else "mp3"
    timeout_dl = 600   if media_type == "video" else 300
    file_path  = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    # Auth goes in the X-API-Key header, not as a query param
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if RAILWAY_YT_API_KEY:
        headers["X-API-Key"] = str(RAILWAY_YT_API_KEY)

    params = {"id": video_id}

    async def _stream_to_file(session: aiohttp.ClientSession, url: str) -> bool:
        """Stream bytes from url directly into file_path. Returns True on success."""
        try:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=timeout_dl)
            ) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as fobj:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            fobj.write(chunk)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        return True
                else:
                    logger.warning("Railway YT API %s → %s for %s", url.split("/")[-1], resp.status, video_id)
        except Exception as exc:
            logger.warning("Railway YT API stream error for %s: %s", video_id, exc)
        return False

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            if media_type == "audio":
                # Step 1: try the proxy endpoint (direct byte stream)
                if await _stream_to_file(session, f"{RAILWAY_YT_API_URL}/play/audio"):
                    logger.info("Railway YT API ✓ /play/audio %s → %s", video_id, file_path)
                    return file_path

                # Step 2: fallback — get JSON, extract best_audio URL, then stream it
                async with session.get(
                    f"{RAILWAY_YT_API_URL}/audio",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        stream_url = (
                            (data.get("audio") or {})
                            .get("best_audio", {})
                            .get("url")
                        )
                        if stream_url:
                            async with session.get(
                                stream_url,
                                timeout=aiohttp.ClientTimeout(total=timeout_dl),
                                allow_redirects=True,
                            ) as file_resp:
                                if file_resp.status == 200:
                                    with open(file_path, "wb") as fobj:
                                        async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                            fobj.write(chunk)
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        logger.info("Railway YT API ✓ /audio+stream %s → %s", video_id, file_path)
                                        return file_path
                    else:
                        logger.warning("Railway YT API /audio status %s for %s", resp.status, video_id)

            else:  # video
                # Step 1: try the proxy endpoint
                if await _stream_to_file(session, f"{RAILWAY_YT_API_URL}/play/video/hq"):
                    logger.info("Railway YT API ✓ /play/video/hq %s → %s", video_id, file_path)
                    return file_path

                # Step 2: fallback — get JSON stream URL
                async with session.get(
                    f"{RAILWAY_YT_API_URL}/video/hq",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        stream_url = (data.get("stream") or {}).get("url")
                        if stream_url:
                            async with session.get(
                                stream_url,
                                timeout=aiohttp.ClientTimeout(total=timeout_dl),
                                allow_redirects=True,
                            ) as file_resp:
                                if file_resp.status == 200:
                                    with open(file_path, "wb") as fobj:
                                        async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                            fobj.write(chunk)
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        logger.info("Railway YT API ✓ /video/hq+stream %s → %s", video_id, file_path)
                                        return file_path
                    else:
                        logger.warning("Railway YT API /video/hq status %s for %s", resp.status, video_id)

        return None

    except Exception as exc:
        logger.warning("Railway YT API download failed for %s: %s", video_id, exc)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
        return None



# ── Main download entrypoint ──────────────────────────────────────────────────
async def _download_with_fallback(
    link: str,
    media_type: str,
) -> tuple[str | None, str]:
    """
    Download via Railway YT API.
    Returns (file_path, downloader_name).
    """
    video_id = _extract_video_id(link) or link

    result = await _railway_download(video_id, media_type)
    if result:
        return result, "railway"

    logger.error("Railway YT API failed for: %s", video_id)
    return None, "none"


# ── Public helpers (kept for backward compat with play.py / calls.py) ─────────
async def download_song(link: str, title: str | None = None) -> str | None:
    path, _ = await _download_with_fallback(link, "audio")
    return path


async def download_video(link: str, title: str | None = None) -> str | None:
    path, _ = await _download_with_fallback(link, "video")
    return path


# ── YouTube class ─────────────────────────────────────────────────────────────
class YouTube:
    def __init__(self):
        self.base     = "https://www.youtube.com/watch?v="
        self.regex    = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.reg      = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self.api      = None
        self.dl_stats = {
            "total_requests": 0,
            "railway":        0,
            "existing_files": 0,
            "failed":         0,
        }

    # ── Validators ────────────────────────────────────────────────────────────
    def valid(self, url: str) -> bool:
        return bool(re.search(self.regex, url))

    def invalid(self, url: str) -> bool:
        return not self.valid(url)

    # ── URL utilities ─────────────────────────────────────────────────────────
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            text = message.text or message.caption or ""
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        return text[entity.offset: entity.offset + entity.length]
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    # ── Metadata fetchers ─────────────────────────────────────────────────────
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = _normalize_youtube_link(link)
        results = VideosSearch(link, limit=1)
        r = (await results.next())["result"][0]
        title        = r["title"]
        duration_min = r["duration"]
        thumbnail    = r["thumbnails"][0]["url"].split("?")[0]
        vidid        = r["id"]
        duration_sec = int(utils.to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str | None:
        if videoid:
            link = self.base + link
        link = _normalize_youtube_link(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            return r["title"]
        return None

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> str | None:
        if videoid:
            link = self.base + link
        link = _normalize_youtube_link(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            return r["duration"]
        return None

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str | None:
        if videoid:
            link = self.base + link
        link = _normalize_youtube_link(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            return r["thumbnails"][0]["url"].split("?")[0]
        return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = _normalize_youtube_link(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            track_details = {
                "title":        r["title"],
                "link":         r["link"],
                "vidid":        r["id"],
                "duration_min": r["duration"],
                "thumb":        r["thumbnails"][0]["url"].split("?")[0],
            }
            return track_details, r["id"]
        return None, None

    async def search(
        self,
        query: str,
        message_id: int,
        video: bool = False,
    ):
        """Search YouTube and return a Track dataclass or None."""
        from ishu.helpers._dataclass import Track

        try:
            results = VideosSearch(query.strip(), limit=1)
            result  = (await results.next())["result"]
            if not result:
                return None
            r            = result[0]
            vidid        = r["id"]
            duration_min = r.get("duration") or "00:00"
            duration_sec = int(utils.to_seconds(duration_min)) if duration_min else 0
            return Track(
                id           = vidid,
                title        = r["title"],
                url          = r.get("link", self.base + vidid),
                duration     = duration_min,
                duration_sec = duration_sec,
                thumbnail    = r["thumbnails"][0]["url"].split("?")[0],
                channel_name = (r.get("channel") or {}).get("name", ""),
                message_id   = message_id,
                video        = video,
                time         = int(_time.time()),
            )
        except Exception as e:
            logger.warning("YouTube search error for '%s': %s", query, e)
            return None

    # ── Slider ────────────────────────────────────────────────────────────────
    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link        = _normalize_youtube_link(link)
        search      = VideosSearch(link, limit=10)
        raw_results = (await search.next()).get("result", [])

        filtered = []
        for item in raw_results:
            duration_str = item.get("duration") or "0:00"
            parts = duration_str.split(":")
            try:
                if len(parts) == 3:
                    secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:
                    secs = int(parts[0]) * 60 + int(parts[1])
                else:
                    secs = 0
            except (ValueError, IndexError):
                continue
            if 0 < secs <= 3600:
                filtered.append(item)

        if not filtered or query_type >= len(filtered):
            raise ValueError("No suitable videos found within duration limit")

        s = filtered[query_type]
        return s["title"], s.get("duration") or "0:00", s["thumbnails"][0]["url"].split("?")[0], s["id"]

    # ── Video stream URL ──────────────────────────────────────────────────────
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = _normalize_youtube_link(link)
        video_id = _extract_video_id(link) or link
        if not RAILWAY_YT_API_URL:
            return 0, "Railway YT API not configured"
        # Build params — only include api_key when it is actually set
        params: dict = {"id": video_id}
        if RAILWAY_YT_API_KEY:
            params["api_key"] = str(RAILWAY_YT_API_KEY)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{RAILWAY_YT_API_URL}/play/video/hq",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=False,
                ) as resp:
                    if resp.status in (200, 302, 301):
                        stream_url = resp.headers.get("Location") or str(resp.url)
                        return 1, stream_url
                    return 0, f"Railway API returned {resp.status}"
        except Exception as exc:
            return 0, str(exc)

    # ── Download (main method called by play.py / calls.py) ──────────────────
    async def download(
        self,
        video_id: str,
        video: bool = False,
        title: str | None = None,
    ) -> str | None:
        """
        Download audio/video by video_id via Railway YT API.
        Returns file path or None.
        """
        self.dl_stats["total_requests"] += 1
        link = _normalize_youtube_link(video_id, self.base)

        try:
            result, downloader = await _download_with_fallback(link, "video" if video else "audio")
            if result:
                self.dl_stats[downloader] += 1
                logger.info(
                    "YouTube.download success: %s (%s) via %s",
                    video_id,
                    "video" if video else "audio",
                    downloader,
                )
            else:
                self.dl_stats["failed"] += 1
            return result
        except Exception as e:
            self.dl_stats["failed"] += 1
            logger.warning("YouTube.download error for '%s': %s", video_id, e)
            return None

    # ── Playlist ──────────────────────────────────────────────────────────────
    async def playlist(
        self,
        limit: int,
        mention: str,
        link: str,
        video: bool = False,
    ) -> list:
        """Fetch playlist tracks, return list of Track dataclasses."""
        from ishu.helpers._dataclass import Track

        link = _normalize_youtube_link(link)
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []

        tracks = []
        for data in (plist.get("videos") or [])[:limit]:
            if not data:
                continue
            vidid = data.get("id")
            if not vidid:
                continue
            duration_min = data.get("duration") or "00:00"
            duration_sec = int(utils.to_seconds(duration_min)) if duration_min else 0
            thumbs       = data.get("thumbnails") or []
            thumbnail    = thumbs[0].get("url", "").split("?")[0] if thumbs else ""
            tracks.append(Track(
                id           = vidid,
                title        = data.get("title") or vidid,
                url          = data.get("link") or self.base + vidid,
                duration     = duration_min,
                duration_sec = duration_sec,
                thumbnail    = thumbnail,
                user         = mention,
                video        = video,
                time         = int(_time.time()),
            ))
        return tracks
