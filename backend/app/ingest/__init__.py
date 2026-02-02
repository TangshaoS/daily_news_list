"""
Ingest module - fetches news from RSS feeds and other sources.
"""
from .fetcher import RSSFetcher, fetch_all_sources

__all__ = ["RSSFetcher", "fetch_all_sources"]
