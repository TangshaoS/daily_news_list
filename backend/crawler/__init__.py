"""News crawler module"""
from .rss_fetcher import RSSFetcher
from .content_extractor import ContentExtractor
from .deduplicator import Deduplicator

__all__ = ["RSSFetcher", "ContentExtractor", "Deduplicator"]
