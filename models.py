"""Data models for scraped content and alerts."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class ContentType(str, Enum):
    POST = "post"
    STORY = "story"
    REEL = "reel"
    VIDEO = "video"


class AlertType(str, Enum):
    DROP = "drop"  # new product release / drop
    EVENT = "event"  # pop-up, show, party, etc.
    ANNOUNCEMENT = "announcement"  # general brand news
    COLLAB = "collab"  # collaboration between brands


class ScrapedPost(BaseModel):
    post_id: str
    platform: Platform
    content_type: ContentType
    brand: str
    username: str
    caption: str = ""
    url: str = ""
    media_urls: list[str] = []
    timestamp: datetime | None = None
    likes: int | None = None
    comments: int | None = None
    hashtags: list[str] = []


class BrandAlert(BaseModel):
    alert_type: AlertType
    brand: str
    title: str
    details: str
    drop_date: str | None = None  # e.g. "2026-04-01 10:00 EST"
    source_post: ScrapedPost
    confidence: float = 0.0  # 0-1 how confident the detection is
    created_at: datetime = datetime.now()

    def short(self) -> str:
        icon = {"drop": "🔥", "event": "📍", "announcement": "📢", "collab": "🤝"}
        i = icon.get(self.alert_type, "•")
        date = f" — {self.drop_date}" if self.drop_date else ""
        return f"{i} [{self.brand}] {self.title}{date}"


class AlertStore:
    """Simple JSON file-backed alert store to avoid duplicates."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._load()

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._seen = set(data.get("seen_ids", []))

    def _save(self):
        self.path.write_text(json.dumps({"seen_ids": sorted(self._seen)}, indent=2))

    def is_new(self, post_id: str) -> bool:
        return post_id not in self._seen

    def mark_seen(self, post_id: str):
        self._seen.add(post_id)
        self._save()
