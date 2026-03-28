#!/usr/bin/env python3
"""
Brand Tracker CLI — monitor clothing brands for drops, events & announcements.

Usage:
    python main.py                  # one-time scan of all brands
    python main.py --watch          # continuous monitoring (runs every N minutes)
    python main.py --brand Nike     # scan a single brand
    python main.py --list           # list tracked brands
    python main.py --add nike_sub   # add an Instagram username to track
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import schedule
from rich.console import Console

from config import TRACKED_BRANDS, BrandConfig, Settings
from tracker import BrandTracker

console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="Track clothing brand drops & events")
    p.add_argument("--watch", action="store_true", help="Run continuously on a schedule")
    p.add_argument("--interval", type=int, default=30, help="Minutes between checks (default: 30)")
    p.add_argument("--brand", type=str, help="Only check a specific brand by name")
    p.add_argument("--list", action="store_true", help="List all tracked brands")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return p.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list:
        console.print("\n[bold]Tracked Brands:[/bold]\n")
        for b in TRACKED_BRANDS:
            ig = f"IG: @{b.instagram_username}" if b.instagram_username else ""
            tt = f"TT: @{b.tiktok_username}" if b.tiktok_username else ""
            console.print(f"  • {b.name:<16} {ig:<28} {tt}")
        console.print()
        return

    settings = Settings()
    tracker = BrandTracker(settings)

    # Filter to one brand if requested
    brands = TRACKED_BRANDS
    if args.brand:
        brands = [b for b in TRACKED_BRANDS if b.name.lower() == args.brand.lower()]
        if not brands:
            console.print(f"[red]Brand '{args.brand}' not found in config.[/red]")
            console.print("Available: " + ", ".join(b.name for b in TRACKED_BRANDS))
            sys.exit(1)

    if args.watch:
        console.print(
            f"\n[bold green]Starting continuous monitor — checking every {args.interval} min[/bold green]\n"
        )

        def run_check():
            alerts = tracker.check_all(brands)
            tracker.display_alerts(alerts)

        run_check()  # run immediately
        schedule.every(args.interval).minutes.do(run_check)

        try:
            while True:
                schedule.run_pending()
                time.sleep(10)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped.[/dim]")
    else:
        alerts = tracker.check_all(brands)
        tracker.display_alerts(alerts)


if __name__ == "__main__":
    main()
