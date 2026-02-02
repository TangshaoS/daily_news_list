"""
SQLite database for storing news metadata.
Stores only metadata (title, URL, source, timestamps, scores) - no full text.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..models import Category, NewsItem

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path("data/news.db")

# Schema version for migrations
SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
-- News items table
CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    summary TEXT,
    source_id TEXT NOT NULL,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    
    -- Scoring
    source_weight REAL DEFAULT 1.0,
    recency_score REAL DEFAULT 0.0,
    cluster_size INTEGER DEFAULT 1,
    final_score REAL DEFAULT 0.0,
    
    -- Classification
    categories TEXT,  -- JSON array
    keywords TEXT,    -- JSON array
    cluster_id TEXT,
    
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_news_source ON news_items(source_id);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_score ON news_items(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_news_cluster ON news_items(cluster_id);

-- Export history table (tracks what was exported to NotebookLM)
CREATE TABLE IF NOT EXISTS export_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exported_at TEXT NOT NULL,
    filepath TEXT NOT NULL,
    url_count INTEGER NOT NULL,
    categories TEXT,  -- JSON array
    top_score REAL,
    min_score REAL
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


class NewsDatabase:
    """SQLite database wrapper for news items."""
    
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._ensure_directory()
        self._init_schema()
    
    def _ensure_directory(self):
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            
            # Check/set schema version
            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,)
                )
            
            conn.commit()
        
        logger.info(f"Database initialized at {self.db_path}")
    
    def upsert_item(self, item: NewsItem) -> int:
        """
        Insert or update a news item.
        
        Args:
            item: NewsItem to store
        
        Returns:
            Row ID of the inserted/updated item
        """
        now = datetime.now(timezone.utc).isoformat()
        
        # Serialize categories and keywords to JSON
        categories_json = json.dumps([c.value for c in item.categories]) if item.categories else "[]"
        keywords_json = json.dumps(item.keywords) if item.keywords else "[]"
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO news_items (
                    url, normalized_url, title, summary, source_id,
                    published_at, fetched_at, source_weight, recency_score,
                    cluster_size, final_score, categories, keywords, cluster_id,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_url) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    source_weight = excluded.source_weight,
                    recency_score = excluded.recency_score,
                    cluster_size = excluded.cluster_size,
                    final_score = excluded.final_score,
                    categories = excluded.categories,
                    keywords = excluded.keywords,
                    cluster_id = excluded.cluster_id,
                    updated_at = excluded.updated_at
                """,
                (
                    item.url,
                    item.normalized_url or item.url,
                    item.title,
                    item.summary,
                    item.source_id,
                    item.published_at.isoformat() if item.published_at else None,
                    item.fetched_at.isoformat(),
                    item.source_weight,
                    item.recency_score,
                    item.cluster_size,
                    item.final_score,
                    categories_json,
                    keywords_json,
                    item.cluster_id,
                    now,
                )
            )
            conn.commit()
            return cursor.lastrowid
    
    def upsert_items(self, items: list[NewsItem]) -> int:
        """
        Batch insert/update news items.
        
        Args:
            items: List of NewsItem objects
        
        Returns:
            Number of items processed
        """
        for item in items:
            self.upsert_item(item)
        
        logger.info(f"Upserted {len(items)} items to database")
        return len(items)
    
    def get_top_items(
        self,
        limit: int = 50,
        categories: list[Category] | None = None,
        min_score: float = 0.0,
        hours_ago: int | None = None,
    ) -> list[NewsItem]:
        """
        Get top-ranked news items.
        
        Args:
            limit: Maximum number of items to return
            categories: Filter by categories (any match)
            min_score: Minimum final_score threshold
            hours_ago: Only include items from the last N hours
        
        Returns:
            List of NewsItem objects, sorted by score descending
        """
        query = "SELECT * FROM news_items WHERE final_score >= ?"
        params: list = [min_score]
        
        if hours_ago is not None:
            cutoff = datetime.now(timezone.utc)
            from datetime import timedelta
            cutoff = cutoff - timedelta(hours=hours_ago)
            query += " AND published_at >= ?"
            params.append(cutoff.isoformat())
        
        if categories:
            # Filter by category (check if any category matches)
            category_conditions = []
            for cat in categories:
                category_conditions.append("categories LIKE ?")
                params.append(f'%"{cat.value}"%')
            query += f" AND ({' OR '.join(category_conditions)})"
        
        query += " ORDER BY final_score DESC LIMIT ?"
        params.append(limit)
        
        items = []
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                item = self._row_to_item(row)
                items.append(item)
        
        return items
    
    def _row_to_item(self, row: sqlite3.Row) -> NewsItem:
        """Convert a database row to a NewsItem."""
        # Parse categories from JSON
        categories_json = row["categories"] or "[]"
        categories = [Category(c) for c in json.loads(categories_json)]
        
        # Parse keywords from JSON
        keywords_json = row["keywords"] or "[]"
        keywords = json.loads(keywords_json)
        
        # Parse dates
        published_at = None
        if row["published_at"]:
            from dateutil import parser as date_parser
            published_at = date_parser.parse(row["published_at"])
        
        fetched_at = datetime.now(timezone.utc)
        if row["fetched_at"]:
            from dateutil import parser as date_parser
            fetched_at = date_parser.parse(row["fetched_at"])
        
        return NewsItem(
            url=row["url"],
            title=row["title"],
            source_id=row["source_id"],
            published_at=published_at,
            summary=row["summary"] or "",
            normalized_url=row["normalized_url"],
            categories=categories,
            keywords=keywords,
            source_weight=row["source_weight"],
            recency_score=row["recency_score"],
            cluster_size=row["cluster_size"],
            final_score=row["final_score"],
            fetched_at=fetched_at,
            cluster_id=row["cluster_id"],
        )
    
    def record_export(
        self,
        filepath: str,
        url_count: int,
        categories: list[Category],
        top_score: float,
        min_score: float,
    ):
        """Record an export operation to history."""
        now = datetime.now(timezone.utc).isoformat()
        categories_json = json.dumps([c.value for c in categories])
        
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO export_history 
                (exported_at, filepath, url_count, categories, top_score, min_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, filepath, url_count, categories_json, top_score, min_score)
            )
            conn.commit()
    
    def get_item_count(self) -> int:
        """Get total number of items in database."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM news_items")
            return cursor.fetchone()[0]


def init_database(db_path: Path | str = DEFAULT_DB_PATH) -> NewsDatabase:
    """
    Initialize and return a NewsDatabase instance.
    
    Args:
        db_path: Path to the SQLite database file
    
    Returns:
        Initialized NewsDatabase instance
    """
    return NewsDatabase(db_path)
