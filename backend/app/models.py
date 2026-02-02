"""
Data models for the news summary pipeline.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Category(str, Enum):
    """News category classification."""
    GEOPOLITICS = "geopolitics"       # 地缘政治
    ECONOMY = "economy"               # 经济数据/货币政策
    MARKETS = "markets"               # 投资市场情绪
    SUPPLY_CHAIN = "supply_chain"     # 供应链相关
    COMMODITIES = "commodities"       # 大宗商品/稀土/有色金属
    AI_TECH = "ai_tech"               # AI技术
    ENERGY_INFRA = "energy_infra"     # 能源基础设施（电力、液冷、储能）
    OTHER = "other"


@dataclass
class NewsItem:
    """Represents a single news article/link."""
    url: str
    title: str
    source_id: str              # e.g., "reuters", "wsj", "bloomberg"
    published_at: Optional[datetime] = None
    
    # Extracted/computed fields
    summary: str = ""           # RSS description or extracted snippet
    normalized_url: str = ""    # Canonical URL without tracking params
    
    # Classification
    categories: list[Category] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    
    # Scoring
    source_weight: float = 1.0
    recency_score: float = 0.0
    cluster_size: int = 1       # How many sources reported same story
    final_score: float = 0.0
    
    # Metadata
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    cluster_id: Optional[str] = None  # For grouping similar stories
    
    def __hash__(self):
        return hash(self.normalized_url or self.url)
    
    def __eq__(self, other):
        if not isinstance(other, NewsItem):
            return False
        url1 = self.normalized_url or self.url
        url2 = other.normalized_url or other.url
        return url1 == url2


@dataclass
class SourceConfig:
    """Configuration for a news source."""
    id: str                     # Unique identifier
    name: str                   # Display name
    name_zh: str                # Chinese display name
    feed_urls: list[str]        # RSS/Atom feed URLs
    weight: float = 1.0         # Source credibility/importance weight
    language: str = "en"        # Primary language
    
    # Optional: category hints (feeds often organized by topic)
    category_hints: dict[str, Category] = field(default_factory=dict)
    
    # Rate limiting
    min_fetch_interval_seconds: int = 300  # 5 minutes minimum


@dataclass
class ExportResult:
    """Result of exporting news to NotebookLM format."""
    filepath: str
    url_count: int
    categories: list[Category]
    timestamp: datetime = field(default_factory=datetime.utcnow)
