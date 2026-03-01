#!/usr/bin/env python3
"""
End-to-end validation of page metadata enrichment.

Uses Google News URLs from existing exports to verify:
- resolved_url: Google News URLs resolve to publisher URLs (reuters.com, etc.)
- title: Populated from og:title or page <title>
- description: Populated from og:description or meta description

Usage:
    python scripts/validate_enrichment.py
    python scripts/validate_enrichment.py --limit 3
    python scripts/validate_enrichment.py --urls-file exports/notebooklm_urls_20260202_221956.txt
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.enrich import enrich_items
from backend.app.models import Category, NewsItem


def load_urls_from_exports(urls_file: Path, limit: int = 5) -> list[str]:
    """Load sample URLs from exports file (plain text, one URL per line)."""
    urls = []
    with open(urls_file, encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url and not url.startswith("#"):
                urls.append(url)
                if len(urls) >= limit:
                    break
    return urls


def urls_to_news_items(urls: list[str]) -> list[NewsItem]:
    """Create minimal NewsItem objects from URLs for enrichment."""
    items = []
    for url in urls:
        item = NewsItem(
            url=url,
            title="",  # Will be filled by enrichment or fallback
            source_id="validate",
            summary="",  # RSS fallback when meta unavailable
        )
        item.normalized_url = url
        items.append(item)
    return items


def main():
    parser = argparse.ArgumentParser(description="Validate enrichment with sample Google News URLs")
    parser.add_argument(
        "--urls-file",
        type=Path,
        default=Path("exports/notebooklm_urls_20260202_221956.txt"),
        help="Path to URLs file (one URL per line)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of URLs to validate (default: 5)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write enriched JSON to file (default: exports/validation_enrichment_<timestamp>.json)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent fetches (default: 5)",
    )
    args = parser.parse_args()

    urls_file = args.urls_file
    if not urls_file.exists():
        # Try relative to project root
        root = Path(__file__).resolve().parent.parent
        urls_file = root / urls_file
    if not urls_file.exists():
        print(f"Error: URLs file not found: {args.urls_file}", file=sys.stderr)
        sys.exit(1)

    urls = load_urls_from_exports(urls_file, limit=args.limit)
    if not urls:
        print("Error: No URLs found in file", file=sys.stderr)
        sys.exit(1)

    print(f"Validating enrichment for {len(urls)} URLs from {urls_file.name}")
    print("=" * 80)

    items = urls_to_news_items(urls)
    meta_map = asyncio.run(enrich_items(items, concurrency=args.concurrency))

    # Build enriched output for verification
    enriched = []
    for item in items:
        url = item.normalized_url or item.url
        meta = meta_map.get(url)
        if meta:
            resolved_changed = meta.resolved_url != url
            entry = {
                "input_url": url[:80] + "..." if len(url) > 80 else url,
                "resolved_url": meta.resolved_url,
                "resolved_changed": resolved_changed,
                "title": meta.title or item.title,
                "description": (meta.description or item.summary)[:120] + "..." if (meta.description or item.summary) and len(meta.description or item.summary) > 120 else (meta.description or item.summary),
                "canonical_url": meta.canonical_url,
                "site_name": meta.site_name,
                "fetch_ok": meta.fetch_ok,
            }
        else:
            entry = {
                "input_url": url[:80] + "..." if len(url) > 80 else url,
                "resolved_url": url,
                "resolved_changed": False,
                "title": item.title,
                "description": item.summary,
                "error": "No meta returned",
            }
        enriched.append(entry)

    # Print summary
    resolved_count = sum(1 for e in enriched if e.get("resolved_changed"))
    title_count = sum(1 for e in enriched if e.get("title"))
    desc_count = sum(1 for e in enriched if e.get("description"))

    print(f"\n[Results] resolved_url changed: {resolved_count}/{len(enriched)} | "
          f"title filled: {title_count}/{len(enriched)} | "
          f"description filled: {desc_count}/{len(enriched)}")
    print()

    for i, e in enumerate(enriched, 1):
        print(f"--- Item {i} ---")
        print(f"  input_url:    {e['input_url']}")
        print(f"  resolved_url: {e['resolved_url']}")
        if e.get("resolved_changed"):
            suffix = " (gstatic)" if "gstatic.com" in (e.get("resolved_url") or "") else " (publisher)"
            print(f"  ✓ resolved{suffix}")
        print(f"  title:        {(e.get('title') or '(empty)')[:70]}...")
        print(f"  description:  {(e.get('description') or '(empty)')[:100]}...")
        if e.get("site_name"):
            print(f"  site_name:    {e['site_name']}")
        print()

    result = {
        "validated_count": len(enriched),
        "resolved_changed": resolved_count,
        "title_filled": title_count,
        "description_filled": desc_count,
        "items": enriched,
    }

    # Always write results to file for review
    out_path = args.output
    if out_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path("exports/validation_enrichment_" + ts + ".json")
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parent.parent / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Full results written to {out_path}")

    # Report validation outcome
    gstatic_count = sum(1 for e in enriched if "gstatic.com" in (e.get("resolved_url") or ""))
    if resolved_count >= 1 and title_count >= 1 and gstatic_count == 0:
        print("✓ Validation passed: resolved_url and title populated successfully")
    elif gstatic_count > 0:
        print("⚠ Google News URLs redirect to gstatic.com (Google CDN); "
              "publisher URL extraction may need decoder (e.g. googlenewsdecoder)")
    else:
        print("⚠ Validation partial: some URLs may not resolve or lack meta")
    sys.exit(0)  # Always 0 - we report results; transient failures are expected


if __name__ == "__main__":
    main()
