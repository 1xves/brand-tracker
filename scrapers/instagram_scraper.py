"""Instagram scraper using instaloader (public profiles) and Graph API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import instaloader

from config import BrandConfig, Settings
from models import ContentType, Platform, ScrapedPost

from .base import BaseScraper

log = logging.getLogger(__name__)


class InstagramScraper(BaseScraper):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )
        # If you have session cookies you can log in for better access:
        # self.loader.load_session_from_file("your_username")

    def scrape_posts(self, brand: BrandConfig, limit: int = 10) -> list[ScrapedPost]:
        username = brand.instagram_username
        if not username:
            return []

        posts: list[ScrapedPost] = []
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            for i, post in enumerate(profile.get_posts()):
                if i >= limit:
                    break

                content_type = ContentType.REEL if post.is_video else ContentType.POST
                caption = post.caption or ""
                hashtags = [
                    tag.strip("#").lower()
                    for tag in caption.split()
                    if tag.startswith("#")
                ]

                media_urls = []
                if post.is_video and post.video_url:
                    media_urls.append(post.video_url)
                elif post.url:
                    media_urls.append(post.url)

                posts.append(
                    ScrapedPost(
                        post_id=f"ig_{post.shortcode}",
                        platform=Platform.INSTAGRAM,
                        content_type=content_type,
                        brand=brand.name,
                        username=username,
                        caption=caption,
                        url=f"https://www.instagram.com/p/{post.shortcode}/",
                        media_urls=media_urls,
                        timestamp=post.date_utc.replace(tzinfo=timezone.utc),
                        likes=post.likes,
                        comments=post.comments,
                        hashtags=hashtags,
                    )
                )
        except Exception as e:
            log.warning("Instagram scrape failed for %s: %s", username, e)

        return posts

    def scrape_stories(self, brand: BrandConfig) -> list[ScrapedPost]:
        """Scrape stories — requires login session."""
        username = brand.instagram_username
        if not username:
            return []

        stories: list[ScrapedPost] = []
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            for story in self.loader.get_stories(userids=[profile.userid]):
                for item in story.get_items():
                    ct = ContentType.STORY
                    caption = item.caption or ""

                    media_urls = []
                    if item.is_video and item.video_url:
                        media_urls.append(item.video_url)
                    elif item.url:
                        media_urls.append(item.url)

                    stories.append(
                        ScrapedPost(
                            post_id=f"ig_story_{item.mediaid}",
                            platform=Platform.INSTAGRAM,
                            content_type=ct,
                            brand=brand.name,
                            username=username,
                            caption=caption,
                            url=f"https://www.instagram.com/stories/{username}/{item.mediaid}/",
                            media_urls=media_urls,
                            timestamp=item.date_utc.replace(tzinfo=timezone.utc),
                            hashtags=[],
                        )
                    )
        except Exception as e:
            log.warning(
                "Instagram stories failed for %s (login may be required): %s",
                username,
                e,
            )

        return stories
