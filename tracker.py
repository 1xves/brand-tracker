"""Main tracker — orchestrates scraping, analysis, and alerting."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from analyzer import analyze_post
from config import TRACKED_BRANDS, BrandConfig, Settings
from models import AlertStore, BrandAlert, ScrapedPost
from scrapers.instagram_scraper import InstagramScraper
from scrapers.tiktok_scraper import TikTokScraper

log = logging.getLogger(__name__)
console = Console()


class BrandTracker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = AlertStore(self.settings.data_dir / "seen.json")
        self.ig = InstagramScraper(self.settings)
        self.tt = TikTokScraper(self.settings)

    def check_brand(self, brand: BrandConfig) -> list[BrandAlert]:
        """Scrape and analyze a single brand across all platforms."""
        all_posts: list[ScrapedPost] = []

        console.print(f"  [dim]Checking {brand.name}...[/dim]")

        # Instagram
        if brand.instagram_username:
            posts = self.ig.scrape_posts(brand, limit=self.settings.max_posts_per_check)
            stories = self.ig.scrape_stories(brand)
            all_posts.extend(posts)
            all_posts.extend(stories)
            console.print(
                f"    Instagram: {len(posts)} posts, {len(stories)} stories"
            )

        # TikTok
        if brand.tiktok_username:
            videos = self.tt.scrape_posts(brand, limit=self.settings.max_posts_per_check)
            all_posts.extend(videos)
            console.print(f"    TikTok: {len(videos)} videos")

        # Filter out already-seen posts
        new_posts = [p for p in all_posts if self.store.is_new(p.post_id)]

        # Analyze each new post
        alerts: list[BrandAlert] = []
        for post in new_posts:
            post_alerts = analyze_post(post, brand.keywords)
            alerts.extend(post_alerts)
            self.store.mark_seen(post.post_id)

        return alerts

    def check_all(self, brands: list[BrandConfig] | None = None) -> list[BrandAlert]:
        """Run a full check across all tracked brands."""
        brands = brands or TRACKED_BRANDS
        all_alerts: list[BrandAlert] = []

        console.print(
            Panel(
                f"[bold]Scanning {len(brands)} brands...[/bold]",
                style="blue",
            )
        )

        for brand in brands:
            try:
                alerts = self.check_brand(brand)
                all_alerts.extend(alerts)
            except Exception as e:
                console.print(f"  [red]Error with {brand.name}: {e}[/red]")

        return all_alerts

    def display_alerts(self, alerts: list[BrandAlert]):
        """Pretty-print alerts to the terminal."""
        if not alerts:
            console.print("\n[dim]No new drops, events, or announcements found.[/dim]\n")
            return

        # Sort: drops first, then events, then announcements
        priority = {
            "drop": 0,
            "collab": 1,
            "event": 2,
            "announcement": 3,
        }
        alerts.sort(key=lambda a: (priority.get(a.alert_type, 9), -a.confidence))

        table = Table(title="Brand Alerts", show_lines=True, expand=True)
        table.add_column("Type", style="bold", width=14)
        table.add_column("Brand", width=14)
        table.add_column("Details", ratio=3)
        table.add_column("When", width=20)
        table.add_column("Conf.", width=6, justify="right")
        table.add_column("Link", width=30)

        icons = {"drop": "🔥 DROP", "event": "📍 EVENT", "announcement": "📢 NEWS", "collab": "🤝 COLLAB"}

        for alert in alerts:
            type_label = icons.get(alert.alert_type, alert.alert_type.upper())
            style = "red bold" if alert.alert_type == "drop" else ""
            table.add_row(
                type_label,
                alert.brand,
                alert.details[:120] + ("..." if len(alert.details) > 120 else ""),
                alert.drop_date or "—",
                f"{alert.confidence:.0%}",
                alert.source_post.url[:30] + "...",
                style=style,
            )

        console.print()
        console.print(table)
        console.print()
