# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic
#
# YouTube Download / Stream Handler
# Uses YT_STREAM_GATEWAY from config.py

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


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

YOUTUBE_API_KEY = getattr(config, "YOUTUBE_API_KEY", None)

YT_STREAM_GATEWAY = getattr(
    config,
    "YT_STREAM_GATEWAY",
    "https://vbit-api-store.vercel.app/api/v1/yt",
)

DOWNLOAD_DIR = "downloads"


# ─────────────────────────────────────────────────────────────────────────────
# LINK HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_youtube_link(
    link: str,
    base: str = "https://www.youtube.com/watch?v=",
) -> str:
    if not link:
        return ""

    cleaned = str(link).strip()

    if "youtube.com" not in cleaned and "youtu.be" not in cleaned:
        cleaned = base + cleaned

    cleaned = cleaned.split("&si=")[0]
    cleaned = cleaned.split("?si=")[0]

    if "&" in cleaned and "list=" not in cleaned:
        cleaned = cleaned.split("&")[0]

    return cleaned


def _extract_video_id(link: str) -> str | None:
    cleaned = _normalize_youtube_link(link)

    if not cleaned:
        return None

    if "v=" in cleaned:
        return cleaned.split("v=", 1)[1].split("&")[0]

    if "youtu.be/" in cleaned:
        return (
            cleaned.split("youtu.be/", 1)[1]
            .split("?")[0]
            .split("&")[0]
        )

    return cleaned if len(cleaned) == 11 else None


# ─────────────────────────────────────────────────────────────────────────────
# HTTP HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _api_headers() -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    if YOUTUBE_API_KEY:
        headers["X-API-Key"] = str(YOUTUBE_API_KEY)

    return headers


async def _save_response_to_file(
    response: aiohttp.ClientResponse,
    file_path: str,
) -> bool:
    try:
        if response.status != 200:
            return False

        with open(file_path, "wb") as file:
            async for chunk in response.content.iter_chunked(1024 * 1024):
                if chunk:
                    file.write(chunk)

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 0
        ):
            return True

    except Exception as exc:
        logger.warning(
            "File write error: %s",
            exc,
        )

    return False


# ─────────────────────────────────────────────────────────────────────────────
# YOUTUBE API DOWNLOADER
# ─────────────────────────────────────────────────────────────────────────────

async def _railway_download(
    video_id: str,
    media_type: str,
) -> str | None:
    """
    Download audio/video using YT_STREAM_GATEWAY.

    Audio:
        /play/audio?id=VIDEO_ID
        fallback:
        /audio?id=VIDEO_ID

    Video:
        /play/video/hq?id=VIDEO_ID
        fallback:
        /video/hq?id=VIDEO_ID
    """

    if not YT_STREAM_GATEWAY:
        logger.error(
            "YouTube API not configured: YT_STREAM_GATEWAY is missing"
        )
        return None

    video_id = str(video_id).strip()

    if not video_id:
        return None

    if media_type not in ("audio", "video"):
        logger.warning(
            "Invalid media type: %s",
            media_type,
        )
        return None

    extension = "mp4" if media_type == "video" else "mp3"

    timeout_dl = (
        600
        if media_type == "video"
        else 300
    )

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{video_id}.{extension}",
    )

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True,
    )

    # Existing file
    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 0
    ):
        logger.info(
            "Existing file found: %s",
            file_path,
        )
        return file_path

    base_url = YT_STREAM_GATEWAY.rstrip("/")

    headers = _api_headers()

    params = {
        "id": video_id,
    }

    async def stream_endpoint(
        session: aiohttp.ClientSession,
        endpoint: str,
        timeout: int,
    ) -> bool:
        try:
            async with session.get(
                endpoint,
                params=params,
                timeout=aiohttp.ClientTimeout(
                    total=timeout
                ),
                allow_redirects=True,
            ) as response:

                if response.status == 200:
                    success = await _save_response_to_file(
                        response,
                        file_path,
                    )

                    if success:
                        return True

                logger.warning(
                    "YouTube API %s returned HTTP %s for %s",
                    endpoint,
                    response.status,
                    video_id,
                )

        except asyncio.TimeoutError:
            logger.warning(
                "YouTube API timeout for %s",
                video_id,
            )

        except aiohttp.ClientError as exc:
            logger.warning(
                "YouTube API connection error for %s: %s",
                video_id,
                exc,
            )

        except Exception as exc:
            logger.warning(
                "YouTube API stream error for %s: %s",
                video_id,
                exc,
            )

        return False

    try:
        async with aiohttp.ClientSession(
            headers=headers
        ) as session:

            # ─────────────────────────────────────────
            # AUDIO
            # ─────────────────────────────────────────

            if media_type == "audio":

                # Direct proxy
                audio_play_url = (
                    f"{base_url}/play/audio"
                )

                if await stream_endpoint(
                    session,
                    audio_play_url,
                    timeout_dl,
                ):
                    logger.info(
                        "YouTube API ✓ /play/audio %s → %s",
                        video_id,
                        file_path,
                    )
                    return file_path

                # JSON fallback
                audio_api_url = (
                    f"{base_url}/audio"
                )

                try:
                    async with session.get(
                        audio_api_url,
                        params=params,
                        timeout=aiohttp.ClientTimeout(
                            total=30
                        ),
                    ) as response:

                        if response.status != 200:
                            logger.warning(
                                "YouTube API /audio returned %s for %s",
                                response.status,
                                video_id,
                            )
                            return None

                        data = await response.json(
                            content_type=None
                        )

                        audio_data = (
                            data.get("audio")
                            or {}
                        )

                        best_audio = (
                            audio_data.get(
                                "best_audio"
                            )
                            or {}
                        )

                        stream_url = (
                            best_audio.get("url")
                        )

                        if not stream_url:
                            logger.warning(
                                "No audio stream URL returned for %s",
                                video_id,
                            )
                            return None

                        try:
                            async with session.get(
                                stream_url,
                                timeout=aiohttp.ClientTimeout(
                                    total=timeout_dl
                                ),
                                allow_redirects=True,
                            ) as file_response:

                                if await _save_response_to_file(
                                    file_response,
                                    file_path,
                                ):
                                    logger.info(
                                        "YouTube API ✓ /audio stream %s → %s",
                                        video_id,
                                        file_path,
                                    )
                                    return file_path

                                logger.warning(
                                    "Audio stream returned HTTP %s for %s",
                                    file_response.status,
                                    video_id,
                                )

                        except Exception as exc:
                            logger.warning(
                                "Audio stream error for %s: %s",
                                video_id,
                                exc,
                            )

                except Exception as exc:
                    logger.warning(
                        "YouTube API /audio error for %s: %s",
                        video_id,
                        exc,
                    )

            # ─────────────────────────────────────────
            # VIDEO
            # ─────────────────────────────────────────

            else:

                # Direct proxy
                video_play_url = (
                    f"{base_url}/play/video/hq"
                )

                if await stream_endpoint(
                    session,
                    video_play_url,
                    timeout_dl,
                ):
                    logger.info(
                        "YouTube API ✓ /play/video/hq %s → %s",
                        video_id,
                        file_path,
                    )
                    return file_path

                # JSON fallback
                video_api_url = (
                    f"{base_url}/video/hq"
                )

                try:
                    async with session.get(
                        video_api_url,
                        params=params,
                        timeout=aiohttp.ClientTimeout(
                            total=30
                        ),
                    ) as response:

                        if response.status != 200:
                            logger.warning(
                                "YouTube API /video/hq returned %s for %s",
                                response.status,
                                video_id,
                            )
                            return None

                        data = await response.json(
                            content_type=None
                        )

                        stream_data = (
                            data.get("stream")
                            or {}
                        )

                        stream_url = (
                            stream_data.get("url")
                        )

                        if not stream_url:
                            logger.warning(
                                "No video stream URL returned for %s",
                                video_id,
                            )
                            return None

                        try:
                            async with session.get(
                                stream_url,
                                timeout=aiohttp.ClientTimeout(
                                    total=timeout_dl
                                ),
                                allow_redirects=True,
                            ) as file_response:

                                if await _save_response_to_file(
                                    file_response,
                                    file_path,
                                ):
                                    logger.info(
                                        "YouTube API ✓ /video/hq stream %s → %s",
                                        video_id,
                                        file_path,
                                    )
                                    return file_path

                                logger.warning(
                                    "Video stream returned HTTP %s for %s",
                                    file_response.status,
                                    video_id,
                                )

                        except Exception as exc:
                            logger.warning(
                                "Video stream error for %s: %s",
                                video_id,
                                exc,
                            )

                except Exception as exc:
                    logger.warning(
                        "YouTube API /video/hq error for %s: %s",
                        video_id,
                        exc,
                    )

    except Exception as exc:
        logger.warning(
            "YouTube API download failed for %s: %s",
            video_id,
            exc,
        )

    # Remove incomplete file
    try:
        if os.path.exists(file_path):
            if os.path.getsize(file_path) <= 0:
                os.remove(file_path)
    except OSError:
        pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DOWNLOAD FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

async def _download_with_fallback(
    link: str,
    media_type: str,
) -> tuple[str | None, str]:

    video_id = _extract_video_id(link)

    if not video_id:
        video_id = str(link).strip()

    if not video_id:
        return None, "none"

    result = await _railway_download(
        video_id,
        media_type,
    )

    if result:
        return result, "YouTube"

    logger.error(
        "YouTube API failed for: %s",
        video_id,
    )

    return None, "none"


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC DOWNLOAD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def download_song(
    link: str,
    title: str | None = None,
) -> str | None:

    path, _ = await _download_with_fallback(
        link,
        "audio",
    )

    return path


async def download_video(
    link: str,
    title: str | None = None,
) -> str | None:

    path, _ = await _download_with_fallback(
        link,
        "video",
    )

    return path


# ─────────────────────────────────────────────────────────────────────────────
# YOUTUBE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class YouTube:

    def __init__(self):

        self.base = (
            "https://www.youtube.com/watch?v="
        )

        self.regex = (
            r"(?:youtube\.com|youtu\.be)"
        )

        self.listbase = (
            "https://youtube.com/playlist?list="
        )

        self.reg = re.compile(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
        )

        self.api = None

        self.dl_stats = {
            "total_requests": 0,
            "YouTube": 0,
            "existing_files": 0,
            "failed": 0,
        }

    # ─────────────────────────────────────────────
    # VALIDATORS
    # ─────────────────────────────────────────────

    def valid(self, url: str) -> bool:
        if not url:
            return False

        return bool(
            re.search(
                self.regex,
                url,
                re.IGNORECASE,
            )
        )

    def invalid(self, url: str) -> bool:
        return not self.valid(url)

    # ─────────────────────────────────────────────
    # EXISTS
    # ─────────────────────────────────────────────

    async def exists(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ) -> bool:

        if videoid:
            link = self.base + str(link)

        return bool(
            re.search(
                self.regex,
                link or "",
                re.IGNORECASE,
            )
        )

    # ─────────────────────────────────────────────
    # URL
    # ─────────────────────────────────────────────

    async def url(
        self,
        message_1: Message,
    ) -> Union[str, None]:

        messages = [message_1]

        if message_1.reply_to_message:
            messages.append(
                message_1.reply_to_message
            )

        for message in messages:

            text = (
                message.text
                or message.caption
                or ""
            )

            # Text entities
            if message.entities:

                for entity in message.entities:

                    if entity.type == MessageEntityType.URL:

                        return text[
                            entity.offset:
                            entity.offset + entity.length
                        ]

                    if (
                        entity.type
                        == MessageEntityType.TEXT_LINK
                    ):
                        return entity.url

            # Caption entities
            if message.caption_entities:

                for entity in message.caption_entities:

                    if (
                        entity.type
                        == MessageEntityType.TEXT_LINK
                    ):
                        return entity.url

        return None

    # ─────────────────────────────────────────────
    # DETAILS
    # ─────────────────────────────────────────────

    async def details(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        results = VideosSearch(
            link,
            limit=1,
        )

        data = await results.next()

        result = data.get("result", [])

        if not result:
            raise ValueError(
                "No YouTube result found"
            )

        r = result[0]

        title = r.get("title")
        duration_min = r.get("duration")

        thumbnails = (
            r.get("thumbnails")
            or []
        )

        thumbnail = (
            thumbnails[0].get("url", "").split("?")[0]
            if thumbnails
            else ""
        )

        vidid = r.get("id")

        duration_sec = (
            int(utils.to_seconds(duration_min))
            if duration_min
            else 0
        )

        return (
            title,
            duration_min,
            duration_sec,
            thumbnail,
            vidid,
        )

    # ─────────────────────────────────────────────
    # TITLE
    # ─────────────────────────────────────────────

    async def title(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ) -> str | None:

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        results = VideosSearch(
            link,
            limit=1,
        )

        data = await results.next()

        for r in data.get("result", []):
            return r.get("title")

        return None

    # ─────────────────────────────────────────────
    # DURATION
    # ─────────────────────────────────────────────

    async def duration(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ) -> str | None:

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        results = VideosSearch(
            link,
            limit=1,
        )

        data = await results.next()

        for r in data.get("result", []):
            return r.get("duration")

        return None

    # ─────────────────────────────────────────────
    # THUMBNAIL
    # ─────────────────────────────────────────────

    async def thumbnail(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ) -> str | None:

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        results = VideosSearch(
            link,
            limit=1,
        )

        data = await results.next()

        for r in data.get("result", []):

            thumbnails = (
                r.get("thumbnails")
                or []
            )

            if thumbnails:
                return (
                    thumbnails[0]
                    .get("url", "")
                    .split("?")[0]
                )

        return None

    # ─────────────────────────────────────────────
    # TRACK
    # ─────────────────────────────────────────────

    async def track(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        results = VideosSearch(
            link,
            limit=1,
        )

        data = await results.next()

        result = data.get("result", [])

        if not result:
            return None, None

        r = result[0]

        thumbnails = (
            r.get("thumbnails")
            or []
        )

        thumbnail = (
            thumbnails[0]
            .get("url", "")
            .split("?")[0]
            if thumbnails
            else ""
        )

        track_details = {
            "title": r.get("title", ""),
            "link": r.get(
                "link",
                self.base + r.get("id", ""),
            ),
            "vidid": r.get("id"),
            "duration_min": r.get(
                "duration"
            ),
            "thumb": thumbnail,
        }

        return track_details, r.get("id")

    # ─────────────────────────────────────────────
    # SEARCH
    # ─────────────────────────────────────────────

    async def search(
        self,
        query: str,
        message_id: int,
        video: bool = False,
    ):

        from ishu.helpers._dataclass import Track

        try:

            results = VideosSearch(
                query.strip(),
                limit=1,
            )

            data = await results.next()

            result = data.get("result", [])

            if not result:
                return None

            r = result[0]

            vidid = r.get("id")

            duration_min = (
                r.get("duration")
                or "00:00"
            )

            duration_sec = (
                int(utils.to_seconds(duration_min))
                if duration_min
                else 0
            )

            thumbnails = (
                r.get("thumbnails")
                or []
            )

            thumbnail = (
                thumbnails[0]
                .get("url", "")
                .split("?")[0]
                if thumbnails
                else ""
            )

            channel = (
                r.get("channel")
                or {}
            )

            return Track(
                id=vidid,
                title=r.get(
                    "title",
                    vidid,
                ),
                url=r.get(
                    "link",
                    self.base + vidid,
                ),
                duration=duration_min,
                duration_sec=duration_sec,
                thumbnail=thumbnail,
                channel_name=channel.get(
                    "name",
                    "",
                ),
                message_id=message_id,
                video=video,
                time=int(_time.time()),
            )

        except Exception as exc:

            logger.warning(
                "YouTube search error for '%s': %s",
                query,
                exc,
            )

            return None

    # ─────────────────────────────────────────────
    # SLIDER
    # ─────────────────────────────────────────────

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        search = VideosSearch(
            link,
            limit=10,
        )

        data = await search.next()

        raw_results = data.get(
            "result",
            [],
        )

        filtered = []

        for item in raw_results:

            duration_str = (
                item.get("duration")
                or "0:00"
            )

            parts = duration_str.split(":")

            try:

                if len(parts) == 3:

                    secs = (
                        int(parts[0]) * 3600
                        + int(parts[1]) * 60
                        + int(parts[2])
                    )

                elif len(parts) == 2:

                    secs = (
                        int(parts[0]) * 60
                        + int(parts[1])
                    )

                else:
                    secs = 0

            except (
                ValueError,
                IndexError,
            ):
                continue

            if 0 < secs <= 3600:
                filtered.append(item)

        if (
            not filtered
            or query_type >= len(filtered)
        ):
            raise ValueError(
                "No suitable videos found within duration limit"
            )

        selected = filtered[query_type]

        thumbnails = (
            selected.get("thumbnails")
            or []
        )

        thumbnail = (
            thumbnails[0]
            .get("url", "")
            .split("?")[0]
            if thumbnails
            else ""
        )

        return (
            selected.get("title", ""),
            selected.get(
                "duration",
                "0:00",
            ),
            thumbnail,
            selected.get("id"),
        )

    # ─────────────────────────────────────────────
    # VIDEO STREAM URL
    # ─────────────────────────────────────────────

    async def video(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        link = _normalize_youtube_link(link)

        video_id = (
            _extract_video_id(link)
            or link
        )

        if not YT_STREAM_GATEWAY:

            return (
                0,
                "YouTube API not configured",
            )

        base_url = (
            YT_STREAM_GATEWAY.rstrip("/")
        )

        params = {
            "id": video_id,
        }

        headers = _api_headers()

        try:

            async with aiohttp.ClientSession(
                headers=headers
            ) as session:

                async with session.get(
                    f"{base_url}/play/video/hq",
                    params=params,
                    timeout=aiohttp.ClientTimeout(
                        total=30
                    ),
                    allow_redirects=False,
                ) as response:

                    if response.status in (
                        200,
                        301,
                        302,
                        303,
                        307,
                        308,
                    ):

                        location = (
                            response.headers.get(
                                "Location"
                            )
                        )

                        if location:
                            return 1, location

                        return (
                            1,
                            str(response.url),
                        )

                    return (
                        0,
                        f"YouTube API returned {response.status}",
                    )

        except Exception as exc:

            logger.warning(
                "YouTube.video error for %s: %s",
                video_id,
                exc,
            )

            return 0, str(exc)

    # ─────────────────────────────────────────────
    # DOWNLOAD
    # ─────────────────────────────────────────────

    async def download(
        self,
        video_id: str,
        video: bool = False,
        title: str | None = None,
    ) -> str | None:

        self.dl_stats[
            "total_requests"
        ] += 1

        link = _normalize_youtube_link(
            video_id,
            self.base,
        )

        try:

            result, downloader = (
                await _download_with_fallback(
                    link,
                    "video"
                    if video
                    else "audio",
                )
            )

            if result:

                self.dl_stats[
                    downloader
                ] = (
                    self.dl_stats.get(
                        downloader,
                        0,
                    )
                    + 1
                )

                logger.info(
                    "YouTube.download success: "
                    "%s (%s) via %s",
                    video_id,
                    "video"
                    if video
                    else "audio",
                    downloader,
                )

            else:

                self.dl_stats[
                    "failed"
                ] += 1

            return result

        except Exception as exc:

            self.dl_stats[
                "failed"
            ] += 1

            logger.warning(
                "YouTube.download error for '%s': %s",
                video_id,
                exc,
            )

            return None

    # ─────────────────────────────────────────────
    # PLAYLIST
    # ─────────────────────────────────────────────

    async def playlist(
        self,
        limit: int,
        mention: str,
        link: str,
        video: bool = False,
    ) -> list:

        from ishu.helpers._dataclass import Track

        link = _normalize_youtube_link(link)

        try:

            plist = await Playlist.get(link)

        except Exception as exc:

            logger.warning(
                "Playlist error: %s",
                exc,
            )

            return []

        tracks = []

        for data in (
            plist.get("videos")
            or []
        )[:limit]:

            if not data:
                continue

            vidid = data.get("id")

            if not vidid:
                continue

            duration_min = (
                data.get("duration")
                or "00:00"
            )

            try:

                duration_sec = (
                    int(
                        utils.to_seconds(
                            duration_min
                        )
                    )
                    if duration_min
                    else 0
                )

            except Exception:

                duration_sec = 0

            thumbs = (
                data.get("thumbnails")
                or []
            )

            thumbnail = (
                thumbs[0]
                .get("url", "")
                .split("?")[0]
                if thumbs
                else ""
            )

            tracks.append(
                Track(
                    id=vidid,
                    title=data.get(
                        "title",
                        vidid,
                    ),
                    url=data.get(
                        "link",
                        self.base + vidid,
                    ),
                    duration=duration_min,
                    duration_sec=duration_sec,
                    thumbnail=thumbnail,
                    user=mention,
                    video=video,
                    time=int(_time.time()),
                )
            )

        return tracks
