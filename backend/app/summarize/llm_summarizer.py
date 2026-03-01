"""
LLM-based summarization - uses language models for high-quality summaries.

This module is OPTIONAL - only used if you have API keys configured.
Supports OpenAI and Anthropic APIs.

Usage:
    export OPENAI_API_KEY=sk-...
    # or
    export ANTHROPIC_API_KEY=sk-ant-...
"""
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from ..models import Category, NewsItem

logger = logging.getLogger(__name__)


@dataclass
class SummaryConfig:
    """Configuration for LLM summarization."""
    # Number of bullet points to generate
    num_points: int = 5
    # Maximum tokens for summary
    max_tokens: int = 300
    # Language for output
    language: Literal["en", "zh"] = "zh"
    # Model to use
    model: str = "gpt-4o-mini"  # or "claude-3-haiku-20240307"


# System prompt for summary generation
SYSTEM_PROMPT = """You are a professional news analyst specializing in global economics, geopolitics, and financial markets.

Your task is to summarize news articles into concise bullet points that:
1. Capture the most important facts and implications
2. Highlight any market-moving information
3. Note geopolitical or supply chain impacts if relevant
4. Use clear, professional language

Focus areas:
- 地缘政治 (Geopolitics): conflicts, sanctions, diplomacy
- 经济数据 (Economy): GDP, inflation, central bank policies
- 投资市场 (Markets): sentiment, trends, key movements
- 供应链 (Supply Chain): disruptions, trade, logistics
- 大宗商品 (Commodities): oil, metals, rare earths
- AI/科技 (AI & Tech): developments, investments, regulations"""

# Prompt for refining extractive cluster points (input: headline + bullets)
REFINE_CLUSTER_SYSTEM = """You are a news editor. Given a headline and a list of raw bullet points from multiple sources, output 3–5 refined, concise bullet points that capture the key facts. Use clear language. 用中文输出。"""
REFINE_CLUSTER_USER_TEMPLATE = """标题: {headline}

原始要点:
{points}

请输出 3–5 条精炼后的要点，每条一行，用 "•" 开头。"""


def _build_summary_prompt(
    item: NewsItem,
    config: SummaryConfig,
) -> str:
    """Build the user prompt for summarization."""
    categories_str = ", ".join(c.value for c in item.categories) if item.categories else "general"
    
    lang_instruction = "用中文输出" if config.language == "zh" else "Output in English"
    
    return f"""请为以下新闻生成{config.num_points}条要点摘要。{lang_instruction}。

标题: {item.title}
来源: {item.source_id}
分类: {categories_str}

内容摘要:
{item.summary or '(无详细内容，仅根据标题总结)'}

请输出{config.num_points}条简洁的要点，每条一行，用 "•" 开头。"""


def _build_refine_prompt(headline: str, points: list[str]) -> str:
    points_text = "\n".join(f"- {p}" for p in points) if points else "(无)"
    return REFINE_CLUSTER_USER_TEMPLATE.format(headline=headline, points=points_text)


class BaseLLMSummarizer(ABC):
    """Abstract base class for LLM summarizers."""
    
    @abstractmethod
    async def summarize(self, item: NewsItem, config: SummaryConfig) -> list[str]:
        """Generate summary bullet points for a news item."""
        pass

    async def refine_cluster_points(
        self,
        headline: str,
        points: list[str],
        max_tokens: int = 300,
    ) -> list[str]:
        """Refine extractive cluster points into concise bullets. Default: return points unchanged."""
        return points


class OpenAISummarizer(BaseLLMSummarizer):
    """Summarizer using OpenAI API."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        # Lazy import
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
    
    async def summarize(self, item: NewsItem, config: SummaryConfig) -> list[str]:
        """Generate summary using OpenAI."""
        prompt = _build_summary_prompt(item, config)
        
        try:
            response = await self.client.chat.completions.create(
                model=config.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=config.max_tokens,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content or ""
            return _parse_bullet_points(content)
        
        except Exception as e:
            logger.error(f"OpenAI summarization failed: {e}")
            return []

    async def refine_cluster_points(
        self,
        headline: str,
        points: list[str],
        max_tokens: int = 300,
    ) -> list[str]:
        if not points:
            return []
        prompt = _build_refine_prompt(headline, points)
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": REFINE_CLUSTER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            content = response.choices[0].message.content or ""
            return _parse_bullet_points(content)
        except Exception as e:
            logger.error(f"OpenAI refine_cluster_points failed: {e}")
            return points


class AnthropicSummarizer(BaseLLMSummarizer):
    """Summarizer using Anthropic API."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        # Lazy import
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
    
    async def summarize(self, item: NewsItem, config: SummaryConfig) -> list[str]:
        """Generate summary using Anthropic."""
        prompt = _build_summary_prompt(item, config)
        
        try:
            response = await self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=config.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            
            content = response.content[0].text if response.content else ""
            return _parse_bullet_points(content)
        
        except Exception as e:
            logger.error(f"Anthropic summarization failed: {e}")
            return []

    async def refine_cluster_points(
        self,
        headline: str,
        points: list[str],
        max_tokens: int = 300,
    ) -> list[str]:
        if not points:
            return []
        prompt = _build_refine_prompt(headline, points)
        try:
            response = await self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=max_tokens,
                system=REFINE_CLUSTER_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text if response.content else ""
            return _parse_bullet_points(content)
        except Exception as e:
            logger.error(f"Anthropic refine_cluster_points failed: {e}")
            return points


def _parse_bullet_points(text: str) -> list[str]:
    """Parse bullet points from LLM response."""
    lines = text.strip().split("\n")
    points = []
    
    for line in lines:
        line = line.strip()
        # Remove common bullet prefixes
        for prefix in ["•", "-", "*", "·", "●", "○"]:
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        # Remove numbered prefixes like "1.", "1)", etc.
        if line and line[0].isdigit():
            import re
            line = re.sub(r'^\d+[.)]\s*', '', line)
        
        if line:
            points.append(line)
    
    return points


class LLMSummarizer:
    """
    Factory class that selects the appropriate LLM backend.
    Falls back gracefully if no API keys are configured.
    """
    
    def __init__(self, backend: Literal["openai", "anthropic", "auto"] = "auto"):
        self.backend = backend
        self._summarizer: BaseLLMSummarizer | None = None
        self._init_backend()
    
    def _init_backend(self):
        """Initialize the appropriate backend."""
        if self.backend == "auto":
            # Try OpenAI first, then Anthropic
            if os.getenv("OPENAI_API_KEY"):
                try:
                    self._summarizer = OpenAISummarizer()
                    logger.info("Using OpenAI for summarization")
                    return
                except Exception as e:
                    logger.warning(f"Failed to init OpenAI: {e}")
            
            if os.getenv("ANTHROPIC_API_KEY"):
                try:
                    self._summarizer = AnthropicSummarizer()
                    logger.info("Using Anthropic for summarization")
                    return
                except Exception as e:
                    logger.warning(f"Failed to init Anthropic: {e}")
            
            logger.warning("No LLM API keys found. LLM summarization disabled.")
        
        elif self.backend == "openai":
            self._summarizer = OpenAISummarizer()
        
        elif self.backend == "anthropic":
            self._summarizer = AnthropicSummarizer()
    
    @property
    def is_available(self) -> bool:
        """Check if LLM summarization is available."""
        return self._summarizer is not None
    
    async def summarize(
        self,
        item: NewsItem,
        config: SummaryConfig | None = None,
    ) -> list[str]:
        """
        Generate summary bullet points for a news item.
        
        Args:
            item: NewsItem to summarize
            config: Optional summarization config
        
        Returns:
            List of bullet point strings, empty if unavailable
        """
        if not self._summarizer:
            logger.warning("LLM summarizer not available")
            return []
        
        if config is None:
            config = SummaryConfig()
        
        return await self._summarizer.summarize(item, config)

    async def refine_cluster_points(
        self,
        headline: str,
        points: list[str],
        max_tokens: int = 300,
    ) -> list[str]:
        """Refine extractive cluster points with LLM. Returns original points if LLM unavailable."""
        if not self._summarizer:
            return points
        return await self._summarizer.refine_cluster_points(
            headline, points, max_tokens=max_tokens
        )


async def refine_all_cluster_points(
    cluster_points: dict[str, list[str]],
    headlines: dict[str, str],
    backend: Literal["openai", "anthropic", "auto"] = "auto",
) -> dict[str, list[str]]:
    """
    Refine cluster points for digest using LLM. Keys are cluster_id.
    Returns original cluster_points if LLM is not available.
    """
    summarizer = LLMSummarizer(backend)
    if not summarizer.is_available:
        logger.warning("LLM not available; using extractive points as-is")
        return cluster_points
    result = {}
    for cid, points in cluster_points.items():
        headline = headlines.get(cid, "")
        refined = await summarizer.refine_cluster_points(headline, points)
        result[cid] = refined if refined else points
    return result


async def summarize_with_llm(
    items: list[NewsItem],
    config: SummaryConfig | None = None,
    backend: Literal["openai", "anthropic", "auto"] = "auto",
) -> dict[str, list[str]]:
    """
    Convenience function to summarize multiple items.
    
    Args:
        items: List of NewsItem objects
        config: Optional summarization config
        backend: LLM backend to use
    
    Returns:
        Dict mapping normalized_url to list of bullet points
    """
    summarizer = LLMSummarizer(backend)
    
    if not summarizer.is_available:
        logger.warning("LLM summarization not available - returning empty results")
        return {}
    
    results = {}
    for item in items:
        url = item.normalized_url or item.url
        points = await summarizer.summarize(item, config)
        if points:
            results[url] = points
    
    return results
