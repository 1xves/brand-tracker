"""Persistent JSON-file-backed storage for brands and alerts."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from config import TRACKED_BRANDS, BrandConfig
from models import AlertType, BrandAlert

log = logging.getLogger(__name__)


class BrandStore:
    """CRUD operations for tracked brands, persisted to a JSON file.

    On first run (no file on disk) the store is seeded from
    ``config.TRACKED_BRANDS`` so default brands are always available.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._brands: dict[str, BrandConfig] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                for item in raw:
                    bc = BrandConfig(**item)
                    self._brands[bc.name.lower()] = bc
                log.info("Loaded %d brands from %s", len(self._brands), self._path)
            except Exception:
                log.exception("Failed to load brands file, seeding from config")
                self._seed()
        else:
            self._seed()

    def _seed(self) -> None:
        for bc in TRACKED_BRANDS:
            self._brands[bc.name.lower()] = bc
        self._save()

    def _save(self) -> None:
        data = [bc.model_dump() for bc in self._brands.values()]
        self._path.write_text(json.dumps(data, indent=2))

    # ── public API ───────────────────────────────────────────────────────

    def list_all(self) -> list[BrandConfig]:
        """Return every tracked brand."""
        with self._lock:
            return list(self._brands.values())

    def get(self, name: str) -> BrandConfig | None:
        """Fetch a single brand by name (case-insensitive)."""
        with self._lock:
            return self._brands.get(name.lower())

    def add(self, brand: BrandConfig) -> BrandConfig:
        """Add a new brand. Raises ``ValueError`` if it already exists."""
        with self._lock:
            key = brand.name.lower()
            if key in self._brands:
                raise ValueError(f"Brand '{brand.name}' already exists")
            self._brands[key] = brand
            self._save()
            return brand

    def remove(self, name: str) -> BrandConfig:
        """Remove a brand by name. Raises ``KeyError`` if not found."""
        with self._lock:
            key = name.lower()
            if key not in self._brands:
                raise KeyError(f"Brand '{name}' not found")
            brand = self._brands.pop(key)
            self._save()
            return brand


class AlertHistory:
    """Append-only alert log with query support, persisted to a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._alerts: list[dict] = []
        self._scan_ids: list[str] = []
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                self._alerts = raw.get("alerts", [])
                self._scan_ids = raw.get("scan_ids", [])
                log.info("Loaded %d alerts from %s", len(self._alerts), self._path)
            except Exception:
                log.exception("Failed to load alerts file, starting fresh")
                self._alerts = []
                self._scan_ids = []

    def _save(self) -> None:
        data = {"alerts": self._alerts, "scan_ids": self._scan_ids}
        self._path.write_text(json.dumps(data, indent=2, default=str))

    # ── public API ───────────────────────────────────────────────────────

    def append(self, alerts: list[BrandAlert], scan_id: str) -> None:
        """Persist a batch of alerts from a single scan run."""
        with self._lock:
            for alert in alerts:
                entry = alert.model_dump(mode="json")
                entry["scan_id"] = scan_id
                self._alerts.append(entry)
            if scan_id not in self._scan_ids:
                self._scan_ids.append(scan_id)
            self._save()

    def query(
        self,
        *,
        brand: str | None = None,
        alert_type: str | None = None,
        limit: int = 100,
        scan_id: str | None = None,
    ) -> list[dict]:
        """Return alerts matching the given filters, most recent first."""
        with self._lock:
            results = list(reversed(self._alerts))

        if brand:
            results = [a for a in results if a.get("brand", "").lower() == brand.lower()]
        if alert_type:
            results = [a for a in results if a.get("alert_type") == alert_type]
        if scan_id:
            results = [a for a in results if a.get("scan_id") == scan_id]

        return results[:limit]

    def latest_scan_id(self) -> str | None:
        """Return the ID of the most recent scan, or None."""
        with self._lock:
            return self._scan_ids[-1] if self._scan_ids else None

    def stats(self) -> dict:
        """Compute summary statistics across all stored alerts."""
        with self._lock:
            alerts = list(self._alerts)

        by_type: dict[str, int] = {}
        by_brand: dict[str, int] = {}
        for a in alerts:
            t = a.get("alert_type", "unknown")
            b = a.get("brand", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
            by_brand[b] = by_brand.get(b, 0) + 1

        return {
            "total_alerts": len(alerts),
            "alerts_by_type": by_type,
            "alerts_by_brand": by_brand,
        }
