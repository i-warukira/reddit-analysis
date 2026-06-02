"""
Sentiment Tagger Plugin
Adds sentiment scores and labels to posts and comments.
"""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins import Plugin
from analytics.sentiment import analyze_sentiment


class SentimentTagger(Plugin):
    """Add sentiment analysis to scraped content."""
    
    name = "sentiment_tagger"
    description = "Adds sentiment scores and labels to posts"
    enabled = True
    
    def process_posts(self, posts):
        """Add sentiment to posts."""
        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}"
            score, label = analyze_sentiment(text)
            post['sentiment_score'] = score
            post['sentiment_label'] = label
        
        # Count sentiments
        pos = sum(1 for p in posts if p.get('sentiment_label') == 'positive')
        neg = sum(1 for p in posts if p.get('sentiment_label') == 'negative')
        neu = len(posts) - pos - neg
        
        print(f"   📊 Sentiment: {pos} positive, {neu} neutral, {neg} negative")
        return posts
    
    def process_comments(self, comments):
        """Add sentiment to comments."""
        for comment in comments:
            score, label = analyze_sentiment(comment.get('body', ''))
            comment['sentiment_score'] = score
            comment['sentiment_label'] = label
        
        return comments
