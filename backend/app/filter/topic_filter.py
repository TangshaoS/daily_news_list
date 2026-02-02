"""
Topic-based filtering for news items.
Filters news by relevance to: geopolitics, economy, markets, supply chain, commodities, AI.
"""
import logging
import re
from dataclasses import dataclass
from typing import Callable

from ..models import Category, NewsItem

logger = logging.getLogger(__name__)


@dataclass
class TopicKeywords:
    """Keywords for a specific topic category."""
    category: Category
    # Strong keywords - one match is enough
    strong: set[str]
    # Regular keywords - need multiple matches or combined with other signals
    regular: set[str]
    # Negative keywords - presence reduces relevance
    negative: set[str]


# =============================================================================
# KEYWORD DICTIONARIES
# =============================================================================

GEOPOLITICS_KEYWORDS = TopicKeywords(
    category=Category.GEOPOLITICS,
    strong={
        # Conflicts & tensions
        "war", "conflict", "invasion", "military", "troops", "sanctions",
        "ceasefire", "treaty", "alliance", "nato", "defense",
        # Diplomacy
        "summit", "diplomatic", "ambassador", "foreign minister", "state visit",
        "bilateral", "multilateral",
        # Regions of interest
        "ukraine", "russia", "taiwan", "china", "middle east", "gaza", "israel",
        "iran", "north korea", "south china sea", "indo-pacific",
        # Chinese
        "地缘", "战争", "冲突", "制裁", "军事", "外交", "领土",
    },
    regular={
        "government", "president", "prime minister", "parliament", "election",
        "policy", "border", "territory", "sovereignty",
        "政府", "总统", "首相", "选举", "边境",
    },
    negative=set(),
)

SUPPLY_CHAIN_KEYWORDS = TopicKeywords(
    category=Category.SUPPLY_CHAIN,
    strong={
        "supply chain", "supply-chain", "logistics", "shipping", "freight",
        "port", "semiconductor", "chip shortage", "chip supply",
        "decoupling", "reshoring", "nearshoring", "onshoring",
        "blockade", "embargo", "export controls", "export ban",
        # Chinese
        "供应链", "物流", "芯片", "半导体", "脱钩", "出口管制",
    },
    regular={
        "manufacturing", "factory", "production", "inventory", "shortage",
        "bottleneck", "disruption", "delay",
        "制造", "工厂", "生产", "短缺",
    },
    negative=set(),
)

ECONOMY_KEYWORDS = TopicKeywords(
    category=Category.ECONOMY,
    strong={
        # Economic indicators
        "gdp", "inflation", "cpi", "ppi", "unemployment", "jobs report",
        "economic growth", "recession", "stagflation",
        # Central banks & policy
        "federal reserve", "fed", "interest rate", "rate hike", "rate cut",
        "monetary policy", "quantitative", "ecb", "boj", "pboc",
        "central bank", "treasury",
        # Fiscal
        "fiscal policy", "government spending", "budget deficit", "debt ceiling",
        # Chinese
        "经济", "通胀", "利率", "央行", "货币政策", "财政", "GDP",
    },
    regular={
        "growth", "economy", "economic", "market", "financial",
        "增长", "金融", "市场",
    },
    negative=set(),
)

MARKETS_KEYWORDS = TopicKeywords(
    category=Category.MARKETS,
    strong={
        # Market sentiment
        "bull market", "bear market", "rally", "selloff", "crash",
        "volatility", "vix", "risk appetite", "risk-off",
        # Indices
        "s&p 500", "nasdaq", "dow jones", "ftse", "nikkei", "hang seng",
        "shanghai composite", "a-shares",
        # Investment
        "investor", "investment", "portfolio", "hedge fund", "etf",
        "股市", "牛市", "熊市", "投资", "股票",
    },
    regular={
        "stock", "equity", "bond", "yield", "trading", "shares",
        "债券", "收益率", "交易",
    },
    negative=set(),
)

COMMODITIES_KEYWORDS = TopicKeywords(
    category=Category.COMMODITIES,
    strong={
        # Energy
        "oil", "crude", "brent", "wti", "opec", "natural gas", "lng",
        # Metals
        "gold", "silver", "copper", "aluminum", "iron ore", "steel",
        "rare earth", "lithium", "cobalt", "nickel",
        "稀土", "锂", "钴", "镍",
        # Agriculture
        "wheat", "corn", "soybean", "commodity prices",
        # General
        "commodity", "commodities", "raw materials",
        "大宗商品", "原材料", "有色金属",
    },
    regular={
        "mining", "metal", "energy", "agriculture",
        "矿业", "金属", "能源",
    },
    negative=set(),
)

AI_TECH_KEYWORDS = TopicKeywords(
    category=Category.AI_TECH,
    strong={
        # AI specific
        "artificial intelligence", "ai", "machine learning", "deep learning",
        "large language model", "llm", "chatgpt", "gpt", "openai", "anthropic",
        "generative ai", "gen ai",
        # AI business
        "ai chip", "ai investment", "ai regulation", "ai safety",
        # AI infrastructure - data centers & cooling
        "data center", "datacenter", "hyperscaler",
        "liquid cooling", "immersion cooling",
        # Chinese
        "人工智能", "大模型", "机器学习",
        "数据中心", "液冷", "浸没式冷却",
    },
    regular={
        "technology", "tech", "nvidia", "semiconductor",
        "科技", "技术",
    },
    negative=set(),
)

ENERGY_INFRA_KEYWORDS = TopicKeywords(
    category=Category.ENERGY_INFRA,
    strong={
        # Power & electricity
        "electricity", "power grid", "power plant", "blackout", "brownout",
        "grid stability", "power shortage", "electricity price",
        "transmission line", "substation", "transformer",
        # Cooling technology
        "liquid cooling", "immersion cooling", "cooling system",
        "heat dissipation", "thermal management",
        # Energy storage
        "battery storage", "energy storage", "pumped hydro",
        "grid-scale battery", "utility-scale storage",
        # Renewables
        "solar power", "wind power", "renewable energy", "clean energy",
        "nuclear power", "nuclear plant", "hydropower",
        # Smart grid & infrastructure
        "smart grid", "microgrid", "distributed energy",
        "energy infrastructure", "power infrastructure",
        # Chinese - Power & electricity
        "电力", "电网", "输电", "配电", "变电站", "停电", "限电",
        "电价", "电力短缺", "电力供应",
        # Chinese - Cooling
        "液冷", "浸没式冷却", "冷却系统", "散热", "热管理",
        # Chinese - Energy storage
        "储能", "电池储能", "抽水蓄能",
        # Chinese - Renewables & infrastructure
        "新能源", "清洁能源", "光伏", "风电", "核电", "水电",
        "能源基础设施", "电力基础设施",
    },
    regular={
        "power", "energy", "utility", "grid", "electricity demand",
        "能源", "电能", "公用事业",
    },
    negative=set(),
)

ALL_TOPIC_KEYWORDS = [
    GEOPOLITICS_KEYWORDS,
    SUPPLY_CHAIN_KEYWORDS,
    ECONOMY_KEYWORDS,
    MARKETS_KEYWORDS,
    COMMODITIES_KEYWORDS,
    AI_TECH_KEYWORDS,
    ENERGY_INFRA_KEYWORDS,
]


# =============================================================================
# FILTER IMPLEMENTATION
# =============================================================================

class TopicFilter:
    """
    Filters and categorizes news items by topic relevance.
    Uses keyword matching with strong/regular/negative weighting.
    """
    
    def __init__(
        self,
        topic_keywords: list[TopicKeywords] | None = None,
        min_score: float = 1.0,
    ):
        """
        Args:
            topic_keywords: List of TopicKeywords to use. Defaults to all topics.
            min_score: Minimum relevance score to pass filter.
        """
        self.topics = topic_keywords or ALL_TOPIC_KEYWORDS
        self.min_score = min_score
        
        # Pre-compile patterns for efficiency
        self._compiled_patterns: dict[Category, dict[str, re.Pattern]] = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for each topic."""
        for topic in self.topics:
            self._compiled_patterns[topic.category] = {
                "strong": self._keywords_to_pattern(topic.strong),
                "regular": self._keywords_to_pattern(topic.regular),
                "negative": self._keywords_to_pattern(topic.negative) if topic.negative else None,
            }
    
    @staticmethod
    def _keywords_to_pattern(keywords: set[str]) -> re.Pattern | None:
        """Convert a set of keywords to a compiled regex pattern."""
        if not keywords:
            return None
        # Escape special characters and join with |
        escaped = [re.escape(kw) for kw in keywords]
        pattern = r"\b(" + "|".join(escaped) + r")\b"
        return re.compile(pattern, re.IGNORECASE)
    
    def score_item(self, item: NewsItem) -> dict[Category, float]:
        """
        Calculate relevance scores for each topic category.
        
        Returns:
            Dict mapping Category to relevance score
        """
        # Combine title and summary for matching
        text = f"{item.title} {item.summary}".lower()
        
        scores: dict[Category, float] = {}
        
        for topic in self.topics:
            patterns = self._compiled_patterns[topic.category]
            score = 0.0
            
            # Strong keywords: +2 points each
            if patterns["strong"]:
                strong_matches = patterns["strong"].findall(text)
                score += len(set(strong_matches)) * 2.0
            
            # Regular keywords: +0.5 points each
            if patterns["regular"]:
                regular_matches = patterns["regular"].findall(text)
                score += len(set(regular_matches)) * 0.5
            
            # Negative keywords: -1 point each
            if patterns["negative"]:
                negative_matches = patterns["negative"].findall(text)
                score -= len(set(negative_matches)) * 1.0
            
            if score > 0:
                scores[topic.category] = score
        
        return scores
    
    def filter_item(self, item: NewsItem) -> bool:
        """
        Check if an item passes the relevance filter.
        Also populates item.categories with matched topics.
        
        Returns:
            True if item is relevant, False otherwise
        """
        scores = self.score_item(item)
        
        # Get categories that meet the threshold
        relevant_categories = [
            cat for cat, score in scores.items()
            if score >= self.min_score
        ]
        
        if relevant_categories:
            item.categories = relevant_categories
            # Store top keywords for debugging/display
            return True
        
        return False
    
    def filter_items(self, items: list[NewsItem]) -> list[NewsItem]:
        """
        Filter a list of items, keeping only relevant ones.
        
        Args:
            items: List of NewsItem objects
        
        Returns:
            Filtered list with categories populated
        """
        filtered = [item for item in items if self.filter_item(item)]
        
        logger.info(
            f"Topic filter: {len(filtered)}/{len(items)} items passed "
            f"(removed {len(items) - len(filtered)})"
        )
        
        return filtered


def filter_by_topics(
    items: list[NewsItem],
    min_score: float = 1.0,
) -> list[NewsItem]:
    """
    Convenience function to filter items by topic relevance.
    
    Args:
        items: List of NewsItem objects
        min_score: Minimum relevance score
    
    Returns:
        Filtered list with categories populated
    """
    topic_filter = TopicFilter(min_score=min_score)
    return topic_filter.filter_items(items)
