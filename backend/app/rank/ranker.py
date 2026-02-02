"""
Hotness ranking for news items.

Scoring formula (MVP):
    score = source_weight × recency × (1 + α × (cluster_size - 1))

Where:
- source_weight: Credibility/importance of the source (0.5-1.5)
- recency: Exponential decay based on age (e^(-hours/half_life))
- cluster_size: Number of sources covering the same story
- α: Multi-source boost factor (default 0.3)
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from ..models import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class RankingConfig:
    """Configuration for the ranking algorithm."""
    # Recency decay half-life in hours (after this time, score is halved)
    recency_half_life_hours: float = 12.0
    
    # Multi-source boost factor (α)
    cluster_boost_factor: float = 0.3
    
    # Maximum age to consider (older items get minimum recency score)
    max_age_hours: float = 72.0
    
    # Minimum recency score (for very old items)
    min_recency_score: float = 0.1


class HotnessRanker:
    """
    Ranks news items by hotness/importance.
    """
    
    def __init__(self, config: RankingConfig | None = None):
        self.config = config or RankingConfig()
    
    def calculate_recency_score(
        self,
        published_at: datetime | None,
        reference_time: datetime | None = None,
    ) -> float:
        """
        Calculate recency score based on exponential decay.
        
        Args:
            published_at: When the article was published
            reference_time: Time to compare against (defaults to now)
        
        Returns:
            Recency score between min_recency_score and 1.0
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        if published_at is None:
            # No publish date - assume moderately recent
            return 0.5
        
        # Ensure both datetimes are timezone-aware
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        
        # Calculate age in hours
        age_seconds = (reference_time - published_at).total_seconds()
        age_hours = max(0, age_seconds / 3600)
        
        # Cap at max age
        if age_hours >= self.config.max_age_hours:
            return self.config.min_recency_score
        
        # Exponential decay: score = e^(-λt) where λ = ln(2) / half_life
        decay_constant = math.log(2) / self.config.recency_half_life_hours
        recency = math.exp(-decay_constant * age_hours)
        
        return max(recency, self.config.min_recency_score)
    
    def calculate_cluster_boost(self, cluster_size: int) -> float:
        """
        Calculate boost factor for multi-source stories.
        
        Args:
            cluster_size: Number of unique sources covering the story
        
        Returns:
            Boost multiplier (1.0 for single source, higher for multiple)
        """
        if cluster_size <= 1:
            return 1.0
        
        # Boost = 1 + α × (cluster_size - 1)
        # This gives linear boost with diminishing per-source returns
        boost = 1.0 + self.config.cluster_boost_factor * (cluster_size - 1)
        
        # Cap the boost to prevent extreme values
        return min(boost, 3.0)
    
    def score_item(
        self,
        item: NewsItem,
        reference_time: datetime | None = None,
    ) -> float:
        """
        Calculate the final hotness score for a news item.
        
        Args:
            item: The NewsItem to score
            reference_time: Reference time for recency calculation
        
        Returns:
            Final hotness score
        """
        # Calculate components
        recency = self.calculate_recency_score(item.published_at, reference_time)
        cluster_boost = self.calculate_cluster_boost(item.cluster_size)
        
        # Store recency score on item for transparency
        item.recency_score = recency
        
        # Final score
        score = item.source_weight * recency * cluster_boost
        
        # Bonus for having multiple relevant categories
        if len(item.categories) > 1:
            score *= 1.1  # 10% bonus for cross-category relevance
        
        item.final_score = score
        return score
    
    def rank_items(
        self,
        items: list[NewsItem],
        reference_time: datetime | None = None,
    ) -> list[NewsItem]:
        """
        Score and sort items by hotness (descending).
        
        Args:
            items: List of NewsItem objects
            reference_time: Reference time for recency calculation
        
        Returns:
            Sorted list (highest score first)
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        # Score all items
        for item in items:
            self.score_item(item, reference_time)
        
        # Sort by final score (descending)
        sorted_items = sorted(items, key=lambda x: x.final_score, reverse=True)
        
        # Log score distribution
        if sorted_items:
            top_score = sorted_items[0].final_score
            median_idx = len(sorted_items) // 2
            median_score = sorted_items[median_idx].final_score if median_idx < len(sorted_items) else 0
            logger.info(
                f"Ranked {len(sorted_items)} items. "
                f"Top score: {top_score:.3f}, Median: {median_score:.3f}"
            )
        
        return sorted_items


def rank_items(
    items: list[NewsItem],
    config: RankingConfig | None = None,
) -> list[NewsItem]:
    """
    Convenience function to rank items by hotness.
    
    Args:
        items: List of NewsItem objects
        config: Optional ranking configuration
    
    Returns:
        Sorted list (highest score first)
    """
    ranker = HotnessRanker(config)
    return ranker.rank_items(items)
