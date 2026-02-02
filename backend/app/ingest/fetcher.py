"""
RSS/Feed fetcher - pulls news items from configured sources.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

import feedparser
import httpx
from dateutil import parser as date_parser

from ..models import NewsItem, SourceConfig
from ..sources import get_all_sources

logger = logging.getLogger(__name__)

# HTTP client settings
DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsSummaryBot/1.0; +https://github.com/news-summary)"
)


class RSSFetcher:
    """Fetches and parses RSS/Atom feeds."""
    
    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def fetch_feed(self, url: str) -> str | None:
        """Fetch raw feed content from URL."""
        if not self._client:
            raise RuntimeError("Fetcher not initialized. Use async with.")
        
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error fetching {url}: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.warning(f"Request error fetching {url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
        
        return None
    
    def parse_feed(
        self,
        content: str,
        source: SourceConfig,
        feed_url: str,
    ) -> list[NewsItem]:
        """Parse feed content into NewsItem objects."""
        items = []
        
        try:
            feed = feedparser.parse(content)
        except Exception as e:
            logger.error(f"Failed to parse feed from {source.id}: {e}")
            return items
        
        for entry in feed.entries:
            try:
                item = self._entry_to_news_item(entry, source, feed_url)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse entry from {source.id}: {e}")
                continue
        
        logger.info(f"Parsed {len(items)} items from {source.id} ({feed_url})")
        return items
    
    def _entry_to_news_item(
        self,
        entry: dict,
        source: SourceConfig,
        feed_url: str,
    ) -> NewsItem | None:
        """Convert a feedparser entry to a NewsItem."""
        # Extract URL
        url = entry.get("link") or entry.get("id")
        if not url:
            return None
        
        # Extract title
        title = entry.get("title", "").strip()
        if not title:
            return None
        
        # Extract published date
        published_at = None
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if date_field in entry and entry[date_field]:
                try:
                    import time
                    published_at = datetime.fromtimestamp(
                        time.mktime(entry[date_field]),
                        tz=timezone.utc,
                    )
                    break
                except (ValueError, TypeError, OverflowError):
                    continue
        
        # Fallback: try parsing string dates
        if not published_at:
            for date_field in ["published", "updated", "created"]:
                if date_field in entry and entry[date_field]:
                    try:
                        published_at = date_parser.parse(entry[date_field])
                        if published_at.tzinfo is None:
                            published_at = published_at.replace(tzinfo=timezone.utc)
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Extract summary/description
        summary = ""
        if "summary" in entry:
            summary = entry["summary"]
        elif "description" in entry:
            summary = entry["description"]
        
        # Clean HTML from summary (basic)
        if summary:
            import re
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            summary = summary[:500]  # Truncate long summaries
        
        return NewsItem(
            url=url,
            title=title,
            source_id=source.id,
            published_at=published_at,
            summary=summary,
            source_weight=source.weight,
        )
    
    async def fetch_source(self, source: SourceConfig) -> list[NewsItem]:
        """Fetch all feeds for a single source."""
        all_items = []
        
        tasks = [self.fetch_feed(url) for url in source.feed_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, result in zip(source.feed_urls, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch {url}: {result}")
                continue
            if result:
                items = self.parse_feed(result, source, url)
                all_items.extend(items)
        
        return all_items


async def fetch_all_sources(
    sources: list[SourceConfig] | None = None,
) -> list[NewsItem]:
    """
    Fetch news from all configured sources.
    
    Args:
        sources: Optional list of sources to fetch. Defaults to all registered sources.
    
    Returns:
        List of all fetched NewsItem objects.
    """
    if sources is None:
        sources = get_all_sources()
    
    all_items = []
    
    async with RSSFetcher() as fetcher:
        tasks = [fetcher.fetch_source(source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for source, result in zip(sources, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch source {source.id}: {result}")
                continue
            all_items.extend(result)
    
    logger.info(f"Total items fetched: {len(all_items)}")
    return all_items
