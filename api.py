"""FastAPI backend for the brand-tracker application."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import BrandConfig, Settings
from store import AlertHistory, BrandStore
from tracker import BrandTracker

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Settings & shared instances ──────────────────────────────────────────

settings = Settings()
DATA_DIR: Path = settings.data_dir
DATA_DIR.mkdir(parents=True, exist_ok=True)

brand_store = BrandStore(settings.database_url)
alert_history = AlertHistory(settings.database_url)
tracker = BrandTracker(settings)

# ── FastAPI app ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Brand Tracker API",
    description="REST API for tracking streetwear brand drops, events, and announcements across Instagram and TikTok.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic response / request models ───────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class BrandIn(BaseModel):
    """Payload for adding a new brand."""
    name: str
    instagram_username: str | None = None
    tiktok_username: str | None = None
    keywords: list[str] = []


class BrandOut(BaseModel):
    name: str
    instagram_username: str | None = None
    tiktok_username: str | None = None
    keywords: list[str] = []


class BrandListResponse(BaseModel):
    brands: list[BrandOut]
    count: int


class BrandDeleteResponse(BaseModel):
    deleted: str
    message: str


class ScanSummary(BaseModel):
    scan_id: str
    brands_scanned: int
    alerts_found: int
    by_type: dict[str, int]
    started_at: str
    finished_at: str | None = None


class ScanResponse(BaseModel):
    summary: ScanSummary
    alerts: list[dict]


class ScanAccepted(BaseModel):
    scan_id: str
    message: str
    status: str


class AlertListResponse(BaseModel):
    alerts: list[dict]
    count: int


class StatsResponse(BaseModel):
    total_brands: int
    total_alerts: int
    alerts_by_type: dict[str, int]
    alerts_by_brand: dict[str, int]
    timestamp: str


# ── Helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_scan(brands: list[BrandConfig], scan_id: str) -> ScanResponse:
    """Execute a scan synchronously and persist the results."""
    started = _now_iso()
    all_alerts = tracker.check_all(brands)
    finished = _now_iso()

    alert_history.append(all_alerts, scan_id)

    by_type: dict[str, int] = {}
    for a in all_alerts:
        t = a.alert_type.value
        by_type[t] = by_type.get(t, 0) + 1

    alert_dicts = [a.model_dump(mode="json") for a in all_alerts]

    summary = ScanSummary(
        scan_id=scan_id,
        brands_scanned=len(brands),
        alerts_found=len(all_alerts),
        by_type=by_type,
        started_at=started,
        finished_at=finished,
    )
    return ScanResponse(summary=summary, alerts=alert_dicts)


def _run_scan_background(brands: list[BrandConfig], scan_id: str) -> None:
    """Background wrapper that catches exceptions so they don't vanish."""
    try:
        _run_scan(brands, scan_id)
        log.info("Background scan %s completed", scan_id)
    except Exception:
        log.exception("Background scan %s failed", scan_id)


# ── Endpoints ────────────────────────────────────────────────────────────


@app.get("/", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=_now_iso(),
        version="1.0.0",
    )


# ── Brands ───────────────────────────────────────────────────────────────


@app.get("/api/brands", response_model=BrandListResponse)
async def list_brands() -> BrandListResponse:
    """List all tracked brands with their social handles."""
    brands = brand_store.list_all()
    return BrandListResponse(
        brands=[BrandOut(**b.model_dump()) for b in brands],
        count=len(brands),
    )


@app.post("/api/brands", response_model=BrandOut, status_code=201)
async def add_brand(body: BrandIn) -> BrandOut:
    """Add a new brand to track."""
    if not body.instagram_username and not body.tiktok_username:
        raise HTTPException(
            status_code=422,
            detail="At least one social handle (instagram_username or tiktok_username) is required.",
        )
    bc = BrandConfig(
        name=body.name,
        instagram_username=body.instagram_username,
        tiktok_username=body.tiktok_username,
        keywords=body.keywords,
    )
    try:
        brand_store.add(bc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return BrandOut(**bc.model_dump())


@app.delete("/api/brands/{name}", response_model=BrandDeleteResponse)
async def delete_brand(name: str) -> BrandDeleteResponse:
    """Remove a tracked brand by name."""
    try:
        removed = brand_store.remove(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return BrandDeleteResponse(
        deleted=removed.name,
        message=f"Brand '{removed.name}' has been removed from tracking.",
    )


# ── Scanning ─────────────────────────────────────────────────────────────


@app.post("/api/scan", response_model=ScanResponse)
async def scan_all_brands(
    background: bool = Query(False, description="Run the scan asynchronously in the background"),
    background_tasks: BackgroundTasks = BackgroundTasks(),  # noqa: B008
) -> ScanResponse | ScanAccepted:  # type: ignore[return]
    """Trigger a full scan of all tracked brands."""
    brands = brand_store.list_all()
    if not brands:
        raise HTTPException(status_code=400, detail="No brands are being tracked.")

    scan_id = uuid.uuid4().hex[:12]

    if background:
        background_tasks.add_task(_run_scan_background, brands, scan_id)
        return ScanAccepted(
            scan_id=scan_id,
            message=f"Scan started in background for {len(brands)} brands.",
            status="accepted",
        )

    return _run_scan(brands, scan_id)


@app.post("/api/scan/{brand_name}", response_model=ScanResponse)
async def scan_single_brand(
    brand_name: str,
    background: bool = Query(False, description="Run the scan asynchronously in the background"),
    background_tasks: BackgroundTasks = BackgroundTasks(),  # noqa: B008
) -> ScanResponse | ScanAccepted:  # type: ignore[return]
    """Scan a specific brand by name."""
    bc = brand_store.get(brand_name)
    if bc is None:
        raise HTTPException(status_code=404, detail=f"Brand '{brand_name}' not found.")

    scan_id = uuid.uuid4().hex[:12]

    if background:
        background_tasks.add_task(_run_scan_background, [bc], scan_id)
        return ScanAccepted(
            scan_id=scan_id,
            message=f"Scan started in background for '{bc.name}'.",
            status="accepted",
        )

    return _run_scan([bc], scan_id)


# ── Alerts ───────────────────────────────────────────────────────────────


@app.get("/api/alerts", response_model=AlertListResponse)
async def get_alerts(
    brand: str | None = Query(None, description="Filter by brand name"),
    type: str | None = Query(None, description="Filter by alert type (drop, event, announcement, collab)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of alerts to return"),
) -> AlertListResponse:
    """Retrieve stored alerts with optional filters."""
    results = alert_history.query(brand=brand, alert_type=type, limit=limit)
    return AlertListResponse(alerts=results, count=len(results))


@app.get("/api/alerts/latest", response_model=AlertListResponse)
async def get_latest_alerts() -> AlertListResponse:
    """Get alerts from the most recent scan."""
    scan_id = alert_history.latest_scan_id()
    if scan_id is None:
        return AlertListResponse(alerts=[], count=0)
    results = alert_history.query(scan_id=scan_id, limit=1000)
    return AlertListResponse(alerts=results, count=len(results))


# ── Stats ────────────────────────────────────────────────────────────────


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Summary statistics across all tracked brands and alerts."""
    stats = alert_history.stats()
    brands = brand_store.list_all()
    return StatsResponse(
        total_brands=len(brands),
        total_alerts=stats["total_alerts"],
        alerts_by_type=stats["alerts_by_type"],
        alerts_by_brand=stats["alerts_by_brand"],
        timestamp=_now_iso(),
    )
