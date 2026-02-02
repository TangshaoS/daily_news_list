"""Calculate hotness score for news items"""
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class HotnessCalculator:
    """Calculate hotness score based on recency and source weight"""
    
    def __init__(self, base_decay_hours: int = 24):
        """
        Args:
            base_decay_hours: Hours after which score decays significantly
        """
        self.base_decay_hours = base_decay_hours
    
    def calculate(
        self,
        published_at: datetime,
        source_weight: float = 1.0,
        view_count: int = 0,
        current_time: Optional[datetime] = None
    ) -> float:
        """
        Calculate hotness score
        
        Args:
            published_at: When the news was published
            source_weight: Weight of the source (e.g., Reuters = 1.5)
            view_count: Number of views
            current_time: Current time (defaults to now)
        
        Returns:
            Hotness score (higher = hotter)
        """
        if current_time is None:
            current_time = datetime.utcnow()
        
        # Time decay factor (exponential decay)
        hours_old = (current_time - published_at).total_seconds() / 3600
        
        if hours_old < 0:
            hours_old = 0
        
        # Exponential decay: score = e^(-hours / decay_hours)
        time_factor = 1.0 / (1.0 + hours_old / self.base_decay_hours)
        
        # View count boost (logarithmic to prevent gaming)
        view_factor = 1.0 + 0.1 * (view_count ** 0.5)
        
        # Final score
        score = source_weight * time_factor * view_factor
        
        return round(score, 4)
