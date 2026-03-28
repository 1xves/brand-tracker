"""Analyze scraped posts to detect drops, events, and announcements."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from models import AlertType, BrandAlert, ScrapedPost

log = logging.getLogger(__name__)

# ── Keyword patterns for detection ────────────────────────────────────────

DROP_KEYWORDS = [
    r"\bdrop(?:s|ping)?\b",
    r"\breleas(?:e|ing|ed)\b",
    r"\blaunch(?:es|ing)?\b",
    r"\bavailable\s+now\b",
    r"\bout\s+now\b",
    r"\bcoming\s+soon\b",
    r"\bpre[- ]?order\b",
    r"\brestock\b",
    r"\bsold\s+out\b",
    r"\blimited\s+edition\b",
    r"\bexclusive\b",
    r"\bnew\s+arriv",
    r"\bshop\s+now\b",
    r"\bcop\s+(or\s+drop|now)\b",
    r"\bfirst\s+come\b",
    r"\bin[- ]store\s+(and\s+)?online\b",
    r"\blink\s+in\s+bio\b",
]

EVENT_KEYWORDS = [
    r"\bpop[- ]?up\b",
    r"\bevent\b",
    r"\bshow(?:room)?\b",
    r"\bfashion\s+week\b",
    r"\brunway\b",
    r"\bexhibition\b",
    r"\bparty\b",
    r"\bopening\b",
    r"\binvit(?:e|ation)\b",
    r"\brsvp\b",
    r"\btickets?\b",
    r"\bfestival\b",
    r"\bactivation\b",
    r"\bmeet\s+and\s+greet\b",
]

ANNOUNCEMENT_KEYWORDS = [
    r"\bannounce|announcing\b",
    r"\bintroduc(?:e|ing)\b",
    r"\bnew\s+collection\b",
    r"\bcampaign\b",
    r"\bseason\b",
    r"\bss\d{2}|fw\d{2}\b",
    r"\bspring|summer|fall|autumn|winter\b.*\b20\d{2}\b",
    r"\bcollaboration\b",
    r"\bcollab\b",
    r"\bpartner(?:ship)?\b",
    r"\bx\s+\w+\b",  # "Brand x Brand" collabs
]

# Date/time extraction patterns
DATE_PATTERNS = [
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",  # 03/28/2026
    r"(\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})",  # March 28th, 2026
    r"(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4})",  # 28th March 2026
    r"(\w+\s+\d{1,2}(?:st|nd|rd|th)?)\b",  # March 28th (no year)
    r"(this\s+(?:friday|saturday|sunday|monday|tuesday|wednesday|thursday))",
    r"(tomorrow|tonight|today)",
]

TIME_PATTERNS = [
    r"(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))",
    r"(\d{1,2}\s*(?:am|pm|AM|PM))",
    r"(\d{1,2}:\d{2}\s*(?:EST|PST|CST|MST|ET|PT|CT|GMT|BST|CET))",
    r"(noon|midnight)",
]


def _match_score(text: str, patterns: list[str]) -> float:
    """Return 0-1 score for how many patterns match in the text."""
    if not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for p in patterns if re.search(p, text_lower, re.IGNORECASE))
    return min(hits / 3.0, 1.0)  # 3+ matches = max confidence


def _extract_date_time(text: str) -> str | None:
    """Try to extract a date/time string from caption text."""
    if not text:
        return None

    parts = []
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            parts.append(m.group(1))
            break

    for pattern in TIME_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            parts.append(m.group(1))
            break

    return " ".join(parts) if parts else None


def analyze_post(post: ScrapedPost, brand_keywords: list[str] = []) -> list[BrandAlert]:
    """Analyze a single post and return any alerts detected."""
    text = f"{post.caption} {' '.join(post.hashtags)}"
    if not text.strip():
        return []

    # Check brand-specific keywords boost
    brand_boost = 0.0
    text_lower = text.lower()
    for kw in brand_keywords:
        if kw.lower() in text_lower:
            brand_boost = 0.15
            break

    alerts: list[BrandAlert] = []

    # Check for drops
    drop_score = _match_score(text, DROP_KEYWORDS) + brand_boost
    if drop_score >= 0.3:
        alerts.append(
            BrandAlert(
                alert_type=AlertType.DROP,
                brand=post.brand,
                title=_make_title(post, "Drop"),
                details=post.caption[:500],
                drop_date=_extract_date_time(text),
                source_post=post,
                confidence=min(drop_score, 1.0),
            )
        )

    # Check for events
    event_score = _match_score(text, EVENT_KEYWORDS) + brand_boost
    if event_score >= 0.3:
        alerts.append(
            BrandAlert(
                alert_type=AlertType.EVENT,
                brand=post.brand,
                title=_make_title(post, "Event"),
                details=post.caption[:500],
                drop_date=_extract_date_time(text),
                source_post=post,
                confidence=min(event_score, 1.0),
            )
        )

    # Check for announcements / collabs
    announce_score = _match_score(text, ANNOUNCEMENT_KEYWORDS) + brand_boost
    if announce_score >= 0.3:
        # Detect collab specifically
        is_collab = bool(
            re.search(r"\bcollab|collaboration|partner|x\s+\w+", text, re.IGNORECASE)
        )
        alerts.append(
            BrandAlert(
                alert_type=AlertType.COLLAB if is_collab else AlertType.ANNOUNCEMENT,
                brand=post.brand,
                title=_make_title(post, "Collab" if is_collab else "Announcement"),
                details=post.caption[:500],
                drop_date=_extract_date_time(text),
                source_post=post,
                confidence=min(announce_score, 1.0),
            )
        )

    return alerts


def _make_title(post: ScrapedPost, kind: str) -> str:
    """Generate a short title from the caption."""
    caption = post.caption.replace("\n", " ").strip()
    if len(caption) > 80:
        caption = caption[:77] + "..."
    if not caption:
        caption = f"New {post.content_type.value} from @{post.username}"
    return f"{kind}: {caption}"
