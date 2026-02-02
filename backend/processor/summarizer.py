"""News summarization module"""
import json
from abc import ABC, abstractmethod
from typing import List
import logging

logger = logging.getLogger(__name__)


class Summarizer(ABC):
    """Base class for summarizers"""
    
    @abstractmethod
    def summarize(self, title: str, content: str, max_points: int = 7, min_points: int = 3) -> List[str]:
        """
        Generate bullet point summary
        
        Args:
            title: News title
            content: News content
            max_points: Maximum number of bullet points
            min_points: Minimum number of bullet points
        
        Returns:
            List of bullet point strings
        """
        pass


class LLMSummarizer(Summarizer):
    """LLM-based summarizer using OpenAI API"""
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        try:
            import openai
            self.client = openai.OpenAI(api_key=api_key)
            self.model = model
        except ImportError:
            raise ImportError("openai package is required for LLM summarization")
    
    def summarize(self, title: str, content: str, max_points: int = 7, min_points: int = 3) -> List[str]:
        """Generate summary using LLM"""
        try:
            # Truncate content if too long (LLM context limits)
            max_content_length = 3000
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
            
            prompt = f"""请将以下新闻文章总结为{min_points}-{max_points}个要点，每个要点应该：
1. 简洁明了，不超过50字
2. 包含关键信息和数据
3. 按重要性排序
4. 使用中文

标题：{title}

内容：
{content}

请以JSON数组格式返回要点，例如：["要点1", "要点2", "要点3"]
只返回JSON数组，不要其他文字。"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的新闻摘要助手，擅长提取新闻要点。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                # Remove markdown code blocks if present
                if result.startswith("```"):
                    result = result.split("```")[1]
                    if result.startswith("json"):
                        result = result[4:]
                result = result.strip()
                
                bullet_points = json.loads(result)
                
                # Validate and filter
                if isinstance(bullet_points, list):
                    bullet_points = [str(point).strip() for point in bullet_points if point]
                    # Ensure within bounds
                    bullet_points = bullet_points[:max_points]
                    if len(bullet_points) < min_points:
                        logger.warning(f"Generated only {len(bullet_points)} points, expected {min_points}-{max_points}")
                    
                    return bullet_points
                else:
                    logger.error("LLM returned non-list response")
                    return self._fallback_summary(title, content, min_points)
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM JSON response: {e}, response: {result[:100]}")
                return self._fallback_summary(title, content, min_points)
                
        except Exception as e:
            logger.error(f"Error in LLM summarization: {e}")
            return self._fallback_summary(title, content, min_points)
    
    def _fallback_summary(self, title: str, content: str, min_points: int) -> List[str]:
        """Fallback summary when LLM fails"""
        return [f"标题：{title}", f"内容摘要：{content[:200]}..."]


class ExtractiveSummarizer(Summarizer):
    """Extractive summarizer using TF-IDF and sentence ranking"""
    
    def __init__(self):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            self.TfidfVectorizer = TfidfVectorizer
            self.cosine_similarity = cosine_similarity
            self.np = np
        except ImportError:
            raise ImportError("scikit-learn and numpy are required for extractive summarization")
    
    def summarize(self, title: str, content: str, max_points: int = 7, min_points: int = 3) -> List[str]:
        """Generate extractive summary"""
        try:
            # Split content into sentences
            sentences = self._split_sentences(content)
            
            if len(sentences) <= min_points:
                return sentences[:max_points]
            
            # Calculate sentence scores using TF-IDF
            if len(sentences) < 2:
                return sentences
            
            # Combine title and content for better keyword extraction
            full_text = f"{title} {content}"
            
            # Vectorize sentences
            vectorizer = self.TfidfVectorizer(
                max_features=100,
                stop_words='english',
                ngram_range=(1, 2)
            )
            
            try:
                tfidf_matrix = vectorizer.fit_transform([full_text] + sentences)
            except ValueError:
                # Fallback if vectorization fails
                return self._simple_extract(sentences, min_points, max_points)
            
            # Calculate similarity to full text (first vector)
            full_text_vector = tfidf_matrix[0:1]
            sentence_vectors = tfidf_matrix[1:]
            
            similarities = self.cosine_similarity(full_text_vector, sentence_vectors)[0]
            
            # Get top sentences
            top_indices = similarities.argsort()[-max_points:][::-1]
            top_sentences = [sentences[i] for i in sorted(top_indices)]
            
            # Ensure minimum points
            if len(top_sentences) < min_points:
                # Add more sentences if needed
                remaining = [s for i, s in enumerate(sentences) if i not in top_indices]
                top_sentences.extend(remaining[:min_points - len(top_sentences)])
            
            return top_sentences[:max_points]
            
        except Exception as e:
            logger.error(f"Error in extractive summarization: {e}")
            return self._simple_extract(content.split('.'), min_points, max_points)
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        import re
        # Simple sentence splitting
        sentences = re.split(r'[.!?]\s+', text)
        # Filter out very short sentences
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        return sentences
    
    def _simple_extract(self, sentences: List[str], min_points: int, max_points: int) -> List[str]:
        """Simple extraction fallback"""
        # Take first and last sentences, plus some middle ones
        if len(sentences) <= max_points:
            return sentences
        
        selected = []
        # First sentence
        if sentences:
            selected.append(sentences[0])
        
        # Middle sentences
        step = len(sentences) // (max_points - 2) if max_points > 2 else 1
        for i in range(step, len(sentences) - 1, step):
            if len(selected) < max_points - 1:
                selected.append(sentences[i])
        
        # Last sentence
        if len(selected) < max_points and sentences:
            selected.append(sentences[-1])
        
        return selected[:max_points]
