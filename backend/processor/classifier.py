"""Classify news into topics"""
import re
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class NewsClassifier:
    """Classify news articles into topics"""
    
    # Topic keywords mapping
    TOPIC_KEYWORDS = {
        'economy': {
            'keywords': ['economy', 'economic', 'gdp', 'inflation', 'unemployment', 'market', 
                        'trade', 'commerce', 'financial', 'bank', 'currency', 'stock', 'bond',
                        'economic', 'recession', 'growth', 'fiscal', 'monetary', '央行', '经济',
                        '通胀', 'GDP', '市场', '贸易', '金融', '股票', '债券'],
            'display_name': '经济',
            'name': 'economy'
        },
        'politics': {
            'keywords': ['politics', 'political', 'government', 'election', 'president', 'parliament',
                        'congress', 'senate', 'policy', 'legislation', 'vote', 'campaign',
                        'democracy', 'republican', 'democrat', '政', '政府', '选举', '总统',
                        '议会', '政策', '立法', '投票'],
            'display_name': '时政',
            'name': 'politics'
        },
        'international': {
            'keywords': ['international', 'global', 'world', 'diplomacy', 'foreign', 'relations',
                        'summit', 'treaty', 'alliance', 'conflict', 'war', 'peace', 'sanctions',
                        'international', 'geopolitics', '国际', '全球', '外交', '关系', '峰会',
                        '条约', '冲突', '战争', '和平', '制裁', '地缘'],
            'display_name': '国际局势',
            'name': 'international'
        },
        'investment': {
            'keywords': ['investment', 'investor', 'portfolio', 'asset', 'fund', 'hedge',
                        'venture', 'capital', 'IPO', 'merger', 'acquisition', 'dividend',
                        'yield', 'return', 'investment', '投资', '投资者', '资产', '基金',
                        'IPO', '并购', '股息', '收益', '回报'],
            'display_name': '投资方向',
            'name': 'investment'
        }
    }
    
    def __init__(self):
        self.topics = list(self.TOPIC_KEYWORDS.keys())
    
    def classify(self, title: str, content: str) -> Optional[str]:
        """
        Classify news into a topic
        
        Args:
            title: News title
            content: News content
        
        Returns:
            Topic name or None if no match
        """
        text = f"{title} {content}".lower()
        
        # Score each topic
        topic_scores = {}
        for topic_name, topic_data in self.TOPIC_KEYWORDS.items():
            score = 0
            keywords = topic_data['keywords']
            
            for keyword in keywords:
                # Count occurrences
                count = len(re.findall(r'\b' + re.escape(keyword.lower()) + r'\b', text))
                score += count
            
            if score > 0:
                topic_scores[topic_name] = score
        
        if not topic_scores:
            return None
        
        # Return topic with highest score
        best_topic = max(topic_scores.items(), key=lambda x: x[1])
        logger.debug(f"Classified as {best_topic[0]} with score {best_topic[1]}")
        return best_topic[0]
    
    def get_topic_display_name(self, topic_name: str) -> str:
        """Get display name for a topic"""
        return self.TOPIC_KEYWORDS.get(topic_name, {}).get('display_name', topic_name)
    
    def get_all_topics(self) -> List[dict]:
        """Get all topics with metadata"""
        return [
            {
                'name': name,
                'display_name': data['display_name']
            }
            for name, data in self.TOPIC_KEYWORDS.items()
        ]
