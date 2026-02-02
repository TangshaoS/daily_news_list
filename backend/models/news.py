"""News data models"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.database import Base


class Source(Base):
    """News source model"""
    __tablename__ = "sources"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    url = Column(String(500), nullable=False)
    rss_url = Column(String(500))
    weight = Column(Float, default=1.0)  # Source weight for hotness calculation
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    news_items = relationship("NewsItem", back_populates="source")


class Topic(Base):
    """Topic/Category model"""
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    news_items = relationship("NewsItem", back_populates="topic")


class NewsItem(Base):
    """News article model"""
    __tablename__ = "news_items"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    original_title = Column(String(500))  # Original title in source language
    content = Column(Text, nullable=False)
    url = Column(String(1000), unique=True, nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    
    published_at = Column(DateTime, nullable=False, index=True)
    crawled_at = Column(DateTime, default=datetime.utcnow)
    
    # Hotness metrics
    hotness_score = Column(Float, default=0.0, index=True)
    view_count = Column(Integer, default=0)
    
    # Metadata
    language = Column(String(10), default="en")
    region = Column(String(50))  # e.g., "US", "EU", "Asia"
    tags = Column(String(500))  # Comma-separated tags
    
    source = relationship("Source", back_populates="news_items")
    topic = relationship("Topic", back_populates="news_items")
    summary = relationship("Summary", back_populates="news_item", uselist=False)


class Summary(Base):
    """News summary model"""
    __tablename__ = "summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    news_item_id = Column(Integer, ForeignKey("news_items.id"), unique=True, nullable=False)
    
    # Summary content (JSON string for bullet points)
    # Format: ["point1", "point2", ...]
    bullet_points = Column(Text, nullable=False)
    
    # Summary metadata
    method = Column(String(20), nullable=False)  # "llm" or "extractive"
    generated_at = Column(DateTime, default=datetime.utcnow)
    
    # Quality metrics
    coverage_score = Column(Float)  # How well summary covers the content
    uniqueness_score = Column(Float)  # How unique compared to other summaries
    
    news_item = relationship("NewsItem", back_populates="summary")
