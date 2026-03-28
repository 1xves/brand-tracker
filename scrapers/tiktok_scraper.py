"""TikTok scraper using yt-dlp for public video metadata."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone

from config import BrandConfig, Settings
from models import ContentType, Platform, ScrapedPost

from .base import BaseScraper

log = logging.getLogger(__name__)


class TikTokScraper(BaseScraper):
    """
    Uses yt-dlp to extract public TikTok video metadata.
    This avoids needing the unofficial TikTokApi which breaks frequently.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def scrape_posts(self, brand: BrandConfig, limit: int = 10) -> list[ScrapedPost]:
        username = brand.tiktok_username
        if not username:
            return []

        posts: list[ScrapedPost] = []
        profile_url = f"https://www.tiktok.com/@{username}"

        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--dump-json",
                    "--flat-playlist",
                    "--playlist-end",
                    str(limit),
                    "--no-download",
                    "--quiet",
                    "--no-warnings",
                    profile_url,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                log.warning("yt-dlp failed for %s: %s", username, result.stderr[:200])
                return []

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                video_id = data.get("id", "")
                description = data.get("description", "") or data.get("title", "")
                hashtags = [
                    tag.strip("#").lower()
                    for tag in description.split()
                    if tag.startswith("#")
                ]

                ts = None
                if data.get("timestamp"):
                    ts = datetime.fromtimestamp(data["timestamp"], tz=timezone.utc)

                url = data.get("webpage_url") or f"https://www.tiktok.com/@{username}/video/{video_id}"

                posts.append(
                    ScrapedPost(
                        post_id=f"tt_{video_id}",
                        platform=Platform.TIKTOK,
                        content_type=ContentType.VIDEO,
                        brand=brand.name,
                        username=username,
                        caption=description,
                        url=url,
                        media_urls=[url],
                        timestamp=ts,
                        likes=data.get("like_count"),
                        comments=data.get("comment_count"),
                        hashtags=hashtags,
                    )
                )

        except subprocess.TimeoutExpired:
            log.warning("yt-dlp timed out for %s", username)
        except FileNotFoundError:
            log.error("yt-dlp not found — install it: pip install yt-dlp")
        except Exception as e:
            log.warning("TikTok scrape failed for %s: %s", username, e)

        return posts

    def scrape_stories(self, brand: BrandConfig) -> list[ScrapedPost]:
        """TikTok stories aren't publicly accessible — skip."""
        return []
