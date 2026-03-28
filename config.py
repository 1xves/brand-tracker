"""Configuration and settings for brand tracker."""

from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class BrandConfig(BaseModel):
    name: str
    instagram_username: str | None = None
    tiktok_username: str | None = None
    keywords: list[str] = []  # extra keywords to watch for


class Settings(BaseSettings):
    # API keys
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Scraping settings
    check_interval_minutes: int = 30
    data_dir: Path = Path("data")
    max_posts_per_check: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# ── Brands to track ──────────────────────────────────────────────────────
# Add or remove brands here. Each brand needs at least one social handle.
TRACKED_BRANDS: list[BrandConfig] = [
    BrandConfig(
        name="Nike",
        instagram_username="nike",
        tiktok_username="nike",
        keywords=["air max", "jordan", "dunk"],
    ),
    BrandConfig(
        name="Adidas",
        instagram_username="adidas",
        tiktok_username="adidas",
        keywords=["yeezy", "samba", "gazelle"],
    ),
    BrandConfig(
        name="Supreme",
        instagram_username="supremenewyork",
        tiktok_username="supreme",
        keywords=["box logo", "bogo", "fw", "ss"],
    ),
    BrandConfig(
        name="Stussy",
        instagram_username="stussy",
        tiktok_username="stussy",
        keywords=["world tour", "8 ball"],
    ),
    BrandConfig(
        name="Palace",
        instagram_username="palaceskateboards",
        tiktok_username="palaceskateboards",
        keywords=["tri-ferg", "ultimo", "basically"],
    ),
    BrandConfig(
        name="New Balance",
        instagram_username="newbalance",
        tiktok_username="newbalance",
        keywords=["550", "2002r", "990", "1906"],
    ),
    BrandConfig(
        name="Fear of God",
        instagram_username="fearofgod",
        tiktok_username="fearofgod",
        keywords=["essentials", "jerry lorenzo"],
    ),
    BrandConfig(
        name="Corteiz",
        instagram_username="corteiz",
        tiktok_username="corteiz",
        keywords=["alcatraz", "rules the world"],
    ),
]
