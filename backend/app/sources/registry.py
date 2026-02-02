"""
Source registry - defines all available news sources.
"""
from ..models import SourceConfig, Category

# =============================================================================
# SOURCE CONFIGURATIONS
# =============================================================================

REUTERS = SourceConfig(
    id="reuters",
    name="Reuters",
    name_zh="路透社",
    weight=1.0,  # High credibility
    language="en",
    feed_urls=[
        # Reuters官方feed已停用，使用Google News获取Reuters内容
        "https://news.google.com/rss/search?q=site:reuters.com+economy+OR+markets+when:1d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=site:reuters.com+politics+OR+world+when:1d&hl=en-US&gl=US&ceid=US:en",
    ],
    category_hints={
        "economy": Category.ECONOMY,
        "politics": Category.GEOPOLITICS,
    }
)

WSJ = SourceConfig(
    id="wsj",
    name="Wall Street Journal",
    name_zh="华尔街日报",
    weight=1.0,
    language="en",
    feed_urls=[
        # WSJ RSS feeds (some publicly accessible)
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
        # Google News fallback for WSJ content
        "https://news.google.com/rss/search?q=site:wsj.com+when:1d&hl=en-US&gl=US&ceid=US:en",
    ],
    category_hints={
        "RSSMarketsMain": Category.MARKETS,
        "RSSWorldNews": Category.GEOPOLITICS,
        "WSJcomUSBusiness": Category.ECONOMY,
    }
)

BLOOMBERG = SourceConfig(
    id="bloomberg",
    name="Bloomberg",
    name_zh="彭博社",
    weight=1.0,
    language="en",
    feed_urls=[
        # Bloomberg doesn't have public RSS, use Google News
        "https://news.google.com/rss/search?q=site:bloomberg.com+economy+OR+markets+when:1d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=site:bloomberg.com+commodities+OR+metals+when:1d&hl=en-US&gl=US&ceid=US:en",
    ],
)

FT = SourceConfig(
    id="ft",
    name="Financial Times",
    name_zh="金融时报",
    weight=1.0,
    language="en",
    feed_urls=[
        # FT官方RSS需要付费订阅，使用Google News获取FT内容
        "https://news.google.com/rss/search?q=site:ft.com+economy+OR+markets+when:1d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=site:ft.com+geopolitics+OR+china+OR+trade+when:1d&hl=en-US&gl=US&ceid=US:en",
    ],
    category_hints={
        "economy": Category.ECONOMY,
        "markets": Category.MARKETS,
        "geopolitics": Category.GEOPOLITICS,
    }
)

THEPAPER = SourceConfig(
    id="thepaper",
    name="The Paper (Pengpai)",
    name_zh="澎湃新闻",
    weight=0.9,  # Slightly lower for regional focus
    language="zh",
    feed_urls=[
        # 使用Google News中文版获取澎湃新闻内容
        "https://news.google.com/rss/search?q=site:thepaper.cn+经济+OR+财经&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=site:thepaper.cn+国际+OR+时政&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        # 备用RSSHub实例（如果上面失败可尝试自建实例）
        # "https://your-rsshub-instance/thepaper/channel/25951",
    ],
    category_hints={
        "经济": Category.ECONOMY,
        "国际": Category.GEOPOLITICS,
    }
)

# =============================================================================
# REGISTRY
# =============================================================================

SOURCE_REGISTRY: dict[str, SourceConfig] = {
    "reuters": REUTERS,
    "wsj": WSJ,
    "bloomberg": BLOOMBERG,
    "ft": FT,
    "thepaper": THEPAPER,
}


def get_source(source_id: str) -> SourceConfig | None:
    """Get a source configuration by ID."""
    return SOURCE_REGISTRY.get(source_id)


def get_all_sources() -> list[SourceConfig]:
    """Get all registered source configurations."""
    return list(SOURCE_REGISTRY.values())
