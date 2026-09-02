from os import getenv
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):

        # ─────────────────────────────────────────────
        # Telegram
        # ─────────────────────────────────────────────

        self.API_ID = int(getenv("API_ID", 0))
        self.API_HASH = getenv("API_HASH")
        self.BOT_TOKEN = getenv("BOT_TOKEN")

        # ─────────────────────────────────────────────
        # Database
        # ─────────────────────────────────────────────

        self.MONGO_URL = getenv("MONGO_URL")

        # ─────────────────────────────────────────────
        # IDs
        # ─────────────────────────────────────────────

        self.LOGGER_ID = int(getenv("LOGGER_ID", 0))
        self.OWNER_ID = int(getenv("OWNER_ID", 0))

        # ─────────────────────────────────────────────
        # Limits
        # ─────────────────────────────────────────────

        self.DURATION_LIMIT = (
            int(getenv("DURATION_LIMIT", 120)) * 60
        )

        self.QUEUE_LIMIT = int(
            getenv("QUEUE_LIMIT", 20)
        )

        self.PLAYLIST_LIMIT = int(
            getenv("PLAYLIST_LIMIT", 20)
        )

        # ─────────────────────────────────────────────
        # Assistant Sessions
        # ─────────────────────────────────────────────

        self.SESSION1 = getenv("SESSION", None)
        self.SESSION2 = getenv("SESSION2", None)
        self.SESSION3 = getenv("SESSION3", None)

        # ─────────────────────────────────────────────
        # Support
        # ─────────────────────────────────────────────

        self.SUPPORT_CHANNEL = getenv(
            "SUPPORT_CHANNEL",
            "https://t.me/annu_updates",
        )

        self.SUPPORT_CHAT = getenv(
            "SUPPORT_CHAT",
            "https://t.me/annu_support",
        )

        # ─────────────────────────────────────────────
        # YouTube API
        # ─────────────────────────────────────────────

        default_yt_url = (
            "https://vbit-api-store.vercel.app/api/v1/yt"
        )

        # Preferred variable
        _raw_url = getenv(
            "YT_STREAM_GATEWAY",
            None,
        )

        # Backward compatibility
        if not _raw_url:
            _raw_url = getenv(
                "YOUTUBE_YT_API_URL",
                default_yt_url,
            )

        # Prevent API key accidentally being used as URL
        if _raw_url and not _raw_url.startswith(
            ("http://", "https://")
        ):
            _raw_url = default_yt_url

        self.YT_STREAM_GATEWAY = (
            _raw_url.rstrip("/")
            if _raw_url
            else default_yt_url
        )

        # Old variable name compatibility
        self.YOUTUBE_YT_API_URL = (
            self.YT_STREAM_GATEWAY
        )

        # API Key
        self.YOUTUBE_API_KEY = getenv(
            "YOUTUBE_API_KEY",
            getenv("YOUTUBE_YT_API_KEY", None),
        )

        # Old API-key variable compatibility
        self.YOUTUBE_YT_API_KEY = (
            self.YOUTUBE_API_KEY
        )

        self.RAILWAY_YT_API_URL = (
            self.YT_STREAM_GATEWAY
        )

        self.RAILWAY_YT_API_KEY = (
            self.YOUTUBE_API_KEY
        )

        # ─────────────────────────────────────────────
        # Images
        # ─────────────────────────────────────────────

        self.DEFAULT_THUMB = getenv(
            "DEFAULT_THUMB",
            "https://te.legra.ph/file/3e40a408286d4eda24191.jpg",
        )

        self.PING_IMG = getenv(
            "PING_IMG",
            "https://d.uguu.se/QmhEjBZF.jpg",
        )

        self.START_IMG = getenv(
            "START_IMG",
            "https://d.uguu.se/QmhEjBZF.jpg",
        )

        # ─────────────────────────────────────────────
        # Features
        # ─────────────────────────────────────────────

        self.AUTO_LEAVE = (
            getenv(
                "AUTO_LEAVE",
                "False",
            ).lower()
            == "true"
        )

        self.AUTO_END = (
            getenv(
                "AUTO_END",
                "False",
            ).lower()
            == "true"
        )

        self.THUMB_GEN = (
            getenv(
                "THUMB_GEN",
                "True",
            ).lower()
            == "true"
        )

        self.VIDEO_PLAY = (
            getenv(
                "VIDEO_PLAY",
                "True",
            ).lower()
            == "true"
        )

        # ─────────────────────────────────────────────
        # Language
        # ─────────────────────────────────────────────

        self.LANG_CODE = getenv(
            "LANG_CODE",
            "en",
        )

    # ─────────────────────────────────────────────
    # CHECK CONFIG
    # ─────────────────────────────────────────────

    def check(self):

        missing = [
            var
            for var in [
                "API_ID",
                "API_HASH",
                "BOT_TOKEN",
                "MONGO_URL",
                "LOGGER_ID",
                "OWNER_ID",
                "SESSION1",
            ]
            if not getattr(self, var)
        ]

        if missing:
            raise SystemExit(
                "Missing required environment variables: "
                + ", ".join(missing)
            )
