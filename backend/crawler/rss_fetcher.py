"""RSS feed fetcher"""
import feedparser
import requests
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RSSFetcher:
    """Fetch news from RSS feeds"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def fetch_feed(self, rss_url: str) -> List[Dict]:
        """
        Fetch and parse RSS feed
        
        Returns:
            List of news items with keys: title, link, published, description
        """
        try:
            feed = feedparser.parse(rss_url)
            
            if feed.bozo:
                logger.warning(f"Feed parsing error for {rss_url}: {feed.bozo_exception}")
            
            items = []
            for entry in feed.entries:
                try:
                    # Parse published date
                    published = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published = datetime(*entry.updated_parsed[:6])
                    else:
                        published = datetime.utcnow()
                    
                    items.append({
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'description': entry.get('description', ''),
                        'published': published,
                        'content': entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''
                    })
                except Exception as e:
                    logger.error(f"Error parsing entry: {e}")
                    continue
            
            logger.info(f"Fetched {len(items)} items from {rss_url}")
            return items
            
        except Exception as e:
            logger.error(f"Error fetching RSS feed {rss_url}: {e}")
            return []
    
    def fetch_multiple_feeds(self, rss_urls: List[str]) -> List[Dict]:
        """Fetch multiple RSS feeds"""
        all_items = []
        for url in rss_urls:
            items = self.fetch_feed(url)
            all_items.extend(items)
        return all_items
