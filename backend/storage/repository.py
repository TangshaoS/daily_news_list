"""Data repository for news items"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_
from typing import List, Optional
from datetime import datetime, timedelta
from backend.models.news import NewsItem, Summary, Topic, Source


class NewsRepository:
    """Repository for news data operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # News Items
    def create_news_item(self, news_item: NewsItem) -> NewsItem:
        """Create a new news item"""
        self.db.add(news_item)
        self.db.commit()
        self.db.refresh(news_item)
        return news_item
    
    def get_news_item_by_url(self, url: str) -> Optional[NewsItem]:
        """Get news item by URL"""
        return self.db.query(NewsItem).filter(NewsItem.url == url).first()
    
    def get_news_item(self, news_id: int) -> Optional[NewsItem]:
        """Get news item by ID"""
        return self.db.query(NewsItem).filter(NewsItem.id == news_id).first()
    
    def get_hot_news(
        self,
        limit: int = 20,
        topic_id: Optional[int] = None,
        hours: int = 24
    ) -> List[NewsItem]:
        """Get hot news items"""
        query = self.db.query(NewsItem)
        
        # Filter by topic if specified
        if topic_id:
            query = query.filter(NewsItem.topic_id == topic_id)
        
        # Filter by time window
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(NewsItem.published_at >= cutoff_time)
        
        # Order by hotness score
        return query.order_by(desc(NewsItem.hotness_score)).limit(limit).all()
    
    def get_latest_news(
        self,
        limit: int = 20,
        topic_id: Optional[int] = None
    ) -> List[NewsItem]:
        """Get latest news items"""
        query = self.db.query(NewsItem)
        
        if topic_id:
            query = query.filter(NewsItem.topic_id == topic_id)
        
        return query.order_by(desc(NewsItem.published_at)).limit(limit).all()
    
    def search_news(
        self,
        keyword: str,
        limit: int = 20,
        topic_id: Optional[int] = None
    ) -> List[NewsItem]:
        """Search news by keyword"""
        query = self.db.query(NewsItem).filter(
            NewsItem.title.contains(keyword) | NewsItem.content.contains(keyword)
        )
        
        if topic_id:
            query = query.filter(NewsItem.topic_id == topic_id)
        
        return query.order_by(desc(NewsItem.published_at)).limit(limit).all()
    
    def update_hotness_score(self, news_id: int, score: float):
        """Update hotness score for a news item"""
        news_item = self.get_news_item(news_id)
        if news_item:
            news_item.hotness_score = score
            self.db.commit()
    
    # Summaries
    def create_summary(self, summary: Summary) -> Summary:
        """Create a summary"""
        self.db.add(summary)
        self.db.commit()
        self.db.refresh(summary)
        return summary
    
    def get_summary(self, news_item_id: int) -> Optional[Summary]:
        """Get summary for a news item"""
        return self.db.query(Summary).filter(Summary.news_item_id == news_item_id).first()
    
    # Topics
    def get_topic_by_name(self, name: str) -> Optional[Topic]:
        """Get topic by name"""
        return self.db.query(Topic).filter(Topic.name == name).first()
    
    def get_all_topics(self) -> List[Topic]:
        """Get all topics"""
        return self.db.query(Topic).all()
    
    # Sources
    def get_source_by_name(self, name: str) -> Optional[Source]:
        """Get source by name"""
        return self.db.query(Source).filter(Source.name == name).first()
    
    def create_source(self, source: Source) -> Source:
        """Create a news source"""
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source
    
    def get_enabled_sources(self) -> List[Source]:
        """Get all enabled sources"""
        return self.db.query(Source).filter(Source.enabled == True).all()
