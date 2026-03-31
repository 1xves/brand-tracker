"""SQLite-backed storage for brands and alerts (SQLAlchemy).

Switching to PostgreSQL or Supabase later requires only changing the
DATABASE_URL in your .env — the rest of this file stays the same.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, JSON, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import TRACKED_BRANDS, BrandConfig
from models import BrandAlert

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class BrandRow(Base):
    __tablename__ = "brands"
    name = Column(String, primary_key=True)
    instagram_username = Column(String, nullable=True)
    tiktok_username = Column(String, nullable=True)
    keywords = Column(JSON, default=list)


class AlertRow(Base):
    __tablename__ = "alerts"
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    scan_id = Column(String, index=True)
    brand = Column(String, index=True)
    alert_type = Column(String, index=True)
    data = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def _make_engine(db_url: str):
    kwargs = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=kwargs)


class BrandStore:
    def __init__(self, db_url: str) -> None:
        self._engine = _make_engine(db_url)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(self._engine, expire_on_commit=False)
        self._seed_if_empty()

    def _seed_if_empty(self) -> None:
        with self._Session() as session:
            if session.query(BrandRow).count() == 0:
                for bc in TRACKED_BRANDS:
                    session.add(BrandRow(
                        name=bc.name,
                        instagram_username=bc.instagram_username,
                        tiktok_username=bc.tiktok_username,
                        keywords=bc.keywords,
                    ))
                session.commit()
                log.info("Seeded %d default brands into database", len(TRACKED_BRANDS))

    @staticmethod
    def _to_config(row: BrandRow) -> BrandConfig:
        return BrandConfig(
            name=row.name,
            instagram_username=row.instagram_username,
            tiktok_username=row.tiktok_username,
            keywords=row.keywords or [],
        )

    def list_all(self) -> list[BrandConfig]:
        with self._Session() as session:
            return [self._to_config(r) for r in session.query(BrandRow).all()]

    def get(self, name: str) -> BrandConfig | None:
        with self._Session() as session:
            row = session.query(BrandRow).filter(func.lower(BrandRow.name) == name.lower()).first()
            return self._to_config(row) if row else None

    def add(self, brand: BrandConfig) -> BrandConfig:
        with self._Session() as session:
            exists = session.query(BrandRow).filter(func.lower(BrandRow.name) == brand.name.lower()).first()
            if exists:
                raise ValueError(f"Brand '{brand.name}' already exists")
            session.add(BrandRow(
                name=brand.name,
                instagram_username=brand.instagram_username,
                tiktok_username=brand.tiktok_username,
                keywords=brand.keywords,
            ))
            session.commit()
        return brand

    def remove(self, name: str) -> BrandConfig:
        with self._Session() as session:
            row = session.query(BrandRow).filter(func.lower(BrandRow.name) == name.lower()).first()
            if not row:
                raise KeyError(f"Brand '{name}' not found")
            bc = self._to_config(row)
            session.delete(row)
            session.commit()
        return bc


class AlertHistory:
    def __init__(self, db_url: str) -> None:
        self._engine = _make_engine(db_url)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(self._engine, expire_on_commit=False)

    def append(self, alerts: list[BrandAlert], scan_id: str) -> None:
        with self._Session() as session:
            for alert in alerts:
                data = alert.model_dump(mode="json")
                data["scan_id"] = scan_id
                alert_type = alert.alert_type.value if hasattr(alert.alert_type, "value") else alert.alert_type
                session.add(AlertRow(
                    id=uuid.uuid4().hex,
                    scan_id=scan_id,
                    brand=alert.brand,
                    alert_type=alert_type,
                    data=data,
                    created_at=datetime.now(timezone.utc),
                ))
            session.commit()

    def query(self, *, brand: str | None = None, alert_type: str | None = None, limit: int = 100, scan_id: str | None = None) -> list[dict]:
        with self._Session() as session:
            q = session.query(AlertRow).order_by(AlertRow.created_at.desc())
            if brand:
                q = q.filter(func.lower(AlertRow.brand) == brand.lower())
            if alert_type:
                q = q.filter(AlertRow.alert_type == alert_type)
            if scan_id:
                q = q.filter(AlertRow.scan_id == scan_id)
            return [row.data for row in q.limit(limit).all()]

    def latest_scan_id(self) -> str | None:
        with self._Session() as session:
            row = session.query(AlertRow).order_by(AlertRow.created_at.desc()).first()
            return row.scan_id if row else None

    def stats(self) -> dict:
        with self._Session() as session:
            rows = session.query(AlertRow).all()
        by_type: dict[str, int] = {}
        by_brand: dict[str, int] = {}
        for row in rows:
            by_type[row.alert_type] = by_type.get(row.alert_type, 0) + 1
            by_brand[row.brand] = by_brand.get(row.brand, 0) + 1
        return {"total_alerts": len(rows), "alerts_by_type": by_type, "alerts_by_brand": by_brand}
