"""Base scraper interface."""

from __future__ import annotations

import abc

from config import BrandConfig
from models import ScrapedPost


class BaseScraper(abc.ABC):
    @abc.abstractmethod
    def scrape_posts(self, brand: BrandConfig, limit: int = 10) -> list[ScrapedPost]:
        """Fetch recent posts for a brand."""

    @abc.abstractmethod
    def scrape_stories(self, brand: BrandConfig) -> list[ScrapedPost]:
        """Fetch current stories for a brand."""
