"""Extract main content from news articles"""
import requests
from bs4 import BeautifulSoup
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extract main content from web pages"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def extract_content(self, url: str) -> Optional[str]:
        """
        Extract main content from a news article URL
        
        Returns:
            Main content text or None if extraction fails
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
                script.decompose()
            
            # Try to find main content area
            # Common selectors for news articles
            content_selectors = [
                'article',
                '[role="article"]',
                '.article-body',
                '.article-content',
                '.story-body',
                '.content',
                'main',
                '.post-content'
            ]
            
            content = None
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    content = ' '.join([elem.get_text(strip=True) for elem in elements])
                    if len(content) > 200:  # Minimum content length
                        break
            
            # Fallback: get all paragraphs
            if not content or len(content) < 200:
                paragraphs = soup.find_all('p')
                content = ' '.join([p.get_text(strip=True) for p in paragraphs])
            
            # Clean up content
            content = ' '.join(content.split())  # Normalize whitespace
            
            if len(content) < 100:
                logger.warning(f"Extracted content too short for {url}")
                return None
            
            return content
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None
