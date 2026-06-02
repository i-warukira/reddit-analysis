"""
Keyword Extractor Plugin
Extracts and tags posts with top keywords.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins import Plugin
from analytics.sentiment import extract_keywords


class KeywordExtractor(Plugin):
    """Extract and add keywords to posts."""
    
    name = "keyword_extractor"
    description = "Adds top keywords to each post"
    enabled = True
    top_n = 5  # Number of keywords per post
    
    def process_posts(self, posts):
        """Add keywords to each post."""
        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}"
            keywords = extract_keywords([text], top_n=self.top_n)
            post['keywords'] = ','.join([kw for kw, count in keywords])
        
        # Also extract global keywords
        all_texts = [f"{p.get('title', '')} {p.get('selftext', '')}" for p in posts]
        global_keywords = extract_keywords(all_texts, top_n=10)
        
        print(f"   🏷️ Top keywords: {', '.join([kw for kw, _ in global_keywords[:5]])}")
        
        return posts
