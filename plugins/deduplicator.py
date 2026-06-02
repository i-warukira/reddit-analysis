"""
Deduplicator Plugin
Removes duplicate posts based on permalink.
"""
from plugins import Plugin


class Deduplicator(Plugin):
    """Remove duplicate posts by permalink."""
    
    name = "deduplicator"
    description = "Removes duplicate posts by permalink"
    enabled = True
    
    def process_posts(self, posts):
        """Remove duplicate posts."""
        seen = set()
        unique = []
        duplicates = 0
        
        for post in posts:
            key = post.get('permalink')
            if key and key not in seen:
                seen.add(key)
                unique.append(post)
            else:
                duplicates += 1
        
        if duplicates > 0:
            print(f"   🔄 Removed {duplicates} duplicate posts")
        
        return unique
    
    def process_comments(self, comments):
        """Remove duplicate comments."""
        seen = set()
        unique = []
        
        for comment in comments:
            key = comment.get('comment_id')
            if key and key not in seen:
                seen.add(key)
                unique.append(comment)
        
        return unique
