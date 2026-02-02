"""Deduplicate news items"""
from typing import List, Dict
from difflib import SequenceMatcher
import hashlib
import logging

logger = logging.getLogger(__name__)


class Deduplicator:
    """Remove duplicate news items"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def _generate_hash(self, title: str, url: str) -> str:
        """Generate hash for a news item"""
        content = f"{title}:{url}".lower()
        return hashlib.md5(content.encode()).hexdigest()
    
    def deduplicate(self, items: List[Dict], existing_urls: set = None) -> List[Dict]:
        """
        Remove duplicates from news items
        
        Args:
            items: List of news item dicts
            existing_urls: Set of existing URLs to filter out
        
        Returns:
            Deduplicated list of news items
        """
        if existing_urls is None:
            existing_urls = set()
        
        # Filter by URL first
        seen_urls = set(existing_urls)
        unique_items = []
        
        for item in items:
            url = item.get('link', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_items.append(item)
        
        # Further deduplication by title similarity
        if len(unique_items) <= 1:
            return unique_items
        
        deduplicated = [unique_items[0]]
        
        for item in unique_items[1:]:
            is_duplicate = False
            title = item.get('title', '')
            
            for existing in deduplicated:
                existing_title = existing.get('title', '')
                similarity = self._calculate_similarity(title, existing_title)
                
                if similarity >= self.similarity_threshold:
                    is_duplicate = True
                    logger.debug(f"Duplicate detected: {title[:50]}... (similarity: {similarity:.2f})")
                    break
            
            if not is_duplicate:
                deduplicated.append(item)
        
        logger.info(f"Deduplicated {len(items)} items to {len(deduplicated)}")
        return deduplicated
