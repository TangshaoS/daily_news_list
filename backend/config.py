"""Configuration management"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # Database
    database_url: str = "sqlite:///./news_summary.db"
    
    # LLM API (Optional)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-3.5-turbo"
    
    # News Sources
    reuters_rss_url: str = "https://www.reuters.com/rssFeed/worldNews"
    bbc_rss_url: str = "http://feeds.bbci.co.uk/news/rss.xml"
    
    # Update Schedule
    update_interval_hours: int = 2
    
    # Summary Configuration
    summary_max_points: int = 7
    summary_min_points: int = 3
    summary_method: str = "llm"  # llm or extractive
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
